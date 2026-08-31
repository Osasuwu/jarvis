"""Tests for agents/task_dedup.py's row_issue_number() (#1119)."""

from __future__ import annotations

from agents.task_dedup import row_issue_number


class TestRowIssueNumber:
    def test_prefers_issue_number_column(self) -> None:
        row = {"issue_number": 931, "target_type": "issue", "target_number": 1119}
        assert row_issue_number(row, goal="unrelated goal text") == 931

    def test_falls_back_to_target_number_when_issue_number_absent(self) -> None:
        """#1119: a row enqueued via the structured-pin path alone (no
        issue_number column value) must still resolve for the sibling-dedup
        predicate — target_number is the new pin, issue_number is now the
        deprecated mirror."""
        row = {"target_type": "issue", "target_number": 1119}
        assert row_issue_number(row, goal="unrelated goal text") == 1119

    def test_target_number_ignored_when_target_type_not_issue(self) -> None:
        row = {"target_type": "pr", "target_number": 42}
        assert row_issue_number(row, goal="Implement #931 dispatch dedup") == 931

    def test_falls_back_to_goal_regex_when_no_column_or_pin(self) -> None:
        row: dict = {}
        assert row_issue_number(row, goal="Implement #931 dispatch dedup") == 931

    def test_returns_none_when_nothing_resolves(self) -> None:
        row: dict = {}
        assert row_issue_number(row, goal="no issue reference here") is None
