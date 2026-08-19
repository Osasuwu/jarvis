"""Shared escalation dedup state for the two delivery channels (#1591).

Both the morning digest and SessionStart surface pending owner escalations
(task_queue rows with assignee='owner', status='pending'). This module
ensures each escalation appears in at most one channel per day — dedup by
task_queue row UUID, NOT by text (AC: не опирается на совпадение текста).

State is persisted in Supabase `memories` under the name
`escalation_dedup_{YYYY-MM-DD}` (UTC) so it is cross-device.

Failure is non-fatal in both directions:
- read failure → treated as no prior shows (both channels see everything)
- write failure → logged to stderr, channel continues showing normally
The worst-case outcome is an escalation appearing in both channels once
rather than being silently dropped.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from typing import Any

CHANNEL_SESSION_START = "session_start"
CHANNEL_DIGEST = "digest"

_DEDUP_PREFIX = "escalation_dedup_"


def today_utc() -> str:
    """Return today's date in UTC as YYYY-MM-DD."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def dedup_name(date_str: str) -> str:
    """Memories record name for today's escalation dedup state."""
    return f"{_DEDUP_PREFIX}{date_str}"


def filter_for_channel(
    tasks: list[dict],
    shown_by_other: list[str],
) -> list[dict]:
    """Return tasks not already shown by the other channel.

    Pure function — no I/O. Dedup is by task `id`, not by text.
    """
    if not shown_by_other:
        return list(tasks)
    shown_set = set(shown_by_other)
    return [t for t in tasks if str(t.get("id", "")) not in shown_set]


def _safe_parse(content: Any) -> dict[str, list[str]]:
    """Parse dedup content from memories row. Returns {} on any error."""
    if isinstance(content, str):
        try:
            content = json.loads(content)
        except Exception:
            return {}
    if isinstance(content, dict):
        return {k: list(v) for k, v in content.items() if isinstance(v, list)}
    return {}


def _fetch_row(client: Any, date_str: str) -> tuple[str | None, dict[str, list[str]]]:
    """Fetch today's dedup row, if any.

    Returns (row_id, parsed_content) — (None, {}) if no row exists yet.
    Shared by read_shown() and write_shown(); raises on client error, the
    caller's try/except is responsible for the non-fatal fallback.
    """
    result = (
        client.table("memories")
        .select("id, content")
        .eq("name", dedup_name(date_str))
        .is_("deleted_at", "null")
        .order("updated_at", desc=True)
        .limit(1)
        .execute()
    )
    if result.data:
        return result.data[0]["id"], _safe_parse(result.data[0].get("content"))
    return None, {}


def read_shown(client: Any, date_str: str) -> dict[str, list[str]]:
    """Return {channel: [ids]} shown today from Supabase memories.

    Returns {} on any error (non-fatal — treat as no prior shows).
    """
    try:
        _row_id, data = _fetch_row(client, date_str)
        return data
    except Exception as exc:
        print(f"[escalation_dedup] read failed: {exc}", file=sys.stderr)
    return {}


def write_shown(client: Any, date_str: str, channel: str, ids: list[str]) -> None:
    """Merge ids into this channel's shown list for today (idempotent, best-effort).

    Reads the existing record, merges without duplicates, then updates or
    inserts. Failures are logged to stderr but never raised — a write failure
    means the escalation may appear twice, not that it disappears.
    """
    if not ids:
        return
    try:
        existing_row_id, data = _fetch_row(client, date_str)

        current = set(data.get(channel, []))
        current.update(ids)
        data[channel] = sorted(current)
        content = json.dumps(data)

        if existing_row_id:
            client.table("memories").update({"content": content}).eq(
                "id", existing_row_id
            ).execute()
        else:
            client.table("memories").insert(
                {
                    "type": "project",
                    "name": dedup_name(date_str),
                    "content": content,
                    "project": "jarvis",
                    "source_provenance": "script:escalation_dedup",
                }
            ).execute()
    except Exception as exc:
        print(f"[escalation_dedup] write failed: {exc}", file=sys.stderr)
