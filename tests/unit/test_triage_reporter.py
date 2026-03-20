"""Tests for triage report formatting."""

from jarvis.triage.models import (
    CheckCategory,
    Severity,
    TriageReport,
    TriageViolation,
)
from jarvis.triage.reporter import to_console, to_markdown


def _sample_report() -> TriageReport:
    return TriageReport(
        violations=[
            TriageViolation(
                issue_number=11,
                issue_title="Daily Triage Engine",
                category=CheckCategory.METADATA,
                severity=Severity.ERROR,
                message="Missing required label with prefix 'status:'",
                suggested_action="Add a 'status:*' label to #11.",
            ),
            TriageViolation(
                issue_number=99,
                issue_title="Old task",
                category=CheckCategory.STALENESS,
                severity=Severity.WARNING,
                message="No updates for 21 days.",
                suggested_action="Review #99.",
            ),
        ],
        total_open_issues=15,
        issues_checked=15,
        blocked_count=1,
    )


def test_to_console_contains_header() -> None:
    text = to_console(_sample_report())
    assert "Daily Triage Report" in text


def test_to_console_contains_issue_numbers() -> None:
    text = to_console(_sample_report())
    assert "#11" in text
    assert "#99" in text


def test_to_console_healthy_report() -> None:
    text = to_console(TriageReport())
    assert "healthy" in text.lower()


def test_to_markdown_contains_table() -> None:
    md = to_markdown(_sample_report())
    assert "| Open issues |" in md
    assert "15" in md


def test_to_markdown_healthy() -> None:
    md = to_markdown(TriageReport())
    assert "healthy" in md.lower()
