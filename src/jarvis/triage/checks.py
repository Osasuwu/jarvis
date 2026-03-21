"""Individual triage check functions.

Each check inspects a list of IssueSnapshots and returns violations.
Checks follow the rules defined in .github/github-process-runbook.md:
- Every task/bug needs status, priority, and area labels.
- Every task/bug needs parent linkage (except priority:critical hotfixes).
- Blocked items must have a next action documented.
- Issues older than 14 days with no update may be stale.
"""

from __future__ import annotations

from datetime import UTC, datetime

from jarvis.triage.models import (
    CheckCategory,
    IssueSnapshot,
    Severity,
    TriageViolation,
)

REQUIRED_LABEL_PREFIXES = ("status:", "priority:", "area:")


def check_metadata(issues: list[IssueSnapshot]) -> list[TriageViolation]:
    """Check that every non-epic issue has required labels."""
    violations: list[TriageViolation] = []

    for issue in issues:
        if issue.is_epic:
            continue

        labels_lower = [lb.lower() for lb in issue.labels]

        for prefix in REQUIRED_LABEL_PREFIXES:
            has = any(lb.startswith(prefix) for lb in labels_lower)
            if not has:
                violations.append(
                    TriageViolation(
                        issue_number=issue.number,
                        issue_title=issue.title,
                        category=CheckCategory.METADATA,
                        severity=Severity.ERROR,
                        message=f"Missing required label with prefix '{prefix}'",
                        suggested_action=f"Add a '{prefix}*' label to #{issue.number}.",
                    )
                )

    return violations


def check_hierarchy(issues: list[IssueSnapshot]) -> list[TriageViolation]:
    """Check parent linkage for tasks/bugs.

    Hotfixes (priority:critical without a parent) are allowed.
    """
    violations: list[TriageViolation] = []

    for issue in issues:
        if issue.is_epic:
            continue

        is_critical = "priority:critical" in issue.labels
        if issue.parent_number is None and not is_critical:
            violations.append(
                TriageViolation(
                    issue_number=issue.number,
                    issue_title=issue.title,
                    category=CheckCategory.HIERARCHY,
                    severity=Severity.WARNING,
                    message="Task has no parent epic linkage.",
                    suggested_action=(
                        f"Link #{issue.number} to a parent epic via GitHub sub-issues, "
                        "or mark priority:critical if this is a standalone hotfix."
                    ),
                )
            )

    return violations


def check_blocked(issues: list[IssueSnapshot]) -> list[TriageViolation]:
    """Identify blocked issues and escalate them with suggested next action."""
    violations: list[TriageViolation] = []

    for issue in issues:
        if "status:blocked" not in issue.labels:
            continue

        violations.append(
            TriageViolation(
                issue_number=issue.number,
                issue_title=issue.title,
                category=CheckCategory.BLOCKED,
                severity=Severity.ERROR,
                message="Issue is blocked — requires supervisor attention.",
                suggested_action=(
                    f"Review #{issue.number} blockers, resolve or re-prioritize. "
                    "Ensure the issue body documents what is blocking progress."
                ),
            )
        )

    return violations


def check_staleness(
    issues: list[IssueSnapshot],
    stale_days: int = 14,
) -> list[TriageViolation]:
    """Flag issues that have had no updates for *stale_days*."""
    violations: list[TriageViolation] = []
    now = datetime.now(tz=UTC)

    for issue in issues:
        if issue.is_epic:
            continue

        # Skip issues that are already blocked (handled by check_blocked)
        if "status:blocked" in issue.labels:
            continue

        try:
            updated = datetime.fromisoformat(issue.updated_at.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            continue

        age_days = (now - updated).days
        if age_days >= stale_days:
            violations.append(
                TriageViolation(
                    issue_number=issue.number,
                    issue_title=issue.title,
                    category=CheckCategory.STALENESS,
                    severity=Severity.WARNING,
                    message=f"No updates for {age_days} days.",
                    suggested_action=(
                        f"Review #{issue.number}: update status, close if done, "
                        "or mark blocked with a note."
                    ),
                )
            )

    return violations
