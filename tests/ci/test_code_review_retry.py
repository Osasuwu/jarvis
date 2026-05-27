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
RETRY_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "code-review-retry.yml"
REVIEW_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "code-review.yml"


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
def retry_workflow() -> dict:
    return yaml.safe_load(RETRY_WORKFLOW.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def review_workflow() -> dict:
    return yaml.safe_load(REVIEW_WORKFLOW.read_text(encoding="utf-8"))


def _triggers(workflow: dict) -> dict:
    # PyYAML parses bare `on:` as Python True (YAML 1.1 boolean).
    return workflow.get("on") or workflow.get(True)


class TestRetryWorkflowWiring:
    def test_retry_workflow_exists(self):
        assert RETRY_WORKFLOW.exists(), (
            "Retry workflow split out into its own file because GitHub rejects "
            "workflows that declare workflow_run triggers on themselves "
            "(validation failure with 0 jobs)."
        )

    def test_listens_to_code_review_completion(self, retry_workflow):
        on = _triggers(retry_workflow)
        assert "workflow_run" in on
        wr = on["workflow_run"]
        assert "Code Review" in wr.get("workflows", []), (
            "Retry must listen to the Code Review workflow by name"
        )
        assert "completed" in wr.get("types", [])

    def test_retry_job_gates_on_failure(self, retry_workflow):
        retry = retry_workflow["jobs"]["retry"]
        gate = retry["if"]
        assert "conclusion == 'failure'" in gate
        # Default-branch gate prevents dispatching for dispatch-from-main runs
        assert "default_branch" in gate

    def test_retry_job_has_required_permissions(self, retry_workflow):
        perms = retry_workflow["jobs"]["retry"]["permissions"]
        assert perms.get("actions") == "write", (
            "Retry dispatches workflow_dispatch → needs actions:write"
        )
        assert perms.get("pull-requests") == "write", (
            "Retry posts exhausted-retry PR comment → needs pull-requests:write"
        )

    def test_retry_job_invokes_script(self, retry_workflow):
        steps = retry_workflow["jobs"]["retry"]["steps"]
        invocations = " ".join(s.get("run", "") for s in steps)
        assert "code_review_retry.py" in invocations

    def test_retry_job_passes_required_env(self, retry_workflow):
        steps = retry_workflow["jobs"]["retry"]["steps"]
        invoke_step = next(s for s in steps if "code_review_retry.py" in s.get("run", ""))
        env = invoke_step["env"]
        # The script reads these env vars (see scripts/code_review_retry.py:main).
        for key in ("REPO", "HEAD_BRANCH", "HEAD_SHA", "FAILED_RUN_ID", "GH_TOKEN"):
            assert key in env, f"Retry step must pass {key} env to the script"


class TestReviewWorkflowUntouched:
    """The split-out retry workflow must NOT modify code-review.yml triggers."""

    def test_review_workflow_keeps_pull_request_trigger(self, review_workflow):
        on = _triggers(review_workflow)
        assert "pull_request" in on
        assert "workflow_dispatch" in on

    def test_review_workflow_has_no_workflow_run_trigger(self, review_workflow):
        # If this trigger reappears, we're back to the validation-failure
        # scenario where GitHub rejects self-referencing workflow_run.
        on = _triggers(review_workflow)
        assert "workflow_run" not in on, (
            "code-review.yml must not self-reference via workflow_run — "
            "use code-review-retry.yml instead."
        )
