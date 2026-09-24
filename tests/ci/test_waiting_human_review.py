"""Meta-test for .github/workflows/waiting-human-review.yml (#1892).

Reimplements the workflow's decision rule in Python and asserts the check
reports red exactly when a human look is owed:

  - A pending reviewer or team request     -> red
  - The `waiting-human-review` label,      -> red (solo-developer path: a
    with no request pending                   review cannot be requested from
                                               oneself, so the label carries
                                               the same hold)
  - Neither present                        -> green

Convention from docs/reference/ci-guard-meta-tests.md (logic dimension):
mirror the guard's decision rule in Python and exercise the scenarios it
claims to handle. This workflow carries no `paths:` filter (it fires on
every PR unconditionally), so the config-dimension convention guard
(tests/ci/test_guard_test_convention.py) does not require this file — it
exists because the escape/precedence logic is non-trivial enough to drift
silently otherwise, same rationale as test_pr_body_check_guard.py.
"""

from __future__ import annotations

from pathlib import Path

import pytest

WORKFLOW_PATH = (
    Path(__file__).resolve().parents[2] / ".github" / "workflows" / "waiting-human-review.yml"
)

LABEL_NAME = "waiting-human-review"


def evaluate(
    requested_reviewers: list[str], requested_teams: list[str], labels: list[str]
) -> tuple[bool, str]:
    """Mirror the workflow's decision rule. Returns (is_red, reason)."""
    if requested_reviewers or requested_teams:
        return True, "review-requested"
    if LABEL_NAME in labels:
        return True, "label"
    return False, "clear"


def test_pending_reviewer_request_is_red():
    red, reason = evaluate(["alice"], [], [])
    assert red
    assert reason == "review-requested"


def test_pending_team_request_is_red():
    red, reason = evaluate([], ["core-team"], [])
    assert red
    assert reason == "review-requested"


def test_no_request_no_label_is_green():
    red, _ = evaluate([], [], [])
    assert not red


def test_label_with_no_request_is_red():
    """#1892 AC4: the solo-developer path — a label of the same name."""
    red, reason = evaluate([], [], [LABEL_NAME])
    assert red
    assert reason == "label"


def test_request_removed_is_green():
    """review_request_removed: the reviewer no longer appears in the pending list."""
    red, _ = evaluate([], [], [])
    assert not red


def test_review_submitted_clears_request():
    """review_submitted: GitHub clears requested_reviewers for that user once their
    review posts, and the workflow re-fetches PR state on the event — so a
    submitted review with no other reviewer still pending reads green."""
    red, _ = evaluate([], [], [])
    assert not red


def test_other_labels_do_not_trigger():
    red, _ = evaluate([], [], ["priority:high", "area:infrastructure"])
    assert not red


def test_label_and_request_both_present_still_red():
    red, reason = evaluate(["bob"], [], [LABEL_NAME])
    assert red
    assert reason == "review-requested"


def test_workflow_file_exists():
    assert WORKFLOW_PATH.exists(), "waiting-human-review.yml is missing"


def test_workflow_yaml_references_label_name():
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert LABEL_NAME in text, "workflow no longer references the waiting-human-review label"


def test_workflow_yaml_triggers_on_required_events():
    """#1892 AC2: settles without a re-run needed by hand."""
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    for event in (
        "opened",
        "synchronize",
        "ready_for_review",
        "review_requested",
        "review_request_removed",
    ):
        assert event in text, f"missing pull_request trigger type: {event}"
    assert "pull_request_review" in text, "missing pull_request_review trigger (review submitted)"
    assert "submitted" in text, "missing 'submitted' review type trigger"


def test_workflow_yaml_triggers_on_label_toggle():
    """#1892 AC2/AC4: the solo-developer path is carried by the label alone, so
    toggling it must itself re-run the check — otherwise a label add/remove
    with no other PR event leaves a stale status until an unrelated re-run,
    breaking AC2's "settles without a re-run needed by hand" promise for that
    path (plan-review tiebreak finding, planner run 1892-planrun-20260924)."""
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    for event in ("labeled", "unlabeled"):
        assert event in text, f"missing pull_request trigger type: {event}"


def test_workflow_job_id_matches_check_name():
    """#1892 AC5: the check name must match what #1893's branch-protection ruleset
    will reference, exactly — the job id IS the check name (no jobs.<id>.name
    override), same pattern as require-linked-issue in pr-body-check.yml."""
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "waiting-human-review:" in text, "job id must be 'waiting-human-review'"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
