"""Tests for the parked-event re-queue poller (#745 — Path B).

The poller re-queues ``parked`` events when their blocking task reaches a
terminal state (``done``, ``failed``, or ``parked``). It is a pure function
over a :class:`PollerPort` interface — every test uses an in-memory fake so
no live database is required.
"""

from __future__ import annotations

import json
import os
import uuid
from typing import Any

import pytest

from agents import poller


# ---------------------------------------------------------------------------
# FSM-faithful fake
# ---------------------------------------------------------------------------


class FakePollerPort:
    """In-memory :class:`PollerPort` holding both events and tasks.

    Events and tasks are plain dicts. The fake mirrors the subset of each
    FSM that the poller observes — it does not enforce state transitions
    (that is the real database's job).
    """

    def __init__(
        self,
        events: list[dict[str, Any]] | None = None,
        tasks: list[dict[str, Any]] | None = None,
    ) -> None:
        self.events: list[dict[str, Any]] = events or []
        self.tasks: list[dict[str, Any]] = tasks or []
        self.requeue_calls: list[tuple[str, str]] = []  # (event_id, reason)

    # -- PollerPort surface --------------------------------------------------

    def find_parked_events(self) -> list[dict[str, Any]]:
        """Return parked events whose ``blocked_by_task_id`` column is set (#1455 AC4)."""
        result: list[dict[str, Any]] = []
        for ev in self.events:
            if ev.get("state") != "parked":
                continue
            tid = ev.get("blocked_by_task_id")
            # Mirror the production guard (_blocking_task_id): present-but-falsy
            # ids such as int 0 must survive — a truthiness test would drop them
            # and silently strand the event.
            if tid is not None and tid != "":
                result.append(ev)
        return result

    def get_task_statuses(self, task_ids: list[str]) -> dict[str, str]:
        result: dict[str, str] = {}
        for t in self.tasks:
            tid = t.get("id")
            if tid in task_ids and t.get("status") is not None:
                result[tid] = t["status"]
        return result

    def requeue_event(self, event_id: str, *, reason: str) -> bool:
        for ev in self.events:
            if ev["id"] == event_id:
                if ev["state"] != "parked":
                    return False
                ev["state"] = "pending"
                self.requeue_calls.append((event_id, reason))
                return True
        return False

    # -- test helpers --------------------------------------------------------

    def state_of(self, event_id: str) -> str:
        return next(ev["state"] for ev in self.events if ev["id"] == event_id)

    def task_status(self, task_id: str) -> str | None:
        return self.get_task_statuses([task_id]).get(task_id)


def _ev(
    eid: str,
    task_id: str | None = None,
    state: str = "parked",
) -> dict[str, Any]:
    """Build an event dict. ``task_id`` lands in the dedicated column (#1455 AC4),
    never in payload — payload stays immutable so the replay's idempotency key
    is unchanged."""
    return {"id": eid, "state": state, "blocked_by_task_id": task_id, "payload": {}}


def _task(tid: str, status: str) -> dict[str, Any]:
    return {"id": tid, "status": status}


# ===========================================================================
# AC1: done task → event requeued
# ===========================================================================


class TestBlockingTaskDone:
    """When the blocking task reaches ``done``, the event is re-queued."""

    def test_requeues_parked_event_when_task_is_done(self):
        port = FakePollerPort(
            events=[_ev("e1", task_id="t1")],
            tasks=[_task("t1", "done")],
        )
        n = poller.poll(port)
        assert n == 1
        assert port.state_of("e1") == "pending"
        assert len(port.requeue_calls) == 1
        assert port.requeue_calls[0][0] == "e1"
        assert "completed" in port.requeue_calls[0][1]

    def test_requeues_multiple_events_when_all_tasks_done(self):
        port = FakePollerPort(
            events=[_ev("e1", task_id="t1"), _ev("e2", task_id="t2")],
            tasks=[_task("t1", "done"), _task("t2", "done")],
        )
        n = poller.poll(port)
        assert n == 2
        assert port.state_of("e1") == "pending"
        assert port.state_of("e2") == "pending"


# ===========================================================================
# AC2: running task → event stays parked
# ===========================================================================


class TestBlockingTaskStillRunning:
    """A task that is still ``running`` leaves the event parked."""

    def test_does_not_requeue_when_task_still_running(self):
        port = FakePollerPort(
            events=[_ev("e1", task_id="t1")],
            tasks=[_task("t1", "running")],
        )
        n = poller.poll(port)
        assert n == 0
        assert port.state_of("e1") == "parked"
        assert port.requeue_calls == []


# ===========================================================================
# AC2b (#1119): parked task is non-terminal → event stays parked
# ===========================================================================


class TestBlockingTaskParked:
    """A ``parked`` blocking task is non-terminal (#1119) — the event must
    stay parked, same as a still-``running`` blocking task.

    ``parked`` is no longer in ``task_queue._TERMINAL_STATES``: its only
    legal edge is back to ``pending`` (unpark), after which it resumes
    through the normal claim/drain cycle and may still reach ``done`` or
    ``failed``. Requeueing the blocked event early would hand it to the
    orchestrator before the blocking task's outcome is known.
    """

    def test_does_not_requeue_event_when_task_parked(self):
        port = FakePollerPort(
            events=[_ev("e1", task_id="t1")],
            tasks=[_task("t1", "parked")],
        )
        n = poller.poll(port)
        assert n == 0
        assert port.state_of("e1") == "parked"
        assert port.requeue_calls == []


# ===========================================================================
# AC3: failed task → event requeued (not silently dropped)
# ===========================================================================


class TestBlockingTaskFailed:
    """A ``failed`` task causes the event to be re-queued for the orchestrator."""

    def test_requeues_event_when_task_failed(self):
        port = FakePollerPort(
            events=[_ev("e1", task_id="t1")],
            tasks=[_task("t1", "failed")],
        )
        n = poller.poll(port)
        assert n == 1
        assert port.state_of("e1") == "pending"
        assert len(port.requeue_calls) == 1
        assert "failed" in port.requeue_calls[0][1]

    def test_mixed_states_only_requeues_terminal(self):
        """Terminal tasks (done/failed) requeue; running/parked (#1119) stay."""
        port = FakePollerPort(
            events=[
                _ev("e-done", task_id="t-done"),
                _ev("e-failed", task_id="t-failed"),
                _ev("e-running", task_id="t-running"),
                _ev("e-parked", task_id="t-parked"),
            ],
            tasks=[
                _task("t-done", "done"),
                _task("t-failed", "failed"),
                _task("t-running", "running"),
                _task("t-parked", "parked"),
            ],
        )
        n = poller.poll(port)
        assert n == 2  # done + failed only — parked (#1119) is non-terminal now
        assert port.state_of("e-done") == "pending"
        assert port.state_of("e-failed") == "pending"
        assert port.state_of("e-parked") == "parked"  # non-terminal, stays
        assert port.state_of("e-running") == "parked"  # non-terminal, stays


# ===========================================================================
# Edge cases
# ===========================================================================


class TestEdgeCases:
    """Events without blocked_by_task_id, missing tasks, empty queue."""

    def test_no_blocking_task_id_is_skipped(self):
        """Parked event without ``blocked_by_task_id`` in payload is skipped."""
        port = FakePollerPort(
            events=[
                _ev("e-no-ref", task_id=None),  # no blocked_by_task_id
            ],
        )
        n = poller.poll(port)
        assert n == 0
        assert port.state_of("e-no-ref") == "parked"

    def test_unknown_task_id_is_skipped(self):
        """When the referenced task does not exist, the event stays parked."""
        port = FakePollerPort(
            events=[_ev("e1", task_id="nonexistent")],
            tasks=[],  # no matching task
        )
        n = poller.poll(port)
        assert n == 0
        assert port.state_of("e1") == "parked"

    def test_empty_parked_queue_is_a_noop(self):
        port = FakePollerPort(events=[], tasks=[])
        assert poller.poll(port) == 0

    def test_non_parked_events_are_ignored(self):
        """Only parked events are evaluated — pending/claimed/processed are skipped."""
        port = FakePollerPort(
            events=[
                _ev("e-pending", task_id="t1", state="pending"),
                _ev("e-claimed", task_id="t2", state="claimed"),
                _ev("e-processed", task_id="t3", state="processed"),
            ],
            tasks=[
                _task("t1", "done"),
                _task("t2", "done"),
                _task("t3", "done"),
            ],
        )
        n = poller.poll(port)
        assert n == 0  # no parked events with blocked_by_task_id

    def test_requeue_event_returns_false_for_nonexistent_event(self):
        port = FakePollerPort(events=[], tasks=[])
        result = port.requeue_event("no-such-event", reason="test")
        assert result is False

    def test_unknown_task_status_leaves_event_parked(self):
        """A novel task status (e.g. future ``cancelled``) leaves the event parked."""
        port = FakePollerPort(
            events=[_ev("e1", task_id="t1")],
            tasks=[_task("t1", "cancelled")],
        )
        n = poller.poll(port)
        assert n == 0
        assert port.state_of("e1") == "parked"

    def test_requeue_already_pending_event_returns_false(self):
        """FakePollerPort mirrors production: requeue only from parked state."""
        port = FakePollerPort(
            events=[_ev("e1", task_id="t1", state="pending")],
            tasks=[_task("t1", "done")],
        )
        result = port.requeue_event("e1", reason="test")
        assert result is False


# ===========================================================================
# _blocking_task_id — dedicated column, not payload (#1455 AC4)
# ===========================================================================


class TestBlockingTaskIdParsing:
    """Direct tests for the column extractor — the payload marker is dead."""

    def test_preserves_integer_zero(self):
        """A falsy-but-present task id (int ``0``) must survive, not be dropped."""
        ev = {"id": "e1", "state": "parked", "blocked_by_task_id": 0}
        assert poller._blocking_task_id(ev) == "0"

    def test_empty_string_task_id_is_none(self):
        ev = {"id": "e1", "state": "parked", "blocked_by_task_id": ""}
        assert poller._blocking_task_id(ev) is None

    def test_missing_column_is_none(self):
        ev = {"id": "e1", "state": "parked"}
        assert poller._blocking_task_id(ev) is None

    def test_null_column_is_none(self):
        ev = {"id": "e1", "state": "parked", "blocked_by_task_id": None}
        assert poller._blocking_task_id(ev) is None

    def test_payload_marker_is_not_read(self):
        """AC4 boundary: a legacy payload marker without the column must NOT
        resurrect the event — the column is the only carrier."""
        ev = {
            "id": "e1",
            "state": "parked",
            "blocked_by_task_id": None,
            "payload": {"blocked_by_task_id": "t9"},
        }
        assert poller._blocking_task_id(ev) is None


# ===========================================================================
# Poison-pill exclusion (#1455 AC8 — #1385 boundary preserved)
# ===========================================================================


class TestPoisonPillExclusion:
    """Crash-parked events (#1385 poison-pill path, ``park()``/``park_event``)
    carry ``blocked_by_task_id`` NULL and are structurally excluded from the
    sweep — they stay parked until a human intervenes."""

    def test_poison_pill_parked_event_is_never_requeued(self):
        poison = {
            "id": "e-pp",
            "state": "parked",
            "blocked_by_task_id": None,
            # Sneaky legacy marker in payload — proves the column governs.
            "payload": {"blocked_by_task_id": "t1"},
        }
        port = FakePollerPort(events=[poison], tasks=[_task("t1", "done")])
        n = poller.poll(port)
        assert n == 0
        assert port.state_of("e-pp") == "parked"
        assert port.requeue_calls == []


# ===========================================================================
# Robustness: per-event isolation + confirmed-requeue counting (#964 MAJOR #3/#4)
# ===========================================================================


class _RaisingStatusPort(FakePollerPort):
    """Fake whose batch status probe raises when a specific task id is requested."""

    def __init__(self, *, raise_for: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._raise_for = raise_for

    def get_task_statuses(self, task_ids: list[str]) -> dict[str, str]:
        if self._raise_for in task_ids:
            raise RuntimeError("status probe blew up")
        return super().get_task_statuses(task_ids)


class _FalseRequeuePort(FakePollerPort):
    """Fake whose ``requeue_event`` reports the transition was NOT applied."""

    def requeue_event(self, event_id: str, *, reason: str) -> bool:
        return False


class _RaisingRequeuePort(FakePollerPort):
    """Fake whose ``requeue_event`` raises for one specific event id."""

    def __init__(self, *, raise_for: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._raise_for = raise_for

    def requeue_event(self, event_id: str, *, reason: str) -> bool:
        if event_id == self._raise_for:
            raise RuntimeError("requeue blew up")
        return super().requeue_event(event_id, reason=reason)


class _RaisingFindPort(FakePollerPort):
    """Fake whose ``find_parked_events`` raises — simulates a query outage."""

    def find_parked_events(self) -> list[dict[str, Any]]:
        raise RuntimeError("find_parked_events blew up")


class TestPollRobustness:
    def test_status_probe_failure_leaves_all_events_parked_for_next_pass(self):
        """A batch status-fetch failure must not lose events, and must not
        raise out of ``poll()`` — it leaves every parked event in this sweep
        parked (not just the one whose task id triggered the failure), since
        statuses are now fetched in a single batch call per sweep (#1475
        review, MEDIUM) rather than one call per event."""
        port = _RaisingStatusPort(
            raise_for="t-bad",
            events=[_ev("e-bad", task_id="t-bad"), _ev("e-good", task_id="t-good")],
            tasks=[_task("t-bad", "done"), _task("t-good", "done")],
        )
        n = poller.poll(port)
        assert n == 0  # batch failure aborts the whole sweep, not just e-bad
        assert port.state_of("e-good") == "parked"  # left parked, not lost
        assert port.state_of("e-bad") == "parked"  # left parked, not lost

    def test_unconfirmed_requeue_is_not_counted(self):
        """``requeue_event`` returning False means no transition → don't count it."""
        port = _FalseRequeuePort(
            events=[_ev("e1", task_id="t1")],
            tasks=[_task("t1", "done")],
        )
        n = poller.poll(port)
        assert n == 0

    def test_unconfirmed_requeue_for_failed_task_is_not_counted(self):
        port = _FalseRequeuePort(
            events=[_ev("e1", task_id="t1")],
            tasks=[_task("t1", "failed")],
        )
        assert poller.poll(port) == 0

    def test_requeue_raising_on_one_event_does_not_strand_the_rest(self):
        """A ``requeue_event`` failure on one event must not abort the sweep."""
        port = _RaisingRequeuePort(
            raise_for="e-bad",
            events=[_ev("e-bad", task_id="t-bad"), _ev("e-good", task_id="t-good")],
            tasks=[_task("t-bad", "done"), _task("t-good", "done")],
        )
        n = poller.poll(port)
        assert n == 1  # the good event still requeued
        assert port.state_of("e-good") == "pending"
        assert port.state_of("e-bad") == "parked"  # left parked, not lost

    def test_find_parked_events_failure_propagates_to_caller(self):
        """``poll()`` does not swallow a ``find_parked_events`` outage.

        The whole sweep is wrapped in a try/except by the wake_driver's tick
        (Step 2b) so a query outage retries next tick — but ``poll()`` itself
        surfaces the failure rather than reporting a false ``0`` requeued.
        """
        port = _RaisingFindPort()
        with pytest.raises(RuntimeError):
            poller.poll(port)


# ===========================================================================
# Wake-driver integration: tick calls the poller
# ===========================================================================


class _MinimalFakeEventQueue:
    """Minimal EventQueuePort stub for the integration test.

    ``claim_next`` returns ``None`` (empty pool) so the drain is a no-op
    and we can focus on the poller step.
    """

    def __init__(self) -> None:
        self.wake_signals: list[bool] = []

    def claim_next(self) -> None:
        return None

    def mark_processed(self, event_id: str, *, action: str = "") -> bool:
        return False

    def reclaim_stale(self, *, older_than_seconds: float) -> int:
        return 0

    def wait_for_wake(self, *, timeout_seconds: float | None) -> bool:
        if self.wake_signals:
            return self.wake_signals.pop(0)
        return False


def test_tick_calls_poller_when_port_provided():
    """``tick()`` re-queues parked events when ``poller_port`` is given."""
    from agents import wake_driver

    poller_port = FakePollerPort(
        events=[_ev("e1", task_id="t1")],
        tasks=[_task("t1", "done")],
    )
    event_q = _MinimalFakeEventQueue()

    result = wake_driver.tick(
        event_q,
        wake_driver.default_orchestrator,
        stale_after_seconds=300,
        poller_port=poller_port,
    )

    assert result.requeued == 1
    assert poller_port.state_of("e1") == "pending"


def test_tick_skips_poller_when_port_is_none():
    """``tick()`` without ``poller_port`` works as before (backward compat)."""
    from agents import wake_driver

    q = _MinimalFakeEventQueue()
    result = wake_driver.tick(
        q,
        wake_driver.default_orchestrator,
        stale_after_seconds=300,
    )

    assert result.requeued == 0
    assert result.reclaimed == 0
    assert result.processed == 0


class _RaisingPollerPort:
    """A poller port whose sweep always raises — simulates a poller outage."""

    def find_parked_events(self) -> list[dict[str, Any]]:
        raise RuntimeError("poller down")

    def get_task_statuses(self, task_ids: list[str]) -> dict[str, str]:
        return {}

    def requeue_event(self, event_id: str, *, reason: str) -> bool:
        return False


class _OneEventQueue(_MinimalFakeEventQueue):
    """Yields a single pending event once, then drains empty."""

    def __init__(self) -> None:
        super().__init__()
        self._pending: list[dict[str, Any]] = [{"id": "ev-1"}]
        self.processed_ids: list[str] = []

    def claim_next(self) -> dict[str, Any] | None:
        if self._pending:
            return self._pending.pop(0)
        return None

    def mark_processed(self, event_id: str, *, action: str = "") -> bool:
        self.processed_ids.append(event_id)
        return True


def test_tick_poller_exception_does_not_skip_event_drain():
    """CRITICAL #2: a poller blow-up must not abort the event drain (Step 3).

    Without the try/except around the poll step, the raise propagates out of
    ``tick()`` before ``drain_pending`` runs — stranding every event claimed
    this pass. The drain is the primary wake path and must survive a poller
    outage.
    """
    from agents import wake_driver

    q = _OneEventQueue()
    result = wake_driver.tick(
        q,
        wake_driver.default_orchestrator,
        stale_after_seconds=300,
        poller_port=_RaisingPollerPort(),
    )

    assert result.processed == 1  # event drained despite the poller failure
    assert q.processed_ids == ["ev-1"]
    assert result.requeued == 0  # poller produced nothing


def test_run_forwards_poller_port_to_tick():
    """MAJOR #5: ``run()`` must thread ``poller_port`` through to each ``tick()``."""
    from agents import wake_driver

    poller_port = FakePollerPort(
        events=[_ev("e1", task_id="t1")],
        tasks=[_task("t1", "done")],
    )
    q = _MinimalFakeEventQueue()
    q.wake_signals = [True]

    calls = {"n": 0}

    def should_continue() -> bool:
        calls["n"] += 1
        return calls["n"] <= 1  # exactly one tick

    wake_driver.run(
        q,
        wake_driver.default_orchestrator,
        stale_after_seconds=300,
        should_continue=should_continue,
        poller_port=poller_port,
    )

    # The single tick forwarded poller_port and requeued the parked event.
    assert poller_port.state_of("e1") == "pending"
    assert poller_port.requeue_calls
    assert poller_port.requeue_calls[0][0] == "e1"


# ---------------------------------------------------------------------------
# E2E: live-database poller/tick behavior (AC4/AC5, issue #1393)
# ---------------------------------------------------------------------------
#
# Gated on ``AGENTS_E2E_POSTGRES_URL`` — a dedicated live Postgres connection
# string, deliberately distinct from the production ``AGENTS_POSTGRES_URL`` so
# these tests never run against a live orchestrator's database by accident.
# Skipped (not failed) when unset, which is every environment except a
# deliberately provisioned E2E database (decision `7283d043`).

_E2E_POSTGRES_URL = os.environ.get("AGENTS_E2E_POSTGRES_URL")

_e2e = pytest.mark.skipif(
    not _E2E_POSTGRES_URL,
    reason="AGENTS_E2E_POSTGRES_URL not set — skipping live-database E2E test",
)


def _insert_parked_event(conn: Any, *, blocked_by_task_id: str | None) -> str:
    """Insert a ``parked`` events row directly via SQL.

    The ``blocked_by_task_id`` column (#1455 AC4) marks the event as blocked
    on a task — payload stays empty, mirroring production where the payload
    is never mutated. Direct insert because the parking RPCs
    (``park_event``, ``park_blocked_on_task``) require ``state='claimed'``
    as a precondition, which itself needs a claimed fixture row first.
    """
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO events "
            "(event_type, severity, repo, source, title, payload, state, blocked_by_task_id) "
            "VALUES (%s, %s, %s, %s, %s, %s::jsonb, 'parked', %s) RETURNING id",
            (
                "ci_failure",
                "high",
                "test/e2e",
                "test_poller_e2e",
                "E2E poller fixture",
                json.dumps({}),
                blocked_by_task_id,
            ),
        )
        event_id = cur.fetchone()[0]
    conn.commit()
    return str(event_id)


def _event_state(conn: Any, event_id: str) -> str:
    with conn.cursor() as cur:
        cur.execute("SELECT state FROM events WHERE id = %s", (event_id,))
        row = cur.fetchone()
    conn.commit()
    assert row is not None, f"event {event_id} vanished"
    return row[0]


def _event_row(conn: Any, event_id: str) -> tuple[str, str | None]:
    """Return ``(state, blocked_by_task_id)`` for an event."""
    with conn.cursor() as cur:
        cur.execute("SELECT state, blocked_by_task_id FROM events WHERE id = %s", (event_id,))
        row = cur.fetchone()
    conn.commit()
    assert row is not None, f"event {event_id} vanished"
    state, blocked = row
    return state, (str(blocked) if blocked is not None else None)


@_e2e
def test_poller_e2e_requeues_and_processes_event_once_blocking_task_is_done():
    """AC4: parked event + terminal blocking task → one tick → processed + follow-up task."""
    import psycopg

    from agents import orchestrator, task_queue, wake_driver
    from agents.orchestrator import _idempotency_key, _target_of
    from agents.supabase_client import get_client

    client = get_client()
    conn = psycopg.connect(_E2E_POSTGRES_URL)
    event_id: str | None = None
    blocking_task_id: str | None = None
    followup_key: str | None = None
    try:
        blocking = task_queue.enqueue(
            goal="E2E poller fixture — blocking task",
            idempotency_key=f"e2e-poller-blocking-{uuid.uuid4()}",
            client=client,
        )
        blocking_task_id = blocking["id"]
        task_queue.transition(blocking_task_id, "claimed", client=client)
        task_queue.transition(blocking_task_id, "running", client=client)
        task_queue.transition(blocking_task_id, "done", client=client)

        event_id = _insert_parked_event(conn, blocked_by_task_id=blocking_task_id)
        # The requeued event drains with its ORIGINAL (empty) payload — the
        # column carrier never touches it — so the follow-up task's
        # idempotency key is computed over that unchanged payload (#1455 AC4).
        payload: dict[str, Any] = {}
        followup_key = _idempotency_key("ci_failure", _target_of(payload), payload)

        queue = wake_driver.PsycopgEventQueue(conn)
        prod_orchestrator = orchestrator.build_production_orchestrator(client=client)

        wake_driver.tick(queue, prod_orchestrator, stale_after_seconds=300, poller_port=queue)

        assert _event_state(conn, event_id) == "processed"

        rows = (
            client.table("task_queue").select("id").eq("idempotency_key", followup_key).execute()
        ).data
        assert rows, f"expected a follow-up task_queue row with idempotency_key={followup_key}"
    finally:
        if event_id is not None:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM events WHERE id = %s", (event_id,))
            conn.commit()
        conn.close()
        if blocking_task_id is not None:
            client.table("task_queue").delete().eq("id", blocking_task_id).execute()
        if followup_key is not None:
            client.table("task_queue").delete().eq("idempotency_key", followup_key).execute()


@_e2e
def test_poller_e2e_full_path_b_cycle():
    """#1455 AC7: the whole Path B loop against a live database.

    pending event → drain routes EMIT_TASK, enqueues a task, parks the event
    with ``blocked_by_task_id`` set → task reaches terminal → next tick's
    poller requeues the event → the same-tick drain replays it through the
    orchestrator, the enqueue collides on the unchanged idempotency key, and
    the event closes ``processed``. Exactly one task row exists throughout.
    """
    import psycopg

    from agents import orchestrator, wake_driver
    from agents.orchestrator import _idempotency_key, _target_of
    from agents.supabase_client import get_client
    from agents.task_queue import transition

    client = get_client()
    conn = psycopg.connect(_E2E_POSTGRES_URL)
    event_id: str | None = None
    task_key: str | None = None
    try:
        # Unique target → unique idempotency key per run, no cross-test bleed.
        payload = {"target": f"e2e-path-b-cycle-{uuid.uuid4()}"}
        task_key = _idempotency_key("ci_failure", _target_of(payload), payload)

        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO events (event_type, severity, repo, source, title, payload, state) "
                "VALUES (%s, %s, %s, %s, %s, %s::jsonb, 'pending') RETURNING id",
                (
                    "ci_failure",
                    "high",
                    "test/e2e",
                    "test_poller_e2e",
                    "E2E Path B full-cycle fixture",
                    json.dumps(payload),
                ),
            )
            event_id = str(cur.fetchone()[0])
        conn.commit()

        queue = wake_driver.PsycopgEventQueue(conn)
        prod_orchestrator = orchestrator.build_production_orchestrator(client=client)

        # Tick 1 — drain: EMIT_TASK enqueue + park blocked on the fresh task.
        wake_driver.tick(queue, prod_orchestrator, stale_after_seconds=300, poller_port=queue)

        state, blocked = _event_row(conn, event_id)
        assert state == "parked"
        assert blocked is not None, "producer must set blocked_by_task_id on park"
        rows = (
            client.table("task_queue").select("id").eq("idempotency_key", task_key).execute()
        ).data
        assert len(rows) == 1
        assert str(rows[0]["id"]) == blocked

        # Blocking task reaches a terminal state.
        transition(blocked, "claimed", client=client)
        transition(blocked, "running", client=client)
        transition(blocked, "done", client=client)

        # Tick 2 — poller requeues, same-tick drain replays, enqueue collides
        # on the unchanged payload key, event closes processed.
        wake_driver.tick(queue, prod_orchestrator, stale_after_seconds=300, poller_port=queue)

        state, blocked_after = _event_row(conn, event_id)
        assert state == "processed"
        # Lineage: the column is deliberately NOT cleared on requeue/close.
        assert blocked_after == blocked
        rows = (
            client.table("task_queue").select("id").eq("idempotency_key", task_key).execute()
        ).data
        assert len(rows) == 1, "collision closure must not create a second task row"
    finally:
        if event_id is not None:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM events WHERE id = %s", (event_id,))
            conn.commit()
        conn.close()
        if task_key is not None:
            client.table("task_queue").delete().eq("idempotency_key", task_key).execute()


@_e2e
def test_poller_e2e_leaves_event_parked_without_blocking_task_id():
    """AC5: parked event with no ``blocked_by_task_id`` stays parked after one tick."""
    import psycopg

    from agents import orchestrator, wake_driver
    from agents.supabase_client import get_client

    client = get_client()
    conn = psycopg.connect(_E2E_POSTGRES_URL)
    event_id: str | None = None
    try:
        event_id = _insert_parked_event(conn, blocked_by_task_id=None)

        queue = wake_driver.PsycopgEventQueue(conn)
        prod_orchestrator = orchestrator.build_production_orchestrator(client=client)

        wake_driver.tick(queue, prod_orchestrator, stale_after_seconds=300, poller_port=queue)

        assert _event_state(conn, event_id) == "parked"
    finally:
        if event_id is not None:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM events WHERE id = %s", (event_id,))
            conn.commit()
        conn.close()
