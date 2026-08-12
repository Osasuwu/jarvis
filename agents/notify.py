"""Notifier registry + Telegram transport for orchestrator escalations.

Telegram (#1385 AC-D) is the only built-in transport with a native client;
it is the only Telegram path left after ``scripts/telegram-notify-hook.py``
(a standalone drain of pending events) was retired (#1139): every escalation
now flows through the orchestrator's ``ESCALATE`` route, scoped to a single
:class:`agents.orchestrator.Decision` rather than a raw Supabase event row —
``dispatch``'s ``ESCALATE`` branch has only the routing verdict, not the
original event payload. Env-gated: unset ``TELEGRAM_BOT_TOKEN``/
``TELEGRAM_ALLOW_USER_ID`` means "notifications not configured yet", not an
error.

Telegram notifier is called from inside a live ``wake_driver`` tick (via
``dispatch``/``build_production_orchestrator``), so it must never raise — a
notification failure would otherwise abort an event that was routed and
enqueued successfully. ``dispatch`` also wraps the call in a try/except as
defense-in-depth; the no-raise contract here is the primary guarantee. The
same no-raise contract holds for every transport reachable through
:func:`resolve_notifier`.

``resolve_notifier`` (#1547, milestone #65 S1) is the install-level binding
point: it reads an explicit ``env`` mapping (never ``os.environ`` directly —
tested at #1547 AC11, "env read at wiring time, not import time") and picks
one of ``telegram`` / ``apprise`` / ``none`` / a dotted ``pkg.mod:fn``
callable. An unrecognized or missing configuration never falls back to
Telegram silently — it logs loudly, writes an owner ``task_queue`` row, and
resolves to an effective ``none`` transport whose callable reports failure
(distinct from an explicit, successful ``none`` opt-out) so callers such as
``wake_driver --notify-test`` can tell "intentionally disabled" apart from
"broken". Production wiring through this registry, and the
``TELEGRAM_NOW``→``NOTIFY_NOW`` rename, are milestone #65 S2 scope (#1548) —
S1 only adds the registry and the ``--notify-test`` smoke check.
"""

from __future__ import annotations

import importlib
import logging
import os
import re
from typing import TYPE_CHECKING, Callable, Mapping

from agents import task_queue

try:
    import httpx
except ImportError:  # pragma: no cover - exercised only when httpx is absent
    httpx = None  # type: ignore[assignment]

try:
    import apprise as _apprise_lib
except ImportError:  # pragma: no cover - exercised only when apprise is absent
    _apprise_lib = None  # type: ignore[assignment]

if TYPE_CHECKING:
    from agents.orchestrator import Decision

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org"

NotifierFn = Callable[["Decision"], bool]

# URL-shaped substrings may embed tokens/webhook secrets (Telegram bot token,
# Apprise service URL) — never let one reach log output (#1547 AC9). Apprise
# URLs use non-http schemes (tgram://, discord://, slack://, matrix://, ...;
# see .gitleaks.toml's jarvis-apprise-service-webhook-url rule), so this must
# match any URI scheme, not just http(s).
_URL_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9+.-]*://\S+")


def _sanitize(text: str) -> str:
    """Redact URL-shaped substrings from a string before logging."""
    return _URL_RE.sub("<redacted-url>", text)


def _format_message(decision: "Decision") -> str:
    lines = [
        f"[{decision.severity.upper()}] {decision.event_type}",
        f"Target: {decision.target}",
    ]
    if decision.escalated_reason:
        lines.append(f"Reason: {decision.escalated_reason}")
    if decision.goal:
        lines.append(f"Goal: {decision.goal}")
    return "\n".join(lines)


def telegram_notifier(decision: "Decision") -> bool:
    """Send one Telegram message for an escalated :class:`Decision`.

    Returns ``True`` only on a confirmed send; every other case (missing
    env, missing ``httpx``, HTTP failure, network exception) logs a warning
    and returns ``False`` — never raises.
    """
    token = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    chat_id = (os.environ.get("TELEGRAM_ALLOW_USER_ID") or "").strip()
    if not token or not chat_id:
        logger.warning(
            "telegram_notifier: TELEGRAM_BOT_TOKEN/TELEGRAM_ALLOW_USER_ID not set "
            "— skipping notification for %s/%s",
            decision.event_type,
            decision.severity,
        )
        return False

    if httpx is None:
        logger.warning("telegram_notifier: httpx not installed — skipping notification")
        return False

    text = _format_message(decision)
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(
                f"{TELEGRAM_API}/bot{token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "disable_web_page_preview": True,
                },
            )
            body = (
                resp.json()
                if resp.headers.get("content-type", "").startswith("application/json")
                else {}
            )
            if resp.status_code == 200 and body.get("ok"):
                return True
            # Never log the response body — Telegram's error payload can
            # echo the request back, including the bot token in the URL it
            # rejected (#1547 AC9). Status code alone is enough to diagnose.
            logger.warning("telegram_notifier: send failed HTTP %s", resp.status_code)
            return False
    except Exception as exc:
        logger.warning("telegram_notifier: %s: %s", type(exc).__name__, _sanitize(str(exc)))
        return False


def _none_notifier(decision: "Decision") -> bool:
    """Explicit ``none`` transport — a deliberate no-op, not a failure."""
    return True


def _disabled_notifier(decision: "Decision") -> bool:
    """Effective-none fallback after a misconfiguration.

    Distinct from :func:`_none_notifier`: this always reports failure so
    callers (``wake_driver --notify-test`` today; dispatch's own
    notified-tracking in a later slice) can tell "the operator chose no
    notifications" apart from "the configured transport was broken".
    """
    return False


def _log_resolved(name: str) -> None:
    logger.info("notify: resolved transport=%s", name)


def _misconfig(reason: str) -> tuple[str, NotifierFn]:
    """Loud-misconfiguration landing zone shared by every failure path.

    ERROR log + owner ``task_queue`` row + effective ``none`` — never a
    silent Telegram fallback (#1547 AC5/AC6). The task_queue row is
    idempotent per distinct reason so repeated restarts on the same bad
    config don't spam duplicate rows.
    """
    logger.error("notify: %s — effective transport=none", reason)
    try:
        task_queue.enqueue(
            goal="notify: transport misconfigured",
            assignee="owner",
            priority=0,
            idempotency_key=f"notify-misconfig:{reason}",
            escalated_reason=reason,
        )
    except Exception as exc:
        logger.error(
            "notify: failed to write owner task_queue row: %s: %s",
            type(exc).__name__,
            _sanitize(str(exc)),
        )
    _log_resolved("none")
    return "none", _disabled_notifier


def _make_apprise_notifier(apprise_url: str) -> NotifierFn:
    def _apprise_notifier(decision: "Decision") -> bool:
        if _apprise_lib is None:
            logger.warning(
                "apprise_notifier: apprise package not installed — skipping notification"
            )
            return False
        try:
            app = _apprise_lib.Apprise()
            if not app.add(apprise_url):
                # Never log the URL itself — it may embed webhook credentials.
                logger.warning(
                    "apprise_notifier: configured NOTIFY_APPRISE_URL could not be registered"
                )
                return False
            text = _format_message(decision)
            title = f"[{decision.severity.upper()}] {decision.event_type}"
            return bool(app.notify(body=text, title=title))
        except Exception as exc:
            logger.warning("apprise_notifier: %s: %s", type(exc).__name__, _sanitize(str(exc)))
            return False

    return _apprise_notifier


def resolve_notifier(env: Mapping[str, str]) -> tuple[str, NotifierFn]:
    """Resolve ``NOTIFY_TRANSPORT`` to a bound ``(name, notifier)`` pair.

    Reads only the passed ``env`` mapping — never ``os.environ`` directly —
    so resolution can be exercised in tests with explicit mappings and so
    the binding genuinely happens at wiring time, not at import time
    (#1547 AC1/AC11). Every branch logs the resolved transport (AC7); every
    failure branch routes through :func:`_misconfig` (AC5/AC6) rather than
    falling back to Telegram silently.
    """
    raw = (env.get("NOTIFY_TRANSPORT") or "").strip()
    normalized = raw.lower()

    if normalized == "telegram":
        _log_resolved("telegram")
        return "telegram", telegram_notifier

    if normalized == "apprise":
        apprise_url = (env.get("NOTIFY_APPRISE_URL") or "").strip()
        if not apprise_url:
            return _misconfig("NOTIFY_TRANSPORT=apprise but NOTIFY_APPRISE_URL is unset")
        _log_resolved("apprise")
        return "apprise", _make_apprise_notifier(apprise_url)

    if normalized == "none":
        _log_resolved("none")
        return "none", _none_notifier

    if not normalized:
        token = (env.get("TELEGRAM_BOT_TOKEN") or "").strip()
        chat_id = (env.get("TELEGRAM_ALLOW_USER_ID") or "").strip()
        if token and chat_id:
            _log_resolved("telegram")
            return "telegram", telegram_notifier
        return _misconfig(
            "NOTIFY_TRANSPORT unset and no Telegram credentials configured — notifications disabled"
        )

    if ":" in raw:
        module_path, _, fn_name = raw.partition(":")
        try:
            module = importlib.import_module(module_path)
            fn = getattr(module, fn_name)
            if not callable(fn):
                raise TypeError(f"{fn_name!r} is not callable")
        except Exception as exc:
            return _misconfig(
                f"dotted-path transport {_sanitize(raw)!r} failed to import: "
                f"{type(exc).__name__}: {_sanitize(str(exc))}"
            )
        _log_resolved(raw)
        return raw, fn

    return _misconfig(f"unrecognized NOTIFY_TRANSPORT value {_sanitize(raw)!r}")
