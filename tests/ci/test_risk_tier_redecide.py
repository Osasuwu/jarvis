"""Re-deciding `risk-tier` once the code review completes (.github/scripts/risk_tier_redecide.py, #2202).

`risk-tier` is a GitHub Actions job, so nothing but a run of that job can change its check.
When a review completes, the verdict workflow re-runs the latest `risk-tier` job on the
reviewed head unless a run that started after the review already reads its evidence.
These tests drive the real script against the shared fake API; expected values are literals.
"""

import importlib.util
import urllib.error
from pathlib import Path

import pytest
import yaml

from ._github_fake import FakeApi, http_error

_root = next(p for p in Path(__file__).resolve().parents if (p / ".github" / "scripts").is_dir())
_spec = importlib.util.spec_from_file_location(
    "risk_tier_redecide", _root / ".github" / "scripts" / "risk_tier_redecide.py"
)
redecide = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(redecide)

REPO = "o/r"
SHA = "a" * 40
DONE = "2026-11-16T10:00:00Z"  # the review run's completion
RUNS = f"repos/{REPO}/actions/workflows/pr-body-check.yml/runs?head_sha={SHA}"


def _run(id=500, created="2026-11-16T09:00:00Z", status="completed", prs=(7,)):
    return {
        "id": id,
        "created_at": created,
        "status": status,
        "head_sha": SHA,
        "pull_requests": [{"number": n} for n in prs],
    }


def _jobs(*names):
    return {"jobs": [{"id": 77 + i, "name": n} for i, n in enumerate(names)]}


def _api(runs, jobs=None, polls=()):
    """`polls`: what each later read of run 500 answers, in order."""
    later = iter(polls)
    return FakeApi(
        {
            RUNS: {"workflow_runs": list(runs)},
            f"repos/{REPO}/actions/runs/500/jobs": jobs
            or _jobs("require-linked-issue", "risk-tier"),
            f"repos/{REPO}/actions/runs/500": lambda m, p, b: next(later),
        }
    )


def _call(api, **kw):
    kw.setdefault("sleep", lambda s: None)
    return redecide.redecide(api, REPO, 7, SHA, DONE, **kw)


def _posts(api):
    return [p for m, p, _ in api.calls if m == "POST"]


def test_a_run_from_before_the_review_completed_gets_its_risk_tier_job_re_run():
    api = _api([_run()])
    assert _call(api) == (True, "re-ran risk-tier job 78 of run 500 on aaaaaaa")
    assert _posts(api) == [f"repos/{REPO}/actions/jobs/78/rerun"]


def test_the_latest_run_is_the_one_re_run():
    api = _api([_run(id=400, created="2026-11-16T08:00:00Z"), _run()])
    ok, _ = _call(api)
    assert ok is True
    assert _posts(api) == [f"repos/{REPO}/actions/jobs/78/rerun"]


def test_a_run_that_started_after_the_review_completed_is_left_alone():
    api = _api([_run(created="2026-11-16T10:00:01Z", status="in_progress")])
    assert _call(api) == (
        True,
        "risk-tier run 500 started after the review completed; it reads the review's evidence",
    )
    assert _posts(api) == []


def test_a_run_still_in_progress_is_waited_for_then_re_run():
    """A run cannot be re-run before it completes, and one that started before the review
    completed may have read no evidence."""
    api = _api([_run(status="in_progress")], polls=[_run(status="in_progress"), _run()])
    slept = []
    ok, _ = _call(api, sleep=slept.append)
    assert ok is True
    assert slept == [15, 15]
    assert _posts(api) == [f"repos/{REPO}/actions/jobs/78/rerun"]


def test_a_run_that_never_completes_fails_after_the_wait_and_re_runs_nothing():
    api = _api([_run(status="in_progress")], polls=[_run(status="in_progress")] * 100)
    ok, message = _call(api, wait_s=60)
    assert ok is False
    assert message == "risk-tier run 500 did not complete within 60 s: nothing re-run"
    assert _posts(api) == []


def test_no_risk_tier_run_on_the_head_is_nothing_to_re_run():
    api = _api([])
    assert _call(api) == (
        True,
        "no risk-tier run on aaaaaaa yet: the first one reads the review's evidence",
    )


def test_a_run_for_another_pr_on_the_same_head_is_not_re_run():
    api = _api([_run(prs=(8,))])
    ok, _ = _call(api)
    assert ok is True
    assert _posts(api) == []


def test_a_fork_prs_run_lists_no_pr_and_is_still_re_run():
    """A fork's runs carry an empty `pull_requests`; the head SHA binds them."""
    api = _api([_run(prs=())])
    ok, _ = _call(api)
    assert ok is True
    assert _posts(api) == [f"repos/{REPO}/actions/jobs/78/rerun"]


def test_a_run_without_the_risk_tier_job_fails():
    api = _api([_run()], jobs=_jobs("require-linked-issue"))
    assert _call(api) == (False, "run 500 has no risk-tier job: nothing re-run")


def test_a_refused_re_run_propagates():
    """The re-run API refuses a run older than 30 days; the verdict job then fails and
    `code-gate` is not posted, so neither check goes green on an unread raise."""
    api = _api([_run()])
    api.writes = {f"repos/{REPO}/actions/jobs/78/rerun": http_error(403)}
    with pytest.raises(urllib.error.HTTPError):
        _call(api)


# --- the workflow job ---------------------------------------------------------------------

VERDICT = yaml.safe_load(
    (_root / ".github" / "workflows" / "code-gate-verdict.yml").read_text(encoding="utf-8")
)


def test_the_redecide_job_runs_only_when_a_review_completes():
    job = VERDICT["jobs"]["risk-tier-redecide"]
    assert job["needs"] == "resolve"
    assert job["if"] == (
        "github.event_name == 'workflow_run' && needs.resolve.outputs.targets != '[]'"
    )
    (step,) = [s for s in job["steps"] if "run" in s]
    assert step["run"] == "python -I .github/scripts/risk_tier_redecide.py"
    assert step["env"]["REVIEW_COMPLETED_AT"] == "${{ github.event.workflow_run.updated_at }}"
    assert (step["env"]["PR_NUMBER"], step["env"]["HEAD_SHA"]) == (
        "${{ matrix.target.pr_number }}",
        "${{ matrix.target.head_sha }}",
    )


def test_the_redecide_job_alone_holds_actions_write_and_no_app_key():
    job = VERDICT["jobs"]["risk-tier-redecide"]
    assert job["permissions"] == {"actions": "write", "contents": "read"}
    assert "environment" not in job
    assert "GATE_APP_PRIVATE_KEY" not in str(job) and "GATE_TOKEN" not in str(job)


def test_code_gate_is_posted_only_after_risk_tier_is_re_queued():
    """Ordering: a green `code-gate` must not land while `risk-tier` still shows the tier
    decided before the review, or a merge could slip in before the raise is read. A failed
    re-run leaves `code-gate` unposted for this event (fail closed)."""
    verdict = VERDICT["jobs"]["verdict"]
    assert verdict["needs"] == ["resolve", "risk-tier-redecide"]
    assert verdict["if"] == (
        "!cancelled() && needs.resolve.result == 'success'"
        " && needs.resolve.outputs.targets != '[]'"
        " && (needs.risk-tier-redecide.result == 'success'"
        " || needs.risk-tier-redecide.result == 'skipped')"
    )
