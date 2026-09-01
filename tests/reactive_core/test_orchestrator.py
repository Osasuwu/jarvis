"""Tests for the deterministic event router (issue #744).

The router is a pure function of one ``events``-table row. No live model:
every assertion here pins a fixed (event_type, severity) input to its route.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import datetime

import pytest
from postgrest.exceptions import APIError

from agents import safety
from agents.orchestrator import (
    Decision,
    DispatchResult,
    EscalationNotice,
    InlineResult,
    Route,
    build_production_orchestrator,
    dispatch,
    escalation_notice,
    handle_event,
    priority_for,
    run_inline_tool,
)


def _ev(event_type: str, severity: str = "info", payload: dict | None = None) -> dict:
    return {
        "event_type": event_type,
        "severity": severity,
        "payload": payload or {},
    }


# -- Fake task_queue client (insert-only; simulates idempotency collision) --


class _FakeResult:
    def __init__(self, data: list[dict]) -> None:
        self.data = data


class _FakeInsert:
    def __init__(
        self,
        table: _FakeTable,
        payload: dict,
        *,
        on_conflict: str | None = None,
        ignore_duplicates: bool = False,
    ) -> None:
        self._table = table
        self._payload = payload
        self._on_conflict = on_conflict
        self._ignore_duplicates = ignore_duplicates

    def execute(self) -> _FakeResult:
        key = self._payload.get("idempotency_key")
        if any(r.get("idempotency_key") == key for r in self._table.rows):
            # Faithful PostgREST: bare insert on a duplicate raises; only
            # upsert(on_conflict="idempotency_key", ignore_duplicates=True)
            # resolves the collision to empty data (#1455 AC5).
            if self._on_conflict == "idempotency_key" and self._ignore_duplicates:
                return _FakeResult([])
            raise RuntimeError("23505: duplicate key value violates unique constraint")
        # #1119's idx_task_queue_target_active partial unique index — a
        # *different* idempotency_key can still collide on target pins
        # (target_repo, target_type, target_number), which the on_conflict
        # clause above doesn't cover. Raises the real APIError shape
        # task_queue.enqueue's `except APIError as e: e.code == "23505"`
        # branch actually catches (#1617 plan step 15).
        target_type = self._payload.get("target_type")
        if target_type not in (None, "none"):
            target_key = (
                self._payload.get("target_repo"),
                target_type,
                self._payload.get("target_number"),
            )
            if any(
                (r.get("target_repo"), r.get("target_type"), r.get("target_number")) == target_key
                for r in self._table.rows
                if r.get("target_type") not in (None, "none")
            ):
                raise APIError(
                    {
                        "message": "duplicate key value violates unique constraint "
                        '"idx_task_queue_target_active"',
                        "code": "23505",
                        "details": None,
                        "hint": None,
                    }
                )
        stored = {**self._payload, "id": f"tq-{len(self._table.rows) + 1}"}
        self._table.rows.append(stored)
        return _FakeResult([stored])


class _FakeTable:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    def insert(self, payload: dict) -> _FakeInsert:
        return _FakeInsert(self, payload)

    def upsert(
        self,
        payload: dict,
        *,
        on_conflict: str | None = None,
        ignore_duplicates: bool = False,
        **kwargs: object,
    ) -> _FakeInsert:
        return _FakeInsert(
            self, payload, on_conflict=on_conflict, ignore_duplicates=ignore_duplicates
        )


class _FakeClient:
    def __init__(self) -> None:
        self._tables: dict[str, _FakeTable] = {}

    def table(self, name: str) -> _FakeTable:
        return self._tables.setdefault(name, _FakeTable())


# Weekdays/weekends with a fixed, deterministic clock (no Date.now()).
_FRIDAY = datetime(2026, 5, 29, 10, 0, 0)  # weekday() == 4
_SATURDAY = datetime(2026, 5, 30, 10, 0, 0)  # weekday() == 5
_SUNDAY = datetime(2026, 5, 31, 10, 0, 0)  # weekday() == 6
_MONDAY = datetime(2026, 6, 1, 10, 0, 0)  # weekday() == 0


# -- AC1: deterministic route table ----------------------------------------


def test_security_alert_critical_escalates():
    assert handle_event(_ev("security_alert", "critical")).route is Route.ESCALATE


def test_ci_failure_high_emits_task():
    d = handle_event(_ev("ci_failure", "high", {"pr": 5}))
    assert d.route is Route.EMIT_TASK
    assert d.assignee == "sandcastle"


def test_ci_failure_goal_includes_cross_repo_context():
    """Cross-repo ci_failure goals carry the originating repo for debuggability."""
    event = {
        "event_type": "ci_failure",
        "severity": "high",
        "repo": "SergazyNarynov/redrobot",
        "payload": {"workflow": "CI", "branch": "master"},
    }
    d = handle_event(event)
    assert d.route is Route.EMIT_TASK
    assert "SergazyNarynov/redrobot" in d.goal


def test_ci_failure_goal_no_redundant_repo_for_own_repo(monkeypatch):
    """Own-repo ci_failure goals stay clean — no self-referential repo tag."""
    monkeypatch.delenv("GITHUB_REPO", raising=False)
    event = {
        "event_type": "ci_failure",
        "severity": "high",
        "repo": "Osasuwu/jarvis",
        "payload": {"workflow": "Tests", "branch": "main"},
    }
    d = handle_event(event)
    assert d.route is Route.EMIT_TASK
    assert "Osasuwu/jarvis" not in d.goal


def test_ci_failure_goal_no_redundant_repo_for_own_repo_on_fork(monkeypatch):
    """GITHUB_REPO drives the own-repo check — a jarvis-oss fork's own events
    must stay untagged too, not just the canonical Osasuwu/jarvis slug."""
    monkeypatch.setenv("GITHUB_REPO", "someoperator/jarvis-oss")
    event = {
        "event_type": "ci_failure",
        "severity": "high",
        "repo": "someoperator/jarvis-oss",
        "payload": {"workflow": "Tests", "branch": "main"},
    }
    d = handle_event(event)
    assert d.route is Route.EMIT_TASK
    assert "someoperator/jarvis-oss" not in d.goal


def test_review_negative_medium_emits_rework():
    d = handle_event(_ev("review_negative", "medium", {"pr": 7}))
    assert d.route is Route.EMIT_TASK
    assert d.assignee == "sandcastle"
    assert "/rework" in d.goal and "7" in d.goal


def test_global_task_due_low_emits_task():
    """global_task_due at severity='low' routes to EMIT_TASK."""
    d = handle_event(
        _ev(
            "global_task_due",
            "low",
            {
                "dispatcher_skill": "research",
                "output_sink": "memory",
                "lapse_intervals": 1,
            },
        )
    )
    assert d.route is Route.EMIT_TASK
    assert d.assignee == "sandcastle"
    assert "research" in d.goal


def test_global_task_due_defaults_dispatcher_skill_to_research():
    """A global_task_due payload missing dispatcher_skill defaults to 'research'
    (payload.get(..., 'research')) — the goal still names a concrete skill rather
    than emitting None."""
    d = handle_event(_ev("global_task_due", "low", {"output_sink": "memory", "lapse_intervals": 1}))
    assert d.route is Route.EMIT_TASK
    assert d.goal.startswith("global task: research")
    assert "None" not in d.goal


def test_global_task_due_goal_carries_source_and_body():
    """CRITICAL #2: the EMIT_TASK goal IS the spawned ``claude -p`` agent's
    prompt, so it must carry actionable context — the source row id (traceable,
    and distinct per source) and the task ``body`` (what to actually do) — not
    just the bare skill name. Before the fix the goal was ``"global task:
    research"`` with no source/body, so the agent had nothing to act on."""
    d = handle_event(
        _ev(
            "global_task_due",
            "low",
            {
                "dispatcher_skill": "research",
                "source_id": "src-42",
                "output_sink": "memory",
                "title": "Weekly arxiv sweep",
                "body": "Summarize this week's arxiv on agents.",
                "lapse_intervals": 1,
            },
        )
    )
    assert d.route is Route.EMIT_TASK
    assert "src-42" in d.goal
    assert "Summarize this week's arxiv on agents." in d.goal


def test_global_task_due_goal_unique_per_source():
    """MAJOR #2: two sources with the same dispatcher_skill must not collapse to
    an identical goal string (queue rows would be indistinguishable). The source
    id disambiguates them."""
    base = {"dispatcher_skill": "research", "output_sink": "memory", "body": "x"}
    g1 = handle_event(_ev("global_task_due", "low", {**base, "source_id": "a"})).goal
    g2 = handle_event(_ev("global_task_due", "low", {**base, "source_id": "b"})).goal
    assert g1 != g2


@pytest.mark.parametrize("severity", ["info", "medium", "high", "critical"])
def test_global_task_due_non_low_severity_failsafe_escalates(severity):
    """global_task_due is an enumerated route ONLY at severity='low'. Any other
    severity is an unknown (event_type, severity) pair → fail-safe escalate,
    never a silent EMIT_TASK at the wrong priority (MAJOR #11)."""
    d = handle_event(_ev("global_task_due", severity, {"dispatcher_skill": "research"}))
    assert d.route is Route.ESCALATE


@pytest.mark.parametrize("event_type", ["pr_approved", "pr_merged", "ci_success"])
def test_pipeline_events_are_inline_noop(event_type):
    d = handle_event(_ev(event_type, "info"))
    assert d.route is Route.HANDLE_INLINE
    assert d.noop is True


# -- #1385 AC-B: telemetry events route to inline no-op, any severity -------


@pytest.mark.parametrize(
    "event_type",
    [
        "memory_recall",
        "review_debt_collected",
        "consolidation_run",
        "consolidation_applied",
        "consolidation_rejected",
        "evolve_run",
        "fok_run",
        "memory_migration",
    ],
)
@pytest.mark.parametrize("severity", ["info", "medium", "high", "critical"])
def test_telemetry_events_are_inline_noop_at_any_severity(event_type, severity):
    # consolidation_run fires at both info and high in live traffic — the
    # route must not depend on severity for any telemetry type.
    d = handle_event(_ev(event_type, severity))
    assert d.route is Route.HANDLE_INLINE
    assert d.noop is True


@pytest.mark.parametrize("severity", ["info", "high"])
def test_github_prefixed_events_are_inline_noop(severity):
    d = handle_event(_ev("github.pull_request", severity))
    assert d.route is Route.HANDLE_INLINE
    assert d.noop is True


def test_dispatcher_escalation_is_not_a_telemetry_route():
    # Deliberately excluded (#1385 AC-B) — retired scaffolding with no live
    # producer. Falling through to fail-safe ESCALATE is the correct route.
    assert handle_event(_ev("dispatcher_escalation", "info")).route is Route.ESCALATE


def test_mcp_write_scrubber_disabled_high_escalates():
    """mcp_write_scrubber_disabled at severity=high must escalate to the owner
    with a named reason — the write-scrubber gate being down is a security
    concern that requires human review, not an agent action (#1000)."""
    d = handle_event(_ev("mcp_write_scrubber_disabled", "high"))
    assert d.route is Route.ESCALATE
    assert d.escalated_reason is not None
    assert "scrubber" in d.escalated_reason


def test_unknown_event_type_failsafe_escalates():
    assert handle_event(_ev("totally_unknown", "high")).route is Route.ESCALATE


def test_quota_pressure_high_failsafe_escalates():
    """#1139: telegram-notify-hook (the drain) is retired — quota_pressure's
    only remaining Telegram path is this fail-safe ESCALATE (unenumerated
    event_type, high severity), routed through the notifier in dispatch()."""
    assert handle_event(_ev("quota_pressure", "high")).route is Route.ESCALATE


def test_known_type_unenumerated_severity_failsafe_escalates():
    # ci_failure only routes to emit_task at `high`; any other severity is an
    # unknown (event_type, severity) pair → fail-safe escalate.
    assert handle_event(_ev("ci_failure", "low")).route is Route.ESCALATE
    assert handle_event(_ev("review_negative", "high")).route is Route.ESCALATE


# -- AC4: security_alert is a safety floor the router cannot override -------


@pytest.mark.parametrize("severity", ["critical", "high", "medium", "low", "info"])
def test_security_alert_never_inline_at_any_severity(severity):
    d = handle_event(_ev("security_alert", severity))
    assert d.route is Route.ESCALATE
    assert d.route is not Route.HANDLE_INLINE


# -- AC2: priority = f(severity), strictly monotonic -----------------------


def test_priority_strictly_monotonic_by_severity():
    p = [priority_for(s) for s in ("info", "low", "medium", "high", "critical")]
    assert p == sorted(p)
    assert len(set(p)) == 5  # strictly increasing, no ties


def test_emit_task_priority_tracks_severity():
    assert handle_event(_ev("ci_failure", "high")).priority == priority_for("high")


# -- AC2: idempotency_key dedups re-delivery, re-runs genuinely-new events --


def test_idempotency_key_stable_for_identical_event():
    e = _ev("ci_failure", "high", {"pr": 5, "sha": "abc"})
    assert (
        handle_event(e).idempotency_key
        == handle_event(_ev("ci_failure", "high", {"pr": 5, "sha": "abc"})).idempotency_key
    )


def test_idempotency_key_differs_for_new_payload_state():
    k1 = handle_event(_ev("ci_failure", "high", {"pr": 5, "sha": "abc"})).idempotency_key
    k2 = handle_event(_ev("ci_failure", "high", {"pr": 5, "sha": "def"})).idempotency_key
    assert k1 != k2


def test_idempotency_key_differs_by_event_type():
    k1 = handle_event(_ev("ci_failure", "high", {"pr": 5})).idempotency_key
    k2 = handle_event(_ev("review_negative", "medium", {"pr": 5})).idempotency_key
    assert k1 != k2


# -- AC3: escalate decision carries owner assignee + reason + elevated pri --


def test_escalate_decision_fields():
    d = handle_event(_ev("security_alert", "critical", {"detail": "leaked key"}))
    assert d.route is Route.ESCALATE
    assert d.assignee == "owner"
    assert d.escalated_reason  # non-empty human-readable reason
    # elevated: an escalation outranks a same-severity emit_task
    assert d.priority >= priority_for("critical")


def test_decision_is_frozen():
    d = handle_event(_ev("pr_merged"))
    with pytest.raises(Exception):
        d.route = Route.ESCALATE  # type: ignore[misc]
    assert isinstance(d, Decision)


# ===========================================================================
# #1085 S1-4: Decision.issue_number threaded to dispatch()'s enqueue() calls
# ===========================================================================


def test_review_negative_decision_issue_number_is_none():
    """No current event type carries a genuine issue-target payload — every
    route today leaves issue_number None (#1085 S1-4)."""
    d = handle_event(_ev("review_negative", "medium", {"pr": 7}))
    assert d.issue_number is None


def test_ci_failure_decision_issue_number_is_none():
    d = handle_event(_ev("ci_failure", "high", {"pr": 5}))
    assert d.issue_number is None


def test_dispatch_emit_task_threads_issue_number_to_enqueued_row():
    """A Decision carrying issue_number reaches the task_queue row via
    dispatch()'s enqueue() call — proves the plumbing, not just the default."""
    cli = _FakeClient()
    d = handle_event(_ev("ci_failure", "high", {"pr": 5, "sha": "abc"}))
    d = replace(d, issue_number=1085)
    res = dispatch(d, now=_FRIDAY, client=cli)
    assert res.enqueued is True
    assert res.row["issue_number"] == 1085


def test_dispatch_emit_task_omits_issue_number_when_none():
    """issue_number=None must not land on the row (enqueue()'s conditional —
    matches the NULLs-never-collide CAS semantics, #1085 S1-1/S1-3)."""
    cli = _FakeClient()
    d = handle_event(_ev("ci_failure", "high", {"pr": 5, "sha": "abc"}))
    assert d.issue_number is None
    res = dispatch(d, now=_FRIDAY, client=cli)
    assert res.enqueued is True
    assert "issue_number" not in res.row


def test_dispatch_escalate_threads_issue_number_to_enqueued_row():
    cli = _FakeClient()
    d = handle_event(_ev("security_alert", "critical", {"detail": "leaked key"}))
    d = replace(d, issue_number=1085)
    res = dispatch(d, now=_FRIDAY, client=cli)
    assert res.row is not None
    assert res.row["issue_number"] == 1085


# ===========================================================================
# AC2 side-effect: dispatch(EMIT_TASK) writes a sandcastle row, dedups
# ===========================================================================


def test_dispatch_emit_task_writes_sandcastle_row():
    cli = _FakeClient()
    d = handle_event(_ev("ci_failure", "high", {"pr": 5, "sha": "abc"}))
    res = dispatch(d, now=_FRIDAY, client=cli)
    assert isinstance(res, DispatchResult)
    assert res.enqueued is True
    assert res.row is not None
    assert res.row["assignee"] == "sandcastle"
    assert res.row["priority"] == priority_for("high")
    assert res.row["idempotency_key"] == d.idempotency_key
    assert res.row["status"] == "pending"


def test_dispatch_emit_task_stamps_substrate_worktree():
    """#1121 plan step 7: every EMIT_TASK enqueue is stamped substrate="worktree"
    so drain_tasks can route it onto the new supervisor path (step 8)."""
    cli = _FakeClient()
    d = handle_event(_ev("ci_failure", "high", {"pr": 5, "sha": "abc"}))
    res = dispatch(d, now=_FRIDAY, client=cli)
    assert res.enqueued is True
    assert res.row["substrate"] == "worktree"


def test_dispatch_emit_task_redelivery_dedups():
    cli = _FakeClient()
    e = _ev("ci_failure", "high", {"pr": 5, "sha": "abc"})
    first = dispatch(handle_event(e), now=_FRIDAY, client=cli)
    # Identical re-delivery → same idempotency_key → collision, no second row.
    second = dispatch(handle_event(dict(e)), now=_FRIDAY, client=cli)
    assert first.enqueued is True
    assert second.enqueued is False
    assert second.row is None
    assert len(cli.table("task_queue").rows) == 1


def test_dispatch_emit_task_new_event_reruns():
    cli = _FakeClient()
    first = dispatch(
        handle_event(_ev("ci_failure", "high", {"pr": 5, "sha": "abc"})),
        now=_FRIDAY,
        client=cli,
    )
    # A genuinely-new event for a *different* PR has both a different
    # idempotency_key and a different target pin → re-runs. (Two events on
    # the *same* PR with only a different sha now collide on the #1119
    # target-pin index even though their idempotency_key differs — see
    # test_dispatch_emit_task_same_target_different_key_collides below.)
    second = dispatch(
        handle_event(_ev("ci_failure", "high", {"pr": 6, "sha": "def"})),
        now=_FRIDAY,
        client=cli,
    )
    assert first.enqueued is True and second.enqueued is True
    assert len(cli.table("task_queue").rows) == 2


def test_dispatch_emit_task_same_target_different_key_collides():
    """#1617 plan step 15: the #1119 target-pin partial unique index dedups
    same-PR events even when idempotency_key differs (distinct sha) — a
    target-CAS collision, not an idempotency-key collision."""
    cli = _FakeClient()
    first = dispatch(
        handle_event(_ev("ci_failure", "high", {"pr": 5, "sha": "abc"})),
        now=_FRIDAY,
        client=cli,
    )
    second_decision = handle_event(_ev("ci_failure", "high", {"pr": 5, "sha": "def"}))
    second = dispatch(second_decision, now=_FRIDAY, client=cli)
    assert first.enqueued is True
    assert second_decision.idempotency_key != first.row["idempotency_key"]
    assert second.enqueued is False
    assert len(cli.table("task_queue").rows) == 1


# ===========================================================================
# #1455 AC1: DispatchResult carries blocked_by_task_id (Path B producer)
# ===========================================================================


def test_dispatch_emit_task_sets_blocked_by_task_id():
    """A successful fresh EMIT_TASK enqueue exposes the task id so the drain
    loop can park the event blocked on it (Path B producer, #1455 AC1)."""
    cli = _FakeClient()
    d = handle_event(_ev("ci_failure", "high", {"pr": 5, "sha": "abc"}))
    res = dispatch(d, now=_FRIDAY, client=cli)
    assert res.enqueued is True
    assert res.blocked_by_task_id == str(res.row["id"])


def test_dispatch_emit_task_collision_blocked_by_task_id_is_none():
    """Idempotency collision → no fresh task → nothing to block on (AC1/AC6)."""
    cli = _FakeClient()
    e = _ev("ci_failure", "high", {"pr": 5, "sha": "abc"})
    dispatch(handle_event(e), now=_FRIDAY, client=cli)
    second = dispatch(handle_event(dict(e)), now=_FRIDAY, client=cli)
    assert second.enqueued is False
    assert second.blocked_by_task_id is None


def test_dispatch_escalate_blocked_by_task_id_is_none():
    """ESCALATE keeps notify-then-processed semantics: owner rows never reach
    a terminal state in production, so parking on them would park forever
    (EMIT_TASK-only scope, decision 3997893d)."""
    cli = _FakeClient()
    d = handle_event(_ev("security_alert", "critical", {"detail": "x"}))
    res = dispatch(d, now=_FRIDAY, client=cli)
    assert res.row is not None  # owner row written…
    assert res.blocked_by_task_id is None  # …but the event is not blocked on it


def test_dispatch_handle_inline_blocked_by_task_id_is_none():
    cli = _FakeClient()
    d = handle_event(_ev("memory_recall", "info"))
    assert d.route is Route.HANDLE_INLINE
    res = dispatch(d, now=_FRIDAY, client=cli)
    assert res.blocked_by_task_id is None


# ===========================================================================
# AC3 side-effect: escalate writes owner row + escalated_reason; weekend-aware
# ===========================================================================


def test_dispatch_escalate_writes_owner_row_with_reason():
    cli = _FakeClient()
    d = handle_event(_ev("security_alert", "critical", {"detail": "leaked key"}))
    res = dispatch(d, now=_FRIDAY, client=cli)
    assert res.row is not None
    assert res.row["assignee"] == "owner"
    assert res.row["escalated_reason"]  # persisted on the row
    assert res.row["priority"] >= priority_for("critical")


def test_escalation_notice_critical_pings_any_day():
    for day in (_FRIDAY, _SATURDAY, _SUNDAY, _MONDAY):
        assert escalation_notice("critical", day) is EscalationNotice.TELEGRAM_NOW


def test_escalation_notice_high_pings_any_day():
    """AC1/AC2 (#1392): the immediate-notify floor is >= high, not == critical —
    critical-only made TELEGRAM_NOW practically unreachable (no live producer
    emits critical; escalate_to_human fail-safe events land at high/medium).
    Decision db4495da-4746-43fd-a3c6-755fc24ea0a9."""
    for day in (_FRIDAY, _SATURDAY, _SUNDAY, _MONDAY):
        assert escalation_notice("high", day) is EscalationNotice.TELEGRAM_NOW


def test_escalation_notice_noncritical_weekend_parks_to_monday():
    assert escalation_notice("medium", _SATURDAY) is EscalationNotice.PARK_MONDAY
    assert escalation_notice("low", _SUNDAY) is EscalationNotice.PARK_MONDAY


def test_escalation_notice_noncritical_weekday_sessionstart():
    assert escalation_notice("medium", _FRIDAY) is EscalationNotice.SESSIONSTART
    assert escalation_notice("low", _MONDAY) is EscalationNotice.SESSIONSTART


def test_dispatch_critical_fires_notifier():
    cli = _FakeClient()
    pinged: list[Decision] = []
    d = handle_event(_ev("security_alert", "critical", {"detail": "x"}))
    res = dispatch(d, now=_SATURDAY, client=cli, notifier=pinged.append)
    assert res.notice is EscalationNotice.TELEGRAM_NOW
    assert res.notified is True
    assert pinged == [d]


def test_dispatch_noncritical_weekend_does_not_ping():
    cli = _FakeClient()
    pinged: list[Decision] = []
    # Unknown (event_type, severity) → fail-safe escalate below the
    # >=high immediate-notify floor (AC1/AC2, decision db4495da).
    d = handle_event(_ev("some_unknown_event", "medium"))
    assert d.route is Route.ESCALATE
    res = dispatch(d, now=_SATURDAY, client=cli, notifier=pinged.append)
    assert res.notice is EscalationNotice.PARK_MONDAY
    assert res.notified is False
    assert pinged == []
    # The owner row is still written — work is never lost, only the ping waits.
    assert res.row is not None and res.row["assignee"] == "owner"


def test_dispatch_escalate_notifier_routes_through_safety_gate(monkeypatch: pytest.MonkeyPatch):
    """#1385 review finding: the ESCALATE ping must go through safety.gate(),
    not call the notifier directly — so it's classified + audited like every
    other action-agent side effect.
    """
    cli = _FakeClient()
    gate_calls: list[dict] = []
    real_gate = safety.gate

    def _spy_gate(**kwargs):
        gate_calls.append(kwargs)
        return real_gate(**kwargs)

    monkeypatch.setattr("agents.orchestrator.safety.gate", _spy_gate)

    pinged: list[Decision] = []
    d = handle_event(_ev("security_alert", "critical", {"detail": "x"}))
    res = dispatch(d, now=_SATURDAY, client=cli, notifier=pinged.append)

    assert res.notified is True
    assert pinged == [d]
    assert len(gate_calls) == 1
    call = gate_calls[0]
    assert call["area"] == "messaging"
    assert call["action"] == "notify_owner_escalation"
    assert call["tool_name"] == "telegram_notifier"
    assert safety.classify(call["tool_name"], call["action"], "x", area=call["area"]) == (
        safety.Tier.AUTO
    )


def test_dispatch_notifier_exception_does_not_abort_tick():
    """#1385 AC-D: a raising notifier must not propagate out of dispatch.

    The escalation side effect (owner row) already landed before the notify
    step runs — a Telegram/network failure here must not undo or block that,
    since dispatch executes inside a live wake_driver tick.
    """
    cli = _FakeClient()

    def _boom(_decision: Decision) -> None:
        raise RuntimeError("telegram down")

    d = handle_event(_ev("security_alert", "critical", {"detail": "x"}))
    res = dispatch(d, now=_SATURDAY, client=cli, notifier=_boom)
    assert res.notice is EscalationNotice.TELEGRAM_NOW
    assert res.notified is False
    assert res.row is not None and res.row["assignee"] == "owner"


# ===========================================================================
# AC5: inline tool surface routes through safety.gate (Tier 0 / 1 / 2)
# ===========================================================================


def test_run_inline_tier0_fires_fn():
    ran: list[str] = []
    res = run_inline_tool("audit_event", fn=lambda: ran.append("ran"))
    assert isinstance(res, InlineResult)
    assert res.tier is safety.Tier.AUTO
    assert res.fired is True
    assert ran == ["ran"]
    assert res.queued_owner_row is None


def test_run_inline_unmapped_tool_degrades_to_owner_row():
    cli = _FakeClient()
    ran: list[str] = []
    res = run_inline_tool("mystery_tool", fn=lambda: ran.append("ran"), client=cli)
    assert res.tier is safety.Tier.OWNER_QUEUE
    assert res.fired is False
    assert ran == []  # never auto-run an unvetted tool
    assert res.queued_owner_row is not None
    assert res.queued_owner_row["assignee"] == "owner"


def test_run_inline_tier2_blocks_and_audits():
    ran: list[str] = []
    # A destructive action classifies Tier 2 → gate raises, fn never runs.
    with pytest.raises(safety.GateError):
        run_inline_tool("delete", fn=lambda: ran.append("ran"))
    assert ran == []


# ===========================================================================
# AC-A (#1385): build_production_orchestrator wires handle_event -> dispatch
# ===========================================================================


def test_build_production_orchestrator_routes_event_through_dispatch():
    cli = _FakeClient()
    orch = build_production_orchestrator(client=cli, clock=lambda: _FRIDAY)
    result = orch(_ev("ci_failure", "high", {"pr": 5}))
    assert isinstance(result, DispatchResult)
    assert result.route is Route.EMIT_TASK
    assert result.enqueued is True
    assert result.row is not None
    assert result.row["assignee"] == "sandcastle"


def test_build_production_orchestrator_wires_notifier_for_critical_escalation():
    cli = _FakeClient()
    pinged: list[Decision] = []
    orch = build_production_orchestrator(
        client=cli, notifier=pinged.append, clock=lambda: _SATURDAY
    )
    result = orch(_ev("security_alert", "critical", {"detail": "x"}))
    assert result.notified is True
    assert len(pinged) == 1


def test_build_production_orchestrator_default_clock_and_notifier_do_not_raise():
    cli = _FakeClient()
    orch = build_production_orchestrator(client=cli)
    result = orch(_ev("pr_merged"))
    assert isinstance(result, DispatchResult)
    assert result.route is Route.HANDLE_INLINE


def test_build_production_orchestrator_logs_warning_on_enqueue_collision(
    caplog: pytest.LogCaptureFixture,
):
    """#1455 AC6: a colliding EMIT_TASK enqueue during drain means the event's
    work is already queued elsewhere — the event is NOT parked (drain will
    mark_processed on blocked_by_task_id=None), and the wrapper logs a warning
    carrying the event id + idempotency key for visibility."""
    cli = _FakeClient()
    orch = build_production_orchestrator(client=cli, clock=lambda: _FRIDAY)
    e = {**_ev("ci_failure", "high", {"pr": 5, "sha": "abc"}), "id": "ev-42"}
    first = orch(e)
    assert first.enqueued is True
    with caplog.at_level(logging.WARNING, logger="agents.orchestrator"):
        second = orch(dict(e))
    assert second.enqueued is False
    assert second.blocked_by_task_id is None
    collision_logs = [r for r in caplog.records if "collision" in r.getMessage()]
    assert collision_logs, "expected a warning on the enqueue-collision branch"
    msg = collision_logs[0].getMessage()
    assert "ev-42" in msg
    assert first.row["idempotency_key"] in msg


def test_build_production_orchestrator_no_warning_on_fresh_enqueue(
    caplog: pytest.LogCaptureFixture,
):
    cli = _FakeClient()
    orch = build_production_orchestrator(client=cli, clock=lambda: _FRIDAY)
    with caplog.at_level(logging.WARNING, logger="agents.orchestrator"):
        result = orch({**_ev("ci_failure", "high", {"pr": 5}), "id": "ev-1"})
    assert result.enqueued is True
    assert not [r for r in caplog.records if "collision" in r.getMessage()]


def test_build_production_orchestrator_logs_target_pins_on_target_cas_collision(
    caplog: pytest.LogCaptureFixture,
):
    """#1617 plan step 15: two ci_failure/high events on the same PR with
    *different* idempotency keys (distinct sha) don't dedup on
    idempotency_key at all — they collide on the target-pin partial unique
    index (#1119) instead. enqueue() still returns None via the existing
    APIError/23505 catch, the wrapper still treats it as mark-processed-not-
    parked, and the warning now names the target pins, not just the
    idempotency key, since idempotency_key differs across the two events."""
    cli = _FakeClient()
    orch = build_production_orchestrator(client=cli, clock=lambda: _FRIDAY)
    first_event = {**_ev("ci_failure", "high", {"pr": 5, "sha": "abc"}), "id": "ev-1"}
    second_event = {**_ev("ci_failure", "high", {"pr": 5, "sha": "def"}), "id": "ev-2"}

    first = orch(first_event)
    assert first.enqueued is True
    first_key = first.row["idempotency_key"]

    with caplog.at_level(logging.WARNING, logger="agents.orchestrator"):
        second = orch(second_event)

    second_decision = handle_event(second_event)
    assert second_decision.idempotency_key != first_key, (
        "test premise: the two events must NOT dedup on idempotency_key — "
        "otherwise this isn't exercising the target-CAS collision path"
    )
    assert second.enqueued is False
    collision_logs = [r for r in caplog.records if "collision" in r.getMessage()]
    assert collision_logs, "expected a warning on the target-CAS collision branch"
    msg = collision_logs[0].getMessage()
    assert "ev-2" in msg
    assert second_decision.target_repo is not None
    assert second_decision.target_type is not None
    assert str(second_decision.target_number) in msg
    assert second_decision.target_repo in msg
    assert second_decision.target_type in msg


# ===========================================================================
# #1617 AC1: emit-side target pin population (target_type/target_number/
# target_repo), consumed by the drain-time readiness gate for orchestrator
# rows. Numeric target (PR) -> "pr"; non-numeric/absent -> explicit "none",
# never NULL (NULL is reserved for "emit path forgot to classify").
# ===========================================================================


def test_decision_target_pin_fields_default_none():
    d = handle_event(_ev("pr_merged"))
    assert d.target_type is None
    assert d.target_number is None
    assert d.target_repo is None


def test_ci_failure_numeric_pr_pins_target_type_pr(monkeypatch):
    monkeypatch.delenv("GITHUB_REPO", raising=False)
    event = {
        "event_type": "ci_failure",
        "severity": "high",
        "repo": "Osasuwu/jarvis",
        "payload": {"pr": 5},
    }
    d = handle_event(event)
    assert d.target_type == "pr"
    assert d.target_number == 5
    assert d.target_repo == "Osasuwu/jarvis"


def test_ci_failure_non_numeric_target_pins_target_type_none(monkeypatch):
    monkeypatch.delenv("GITHUB_REPO", raising=False)
    event = {
        "event_type": "ci_failure",
        "severity": "high",
        "repo": "Osasuwu/jarvis",
        "payload": {"workflow": "CI", "branch": "master"},
    }
    d = handle_event(event)
    assert d.target_type == "none"
    assert d.target_number is None
    assert d.target_repo == "Osasuwu/jarvis"


def test_ci_failure_no_repo_on_event_defaults_target_repo_to_own_repo(monkeypatch):
    monkeypatch.delenv("GITHUB_REPO", raising=False)
    d = handle_event(_ev("ci_failure", "high", {"pr": 5}))
    assert d.target_repo == "Osasuwu/jarvis"


def test_ci_failure_target_repo_honors_github_repo_env(monkeypatch):
    monkeypatch.setenv("GITHUB_REPO", "someoperator/jarvis-oss")
    d = handle_event(_ev("ci_failure", "high", {"pr": 5}))
    assert d.target_repo == "someoperator/jarvis-oss"


def test_review_negative_numeric_pr_pins_target_type_pr():
    d = handle_event(_ev("review_negative", "medium", {"pr": 7}))
    assert d.target_type == "pr"
    assert d.target_number == 7


def test_global_task_due_pins_target_type_none():
    d = handle_event(
        _ev(
            "global_task_due",
            "low",
            {"dispatcher_skill": "research", "output_sink": "memory"},
        )
    )
    assert d.target_type == "none"
    assert d.target_number is None


def test_redrive_copies_target_pins_from_payload():
    """A re-drive must carry the ORIGINAL task's target pins forward — not
    reclassify from the terminal event's own (typically target-less) payload."""
    d = handle_event(
        _ev(
            "task_failed",
            "high",
            {
                "pr_evidence": False,
                "attempt": 0,
                "exit_confirmed": True,
                "task_id": "t-1",
                "goal": "/rework #7",
                "target_type": "pr",
                "target_number": 7,
                "target_repo": "Osasuwu/jarvis",
            },
        )
    )
    assert d.route is Route.EMIT_TASK
    assert d.target_type == "pr"
    assert d.target_number == 7
    assert d.target_repo == "Osasuwu/jarvis"


def test_dispatch_emit_task_threads_target_pins_and_origin_to_row():
    cli = _FakeClient()
    d = handle_event(_ev("ci_failure", "high", {"pr": 5}))
    res = dispatch(d, now=_FRIDAY, client=cli)
    assert res.enqueued is True
    assert res.row["target_type"] == "pr"
    assert res.row["target_number"] == 5
    assert res.row["origin"] == "orchestrator"


def test_dispatch_escalate_threads_origin_to_row():
    cli = _FakeClient()
    d = handle_event(_ev("security_alert", "critical", {"detail": "leaked key"}))
    res = dispatch(d, now=_FRIDAY, client=cli)
    assert res.row["origin"] == "orchestrator"


def test_redrive_preserves_dispatch_origin_from_payload():
    """A re-drive of a /dispatch-origin task must re-enqueue with
    origin="dispatch", not fall back to "orchestrator" — otherwise the
    redrive is permanently unable to drain via check_orchestrator_target's
    (currently always-failing) "issue" branch instead of the dispatch rows'
    own check_issue/check_repo gate (#1758 review finding)."""
    d = handle_event(
        _ev(
            "task_failed",
            "high",
            {
                "pr_evidence": False,
                "attempt": 0,
                "exit_confirmed": True,
                "task_id": "t-1",
                "goal": "/dispatch #7",
                "target_type": "issue",
                "target_number": 7,
                "target_repo": "Osasuwu/jarvis",
                "origin": "dispatch",
            },
        )
    )
    assert d.origin == "dispatch"
    cli = _FakeClient()
    res = dispatch(d, now=_FRIDAY, client=cli)
    assert res.row["origin"] == "dispatch"


def test_redrive_defaults_origin_to_orchestrator_when_payload_omits_it():
    """Older/orchestrator-originated terminal events carry no `origin` key —
    the re-drive must still default to "orchestrator", preserving pre-#1758
    behavior for genuine orchestrator-detected retries."""
    d = handle_event(
        _ev(
            "task_failed",
            "high",
            {
                "pr_evidence": False,
                "attempt": 0,
                "exit_confirmed": True,
                "task_id": "t-2",
                "goal": "/rework #7",
                "target_type": "pr",
                "target_number": 7,
                "target_repo": "Osasuwu/jarvis",
            },
        )
    )
    assert d.origin is None
    cli = _FakeClient()
    res = dispatch(d, now=_FRIDAY, client=cli)
    assert res.row["origin"] == "orchestrator"
