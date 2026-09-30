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
import yaml

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


def test_other_labels_do_not_trigger():
    red, _ = evaluate([], [], ["priority:high", "area:infrastructure"])
    assert not red


def test_label_and_request_both_present_still_red():
    red, reason = evaluate(["bob"], [], [LABEL_NAME])
    assert red
    assert reason == "review-requested"


# --- Config dimension: assert against the parsed workflow, not raw file text.
# The file's comments, step script and log lines all repeat the event and label
# names, so a raw-text search stays green after the trigger itself is removed.


def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))


def _triggers() -> dict:
    doc = _workflow()
    # PyYAML (YAML 1.1) parses the bare key `on` as boolean True.
    return doc["on"] if "on" in doc else doc[True]


def test_workflow_script_compares_against_the_label_name():
    scripts = [
        step.get("with", {}).get("script", "")
        for step in _workflow()["jobs"]["waiting-human-review"]["steps"]
    ]
    assert any(f"'{LABEL_NAME}'" in script for script in scripts), (
        f"no step script references the label as the string literal '{LABEL_NAME}'"
    )


def test_workflow_yaml_triggers_on_required_events():
    """#1892 AC2: settles without a re-run needed by hand."""
    triggers = _triggers()
    pr_types = triggers["pull_request"]["types"]
    missing = [
        event
        for event in (
            "opened",
            "synchronize",
            "ready_for_review",
            "review_requested",
            "review_request_removed",
        )
        if event not in pr_types
    ]
    assert not missing, f"missing pull_request trigger type(s): {missing}"
    assert "submitted" in triggers["pull_request_review"]["types"], (
        "missing pull_request_review 'submitted' trigger (review submitted)"
    )


def test_workflow_yaml_triggers_on_label_toggle():
    """#1892 AC2/AC4: the solo-developer path is carried by the label alone, so
    toggling it must itself re-run the check — otherwise a label add/remove
    with no other PR event leaves a stale status until an unrelated re-run,
    breaking AC2's "settles without a re-run needed by hand" promise for that
    path (plan-review tiebreak finding, planner run 1892-planrun-20260924)."""
    pr_types = _triggers()["pull_request"]["types"]
    missing = [event for event in ("labeled", "unlabeled") if event not in pr_types]
    assert not missing, f"missing pull_request trigger type(s): {missing}"


def test_workflow_job_id_matches_check_name():
    """#1892 AC5: the check name must match what #1893's branch-protection ruleset
    will reference, exactly — the job id IS the check name (no jobs.<id>.name
    override), same pattern as require-linked-issue in pr-body-check.yml."""
    jobs = _workflow()["jobs"]
    assert "waiting-human-review" in jobs, "job id must be 'waiting-human-review'"
    assert "name" not in jobs["waiting-human-review"], (
        "a jobs.<id>.name override renames the check the ruleset requires"
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
