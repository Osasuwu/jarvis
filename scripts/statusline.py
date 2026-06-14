#!/usr/bin/env python3
"""Status line for Claude Code.

Reads the status-line JSON payload on stdin and prints a single line:

    <model> | ctx <N>% | <git-branch>

Replaces the old (now-unsupported) settings.json `statusLine.type: "inline"`
+ `format: "{model} | ctx {context_usage}% | {git_branch}"`, which Claude Code
no longer recognises (only `type: "command"` is valid). Wired in via
settings.json -> statusLine.command.

Payload fields used (see Claude Code status-line schema):
- model.display_name          -> model name
- context_window.used_percentage -> context usage (may be null early in session)
- cwd                         -> dir to resolve the git branch from
"""
import json
import subprocess
import sys


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        # No/invalid payload: emit nothing rather than a Python traceback.
        return

    model = data.get("model", {}).get("display_name") or "?"

    cw = data.get("context_window") or {}
    used = cw.get("used_percentage")
    ctx = f"ctx {int(used)}%" if isinstance(used, (int, float)) else "ctx -"

    cwd = data.get("cwd") or data.get("workspace", {}).get("current_dir") or "."
    try:
        branch = subprocess.run(
            ["git", "-C", cwd, "branch", "--show-current"],
            capture_output=True,
            text=True,
            timeout=2,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        branch = ""
    branch = branch or "no repo"

    print(f"{model} | {ctx} | {branch}")


if __name__ == "__main__":
    main()
