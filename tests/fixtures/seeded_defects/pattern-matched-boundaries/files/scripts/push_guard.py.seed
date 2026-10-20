"""Block an agent's push to the default branch.

A PreToolUse hook for the Bash tool. It reads the hook payload on stdin
(``{"tool_input": {"command": "..."}}``) and exits 2 with a reason on stderr
when the command pushes to main or master, so the harness denies the call.
Every other command exits 0.
"""

from __future__ import annotations

import json
import sys

DENIED = ("git push origin main", "git push origin master")


def is_blocked(command: str) -> bool:
    """Whether ``command`` pushes to the default branch."""
    text = command.strip()
    return any(text == denied or text.startswith(denied + " ") for denied in DENIED)


def main() -> int:
    payload = json.load(sys.stdin)
    command = (payload.get("tool_input") or {}).get("command", "")
    if is_blocked(command):
        print("push to the default branch is not allowed", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
