from __future__ import annotations

import argparse
import asyncio
import sys
from uuid import uuid4

from handlers.telegram import run_telegram_loop
from jarvis.config import load_config
from jarvis.dispatcher import (
    UnsupportedCommandError,
    build_prompt_for_user_input,
    dispatch_skill,
    get_skill,
)


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


async def run_command(user_input: str, config) -> int:
    """Unified command execution via dispatcher auto-discovery."""
    session_id = f"cli-{uuid4().hex[:10]}"

    result = await dispatch_skill(user_input, config, session_id=session_id)

    if result.cost_usd > 0 or result.input_tokens > 0:
        print(f"[jarvis] tokens: in={result.input_tokens} out={result.output_tokens} cost=${result.cost_usd:.4f}")

    if not result.success:
        print(f"[jarvis] error: {result.text}", file=sys.stderr)
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

        command = user_input.split(maxsplit=1)[0] if user_input.startswith("/") else "chat"
        skill = get_skill(command)
        model = skill.model if skill else "haiku"
        print(f"[jarvis] skill: {command} | model: {model}")
        print(f"[jarvis] prompt preview (first 600 chars):\n{prompt[:600]}")
        return 0

    return asyncio.run(run_command(user_input, config))


if __name__ == "__main__":
    raise SystemExit(main())
