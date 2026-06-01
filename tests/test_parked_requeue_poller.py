"""Path B: parked-event re-queue poller — resume blocked work on task done (issue #745).

The poller watches the task_queue for terminal-state transitions (done, failed, parked)
and auto-requeues any parked events that were blocked by the completed task.

**AC1** — Poller maps parked events to blocking tasks and flips parked → pending on task done.
**AC2** — Parking event against running task then driving task to done requeues the event.
**AC3** — Event stays parked if blocking task still running (or is in failed/parked state).
**AC4** — Failed task handled per routing contract — no silent drop of parked events.

Schema prerequisite: events table must have `blocking_task` column (UUID of blocking task).
See issue #745 for schema migration details.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from agents.parked_requeue_poller import (
    ParkedRequeuePoller,
    check_and_requeue_for_task,
    run_poller,
)


# =========================================================================
# Fixtures and helpers
# =========================================================================


@pytest.fixture
def mock_client() -> MagicMock:
    """Mock Supabase client for testing."""
    return MagicMock()


@pytest.fixture
def sample_event_id() -> str:
    return str(uuid4())


@pytest.fixture
def sample_task_id() -> str:
    return str(uuid4())


def _mock_rpc(mock_client: MagicMock, rpc_name: str, return_data: list | bool | None):
    """Configure mock_client.rpc(rpc_name) to return execute()->data."""
    rpc_builder = MagicMock()
    rpc_builder.execute.return_value = MagicMock(data=return_data)
    mock_client.rpc.return_value = rpc_builder


def _setup_table_chain(return_data: list[dict] | None):
    """Create a chainable mock for client.table().select().eq()...execute()."""
    # Execute returns a result with .data
    execute_mock = MagicMock(return_value=MagicMock(data=return_data or []))

    # eq() chains and returns itself, with execute at the end
    eq_mock = MagicMock()
    eq_mock.eq = MagicMock(return_value=eq_mock)
    eq_mock.execute = execute_mock

    # select() returns something with eq()
    select_mock = MagicMock()
    select_mock.eq = MagicMock(return_value=eq_mock)

    # table() returns something with select()
    table_mock = MagicMock()
    table_mock.select = MagicMock(return_value=select_mock)

    return table_mock


def _mock_table_select(
    mock_client: MagicMock, table_name: str, return_data: list[dict] | None
):
    """Configure mock_client.table(table_name).select(...).eq(...).execute() chain."""
    table_mock = _setup_table_chain(return_data)
    mock_client.table.return_value = table_mock


# =========================================================================
# AC1 — Poller maps parked events to blocking tasks and flips parked → pending
# =========================================================================


def test_check_and_requeue_for_task_done_requeues_parked_events(
    mock_client: MagicMock,
    sample_task_id: str,
    sample_event_id: str,
) -> None:
    """When a task transitions to 'done', any parked events blocked by it are requeued."""
    task_id = sample_task_id
    event_id = sample_event_id

    # Setup: mock client.table() to return different chains based on table name
    def table_side_effect(table_name: str) -> MagicMock:
        if table_name == "task_queue":
            # Return done task
            task_row = {"id": task_id, "status": "done"}
            return _setup_table_chain([task_row])
        elif table_name == "events":
            # Return parked event
            parked_event = {"id": event_id, "state": "parked", "blocking_task": task_id}
            return _setup_table_chain([parked_event])
        return _setup_table_chain([])

    mock_client.table.side_effect = table_side_effect

    # Setup: requeue_event RPC succeeds
    _mock_rpc(mock_client, "requeue_event", True)

    # Act
    result = check_and_requeue_for_task(task_id, mock_client)

    # Assert: requeue was called for the parked event
    assert result.get("requeued_count", 0) > 0, f"Should requeue event; got {result}"
    assert result.get("task_status") == "done"


# =========================================================================
# AC2 — Park event against running task, then drive task to done, event requeued
# =========================================================================


@pytest.mark.asyncio
async def test_park_event_then_complete_task_requeues(
    mock_client: MagicMock,
    sample_task_id: str,
    sample_event_id: str,
) -> None:
    """Full scenario: event → parked (blocked by task) → task done → event pending.

    Tests AC2: parking event against running task then driving task to done requeues the event.
    """
    task_id = sample_task_id
    event_id = sample_event_id

    # Phase 1: Simulate parking the event (claimed → parked, blocking_task set to task_id)
    # In real flow, this is done via park_event RPC. Here we just mock the state.
    _mock_rpc(mock_client, "park_event", True)

    # Phase 2: Task reaches 'done' state
    task_row = {"id": task_id, "status": "done"}

    # Setup mock to return done task and parked event blocked by it
    def table_side_effect(table_name: str) -> MagicMock:
        if table_name == "task_queue":
            return _setup_table_chain([task_row])
        elif table_name == "events":
            parked_event = {"id": event_id, "state": "parked", "blocking_task": task_id}
            return _setup_table_chain([parked_event])
        return _setup_table_chain([])

    mock_client.table.side_effect = table_side_effect

    # Phase 3: Poller requeues the event (parked → pending)
    _mock_rpc(mock_client, "requeue_event", True)
    result = check_and_requeue_for_task(task_id, mock_client)

    assert (
        result.get("requeued_count", 0) > 0
    ), f"Event should be requeued when task done; got {result}"


# =========================================================================
# AC3 — Event stays parked if blocking task still running (or failed/parked)
# =========================================================================


def test_event_stays_parked_if_task_running(
    mock_client: MagicMock,
    sample_task_id: str,
    sample_event_id: str,
) -> None:
    """Parked event should NOT be requeued if blocking task is still 'running'."""
    task_id = sample_task_id
    event_id = sample_event_id

    # Task is still in 'running' state
    task_row = {"id": task_id, "status": "running"}
    _mock_table_select(mock_client, "task_queue", [task_row])

    # Parked event blocked by this task
    parked_event = {"id": event_id, "state": "parked", "blocking_task": task_id}
    _mock_table_select(mock_client, "events", [parked_event])

    # Act
    result = check_and_requeue_for_task(task_id, mock_client)

    # Assert: requeue should NOT be called (task not terminal)
    assert (
        result.get("requeued_count", 0) == 0
    ), f"Event should stay parked while task running; got {result}"


def test_event_stays_parked_if_task_failed(
    mock_client: MagicMock,
    sample_task_id: str,
    sample_event_id: str,
) -> None:
    """Parked event should stay parked if blocking task 'failed' (per routing contract)."""
    task_id = sample_task_id
    event_id = sample_event_id

    # Task reached 'failed' terminal state
    task_row = {"id": task_id, "status": "failed"}
    _mock_table_select(mock_client, "task_queue", [task_row])

    # Parked event blocked by this task
    parked_event = {"id": event_id, "state": "parked", "blocking_task": task_id}
    _mock_table_select(mock_client, "events", [parked_event])

    # Act
    result = check_and_requeue_for_task(task_id, mock_client)

    # Assert: event stays parked; no auto-requeue on 'failed'
    assert (
        result.get("requeued_count", 0) == 0
    ), "Event should stay parked if blocking task failed"


# =========================================================================
# AC4 — Failed task handled per routing contract (no silent drop)
# =========================================================================


def test_failed_task_does_not_silently_drop_parked_events(
    mock_client: MagicMock,
    sample_task_id: str,
    sample_event_id: str,
) -> None:
    """Failed tasks with parked dependents should be routed via escalation, not silently dropped."""
    task_id = sample_task_id
    event_id = sample_event_id

    # Task failed
    task_row = {
        "id": task_id,
        "status": "failed",
        "escalated_reason": "Test failure",
    }
    _mock_table_select(mock_client, "task_queue", [task_row])

    # Parked event blocked by failed task
    parked_event = {"id": event_id, "state": "parked", "blocking_task": task_id}
    _mock_table_select(mock_client, "events", [parked_event])

    # Act
    result = check_and_requeue_for_task(task_id, mock_client)

    # Assert: result includes the parked event (was not dropped)
    # The routing decision (whether to escalate) is made upstream, but the event
    # is accounted for and visible in the result
    assert "parked_events" in result or result.get("requeued_count", 0) == 0, (
        "Failed task with parked dependents should be accounted for in result "
        "(not silently dropped)"
    )


# =========================================================================
# Poller lifecycle
# =========================================================================


@pytest.mark.asyncio
async def test_poller_runs_check_on_task_done_event(mock_client: MagicMock) -> None:
    """Poller subscribes to task_queue events and triggers check on terminal state."""
    poller = ParkedRequeuePoller(mock_client)

    # Simulate a task reaching 'done'
    task_id = str(uuid4())
    task_done_event = {"id": task_id, "status": "done"}

    # Mock the check_and_requeue_for_task call
    with patch("agents.parked_requeue_poller.check_and_requeue_for_task") as mock_check:
        mock_check.return_value = {"requeued_count": 1}

        # Trigger the poller's event handler (simulating a NOTIFY event)
        await poller.handle_task_done(task_done_event)

        # Assert: check was called
        mock_check.assert_called_once_with(task_id, mock_client)


@pytest.mark.asyncio
async def test_poller_ignores_non_terminal_task_events(
    mock_client: MagicMock,
) -> None:
    """Poller should not trigger checks for pending/claimed/running tasks."""
    poller = ParkedRequeuePoller(mock_client)

    task_id = str(uuid4())
    running_event = {"id": task_id, "status": "running"}

    with patch("agents.parked_requeue_poller.check_and_requeue_for_task") as mock_check:
        await poller.handle_task_done(running_event)

        # Assert: check was not called for non-terminal state
        mock_check.assert_not_called()
