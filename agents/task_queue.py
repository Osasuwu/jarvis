"""Task queue interface — enqueue, claim_next, transition.

Built on the reshaped ``task_queue`` table (issue #740):
- FSM: ``pending → claimed → running → done | failed | parked``
- Priority-ordered claiming (highest first, FIFO for ties)
- Idempotency-key dedup (colliding key on enqueue is a silent no-op)

Usage::

    from agents.task_queue import claim_next, enqueue, transition

    row = enqueue(goal="fix: tighten error path",
                  priority=10,
                  idempotency_key=sha256(...))
    if row is None:
        ...  # colliding key

    claimed = claim_next()
    if claimed is None:
        ...  # queue empty

    transition(claimed["id"], "running")
    transition(claimed["id"], "done")
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from supabase import Client

from agents.supabase_client import get_client

# -- FSM -------------------------------------------------------------------

_VALID_TRANSITIONS: dict[str, frozenset[str]] = {
    "pending": frozenset({"claimed"}),
    "claimed": frozenset({"running"}),
    "running": frozenset({"done", "failed", "parked"}),
}

_TERMINAL_STATES: frozenset[str] = frozenset({"done", "failed", "parked"})


# -- Public API ------------------------------------------------------------


def enqueue(
    *,
    goal: str,
    priority: int = 0,
    assignee: str | None = None,
    idempotency_key: str,
    scope_files: list[str] | None = None,
    escalated_reason: str | None = None,
    client: Client | None = None,
) -> dict[str, Any] | None:
    """Insert a task into the queue.

    **Idempotent:** a colliding ``idempotency_key`` silently returns
    ``None`` instead of raising. Callers that need to detect collision
    should check the return value.

    ``escalated_reason`` is persisted on insert for ``assignee='owner'``
    escalation rows (the deterministic router's ``escalate_to_human``
    route, #744) so the owner sees *why* a task was escalated without a
    separate transition. The column already exists on ``task_queue``.

    Returns the inserted row, or ``None`` if the key already existed.
    """
    cli = client or get_client()
    row: dict[str, Any] = {
        "goal": goal,
        "priority": priority,
        "idempotency_key": idempotency_key,
        "status": "pending",
    }
    if assignee is not None:
        row["assignee"] = assignee
    if scope_files:
        row["scope_files"] = scope_files
    if escalated_reason is not None:
        row["escalated_reason"] = escalated_reason

    result = cli.table("task_queue").insert(row).execute()
    data = result.data or []
    return data[0] if data else None


def claim_next(
    client: Client | None = None,
) -> dict[str, Any] | None:
    """Claim the highest-priority pending task (priority desc, FIFO ties).

    Returns the claimed row with status updated to ``claimed``, or
    ``None`` if the queue is empty or another worker claimed the task
    first (optimistic lock).

    The returned dict includes the full row as it looked after the update,
    including ``id``, ``status``, ``claimed_at``, etc.
    """
    cli = client or get_client()

    # Read the highest-priority pending task
    rows = (
        cli.table("task_queue")
        .select("*")
        .eq("status", "pending")
        .order("priority", desc=True)
        .order("created_at", desc=False)
        .limit(1)
        .execute()
    ).data or []

    if not rows:
        return None

    task = rows[0]

    # Optimistic-lock claim: only succeeds if row is still pending
    now = datetime.now(timezone.utc).isoformat()
    result = (
        cli.table("task_queue")
        .update({"status": "claimed", "claimed_at": now})
        .eq("id", task["id"])
        .eq("status", "pending")
        .execute()
    )

    updated = result.data or []
    return updated[0] if updated else None


def transition(
    task_id: str,
    to_status: str,
    *,
    reason: str | None = None,
    client: Client | None = None,
) -> dict[str, Any]:
    """Transition a task to a new status, validating the FSM.

    Parameters
    ----------
    task_id
        UUID of the task to transition.
    to_status
        Target FSM state. Must be a legal transition from the current
        state of the task.
    reason
        Optional reason attached to ``escalated_reason`` (useful for
        ``failed`` transitions to document the failure cause).

    Returns the updated row.

    Raises
    ------
    ValueError
        The transition is not allowed by the FSM (e.g. ``pending → done``
        without going through ``claimed → running``).
    RuntimeError
        The task does not exist, or another worker modified it between
        our read and write (optimistic lock failure).
    """
    cli = client or get_client()

    # Read current state
    rows = (
        cli.table("task_queue").select("status").eq("id", task_id).limit(1).execute()
    ).data or []

    if not rows:
        raise RuntimeError(f"Task not found: {task_id}")

    current_status = rows[0]["status"]

    if current_status in _TERMINAL_STATES:
        raise ValueError(f"Cannot transition from terminal state {current_status!r}")

    allowed = _VALID_TRANSITIONS.get(current_status, frozenset())
    if to_status not in allowed:
        raise ValueError(
            f"Illegal transition: {current_status!r} → {to_status!r}. "
            f"Allowed targets from {current_status!r}: "
            f"{sorted(allowed)}"
        )

    # Build update payload
    now = datetime.now(timezone.utc).isoformat()
    update: dict[str, Any] = {"status": to_status}

    if to_status == "claimed":
        update["claimed_at"] = now
    elif to_status in ("done", "failed"):
        update["completed_at"] = now

    if reason is not None:
        update["escalated_reason"] = reason

    # Optimistic lock: only succeeds if status hasn't changed since our read
    result = (
        cli.table("task_queue")
        .update(update)
        .eq("id", task_id)
        .eq("status", current_status)
        .execute()
    )

    updated = result.data or []
    if not updated:
        raise RuntimeError(
            f"Transition {current_status!r} → {to_status!r} failed: "
            f"task {task_id} was modified by another worker"
        )

    return updated[0]
