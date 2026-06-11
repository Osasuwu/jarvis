"""Tests for the wake_driver loop (#743).

The wake_driver is the crash-safe, event-driven loop that replaces the
retired APScheduler resident scheduler. It owns no decisions — only the
wake mechanics: LISTEN for a NOTIFY wake signal, cold-boot the (injected)
orchestrator for the next single ``pending`` event, drain one at a time,
and let a watchdog re-claim rows stranded in ``claimed`` by a dead tick.

These tests exercise the loop's *external behavior* through the
``EventQueuePort`` interface with an FSM-faithful fake — the same approach
the issue's Testing Decisions call for ("fixed event inputs, no live
model"). The psycopg-backed adapter is an integration seam and is not
unit-tested here (no live DB).
"""

from __future__ import annotations

import inspect
import tomllib
from pathlib import Path

import pytest

from agents import wake_driver

_REPO_ROOT = Path(__file__).resolve().parent.parent

# --- FSM-faithful fake -----------------------------------------------------

_SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


class FakeEventQueue:
    """In-memory model of the #739 events FSM, behind the EventQueuePort.

    Mirrors the Postgres RPCs: ``claim_next`` (highest-severity pending,
    pending→claimed), ``mark_processed`` (claimed→processed),
    ``reclaim_stale`` (claimed→pending for rows older than a threshold).
    A monotonically-advanceable ``clock`` stands in for ``now()`` so the
    watchdog threshold can be tested deterministically.
    """

    def __init__(self, events: list[dict] | None = None) -> None:
        self.events: list[dict] = events or []
        self.clock: float = 0.0
        # Scripted wake signals consumed by wait_for_wake (True=NOTIFY).
        self.wake_signals: list[bool] = []
        self.processed_calls: list[str] = []

    # -- EventQueuePort surface --------------------------------------------

    def claim_next(self) -> dict | None:
        pending = [e for e in self.events if e["state"] == "pending"]
        if not pending:
            return None
        pending.sort(key=lambda e: (_SEVERITY_RANK.get(e.get("severity", "info"), 4), e["id"]))
        row = pending[0]
        row["state"] = "claimed"
        row["claimed_at"] = self.clock
        return dict(row)

    def mark_processed(self, event_id: str, *, action: str = "") -> bool:
        for e in self.events:
            if e["id"] == event_id and e["state"] == "claimed":
                e["state"] = "processed"
                self.processed_calls.append(event_id)
                return True
        return False

    def reclaim_stale(self, *, older_than_seconds: float) -> int:
        count = 0
        for e in self.events:
            if e["state"] == "claimed" and (self.clock - e["claimed_at"]) >= older_than_seconds:
                e["state"] = "pending"
                e["claimed_at"] = None
                count += 1
        return count

    def wait_for_wake(self, *, timeout_seconds: float | None) -> bool:
        if self.wake_signals:
            return self.wake_signals.pop(0)
        return False

    # -- test helpers ------------------------------------------------------

    def state_of(self, event_id: str) -> str:
        return next(e["state"] for e in self.events if e["id"] == event_id)


def _ev(eid: str, severity: str = "info", state: str = "pending") -> dict:
    return {"id": eid, "severity": severity, "state": state, "claimed_at": None}


# --- AC1 / AC2: drain one at a time, advance immediately -------------------


def test_drain_pending_processes_every_pending_event_once():
    q = FakeEventQueue([_ev("a"), _ev("b"), _ev("c")])

    processed = wake_driver.drain_pending(q, wake_driver.default_orchestrator)

    assert processed == 3
    assert q.processed_calls == ["a", "b", "c"]
    assert all(e["state"] == "processed" for e in q.events)


def test_drain_pending_claims_highest_severity_first():
    q = FakeEventQueue([_ev("lo", "low"), _ev("crit", "critical"), _ev("med", "medium")])

    wake_driver.drain_pending(q, wake_driver.default_orchestrator)

    # Severity order, not insertion order — proves claim_next ordering is honored.
    assert q.processed_calls == ["crit", "med", "lo"]


def test_drain_pending_empty_queue_is_a_noop():
    q = FakeEventQueue([])
    assert wake_driver.drain_pending(q, wake_driver.default_orchestrator) == 0


def test_drain_advances_to_next_without_a_fixed_interval():
    # AC2: one drain call empties the queue in a single pass — no per-event
    # sleep / interval. We assert the orchestrator saw every event in order
    # within one synchronous drain (a fixed-interval poller could not).
    seen: list[str] = []
    q = FakeEventQueue([_ev("e1"), _ev("e2"), _ev("e3")])

    wake_driver.drain_pending(q, lambda event: seen.append(event["id"]))

    assert seen == ["e1", "e2", "e3"]


# --- AC1: a wake signal cold-boots a tick ----------------------------------


def test_run_drains_on_a_wake_signal_then_stops():
    q = FakeEventQueue([_ev("x"), _ev("y")])
    q.wake_signals = [True]  # one NOTIFY, then should_continue stops the loop.
    ticks = {"n": 0}

    def should_continue() -> bool:
        ticks["n"] += 1
        return ticks["n"] <= 1

    wake_driver.run(q, wake_driver.default_orchestrator, should_continue=should_continue)

    assert q.processed_calls == ["x", "y"]


def test_run_runs_watchdog_each_tick_even_without_a_notify():
    # A timeout (no NOTIFY) still triggers a tick so the watchdog runs.
    q = FakeEventQueue([_ev("stuck", state="claimed")])
    q.events[0]["claimed_at"] = 0.0
    q.clock = 999.0  # well past the threshold
    q.wake_signals = [False]  # timeout, not a NOTIFY
    ticks = {"n": 0}

    def should_continue() -> bool:
        ticks["n"] += 1
        return ticks["n"] <= 1

    wake_driver.run(
        q,
        wake_driver.default_orchestrator,
        stale_after_seconds=300,
        should_continue=should_continue,
    )

    # Stale claimed row was reclaimed → re-drained → processed in the same tick.
    assert q.state_of("stuck") == "processed"


# --- AC3: crash-safety — killed mid-tick → reprocessed, never lost ---------


def test_event_left_claimed_when_orchestrator_dies_midtick():
    q = FakeEventQueue([_ev("boom")])

    def crashing(event: dict) -> None:
        raise RuntimeError("simulated kill mid-tick")

    with pytest.raises(RuntimeError):
        wake_driver.drain_pending(q, crashing)

    # mark_processed never ran: the row is stranded in 'claimed', not lost,
    # and crucially not 'processed'.
    assert q.state_of("boom") == "claimed"
    assert q.processed_calls == []


def test_stranded_event_is_reprocessed_after_watchdog_reclaim():
    q = FakeEventQueue([_ev("boom")])

    def crashing(event: dict) -> None:
        raise RuntimeError("simulated kill mid-tick")

    with pytest.raises(RuntimeError):
        wake_driver.drain_pending(q, crashing)
    assert q.state_of("boom") == "claimed"

    # Watchdog runs after the threshold elapses; the row returns to pending.
    q.clock = 400.0
    reclaimed = wake_driver.run_watchdog(q, stale_after_seconds=300)
    assert reclaimed == 1
    assert q.state_of("boom") == "pending"

    # A healthy re-drain now processes it — at-least-once delivery.
    processed = wake_driver.drain_pending(q, wake_driver.default_orchestrator)
    assert processed == 1
    assert q.state_of("boom") == "processed"


# --- AC4: watchdog re-claims a stale claimed row ---------------------------


def test_watchdog_reclaims_only_rows_past_the_threshold():
    fresh = _ev("fresh", state="claimed")
    stale = _ev("stale", state="claimed")
    q = FakeEventQueue([fresh, stale])
    q.events[0]["claimed_at"] = 350.0  # fresh: claimed recently
    q.events[1]["claimed_at"] = 0.0  # stale: claimed long ago
    q.clock = 400.0

    reclaimed = wake_driver.run_watchdog(q, stale_after_seconds=300)

    assert reclaimed == 1
    assert q.state_of("stale") == "pending"
    assert q.state_of("fresh") == "claimed"


def test_watchdog_noop_when_nothing_is_stale():
    q = FakeEventQueue([_ev("c", state="claimed")])
    q.events[0]["claimed_at"] = 100.0
    q.clock = 200.0
    assert wake_driver.run_watchdog(q, stale_after_seconds=300) == 0


def test_tick_reclaims_then_drains():
    q = FakeEventQueue([_ev("stale", state="claimed"), _ev("new")])
    q.events[0]["claimed_at"] = 0.0
    q.clock = 400.0

    result = wake_driver.tick(q, wake_driver.default_orchestrator, stale_after_seconds=300)

    assert result.reclaimed == 1
    assert result.processed == 2  # the reclaimed row + the new pending row
    assert all(e["state"] == "processed" for e in q.events)


# --- AC6: no resident-process / `while True: sleep` loop -------------------


def test_wake_driver_has_no_busy_sleep_poll_loop():
    src = inspect.getsource(wake_driver)
    # The retired scheduler used `while True:` + `time.sleep(...)` as a
    # resident interval poller. wake_driver must be event-driven instead.
    assert "while True" not in src, "wake_driver must not contain a `while True` resident loop"
    assert "time.sleep(" not in src, (
        "wake_driver must not busy-sleep; it blocks on the NOTIFY socket"
    )


# --- AC5: scheduler.py + apscheduler dep + installer retired ---------------


def test_scheduler_module_is_retired():
    assert not (_REPO_ROOT / "agents" / "scheduler.py").exists(), (
        "agents/scheduler.py must be deleted — wake_driver replaces the APScheduler scheduler"
    )


def test_scheduler_service_installer_is_retired():
    assert not (_REPO_ROOT / "scripts" / "install" / "install-scheduler-service.ps1").exists(), (
        "install-scheduler-service.ps1 must be deleted — the resident scheduler service is retired"
    )


def test_apscheduler_and_sqlalchemy_dropped_from_deps():
    pyproject = tomllib.loads((_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    agents_deps = pyproject["project"]["optional-dependencies"]["agents"]
    joined = " ".join(agents_deps).lower()
    assert "apscheduler" not in joined, "apscheduler dep must be dropped with scheduler.py"
    assert "sqlalchemy" not in joined, (
        "sqlalchemy was only APScheduler's jobstore driver — drop it too"
    )


# --- #909 AC1: tick gains task reclaim + task drain, four ordered steps -----


class _RecordingTaskQueue:
    """Minimal TaskQueuePort that logs the calls drain/reclaim make, in order.

    Shares the order log with a _LoggingEventQueue so a single tick's
    event-side and task-side operations can be asserted against AC1's
    ``reclaim(events) → reclaim_tasks() → drain(events) → drain_tasks()`` order.
    """

    def __init__(self, log: list, *, pending=None, stale_claimed: int = 0, stale_running=None):
        self._log = log
        self._pending = list(pending or [])
        self._stale_claimed = stale_claimed
        self._stale_running = list(stale_running or [])

    def claim_next(self, *, assignee: str):
        for i, r in enumerate(self._pending):
            if r.get("assignee", "sandcastle") == assignee:
                self._log.append("task_drain")
                return self._pending.pop(i)
        return None

    def count_running(self, *, assignee: str) -> int:
        return 0

    def transition(self, task_id: str, to_status: str, *, reason=None):
        self._log.append(f"task_transition:{to_status}")
        return {"id": task_id, "status": to_status}

    def reclaim_stale_claimed(self, *, assignee: str, older_than_seconds: float) -> int:
        self._log.append("task_reclaim")
        return self._stale_claimed

    def list_stale_running(self, *, assignee: str, older_than_seconds: float):
        self._log.append("task_list_running")
        return list(self._stale_running)


class _LoggingEventQueue(FakeEventQueue):
    """FakeEventQueue that records reclaim/drain into a shared order log."""

    def __init__(self, log: list, events=None):
        super().__init__(events)
        self._log = log

    def reclaim_stale(self, *, older_than_seconds: float) -> int:
        self._log.append("event_reclaim")
        return super().reclaim_stale(older_than_seconds=older_than_seconds)

    def claim_next(self):
        row = super().claim_next()
        if row is not None:
            self._log.append("event_drain")
        return row


def test_tick_runs_the_four_steps_in_order():
    log: list = []
    eq = _LoggingEventQueue(log, [_ev("e1", state="claimed")])
    eq.events[0]["claimed_at"] = 0.0
    eq.clock = 999.0  # the claimed event is stale → reclaimed → drained this tick
    tq = _RecordingTaskQueue(log, pending=[{"id": "t1", "goal": "g", "assignee": "sandcastle"}])

    wake_driver.tick(
        eq,
        wake_driver.default_orchestrator,
        stale_after_seconds=300,
        task_port=tq,
        task_spawn=lambda goal: None,
        task_resolve_binary=lambda: "claude",
    )

    # AC1 order: reclaim(events) → reclaim_tasks() → drain(events) → drain_tasks()
    assert log.index("event_reclaim") < log.index("task_reclaim")
    # Within the task watchdog, claimed-reclaim precedes the running-reaper scan.
    assert log.index("task_reclaim") < log.index("task_list_running")
    assert log.index("task_list_running") < log.index("event_drain")
    assert log.index("event_drain") < log.index("task_drain")


def test_tick_without_task_port_is_event_only():
    # Backward-compat: omitting task_port skips both task steps entirely.
    q = FakeEventQueue([_ev("a")])
    result = wake_driver.tick(q, wake_driver.default_orchestrator, stale_after_seconds=300)
    assert result.processed == 1
    assert result.tasks_spawned == 0
    assert result.tasks_reclaimed == 0
    assert result.tasks_reaped == 0
    assert result.tasks_failed == 0


def test_tick_reports_task_counts():
    log: list = []
    eq = FakeEventQueue([])
    tq = _RecordingTaskQueue(
        log,
        pending=[{"id": "t1", "goal": "g", "assignee": "sandcastle"}],
        stale_claimed=2,
        stale_running=[{"id": "r1"}],
    )
    result = wake_driver.tick(
        eq,
        wake_driver.default_orchestrator,
        stale_after_seconds=300,
        task_port=tq,
        task_spawn=lambda goal: None,
        task_resolve_binary=lambda: "claude",
    )
    assert result.tasks_reclaimed == 2  # AC5 stale claimed → pending
    assert result.tasks_reaped == 1  # AC6 stale running → failed
    assert result.tasks_spawned == 1  # AC2/AC3/AC4 the pending sandcastle row


# --- review #1: the task side and event side are isolated within a tick -----


class _RaisingOnReclaimTaskQueue:
    """TaskQueuePort whose task watchdog raises — models a Supabase outage in
    tick Step 2 (the task reclaim), which must not starve the event drain."""

    def claim_next(self, *, assignee: str):
        return None

    def count_running(self, *, assignee: str) -> int:
        return 0

    def transition(self, task_id: str, to_status: str, *, reason=None):
        return {"id": task_id, "status": to_status}

    def reclaim_stale_claimed(self, *, assignee: str, older_than_seconds: float) -> int:
        raise RuntimeError("supabase unreachable")

    def list_stale_running(self, *, assignee: str, older_than_seconds: float):
        return []


class _RaisingOnDrainTaskQueue:
    """TaskQueuePort whose drain raises — models a task-store outage in tick
    Step 4 (after events already drained in Step 3)."""

    def claim_next(self, *, assignee: str):
        raise RuntimeError("supabase unreachable")

    def count_running(self, *, assignee: str) -> int:
        return 0

    def transition(self, task_id: str, to_status: str, *, reason=None):
        return {"id": task_id, "status": to_status}

    def reclaim_stale_claimed(self, *, assignee: str, older_than_seconds: float) -> int:
        return 0

    def list_stale_running(self, *, assignee: str, older_than_seconds: float):
        return []


def test_tick_task_watchdog_failure_does_not_block_event_drain():
    # A Supabase outage in the task watchdog (Step 2) must not starve the
    # psycopg-backed event path (Step 3). Events still drain; task counts are
    # zero; the tick returns instead of raising.
    q = FakeEventQueue([_ev("a"), _ev("b")])
    result = wake_driver.tick(
        q,
        wake_driver.default_orchestrator,
        stale_after_seconds=300,
        task_port=_RaisingOnReclaimTaskQueue(),
        task_resolve_binary=lambda: "claude",
    )
    assert result.processed == 2  # events drained despite the task-side outage
    assert result.tasks_reclaimed == 0
    assert result.tasks_reaped == 0


def test_tick_task_drain_failure_does_not_crash_tick():
    # A failure in the task drain (Step 4) is contained — the event drain
    # (Step 3) already ran, and the tick returns a result instead of raising.
    q = FakeEventQueue([_ev("a")])
    result = wake_driver.tick(
        q,
        wake_driver.default_orchestrator,
        stale_after_seconds=300,
        task_port=_RaisingOnDrainTaskQueue(),
        task_resolve_binary=lambda: "claude",
    )
    assert result.processed == 1
    assert result.tasks_spawned == 0
    assert result.tasks_failed == 0


# --- review #3: run() forwards every task param to tick() -------------------


def test_run_forwards_task_spawn_and_resolver_to_tick():
    # run() must forward task_spawn / task_resolve_binary, else the loop
    # silently falls back to the production defaults (real claude binary, real
    # spawn) no matter what main() injected. Drive one iteration and assert the
    # injected fakes were the ones used.
    log: list = []
    q = FakeEventQueue([])
    q.wake_signals = [True]
    tq = _RecordingTaskQueue(
        log, pending=[{"id": "t1", "goal": "do-the-thing", "assignee": "sandcastle"}]
    )
    spawned: list[str] = []
    resolved = {"n": 0}
    ticks = {"n": 0}

    def should_continue() -> bool:
        ticks["n"] += 1
        return ticks["n"] <= 1

    def fake_resolve() -> str:
        resolved["n"] += 1
        return "claude"

    wake_driver.run(
        q,
        wake_driver.default_orchestrator,
        should_continue=should_continue,
        task_port=tq,
        task_spawn=lambda goal: spawned.append(goal),
        task_resolve_binary=fake_resolve,
    )

    assert spawned == ["do-the-thing"]  # injected spawn forwarded, not the default
    assert resolved["n"] == 1  # injected resolver forwarded, not the default


def test_run_forwards_task_thresholds_to_tick():
    # The claimed/running staleness thresholds must reach reclaim_stale_tasks;
    # a partial forward would silently apply the module defaults instead.
    seen: dict = {}

    class _ThresholdPort:
        def claim_next(self, *, assignee: str):
            return None

        def count_running(self, *, assignee: str) -> int:
            return 0

        def transition(self, task_id: str, to_status: str, *, reason=None):
            return {"id": task_id}

        def reclaim_stale_claimed(self, *, assignee: str, older_than_seconds: float) -> int:
            seen["claimed"] = older_than_seconds
            return 0

        def list_stale_running(self, *, assignee: str, older_than_seconds: float):
            seen["running"] = older_than_seconds
            return []

    q = FakeEventQueue([])
    q.wake_signals = [False]
    ticks = {"n": 0}

    def should_continue() -> bool:
        ticks["n"] += 1
        return ticks["n"] <= 1

    wake_driver.run(
        q,
        wake_driver.default_orchestrator,
        should_continue=should_continue,
        task_port=_ThresholdPort(),
        task_resolve_binary=lambda: "claude",
        task_claimed_stale_after_seconds=111,
        task_running_reap_after_seconds=222,
    )

    assert seen == {"claimed": 111, "running": 222}
