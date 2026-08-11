"""Reactive retry for `.github/workflows/code-review.yml` (#807).

Fires from the workflow's own `workflow_run` trigger when a run completes with
conclusion=failure. Re-dispatches the same PR's review, with two guards:

  1. **Retry cap** — skip after MAX_ATTEMPTS failed runs on the same head SHA.
     Prevents infinite loops on permanent failures (plugin bug, malformed PR).

  2. **Quota-aware delay** — Claude Max session limits include a reset time in
     the error message (`You've hit your session limit · resets 3:40am (UTC)`).
     If the failed run's log carries that signature, sleep until reset + 60s
     before re-dispatching. Otherwise retry immediately (other transient
     failures: runner setup, plugin hiccup, GitHub API blip).

Also logs a `failure_signature` classification (`classify_failure_signature`,
#1325 Option C') on every code path — quota-reset / permission-denied /
blocking-finding / verdict-inflight-race / plugin-install-failure /
review-never-posted / no-log-available / unknown (last two added #1331).
Two of these now feed the dispatch decision itself (#1514):

  3. **Blocking-finding skip** — the "Verify review verdict" step failed
     because a genuine blocking finding was posted for this exact commit
     (structured findings-block or prose severity-heading path). No rerun
     changes that outcome, so `decide()` skips unconditionally instead of
     burning the retry cap and posting a misleading "auto-retry exhausted"
     comment over a gate that did its job correctly.

  4. **In-flight-review wait** — the step failed closed on LINEAGE_INFLIGHT
     (#1434): the real review for this SHA is still running in a separate
     workflow run (a race with, e.g., a merge-train autobase push). Rerunning
     immediately just re-hits the same race, so `main()` polls the in-flight
     run id(s) (bounded by `VERDICT_INFLIGHT_MAX_WAIT_SEC`) before rerunning,
     instead of exhausting all attempts minutes before the real review posts.

Other signatures remain diagnostic only and exist to give a follow-up
investigation something to grep for instead of raw Action logs.

Env contract:
  GH_TOKEN       — gh CLI auth (provided by Actions; a GitHub App installation
                   token as of #1325 Option B — see code-review-retry.yml)
  REPO           — owner/name
  HEAD_BRANCH    — branch of the failed run (from workflow_run event)
  HEAD_SHA       — head SHA of the failed run
  FAILED_RUN_ID  — id of the failed run — reused as the rerun target (#1325
                   Option A: `gh run rerun <id> --failed` reruns this SAME
                   run in place instead of firing a fresh dispatch)
  RUN_ATTEMPT    — github.event.workflow_run.run_attempt; drives the retry
                   cap directly instead of counting runs-list rows (#1325)

The pure functions (`decide`, `parse_reset_time_utc`, `classify_failure_signature`)
are covered by `tests/ci/test_code_review_retry.py`.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone

MAX_ATTEMPTS = 4  # counts the triggering run; net retries = MAX_ATTEMPTS - 1 = 3
RESET_BUFFER_SEC = 60
MAX_SLEEP_SEC = 6 * 60 * 60  # 6h — Claude Max rolling window is ~5h, leave headroom

# Pattern observed in claude-code-action SDK failures, e.g.
# "Claude Code returned an error result: You've hit your session limit · resets 3:40am (UTC)"
_RESET_RE = re.compile(
    r"session limit\s*[·\-]\s*resets\s+(\d{1,2}):(\d{2})\s*(am|pm)?\s*\(UTC\)",
    re.IGNORECASE,
)

# #1325 Option C': the retry mechanism has a historically 0% observed success
# rate — before this, a failed retry left no trace of *why* a rerun didn't
# help. GitHub App / GITHUB_TOKEN permission errors surface in gh CLI /
# Actions logs in a couple of recognizable shapes; a rerun can't fix a
# permission error (Option B addresses the App-token half of that, but a
# misconfigured App installation would still show up here).
_PERMISSION_DENIED_RE = re.compile(
    r"resource not accessible by integration|bad credentials|HTTP 40[13]",
    re.IGNORECASE,
)

# #1514: two more failure classes the retrier can now tell apart instead of
# treating every "Verify review verdict" failure identically.
#
# Class A — a genuine blocking verdict was already posted for this exact
# commit (structured findings-block path or the prose severity-heading path,
# both in code-review.yml's "Verify review verdict" step). Rerunning hits the
# same unchanged commit and the same finding every time — no retry could ever
# succeed, so retrying is pure noise on top of a gate that did its job.
_BLOCKING_FINDING_RE = re.compile(
    r"blocking finding\(s\)|blocking severity sections",
    re.IGNORECASE,
)

# Class B — the verdict-guard fail-closed on LINEAGE_INFLIGHT (#1434): a
# review over this PR's own commits is still running in a SEPARATE workflow
# run. Rerunning immediately just re-hits the same race; waiting for that run
# to finish first lets the rerun pick up its freshly posted comment instead.
_VERDICT_INFLIGHT_RE = re.compile(
    r"code-review run\(s\) over this PR's commits are still running",
    re.IGNORECASE,
)
_INFLIGHT_RUN_IDS_RE = re.compile(
    r"still running \(run id\(s\): ([^)]*)\)",
    re.IGNORECASE,
)

# #1331: production validation of the retry mechanism (PRs #1518/#1519/#1522,
# 2026-08-11) surfaced two more shapes that were falling into "unknown" —
# both stem from the same incident (the code-review Action's plugin
# bootstrap step failed because its marketplace pin resolved to a commit SHA
# no longer present in the jarvis-fork-plugins repo), but a rerun of the SAME
# failed run (#1325 Option A) never cleared it — all 3 PRs hit
# decision=exhausted before a fresh, out-of-band commit finally forced a new
# `pull_request` run that succeeded. Diagnostic only, same as the other
# classes below the dispatch-affecting two above.
_PLUGIN_INSTALL_RE = re.compile(
    r"Failed to install plugin ['\"]code-review|not found in upstream origin",
    re.IGNORECASE,
)

# The verdict-guard's own fail-closed message (#1228) when every review
# attempt over this PR's commits so far died before posting a verdict — the
# cascade symptom of whatever made the upstream code-review run(s) fail
# (often _PLUGIN_INSTALL_RE above, but not necessarily).
_REVIEW_NEVER_POSTED_RE = re.compile(
    r"[Ee]very review attempt died before it could post",
)

VERDICT_INFLIGHT_POLL_INTERVAL_SEC = 20
VERDICT_INFLIGHT_MAX_WAIT_SEC = 15 * 60  # comfortably above the review's ~10min runtime


@dataclass(frozen=True)
class Decision:
    kind: str  # "dispatch" | "skip" | "exhausted"
    reason: str
    pr_number: int | None = None


def decide(
    open_prs: list[dict],
    head_branch: str,
    head_sha: str,
    run_attempt: int,
    max_attempts: int = MAX_ATTEMPTS,
    failure_signature: str | None = None,
) -> Decision:
    pr = next((p for p in open_prs if p.get("headRefName") == head_branch), None)
    if pr is None:
        return Decision("skip", f"no open PR for branch {head_branch}")
    if pr.get("headRefOid") != head_sha:
        return Decision(
            "skip",
            f"PR head moved past {head_sha[:8]} (now {str(pr.get('headRefOid'))[:8]}) — stale retry",
            pr_number=pr["number"],
        )
    # #1514 class A: a real blocking verdict already exists for this exact
    # commit — no rerun changes that outcome, so skip unconditionally rather
    # than burning through the attempt cap. This is "skip", not "exhausted":
    # the mechanism didn't fail, the review worked and correctly blocked, so
    # no misleading "auto-retry exhausted" warning should post either.
    if failure_signature == "blocking-finding":
        return Decision(
            "skip",
            "blocking finding already posted for this commit — retry cannot change the verdict",
            pr_number=pr["number"],
        )
    if run_attempt >= max_attempts:
        return Decision(
            "exhausted",
            f"run_attempt {run_attempt} >= cap {max_attempts}",
            pr_number=pr["number"],
        )
    return Decision(
        "dispatch",
        f"attempt {run_attempt}/{max_attempts}",
        pr_number=pr["number"],
    )


def parse_reset_time_utc(log_text: str, now: datetime) -> datetime | None:
    """Find the *next* quota-reset UTC datetime in a failed run's log, or None."""
    m = _RESET_RE.search(log_text)
    if not m:
        return None
    hour, minute, ampm = int(m.group(1)), int(m.group(2)), m.group(3)
    if ampm:
        ampm = ampm.lower()
        # am/pm only valid for 12-hour clock (1–12); 13:00am/pm is nonsense.
        if not (1 <= hour <= 12):
            return None
        if ampm == "pm" and hour != 12:
            hour += 12
        if ampm == "am" and hour == 12:
            hour = 0
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        # Reset time has already passed (log-fetch latency or near-boundary).
        # Return None so the caller retries immediately rather than sleeping ~24h.
        return None
    return target


def classify_failure_signature(log_text: str) -> str:
    """Classify a failed run's log into a diagnostic bucket (#1325 Option C').

    Purely observational — does not affect the dispatch decision. Logged
    alongside `decision=...` so a run of failed retries builds up a signal on
    *why* the mechanism has historically shown a 0% observed success rate,
    without requiring manual log archaeology after the fact.
    """
    if not log_text:
        return "no-log-available"
    if _RESET_RE.search(log_text):
        return "quota-reset"
    if _PERMISSION_DENIED_RE.search(log_text):
        return "permission-denied"
    if _BLOCKING_FINDING_RE.search(log_text):
        return "blocking-finding"
    if _VERDICT_INFLIGHT_RE.search(log_text):
        return "verdict-inflight-race"
    if _PLUGIN_INSTALL_RE.search(log_text):
        return "plugin-install-failure"
    if _REVIEW_NEVER_POSTED_RE.search(log_text):
        return "review-never-posted"
    return "unknown"


def extract_inflight_run_ids(log_text: str) -> list[str]:
    """Pull the in-flight review run id(s) out of a LINEAGE_INFLIGHT log line.

    Matches the exact message code-review.yml's "Verify review verdict" step
    emits (#1434): "...still running (run id(s): 123, 456)." Returns [] if the
    signature line isn't present or carries no ids — callers treat that as
    "nothing to wait on" and fall through to the normal dispatch path.
    """
    m = _INFLIGHT_RUN_IDS_RE.search(log_text)
    if not m:
        return []
    return [run_id.strip() for run_id in m.group(1).split(",") if run_id.strip()]


def _gh(*args: str) -> str:
    return subprocess.check_output(["gh", *args], text=True)


def _fetch_failed_log(repo: str, run_id: str) -> str:
    try:
        return subprocess.check_output(
            ["gh", "run", "view", run_id, "--repo", repo, "--log-failed"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        return ""


def _wait_for_inflight_runs(
    repo: str,
    run_ids: list[str],
    max_wait_sec: int,
    poll_interval_sec: int = VERDICT_INFLIGHT_POLL_INTERVAL_SEC,
) -> float:
    """Poll the given run ids until each reaches status=completed or the
    bound elapses (#1514 class B). Returns elapsed wait in seconds.

    Rerunning the failed verdict-guard step while the REAL review run is
    still executing elsewhere just re-hits the same LINEAGE_INFLIGHT race
    (#1434) — PR #1476 exhausted all 4 attempts in ~4 minutes, a minute
    before the genuine review posted its verdict. Waiting here first lets
    the rerun below land after that run's comment exists.
    """
    start = time.monotonic()
    pending = set(run_ids)
    while pending and (time.monotonic() - start) < max_wait_sec:
        for run_id in list(pending):
            try:
                state = json.loads(_gh("run", "view", run_id, "--repo", repo, "--json", "status"))
            except subprocess.CalledProcessError:
                # Run vanished/inaccessible — nothing more to wait on for it.
                pending.discard(run_id)
                continue
            if state.get("status") == "completed":
                pending.discard(run_id)
        if pending:
            time.sleep(poll_interval_sec)
    return time.monotonic() - start


def _dispatch(repo: str, run_id: str) -> None:
    # #1325 Option A: rerun the SAME run in place instead of a fresh
    # `gh workflow run` dispatch. A fresh dispatch creates a new run (and a
    # new `review` check-run) alongside the earlier failing one, and the
    # stale failure is never cleared — mergeStateStatus stays BLOCKED even
    # after the retry succeeds (#1325 Finding 2). Rerunning in place updates
    # the one check-run's conclusion instead of shadowing it with a second.
    subprocess.check_call(
        [
            "gh",
            "run",
            "rerun",
            run_id,
            "--repo",
            repo,
            "--failed",
        ]
    )


def _post_exhausted_comment(repo: str, pr_number: int, head_sha: str, run_id: str) -> None:
    body = (
        f"WARNING: Claude code-review auto-retry exhausted after {MAX_ATTEMPTS} "
        f"failed attempts on `{head_sha[:8]}`.\n\n"
        f"Last failed run: https://github.com/{repo}/actions/runs/{run_id}\n\n"
        f"Re-run manually once resolved:\n"
        f"```\n"
        f"gh run rerun {run_id} --repo {repo} --failed\n"
        f"```"
    )
    subprocess.check_call(
        [
            "gh",
            "pr",
            "comment",
            str(pr_number),
            "--repo",
            repo,
            "--body",
            body,
        ]
    )


def main() -> int:
    repo = os.environ["REPO"]
    head_branch = os.environ["HEAD_BRANCH"]
    head_sha = os.environ["HEAD_SHA"]
    failed_run_id = os.environ.get("FAILED_RUN_ID", "")
    # #1325 Option A: run_attempt comes straight off the workflow_run webhook
    # payload (github.event.workflow_run.run_attempt), not a runs-list count.
    # `gh run rerun` increments run_attempt on the SAME run row, so a
    # count-the-runs-list approach silently stayed at 1 forever once dispatch
    # stopped creating new run rows — this is the direct fix for that.
    run_attempt = int(os.environ.get("RUN_ATTEMPT", "1"))

    open_prs = json.loads(
        _gh(
            "pr",
            "list",
            "--repo",
            repo,
            "--state",
            "open",
            "--head",
            head_branch,
            "--json",
            "number,headRefName,headRefOid",
            "--limit",
            "5",
        )
    )

    # #1325 Option C' / #1514: classify the failed run's log BEFORE deciding —
    # decide() now needs failure_signature to fold Class A (blocking-finding)
    # into a "skip" outcome rather than burning the retry cap on a verdict
    # that can never change.
    log_text = _fetch_failed_log(repo, failed_run_id) if failed_run_id else ""
    failure_signature = classify_failure_signature(log_text)
    print(f"failure_signature={failure_signature}")

    decision = decide(
        open_prs, head_branch, head_sha, run_attempt, failure_signature=failure_signature
    )
    print(
        f"failed_run={failed_run_id} sha={head_sha[:8]} branch={head_branch} attempt={run_attempt}"
    )
    print(f"decision={decision.kind} reason={decision.reason} pr={decision.pr_number}")

    if decision.kind == "skip":
        return 0
    if decision.kind == "exhausted":
        _post_exhausted_comment(repo, decision.pr_number, head_sha, failed_run_id)
        return 0

    # decision.kind == "dispatch"
    now = datetime.now(timezone.utc)
    reset_at = parse_reset_time_utc(log_text, now)

    if reset_at is not None:
        delay = (reset_at - now).total_seconds() + RESET_BUFFER_SEC
        if delay > MAX_SLEEP_SEC:
            print(
                f"quota reset at {reset_at.isoformat()} is {delay / 60:.0f}min away "
                f"(> cap {MAX_SLEEP_SEC / 60:.0f}min) — marking exhausted"
            )
            _post_exhausted_comment(repo, decision.pr_number, head_sha, failed_run_id)
            return 0
        if delay > 0:
            print(
                f"quota reset at {reset_at.isoformat()}; sleeping {delay:.0f}s "
                f"({delay / 60:.1f}min) before retry"
            )
            time.sleep(delay)

    # #1514 class B: the verdict-guard failed closed on LINEAGE_INFLIGHT (#1434)
    # because the real review for this SHA is still running in a separate
    # workflow run — rerunning immediately just re-hits the same race. Wait for
    # that run to finish (bounded) before proceeding, so the rerun below has a
    # chance to land after its verdict comment is posted.
    if failure_signature == "verdict-inflight-race":
        inflight_ids = extract_inflight_run_ids(log_text)
        if inflight_ids:
            print(f"waiting for in-flight review run(s) {inflight_ids} before rerun")
            waited = _wait_for_inflight_runs(repo, inflight_ids, VERDICT_INFLIGHT_MAX_WAIT_SEC)
            print(f"waited {waited:.0f}s for in-flight run(s)")

    # Finding #2: double-dispatch guard runs before every _dispatch(), not only
    # after quota-sleep. GitHub sometimes delivers duplicate workflow_run
    # events. Now targeted at the specific failed_run_id being rerun (rather
    # than a head_sha-wide runs-list scan) since #1325 Option A reruns that
    # exact run in place — a duplicate event racing this one would show up as
    # that same run already queued/in_progress/succeeded.
    if failed_run_id:
        run_state = json.loads(
            _gh(
                "run",
                "view",
                failed_run_id,
                "--repo",
                repo,
                "--json",
                "status,conclusion",
            )
        )
        if run_state.get("status") in ("queued", "in_progress"):
            print("pre-dispatch: run already queued/in_progress — no rerun")
            return 0
        if run_state.get("conclusion") == "success":
            print("pre-dispatch: run already succeeded — no rerun")
            return 0

    print(f"rerunning failed run {failed_run_id} for PR #{decision.pr_number} at {head_branch}")
    _dispatch(repo, failed_run_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
