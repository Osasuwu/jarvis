"""Hook path resolver — worktree-aware invocation wrapper.

When a hook is invoked from a worktree, this script:
1. Detects the project root using the 2992a9d pattern (path-component scan)
2. Resolves the target script's path relative to that root
3. Invokes the script

This ensures a worktree session runs its own copy of the script (potentially
with newer fixes), not the main checkout's.

Usage:
  python hook-resolver.py <script-name> [args...]

Example (in settings.json):
  "python scripts/hook-resolver.py memory-dedup-check.py"
"""

import os
import subprocess
import sys
from pathlib import Path


KNOWN_PROJECTS = {"jarvis", "redrobot"}
# Directories under the repo root that host worktree checkouts
_WORKTREE_PARENTS = {".claude", ".reactive", ".sandcastle"}


def detect_project_root(path: str | None) -> Path | None:
    """Return the project root for a path, scanning all path components.

    Matches the pattern from commit 2992a9d for consistency with other
    worktree-aware detection in the codebase (pre-compact-backup.py,
    session-context.py, etc.).

    Rightmost match wins so a nested checkout resolves to the inner repo.
    Extends the root into the worktree directory when cwd is inside
    <repo>/<worktree-parent>/worktrees/<name> (the worktree has its own
    scripts/ checkout).  Works from any path (cwd, file path, environment
    variable, etc.).
    """
    if not path:
        return None
    try:
        parts = Path(path).parts
    except Exception:
        return None

    for i in range(len(parts) - 1, -1, -1):
        if parts[i].lower() in KNOWN_PROJECTS:
            root = Path(*parts[: i + 1])
            rest = parts[i + 1 :]
            # Extend root into the worktree directory so each worktree session
            # resolves scripts from its own checkout, not the main repo copy.
            if len(rest) >= 3 and rest[0] in _WORKTREE_PARENTS and rest[1] == "worktrees":
                root = root.joinpath(*rest[:3])
            return root
    return None


def main():
    if len(sys.argv) < 2:
        print("Usage: python hook-resolver.py <script-name> [args...]", file=sys.stderr)
        sys.exit(2)

    script_name = sys.argv[1]
    script_args = sys.argv[2:]

    # Try to detect project root from multiple sources (in priority order):
    # 1. CLAUDE_PROJECT_DIR — Claude Code's documented env var for the project root
    # 2. Current working directory
    # 3. This script's own location (as fallback)
    project_root = None
    for candidate in [
        os.environ.get("CLAUDE_PROJECT_DIR"),
        os.getcwd(),
        str(Path(__file__).resolve().parent.parent),
    ]:
        if candidate:
            root = detect_project_root(candidate)
            if root:
                project_root = root
                break

    if not project_root:
        print("ERROR: Could not detect project root from any source", file=sys.stderr)
        # Exit 2 (blocking) so security-critical hooks like secret-scanner.py
        # fail closed rather than silently skipping enforcement.
        sys.exit(2)

    # Resolve script path
    script_path = project_root / "scripts" / script_name
    if not script_path.exists():
        print(f"ERROR: Script not found: {script_path}", file=sys.stderr)
        sys.exit(2)

    # Invoke the script; pass through its exit code directly.
    sys.exit(subprocess.call([sys.executable, str(script_path), *script_args]))


if __name__ == "__main__":
    main()
