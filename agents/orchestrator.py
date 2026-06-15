"""Deterministic event router for reactive-core (issue #744).

``handle_event(event) -> Decision`` is a **pure function** of one row from the
``events`` table (#739 FSM: channel ``'events'``, ``notify_events_insert``).
It picks one of three routes — :class:`Route` — using a fixed table keyed on
``(event_type, severity)``. There is **no live model**: every current event
type has a deterministic route, and any unenumerated ``(event_type, severity)``
pair fails safe to ``ESCALATE``. The gemma4 judgment layer is deferred to #872.

Side effects (writing ``task_queue`` rows, weekend-aware owner notification,
running inline tool calls through the safety gate) live in :func:`dispatch`
and :func:`run_inline_tool`, which take ``now`` / ``client`` / ``notifier`` as
injected parameters. Keeping the routing decision pure is what lets AC1/AC4 be
asserted on fixed inputs, and the injected ``now`` is what lets AC3's
weekend-aware policy be asserted deterministically.
"""

from __future__ import annotations

import enum
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Mapping

from agents import safety, task_queue

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
    if event_type == "global_task_due" and severity == "low":
        # Global task due — route through EMIT_TASK. Skill dispatch happens in task_queue.
        dispatcher_skill = payload.get("dispatcher_skill", "research")
        return _emit(
            event_type,
            severity,
            target,
            key,
            goal=f"global task: {dispatcher_skill}",
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


# ---------------------------------------------------------------------------
# AC3 — weekend-aware escalation notification policy (pure)
# ---------------------------------------------------------------------------
#
# Decision basis: e5131e38 (#744 grill — weekend-aware escalate) +
# weekday_weekend_scheduling_policy (memory 46ee0986). The escalation *row* is
# always written (the owner never loses the work); this policy governs only
# *when/how* the owner is notified, so weekends stay HITL-free except for real
# incidents.


class EscalationNotice(enum.Enum):
    """How/when to surface an ``escalate_to_human`` decision to the owner."""

    TELEGRAM_NOW = "telegram_now"  # critical — ping immediately, any day (incident exception)
    PARK_MONDAY = "park_monday"  # non-critical on a weekend — defer owner attention to Monday
    SESSIONSTART = "sessionstart"  # non-critical weekday — surface at next SessionStart + on-demand


def escalation_notice(severity: str, now: datetime) -> EscalationNotice:
    """Decide the owner-notification mode for an escalation.

    Pure function of ``(severity, now)`` so it is assertable on fixed inputs:

    - ``critical`` → :attr:`EscalationNotice.TELEGRAM_NOW` regardless of weekday
      (a real incident overrides the no-weekend-HITL rule).
    - non-critical on a weekend (Sat/Sun) → :attr:`EscalationNotice.PARK_MONDAY`
      (weekends are autoregulation-only — no owner HITL).
    - non-critical on a weekday → :attr:`EscalationNotice.SESSIONSTART`
      (no interrupting ping; surfaced at the next session and on demand).
    """
    if severity == "critical":
        return EscalationNotice.TELEGRAM_NOW
    # datetime.weekday(): Monday=0 … Saturday=5, Sunday=6.
    if now.weekday() >= 5:
        return EscalationNotice.PARK_MONDAY
    return EscalationNotice.SESSIONSTART


# ---------------------------------------------------------------------------
# AC2 / AC3 — dispatch a Decision to its side effect
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DispatchResult:
    """Outcome of acting on a :class:`Decision` (what the side-effect layer did)."""

    route: Route
    enqueued: bool  # a task_queue row was written (False on idempotency collision)
    row: dict[str, Any] | None
    notice: EscalationNotice | None  # set only for ESCALATE
    notified: bool  # a Telegram ping was actually sent
    noop: bool  # pure-pipeline event — acknowledged, no work


def dispatch(
    decision: Decision,
    *,
    now: datetime,
    client: Any | None = None,
    notifier: Callable[[Decision], Any] | None = None,
) -> DispatchResult:
    """Perform the side effect for ``decision``.

    - :attr:`Route.EMIT_TASK` → write a ``sandcastle`` ``task_queue`` row
      (AC2). A colliding ``idempotency_key`` is a silent no-op (re-delivered
      event dedups; a genuinely-new event has a different key and re-runs).
    - :attr:`Route.ESCALATE` → write an ``owner`` row carrying
      ``escalated_reason`` (AC3), then apply the weekend-aware notification
      policy: ``critical`` pings Telegram via ``notifier``; everything else is
      parked (weekend) or left for SessionStart (weekday).
    - :attr:`Route.HANDLE_INLINE` → a pure-pipeline no-op is acknowledged
      here; a real inline tool call goes through :func:`run_inline_tool`.
    """
    if decision.route is Route.EMIT_TASK:
        row = task_queue.enqueue(
            goal=decision.goal,
            priority=decision.priority,
            assignee=decision.assignee,
            idempotency_key=decision.idempotency_key,
            client=client,
        )
        return DispatchResult(
            route=decision.route,
            enqueued=row is not None,
            row=row,
            notice=None,
            notified=False,
            noop=False,
        )

    if decision.route is Route.ESCALATE:
        row = task_queue.enqueue(
            goal=decision.goal or decision.escalated_reason or "escalation",
            priority=decision.priority,
            assignee=decision.assignee,
            idempotency_key=decision.idempotency_key,
            escalated_reason=decision.escalated_reason,
            client=client,
        )
        notice = escalation_notice(decision.severity, now)
        notified = False
        if notice is EscalationNotice.TELEGRAM_NOW and notifier is not None:
            notifier(decision)
            notified = True
        return DispatchResult(
            route=decision.route,
            enqueued=row is not None,
            row=row,
            notice=notice,
            notified=notified,
            noop=False,
        )

    # Route.HANDLE_INLINE
    return DispatchResult(
        route=decision.route,
        enqueued=False,
        row=None,
        notice=None,
        notified=False,
        noop=decision.noop,
    )


# ---------------------------------------------------------------------------
# AC5 — inline tool surface, gated by agents.safety (SAFETY-CRITICAL)
# ---------------------------------------------------------------------------
#
# The orchestrator may run a one-shot tool inline instead of emitting a task.
# Every such call routes through ``safety.gate()``: Tier 0 runs inline, Tier 1
# degrades to an owner ``task_queue`` row, Tier 2 is blocked + audited (gate
# raises ``GateError``). The registry below is the *intended* inline surface
# (read-only / Tier-0 tools); ``gate()`` is the enforcement — a registry entry
# that fails to classify Tier 0 still degrades or blocks, so a registration
# mistake cannot silently auto-run an unsafe action.

# tool_name -> (area, action, target) for safety.classify.
_INLINE_TOOL_REGISTRY: dict[str, tuple[str, str, str | None]] = {
    "audit_event": ("supabase", "insert", "audit_log"),
    "append_event": ("supabase", "append", "events"),
    "label_area": ("github", "add_label", "area:core-agent"),
}

_INLINE_AGENT_ID = "orchestrator"


@dataclass(frozen=True)
class InlineResult:
    """Outcome of an inline tool attempt through the safety gate."""

    tier: safety.Tier
    fired: bool  # the tool's fn actually ran (Tier 0)
    queued_owner_row: dict[str, Any] | None  # owner row written on Tier-1 degrade


def run_inline_tool(
    tool_name: str,
    *,
    fn: Callable[[], object] | None = None,
    agent_id: str = _INLINE_AGENT_ID,
    client: Any | None = None,
) -> InlineResult:
    """Run an inline tool under the safety gate (AC5).

    Resolves ``tool_name`` to its ``(area, action, target)`` from the inline
    registry, then defers the tier decision to :func:`safety.gate`:

    - **Tier 0** → ``fn`` runs inline, ``fired=True``.
    - **Tier 1** → degrade to an ``owner`` ``task_queue`` row; ``fn`` is not run.
    - **Tier 2** → :class:`safety.GateError` is raised (already audited).

    An **unmapped** tool has no vetted classification, so it is treated as
    Tier 1 (owner queue) — never auto-run.
    """
    mapping = _INLINE_TOOL_REGISTRY.get(tool_name)
    if mapping is None:
        area: str | None = None
        action = tool_name
        target: str | None = None
    else:
        area, action, target = mapping

    outcome = safety.gate(
        agent_id=agent_id,
        tool_name=tool_name,
        action=action,
        target=target,
        area=area,
        fn=fn,
    )  # Tier 2 raises GateError here (audited) and propagates.

    if outcome.tier is safety.Tier.OWNER_QUEUE:
        row = task_queue.enqueue(
            goal=f"inline tool {tool_name!r} needs owner approval (Tier 1)",
            priority=priority_for("medium"),
            assignee=_ASSIGNEE_OWNER,
            idempotency_key=outcome.idempotency_key,
            escalated_reason=f"inline tool {tool_name!r} classified Tier 1 (owner queue)",
            client=client,
        )
        return InlineResult(tier=outcome.tier, fired=False, queued_owner_row=row)

    return InlineResult(tier=outcome.tier, fired=outcome.fired, queued_owner_row=None)
