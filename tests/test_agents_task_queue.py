"""Unit tests for agents/task_queue.py (issue #740).

Tests enqueue, claim_next, and transition using a stub Supabase client.
No live DB.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from agents import task_queue


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------


@dataclass
class _Response:
    data: list[dict[str, Any]]


class _Table:
    """Stub table that records operations in a calls list."""

    def __init__(self, name: str, calls: list[Any], rows: list[dict[str, Any]]) -> None:
        self.name = name
        self.calls = calls
        self.seeded_rows = rows

    def select(self, *args: Any, **kwargs: Any) -> "_SelectQuery":
        return _SelectQuery(self)

    def upsert(self, payload: dict[str, Any], **kwargs: Any) -> "_UpsertQuery":
        return _UpsertQuery(self, payload, kwargs)

    def update(self, payload: dict[str, Any]) -> "_UpdateBuilder":
        return _UpdateBuilder(self, payload)


class _SelectQuery:
    def __init__(self, table: _Table) -> None:
        self._table = table
        self._filters: list[tuple[str, str, Any]] = []
        self._orders: list[tuple[str, bool]] = []
        self._limit_val: int | None = None
        self._cols: str | None = None

    def select(self, cols: str) -> "_SelectQuery":
        self._cols = cols
        return self

    def eq(self, col: str, val: Any) -> "_SelectQuery":
        self._filters.append(("eq", col, val))
        return self

    def order(self, col: str, *, desc: bool = False) -> "_SelectQuery":
        self._orders.append((col, desc))
        return self

    def limit(self, n: int) -> "_SelectQuery":
        self._limit_val = n
        return self

    def execute(self) -> _Response:
        rows = list(self._table.seeded_rows)
        for op, col, val in self._filters:
            if op == "eq":
                rows = [r for r in rows if r.get(col) == val]

        # Apply ordering
        for col, desc in self._orders:
            rows.sort(key=lambda r, c=col: r.get(c) or 0, reverse=desc)

        if self._limit_val:
            rows = rows[: self._limit_val]

        self._table.calls.append(
            ("select", self._table.name, {"filters": self._filters, "orders": self._orders})
        )
        return _Response(data=rows)


class _UpsertQuery:
    def __init__(self, table: _Table, payload: dict[str, Any], kwargs: dict[str, Any]) -> None:
        self._table = table
        self._payload = payload
        self._kwargs = kwargs

    def ignore_duplicates(self, val: bool) -> "_UpsertQuery":
        return self

    def execute(self) -> _Response:
        key = self._payload.get("idempotency_key")
        existing = [r for r in self._table.seeded_rows if r.get("idempotency_key") == key]

        self._table.calls.append(
            ("upsert", self._table.name, {"payload": self._payload, **self._kwargs})
        )

        if existing:
            return _Response(data=[])  # Duplicate, skipped

        stored = {**self._payload, "id": f"row-{len(self._table.seeded_rows)}"}
        self._table.seeded_rows.append(stored)
        return _Response(data=[stored])


class _UpdateBuilder:
    def __init__(self, table: _Table, payload: dict[str, Any]) -> None:
        self._table = table
        self._payload = payload
        self._filters: list[tuple[str, str, Any]] = []

    def eq(self, col: str, val: Any) -> "_UpdateBuilder":
        self._filters.append(("eq", col, val))
        return self

    def execute(self) -> _Response:
        self._table.calls.append(
            ("update", self._table.name, {"set": self._payload, "filters": self._filters})
        )

        # Apply update to matching rows.
        matching = list(self._table.seeded_rows)
        for op, col, val in self._filters:
            if op == "eq":
                matching = [r for r in matching if r.get(col) == val]

        if not matching:
            return _Response(data=[])

        updated = []
        for row in matching:
            row_copy = dict(row)
            row_copy.update(self._payload)
            updated.append(row_copy)
            # Update in-place in seeded_rows
            for i, r in enumerate(self._table.seeded_rows):
                if r.get("id") == row_copy.get("id"):
                    self._table.seeded_rows[i] = row_copy
                    break

        return _Response(data=updated)


class _StubClient:
    def __init__(self) -> None:
        self.calls: list[Any] = []
        self.rows: dict[str, list[dict[str, Any]]] = {
            "task_queue": [],
        }

    def table(self, name: str) -> _Table:
        return _Table(name, self.calls, self.rows.setdefault(name, []))

    def seed_task_queue(self, rows: list[dict[str, Any]]) -> None:
        self.rows["task_queue"].extend(rows)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_enqueue_inserts_row() -> None:
    client = _StubClient()
    result = task_queue.enqueue(
        client,
        goal="test task",
        scope_files=["a.py"],
        priority=1,
        assignee="user",
        idempotency_key="key-1",
    )

    assert result is not None
    assert result["goal"] == "test task"
    assert result["priority"] == 1
    assert result["assignee"] == "user"
    assert result["status"] == "pending"

    upserts = [c for c in client.calls if c[0] == "upsert"]
    assert len(upserts) == 1


def test_enqueue_duplicate_returns_none() -> None:
    client = _StubClient()
    task_queue.enqueue(client, goal="first", priority=1, idempotency_key="same")

    result = task_queue.enqueue(client, goal="second", priority=2, idempotency_key="same")
    assert result is None  # Duplicate, skipped

    rows = client.rows["task_queue"]
    assert len(rows) == 1
    assert rows[0]["goal"] == "first"


def test_enqueue_auto_idempotency_key() -> None:
    """If no idempotency_key provided, one is auto-generated."""
    client = _StubClient()
    result = task_queue.enqueue(client, goal="auto-key", priority=1)

    assert result is not None
    assert "idempotency_key" in result
    assert len(result["idempotency_key"]) == 64


def test_claim_next_returns_highest_priority() -> None:
    client = _StubClient()
    client.seed_task_queue(
        [
            {
                "id": "1",
                "goal": "low",
                "priority": 3,
                "assignee": None,
                "status": "pending",
                "idempotency_key": "k1",
            },
            {
                "id": "2",
                "goal": "high",
                "priority": 1,
                "assignee": None,
                "status": "pending",
                "idempotency_key": "k2",
            },
            {
                "id": "3",
                "goal": "medium",
                "priority": 2,
                "assignee": None,
                "status": "pending",
                "idempotency_key": "k3",
            },
        ]
    )

    result = task_queue.claim_next(client)

    assert result is not None
    assert result["id"] == "2"  # Highest priority (lowest number)
    assert result["status"] == "claimed"
    assert "claimed_at" in result


def test_claim_next_fifo_within_priority() -> None:
    """Same priority tasks are claimed in FIFO order (oldest first)."""
    client = _StubClient()
    client.seed_task_queue(
        [
            {
                "id": "old",
                "goal": "oldest",
                "priority": 1,
                "assignee": None,
                "status": "pending",
                "idempotency_key": "k1",
                "created_at": "2026-01-01T00:00:00",
            },
            {
                "id": "new",
                "goal": "newest",
                "priority": 1,
                "assignee": None,
                "status": "pending",
                "idempotency_key": "k2",
                "created_at": "2026-01-02T00:00:00",
            },
        ]
    )

    result = task_queue.claim_next(client)
    assert result["id"] == "old"  # Oldest first


def test_claim_next_no_pending_rows() -> None:
    client = _StubClient()
    result = task_queue.claim_next(client)
    assert result is None


def test_claim_next_skips_non_pending() -> None:
    """Only pending rows are eligible for claiming."""
    client = _StubClient()
    client.seed_task_queue(
        [
            {
                "id": "claimed",
                "goal": "already claimed",
                "priority": 1,
                "status": "claimed",
                "idempotency_key": "k1",
            },
            {
                "id": "done",
                "goal": "already done",
                "priority": 1,
                "status": "done",
                "idempotency_key": "k2",
            },
        ]
    )

    result = task_queue.claim_next(client)
    assert result is None


def test_transition_pending_to_claimed() -> None:
    client = _StubClient()
    client.seed_task_queue(
        [
            {
                "id": "t1",
                "goal": "test",
                "priority": 1,
                "status": "pending",
                "idempotency_key": "k1",
            }
        ]
    )

    result = task_queue.transition(client, "t1", "claimed")

    assert result["status"] == "claimed"
    assert "claimed_at" in result

    updates = [c for c in client.calls if c[0] == "update"]
    assert len(updates) == 1


def test_transition_running_to_done() -> None:
    client = _StubClient()
    client.seed_task_queue(
        [
            {
                "id": "t1",
                "goal": "test",
                "priority": 1,
                "status": "running",
                "idempotency_key": "k1",
            }
        ]
    )

    result = task_queue.transition(client, "t1", "done", outcome_note="completed successfully")

    assert result["status"] == "done"
    assert "completed_at" in result
    assert result["outcome_note"] == "completed successfully"


def test_transition_invalid_raises() -> None:
    client = _StubClient()
    client.seed_task_queue(
        [
            {
                "id": "t1",
                "goal": "test",
                "priority": 1,
                "status": "pending",
                "idempotency_key": "k1",
            }
        ]
    )

    with pytest.raises(ValueError, match="Invalid transition"):
        task_queue.transition(client, "t1", "done")  # pending -> done is invalid


def test_transition_nonexistent_row_raises() -> None:
    client = _StubClient()
    with pytest.raises(ValueError, match="not found"):
        task_queue.transition(client, "nonexistent", "claimed")


def test_full_lifecycle() -> None:
    """End-to-end FSM: enqueue -> claim -> run -> done."""
    client = _StubClient()

    # Enqueue
    row = task_queue.enqueue(client, goal="lifecycle test", priority=1, idempotency_key="lifecycle")
    assert row is not None
    row_id = row["id"]

    # Claim
    claimed = task_queue.claim_next(client)
    assert claimed is not None
    assert claimed["id"] == row_id
    assert claimed["status"] == "claimed"

    # Transition to running
    running = task_queue.transition(client, row_id, "running")
    assert running["status"] == "running"

    # Transition to done
    done = task_queue.transition(client, row_id, "done", outcome_note="all good")
    assert done["status"] == "done"
    assert done["outcome_note"] == "all good"
