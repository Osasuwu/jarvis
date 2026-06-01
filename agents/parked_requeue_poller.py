"""Path B: parked-event re-queue poller — resume blocked work on task done (issue #745).

The poller watches the task_queue for terminal-state transitions (done) and
auto-requeues any parked events that were blocked by the completed task.

**Design:**
- When a task reaches 'done' state, check for any events in the 'parked' state
  with blocking_task = task_id.
- Requeue each such event back to 'pending' via the requeue_event RPC.
- Failed/parked tasks: events stay parked (routing decision handled upstream per
  contract #744).

**Integration:**
- Called from wake_driver.handle_event() when a task_done event is observed.
- Can also run as a background task that polls task_queue for terminal transitions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from supabase import Client

# Lazy import to avoid circular dependency
def _get_client() -> Client:
    from agents.supabase_client import get_client
    return get_client()


# =========================================================================
# Main logic: check and requeue
# =========================================================================


def check_and_requeue_for_task(
    task_id: str,
    client: Client | None = None,
) -> dict[str, Any]:
    """Check if a completed task has any parked dependent events and requeue them.

    **Precondition:** The task must already be in a terminal state (done, failed, parked).

    **Behavior:**
    - Only requeues if task status is 'done'. Other terminal states (failed, parked)
      are not auto-requeued per routing contract.
    - Returns a dict with:
      - `requeued_count`: number of events successfully requeued
      - `parked_events`: list of parked event IDs (for accounting, even if not requeued)
      - `task_status`: the task's current status

    **Side effect:** Calls requeue_event RPC for each eligible parked event.
    """
    cli = client or _get_client()

    # 1. Fetch the task to confirm its status
    task_rows = (
        cli.table("task_queue")
        .select("id,status")
        .eq("id", task_id)
        .execute()
    ).data or []

    # Limit to 1 in case there are duplicates (should not happen, but defensive)
    if task_rows:
        task_rows = task_rows[:1]

    if not task_rows:
        return {
            "requeued_count": 0,
            "parked_events": [],
            "task_status": None,
            "error": f"Task {task_id} not found",
        }

    task = task_rows[0]
    task_status = task.get("status")

    # 2. Query for parked events blocked by this task
    parked_events_rows = (
        cli.table("events")
        .select("id,state,blocking_task")
        .eq("blocking_task", task_id)
        .eq("state", "parked")
        .execute()
    ).data or []

    parked_event_ids = [e["id"] for e in parked_events_rows]

    # 3. Only requeue if task is 'done'. Other terminal states (failed, parked)
    #    are handled by the routing contract (#744), not auto-requeued.
    if task_status != "done":
        return {
            "requeued_count": 0,
            "parked_events": parked_event_ids,
            "task_status": task_status,
            "reason": f"Task status is '{task_status}' (not 'done'); events stay parked",
        }

    # 4. Requeue each parked event back to pending
    requeued_count = 0
    for event_id in parked_event_ids:
        try:
            result = cli.rpc(
                "requeue_event",
                {
                    "event_id": event_id,
                    "reason": f"blocking task {task_id} completed",
                },
            ).execute()
            if result.data:
                requeued_count += 1
        except Exception as e:
            # Log the error but continue processing other events
            # (in production, this would be audited)
            pass

    return {
        "requeued_count": requeued_count,
        "parked_events": parked_event_ids,
        "task_status": task_status,
    }


# =========================================================================
# Poller class (stub for integration with wake_driver)
# =========================================================================


class ParkedRequeuePoller:
    """Watches task_queue for done transitions and requeues blocked events."""

    def __init__(self, client: Client | None = None) -> None:
        self.client = client or _get_client()

    async def handle_task_done(self, task_event: dict[str, Any]) -> None:
        """Handle a task event (e.g., from a NOTIFY trigger or event stream).

        **Only triggers on terminal states.** Non-terminal task events (pending,
        claimed, running) are ignored.
        """
        task_id = task_event.get("id")
        task_status = task_event.get("status")

        # Only process terminal states
        if task_status not in ("done", "failed", "parked"):
            return

        # Check and requeue (if appropriate)
        check_and_requeue_for_task(task_id, self.client)


# =========================================================================
# Background poller loop (optional integration point)
# =========================================================================


async def run_poller(
    client: Client | None = None,
    poll_interval_seconds: float = 30.0,
) -> None:
    """Run the parked-event requeue poller as a background task.

    **Polling strategy:**
    - Periodically query task_queue for tasks in 'done' state.
    - For each done task, check for parked events and requeue them.
    - Sleep for poll_interval_seconds between checks.

    **Integration:** Can be spawned as a background asyncio.Task in wake_driver.
    For now, the primary integration is synchronous call from
    orchestrator.handle_event() on task-completion events.
    """
    cli = client or _get_client()
    poller = ParkedRequeuePoller(cli)

    import asyncio

    while True:
        try:
            # Query for tasks that recently transitioned to 'done'
            # (In a live system, this would be event-driven via NOTIFY,
            # not polled. For now, polling is a fallback.)
            done_tasks = (
                cli.table("task_queue")
                .select("id,status")
                .eq("status", "done")
                .limit(100)  # Batch process up to 100 done tasks per poll
                .execute()
            ).data or []

            for task in done_tasks:
                await poller.handle_task_done(task)

        except Exception:
            # Log error and continue (in production, would use structured logging)
            pass

        await asyncio.sleep(poll_interval_seconds)
