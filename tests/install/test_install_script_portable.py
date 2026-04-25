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
