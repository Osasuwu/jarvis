"""Tests for triage data models."""

from jarvis.triage.models import (
    CheckCategory,
    Severity,
    TriageReport,
    TriageViolation,
)


def test_severity_values() -> None:
    assert Severity.ERROR.value == "error"
    assert Severity.WARNING.value == "warning"
    assert Severity.INFO.value == "info"


def test_check_category_values() -> None:
    assert CheckCategory.METADATA.value == "metadata"
    assert CheckCategory.BLOCKED.value == "blocked"
    assert CheckCategory.STALENESS.value == "staleness"
    assert CheckCategory.HIERARCHY.value == "hierarchy"


def test_triage_violation_creation() -> None:
    v = TriageViolation(
        issue_number=42,
        issue_title="Test issue",
        category=CheckCategory.METADATA,
        severity=Severity.ERROR,
        message="Missing label",
        suggested_action="Add label",
    )
    assert v.issue_number == 42
    assert v.category == CheckCategory.METADATA


def test_triage_report_empty() -> None:
    report = TriageReport()
    assert report.error_count == 0
    assert report.warning_count == 0
    assert report.is_healthy is True


def test_triage_report_with_errors() -> None:
    report = TriageReport(
        violations=[
            TriageViolation(
                issue_number=1,
                issue_title="A",
                category=CheckCategory.METADATA,
                severity=Severity.ERROR,
                message="err",
                suggested_action="fix",
            ),
            TriageViolation(
                issue_number=2,
                issue_title="B",
                category=CheckCategory.STALENESS,
                severity=Severity.WARNING,
                message="stale",
                suggested_action="review",
            ),
        ],
        total_open_issues=5,
        issues_checked=5,
    )
    assert report.error_count == 1
    assert report.warning_count == 1
    assert report.is_healthy is False
