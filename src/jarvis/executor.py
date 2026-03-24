from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class ExecutionResult:
    return_code: int
    stdout: str
    stderr: str


def execute_prompt_with_claude(prompt: str) -> ExecutionResult:
    claude_cmd = os.getenv("CLAUDE_CLI_PATH", "claude")
    try:
        completed = subprocess.run(
            [claude_cmd, "-p", prompt, "--bare"],
            check=False,
            text=True,
            capture_output=True,
        )
    except FileNotFoundError:
        return ExecutionResult(
            return_code=127,
            stdout="",
            stderr=(
                "Claude CLI not found. Install `claude` or set CLAUDE_CLI_PATH to its absolute path."
            ),
        )

    return ExecutionResult(
        return_code=completed.returncode,
        stdout=completed.stdout or "",
        stderr=completed.stderr or "",
    )
