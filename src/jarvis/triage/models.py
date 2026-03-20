"""Data models for triage results."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Severity(StrEnum):
    """Triage finding severity."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class CheckCategory(StrEnum):
    """Category of triage check."""

    METADATA = "metadata"
    BLOCKED = "blocked"
    STALENESS = "staleness"
    HIERARCHY = "hierarchy"


@dataclass
class TriageViolation:
    """A single triage finding for an issue."""

    issue_number: int
    issue_title: str
    category: CheckCategory
    severity: Severity
    message: str
    suggested_action: str


@dataclass
class IssueSnapshot:
    """Minimal issue data fetched from GitHub for triage checks."""

    number: int
    title: str
    labels: list[str]
    milestone: str | None
    state: str
    is_epic: bool
    parent_number: int | None
    children_numbers: list[int]
    updated_at: str
    created_at: str
    assignee: str | None


@dataclass
class TriageReport:
    """Aggregated triage result."""

    violations: list[TriageViolation] = field(default_factory=list)
    total_open_issues: int = 0
    issues_checked: int = 0
    blocked_count: int = 0

    @property
    def error_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == Severity.ERROR)

    @property
    def warning_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == Severity.WARNING)

    @property
    def is_healthy(self) -> bool:
        return self.error_count == 0
