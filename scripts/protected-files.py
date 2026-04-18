"""PreToolUse hook: block writes to protected files.

Checks Edit/Write tool inputs for file paths that match the protected list.
Exits 2 to block if a protected file is targeted.
"""

import json
import sys

# Files that require owner review — agents must not modify these.
PROTECTED_FILES = {
    ".mcp.json",
    "config/SOUL.md",
    "CLAUDE.md",
    "mcp-memory/server.py",
    ".claude/settings.json",
    ".gitleaks.toml",
    ".pre-commit-config.yaml",
}


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


def is_protected(file_path: str) -> bool:
    """Check if a file path matches any protected file."""
    normalized = normalize_path(file_path)
    return normalized in PROTECTED_FILES


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
