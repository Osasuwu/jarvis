"""Tests for agents.notify.telegram_notifier (#1385 AC-D).

telegram_notifier is the injectable ``notifier`` callable orchestrator.dispatch
fires on a critical escalation. It must never raise — a missing config or a
failed send both degrade to a warning + ``False``, since this runs inside a
live wake_driver tick where an exception would abort otherwise-successful
event processing.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from agents.notify import resolve_notifier, telegram_notifier
from agents.orchestrator import Decision, Route


def _decision(**overrides) -> Decision:
    base = dict(
        route=Route.ESCALATE,
        event_type="security_alert",
        severity="critical",
        target="repo:Osasuwu/jarvis",
        idempotency_key="key-1",
        priority=10,
        escalated_reason="unknown event",
    )
    base.update(overrides)
    return Decision(**base)


def test_telegram_notifier_noops_when_token_unset(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setenv("TELEGRAM_ALLOW_USER_ID", "12345")
    assert telegram_notifier(_decision()) is False


def test_telegram_notifier_noops_when_chat_id_unset(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.delenv("TELEGRAM_ALLOW_USER_ID", raising=False)
    assert telegram_notifier(_decision()) is False


def test_telegram_notifier_sends_when_configured(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_ALLOW_USER_ID", "12345")

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.headers = {"content-type": "application/json"}
    fake_response.json.return_value = {"ok": True}

    fake_client = MagicMock()
    fake_client.__enter__.return_value = fake_client
    fake_client.post.return_value = fake_response

    with patch("agents.notify.httpx") as fake_httpx:
        fake_httpx.Client.return_value = fake_client
        assert telegram_notifier(_decision()) is True

    sent_url = fake_client.post.call_args.args[0]
    assert "tok" in sent_url
    sent_kwargs = fake_client.post.call_args.kwargs
    assert sent_kwargs["json"]["chat_id"] == "12345"
    assert "security_alert" in sent_kwargs["json"]["text"]


def test_telegram_notifier_returns_false_on_http_failure(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_ALLOW_USER_ID", "12345")

    fake_response = MagicMock()
    fake_response.status_code = 500
    fake_response.headers = {"content-type": "application/json"}
    fake_response.json.return_value = {"ok": False, "description": "boom"}
    fake_response.text = "boom"

    fake_client = MagicMock()
    fake_client.__enter__.return_value = fake_client
    fake_client.post.return_value = fake_response

    with patch("agents.notify.httpx") as fake_httpx:
        fake_httpx.Client.return_value = fake_client
        assert telegram_notifier(_decision()) is False


def test_telegram_notifier_swallows_send_exception(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_ALLOW_USER_ID", "12345")

    with patch("agents.notify.httpx") as fake_httpx:
        fake_httpx.Client.side_effect = RuntimeError("network down")
        # Must not raise.
        assert telegram_notifier(_decision()) is False


def test_resolve_notifier_explicit_telegram(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_ALLOW_USER_ID", raising=False)
    name, notifier = resolve_notifier({"NOTIFY_TRANSPORT": "telegram"})
    assert name == "telegram"
    assert notifier is telegram_notifier


def test_resolve_notifier_normalizes_case_and_whitespace():
    name, notifier = resolve_notifier({"NOTIFY_TRANSPORT": "  Telegram  "})
    assert name == "telegram"
    assert notifier is telegram_notifier


def test_resolve_notifier_defaults_to_telegram_when_creds_present():
    name, notifier = resolve_notifier(
        {
            "TELEGRAM_BOT_TOKEN": "tok",
            "TELEGRAM_ALLOW_USER_ID": "12345",
        }
    )
    assert name == "telegram"
    assert notifier is telegram_notifier


def test_resolve_notifier_none_transport_is_explicit_noop_success():
    name, notifier = resolve_notifier({"NOTIFY_TRANSPORT": "none"})
    assert name == "none"
    assert notifier(_decision()) is True


def test_resolve_notifier_apprise_delivers_via_apprise_library():
    fake_app = MagicMock()
    fake_app.add.return_value = True
    fake_app.notify.return_value = True
    fake_apprise_lib = MagicMock()
    fake_apprise_lib.Apprise.return_value = fake_app

    with patch("agents.notify._apprise_lib", fake_apprise_lib):
        name, notifier = resolve_notifier(
            {"NOTIFY_TRANSPORT": "apprise", "NOTIFY_APPRISE_URL": "webhook://example/tok"}
        )
        assert name == "apprise"
        assert notifier(_decision()) is True

    fake_app.add.assert_called_once_with("webhook://example/tok")
    assert fake_app.notify.call_args.kwargs["body"]
    assert "security_alert" in fake_app.notify.call_args.kwargs["title"]


def test_resolve_notifier_apprise_missing_url_is_loud_misconfig(monkeypatch, caplog):
    enqueue_calls = []
    monkeypatch.setattr(
        "agents.notify.task_queue.enqueue",
        lambda **kwargs: enqueue_calls.append(kwargs) or {"id": "row-1"},
    )
    with caplog.at_level("ERROR", logger="agents.notify"):
        name, notifier = resolve_notifier({"NOTIFY_TRANSPORT": "apprise"})
    assert name == "none"
    assert notifier(_decision()) is False
    assert len(enqueue_calls) == 1
    assert enqueue_calls[0]["assignee"] == "owner"
    assert "NOTIFY_APPRISE_URL" in enqueue_calls[0]["escalated_reason"]
    assert any("NOTIFY_APPRISE_URL" in rec.message for rec in caplog.records)


def test_resolve_notifier_dotted_path_transport(monkeypatch):
    import notify_transport_double

    notify_transport_double.calls.clear()
    name, notifier = resolve_notifier(
        {"NOTIFY_TRANSPORT": "notify_transport_double:fake_transport"}
    )
    assert name == "notify_transport_double:fake_transport"
    decision = _decision()
    assert notifier(decision) is True
    assert notify_transport_double.calls == [decision]


def test_resolve_notifier_dotted_path_import_failure_is_loud_misconfig(monkeypatch, caplog):
    enqueue_calls = []
    monkeypatch.setattr(
        "agents.notify.task_queue.enqueue",
        lambda **kwargs: enqueue_calls.append(kwargs) or {"id": "row-1"},
    )
    with caplog.at_level("ERROR", logger="agents.notify"):
        name, notifier = resolve_notifier({"NOTIFY_TRANSPORT": "no_such_pkg_xyz:fn"})
    assert name == "none"
    assert notifier(_decision()) is False
    assert len(enqueue_calls) == 1
    assert "no_such_pkg_xyz:fn" in enqueue_calls[0]["escalated_reason"]


def test_resolve_notifier_unrecognized_value_is_loud_misconfig(monkeypatch, caplog):
    enqueue_calls = []
    monkeypatch.setattr(
        "agents.notify.task_queue.enqueue",
        lambda **kwargs: enqueue_calls.append(kwargs) or {"id": "row-1"},
    )
    with caplog.at_level("ERROR", logger="agents.notify"):
        name, notifier = resolve_notifier({"NOTIFY_TRANSPORT": "sdfsdf"})
    assert name == "none"
    # Effective-none-after-misconfig always reports failure — distinct from
    # an explicit, successful "none" opt-out.
    assert notifier(_decision()) is False
    assert len(enqueue_calls) == 1
    assert enqueue_calls[0]["assignee"] == "owner"
    assert any(rec.levelname == "ERROR" and "sdfsdf" in rec.message for rec in caplog.records)


def test_resolve_notifier_unset_with_no_telegram_creds_is_loud_misconfig(monkeypatch, caplog):
    enqueue_calls = []
    monkeypatch.setattr(
        "agents.notify.task_queue.enqueue",
        lambda **kwargs: enqueue_calls.append(kwargs) or {"id": "row-1"},
    )
    with caplog.at_level("ERROR", logger="agents.notify"):
        name, notifier = resolve_notifier({})
    assert name == "none"
    assert notifier(_decision()) is False
    assert len(enqueue_calls) == 1
    assert "notifications disabled" in enqueue_calls[0]["escalated_reason"]


def test_resolve_notifier_misconfig_is_idempotent_per_reason(monkeypatch):
    enqueue_calls = []
    monkeypatch.setattr(
        "agents.notify.task_queue.enqueue",
        lambda **kwargs: enqueue_calls.append(kwargs) or None,
    )
    resolve_notifier({"NOTIFY_TRANSPORT": "sdfsdf"})
    resolve_notifier({"NOTIFY_TRANSPORT": "sdfsdf"})
    keys = {c["idempotency_key"] for c in enqueue_calls}
    assert len(enqueue_calls) == 2
    assert len(keys) == 1


@pytest.mark.parametrize(
    "env",
    [
        {"NOTIFY_TRANSPORT": "telegram"},
        {"NOTIFY_TRANSPORT": "none"},
        {"NOTIFY_TRANSPORT": "sdfsdf"},
        {},
    ],
)
def test_resolve_notifier_always_logs_resolved_transport(env, caplog, monkeypatch):
    monkeypatch.setattr("agents.notify.task_queue.enqueue", lambda **kwargs: None)
    with caplog.at_level("INFO", logger="agents.notify"):
        resolve_notifier(env)
    assert any("resolved transport=" in rec.message for rec in caplog.records)


def test_resolve_notifier_never_reads_process_environ(monkeypatch):
    class ExplodingEnviron(dict):
        def get(self, *_args, **_kwargs):
            raise AssertionError("resolve_notifier must not read os.environ directly")

    monkeypatch.setattr(os, "environ", ExplodingEnviron(TELEGRAM_BOT_TOKEN="tok"))
    # A real os.environ read (e.g. accidental os.environ.get inside
    # resolve_notifier) would raise here; passing an explicit dict must not.
    name, notifier = resolve_notifier({"NOTIFY_TRANSPORT": "none"})
    assert name == "none"


def test_telegram_notifier_http_failure_does_not_log_response_body(monkeypatch, caplog):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok-secret-value")
    monkeypatch.setenv("TELEGRAM_ALLOW_USER_ID", "12345")

    fake_response = MagicMock()
    fake_response.status_code = 500
    fake_response.headers = {"content-type": "application/json"}
    fake_response.json.return_value = {
        "ok": False,
        "description": "https://api.telegram.org/bottok-secret-value/sendMessage rejected",
    }
    fake_response.text = "https://api.telegram.org/bottok-secret-value/sendMessage rejected"

    fake_client = MagicMock()
    fake_client.__enter__.return_value = fake_client
    fake_client.post.return_value = fake_response

    with caplog.at_level("WARNING", logger="agents.notify"):
        with patch("agents.notify.httpx") as fake_httpx:
            fake_httpx.Client.return_value = fake_client
            assert telegram_notifier(_decision()) is False

    assert "tok-secret-value" not in caplog.text


def test_telegram_notifier_exception_message_is_sanitized(monkeypatch, caplog):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok-secret-value")
    monkeypatch.setenv("TELEGRAM_ALLOW_USER_ID", "12345")

    with caplog.at_level("WARNING", logger="agents.notify"):
        with patch("agents.notify.httpx") as fake_httpx:
            fake_httpx.Client.side_effect = RuntimeError(
                "connection to https://api.telegram.org/bottok-secret-value/sendMessage failed"
            )
            assert telegram_notifier(_decision()) is False

    assert "tok-secret-value" not in caplog.text
    assert "<redacted-url>" in caplog.text


def test_apprise_notifier_exception_message_is_sanitized():
    fake_app = MagicMock()
    fake_app.add.return_value = True
    fake_app.notify.side_effect = RuntimeError(
        "post to https://hooks.example.com/services/tok-secret-value failed"
    )
    fake_apprise_lib = MagicMock()
    fake_apprise_lib.Apprise.return_value = fake_app

    with patch("agents.notify._apprise_lib", fake_apprise_lib):
        _name, notifier = resolve_notifier(
            {"NOTIFY_TRANSPORT": "apprise", "NOTIFY_APPRISE_URL": "webhook://example/tok"}
        )
        with patch("agents.notify.logger") as fake_logger:
            assert notifier(_decision()) is False

    logged_args = " ".join(str(a) for call in fake_logger.warning.call_args_list for a in call.args)
    assert "tok-secret-value" not in logged_args
