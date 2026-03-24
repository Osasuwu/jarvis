from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Iterable
from uuid import uuid4

import requests

from agents.registry import command_to_agent
from jarvis.costs import record_execution
from jarvis.config import RuntimeConfig
from jarvis.dispatcher import UnsupportedCommandError, build_prompt_for_command, get_skill_command_map
from jarvis.executor import execute_prompt_with_claude

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"
MAX_MESSAGE_LEN = 4096


def _supported_commands() -> list[str]:
    commands = sorted(get_skill_command_map().keys())
    if "/research" not in commands:
        commands.append("/research")
    return commands


def _telegram_command_name(command: str) -> str:
    # Telegram accepts only lowercase letters, digits and underscores in command names.
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
    if canonical_command == "/research":
        return f"/research {arg}".strip()
    return canonical_command


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
    except Exception as exc:  # pragma: no cover - network side effect
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

            normalized_command = _normalize_command(parsed.text)
            if normalized_command is None:
                command_list = ", ".join(_supported_commands())
                _send_message(
                    token,
                    parsed.chat_id,
                    f"Unsupported input. Send one of: {command_list}, /research <topic>",
                )
                continue

            if normalized_command == "/help":
                help_lines = ["Available commands:", *(_supported_commands()), "/research <topic>"]
                _send_message(
                    token,
                    parsed.chat_id,
                    "\n".join(help_lines),
                )
                continue

            try:
                prompt = build_prompt_for_command(normalized_command)
            except (UnsupportedCommandError, FileNotFoundError) as exc:
                _send_message(token, parsed.chat_id, f"[jarvis] {exc}")
                continue

            if not config.anthropic_api_key:
                _send_message(token, parsed.chat_id, "[jarvis] ANTHROPIC_API_KEY is not set.")
                continue

            selected_agent = command_to_agent(normalized_command)
            result = execute_prompt_with_claude(prompt, model=selected_agent.model)
            if result.return_code != 0:
                error = result.stderr.strip() or "unknown claude execution error"
                _send_message(token, parsed.chat_id, f"[jarvis] command failed: {error}")
                continue

            record_execution(
                model=selected_agent.model,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                session_id=session_id,
            )

            response_text = result.stdout.strip() or "[jarvis] Empty response"
            _send_message(token, parsed.chat_id, response_text)

        time.sleep(1)
