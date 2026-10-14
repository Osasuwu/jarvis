"""Guard for the concurrency group in .github/workflows/code-review.yml.

#2044: the workflow starts on ``pull_request`` ``edited`` as well as on pushes,
and narrows ``edited`` to base-branch changes with a job-level ``if``. Its
concurrency group used to be keyed on the PR number alone, with
``cancel-in-progress: true``. Workflow-level concurrency is resolved when the
run is queued, before any job ``if``, so a title or body edit queued a run that
cancelled the review in flight and then skipped its own job. The cancelled
review uploaded no evidence and ``code-gate`` failed with evidence-none until
the next push. ``/implement`` edits the PR body after CI as a matter of course,
so this was hit on ordinary runs (2026-10-08, 2026-10-13). #1936 was the same
class in lane.yml; the fix is the same: a run whose job will be skipped gets a
group unique to its own run.

The invariant pinned here: **a run joins the PR's review group if and only if
its review job runs**, and a new head still supersedes the review of the old
one. The tests evaluate the expressions written in the workflow file
(``_gh_expr``), so a rewrite that keeps the behaviour passes and one that lets a
body edit back into the group fails.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from ._gh_expr import evaluate, evaluate_expression

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "code-review.yml"

# The key this guard exists to keep out of the workflow.
PRE_2044_GROUP = "code-review-${{ github.event.pull_request.number || inputs.pr_number }}"

# Every `pull_request` type the workflow triggers on other than `edited`, read from the
# file, so a type added later is covered without editing this guard. PyYAML parses the
# bare key `on` as the boolean True.
_TYPES = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))[True]["pull_request"]["types"]
PUSH_ACTIONS = [t for t in _TYPES if t != "edited"]
BASE_CHANGE = {"ref": {"from": "release"}}


def pr_event(action: str, pr: int, run_id: int, changes_base: object = None) -> dict[str, object]:
    return {
        "github.event_name": "pull_request",
        "github.event.action": action,
        "github.event.changes.base": changes_base,
        "github.event.pull_request.number": pr,
        "inputs.pr_number": None,
        "github.run_id": run_id,
    }


def dispatch_event(pr: int, run_id: int) -> dict[str, object]:
    return {
        "github.event_name": "workflow_dispatch",
        "github.event.action": None,
        "github.event.changes.base": None,
        "github.event.pull_request.number": None,
        "inputs.pr_number": str(pr),
        "github.run_id": run_id,
    }


@pytest.fixture(scope="module")
def workflow() -> dict:
    return yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def concurrency(workflow: dict) -> dict:
    block = workflow.get("concurrency")
    assert isinstance(block, dict), "code-review.yml must declare a concurrency group"
    return block


def group_of(concurrency: dict, ctx: dict[str, object]) -> str:
    return str(evaluate(concurrency["group"], ctx))


class TestBodyEditLeavesTheReviewAlone:
    def test_body_edit_is_outside_the_review_group(self, concurrency):
        review = group_of(concurrency, pr_event("synchronize", pr=2044, run_id=100))
        edit = group_of(concurrency, pr_event("edited", pr=2044, run_id=200))
        assert edit != review, (
            "a title/body edit joins the review's concurrency group: it cancels the "
            "review in flight and then skips its own job, so code-gate fails (#2044)"
        )

    def test_edit_bursts_do_not_share_a_group(self, concurrency):
        # Two edits in quick succession are two runs; neither may cancel the other's
        # slot or alias a review group.
        a = group_of(concurrency, pr_event("edited", pr=2044, run_id=300))
        b = group_of(concurrency, pr_event("edited", pr=2044, run_id=301))
        assert a != b

    def test_edit_group_never_collides_with_a_review_group(self, concurrency):
        # A run id equal to some PR number must not alias that PR's group.
        review = group_of(concurrency, pr_event("synchronize", pr=2044, run_id=100))
        edit = group_of(concurrency, pr_event("edited", pr=7, run_id=2044))
        assert edit != review


class TestNewHeadSupersedesTheReview:
    def test_a_push_starts_a_review(self):
        # The parametrized cases below read the trigger list; without `synchronize`
        # a new head would not be reviewed at all, and they would not notice.
        assert "synchronize" in PUSH_ACTIONS

    @pytest.mark.parametrize("action", PUSH_ACTIONS)
    def test_review_events_share_the_pr_group(self, concurrency, action):
        first = group_of(concurrency, pr_event("opened", pr=2044, run_id=100))
        later = group_of(concurrency, pr_event(action, pr=2044, run_id=200))
        assert later == first

    def test_base_change_supersedes_the_review(self, concurrency):
        # A base change alters what is under review, so it must cancel like a push.
        review = group_of(concurrency, pr_event("synchronize", pr=2044, run_id=100))
        rebase = group_of(
            concurrency, pr_event("edited", pr=2044, run_id=200, changes_base=BASE_CHANGE)
        )
        assert rebase == review

    def test_dispatch_supersedes_the_review_of_its_pr(self, concurrency):
        review = group_of(concurrency, pr_event("synchronize", pr=2044, run_id=100))
        dispatch = group_of(concurrency, dispatch_event(pr=2044, run_id=200))
        assert dispatch == review

    def test_different_prs_do_not_share_a_group(self, concurrency):
        a = group_of(concurrency, pr_event("synchronize", pr=180, run_id=100))
        b = group_of(concurrency, pr_event("synchronize", pr=1806, run_id=200))
        assert a != b

    def test_superseded_review_is_cancelled(self, concurrency):
        assert concurrency["cancel-in-progress"] is True


class TestGroupAndJobConditionAgree:
    @pytest.mark.parametrize(
        "ctx",
        [
            *(pr_event(action, pr=2044, run_id=200) for action in PUSH_ACTIONS),
            pr_event("edited", pr=2044, run_id=200),
            pr_event("edited", pr=2044, run_id=200, changes_base=BASE_CHANGE),
            dispatch_event(pr=2044, run_id=200),
        ],
        ids=[*PUSH_ACTIONS, "edited-body", "edited-base", "dispatch"],
    )
    def test_run_joins_review_group_iff_review_job_runs(self, workflow, concurrency, ctx):
        # The `edited` narrowing lives in two places (the job `if` and the group
        # key). If they drift, either a skipped run cancels the review again or a
        # base change stops superseding the stale one.
        review_runs = bool(evaluate_expression(str(workflow["jobs"]["review"]["if"]), ctx))
        review_group = group_of(concurrency, pr_event("synchronize", pr=2044, run_id=100))
        assert (group_of(concurrency, ctx) == review_group) is review_runs

    def test_job_declares_no_group_of_its_own(self, workflow):
        # A job-level group keyed on the PR would bring the bug back through a side door.
        assert "concurrency" not in workflow["jobs"]["review"]


class TestGuardDetectsTheOriginalBug:
    def test_pr_only_key_fails_the_isolation_check(self):
        # A guard that is green because its evaluator is vacuous is the failure
        # mode it exists to prevent: the pre-#2044 key must read as broken.
        old = {"group": PRE_2044_GROUP}
        review = group_of(old, pr_event("synchronize", pr=2044, run_id=100))
        edit = group_of(old, pr_event("edited", pr=2044, run_id=200))
        assert edit == review
