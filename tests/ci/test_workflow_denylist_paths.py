"""Every path a workflow's `--disallowed-tools` denylist names must exist (#1965).

`agent-dispatch.yml` denied `Edit(./scripts/secret-scanner.py)`, `Edit(./scripts/protected-files.py)`
and `Edit(./scripts/principal.py)` for weeks after #1800/#1923 moved those files out. A path rule
for a file that is not there protects nothing and never errors, so a renamed guard file silently
drops out of the denylist while the run stays green.

The walk covers every workflow's `claude_args`, not just the dispatch worker's: the invariant is
"a denylist entry names something real", and a copy of it per workflow leaves the next workflow's
denylist unguarded.

Only the file-tool rules (`Edit(path)` and kin) carry a path. `Bash(git push:*)` is a command
prefix with no file behind it, so it is out of scope by construction.
"""

from __future__ import annotations

import glob
import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"

# Claude Code's permission rules that take a file path; `Edit(path)` covers Write/NotebookEdit too.
PATH_TOOLS = ("Edit", "Write", "Read", "NotebookEdit")

_DISALLOWED_RE = re.compile(r'--disallowed-tools\s+((?:"[^"]*"\s*)+)')
_RULE_RE = re.compile(r"^(\w+)\((.*)\)$")


def denylist_path_rules(claude_args: str) -> list[str]:
    """Path patterns named by file-tool rules in every `--disallowed-tools` list of `claude_args`."""
    patterns: list[str] = []
    for raw in _DISALLOWED_RE.findall(claude_args):
        for entry in re.findall(r'"([^"]*)"', raw):
            match = _RULE_RE.match(entry)
            if match and match.group(1) in PATH_TOOLS:
                patterns.append(match.group(2))
    return patterns


def missing_paths(patterns: list[str], root: Path) -> list[str]:
    """Patterns (relative to `root`, leading `./` allowed) that match nothing on disk."""
    return [p for p in patterns if not glob.glob(str(root / p.removeprefix("./")), recursive=True)]


def _claude_args_by_workflow() -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for workflow in sorted(WORKFLOWS_DIR.glob("*.yml")):
        doc = yaml.safe_load(workflow.read_text(encoding="utf-8"))
        for job in (doc.get("jobs") or {}).values():
            for step in job.get("steps") or []:
                args = (step.get("with") or {}).get("claude_args")
                if isinstance(args, str):
                    found.setdefault(workflow.name, []).append(args)
    return found


def test_every_denylist_path_exists_on_disk() -> None:
    dead: list[str] = []
    checked: set[str] = set()
    for name, arg_blocks in _claude_args_by_workflow().items():
        for args in arg_blocks:
            patterns = denylist_path_rules(args)
            checked.update(f"{name}:{p}" for p in patterns)
            dead.extend(f"{name}: {p}" for p in missing_paths(patterns, REPO_ROOT))
    assert not dead, (
        "denylist entries naming a path that does not exist (a renamed or moved guard "
        f"file silently loses its protection): {dead}"
    )
    # The walk must reach the dispatch worker's guard-file rules, or a refactor of the
    # workflow's shape would turn this into a loop over nothing.
    assert "lane.yml:./.claude/settings.json" in checked


def test_checker_flags_a_planted_dead_path(tmp_path: Path) -> None:
    (tmp_path / "hooks").mkdir()
    (tmp_path / "hooks" / "guard.py").write_text("", encoding="utf-8")
    (tmp_path / "keep.toml").write_text("", encoding="utf-8")
    args = (
        '--max-turns 5 --disallowed-tools "Edit(./hooks/**)" "Edit(./keep.toml)" '
        '"Edit(./scripts/gone.py)" "Bash(git push:*)"'
    )
    patterns = denylist_path_rules(args)
    assert patterns == ["./hooks/**", "./keep.toml", "./scripts/gone.py"]
    assert missing_paths(patterns, tmp_path) == ["./scripts/gone.py"]
