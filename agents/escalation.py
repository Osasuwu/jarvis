"""Escalation triggers for the task worker (issue #299, S2-4, refactored #740).

Called before executing a ``task_queue`` row. If any trigger fires,
:func:`escalate` moves the row to ``parked`` state and writes an
``events`` row with ``severity=HIGH``.

Three triggers — split into pure checks (no DB writes, trivially testable)
and one DB-writing :func:`escalate` helper:

1. **Limit near-exhaustion** — :mod:`agents.usage_probe` says budget is
   low; pause rather than burn the last tokens on auto-dispatch.
2. **Cross-task conflict** — another ``running`` row touches overlapping
   ``scope_files``; avoid interleaved edits.
3. **Pattern repeat** — >3 successful runs of the same ``goal`` in
   a row; guards against a runaway loop.

Thresholds are module-level constants so tuning is a one-line change.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from agents import supabase_client
from agents.usage_probe import UsageReading

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tunable thresholds. Change here and the rule changes everywhere.
# ---------------------------------------------------------------------------

PATTERN_REPEAT_THRESHOLD = 3

DISPATCHER_AGENT_ID = "task-dispatcher"
ESCALATION_EVENT_TYPE = "dispatcher_escalation"
ESCALATION_SEVERITY = "high"


class Trigger(str, Enum):
    """Reason an escalation fired. Becomes the ``trigger`` payload field."""

    LIMIT_NEAR_EXHAUSTION = "limit_near_exhaustion"
    CROSS_TASK_CONFLICT = "cross_task_conflict"
    PATTERN_REPEAT = "pattern_repeat"


@dataclass(frozen=True)
class EscalationCheck:
    """Outcome of a single trigger check.

    ``context`` is free-form dict captured for the event payload so the
    owner can reason about *why* without re-running the check. Keep it
    small and JSON-safe — it round-trips through Supabase jsonb.
    """

    should_escalate: bool
    trigger: Trigger | None = None
    context: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def no_action(cls) -> "EscalationCheck":
        return cls(should_escalate=False)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Pure checks — no DB writes, safe to run against synthetic rows in tests.
# ---------------------------------------------------------------------------


def check_limit_near_exhaustion(reading: UsageReading) -> EscalationCheck:
    """Escalate when the usage probe reports budget near-exhaustion."""
    if reading.near_exhaustion:
        return EscalationCheck(
            should_escalate=True,
            trigger=Trigger.LIMIT_NEAR_EXHAUSTION,
            context={
                "used": reading.used,
                "total": reading.total,
                "headroom_ratio": reading.headroom_ratio,
            },
        )
    return EscalationCheck.no_action()


def check_cross_task_conflict(
    row: dict[str, Any],
    *,
    active_dispatched_rows: Iterable[dict[str, Any]],
) -> EscalationCheck:
    """Escalate if another dispatched row's ``scope_files`` overlaps this one.

    ``active_dispatched_rows`` comes from the dispatcher's scan — the rows
    with ``status='dispatched'`` that aren't this one. Dispatcher's
    responsibility to exclude the current row; we don't check ids here.
    """
    own_files = set(row.get("scope_files") or [])
    if not own_files:
        return EscalationCheck.no_action()
    own_id = row.get("id")
    for other in active_dispatched_rows:
        if other.get("id") == own_id:
            # Defensive: dispatcher should've excluded us, but a safety net
            # costs one comparison and prevents a row flagging itself.
            continue
        other_files = set(other.get("scope_files") or [])
        overlap = own_files & other_files
        if overlap:
            return EscalationCheck(
                should_escalate=True,
                trigger=Trigger.CROSS_TASK_CONFLICT,
                context={
                    "conflicting_task_id": str(other.get("id")),
                    "overlapping_files": sorted(overlap),
                },
            )
    return EscalationCheck.no_action()


def check_pattern_repeat(
    row: dict[str, Any],
    *,
    recent_successful_dispatches: Iterable[dict[str, Any]],
    threshold: int = PATTERN_REPEAT_THRESHOLD,
) -> EscalationCheck:
    """Escalate when the same ``goal`` appears > ``threshold`` times consecutively.

    ``recent_successful_dispatches`` should be ordered newest-first
    (standard Supabase ``order('completed_at', desc=True)``). We count the
    run of matching goals from the most recent entry; a different goal
    anywhere in the run resets the count.
    """
    goal = row.get("goal")
    if not goal:
        return EscalationCheck.no_action()
    run_length = 0
    for past in recent_successful_dispatches:
        if past.get("goal") == goal:
            run_length += 1
        else:
            break
    if run_length > threshold:
        return EscalationCheck(
            should_escalate=True,
            trigger=Trigger.PATTERN_REPEAT,
            context={
                "goal": goal,
                "recent_matching_dispatches": run_length,
                "threshold": threshold,
            },
        )
    return EscalationCheck.no_action()


# ---------------------------------------------------------------------------
# Aggregator — dispatcher's single entry point.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EscalationContext:
    """Bundle of context every check needs — keeps the call site terse.

    ``usage_reading`` is the cached probe reading for this tick.
    """

    usage_reading: UsageReading
    active_dispatched_rows: Iterable[dict[str, Any]] = field(default_factory=tuple)
    recent_successful_dispatches: Iterable[dict[str, Any]] = field(default_factory=tuple)


def check_all(row: dict[str, Any], ctx: EscalationContext) -> EscalationCheck:
    """Run every trigger; return the first that fires, or ``no_action``."""
    for check in (
        lambda: check_limit_near_exhaustion(ctx.usage_reading),
        lambda: check_cross_task_conflict(row, active_dispatched_rows=ctx.active_dispatched_rows),
        lambda: check_pattern_repeat(
            row, recent_successful_dispatches=ctx.recent_successful_dispatches
        ),
    ):
        result = check()
        if result.should_escalate:
            return result
    return EscalationCheck.no_action()


# ---------------------------------------------------------------------------
# DB side-effect: write event + flip row status.
# ---------------------------------------------------------------------------


def escalate(
    row: dict[str, Any],
    check: EscalationCheck,
    *,
    client: Any | None = None,
    config: Any | None = None,
) -> dict[str, Any]:
    """Persist an escalation: write `events` row + flip `task_queue.status` to 'parked'.

    Returns the inserted event row. Raises if the check didn't actually
    flag an escalation — easier to catch misuse than to silently skip.
    """
    if not check.should_escalate or check.trigger is None:
        raise ValueError("escalate() called on a non-escalating check")

    cli = client or supabase_client.get_client(config)
    queue_id = row.get("id")
    reason = f"{check.trigger.value}: {check.context}"

    # Event first — dispatcher writes this in tier-0 territory (events is
    # on the Sprint-1 allowlist). Queue update is tier-0 too (status flip
    # within approved rows).
    event_payload = {
        "queue_id": str(queue_id) if queue_id is not None else None,
        "trigger": check.trigger.value,
        "context": check.context,
    }
    event_row = (
        cli.table("events")
        .insert(
            {
                "event_type": ESCALATION_EVENT_TYPE,
                "severity": ESCALATION_SEVERITY,
                "repo": "Osasuwu/jarvis",
                "source": DISPATCHER_AGENT_ID,
                "title": f"Dispatcher escalated task {queue_id}: {check.trigger.value}",
                "payload": event_payload,
            }
        )
        .execute()
    )
    event_data = (event_row.data or [{}])[0]

    # Queue status update — only if we know the id. An unidentifiable row
    # means the caller constructed it by hand; the event still carries the
    # signal, so don't fail the whole escalation on a missing id.
    if queue_id is not None:
        (
            cli.table("task_queue")
            .update({"status": "parked", "outcome_note": reason})
            .eq("id", queue_id)
            .execute()
        )

    return event_data
