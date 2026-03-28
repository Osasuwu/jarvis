from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import dataclass
from typing import Iterable
from uuid import uuid4

import requests

from jarvis.config import RuntimeConfig
from jarvis.dispatcher import (
    discover_skills,
    dispatch_skill,
    get_skill,
    supported_commands,
)

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"
MAX_MESSAGE_LEN = 4096


def _telegram_command_name(command: str) -> str:
    return command.lstrip("/").replace("-", "_")


def _canonical_command_map() -> dict[str, str]:
    """Map both hyphenated and underscored command forms to canonical command."""
    commands = supported_commands()
    mapping = {cmd: cmd for cmd in commands}
    for cmd in commands:
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
    """Register bot commands from auto-discovered skills."""
    skills = discover_skills()
    commands = []
    for cmd in sorted(skills.keys()):
        spec = skills[cmd]
        commands.append(
            {
                "command": _telegram_command_name(cmd),
                "description": spec.description[:256],
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
    """Normalize Telegram command input to canonical form."""
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
    if canonical_command is None:
        return None

    # Always pass args for commands that accept them.
    if arg:
        return f"{canonical_command} {arg}"
    return canonical_command


def _resolve_user_input(text: str) -> str:
    normalized_command = _normalize_command(text)
    return normalized_command or text.strip()


def _run_skill_in_background(
    token: str,
    chat_id: int,
    config: RuntimeConfig,
    user_input: str,
    session_id: str,
) -> None:
    """Execute a skill in a background thread and post result to Telegram."""
    try:
        result = asyncio.run(
            dispatch_skill(user_input, config, session_id=session_id)
        )
    except Exception as exc:
        _send_message(token, chat_id, f"[jarvis] background task failed: {exc}")
        return

    if result.success:
        _send_message(token, chat_id, result.text or "[jarvis] Done (no output)")
    else:
        _send_message(token, chat_id, f"[jarvis] error: {result.text}")


def _handle_message(config: RuntimeConfig, user_input: str, session_id: str) -> str:
    """Process a single foreground message and return the response text."""
    if user_input == "/help":
        help_lines = ["Available commands:"]
        skills = discover_skills()
        for cmd in sorted(skills.keys()):
            help_lines.append(f"  {cmd} — {skills[cmd].description}")
        return "\n".join(help_lines) + "\n\nYou can also send plain text to chat with Jarvis."

    result = asyncio.run(
        dispatch_skill(user_input, config, session_id=session_id)
    )

    if not result.success:
        return f"[jarvis] error: {result.text}"

    return result.text.strip() or "[jarvis] Empty response"


def _should_run_in_background(user_input: str) -> bool:
    """Check if this command should run in a background thread.

    For plain-text messages, applies synchronous keyword-based intent routing
    first so that phrases like "улучши себя" correctly resolve to /self-improve
    (which is a background skill) before the check.
    """
    text = user_input.strip()
    if not text.startswith("/"):
        from jarvis.intent_router import route_user_input  # noqa: WPS433
        route = route_user_input(text)
        if not route.was_routed:
            return False
        text = route.resolved_input.strip()
        if not text.startswith("/"):
            return False
    command = text.split(maxsplit=1)[0]
    skill = get_skill(command)
    return skill is not None and skill.background


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

            if _should_run_in_background(user_input):
                if user_input.lstrip().startswith("/"):
                    command = user_input.split(maxsplit=1)[0]
                    status_message = f"[jarvis] {command} started. Running in background..."
                else:
                    status_message = "[jarvis] Background task started. Running in background..."
                _send_message(token, parsed.chat_id, status_message)
                worker = threading.Thread(
                    target=_run_skill_in_background,
                    args=(token, parsed.chat_id, config, user_input, session_id),
                    daemon=True,
                )
                worker.start()
                continue

            response = _handle_message(config, user_input, session_id)
            _send_message(token, parsed.chat_id, response)

        time.sleep(1)
