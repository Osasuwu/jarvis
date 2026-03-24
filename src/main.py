from __future__ import annotations

import argparse
import asyncio
import sys
from uuid import uuid4

from agents.registry import command_to_agent, is_delegation_command
from handlers.telegram import run_telegram_loop
from jarvis.costs import check_daily_budget, record_execution
from jarvis.config import load_config
from jarvis.delegate import delegate_issue, parse_delegate_args
from jarvis.dispatcher import UnsupportedCommandError, build_prompt_for_user_input
from jarvis.executor import execute_query


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Jarvis — personal AI agent")
    parser.add_argument(
        "--command",
        help="Command to execute, e.g. /triage, /delegate #42",
    )
    parser.add_argument(
        "--text",
        help="Plain text message for Jarvis conversation mode",
    )
    parser.add_argument(
        "--telegram",
        action="store_true",
        help="Run Telegram polling bridge",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show prompt preview without executing",
    )
    return parser.parse_args()


async def run_delegation(user_input: str, config) -> int:
    """Handle /delegate command — full pipeline."""
    try:
        repo, issue_number = parse_delegate_args(user_input)
    except ValueError as exc:
        print(f"[jarvis] {exc}", file=sys.stderr)
        return 2

    print(f"[jarvis] delegating #{issue_number} from {repo}")
    print(f"[jarvis] pipeline: fetch → decompose → branch → code → PR")

    result = await delegate_issue(repo, issue_number)

    if result.success:
        print(f"[jarvis] {result.message}")
        if result.coding_summary:
            print(f"\n--- Coding Agent Summary ---\n{result.coding_summary[:1000]}")
        return 0
    else:
        print(f"[jarvis] delegation failed: {result.message}", file=sys.stderr)
        return 1


async def run_command(user_input: str, config) -> int:
    """Build prompt, check budget, execute via SDK, record cost."""
    try:
        prompt = build_prompt_for_user_input(user_input)
    except (UnsupportedCommandError, FileNotFoundError) as exc:
        print(f"[jarvis] {exc}", file=sys.stderr)
        return 2

    agent = command_to_agent(user_input)

    # Daily budget check
    allowed, remaining = check_daily_budget(config.budget.per_day_usd)
    if not allowed:
        print(f"[jarvis] Daily budget exhausted. Limit: ${config.budget.per_day_usd}", file=sys.stderr)
        return 2

    # Per-query budget: use the smaller of agent default and remaining daily
    query_budget = min(agent.max_budget_usd, remaining)

    print(f"[jarvis] agent: {agent.name} | model: {agent.model} | budget: ${query_budget:.2f}")

    session_id = f"cli-{uuid4().hex[:10]}"

    result = await execute_query(
        prompt,
        model=agent.model,
        allowed_tools=agent.allowed_tools,
        max_budget_usd=query_budget,
    )

    if result.cost_usd > 0 or result.input_tokens > 0:
        record_execution(
            model=agent.model,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            cost_usd=result.cost_usd,
            session_id=session_id,
        )
        print(f"[jarvis] tokens: in={result.input_tokens} out={result.output_tokens} cost=${result.cost_usd:.4f}")

    if not result.success:
        print(f"[jarvis] error: {result.error}", file=sys.stderr)
        return 1

    print(result.text)
    return 0


def main() -> int:
    args = parse_args()
    config = load_config()

    if args.telegram:
        try:
            return run_telegram_loop(config)
        except Exception as exc:
            print(f"[jarvis] telegram mode failed: {exc}", file=sys.stderr)
            return 2

    user_input = args.command or args.text
    if not user_input:
        print("[jarvis] --command or --text is required unless --telegram is provided.", file=sys.stderr)
        return 2

    if args.dry_run:
        try:
            prompt = build_prompt_for_user_input(user_input)
        except (UnsupportedCommandError, FileNotFoundError) as exc:
            print(f"[jarvis] {exc}", file=sys.stderr)
            return 2
        agent = command_to_agent(user_input)
        print(f"[jarvis] agent: {agent.name} | model: {agent.model}")
        print(f"[jarvis] prompt preview (first 600 chars):\n{prompt[:600]}")
        return 0

    # Delegation has its own pipeline
    if is_delegation_command(user_input):
        return asyncio.run(run_delegation(user_input, config))

    return asyncio.run(run_command(user_input, config))


if __name__ == "__main__":
    raise SystemExit(main())
