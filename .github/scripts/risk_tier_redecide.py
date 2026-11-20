"""Re-decide `risk-tier` on a head whose code review just completed (#2202).

The CI reviewer may raise the risk tier through its evidence (`risk_tier.py`, decision "Three
risk tiers; the final tier is computed from the diff, and the reviewer may only raise it" in
docs/decisions/2026-Q4.md). `risk-tier` is a GitHub Actions job of `pr-body-check.yml`, and
only a run of that job can change its check, so the verdict workflow calls this script on the
review's `workflow_run` before it posts `code-gate`: it re-runs the latest `risk-tier` job on
the reviewed head, unless a run created after the review completed already reads the evidence.

Fail closed: when the job cannot be re-run (none found, a run that does not complete within
the wait, a refused re-run), the script fails, the verdict job does not run, and `code-gate`
is not posted for this event. Until a `risk-tier` run reads the completed review, that check
stays red as "waiting for the code review" (`risk_tier.py`).

Stdlib only, with the shared client `github_client.py` beside this script, loaded by file path.
"""

import datetime
import importlib.util
import os
import sys
import time
from pathlib import Path

RISK_TIER_WORKFLOW = "pr-body-check.yml"
RISK_TIER_JOB = "risk-tier"
MAX_RUN_PAGES = 3
WAIT_S = 600
POLL_S = 15


def _github_client():
    name = "_jarvis_github_client"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(
        name, Path(__file__).resolve().with_name("github_client.py")
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)  # a half-built module must not be handed out next time
        raise
    return module


def _when(stamp):
    return datetime.datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ")


def _for_pr(run, number):
    """A run of this PR: it lists the PR, or lists none (a fork's run; the SHA binds it)."""
    listed = run.get("pull_requests") or []
    return not listed or any(p.get("number") == number for p in listed)


def redecide(api, repo, number, head_sha, review_done_at, *, sleep=time.sleep, wait_s=WAIT_S):
    """`(ok, message)`. Re-runs the latest `risk-tier` job on `head_sha` that was created
    no later than `review_done_at`; a refused API call raises."""
    gh = _github_client()
    runs = [
        run
        for run in gh.paged(
            api,
            f"repos/{repo}/actions/workflows/{RISK_TIER_WORKFLOW}/runs?head_sha={head_sha}",
            key="workflow_runs",
            max_pages=MAX_RUN_PAGES,
        )
        if _for_pr(run, number)
    ]
    if not runs:
        return True, (
            f"no {RISK_TIER_JOB} run on {head_sha[:7]} yet: the first one reads the review's evidence"
        )
    run = max(runs, key=lambda r: (_when(r["created_at"]), r["id"]))
    if _when(run["created_at"]) > _when(review_done_at):
        return True, (
            f"{RISK_TIER_JOB} run {run['id']} started after the review completed; "
            "it reads the review's evidence"
        )
    waited = 0
    while run.get("status") != "completed":  # only a completed run can be re-run
        if waited >= wait_s:
            return False, (
                f"{RISK_TIER_JOB} run {run['id']} did not complete within {wait_s} s: nothing re-run"
            )
        sleep(POLL_S)
        waited += POLL_S
        run = api("GET", f"repos/{repo}/actions/runs/{run['id']}")
    jobs = gh.paged(api, f"repos/{repo}/actions/runs/{run['id']}/jobs?filter=latest", key="jobs")
    job = next((j for j in jobs if j.get("name") == RISK_TIER_JOB), None)
    if job is None:
        return False, f"run {run['id']} has no {RISK_TIER_JOB} job: nothing re-run"
    api("POST", f"repos/{repo}/actions/jobs/{job['id']}/rerun", {}, idempotent=False)
    return True, f"re-ran {RISK_TIER_JOB} job {job['id']} of run {run['id']} on {head_sha[:7]}"


def main(make_client=None):
    gh = _github_client()
    client = (make_client or (lambda t: gh.Client(t, user_agent="risk-tier-redecide")))(
        os.environ["GH_TOKEN"]
    )
    ok, message = redecide(
        client,
        os.environ["GITHUB_REPOSITORY"],
        int(os.environ["PR_NUMBER"]),
        os.environ["HEAD_SHA"],
        os.environ["REVIEW_COMPLETED_AT"],
    )
    print(message if ok else f"::error::{message}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
