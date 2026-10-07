"""Guard for the concurrency group in .github/workflows/agent-dispatch.yml.

#1936: the workflow starts on every ``issues: labeled`` event and narrows to
the ``agent:dispatch`` label with a job-level ``if``. Its concurrency group
used to be keyed on the issue number alone. Workflow-level concurrency is
resolved when the run is queued, before any job ``if``, so every label event
on an issue joined the group:

* a label added while a worker was running queued a run that cancelled the
  worker (``cancel-in-progress: true``) and then skipped its own job;
* an ``agent:dispatch`` applied in one call with other labels could be
  cancelled as ``pending`` by a sibling event — a dispatch lost with no run
  to show for it.

Neither errors. The measured trace was 53 ``cancelled`` runs out of 223, every
one a non-dispatch label event cancelled by a sibling from the same label
burst. The fix makes the group key depend on the label: dispatch events share
one group, every other event gets a group unique to its own run.

#2005 (D15, F7) widened the shared group from per-issue to per-repo and moved
to ``queue: max`` with no ``cancel-in-progress``: the default ``queue: single``
cancels the older pending run, so a batch of dispatches would lose its middle
run with no artifact.

The invariant pinned here is the one the workflow has to hold, stated without
reference to how the key is spelled: **a run joins the dispatch group if and
only if its intake job runs** (the worker is gated on intake's output). The tests evaluate the expressions actually
written in the workflow file (``evaluate`` below covers the subset of GitHub's
expression syntax they use), so a rewrite that keeps the behaviour passes and
one that drops the label from the key fails.

Convention: docs/reference/ci-guard-meta-tests.md (#326) covers PR-blocking
``paths:``-filtered workflows; this workflow fires on ``issues: labeled`` and
is out of that scope. Same one-workflow-many-narrow-guards shape as
test_agent_dispatch_automerge_guard.py and test_agent_dispatch_max_turns_guard.py.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "agent-dispatch.yml"

DISPATCH_LABEL = "agent:dispatch"
OTHER_LABELS = ["status:ready", "priority:medium", "bug", "area:infrastructure"]

# The key this guard exists to keep out of the workflow.
PRE_1936_GROUP = "agent-dispatch-issue-${{ github.event.issue.number }}"

_TOKEN = re.compile(
    r"""
    \s*(?:
        (?P<string>'(?:[^']|'')*')
      | (?P<number>\d+)
      | (?P<op>&&|\|\||==|!=|!|\(|\)|,)
      | (?P<name>[A-Za-z_][A-Za-z0-9_.-]*)
    )
    """,
    re.VERBOSE,
)


def _gh_format(template: str, *args: object) -> str:
    for i, arg in enumerate(args):
        template = template.replace("{%d}" % i, str(arg))
    return template


def _evaluate_expression(expr: str, context: dict[str, object]) -> object:
    """Evaluate one GitHub Actions expression (the text inside ``${{ }}``).

    Covers string/number literals, dotted context lookups, ``&& || == != !``,
    parentheses and ``format()``. ``&&``/``||`` return an operand rather than a
    boolean in both GitHub's language and Python's, which is what makes the
    ``cond && a || b`` idiom translate directly. Anything outside the subset
    fails loudly: extend this function, don't route around it.
    """
    out: list[str] = []
    pos = 0
    expr = expr.strip()
    while pos < len(expr):
        m = _TOKEN.match(expr, pos)
        if not m:
            pytest.fail(f"unsupported expression syntax at {expr[pos:]!r}")
        pos = m.end()
        if m.group("string"):
            out.append(repr(m.group("string")[1:-1].replace("''", "'")))
        elif m.group("number"):
            out.append(m.group("number"))
        elif m.group("op"):
            out.append({"&&": "and", "||": "or", "!": "not"}.get(m.group("op"), m.group("op")))
        elif m.group("name") == "format":
            out.append("format")
        else:
            name = m.group("name")
            if name not in context:
                pytest.fail(f"expression reads {name!r}, which this guard does not model")
            out.append(repr(context[name]))
    return eval(" ".join(out), {"__builtins__": {}, "format": _gh_format})


def evaluate(value: object, context: dict[str, object]) -> object:
    """Render a workflow value the way Actions does.

    A value that is exactly one ``${{ }}`` keeps its type (needed for the
    boolean ``cancel-in-progress``); otherwise each ``${{ }}`` is interpolated
    into the surrounding text.
    """
    if not isinstance(value, str):
        return value
    whole = re.fullmatch(r"\s*\$\{\{(.*)\}\}\s*", value, re.DOTALL)
    if whole and "${{" not in whole.group(1):
        return _evaluate_expression(whole.group(1), context)
    return re.sub(
        r"\$\{\{(.*?)\}\}",
        lambda m: str(_evaluate_expression(m.group(1), context)),
        value,
        flags=re.DOTALL,
    )


def event(label: str, issue: int, run_id: int) -> dict[str, object]:
    return {
        "github.event.label.name": label,
        "github.event.issue.number": issue,
        "github.repository": "Osasuwu/jarvis",
        "github.run_id": run_id,
    }


@pytest.fixture(scope="module")
def workflow() -> dict:
    return yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def concurrency(workflow: dict) -> dict:
    block = workflow.get("concurrency")
    assert isinstance(block, dict), "agent-dispatch.yml must declare a concurrency group"
    return block


def group_of(concurrency: dict, ctx: dict[str, object]) -> str:
    return str(evaluate(concurrency["group"], ctx))


class TestDispatchRunsShareOneGroupPerRepo:
    def test_relabel_lands_in_the_same_group(self, concurrency):
        # The documented retry: remove `agent:dispatch`, add it again. The
        # second run must find the first one in its group to queue behind it.
        first = group_of(concurrency, event(DISPATCH_LABEL, issue=1936, run_id=100))
        second = group_of(concurrency, event(DISPATCH_LABEL, issue=1936, run_id=200))
        assert first == second

    def test_pending_dispatches_queue_instead_of_cancelling(self, concurrency):
        # `queue: single` (the default) cancels the older pending run; `queue: max`
        # keeps them all. `cancel-in-progress: true` is a validation error beside it.
        assert concurrency.get("queue") == "max"
        assert "cancel-in-progress" not in concurrency

    def test_different_issues_share_the_repo_group(self, concurrency):
        a = group_of(concurrency, event(DISPATCH_LABEL, issue=180, run_id=100))
        b = group_of(concurrency, event(DISPATCH_LABEL, issue=1806, run_id=200))
        assert a == b


class TestOtherLabelsCannotTouchAWorker:
    @pytest.mark.parametrize("label", OTHER_LABELS)
    def test_other_label_is_outside_the_worker_group(self, concurrency, label):
        worker = group_of(concurrency, event(DISPATCH_LABEL, issue=1936, run_id=100))
        other = group_of(concurrency, event(label, issue=1936, run_id=200))
        assert other != worker, (
            f"a {label!r} event on the same issue joins the worker's concurrency group: "
            "it would cancel the in-flight worker and then skip its own job (#1936)"
        )

    def test_label_burst_siblings_do_not_share_a_group(self, concurrency):
        # Issue creation applies several labels in the same second; each is its
        # own run. Sharing a group is what produced the 53 cancelled runs.
        groups = [
            group_of(concurrency, event(label, issue=1936, run_id=300 + i))
            for i, label in enumerate(OTHER_LABELS)
        ]
        assert len(set(groups)) == len(groups)

    def test_throwaway_group_never_collides_with_a_worker_group(self, concurrency):
        # A run id that happens to equal an issue number must not alias it.
        worker = group_of(concurrency, event(DISPATCH_LABEL, issue=1936, run_id=100))
        other = group_of(concurrency, event("bug", issue=7, run_id=1936))
        assert other != worker


class TestGroupAndJobConditionAgree:
    @pytest.mark.parametrize("label", [DISPATCH_LABEL, *OTHER_LABELS])
    def test_run_joins_worker_group_iff_intake_job_runs(self, workflow, concurrency, label):
        # The label literal lives in two places (the intake job `if` and the
        # group key). If they drift, either intake runs unguarded or a skipped
        # run holds the queue.
        ctx = event(label, issue=1936, run_id=200)
        worker_runs = bool(_evaluate_expression(str(workflow["jobs"]["intake"]["if"]), ctx))
        worker_group = group_of(concurrency, event(DISPATCH_LABEL, issue=1936, run_id=100))
        assert (group_of(concurrency, ctx) == worker_group) is worker_runs

    def test_worker_runs_only_after_intake_passes(self, workflow):
        worker = workflow["jobs"]["worker"]
        assert worker["needs"] == "intake"
        assert worker["if"] == "needs.intake.outputs.pass == 'true'"

    @pytest.mark.parametrize("job", ["intake", "worker", "publish"])
    def test_job_declares_no_group_of_its_own(self, workflow, job):
        # A second, job-level group keyed on the issue would bring the same
        # bug back through a side door.
        assert "concurrency" not in workflow["jobs"][job]


class TestGuardDetectsTheOriginalBug:
    def test_issue_only_key_fails_the_isolation_check(self):
        # A guard that is green because its evaluator is vacuous is the failure
        # mode it exists to prevent: the pre-#1936 key must read as broken.
        old = {"group": PRE_1936_GROUP}
        worker = group_of(old, event(DISPATCH_LABEL, issue=1936, run_id=100))
        other = group_of(old, event("status:ready", issue=1936, run_id=200))
        assert other == worker
