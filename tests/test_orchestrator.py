"""Tests for the deterministic event router (issue #744).

The router is a pure function of one ``events``-table row. No live model:
every assertion here pins a fixed (event_type, severity) input to its route.
"""

from __future__ import annotations

import pytest

from agents.orchestrator import (
    Decision,
    Route,
    handle_event,
    priority_for,
)


def _ev(event_type: str, severity: str = "info", payload: dict | None = None) -> dict:
    return {
        "event_type": event_type,
        "severity": severity,
        "payload": payload or {},
    }


# -- AC1: deterministic route table ----------------------------------------


def test_security_alert_critical_escalates():
    assert handle_event(_ev("security_alert", "critical")).route is Route.ESCALATE


def test_ci_failure_high_emits_task():
    d = handle_event(_ev("ci_failure", "high", {"pr": 5}))
    assert d.route is Route.EMIT_TASK
    assert d.assignee == "sandcastle"


def test_review_negative_medium_emits_rework():
    d = handle_event(_ev("review_negative", "medium", {"pr": 7}))
    assert d.route is Route.EMIT_TASK
    assert d.assignee == "sandcastle"
    assert "/rework" in d.goal and "7" in d.goal


@pytest.mark.parametrize("event_type", ["pr_approved", "pr_merged", "ci_success"])
def test_pipeline_events_are_inline_noop(event_type):
    d = handle_event(_ev(event_type, "info"))
    assert d.route is Route.HANDLE_INLINE
    assert d.noop is True


def test_unknown_event_type_failsafe_escalates():
    assert handle_event(_ev("totally_unknown", "high")).route is Route.ESCALATE


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
