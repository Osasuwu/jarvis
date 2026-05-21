"""Unit tests for dispatcher escalation triggers (issue #299, S2-4, refactored #740).

Pure-check tests use hand-rolled dict rows; DB-write tests use a stub
Supabase client that records the insert/update call shape. No live DB.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from agents.escalation import (
    DISPATCHER_AGENT_ID,
    ESCALATION_EVENT_TYPE,
    ESCALATION_SEVERITY,
    PATTERN_REPEAT_THRESHOLD,
    EscalationCheck,
    EscalationContext,
    Trigger,
    check_all,
    check_cross_task_conflict,
    check_limit_near_exhaustion,
    check_pattern_repeat,
    escalate,
)
from agents.usage_probe import UsageReading


# ---------------------------------------------------------------------------
# Fixtures / builders
# ---------------------------------------------------------------------------


def _queue_row(**overrides: Any) -> dict[str, Any]:
    base = {
        "id": "00000000-0000-0000-0000-000000000001",
        "goal": "refactor: split usage_probe tests",
        "scope_files": ["tests/test_agents_usage_probe.py"],
        "priority": 1,
        "assignee": "owner",
        "status": "pending",
        "idempotency_key": "deadbeef",
    }
    base.update(overrides)
    return base


def _reading(near: bool, used: int = 20, total: int = 100) -> UsageReading:
    return UsageReading(
        limit_window=timedelta(hours=5),
        used=used,
        total=total,
        reset_at=datetime.now(UTC),
        near_exhaustion=near,
    )


# ---------------------------------------------------------------------------
# check_limit_near_exhaustion
# ---------------------------------------------------------------------------


def test_limit_escalates_when_probe_reports_near_exhaustion() -> None:
    result = check_limit_near_exhaustion(_reading(near=True, used=90, total=100))
    assert result.should_escalate is True
    assert result.trigger == Trigger.LIMIT_NEAR_EXHAUSTION
    assert result.context["used"] == 90
    assert result.context["total"] == 100
    assert 0.0 <= result.context["headroom_ratio"] <= 1.0


def test_limit_does_not_escalate_when_probe_reports_headroom() -> None:
    result = check_limit_near_exhaustion(_reading(near=False, used=10, total=100))
    assert result.should_escalate is False


# ---------------------------------------------------------------------------
# check_cross_task_conflict
# ---------------------------------------------------------------------------


def test_cross_task_conflict_overlap_escalates() -> None:
    row = _queue_row(id="me", scope_files=["a.py", "b.py"])
    others = [
        {"id": "other", "scope_files": ["b.py", "c.py"]},
    ]
    result = check_cross_task_conflict(row, active_dispatched_rows=others)
    assert result.should_escalate is True
    assert result.trigger == Trigger.CROSS_TASK_CONFLICT
    assert result.context["conflicting_task_id"] == "other"
    assert result.context["overlapping_files"] == ["b.py"]


def test_cross_task_conflict_disjoint_does_not_escalate() -> None:
    row = _queue_row(id="me", scope_files=["a.py"])
    others = [{"id": "other", "scope_files": ["x.py"]}]
    result = check_cross_task_conflict(row, active_dispatched_rows=others)
    assert result.should_escalate is False


def test_cross_task_conflict_same_id_is_ignored() -> None:
    """Defensive: even if caller forgot to exclude this row, we do."""
    row = _queue_row(id="me", scope_files=["a.py"])
    result = check_cross_task_conflict(
        row, active_dispatched_rows=[{"id": "me", "scope_files": ["a.py"]}]
    )
    assert result.should_escalate is False


def test_cross_task_conflict_empty_scope_does_not_escalate() -> None:
    row = _queue_row(id="me", scope_files=[])
    others = [{"id": "other", "scope_files": ["a.py"]}]
    result = check_cross_task_conflict(row, active_dispatched_rows=others)
    assert result.should_escalate is False


def test_cross_task_conflict_first_overlap_wins() -> None:
    """Stability: we report the first conflicting peer, not all of them."""
    row = _queue_row(id="me", scope_files=["a.py"])
    others = [
        {"id": "peer1", "scope_files": ["a.py"]},
        {"id": "peer2", "scope_files": ["a.py"]},
    ]
    result = check_cross_task_conflict(row, active_dispatched_rows=others)
    assert result.context["conflicting_task_id"] == "peer1"


# ---------------------------------------------------------------------------
# check_pattern_repeat
# ---------------------------------------------------------------------------


def test_pattern_repeat_escalates_above_threshold() -> None:
    row = _queue_row(goal="auto-label cleanup")
    recent = [{"goal": "auto-label cleanup"}] * (PATTERN_REPEAT_THRESHOLD + 1)
    result = check_pattern_repeat(row, recent_successful_dispatches=recent)
    assert result.should_escalate is True
    assert result.trigger == Trigger.PATTERN_REPEAT
    assert result.context["recent_matching_dispatches"] == PATTERN_REPEAT_THRESHOLD + 1
    assert result.context["threshold"] == PATTERN_REPEAT_THRESHOLD


def test_pattern_repeat_at_threshold_does_not_escalate() -> None:
    """Issue says '> 3', so exactly 3 should pass."""
    row = _queue_row(goal="x")
    recent = [{"goal": "x"}] * PATTERN_REPEAT_THRESHOLD
    result = check_pattern_repeat(row, recent_successful_dispatches=recent)
    assert result.should_escalate is False


def test_pattern_repeat_different_goal_resets_run() -> None:
    """A different goal anywhere in the newest-first list breaks the run."""
    row = _queue_row(goal="x")
    recent = [
        {"goal": "x"},
        {"goal": "x"},
        {"goal": "different"},
        {"goal": "x"},
        {"goal": "x"},
    ]
    result = check_pattern_repeat(row, recent_successful_dispatches=recent)
    assert result.should_escalate is False


def test_pattern_repeat_missing_goal_does_not_escalate() -> None:
    row = _queue_row()
    row.pop("goal")
    result = check_pattern_repeat(row, recent_successful_dispatches=[{"goal": "whatever"}] * 10)
    assert result.should_escalate is False


def test_pattern_repeat_custom_threshold() -> None:
    row = _queue_row(goal="x")
    result = check_pattern_repeat(
        row, recent_successful_dispatches=[{"goal": "x"}, {"goal": "x"}], threshold=1
    )
    assert result.should_escalate is True


# ---------------------------------------------------------------------------
# check_all — aggregator
# ---------------------------------------------------------------------------


def test_check_all_no_triggers_returns_no_action() -> None:
    row = _queue_row()
    ctx = EscalationContext(
        usage_reading=_reading(near=False),
    )
    result = check_all(row, ctx)
    assert result.should_escalate is False


def test_check_all_limit_fires() -> None:
    row = _queue_row()
    ctx = EscalationContext(
        usage_reading=_reading(near=True, used=90, total=100),
    )
    result = check_all(row, ctx)
    assert result.trigger == Trigger.LIMIT_NEAR_EXHAUSTION


# ---------------------------------------------------------------------------
# escalate() — DB side effect via stub client.
# ---------------------------------------------------------------------------


@dataclass
class _StubResponse:
    data: list[dict[str, Any]]


class _StubUpdateQuery:
    def __init__(self, table: "_StubTable") -> None:
        self._table = table
        self._update: dict[str, Any] = {}

    def update(self, payload: dict[str, Any]) -> "_StubUpdateQuery":
        self._update = payload
        return self

    def eq(self, col: str, val: Any) -> "_StubUpdateQuery":
        self._table.calls.append(
            ("update", self._table.name, {"match": {col: val}, "set": self._update})
        )
        return self

    def execute(self) -> _StubResponse:
        return _StubResponse(data=[self._update])


class _StubInsertQuery:
    def __init__(self, table: "_StubTable", payload: dict[str, Any]) -> None:
        self._table = table
        self._payload = payload

    def execute(self) -> _StubResponse:
        stored = {**self._payload, "id": f"{self._table.name}-evt-1"}
        self._table.calls.append(("insert", self._table.name, self._payload))
        return _StubResponse(data=[stored])


class _StubTable:
    def __init__(self, name: str, calls: list[Any]) -> None:
        self.name = name
        self.calls = calls

    def insert(self, payload: dict[str, Any]) -> _StubInsertQuery:
        return _StubInsertQuery(self, payload)

    def update(self, payload: dict[str, Any]) -> _StubUpdateQuery:
        q = _StubUpdateQuery(self)
        return q.update(payload)


class _StubClient:
    def __init__(self) -> None:
        self.calls: list[Any] = []

    def table(self, name: str) -> _StubTable:
        return _StubTable(name, self.calls)


def test_escalate_writes_event_with_expected_shape() -> None:
    client = _StubClient()
    row = _queue_row(id="11111111-1111-1111-1111-111111111111", goal="cleanup")
    check = EscalationCheck(
        should_escalate=True,
        trigger=Trigger.LIMIT_NEAR_EXHAUSTION,
        context={"used": 90, "total": 100, "headroom_ratio": 0.1},
    )
    result = escalate(row, check, client=client)
    insert_calls = [c for c in client.calls if c[0] == "insert"]
    assert len(insert_calls) == 1
    _, table, payload = insert_calls[0]
    assert table == "events"
    assert payload["event_type"] == ESCALATION_EVENT_TYPE
    assert payload["severity"] == ESCALATION_SEVERITY
    assert payload["source"] == DISPATCHER_AGENT_ID
    assert payload["payload"]["queue_id"] == row["id"]
    assert payload["payload"]["trigger"] == Trigger.LIMIT_NEAR_EXHAUSTION.value
    assert payload["payload"]["context"] == check.context
    # Title should carry both id and trigger for quick scanning.
    assert row["id"] in payload["title"]
    assert Trigger.LIMIT_NEAR_EXHAUSTION.value in payload["title"]
    # And the returned event should have the stubbed id.
    assert "id" in result


def test_escalate_updates_queue_row_to_parked() -> None:
    client = _StubClient()
    row = _queue_row(id="11111111-1111-1111-1111-111111111111")
    check = EscalationCheck(
        should_escalate=True,
        trigger=Trigger.CROSS_TASK_CONFLICT,
        context={"conflicting_task_id": "peer", "overlapping_files": ["a.py"]},
    )
    escalate(row, check, client=client)
    update_calls = [c for c in client.calls if c[0] == "update"]
    assert len(update_calls) == 1
    _, table, payload = update_calls[0]
    assert table == "task_queue"
    assert payload["match"] == {"id": row["id"]}
    assert payload["set"]["status"] == "parked"
    assert "cross_task_conflict" in payload["set"]["outcome_note"]


def test_escalate_rejects_non_escalating_check() -> None:
    client = _StubClient()
    row = _queue_row()
    with pytest.raises(ValueError, match="non-escalating"):
        escalate(row, EscalationCheck.no_action(), client=client)


def test_escalate_without_id_skips_queue_update_but_writes_event() -> None:
    """An id-less row (hand-built in a test, hypothetically) still records the event."""
    client = _StubClient()
    row = _queue_row()
    row.pop("id")
    check = EscalationCheck(
        should_escalate=True,
        trigger=Trigger.LIMIT_NEAR_EXHAUSTION,
        context={"used": 90},
    )
    escalate(row, check, client=client)
    inserts = [c for c in client.calls if c[0] == "insert"]
    updates = [c for c in client.calls if c[0] == "update"]
    assert len(inserts) == 1
    assert len(updates) == 0
    assert inserts[0][2]["payload"]["queue_id"] is None


def test_escalate_context_round_trips_to_payload() -> None:
    """Nested dict context should survive into the events.payload jsonb."""
    client = _StubClient()
    row = _queue_row(id="x")
    context = {
        "conflicting_task_id": "peer",
        "overlapping_files": ["a.py", "b.py"],
        "nested": {"k": 1},
    }
    check = EscalationCheck(
        should_escalate=True, trigger=Trigger.CROSS_TASK_CONFLICT, context=context
    )
    escalate(row, check, client=client)
    insert = [c for c in client.calls if c[0] == "insert"][0]
    assert insert[2]["payload"]["context"] == context
