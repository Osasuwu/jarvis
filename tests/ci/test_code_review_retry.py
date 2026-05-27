"""Meta-test for scripts/code_review_retry.py + code-review.yml retry job (#807).

Two halves:
  - Pure decision/parsing logic in isolation (no gh subprocess).
  - Workflow file wiring: the retry job exists, gates on workflow_run+failure,
    has actions:write, and invokes the script.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

from scripts.code_review_retry import (
    MAX_ATTEMPTS,
    Decision,
    count_failed_attempts,
    decide,
    parse_reset_time_utc,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "code-review.yml"


# -- Decision logic ----------------------------------------------------------

PR = {"number": 123, "headRefName": "feat/foo", "headRefOid": "abc"}


def _run(conclusion: str | None, status: str = "completed") -> dict:
    return {"conclusion": conclusion, "status": status}


class TestDecide:
    def test_no_runs_dispatches(self):
        d = decide([PR], "feat/foo", [])
        assert d.kind == "dispatch"
        assert d.pr_number == 123

    def test_one_prior_failure_still_dispatches(self):
        d = decide([PR], "feat/foo", [_run("failure")])
        assert d.kind == "dispatch"

    def test_below_cap_still_dispatches(self):
        d = decide([PR], "feat/foo", [_run("failure")] * (MAX_ATTEMPTS - 1))
        assert d.kind == "dispatch"

    def test_at_cap_marks_exhausted(self):
        d = decide([PR], "feat/foo", [_run("failure")] * MAX_ATTEMPTS)
        assert d.kind == "exhausted"
        assert d.pr_number == 123

    def test_success_does_not_count_toward_cap(self):
        runs = [_run("success"), _run("failure"), _run("failure")]
        d = decide([PR], "feat/foo", runs)
        assert d.kind == "dispatch"  # 2 failures < cap; success ignored

    def test_skip_when_no_open_pr_for_branch(self):
        d = decide([], "feat/orphan", [_run("failure")])
        assert d.kind == "skip"
        assert d.pr_number is None

    def test_skip_when_branch_doesnt_match_any_open_pr(self):
        d = decide([PR], "feat/other-branch", [_run("failure")])
        assert d.kind == "skip"


class TestCountFailedAttempts:
    @pytest.mark.parametrize("conclusion", ["failure", "cancelled", "timed_out", "action_required"])
    def test_failure_class_conclusions_count(self, conclusion: str):
        assert count_failed_attempts([_run(conclusion)] * 3) == 3

    @pytest.mark.parametrize("conclusion", ["success", "skipped", "neutral", None])
    def test_non_failure_conclusions_dont_count(self, conclusion):
        assert count_failed_attempts([_run(conclusion)] * 5) == 0


# -- Reset-time parsing ------------------------------------------------------


class TestParseResetTimeUtc:
    def test_returns_none_when_no_signature(self):
        now = datetime(2026, 5, 27, 10, 0, tzinfo=timezone.utc)
        assert parse_reset_time_utc("just a generic error", now) is None

    def test_parses_am_signature_later_today(self):
        # The actual error string we captured from a real failed run.
        log = "Claude Code returned an error result: You've hit your session limit · resets 3:40am (UTC)"
        now = datetime(2026, 5, 27, 1, 0, tzinfo=timezone.utc)
        reset = parse_reset_time_utc(log, now)
        assert reset == datetime(2026, 5, 27, 3, 40, tzinfo=timezone.utc)

    def test_parses_pm_signature(self):
        log = "session limit · resets 4:15pm (UTC)"
        now = datetime(2026, 5, 27, 9, 0, tzinfo=timezone.utc)
        reset = parse_reset_time_utc(log, now)
        assert reset == datetime(2026, 5, 27, 16, 15, tzinfo=timezone.utc)

    def test_rolls_to_next_day_when_reset_already_passed(self):
        log = "session limit · resets 3:40am (UTC)"
        now = datetime(2026, 5, 27, 10, 0, tzinfo=timezone.utc)  # past 03:40
        reset = parse_reset_time_utc(log, now)
        assert reset == datetime(2026, 5, 28, 3, 40, tzinfo=timezone.utc)

    def test_parses_24h_signature_without_ampm(self):
        log = "session limit · resets 14:30 (UTC)"
        now = datetime(2026, 5, 27, 9, 0, tzinfo=timezone.utc)
        reset = parse_reset_time_utc(log, now)
        assert reset == datetime(2026, 5, 27, 14, 30, tzinfo=timezone.utc)

    def test_midnight_12am_is_hour_0(self):
        log = "session limit · resets 12:00am (UTC)"
        now = datetime(2026, 5, 27, 23, 30, tzinfo=timezone.utc)
        reset = parse_reset_time_utc(log, now)
        # 12:00am today (00:00) has already passed; rolls to tomorrow 00:00.
        assert reset == datetime(2026, 5, 28, 0, 0, tzinfo=timezone.utc)

    def test_noon_12pm_is_hour_12(self):
        log = "session limit · resets 12:00pm (UTC)"
        now = datetime(2026, 5, 27, 9, 0, tzinfo=timezone.utc)
        reset = parse_reset_time_utc(log, now)
        assert reset == datetime(2026, 5, 27, 12, 0, tzinfo=timezone.utc)

    def test_rejects_garbage_hour(self):
        log = "session limit · resets 25:99 (UTC)"
        now = datetime(2026, 5, 27, 9, 0, tzinfo=timezone.utc)
        assert parse_reset_time_utc(log, now) is None


# -- Workflow wiring ---------------------------------------------------------


@pytest.fixture(scope="module")
def workflow() -> dict:
    return yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))


def _triggers(workflow: dict) -> dict:
    # PyYAML parses bare `on:` as Python True (YAML 1.1 boolean).
    return workflow.get("on") or workflow.get(True)


class TestWorkflowWiring:
    def test_listens_to_its_own_completion(self, workflow):
        on = _triggers(workflow)
        assert "workflow_run" in on, "Retry path requires workflow_run trigger"
        wr = on["workflow_run"]
        assert "Code Review" in wr.get("workflows", []), (
            "Workflow_run trigger must reference its own workflow by name"
        )
        assert "completed" in wr.get("types", [])

    def test_pull_request_and_dispatch_triggers_preserved(self, workflow):
        on = _triggers(workflow)
        assert "pull_request" in on, "Existing pull_request trigger must remain"
        assert "workflow_dispatch" in on, "Manual dispatch entry point must remain"

    def test_review_job_does_not_fire_on_workflow_run(self, workflow):
        review_if = workflow["jobs"]["review"]["if"]
        # The review job's gate must list pull_request and workflow_dispatch,
        # NOT include workflow_run — otherwise the retry path would
        # re-trigger the review job rather than the retry job.
        assert "pull_request" in review_if
        assert "workflow_dispatch" in review_if
        assert "workflow_run" not in review_if

    def test_retry_job_exists_with_correct_gate(self, workflow):
        retry = workflow["jobs"].get("retry")
        assert retry is not None, "Retry job is the whole point of #807"
        gate = retry["if"]
        assert "workflow_run" in gate
        assert "failure" in gate

    def test_retry_job_has_actions_write_permission(self, workflow):
        perms = workflow["jobs"]["retry"]["permissions"]
        assert perms.get("actions") == "write", (
            "Retry job dispatches workflow_dispatch — needs actions:write"
        )
        assert perms.get("pull-requests") == "write", (
            "Retry job posts exhausted-retry PR comment — needs pull-requests:write"
        )

    def test_retry_job_invokes_script(self, workflow):
        steps = workflow["jobs"]["retry"]["steps"]
        invocations = " ".join(s.get("run", "") for s in steps)
        assert "code_review_retry.py" in invocations, (
            "Retry job must invoke scripts/code_review_retry.py"
        )
