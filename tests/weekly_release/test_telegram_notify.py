"""#1761 - routine notifications never reached Telegram: a bare scheduled
session has no `.env` in its environment, so the credentials were missing.
scripts/notify_telegram.py loads `.env` itself and fails loud.
"""

from __future__ import annotations

import json

import pytest

from scripts.notify_telegram import NotifyError, find_env_file, resolve_env, send


def test_env_file_fills_credentials_missing_from_process_env(tmp_path):
    (tmp_path / ".env").write_text(
        '# comment\nexport TELEGRAM_BOT_TOKEN="tok-from-file"\nTELEGRAM_ALLOW_USER_ID=42\n',
        encoding="utf-8",
    )
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    env = resolve_env({"TELEGRAM_ALLOW_USER_ID": "7"}, find_env_file(nested))
    assert env["TELEGRAM_BOT_TOKEN"] == "tok-from-file"
    assert env["TELEGRAM_ALLOW_USER_ID"] == "7"  # process env wins


def test_send_posts_subject_and_body_to_the_owner_chat():
    calls = []

    def post(url, data):
        calls.append((url, json.loads(data)))
        return {"ok": True}

    send("Published release: o/r v0.5.0", "https://x/y", {"TELEGRAM_BOT_TOKEN": "tok", "TELEGRAM_CHAT_ID": "42"}, post)
    assert calls == [
        (
            "https://api.telegram.org/bottok/sendMessage",
            {"chat_id": "42", "text": "Published release: o/r v0.5.0\n\nhttps://x/y", "disable_web_page_preview": True},
        )
    ]


def test_missing_credentials_fail_loud_naming_keys_only():
    with pytest.raises(NotifyError, match="TELEGRAM_BOT_TOKEN"):
        send("s", "", {"TELEGRAM_ALLOW_USER_ID": "42"}, lambda u, d: {"ok": True})


def test_api_refusal_and_network_errors_raise_without_leaking_token():
    env = {"TELEGRAM_BOT_TOKEN": "secret-tok", "TELEGRAM_ALLOW_USER_ID": "42"}
    with pytest.raises(NotifyError, match="chat not found"):
        send("s", "", env, lambda u, d: {"ok": False, "description": "chat not found"})

    def boom(url, data):
        raise OSError(f"cannot reach {url}")

    with pytest.raises(NotifyError) as exc:
        send("s", "", env, boom)
    assert "secret-tok" not in str(exc.value)
