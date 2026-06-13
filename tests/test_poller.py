"""Tests for the parked-event re-queue poller (#745 — Path B).

The poller re-queues ``parked`` events when their blocking task reaches a
terminal state (``done`` or ``failed``). It is a pure function over a
:class:`PollerPort` interface — every test uses an in-memory fake so no
live database is required.
"""

from __future__ import annotations

from typing import Any

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
        """Return parked events whose payload has a ``blocked_by_task_id`` key."""
        result: list[dict[str, Any]] = []
        for ev in self.events:
            if ev.get("state") != "parked":
                continue
            payload = ev.get("payload") or {}
            if isinstance(payload, dict) and payload.get("blocked_by_task_id"):
                result.append(ev)
        return result

    def get_task_status(self, task_id: str) -> str | None:
        for t in self.tasks:
            if t.get("id") == task_id:
                return t.get("status")
        return None

    def requeue_event(self, event_id: str, *, reason: str) -> bool:
        for ev in self.events:
            if ev["id"] == event_id:
                ev["state"] = "pending"
                self.requeue_calls.append((event_id, reason))
                return True
        return False

    # -- test helpers --------------------------------------------------------

    def state_of(self, event_id: str) -> str:
        return next(ev["state"] for ev in self.events if ev["id"] == event_id)

    def task_status(self, task_id: str) -> str | None:
        return self.get_task_status(task_id)


def _ev(
    eid: str,
    task_id: str | None = None,
    state: str = "parked",
) -> dict[str, Any]:
    """Build an event dict. ``task_id`` is stored in ``payload.blocked_by_task_id``."""
    ev: dict[str, Any] = {"id": eid, "state": state}
    if task_id is not None:
        ev["payload"] = {"blocked_by_task_id": task_id}
    else:
        ev["payload"] = {}
    return ev


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

    def test_does_not_requeue_when_task_still_parked(self):
        port = FakePollerPort(
            events=[_ev("e1", task_id="t1")],
            tasks=[_task("t1", "parked")],
        )
        n = poller.poll(port)
        assert n == 0
        assert port.state_of("e1") == "parked"


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
        """Only done/failed tasks cause requeue; running/parked stay."""
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
        assert n == 2  # done + failed
        assert port.state_of("e-done") == "pending"
        assert port.state_of("e-failed") == "pending"
        assert port.state_of("e-running") == "parked"
        assert port.state_of("e-parked") == "parked"


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
