"""AC4: this PR must not delete or edit the old scripts/*.py hooks, nor the
user-level hook registration — those are deferred to a later "contract
slice" issue (#1800). This is a regression tripwire, not new behavior: it
proves the old, principal-aware scripts/protected-files.py is untouched
(still imports principal and lib.harness) alongside the new standalone
.claude/hooks/ copies.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"


def test_old_hook_scripts_still_exist():
    for name in ("secret-scanner.py", "protected-files.py", "device-info.py"):
        assert (SCRIPTS_DIR / name).exists(), f"scripts/{name} must not be deleted in this PR"


def test_old_protected_files_still_imports_principal_and_harness():
    text = (SCRIPTS_DIR / "protected-files.py").read_text(encoding="utf-8")
    assert "import principal" in text, (
        "scripts/protected-files.py must keep its principal-aware implementation "
        "untouched in this PR — the standalone rewrite lives only under .claude/hooks/"
    )
    assert "from lib.harness import home" in text, (
        "scripts/protected-files.py must keep its lib.harness seam untouched in this PR"
    )
