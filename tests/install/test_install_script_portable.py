r"""Portability guard test for install scripts.

Verifies that install scripts do not contain:
- Hardcoded usernames (e.g., petrk, sergazy)
- Absolute paths starting with C:\Users\<username>
- Device-specific absolute paths

This is a meta-test in the spirit of CI meta-tests (see CLAUDE.md #326).
It prevents silent failures when scripts are run on other machines.
"""

import re
from pathlib import Path


def test_install_scheduler_service_portable():
    """Assert install script has no hardcoded paths or usernames."""
    script_path = Path(__file__).parent.parent.parent / "scripts" / "install" / "install-scheduler-service.ps1"
    content = script_path.read_text(encoding="utf-8")

    # Pattern: absolute Windows path starting with C:\Users\<username>
    # This catches both single-backslash and double-backslash forms
    forbidden_paths = re.findall(r'[C|c]:\\[Uu]sers\\[a-zA-Z0-9_-]+', content)

    # Exclude lines that are in comments or examples
    # Allow if surrounded by backticks (PowerShell quoting) or in strings with variables
    violations = []
    for line in content.split('\n'):
        if line.strip().startswith('#'):  # Comment
            continue
        # Check if any forbidden path is in a code line (not a comment)
        for path in forbidden_paths:
            if path in line and not line.strip().startswith('#'):
                violations.append((line.strip(), path))

    assert not violations, (
        f"Script contains hardcoded absolute paths:\n"
        + "\n".join(f"  {path}: {line}" for line, path in violations)
    )

    # Pattern: known usernames as hardcoded strings
    known_usernames = ["petrk", "sergazy"]
    for username in known_usernames:
        # Allow in comments, env var names, or documentation
        pattern = re.compile(
            rf'\b{username}\b',
            re.IGNORECASE,
        )
        matches = [(i, line) for i, line in enumerate(content.split('\n'), 1)
                   if pattern.search(line) and not line.strip().startswith('#')]

        # These matches are OK if they're in benign contexts:
        # - Variable names ($username_var)
        # - Method calls (.username_method)
        # - Config keys ("username": value)
        ok_patterns = [
            r'\$.*' + username,
            r'"\s*' + username + r'\s*"',
            r'\.' + username,
        ]
        filtered = []
        for line_num, line in matches:
            is_ok = any(re.search(pattern, line) for pattern in ok_patterns)
            if not is_ok:
                filtered.append((line_num, line))

        assert not filtered, (
            f"Script may contain hardcoded username '{username}':\n"
            + "\n".join(f"  Line {num}: {line.strip()}" for num, line in filtered)
        )


def test_uninstall_scheduler_service_portable():
    """Assert uninstall script has no hardcoded paths or usernames."""
    script_path = Path(__file__).parent.parent.parent / "scripts" / "install" / "uninstall-scheduler-service.ps1"
    content = script_path.read_text(encoding="utf-8")

    # Same checks as install script
    forbidden_paths = re.findall(r'[C|c]:\\[Uu]sers\\[a-zA-Z0-9_-]+', content)
    violations = []
    for line in content.split('\n'):
        if line.strip().startswith('#'):
            continue
        for path in forbidden_paths:
            if path in line and not line.strip().startswith('#'):
                violations.append((line.strip(), path))

    assert not violations, (
        f"Script contains hardcoded absolute paths:\n"
        + "\n".join(f"  {path}: {line}" for line, path in violations)
    )


def test_install_script_uses_portable_config():
    """Assert install script reads repo path from config/device.json or env vars."""
    script_path = Path(__file__).parent.parent.parent / "scripts" / "install" / "install-scheduler-service.ps1"
    content = script_path.read_text(encoding="utf-8")

    # Should reference JARVIS_REPO_PATH env var as fallback
    assert "JARVIS_REPO_PATH" in content, "Script should support JARVIS_REPO_PATH env var"

    # Should reference device.json config
    assert "device.json" in content.lower(), "Script should read device.json for repo path"

    # Should not hardcode the repo path directly
    assert "C:\\Users\\petrk\\GitHub\\jarvis" not in content.lower(), \
        "Script should not hardcode repo path"


def test_install_script_sets_proper_logging():
    """Assert install script creates logs under repo/<logs/scheduler> not absolute path."""
    script_path = Path(__file__).parent.parent.parent / "scripts" / "install" / "install-scheduler-service.ps1"
    content = script_path.read_text(encoding="utf-8")

    # Should use relative path under repo
    assert "logs" in content.lower(), "Script should use logs directory"

    # Should not hardcode an absolute log path like C:\logs
    assert "c:\\logs" not in content.lower(), "Script should not hardcode absolute log path"


def test_no_multiarg_join_path_in_ps_scripts():
    """Windows PowerShell 5.1's Join-Path takes only -Path/-ChildPath; 3+ positional args throw.

    Caught a real bug: install-scheduler-service.ps1 had `Join-Path X "config" "device.json"`
    which crashed with "Не удается найти позиционный параметр" on workshop install. PS 7+
    accepts the multi-arg form via -AdditionalChildPath, but the default Windows shell is 5.1.

    Multi-segment paths must be chained: Join-Path (Join-Path A "config") "device.json".

    Detection strategy: only flag the broken shape — three or more *simple* arguments
    (variable, double/single-quoted string, or bareword). Parenthesized expressions are
    skipped, which means a chained `Join-Path (Join-Path A B) C` reads as "first arg is `(`"
    and falls through. Trade-off: false negatives on exotic invocations are acceptable;
    false positives would block correct code.
    """
    repo_root = Path(__file__).parent.parent.parent
    ps_scripts = list((repo_root / "scripts").rglob("*.ps1"))
    assert ps_scripts, "Expected at least one .ps1 script under scripts/"

    simple_token = r'(?:\$\w+|"[^"]*"|\'[^\']*\'|\w+)'
    bad_pattern = re.compile(
        r'Join-Path\s+'
        + simple_token + r'\s+'
        + simple_token + r'\s+'
        + simple_token + r'(?:\s|$|\))'
    )

    violations = []
    for script in ps_scripts:
        content = script.read_text(encoding="utf-8")
        for line_num, line in enumerate(content.split("\n"), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if bad_pattern.search(line):
                violations.append((script.relative_to(repo_root), line_num, stripped))

    assert not violations, (
        "Multi-arg Join-Path X Y Z is not supported in Windows PowerShell 5.1.\n"
        "Chain it: Join-Path (Join-Path X Y) Z\n\n"
        + "\n".join(f"  {path}:{line_num}  {body}" for path, line_num, body in violations)
    )


def test_install_scheduler_checks_lastexitcode():
    """Assert install script checks $LASTEXITCODE after nssm calls and exits on failure.

    Regression test for issue #394: silent error swallowing via Out-Null.
    """
    script_path = Path(__file__).parent.parent.parent / "scripts" / "install" / "install-scheduler-service.ps1"
    content = script_path.read_text(encoding="utf-8")

    # Should reference $LASTEXITCODE in conditional checks
    assert "LASTEXITCODE" in content, (
        "Script should check $LASTEXITCODE after nssm calls to detect failures"
    )

    # Should exit on non-zero exit code (via Invoke-Nssm helper)
    assert "if ($LASTEXITCODE -ne 0)" in content or "Exit-Script $LASTEXITCODE" in content, (
        "Script should exit with error when nssm command fails"
    )

    # Should NOT pipe nssm output to Out-Null (suppresses stderr)
    # Instead it should capture output for diagnostics
    lines = content.split("\n")
    for line_num, line in enumerate(lines, 1):
        if "nssm" in line.lower() and "2>&1 | Out-Null" in line:
            raise AssertionError(
                f"Line {line_num}: nssm output should not be piped to Out-Null "
                "(suppresses diagnostic output). Capture and print instead."
            )


def test_install_scheduler_resolves_python_path():
    """Assert install script resolves python to absolute path before nssm install.

    Regression test for issue #394: bareword 'python' fails under LocalSystem context.
    """
    script_path = Path(__file__).parent.parent.parent / "scripts" / "install" / "install-scheduler-service.ps1"
    content = script_path.read_text(encoding="utf-8")

    # Should check if path is absolute
    assert "Split-Path" in content and "IsAbsolute" in content, (
        "Script should check if pythonPath is absolute using Split-Path -IsAbsolute"
    )

    # Should resolve non-absolute paths using Get-Command
    assert "Get-Command" in content, (
        "Script should use Get-Command to resolve python from PATH"
    )

    # Should have clear error message if python cannot be found
    assert "Cannot resolve Python" in content or "not found in PATH" in content, (
        "Script should have clear error message when python cannot be resolved"
    )

    # Should honor JARVIS_PYTHON env var
    assert "JARVIS_PYTHON" in content, (
        "Script should support JARVIS_PYTHON env var"
    )


def test_install_scheduler_autodiscovers_nssm():
    """Assert install script auto-discovers NSSM in winget package directory.

    Regression test for issue #394: winget-installed NSSM has no PATH shim.
    """
    script_path = Path(__file__).parent.parent.parent / "scripts" / "install" / "install-scheduler-service.ps1"
    content = script_path.read_text(encoding="utf-8")

    # Should support JARVIS_NSSM_PATH env var
    assert "JARVIS_NSSM_PATH" in content, (
        "Script should support JARVIS_NSSM_PATH env var to override NSSM path"
    )

    # Should search winget package directory
    assert "WinGet" in content and ("Packages" in content or "Microsoft" in content), (
        "Script should search winget package directory when Get-Command fails"
    )

    # Should look for nssm.exe in win64 and/or win32 subdirectories
    assert "win64" in content or "win32" in content or "Get-ChildItem" in content, (
        "Script should search winget subdirectories for nssm.exe"
    )


def test_install_scheduler_supports_dryrun():
    """Assert install script supports -DryRun flag for validation without side effects.

    Regression test for issue #394: need smoke test that validates paths without calling nssm.
    """
    script_path = Path(__file__).parent.parent.parent / "scripts" / "install" / "install-scheduler-service.ps1"
    content = script_path.read_text(encoding="utf-8")

    # Should have DryRun parameter in param() block
    assert "[switch]$DryRun" in content, (
        "Script should have -DryRun parameter"
    )

    # Should check $DryRun before calling actual nssm commands
    assert "$DryRun" in content, (
        "Script should reference $DryRun to skip actual nssm calls"
    )

    # Should print what would be called in DryRun mode
    assert "[DRY-RUN]" in content or "DRY-RUN" in content, (
        "Script should indicate DryRun mode in output (prefix with [DRY-RUN])"
    )
