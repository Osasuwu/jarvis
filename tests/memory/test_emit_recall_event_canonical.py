"""``_emit_recall_event`` writes to events_canonical, not events (#1493 AC1).

memory_recall telemetry was 83% of the ``events`` perception queue rows —
the reactive-core orchestrator's ``claim_next`` FSM has to skip past them on
every poll. This reroutes the server-side recall-event producer onto the
append-only ``events_canonical`` substrate (C17, #477) via ``emit_event``,
wrapped in ``asyncio.to_thread`` since ``emit_event`` is a blocking call and
``_emit_recall_event`` is a fire-and-forget async task.

Modeled on tests/decisions/test_record_decision_canonical_dualwrite.py's
contract-style fakes (no deep MagicMock chains).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

# Import ``server`` first so the server <-> handlers.memory import chain is
# fully initialised before we grab the handler module directly — importing
# handlers.memory first triggers a partially-initialised circular import.
import server  # noqa: F401
import handlers.memory as mem
import events_canonical as events_canonical_mod


@pytest.fixture(autouse=True)
def _isolate_buffer() -> None:
    events_canonical_mod._buffer_clear_for_test()
    yield
    events_canonical_mod._buffer_clear_for_test()


class _FakeTable:
    """Records every ``.insert(payload)`` call; optionally raises on execute."""

    def __init__(self, name: str, *, raises: Exception | None = None) -> None:
        self._name = name
        self.insert_payloads: list[dict] = []
        self._raises = raises

    def insert(self, payload: dict):
        self.insert_payloads.append(payload)
        return self

    def execute(self):
        if self._raises is not None:
            raise self._raises
        return MagicMock(data=[{"event_id": "evt-1"}])


class _FakeClient:
    def __init__(self, *, canonical_raises: Exception | None = None) -> None:
        self._tables: dict[str, _FakeTable] = {}
        self._canonical_raises = canonical_raises

    def table(self, name: str) -> _FakeTable:
        if name not in self._tables:
            raises = self._canonical_raises if name == "events_canonical" else None
            self._tables[name] = _FakeTable(name, raises=raises)
        return self._tables[name]


class TestEmitRecallEventCanonical:
    @pytest.mark.asyncio
    async def test_writes_to_events_canonical_not_events(self):
        client = _FakeClient()
        payload = {
            "query": "test query",
            "returned_ids": ["mem-001", "mem-002"],
            "returned_similarities": [0.85, 0.70],
            "returned_count": 2,
            "top_sim": 0.85,
        }

        await mem._emit_recall_event(client, payload)

        assert "events" not in client._tables, "must not write to the legacy events queue"
        assert "events_canonical" in client._tables
        inserts = client._tables["events_canonical"].insert_payloads
        assert len(inserts) == 1
        row = inserts[0]
        assert row["actor"] == "mcp_memory:recall"
        assert row["action"] == "memory_recall"
        assert row["payload"] == payload
        assert "trace_id" in row

    @pytest.mark.asyncio
    async def test_failure_does_not_raise_and_buffers(self):
        client = _FakeClient(canonical_raises=RuntimeError("connection lost"))

        await mem._emit_recall_event(client, {"query": "x"})

        # emit_event's own degraded path buffers the row rather than raising —
        # confirms the failure was absorbed, not silently dropped.
        assert events_canonical_mod._buffer_len_for_test() == 1
