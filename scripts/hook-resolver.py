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


def detect_project_root(path: str | None) -> Path | None:
    """Return the project root for a path, scanning all path components.

    Matches the pattern from commit 2992a9d for consistency with other
    worktree-aware detection in the codebase (pre-compact-backup.py,
    session-context.py, etc.).

    Rightmost match wins so a nested checkout resolves to the inner repo.
    Works from any path (cwd, file path, environment variable, etc.).
    """
    if not path:
        return None
    try:
        parts = Path(path).parts
    except Exception:
        return None

    for part in reversed(parts):
        if part.lower() in KNOWN_PROJECTS:
            # Reconstruct the path up to this part
            try:
                # On Windows: parts = ('C:\\', 'Users', ..., 'jarvis', ...)
                # We want the path ending at 'jarvis'
                idx = len(parts) - 1 - list(reversed(parts)).index(part)
                return Path(*parts[:idx + 1])
            except Exception:
                pass
    return None


def main():
    if len(sys.argv) < 2:
        print("Usage: python hook-resolver.py <script-name> [args...]", file=sys.stderr)
        sys.exit(1)

    script_name = sys.argv[1]
    script_args = sys.argv[2:]

    # Try to detect project root from multiple sources (in priority order):
    # 1. Hook system environment variable (if it sets one)
    # 2. Current working directory
    # 3. This script's own location (as fallback)
    project_root = None
    for candidate in [
        os.environ.get("CLAUDE_HOOK_CWD"),
        os.getcwd(),
        str(Path(__file__).resolve().parent.parent),
    ]:
        if candidate:
            root = detect_project_root(candidate)
            if root:
                project_root = root
                break

    if not project_root:
        print(f"ERROR: Could not detect project root from any source", file=sys.stderr)
        sys.exit(1)

    # Resolve script path
    script_path = project_root / "scripts" / script_name
    if not script_path.exists():
        print(f"ERROR: Script not found: {script_path}", file=sys.stderr)
        sys.exit(1)

    # Invoke the script
    # Use subprocess.call to pass through exit codes
    sys.exit(subprocess.call([sys.executable, str(script_path), *script_args]))


if __name__ == "__main__":
    main()
