"""Task queue interface for the reactive core (issue #740).

Three operations — enqueue, claim_next, transition — that encapsulate
the task_queue table's FSM:

  pending -> claimed -> running -> done | failed | parked
  claimed -> pending      (claim timeout / re-queue)

Usage::

    from agents import task_queue, supabase_client

    client = supabase_client.get_client()
    row = task_queue.claim_next(client)
    if row:
        task_queue.transition(client, row["id"], "running")
        # ... do the work ...
        task_queue.transition(client, row["id"], "done")
"""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

_VALID_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"claimed"},
    "claimed": {"pending", "running"},
    "running": {"done", "failed", "parked"},
}


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _ensure_idempotency_key(row: dict[str, Any]) -> str:
    """Generate an idempotency_key if none provided.

    Uses sha256 of goal + scope_files + priority for auto-generated keys.
    Callers SHOULD provide their own deterministic key when re-enqueueing
    the same logical task is undesirable.
    """
    key = row.get("idempotency_key") or hashlib.sha256(
        f"{row.get('goal', '')}|{row.get('scope_files', [])}|{row.get('priority', 0)}".encode(
            "utf-8"
        )
    ).hexdigest()
    return key


def enqueue(
    client: Any,
    *,
    goal: str,
    scope_files: list[str] | None = None,
    priority: int = 0,
    assignee: str | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any] | None:
    """Insert a new task_queue row in ``pending`` state.

    If ``idempotency_key`` is not provided, one is auto-generated from
    goal + scope_files + priority. Returns the inserted row data, or
    ``None`` if a row with the same key already exists (idempotent).
    """
    key = idempotency_key or _ensure_idempotency_key(
        {"goal": goal, "scope_files": scope_files, "priority": priority}
    )

    row = {
        "goal": goal,
        "scope_files": scope_files or [],
        "priority": priority,
        "assignee": assignee,
        "idempotency_key": key,
        "status": "pending",
    }

    result = (
        client.table("task_queue")
        .upsert(row, on_conflict="idempotency_key", ignore_duplicates=True)
        .execute()
    )
    data = result.data or []
    if data:
        logger.debug("Enqueued task %s (priority=%s, assignee=%s)", key[:12], priority, assignee)
        return data[0]
    logger.debug("Duplicate task %s skipped", key[:12])
    return None


def claim_next(client: Any) -> dict[str, Any] | None:
    """Claim the highest-priority pending task (FIFO within priority).

    Uses a two-step select-then-update pattern suitable for Supabase REST.
    Returns the claimed row, or ``None`` if no pending rows exist.
    """
    # Step 1: find the next candidate.
    candidates = (
        client.table("task_queue")
        .select("id")
        .eq("status", "pending")
        .order("priority", desc=False)  # lower number = higher priority
        .order("created_at", desc=False)  # FIFO within priority
        .limit(1)
        .execute()
        .data
        or []
    )
    if not candidates:
        return None

    row_id = candidates[0]["id"]

    # Step 2: claim it atomically (status check prevents double-claim).
    result = (
        client.table("task_queue")
        .update({"status": "claimed", "claimed_at": _now_iso()})
        .eq("id", row_id)
        .eq("status", "pending")  # safety: only claim if still pending
        .execute()
    )
    data = result.data or []
    if data:
        logger.debug("Claimed task %s", row_id)
        return data[0]
    # Race: another consumer claimed it between select and update.
    # Recurse to find the next available.
    return claim_next(client)


def transition(
    client: Any,
    row_id: str,
    new_status: str,
    *,
    outcome_note: str | None = None,
) -> dict[str, Any]:
    """Move a task from its current status to ``new_status``.

    Validates the transition against the FSM before applying. Returns
    the updated row. Raises ``ValueError`` on invalid transition.
    """
    # Fetch current row to validate transition.
    rows = (
        client.table("task_queue")
        .select("status")
        .eq("id", row_id)
        .limit(1)
        .execute()
        .data
        or []
    )
    if not rows:
        raise ValueError(f"task {row_id} not found")

    current_status = rows[0]["status"]
    allowed = _VALID_TRANSITIONS.get(current_status, set())
    if new_status not in allowed:
        raise ValueError(
            f"Invalid transition: {current_status} -> {new_status} "
            f"(allowed from {current_status}: {sorted(allowed)})"
        )

    update: dict[str, Any] = {"status": new_status}
    if new_status == "claimed":
        update["claimed_at"] = _now_iso()
    elif new_status in ("done", "failed", "parked"):
        update["completed_at"] = _now_iso()
    if outcome_note:
        update["outcome_note"] = outcome_note

    result = (
        client.table("task_queue")
        .update(update)
        .eq("id", row_id)
        .execute()
    )
    data = result.data or []
    if data:
        logger.debug("Transitioned task %s: %s -> %s", row_id, current_status, new_status)
        return data[0]
    raise RuntimeError(f"Failed to transition task {row_id} to {new_status}")
