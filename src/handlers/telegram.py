from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import dataclass
from typing import Iterable
from uuid import uuid4

import requests

from agents.registry import command_to_agent, is_delegation_command
from jarvis.costs import check_daily_budget, record_execution
from jarvis.config import RuntimeConfig
from jarvis.delegate import delegate_issue, parse_delegate_args
from jarvis.dispatcher import (
    UnsupportedCommandError,
    build_prompt_for_user_input,
    get_skill_command_map,
)
from jarvis.executor import execute_query

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"
MAX_MESSAGE_LEN = 4096


def _supported_commands() -> list[str]:
    commands = sorted(get_skill_command_map().keys())
    if "/research" not in commands:
        commands.append("/research")
    return commands


def _telegram_command_name(command: str) -> str:
    return command.lstrip("/").replace("-", "_")


def _canonical_command_map() -> dict[str, str]:
    mapping = {cmd: cmd for cmd in _supported_commands()}
    for cmd in _supported_commands():
        mapping[f"/{_telegram_command_name(cmd)}"] = cmd
    return mapping


@dataclass(frozen=True)
class TelegramMessage:
    update_id: int
    chat_id: int
    text: str
    user_id: int | None


def _chunks(text: str, chunk_size: int = MAX_MESSAGE_LEN) -> Iterable[str]:
    for start in range(0, len(text), chunk_size):
        yield text[start : start + chunk_size]


def _call_telegram(token: str, method: str, payload: dict) -> dict:
    url = TELEGRAM_API.format(token=token, method=method)
    response = requests.post(url, json=payload, timeout=30)
    response.raise_for_status()
    data = response.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram API error for {method}: {data}")
    return data


def _send_message(token: str, chat_id: int, text: str) -> None:
    for part in _chunks(text):
        _call_telegram(
            token,
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": part,
                "disable_web_page_preview": True,
            },
        )


def _set_my_commands(token: str) -> None:
    descriptions = {
        "/triage": "Daily triage across repositories",
        "/weekly-report": "Weekly delivery report",
        "/issue-health": "Deep issue metadata validation",
        "/research": "Source-backed research by topic",
        "/delegate": "Delegate issue to coding agent",
    }
    commands = []
    for cmd in _supported_commands():
        commands.append(
            {
                "command": _telegram_command_name(cmd),
                "description": descriptions.get(cmd, f"Run {cmd}"),
            }
        )
    _call_telegram(token, "setMyCommands", {"commands": commands})


def _parse_update(raw: dict) -> TelegramMessage | None:
    message = raw.get("message")
    if not message:
        return None

    text = message.get("text")
    chat = message.get("chat", {})
    sender = message.get("from", {})
    if not text or "id" not in chat:
        return None

    return TelegramMessage(
        update_id=raw["update_id"],
        chat_id=int(chat["id"]),
        text=text.strip(),
        user_id=int(sender["id"]) if sender.get("id") is not None else None,
    )


def _poll_updates(token: str, offset: int | None) -> list[dict]:
    payload = {"timeout": 30}
    if offset is not None:
        payload["offset"] = offset
    result = _call_telegram(token, "getUpdates", payload)
    return result.get("result", [])


def _normalize_command(text: str) -> str | None:
    line = text.strip().splitlines()[0] if text.strip() else ""
    if not line.startswith("/"):
        return None

    raw = line.split(maxsplit=1)
    command_token = raw[0].split("@", maxsplit=1)[0]
    arg = raw[1].strip() if len(raw) > 1 else ""

    if command_token in {"/start", "/help"}:
        return "/help"

    canonical_map = _canonical_command_map()
    canonical_command = canonical_map.get(command_token)
    if canonical_command in {"/research", "/delegate"}:
        return f"{canonical_command} {arg}".strip()
    return canonical_command


def _resolve_user_input(text: str) -> str:
    normalized_command = _normalize_command(text)
    return normalized_command or text.strip()


def _run_delegation_in_background(
    token: str,
    chat_id: int,
    config: RuntimeConfig,
    user_input: str,
    session_id: str,
) -> None:
    """Execute delegation in a background thread and post final result to Telegram."""
    try:
        repo, issue_number = parse_delegate_args(user_input)
    except ValueError as exc:
        _send_message(token, chat_id, f"[jarvis] {exc}")
        return

    allowed, remaining = check_daily_budget(config.budget.per_day_usd)
    if not allowed:
        _send_message(
            token,
            chat_id,
            f"[jarvis] Daily budget exhausted (${config.budget.per_day_usd:.2f} limit).",
        )
        return

    agent = command_to_agent(user_input)
    query_budget = min(agent.max_budget_usd, config.budget.per_query_usd, remaining)
    if query_budget <= 0:
        _send_message(token, chat_id, "[jarvis] No budget available for delegation.")
        return

    _send_message(
        token,
        chat_id,
        (
            f"[jarvis] Delegation started for #{issue_number} in {repo}.\n"
            f"Pipeline: fetch -> decompose -> branch -> code -> PR\n"
            f"Budget: ${query_budget:.2f}"
        ),
    )

    delegate_session_id = f"{session_id}-delegate-{uuid4().hex[:8]}"
    try:
        result = asyncio.run(
            delegate_issue(
                repo,
                issue_number,
                max_budget_usd=query_budget,
                session_id=delegate_session_id,
                daily_budget_usd=config.budget.per_day_usd,
                per_query_usd=config.budget.per_query_usd,
            )
        )
    except Exception as exc:
        _send_message(token, chat_id, f"[jarvis] delegation failed with unexpected error: {exc}")
        return

    if result.success:
        _send_message(token, chat_id, result.message)
        return

    _send_message(token, chat_id, f"[jarvis] delegation failed: {result.message}")


def _handle_message(config: RuntimeConfig, user_input: str, session_id: str) -> str:
    """Process a single non-delegation message and return the response text."""

    if user_input == "/help":
        help_lines = ["Available commands:", *(_supported_commands())]
        return "\n".join(help_lines) + "\n\nYou can also send plain text to chat with Jarvis."

    try:
        prompt = build_prompt_for_user_input(user_input)
    except (UnsupportedCommandError, FileNotFoundError) as exc:
        return f"[jarvis] {exc}"

    agent = command_to_agent(user_input)

    # Daily budget check
    allowed, remaining = check_daily_budget(config.budget.per_day_usd)
    if not allowed:
        return f"[jarvis] Daily budget exhausted (${config.budget.per_day_usd:.2f} limit)."

    query_budget = min(agent.max_budget_usd, config.budget.per_query_usd, remaining)

    result = asyncio.run(
        execute_query(
            prompt,
            model=agent.model,
            allowed_tools=agent.allowed_tools,
            max_budget_usd=query_budget,
        )
    )

    if result.cost_usd > 0 or result.input_tokens > 0:
        record_execution(
            model=agent.model,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            cost_usd=result.cost_usd,
            session_id=session_id,
        )

    if not result.success:
        return f"[jarvis] error: {result.error}"

    return result.text.strip() or "[jarvis] Empty response"


def run_telegram_loop(config: RuntimeConfig) -> int:
    token = config.telegram_bot_token
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN is not set")

    allow_user = None
    if config.telegram_allow_user_id:
        try:
            allow_user = int(config.telegram_allow_user_id)
        except ValueError as exc:
            raise ValueError("TELEGRAM_ALLOW_USER_ID must be numeric") from exc

    offset: int | None = None
    session_id = f"telegram-{uuid4().hex[:10]}"
    print("[jarvis] Telegram polling started")
    try:
        _set_my_commands(token)
    except Exception as exc:
        print(f"[jarvis] warning: failed to set Telegram commands: {exc}")

    while True:
        updates = _poll_updates(token, offset)
        for raw in updates:
            offset = int(raw["update_id"]) + 1
            parsed = _parse_update(raw)
            if not parsed:
                continue

            if allow_user is not None and parsed.user_id != allow_user:
                _send_message(token, parsed.chat_id, "Access denied for this user.")
                continue

            user_input = _resolve_user_input(parsed.text)

            if is_delegation_command(user_input):
                _send_message(token, parsed.chat_id, "[jarvis] Delegation request accepted. Running in background...")
                worker = threading.Thread(
                    target=_run_delegation_in_background,
                    args=(token, parsed.chat_id, config, user_input, session_id),
                    daemon=True,
                )
                worker.start()
                continue

            response = _handle_message(config, user_input, session_id)
            _send_message(token, parsed.chat_id, response)

        time.sleep(1)
