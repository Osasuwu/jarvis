from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path

from claude_agent_sdk import (
    ClaudeAgentOptions,
    ResultMessage,
    query,
    CLINotFoundError,
    CLIConnectionError,
    ProcessError,
    ClaudeSDKError,
)


ROOT_DIR = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class ExecutionResult:
    success: bool
    text: str
    error: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


async def execute_query(
    prompt: str,
    *,
    model: str,
    allowed_tools: list[str] | None = None,
    max_budget_usd: float = 0.30,
    cwd: str | Path | None = None,
) -> ExecutionResult:
    """Execute a prompt via Claude Agent SDK query()."""
    options = ClaudeAgentOptions(
        model=model,
        allowed_tools=allowed_tools or [],
        max_budget_usd=max_budget_usd,
        permission_mode="bypassPermissions",
        cwd=cwd or ROOT_DIR,
    )

    result_text = ""
    cost = 0.0
    input_tokens = 0
    output_tokens = 0

    try:
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, ResultMessage):
                result_text = message.result or ""
                cost = message.total_cost_usd or 0.0
                usage = message.usage or {}
                input_tokens = usage.get("input_tokens", 0)
                output_tokens = usage.get("output_tokens", 0)
    except CLINotFoundError:
        return ExecutionResult(
            success=False,
            text="",
            error="Claude Code CLI not found. Install with: npm install -g @anthropic-ai/claude-code",
        )
    except CLIConnectionError as exc:
        return ExecutionResult(
            success=False, text="", error=f"Cannot connect to Claude Code: {exc}"
        )
    except ProcessError as exc:
        return ExecutionResult(
            success=False, text="", error=f"Claude process error: {exc}"
        )
    except ClaudeSDKError as exc:
        return ExecutionResult(
            success=False, text="", error=f"SDK error: {exc}"
        )

    if not result_text.strip():
        return ExecutionResult(
            success=False,
            text="",
            error="Claude returned an empty response.",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
        )

    return ExecutionResult(
        success=True,
        text=result_text,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost,
    )


def run_query_sync(
    prompt: str,
    *,
    model: str,
    allowed_tools: list[str] | None = None,
    max_budget_usd: float = 0.30,
    cwd: str | Path | None = None,
) -> ExecutionResult:
    """Synchronous wrapper for execute_query — for use in sync contexts."""
    return asyncio.run(
        execute_query(
            prompt,
            model=model,
            allowed_tools=allowed_tools,
            max_budget_usd=max_budget_usd,
            cwd=cwd,
        )
    )
