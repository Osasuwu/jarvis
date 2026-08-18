"""Hook path resolver — worktree- and cross-project-aware invocation wrapper.

settings.json is registered at the user level (`~/.claude/settings.json`) and
its hooks fire in EVERY Claude Code session, not just jarvis ones. A path
baked at install time pins every hook to whichever jarvis checkout was live
when `install.ps1 -Apply` ran, breaking any other worktree session (#1186).
Templating hook commands to `$CLAUDE_PROJECT_DIR/scripts/...` fixes that for
jarvis sessions but breaks EVERY non-jarvis session, since `$CLAUDE_PROJECT_DIR`
there resolves to that project's own root, which has no `scripts/` dir with
jarvis's hook files (#1565).

This wrapper resolves the right jarvis checkout to invoke scripts from,
regardless of which project's session invoked it:

1. Detects the project root using the 2992a9d path-component-scan pattern,
   tried against `$CLAUDE_PROJECT_DIR`, then cwd, then this script's own
   on-disk location (in that priority order).
2. If the detected root is a jarvis checkout, resolves the target script
   there — extending into the caller's own worktree when it's a jarvis
   worktree session, so each worktree runs its own copy (#1186 case).
3. If no candidate resolves to a jarvis checkout (a non-jarvis session, with
   or without its own worktree), falls through to this script's own
   location — since settings.json bakes an ABSOLUTE path to hook-resolver.py
   itself (never `$CLAUDE_PROJECT_DIR`-templated), that's always physically
   inside the canonical jarvis install.

Usage:
  python hook-resolver.py [--soft] <script-name> [args...]

`--soft` makes a resolution failure exit 1 (non-blocking — Claude Code shows
the stderr message and continues) instead of the default exit 2 (blocking).
Security-critical enforcement hooks (secret-scanner.py, protected-files.py,
record-decision-gate.py, memory-dedup-check.py) must NOT pass --soft: a hook
that silently skips enforcement on resolution failure defeats the point of
having it.

Example (in settings.json, install-time-baked absolute invocation path):
  "python C:/Users/petrk/GitHub/jarvis/scripts/hook-resolver.py --soft session-context.py"
  "python C:/Users/petrk/GitHub/jarvis/scripts/hook-resolver.py secret-scanner.py"
"""

import os
import subprocess
import sys
from pathlib import Path


KNOWN_PROJECTS = {"jarvis", "redrobot"}
# Directories under a repo root that host worktree checkouts.
_WORKTREE_PARENTS = {".claude", ".reactive", ".sandcastle"}


def detect_project_root(path: str | None) -> Path | None:
    """Return the project root for a path, scanning all path components.

    Matches the pattern from commit 2992a9d for consistency with other
    worktree-aware detection in the codebase (pre-compact-backup.py,
    session-context.py, etc.).

    Rightmost match wins so a nested checkout resolves to the inner repo.
    Extends the root into the worktree directory when the remaining path
    is <worktree-parent>/worktrees/<name> (the worktree has its own scripts/
    checkout) — so a jarvis worktree session resolves to ITS OWN root, not
    the main checkout's. A non-jarvis worktree (redrobot, or any other repo)
    is unaffected: `parts[i].lower()` only matches on a KNOWN_PROJECTS
    component, so "we're inside *some* worktree" alone never satisfies this.
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
            if len(rest) >= 3 and rest[0] in _WORKTREE_PARENTS and rest[1] == "worktrees":
                root = root.joinpath(*rest[:3])
            return root
    return None


def resolve_script(script_name: str) -> Path | None:
    """Find `scripts/<script_name>` under the best-matching project root.

    Tries $CLAUDE_PROJECT_DIR, then cwd, then this file's own location, in
    that order — the first candidate whose detected root actually contains
    the target script wins. This is what lets a non-jarvis session fall
    through to the canonical jarvis install: candidates 1-2 detect no
    jarvis/redrobot root (or detect one lacking the script), so resolution
    falls to candidate 3, which — since hook-resolver.py's own invocation
    path in settings.json is install-time-baked absolute, never
    $CLAUDE_PROJECT_DIR-templated — is always physically inside jarvis.
    """
    for candidate in [
        os.environ.get("CLAUDE_PROJECT_DIR"),
        os.getcwd(),
        str(Path(__file__).resolve().parent.parent),
    ]:
        root = detect_project_root(candidate)
        if root is None:
            continue
        script_path = root / "scripts" / script_name
        if script_path.exists():
            return script_path
    return None


def main() -> None:
    args = sys.argv[1:]
    soft = False
    if args and args[0] == "--soft":
        soft = True
        args = args[1:]

    fail_code = 1 if soft else 2

    if not args:
        print("Usage: python hook-resolver.py [--soft] <script-name> [args...]", file=sys.stderr)
        sys.exit(fail_code)

    script_name, script_args = args[0], args[1:]

    script_path = resolve_script(script_name)
    if script_path is None:
        print(f"ERROR: Could not resolve script {script_name!r} from any candidate root", file=sys.stderr)
        sys.exit(fail_code)

    sys.exit(subprocess.call([sys.executable, str(script_path), *script_args]))


if __name__ == "__main__":
    main()
