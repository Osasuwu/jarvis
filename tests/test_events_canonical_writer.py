"""Unit tests for the C17 events_canonical writer + buffer (#477).

Stub-based — no live Supabase. Verifies:
- Happy path: emit_event inserts a row + returns the response.
- Failure path: emit_event buffers, returns None, does NOT raise.
- Drain path: buffered events replay with degraded=true on next success.
- ContextVar bridge: caller-omitted trace_id is synthesized.
- Buffer overflow: oldest events drop (logged, not raised).
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "mcp-memory"))

from events_canonical import (  # noqa: E402
    _BUFFER_MAX,
    _buffer_clear_for_test,
    _buffer_len_for_test,
    emit_event,
)
from trace_context import new_trace, with_trace  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_buffer() -> None:
    """Each test starts with an empty buffer."""
    _buffer_clear_for_test()
    yield
    _buffer_clear_for_test()


def _stub_client(
    *,
    insert_returns: list[dict] | None = None,
    insert_raises: Exception | None = None,
) -> MagicMock:
    """Minimal Supabase-shaped stub.

    Returns a MagicMock whose ``.table(name).insert(row).execute()``
    chain mirrors the real client. ``insert_returns`` controls the
    payload of every successful insert; ``insert_raises`` makes
    ``insert(...)`` raise when set.
    """
    client = MagicMock()
    table = MagicMock()
    insert = MagicMock()
    execute = MagicMock()

    if insert_raises is not None:
        insert.side_effect = insert_raises
        client.table.return_value.insert = insert
    else:
        # Explicit `is None` so passing `insert_returns=[]` produces an
        # empty data response (used to verify defensive empty-result path).
        if insert_returns is None:
            data = [{"event_id": "stub-event-id", "trace_id": "stub-trace-id"}]
        else:
            data = insert_returns
        execute.return_value = MagicMock(data=data)
        insert.return_value = MagicMock(execute=execute)
        table.insert = insert
        client.table.return_value = table

    return client


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_emit_event_inserts_and_returns_row() -> None:
    client = _stub_client(
        insert_returns=[{"event_id": "abc", "trace_id": "xyz"}]
    )
    result = emit_event(
        client,
        actor="skill:test",
        action="decision_made",
        payload={"foo": 1},
        outcome="success",
    )
    assert result == {"event_id": "abc", "trace_id": "xyz"}
    client.table.assert_called_with("events_canonical")


def test_emit_event_uses_context_trace_id() -> None:
    """When context is set, writer picks it up automatically."""
    client = _stub_client()
    tid = new_trace()
    with with_trace(tid):
        emit_event(
            client,
            actor="skill:test",
            action="memory_recall",
        )
    inserted = client.table.return_value.insert.call_args[0][0]
    assert inserted["trace_id"] == tid


def test_emit_event_synthesizes_trace_when_context_missing() -> None:
    """No ContextVar set → writer mints a fresh trace_id, doesn't crash."""
    client = _stub_client()
    emit_event(client, actor="skill:test", action="orphan_action")
    inserted = client.table.return_value.insert.call_args[0][0]
    assert isinstance(inserted["trace_id"], str)
    assert len(inserted["trace_id"]) == 32  # hex


def test_emit_event_includes_optional_cost_fields_when_provided() -> None:
    client = _stub_client()
    emit_event(
        client,
        actor="skill:test",
        action="decision_made",
        cost_tokens=1234,
        cost_usd=0.0125,
    )
    inserted = client.table.return_value.insert.call_args[0][0]
    assert inserted["cost_tokens"] == 1234
    assert inserted["cost_usd"] == 0.0125


def test_emit_event_omits_cost_fields_when_not_provided() -> None:
    """Cost fields default to NULL — omit from row dict, don't pass None."""
    client = _stub_client()
    emit_event(client, actor="skill:test", action="decision_made")
    inserted = client.table.return_value.insert.call_args[0][0]
    assert "cost_tokens" not in inserted
    assert "cost_usd" not in inserted


def test_emit_event_caller_overrides_context() -> None:
    """Explicit trace_id wins over ContextVar."""
    client = _stub_client()
    ctx_id = new_trace()
    explicit = new_trace()
    with with_trace(ctx_id):
        emit_event(
            client,
            actor="skill:test",
            action="x",
            trace_id=explicit,
        )
    inserted = client.table.return_value.insert.call_args[0][0]
    assert inserted["trace_id"] == explicit


# ---------------------------------------------------------------------------
# Failure path — buffer
# ---------------------------------------------------------------------------


def test_emit_event_does_not_raise_on_insert_exception() -> None:
    """Caller MUST NOT see substrate failures."""
    client = _stub_client(insert_raises=RuntimeError("connection dropped"))
    result = emit_event(client, actor="skill:test", action="x")
    assert result is None


def test_emit_event_buffers_on_failure() -> None:
    client = _stub_client(insert_raises=RuntimeError("rls flap"))
    assert _buffer_len_for_test() == 0
    emit_event(client, actor="skill:test", action="x")
    assert _buffer_len_for_test() == 1


def test_emit_event_returns_none_on_empty_data_response() -> None:
    """Defensive — Supabase returning empty data is a soft failure."""
    client = _stub_client(insert_returns=[])
    result = emit_event(client, actor="skill:test", action="x")
    assert result is None
    assert _buffer_len_for_test() == 1


# ---------------------------------------------------------------------------
# Drain path
# ---------------------------------------------------------------------------


def test_buffered_events_drain_on_next_success() -> None:
    """A failure followed by a success drains the buffer with degraded=true."""
    # First call: fails, buffers.
    bad_client = _stub_client(insert_raises=RuntimeError("transient"))
    emit_event(bad_client, actor="skill:test", action="first")
    assert _buffer_len_for_test() == 1

    # Second call: succeeds — should drain the buffered row first.
    good_client = _stub_client()
    emit_event(good_client, actor="skill:test", action="second")

    inserts = [c.args[0] for c in good_client.table.return_value.insert.call_args_list]
    # Two inserts on good client: drained replay + the new one.
    assert len(inserts) == 2
    drained, new = inserts
    assert drained["action"] == "first"
    assert drained["degraded"] is True
    assert new["action"] == "second"
    assert "degraded" not in new or new["degraded"] is False
    assert _buffer_len_for_test() == 0


def test_drain_failure_keeps_row_in_buffer() -> None:
    """If drain replay also fails, the row stays buffered for next attempt."""
    # Buffer one row.
    bad1 = _stub_client(insert_raises=RuntimeError("boom"))
    emit_event(bad1, actor="skill:test", action="first")
    assert _buffer_len_for_test() == 1

    # Second attempt also fails: drain attempt fails, AND new event buffers.
    bad2 = _stub_client(insert_raises=RuntimeError("still boom"))
    emit_event(bad2, actor="skill:test", action="second")
    # Buffer now holds both: failed drain re-buffers + new failure adds.
    assert _buffer_len_for_test() == 2


def test_buffer_overflow_drops_oldest() -> None:
    """When the buffer fills, oldest events drop (FIFO)."""
    bad = _stub_client(insert_raises=RuntimeError("down"))
    for i in range(_BUFFER_MAX + 5):
        emit_event(bad, actor="skill:test", action=f"event-{i}")
    assert _buffer_len_for_test() == _BUFFER_MAX
