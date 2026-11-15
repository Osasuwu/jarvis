"""Fail when a required check has had no result on an open PR's head for too long (#2142).

Runs from `.github/workflows/required-check-heartbeat.yml`. Branch protection waits for every
required check; one that never posts (a workflow that did not trigger, a stuck runner, an app
that is down) leaves the PR pending forever, and nothing on the PR turns red. This probe reads
the required checks from live protection and, for each open PR into the default branch, the
check runs and commit statuses on its head. A required check whose newest result is missing or
unfinished past `STALE_AFTER_MIN` makes the run exit 1; a red scheduled run is the alert
(GitHub notifies the repo's maintainers of failed scheduled runs).

When a check is due:
- no run or status at all: from the head commit's committer date;
- a run still queued or in progress (the newest one by id, so a stuck re-run is not hidden by
  an older result): from that run's `started_at`; a pending status: from its `created_at`.

A check bound to an app counts only that app's check runs, as branch protection does; an
unbound one also counts a commit status of the same name. A PR with merge conflicts is listed
and skipped: GitHub runs no `pull_request` workflow on it, and the conflict is shown on the PR.

Reading no required checks at all exits 2: a heartbeat with nothing to watch is not green.

Stdlib only. The branch object and the shared client are read as in
`branch_protection_drift.py`, loaded from beside this file.
"""

import importlib.util
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

STALE_AFTER_MIN = 60
UNFINISHED_STATUSES = ("pending",)


def _load(name, filename):
    """A script beside this one, shared through `sys.modules` like `github_client` is."""
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(
        name, Path(__file__).resolve().with_name(filename)
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return module


github_client = _load("_jarvis_github_client", "github_client.py")
drift = _load("_jarvis_branch_protection_drift", "branch_protection_drift.py")


class NothingToCheck(Exception):
    """Live protection names no required check."""


def _parse(stamp):
    return datetime.fromisoformat(stamp.replace("Z", "+00:00"))


def _minutes(now, since):
    return int((now - _parse(since)).total_seconds() // 60)


def stale_checks(required, check_runs, statuses, committed_at, now, stale_after_min):
    """[(check, state, minutes due)] for each required check with no result in time.

    `required` maps check name -> bound app id or None; `state` is `no result` or the
    newest run's / status's unfinished state."""
    stale = []
    for name, app_id in required.items():
        runs = [
            r
            for r in check_runs
            if r.get("name") == name
            and (app_id is None or (r.get("app") or {}).get("id") == app_id)
        ]
        sts = [s for s in statuses if s.get("context") == name] if app_id is None else []
        newest_run = max(runs, key=lambda r: r["id"], default=None)
        newest_status = max(sts, key=lambda s: s["id"], default=None)
        if newest_run and newest_run.get("status") == "completed":
            continue
        if newest_status and newest_status.get("state") not in UNFINISHED_STATUSES:
            continue
        if newest_run:
            state, since = newest_run.get("status"), newest_run.get("started_at") or committed_at
        elif newest_status:
            state, since = newest_status["state"], newest_status.get("created_at") or committed_at
        else:
            state, since = "no result", committed_at
        due = _minutes(now, since)
        if due >= stale_after_min:
            stale.append((name, state, due))
    return stale


def scan(api, repo, branch, now, stale_after_min=STALE_AFTER_MIN):
    """(stale lines, info lines) over every open PR into `branch`."""
    required = drift.live_binding(api("GET", f"repos/{repo}/branches/{branch}"))
    if not required:
        raise NothingToCheck(f"no required checks on {repo}@{branch}")
    stale, info = [], []
    for pr in github_client.paged(api, f"repos/{repo}/pulls?state=open&base={branch}"):
        number, sha = pr["number"], pr["head"]["sha"]
        if api("GET", f"repos/{repo}/pulls/{number}").get("mergeable_state") == "dirty":
            info.append(f"#{number} {sha}: merge conflict, checks cannot run")
            continue
        runs = github_client.paged(api, f"repos/{repo}/commits/{sha}/check-runs", key="check_runs")
        statuses = (
            github_client.paged(api, f"repos/{repo}/commits/{sha}/statuses")
            if None in required.values()
            else []
        )
        committed = api("GET", f"repos/{repo}/commits/{sha}")["commit"]["committer"]["date"]
        for name, state, due in stale_checks(
            required, runs, statuses, committed, now, stale_after_min
        ):
            what = "no result" if state == "no result" else f"still {state}"
            stale.append(f"#{number} {sha}: {name} — {what} for {due} min")
    return stale, info


def _make_client(token):
    return github_client.Client(token, user_agent="required-check-heartbeat")


def main(make_client=None, now=None):
    repo = os.environ["GITHUB_REPOSITORY"]
    branch = os.environ["DEFAULT_BRANCH"]
    api = (make_client or _make_client)(os.environ["GH_TOKEN"])
    try:
        stale, info = scan(api, repo, branch, (now or (lambda: datetime.now(timezone.utc)))())
    except NothingToCheck as error:
        print(f"::error::{error}: the heartbeat has nothing to watch", file=sys.stderr)
        return 2
    for line in info:
        print(f"info: {line}")
    for line in stale:
        print(f"::error::{line}")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary and stale:
        with open(summary, "a", encoding="utf-8") as out:
            out.write(f"Required checks with no result after {STALE_AFTER_MIN} min:\n\n")
            out.writelines(f"- {line}\n" for line in stale)
    if not stale:
        print("every required check has a result on every open PR head")
    return 1 if stale else 0


if __name__ == "__main__":
    sys.exit(main())
