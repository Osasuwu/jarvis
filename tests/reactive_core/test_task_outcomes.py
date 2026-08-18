"""Unit tests for agents/task_outcomes.py (#1605 — task_dispatch decomposition 1/7).

Pure extraction from agents/task_dispatch.py — same behavior, new home. These
tests pin the payload shapes and PR-URL resolution semantics that used to live
inline as ``_record_skip_outcome`` / ``_record_completion_outcome`` /
``_resolve_pr_url``.
"""

from __future__ import annotations

from unittest import mock

from agents.task_outcomes import (
    record_completion_outcome,
    record_skip_outcome,
    resolve_pr_url,
)


class TestRecordSkipOutcome:
    def test_writes_task_outcomes_row_with_dispatch_dedup_tags(self) -> None:
        fake_client = mock.MagicMock()
        with mock.patch("agents.supabase_client.get_client", return_value=fake_client):
            record_skip_outcome(
                {
                    "task_id": "t0",
                    "issue_number": 931,
                    "goal": "/task-implement #931",
                    "pointer": "live task_queue row r1 already targets #931",
                }
            )
        fake_client.table.assert_called_once_with("task_outcomes")
        payload = fake_client.table.return_value.insert.call_args.args[0]
        assert payload["task_type"] == "autonomous"
        assert payload["outcome_status"] == "unknown"
        assert payload["pattern_tags"] == ["dispatch-dedup", "skip", "autonomous"]
        assert payload["source_provenance"] == "sandcastle:task_dispatch-dedup"
        assert payload["issue_url"] == "https://github.com/Osasuwu/jarvis/issues/931"
        fake_client.table.return_value.insert.return_value.execute.assert_called_once()

    def test_no_issue_number_omits_issue_url(self) -> None:
        fake_client = mock.MagicMock()
        with mock.patch("agents.supabase_client.get_client", return_value=fake_client):
            record_skip_outcome({"task_id": "t0", "goal": "g", "pointer": "p"})
        payload = fake_client.table.return_value.insert.call_args.args[0]
        assert payload["issue_url"] is None


class TestRecordCompletionOutcome:
    def test_writes_task_outcomes_row_with_subagent_tags(self) -> None:
        fake_client = mock.MagicMock()
        with mock.patch("agents.supabase_client.get_client", return_value=fake_client):
            record_completion_outcome(
                {
                    "task_id": "t0",
                    "goal": "/task-implement #42",
                    "issue_number": 42,
                    "pr_url": "https://github.com/Osasuwu/jarvis/pull/99",
                }
            )
        fake_client.table.assert_called_once_with("task_outcomes")
        payload = fake_client.table.return_value.insert.call_args.args[0]
        assert payload["task_type"] == "autonomous"
        assert payload["outcome_status"] == "pending"
        assert payload["pr_url"] == "https://github.com/Osasuwu/jarvis/pull/99"
        assert payload["pattern_tags"] == ["subagent", "headless", "task-implement"]
        assert payload["source_provenance"] == "sandcastle:task_dispatch-completion"
        assert payload["issue_url"] == "https://github.com/Osasuwu/jarvis/issues/42"


class TestResolvePrUrl:
    def test_no_client_returns_none(self) -> None:
        assert resolve_pr_url("t0", "/rework #42", client=None) is None

    def test_rework_shape_resolves_via_pull_by_number(self) -> None:
        client = mock.MagicMock()
        client.get_pull_by_number.return_value = {"html_url": "https://github.com/x/y/pull/42"}
        result = resolve_pr_url("t0", "/rework #42", client=client)
        client.get_pull_by_number.assert_called_once_with(42)
        assert result == "https://github.com/x/y/pull/42"

    def test_fresh_shape_resolves_via_head_branch(self) -> None:
        client = mock.MagicMock()
        client.get_pull_by_head_branch.return_value = {"html_url": "https://github.com/x/y/pull/7"}
        result = resolve_pr_url("t0", "do the thing (branch=feat/7-x)", client=client)
        client.get_pull_by_head_branch.assert_called_once_with("feat/7-x")
        assert result == "https://github.com/x/y/pull/7"

    def test_fresh_shape_falls_back_to_task_branch_name(self) -> None:
        client = mock.MagicMock()
        client.get_pull_by_head_branch.return_value = None
        result = resolve_pr_url("t0", "do the thing", client=client)
        client.get_pull_by_head_branch.assert_called_once_with("task/t0")
        assert result is None

    def test_empty_shape_returns_none_without_calling_client(self) -> None:
        client = mock.MagicMock()
        assert resolve_pr_url("t0", "", client=client) is None
        client.get_pull_by_number.assert_not_called()
        client.get_pull_by_head_branch.assert_not_called()

    def test_client_raise_is_swallowed(self) -> None:
        client = mock.MagicMock()
        client.get_pull_by_head_branch.side_effect = RuntimeError("network blip")
        assert resolve_pr_url("t0", "do the thing", client=client) is None

    def test_no_pr_found_returns_none(self) -> None:
        client = mock.MagicMock()
        client.get_pull_by_number.return_value = None
        assert resolve_pr_url("t0", "/rework #42", client=client) is None
