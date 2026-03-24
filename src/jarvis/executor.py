from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass

from jarvis.costs import estimate_cost_usd, estimate_tokens


@dataclass(frozen=True)
class ExecutionResult:
    return_code: int
    stdout: str
    stderr: str
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0.0


def execute_prompt_with_claude(prompt: str, model: str) -> ExecutionResult:
    input_tokens = estimate_tokens(prompt)
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
            input_tokens=input_tokens,
            output_tokens=0,
            estimated_cost_usd=0.0,
        )

    output_text = completed.stdout or ""
    output_tokens = estimate_tokens(output_text)
    estimated_cost_usd = estimate_cost_usd(model, input_tokens, output_tokens)

    return ExecutionResult(
        return_code=completed.returncode,
        stdout=output_text,
        stderr=completed.stderr or "",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost_usd=estimated_cost_usd,
    )
