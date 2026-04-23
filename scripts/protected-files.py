"""PreToolUse hook: block writes to protected files.

Checks Edit/Write tool inputs for file paths that match the protected list.
Exits 2 to block if a protected file is targeted.

Covers two surfaces (kept in sync with ``docs/security/agent-boundaries.md``):
- Repo-level files under the jarvis working copy (source of truth).
- User-level files under ``~/.claude/`` installed by ``scripts/install/installer.py``.
  Editing those affects every Claude Code session on the device, so they get
  the same protection as the jarvis-repo source.
"""

import json
import os
import sys
from pathlib import Path

# Repo-level files that require owner review — agents must not modify these.
PROTECTED_FILES = {
    ".mcp.json",
    "config/SOUL.md",
    "CLAUDE.md",
    "mcp-memory/server.py",
    ".claude/settings.json",
    ".gitleaks.toml",
    ".pre-commit-config.yaml",
}

# User-level paths (relative to ``~/.claude/``) that require owner review.
# Expansion target matches installer.py — respects JARVIS_CLAUDE_HOME override.
_USER_LEVEL_PROTECTED_FILES = {
    "settings.json",
    "SOUL.md",
    ".mcp.json",
}


def _user_claude_home() -> str:
    """Return the user-level Claude home directory as a forward-slash string."""
    override = os.environ.get("JARVIS_CLAUDE_HOME")
    home = Path(override).expanduser() if override else (Path.home() / ".claude")
    return home.as_posix().rstrip("/")


def normalize_path(path: str) -> str:
    """Normalize a file path for comparison: forward slashes, strip leading ./"""
    path = path.replace("\\", "/")
    # Strip absolute prefix up to repo root patterns
    for marker in ("/jarvis/", "\\jarvis\\"):
        idx = path.find(marker)
        if idx != -1:
            path = path[idx + len(marker):]
            break
    # Strip leading ./
    if path.startswith("./"):
        path = path[2:]
    return path


def _is_user_level_protected(normalized: str) -> bool:
    """True if `normalized` points at a user-level protected file under ``~/.claude/``.

    Anchored to the resolved user home (or ``$JARVIS_CLAUDE_HOME``) so paths
    like ``some-other-project/.claude/settings.json`` don't false-positive.
    """
    claude_home = _user_claude_home()
    prefix = claude_home + "/"
    if not normalized.startswith(prefix):
        return False
    rel = normalized[len(prefix):]
    if rel in _USER_LEVEL_PROTECTED_FILES:
        return True
    # skills/<name>/SKILL.md — any user-level skill definition.
    parts = rel.split("/")
    return len(parts) == 3 and parts[0] == "skills" and parts[2] == "SKILL.md"


def is_protected(file_path: str) -> bool:
    """Check if a file path matches any protected file (repo-level or user-level)."""
    normalized = normalize_path(file_path)
    if normalized in PROTECTED_FILES:
        return True
    return _is_user_level_protected(normalized)


def block(file_path: str):
    """Output deny JSON and exit 2."""
    result = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                f"BLOCKED: '{file_path}' is a protected file. "
                "Document the needed change in the PR description instead."
            ),
        }
    }
    json.dump(result, sys.stdout)
    sys.exit(2)


def main():
    raw = sys.stdin.read()
    if not raw.strip():
        sys.exit(0)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        sys.exit(0)

    tool_input = data.get("tool_input", {})
    if not isinstance(tool_input, dict):
        sys.exit(0)

    file_path = tool_input.get("file_path", "")
    if not file_path:
        sys.exit(0)

    if is_protected(file_path):
        block(file_path)

    sys.exit(0)


if __name__ == "__main__":
    main()
