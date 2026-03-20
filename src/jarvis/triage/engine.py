"""Triage engine — orchestrates checks and produces a TriageReport.

The engine fetches issue data from GitHub via the ``gh`` CLI (no token
management required — ``gh`` uses the authenticated session) and runs
every registered check against the snapshot.
"""

from __future__ import annotations

import json
import logging
import subprocess
from typing import Any

from jarvis.triage.checks import (
    check_blocked,
    check_hierarchy,
    check_metadata,
    check_staleness,
)
from jarvis.triage.models import IssueSnapshot, TriageReport

logger = logging.getLogger(__name__)


class TriageEngine:
    """Run daily triage checks against the current repository."""

    def __init__(self, stale_days: int = 14) -> None:
        self.stale_days = stale_days

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> TriageReport:
        """Execute all triage checks and return an aggregated report."""
        issues = self._fetch_issues()

        report = TriageReport(
            total_open_issues=len(issues),
            issues_checked=len(issues),
            blocked_count=sum(1 for i in issues if "status:blocked" in i.labels),
        )

        report.violations.extend(check_metadata(issues))
        report.violations.extend(check_hierarchy(issues))
        report.violations.extend(check_blocked(issues))
        report.violations.extend(check_staleness(issues, stale_days=self.stale_days))

        logger.info(
            "Triage completed: %d issues, %d violations (%d errors, %d warnings)",
            report.total_open_issues,
            len(report.violations),
            report.error_count,
            report.warning_count,
        )
        return report

    # ------------------------------------------------------------------
    # Data fetching
    # ------------------------------------------------------------------

    def _fetch_issues(self) -> list[IssueSnapshot]:
        """Fetch open issues using ``gh issue list``."""
        raw = self._gh_json(
            [
                "gh",
                "issue",
                "list",
                "--state",
                "open",
                "--json",
                "number,title,labels,milestone,state,assignees,updatedAt,createdAt,body",
                "--limit",
                "200",
            ]
        )

        snapshots: list[IssueSnapshot] = []
        for item in raw:
            snapshots.append(self._parse_issue(item))
        return snapshots

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_issue(item: dict[str, Any]) -> IssueSnapshot:
        labels = [lb["name"] for lb in item.get("labels", [])]
        milestone = (item.get("milestone") or {}).get("title")
        assignees = item.get("assignees", [])
        assignee = assignees[0]["login"] if assignees else None
        body = item.get("body", "") or ""

        is_epic = "epic" in labels
        parent_number = TriageEngine._extract_parent(body)
        children = TriageEngine._extract_children(body) if is_epic else []

        return IssueSnapshot(
            number=item["number"],
            title=item["title"],
            labels=labels,
            milestone=milestone,
            state=item["state"],
            is_epic=is_epic,
            parent_number=parent_number,
            children_numbers=children,
            updated_at=item.get("updatedAt", ""),
            created_at=item.get("createdAt", ""),
            assignee=assignee,
        )

    @staticmethod
    def _extract_parent(body: str) -> int | None:
        """Extract ``Parent: #NNN`` from issue body."""
        for line in body.splitlines():
            stripped = line.strip().lower()
            if stripped.startswith("parent:"):
                rest = stripped.split("parent:")[-1].strip()
                rest = rest.lstrip("#").strip()
                try:
                    return int(rest.split()[0])
                except (ValueError, IndexError):
                    pass
        return None

    @staticmethod
    def _extract_children(body: str) -> list[int]:
        """Extract child issue numbers from ``- [ ] #NNN`` lines."""
        import contextlib

        children: list[int] = []
        for line in body.splitlines():
            stripped = line.strip()
            if stripped.startswith("- ["):
                # e.g. "- [ ] #11 Daily Triage"
                parts = stripped.split("#")
                for part in parts[1:]:
                    token = part.strip().split()[0] if part.strip() else ""
                    with contextlib.suppress(ValueError):
                        children.append(int(token))
        return children

    # ------------------------------------------------------------------
    # Shell helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _gh_json(cmd: list[str]) -> list[dict[str, Any]]:
        """Run a ``gh`` command that returns JSON and parse the output."""
        try:
            result = subprocess.run(  # noqa: S603
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                logger.error("gh command failed: %s", result.stderr.strip())
                return []
            return json.loads(result.stdout)  # type: ignore[no-any-return]
        except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError) as exc:
            logger.error("Failed to run gh: %s", exc)
            return []
