"""Deterministic event router for reactive-core (issue #744).

``handle_event(event) -> Decision`` is a **pure function** of one row from the
``events`` table (#739 FSM: channel ``'events'``, ``notify_events_insert``).
It picks one of three routes — :class:`Route` — using a fixed table keyed on
``(event_type, severity)``. There is **no live model**: every current event
type has a deterministic route, and any unenumerated ``(event_type, severity)``
pair fails safe to ``ESCALATE``. The gemma4 judgment layer is deferred to #872.

Side effects (writing ``task_queue`` rows, weekend-aware owner notification,
running inline tool calls through the safety gate) live in :func:`dispatch`,
which takes ``now`` / ``client`` / ``notifier`` as injected parameters. Keeping
the routing decision pure is what lets AC1/AC4 be asserted on fixed inputs.
"""

from __future__ import annotations

import enum
import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

# Severity ordering — strictly monotonic so priority never ties across tiers.
_SEVERITY_RANK: dict[str, int] = {
    "info": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}

# Escalations outrank same-severity worker tasks in the queue (AC3).
_ESCALATE_PRIORITY_BOOST = 10

# Pure-pipeline events that need no triage — acknowledge and move on (AC1).
_NOOP_EVENT_TYPES: frozenset[str] = frozenset({"pr_approved", "pr_merged", "ci_success"})

_ASSIGNEE_WORKER = "sandcastle"
_ASSIGNEE_OWNER = "owner"


class Route(enum.Enum):
    """The three dispositions a single event can take."""

    HANDLE_INLINE = "handle_inline"
    EMIT_TASK = "emit_task"
    ESCALATE = "escalate_to_human"


@dataclass(frozen=True)
class Decision:
    """The routing verdict for one event — pure data, no side effects.

    ``dispatch`` consumes this to perform the actual write/notify/run.
    """

    route: Route
    event_type: str
    severity: str
    target: str
    idempotency_key: str
    priority: int
    goal: str = ""
    assignee: str | None = None
    escalated_reason: str | None = None
    noop: bool = False


def priority_for(severity: str) -> int:
    """Map a severity to a queue priority (higher = claimed first).

    Unknown severities sort below ``info`` rather than raising — a malformed
    severity should never crash the router (it will fail safe to escalate on
    the route side anyway)."""
    return _SEVERITY_RANK.get(severity, -1)


def _target_of(payload: Mapping[str, Any]) -> str:
    """Best-effort human/stable target identifier from the event payload.

    Used both for task descriptions (``/rework <PR>``) and as part of the
    idempotency key. Falls back to empty string when nothing identifying is
    present."""
    for k in ("pr", "pr_number", "number", "target", "workflow", "ref"):
        v = payload.get(k)
        if v not in (None, ""):
            return str(v)
    return ""


def _idempotency_key(event_type: str, target: str, payload: Mapping[str, Any]) -> str:
    """``sha256(event_type | target | payload-state-discriminator)`` (AC2).

    The state-discriminator is the canonical JSON of the payload: an identical
    re-delivery hashes the same (dedup), while a genuinely-new event — a fresh
    commit SHA, a new run id — changes the payload and so re-runs. Choosing the
    whole payload (rather than a curated key subset) is an MVP simplification;
    a tighter discriminator that ignores volatile fields belongs with the
    model-layer refinement (#872)."""
    discriminator = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    raw = "|".join([event_type, target, discriminator])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _emit(event_type: str, severity: str, target: str, key: str, *, goal: str) -> Decision:
    return Decision(
        route=Route.EMIT_TASK,
        event_type=event_type,
        severity=severity,
        target=target,
        idempotency_key=key,
        priority=priority_for(severity),
        goal=goal,
        assignee=_ASSIGNEE_WORKER,
    )


def _escalate(event_type: str, severity: str, target: str, key: str, *, reason: str) -> Decision:
    return Decision(
        route=Route.ESCALATE,
        event_type=event_type,
        severity=severity,
        target=target,
        idempotency_key=key,
        priority=priority_for(severity) + _ESCALATE_PRIORITY_BOOST,
        goal=reason,
        assignee=_ASSIGNEE_OWNER,
        escalated_reason=reason,
    )


def _inline_noop(event_type: str, severity: str, target: str, key: str) -> Decision:
    return Decision(
        route=Route.HANDLE_INLINE,
        event_type=event_type,
        severity=severity,
        target=target,
        idempotency_key=key,
        priority=priority_for(severity),
        noop=True,
    )


def handle_event(event: Mapping[str, Any]) -> Decision:
    """Route one ``events`` row to a :class:`Decision`. Pure, no side effects.

    Resolution order (AC1 + AC4):

    1. ``security_alert`` → ``ESCALATE`` at any severity — a safety floor the
       route table cannot override (never inline).
    2. Enumerated ``(event_type, severity)`` pairs → their specific route.
    3. Pure-pipeline events (``pr_approved`` / ``pr_merged`` / ``ci_success``)
       → inline no-op (the wake_driver marks the event processed).
    4. Anything else → fail-safe ``ESCALATE``.
    """
    event_type = str(event.get("event_type", ""))
    severity = str(event.get("severity") or "info")
    payload = event.get("payload") or {}
    target = _target_of(payload)
    key = _idempotency_key(event_type, target, payload)

    # 1. Safety floor (AC4) — security events always reach a human.
    if event_type == "security_alert":
        return _escalate(
            event_type,
            severity,
            target,
            key,
            reason=f"security_alert ({severity}) — owner review required, never auto-handled",
        )

    # 2. Enumerated deterministic routes (AC1).
    if (event_type, severity) == ("ci_failure", "high"):
        return _emit(
            event_type,
            severity,
            target,
            key,
            goal=f"fix: ci_failure on {target or 'unknown target'}",
        )
    if (event_type, severity) == ("review_negative", "medium"):
        return _emit(
            event_type,
            severity,
            target,
            key,
            goal=f"/rework {target}".rstrip(),
        )

    # 3. Pure-pipeline events → acknowledge, no work (AC1).
    if event_type in _NOOP_EVENT_TYPES:
        return _inline_noop(event_type, severity, target, key)

    # 4. Fail-safe (AC1) — unknown (event_type, severity) goes to a human.
    return _escalate(
        event_type,
        severity,
        target,
        key,
        reason=f"no deterministic route for ({event_type!r}, {severity!r})",
    )
