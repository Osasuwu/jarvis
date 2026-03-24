from __future__ import annotations

import argparse
import os
import sys
from uuid import uuid4

from agents.registry import command_to_agent
from handlers.telegram import run_telegram_loop
from jarvis.costs import record_execution
from jarvis.config import load_config
from jarvis.dispatcher import UnsupportedCommandError, build_prompt_for_command
from jarvis.executor import execute_prompt_with_claude



def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Jarvis command runner")
    parser.add_argument(
        "--command",
        help="Command to execute, e.g. /triage, /weekly-report, /issue-health",
    )
    parser.add_argument(
        "--telegram",
        action="store_true",
        help="Run Telegram polling bridge",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="If set, execute via `claude -p` instead of dry-run output",
    )
    return parser.parse_args()



def run_claude(prompt: str, model: str) -> int:
    result = execute_prompt_with_claude(prompt, model=model)
    session_id = os.getenv("JARVIS_SESSION_ID", f"cli-{uuid4().hex[:10]}")
    if result.return_code == 0:
        run_cost = record_execution(
            model=model,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            session_id=session_id,
        )
        print(
            f"[jarvis] estimated usage: in={result.input_tokens}, out={result.output_tokens}, cost=${run_cost:.6f}"
        )
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    return result.return_code



def main() -> int:
    args = parse_args()
    config = load_config()

    if args.telegram:
        try:
            return run_telegram_loop(config)
        except Exception as exc:  # pragma: no cover - top-level safety
            print(f"[jarvis] telegram mode failed: {exc}", file=sys.stderr)
            return 2

    if not args.command:
        print("[jarvis] --command is required unless --telegram is provided.", file=sys.stderr)
        return 2

    try:
        prompt = build_prompt_for_command(args.command)
    except (UnsupportedCommandError, FileNotFoundError) as exc:
        print(f"[jarvis] {exc}", file=sys.stderr)
        return 2

    selected_agent = command_to_agent(args.command)

    print(f"[jarvis] command: {args.command}")
    print(f"[jarvis] default model: {config.models.default_model}")
    print(f"[jarvis] selected agent: {selected_agent.name} ({selected_agent.model})")

    if not args.execute:
        print("[jarvis] dry-run mode. Prompt preview (first 600 chars):")
        print(prompt[:600])
        print("\n[jarvis] use --execute to run through Claude CLI.")
        return 0

    if not config.anthropic_api_key:
        print("[jarvis] ANTHROPIC_API_KEY is not set.", file=sys.stderr)
        return 2

    return run_claude(prompt, selected_agent.model)


if __name__ == "__main__":
    raise SystemExit(main())
