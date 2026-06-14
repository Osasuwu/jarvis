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
from typing import Any, Protocol

logger = logging.getLogger(__name__)


# -- Port ---------------------------------------------------------------------


class PollerPort(Protocol):
    """Interface the poller depends on for events and task_queue access.

    Implemented by an in-memory fake in tests and by a live database-backed
    adapter wired in a future slice (the production poller is scaffolding here —
    no concrete adapter ships in this slice).
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
        try:
            requeued += _process_parked_event(port, event)
        except Exception:  # noqa: BLE001 — one bad event must not abort the sweep
            # A status probe or requeue can raise (network blip, malformed row).
            # Isolate per event: log and continue so the remaining parked events
            # are still evaluated this pass instead of being stranded until the
            # next poll because an earlier event blew up the loop.
            logger.exception(
                "Poller failed on event %s; left parked for the next pass",
                event.get("id"),
            )

    return requeued


def _process_parked_event(port: PollerPort, event: dict[str, Any]) -> int:
    """Evaluate one parked event; return 1 if it was requeued, else 0.

    A requeue only counts when ``requeue_event`` confirms the transition
    (returns ``True``). A ``False`` return means the event was *not* moved to
    ``pending`` — e.g. it vanished or lost its parked state under a concurrent
    writer — so counting it would over-report progress and mask a stuck event.
    """
    task_id = _blocking_task_id(event)
    if task_id is None:
        return 0

    task_status = port.get_task_status(task_id)
    if task_status == "done":
        ok = port.requeue_event(event["id"], reason=f"Blocking task {task_id} completed")
        if not ok:
            logger.warning(
                "Requeue of event %s (task %s done) was not applied",
                event["id"],
                task_id,
            )
            return 0
        logger.info("Re-queued event %s (blocking task %s is done)", event["id"], task_id)
        return 1
    if task_status == "failed":
        ok = port.requeue_event(event["id"], reason=f"Blocking task {task_id} failed")
        if not ok:
            logger.warning(
                "Requeue of event %s (task %s failed) was not applied",
                event["id"],
                task_id,
            )
            return 0
        logger.info(
            "Re-queued event %s (blocking task %s failed — orchestrator re-routes)",
            event["id"],
            task_id,
        )
        return 1
    return 0


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
    # Guard on None/empty-string explicitly, not truthiness: a valid task id of
    # integer ``0`` (or any falsy-but-present value) must survive — ``if tid``
    # would drop it and silently strand the parked event.
    if tid is None or tid == "":
        return None
    return str(tid)
