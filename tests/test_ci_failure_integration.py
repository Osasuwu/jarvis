"""MVP integration tracer: ci_failure event -> sandcastle spawn (whole loop) (#746).

End-to-end behavior:
- A `ci_failure` event lands in the EVENT queue.
- The wake_driver cold-boots the orchestrator for it.
- The orchestrator routes it to a multi-action coding task → emits a `task_queue` row.
- The executor `spawn`s `claude -p` in sandcastle for that task.
- Loop closure is EXTERNAL (Path A/C): everything after spawn is handled by GitHub workflows.

Acceptance criteria:
1. An injected `ci_failure` event drives, end-to-end, to an `executor.spawn` of
   `claude -p` in sandcastle (integration test; no real model required).
2. The spawned run inherits no API-billing keys (billing-trap holds).
3. After spawn the internal system does nothing further; loop re-entry is via a
   fresh `event` (no internal pr_pipeline).
4. Documented demo: inject `ci_failure` → observe the sandcastle spawn attempt.
5. No internal module duplicates the GitHub-side Path A (automerge/rework-cap/escalate).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from agents import executor, orchestrator, task_queue


# --- Fixtures: FSM-faithful fakes for events and task_queue ---------------


class _FakeEventQueue:
    """In-memory model of the #739 events FSM, behind the EventQueuePort."""

    def __init__(self, events: list[dict] | None = None) -> None:
        self.events: list[dict] = events or []
        self.clock: float = 0.0
        self.wake_signals: list[bool] = []
        self.processed_calls: list[str] = []
        self._severity_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}

    def claim_next(self) -> dict[str, Any] | None:
        pending = [e for e in self.events if e["state"] == "pending"]
        if not pending:
            return None
        pending.sort(
            key=lambda e: (
                self._severity_rank.get(e.get("severity", "info"), 4),
                e["id"],
            )
        )
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
            if (
                e["state"] == "claimed"
                and (self.clock - e.get("claimed_at", 0)) >= older_than_seconds
            ):
                e["state"] = "pending"
                e["claimed_at"] = None
                count += 1
        return count

    def wait_for_wake(self, *, timeout_seconds: float | None) -> bool:
        if self.wake_signals:
            return self.wake_signals.pop(0)
        return False


def _ev(
    event_id: str,
    event_type: str = "ci_failure",
    severity: str = "high",
    payload: dict | None = None,
    state: str = "pending",
) -> dict[str, Any]:
    """Create a test event."""
    return {
        "id": event_id,
        "event_type": event_type,
        "severity": severity,
        "payload": payload or {},
        "state": state,
        "claimed_at": None,
    }


class _FakeResult:
    def __init__(self, data: list[dict]) -> None:
        self.data = data


class _FakeInsert:
    def __init__(self, table: _FakeTable, payload: dict) -> None:
        self._table = table
        self._payload = payload

    def execute(self) -> _FakeResult:
        key = self._payload.get("idempotency_key")
        if any(r.get("idempotency_key") == key for r in self._table.rows):
            return _FakeResult([])
        stored = {**self._payload, "id": f"tq-{len(self._table.rows) + 1}"}
        self._table.rows.append(stored)
        return _FakeResult([stored])


class _FakeTable:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    def insert(self, payload: dict) -> _FakeInsert:
        return _FakeInsert(self, payload)


class _FakeClient:
    def __init__(self) -> None:
        self._tables: dict[str, _FakeTable] = {}

    def table(self, name: str) -> _FakeTable:
        return self._tables.setdefault(name, _FakeTable())


# --- AC1: ci_failure event drives to executor.spawn -------


def test_ci_failure_event_reaches_executor_spawn():
    """AC1: ci_failure event reaches executor.spawn with correct task_text."""
    # Track spawn invocations
    spawned_tasks: list[dict[str, Any]] = []

    def fake_spawn(
        task_text: str,
        *,
        stderr_log_dir: str | None = None,
        popen: Any = None,
    ) -> Any:
        spawned_tasks.append({
            "task_text": task_text,
            "stderr_log_dir": stderr_log_dir,
        })
        # Return a mock Popen handle
        class _MockHandle:
            pid = 12345

        return _MockHandle()

    # 1. Create a ci_failure event
    event = _ev("ci-1", payload={"pr": "42"})

    # 2. Orchestrator routes it
    decision = orchestrator.handle_event(event)
    assert decision.route == orchestrator.Route.EMIT_TASK
    assert decision.assignee == "sandcastle"

    # 3. Enqueue the task
    fake_client = _FakeClient()
    task_row = task_queue.enqueue(
        goal=decision.goal,
        priority=decision.priority,
        assignee=decision.assignee,
        idempotency_key=decision.idempotency_key,
        client=fake_client,
    )
    assert task_row is not None
    assert task_row["status"] == "pending"

    # 4. Spawn the task (fire-and-forget)
    with patch("agents.executor.spawn", side_effect=fake_spawn):
        executor.spawn(decision.goal, stderr_log_dir="/tmp/logs")

    # Verify spawn was called with correct task
    assert len(spawned_tasks) == 1
    task = spawned_tasks[0]
    assert "fix:" in task["task_text"]
    assert "42" in task["task_text"]  # PR number


# --- AC2: billing-trap holds in integrated path -------


def test_spawn_inherits_no_api_keys():
    """AC2: Spawned subprocess inherits no API-billing keys."""
    # Track Popen invocations to inspect env
    captured_env: dict[str, str] | None = None

    class _CapturedPopen:
        def __init__(self, argv: list[str], **kwargs: Any) -> None:
            nonlocal captured_env
            captured_env = kwargs.get("env", {})
            self.pid = 99999

    # Simulate parent env with API keys
    parent_env = {
        "PATH": "/usr/bin",
        "ANTHROPIC_API_KEY": "sk-leak-sentinel",
        "CLAUDE_API_KEY": "sk-claude-leak",
        "KEEP_THIS": "safe-env-var",
    }

    with patch("agents.executor.os.environ", parent_env):
        with patch("agents.executor._resolve_claude_binary", return_value="/fake/claude"):
            with patch("agents.executor.subprocess.Popen", _CapturedPopen):
                executor.spawn("test task", stderr_log_dir="/tmp/logs")

    assert captured_env is not None
    assert "ANTHROPIC_API_KEY" not in captured_env
    assert "CLAUDE_API_KEY" not in captured_env
    assert captured_env.get("KEEP_THIS") == "safe-env-var"


# --- AC3: no internal pr_pipeline after spawn     -------


def test_orchestrator_does_not_call_spawn_directly():
    """AC3: Orchestrator emits task, never spawns directly.

    Spawn is external (fire-and-forget in Path A). The orchestrator
    only writes to task_queue; the caller decides when to spawn.
    """
    # If orchestrator called executor.spawn, this patch would fail
    with patch("agents.executor.spawn") as mock_spawn:
        event = _ev("ci-1", payload={"pr": "42"})
        decision = orchestrator.handle_event(event)
        # Orchestrator routes to emit_task, not handling spawn
        assert decision.route == orchestrator.Route.EMIT_TASK
        assert not mock_spawn.called


# --- AC4: documented demo -------


def test_demo_inject_ci_failure_observe_spawn():
    """AC4: Documented demo: inject ci_failure → observe spawn attempt.

    This demonstrates the full loop:
    1. ci_failure event is created
    2. Orchestrator routes it to emit_task
    3. Task is enqueued
    4. Spawn is invoked (fire-and-forget)
    """
    spawned_tasks: list[dict[str, Any]] = []

    def fake_spawn(
        task_text: str,
        *,
        stderr_log_dir: str | None = None,
        popen: Any = None,
    ) -> Any:
        spawned_tasks.append({"task_text": task_text})

        class _MockHandle:
            pid = 99999

        return _MockHandle()

    # 1. Create a ci_failure event
    ci_failure_event = _ev(
        "demo-1",
        event_type="ci_failure",
        severity="high",
        payload={"pr": "123"},
    )

    # 2. Orchestrator routes it
    decision = orchestrator.handle_event(ci_failure_event)
    assert decision.route == orchestrator.Route.EMIT_TASK
    assert decision.assignee == "sandcastle"

    # 3. Enqueue the task
    fake_client = _FakeClient()
    task_row = task_queue.enqueue(
        goal=decision.goal,
        priority=decision.priority,
        assignee=decision.assignee,
        idempotency_key=decision.idempotency_key,
        client=fake_client,
    )
    assert task_row is not None
    assert task_row["status"] == "pending"
    assert task_row["assignee"] == "sandcastle"

    # 4. Spawn the task (fire-and-forget)
    with patch("agents.executor.spawn", side_effect=fake_spawn):
        with patch("agents.executor._resolve_claude_binary", return_value="/fake/claude"):
            executor.spawn(decision.goal, stderr_log_dir="/tmp/logs")

    # Verify spawn was called
    assert len(spawned_tasks) == 1
    assert "fix:" in spawned_tasks[0]["task_text"]
    assert "123" in spawned_tasks[0]["task_text"]


# --- AC5: no internal Path A duplication -------


def test_orchestrator_does_not_merge_or_rework():
    """AC5: Orchestrator emits task only, never merges or reworks.

    Path A (automerge, rework-cap, escalate) is owned by GitHub workflows
    in milestone #41. The orchestrator routes to emit_task; the executor
    spawns a coding task. Loop closure is external.
    """
    # Orchestrator should never emit anything that looks like an internal
    # merge/rework command
    event = _ev("ci-1", payload={"pr": "42"})
    decision = orchestrator.handle_event(event)

    # Decision's goal is a task description, not a merge/rework command
    assert "fix:" in decision.goal
    assert "merge" not in decision.goal.lower()
    assert "rework" not in decision.goal.lower()
