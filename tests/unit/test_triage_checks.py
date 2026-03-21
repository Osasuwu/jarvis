"""Tests for individual triage checks."""

from datetime import UTC, datetime, timedelta

from jarvis.triage.checks import (
    check_blocked,
    check_hierarchy,
    check_metadata,
    check_staleness,
)
from jarvis.triage.models import CheckCategory, IssueSnapshot, Severity


def _make_issue(**overrides) -> IssueSnapshot:  # type: ignore[no-untyped-def]
    defaults = {
        "number": 1,
        "title": "Test issue",
        "labels": ["task", "status:ready", "priority:medium", "area:core-agent"],
        "milestone": "P2 PM+TechLead MVP",
        "state": "OPEN",
        "is_epic": False,
        "parent_number": 5,
        "children_numbers": [],
        "updated_at": datetime.now(tz=UTC).isoformat(),
        "created_at": datetime.now(tz=UTC).isoformat(),
        "assignee": None,
    }
    defaults.update(overrides)
    return IssueSnapshot(**defaults)


# -- check_metadata ----------------------------------------------------------


def test_metadata_all_labels_present() -> None:
    issue = _make_issue()
    violations = check_metadata([issue])
    assert violations == []


def test_metadata_missing_status_label() -> None:
    issue = _make_issue(labels=["task", "priority:medium", "area:core-agent"])
    violations = check_metadata([issue])
    assert len(violations) == 1
    assert violations[0].category == CheckCategory.METADATA
    assert "status:" in violations[0].message


def test_metadata_missing_multiple_labels() -> None:
    issue = _make_issue(labels=["task"])
    violations = check_metadata([issue])
    assert len(violations) == 3  # status, priority, area all missing


def test_metadata_skips_epics() -> None:
    issue = _make_issue(is_epic=True, labels=["epic"])
    violations = check_metadata([issue])
    assert violations == []


# -- check_hierarchy ---------------------------------------------------------


def test_hierarchy_with_parent() -> None:
    issue = _make_issue(parent_number=5)
    violations = check_hierarchy([issue])
    assert violations == []


def test_hierarchy_missing_parent() -> None:
    issue = _make_issue(parent_number=None)
    violations = check_hierarchy([issue])
    assert len(violations) == 1
    assert violations[0].category == CheckCategory.HIERARCHY
    assert violations[0].severity == Severity.WARNING


def test_hierarchy_critical_hotfix_allowed() -> None:
    issue = _make_issue(
        parent_number=None,
        labels=["task", "priority:critical", "status:ready", "area:core-agent"],
    )
    violations = check_hierarchy([issue])
    assert violations == []


def test_hierarchy_skips_epics() -> None:
    issue = _make_issue(is_epic=True, parent_number=None)
    violations = check_hierarchy([issue])
    assert violations == []


# -- check_blocked -----------------------------------------------------------


def test_blocked_issue_escalated() -> None:
    issue = _make_issue(
        labels=["task", "status:blocked", "priority:high", "area:core-agent"],
    )
    violations = check_blocked([issue])
    assert len(violations) == 1
    assert violations[0].severity == Severity.ERROR
    assert violations[0].category == CheckCategory.BLOCKED


def test_non_blocked_issue_ok() -> None:
    issue = _make_issue()
    violations = check_blocked([issue])
    assert violations == []


# -- check_staleness ---------------------------------------------------------


def test_stale_issue_flagged() -> None:
    old_date = (datetime.now(tz=UTC) - timedelta(days=20)).isoformat()
    issue = _make_issue(updated_at=old_date)
    violations = check_staleness([issue], stale_days=14)
    assert len(violations) == 1
    assert violations[0].category == CheckCategory.STALENESS


def test_recent_issue_ok() -> None:
    issue = _make_issue()
    violations = check_staleness([issue], stale_days=14)
    assert violations == []


def test_stale_skips_blocked() -> None:
    old_date = (datetime.now(tz=UTC) - timedelta(days=20)).isoformat()
    issue = _make_issue(
        updated_at=old_date,
        labels=["task", "status:blocked", "priority:medium", "area:core-agent"],
    )
    violations = check_staleness([issue], stale_days=14)
    assert violations == []


def test_stale_skips_epics() -> None:
    old_date = (datetime.now(tz=UTC) - timedelta(days=20)).isoformat()
    issue = _make_issue(is_epic=True, updated_at=old_date)
    violations = check_staleness([issue], stale_days=14)
    assert violations == []
