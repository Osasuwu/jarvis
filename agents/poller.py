"""Parked-event re-queue poller — Path B (#745).

When the orchestrator parks an event because it is blocked on a sandcastle
task, the poller periodically checks whether the blocking task has reached
a terminal state and re-queues the event accordingly.

- Task ``done`` → event is re-queued to ``pending`` so the wake_driver
  picks it up on the next drain.
- Task ``failed`` → event is re-queued to ``pending`` (not silently dropped;
  the orchestrator will re-route it per the deterministic routing table).
- Task still ``running`` or ``parked`` → event stays ``parked``.
- No ``blocked_by_task_id`` in event payload → skipped (parked for a
  different reason).

Usage::

    from agents import poller

    requeued = poller.poll(port)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    import json

logger = logging.getLogger(__name__)


# -- Port ---------------------------------------------------------------------


class PollerPort(Protocol):
    """Interface the poller depends on for events and task_queue access.

    Implemented by an in-memory fake in tests and by a live adapter
    (PsycopgPollerPort) in production.
    """

    def find_parked_events(self) -> list[dict[str, Any]]:
        """Return every ``parked`` event whose payload contains ``blocked_by_task_id``.

        Returns a list of event dicts. Each dict must have at least ``id``
        and ``payload`` keys. Events parked for other reasons (no
        ``blocked_by_task_id``) are filtered out by the port implementation.
        """

    def get_task_status(self, task_id: str) -> str | None:
        """Return the current FSM state of a task, or ``None`` if not found.

        Expected values: ``"running"``, ``"done"``, ``"failed"``, ``"parked"``.
        """

    def requeue_event(self, event_id: str, *, reason: str) -> bool:
        """Transition a parked event back to ``pending``.

        Returns ``True`` if the event was successfully requeued.
        """


# -- Core logic ---------------------------------------------------------------


def poll(port: PollerPort) -> int:
    """Check all parked events with a ``blocked_by_task_id`` reference.

    For each parked event:
    - If the blocking task reached ``done`` → requeue the event.
    - If the blocking task reached ``failed`` → requeue the event (the
      orchestrator will re-route it — never silently dropped).
    - If the blocking task is still ``running`` / ``parked``, or the task
      no longer exists → leave the event parked.

    Returns the number of events requeued.
    """
    parked = port.find_parked_events()
    requeued = 0
    for event in parked:
        task_id = _blocking_task_id(event)
        if task_id is None:
            continue

        task_status = port.get_task_status(task_id)
        if task_status == "done":
            port.requeue_event(event["id"], reason=f"Blocking task {task_id} completed")
            requeued += 1
            logger.info(
                "Re-queued event %s (blocking task %s is done)",
                event["id"],
                task_id,
            )
        elif task_status == "failed":
            port.requeue_event(event["id"], reason=f"Blocking task {task_id} failed")
            requeued += 1
            logger.info(
                "Re-queued event %s (blocking task %s failed — orchestrator re-routes)",
                event["id"],
                task_id,
            )

    return requeued


# -- Helpers ------------------------------------------------------------------


def _blocking_task_id(event: dict[str, Any]) -> str | None:
    """Extract ``blocked_by_task_id`` from an event's ``payload``.

    Handles payload as a dict or a JSON string (PostgREST may return
    jsonb as a pre-parsed dict or as a string depending on the query path).
    Returns ``None`` when the field is missing, empty, or unparseable.
    """
    payload = event.get("payload")
    if payload is None:
        return None
    if isinstance(payload, str):
        try:
            import json

            payload = json.loads(payload)
        except (ValueError, TypeError):
            return None
    if not isinstance(payload, dict):
        return None
    tid = payload.get("blocked_by_task_id")
    return str(tid) if tid else None
