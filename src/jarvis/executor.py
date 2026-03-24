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
    max_budget_usd = os.getenv("JARVIS_MAX_BUDGET_USD")
    timeout_sec = int(os.getenv("JARVIS_EXEC_TIMEOUT_SEC", "600"))
    model_lower = model.lower()
    if "haiku" in model_lower:
        cli_model = "haiku"
    elif "sonnet" in model_lower:
        cli_model = "sonnet"
    elif "opus" in model_lower:
        cli_model = "opus"
    else:
        cli_model = model

    command = [claude_cmd, "--model", cli_model, "-p", prompt, "--bare", "--output-format", "text"]
    if max_budget_usd:
        command.extend(["--max-budget-usd", max_budget_usd])

    try:
        completed = subprocess.run(
            command,
            check=False,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=timeout_sec,
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
    except subprocess.TimeoutExpired:
        return ExecutionResult(
            return_code=124,
            stdout="",
            stderr=(
                f"Claude CLI timeout after {timeout_sec}s. "
                "Increase JARVIS_EXEC_TIMEOUT_SEC or simplify the request."
            ),
            input_tokens=input_tokens,
            output_tokens=0,
            estimated_cost_usd=0.0,
        )

    output_text = completed.stdout or ""
    output_tokens = estimate_tokens(output_text)
    estimated_cost_usd = estimate_cost_usd(model, input_tokens, output_tokens)
    stderr_text = completed.stderr or ""

    if completed.returncode == 0 and not output_text.strip() and not stderr_text.strip():
        stderr_text = "Claude CLI returned an empty response."

    return ExecutionResult(
        return_code=completed.returncode,
        stdout=output_text,
        stderr=stderr_text,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost_usd=estimated_cost_usd,
    )
