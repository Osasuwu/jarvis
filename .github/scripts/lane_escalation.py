"""Escalation marker for the AFK lane: `needs-human` plus one @-mention comment (#2011).

A lane run that passes intake and ends without a PR (the worker escalated, crashed, timed
out or ran out of turns) must not leave the issue silently parked. Two commands, each
driven by environment variables so the workflow hands untrusted strings (branch names,
the worker's own `escalation.md`) over as data and never through a shell:

- `run`   (agent-dispatch.yml `escalate` job): when no PR exists for the run, label the
          issue `needs-human`, drop `status:in-progress`, and post one comment that names
          the run, the cause and the human, quoting `escalation.md` when there is one;
- `watch` (lane-red-check-watcher.yml): label an open `claude/issue-*` PR `needs-human`
          and comment, once per check and head SHA, when a required check on it is red.

Decisions D3, D8, D14 and "Escalation marker" in docs/decisions/2026-Q4.md. The label is
the whole signal: intake refuses an issue that carries it, so a human clears it and
re-applies `agent:dispatch` to re-dispatch. Neither command touches an assignee or the
issue body (a bot edit of the body would trip intake's `bot-edited` rule).

The human @-mentioned is whoever applied `agent:dispatch` for the run (#2051): `run`
reads it from `LANE_LABELER` (the label event's sender), `watch` from the `actor` of the
run named by the PR's branch. When that is not a person (the bot, an app, an unreadable
answer) the mention falls back to the operator, whoever `LANE_OPERATOR` names (repository
variable, no literal here), and the comment says so. When neither resolves, the label and
comment still land without a mention and the command exits 1, so the misconfiguration
shows red; a `watch` pass that flagged nothing exits 0 either way. Every GitHub call goes
through `github_client.py` beside this script (#2068). Stdlib only.
"""

import os
import re
import sys
import urllib.error
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import lane_publish  # noqa: E402

NEEDS_HUMAN = "needs-human"
IN_PROGRESS = lane_publish.IN_PROGRESS
RUN_MARKER = "lane-escalation"
RED_MARKER = "lane-red-check"
LANE_HEAD_PREFIX = "claude/issue-"
_LANE_HEAD = re.compile(rf"^{re.escape(LANE_HEAD_PREFIX)}\d+-(\d+)$")

# The watched checks are the host's required checks, less `waiting-human-review` and
# `risk-tier`: those two are red by design while a human review is owed (a HIGH/CRITICAL
# lane PR waits for an admin approval), which is the hold working, not a failure. The host's
# caller passes the list as `LANE_WATCHED_CHECKS`; a guard test pins jarvis's caller to the
# `required-checks-binding` block of docs/reference/github-repo-setup.md.
CODE_GATE = "code-gate"
RED_CONCLUSIONS = ("failure", "timed_out")

ESCALATED, TIMEOUT, MAX_TURNS = "escalated", "timeout", "max-turns"
CANCELLED, CRASH = "cancelled", "crash"
PUBLISH_FAILED, NO_OUTPUT = "publish-failed", "no-output"

ESCALATION_CAP = 8000
FALLBACK_NOTE = (
    "Sent to the operator: the person who applied `agent:dispatch` could not be resolved."
)
_LOGIN = lane_publish.LOGIN
_WORD = re.compile(r"^[a-z_]+$")
_BACKTICKS = re.compile(r"`+")


_load_client = lane_publish._load_client


def _make_client(token):
    return _load_client().Client(token, user_agent="lane-escalation")


def operator_handle(raw):
    """The login in `raw` (a leading `@` allowed), or None when it is not a GitHub login."""
    handle = (raw or "").strip().removeprefix("@")
    return handle if _LOGIN.match(handle) else None


def mention(handle):
    return f"@{handle} " if handle else ""


def fallback_note(handle, fell_back):
    """The line saying a mention went to the operator in place of the labeller (#2051)."""
    return [FALLBACK_NOTE] if fell_back and handle else []


def _run_recipient(env, bot):
    """`(handle, fell_back)` for a run: who applied `agent:dispatch` (`LANE_LABELER`, the
    label event's sender), else the operator."""
    return lane_publish.recipient(
        env.get("LANE_LABELER"), operator_handle(env.get("LANE_OPERATOR")), bot
    )


def fence(text):
    """`text` in a code fence one backtick longer than any run inside it (three at least)."""
    longest = max((len(run) for run in _BACKTICKS.findall(text)), default=0)
    ticks = "`" * max(3, longest + 1)
    return f"{ticks}\n{text}\n{ticks}"


def worker_outputs(subtype, turns):
    """The worker's ending record from its job outputs; anything unexpected reads as absent."""
    subtype = subtype if subtype and _WORD.match(subtype) else None
    turns = int(turns) if turns and turns.isdigit() else None
    return subtype, turns


def classify(
    *,
    escalation,
    worker_result,
    subtype,
    num_turns,
    worker_minutes,
    timeout_minutes,
    max_turns,
    has_bundle,
):
    """Why a run ended without a PR; the first matching cause in the order of the plan."""
    if escalation is not None:
        return ESCALATED
    if worker_minutes is not None and worker_minutes >= timeout_minutes:
        return TIMEOUT
    if subtype == "error_max_turns" or (num_turns is not None and num_turns > max_turns):
        return MAX_TURNS
    if worker_result == "cancelled":
        return CANCELLED
    if worker_result != "success":
        return CRASH
    return PUBLISH_FAILED if has_bundle else NO_OUTPUT


def cause_text(cause, *, worker_result, timeout_minutes, max_turns):
    return {
        ESCALATED: "the worker stopped and escalated; its note is quoted below.",
        TIMEOUT: f"the worker hit its {timeout_minutes}-minute job timeout.",
        MAX_TURNS: f"the worker ran out of turns (limit {max_turns}).",
        CANCELLED: "the worker job was cancelled.",
        CRASH: f"the worker job ended `{worker_result or 'unknown'}` before it finished.",
        PUBLISH_FAILED: (
            "the worker finished and left commits, but no PR was opened; the `publish` job's"
            " log has the reason."
        ),
        NO_OUTPUT: "the worker finished with no commits and no escalation note.",
    }[cause]


def run_marker(run_id):
    return f"<!-- {RUN_MARKER} run={run_id} -->"


def escalation_comment(*, run_id, run_url, handle, cause, cause_line, escalation, fell_back=False):
    """The one comment of a run. `escalation` is untrusted: it is quoted, never interpreted."""
    lines = [
        run_marker(run_id),
        f"{mention(handle)}run [{run_id}]({run_url}) ended without a PR: {cause_line}",
        *fallback_note(handle, fell_back),
        "",
    ]
    if escalation is not None:
        text = escalation.strip() or "(empty)"
        if len(text) > ESCALATION_CAP:
            text = (
                text[:ESCALATION_CAP]
                + "\n[truncated; the full text is in the run's `lane-out` artifact]"
            )
        lines += ["The worker's `escalation.md`, quoted (untrusted):", "", fence(text), ""]
    lines.append(
        f"Decide, then re-dispatch: remove `{NEEDS_HUMAN}` and re-apply `agent:dispatch`."
        f" Cause: `{cause}`."
    )
    return "\n".join(lines) + "\n"


def _comments(api, repo, number):
    """Every comment as {id, user (login), body}. A listing past its cap raises
    `ListingTruncated`: the marker could sit in the part left unread."""
    return _load_client().comments(api, repo, number)


def _has_marker(comments, bot, marker):
    """Only a comment the bot opened with the marker counts: a quoted copy elsewhere is inert."""
    return any(c.get("user") == bot and (c.get("body") or "").startswith(marker) for c in comments)


def _worker_minutes(api, repo, run_id):
    """Wall-clock minutes of the `worker` job, or None when the jobs API does not say.

    Only the cause's wording rests on it (without it a timeout reads as `cancelled`), so
    a failed read falls back to the worker's result rather than block the escalation."""
    try:
        jobs = api("GET", f"repos/{repo}/actions/runs/{run_id}/jobs")["jobs"]
        worker = next(job for job in jobs if job["name"] == "worker")
        stamp = lambda s: datetime.fromisoformat(s.replace("Z", "+00:00"))  # noqa: E731
        started, completed = stamp(worker["started_at"]), stamp(worker["completed_at"])
        return (completed - started).total_seconds() / 60
    except (
        urllib.error.URLError,  # HTTPError included
        OSError,  # a timeout
        ValueError,  # an empty body, a malformed timestamp
        KeyError,
        AttributeError,  # completed_at null while the job still runs
        StopIteration,  # no worker job
    ):
        return None


def _pr_exists(api, repo, branch):
    """Whether a PR in any state has `branch` of this repository as its head."""
    owner = repo.split("/", 1)[0]
    return bool(api("GET", f"repos/{repo}/pulls?head={owner}:{branch}&state=all&per_page=1"))


def _labels(api, repo, number):
    return [label["name"] for label in api("GET", f"repos/{repo}/issues/{number}")["labels"]]


def escalate(api, env, out_dir):
    """Label and comment on the issue of a run that ended without a PR. Returns the cause."""
    repo, issue, run_id = env["GH_REPO"], env["ISSUE_NUMBER"], env["RUN_ID"]
    if _pr_exists(api, repo, lane_publish.branch_name(issue, run_id)):
        print(f"{repo}#{issue}: run {run_id} opened a PR; nothing to escalate")
        return None

    out = Path(out_dir)
    note = out / "escalation.md"
    escalation = note.read_text(encoding="utf-8", errors="replace") if note.exists() else None
    worker_result = env.get("WORKER_RESULT", "")
    worker_result = worker_result if _WORD.match(worker_result) else ""
    timeout_minutes, max_turns = int(env["WORKER_TIMEOUT_MINUTES"]), int(env["WORKER_MAX_TURNS"])
    subtype, turns = worker_outputs(
        env.get("WORKER_RESULT_SUBTYPE", ""), env.get("WORKER_NUM_TURNS", "")
    )
    minutes = None
    if escalation is None and worker_result != "success":
        minutes = _worker_minutes(api, repo, run_id)
    cause = classify(
        escalation=escalation,
        worker_result=worker_result,
        subtype=subtype,
        num_turns=turns,
        worker_minutes=minutes,
        timeout_minutes=timeout_minutes,
        max_turns=max_turns,
        has_bundle=(out / "work.bundle").exists(),
    )

    bot = lane_publish.require_bot(env, "lane_escalation")
    handle, fell_back = _run_recipient(env, bot)
    server = env.get("GITHUB_SERVER_URL") or "https://github.com"
    comment = escalation_comment(
        run_id=run_id,
        run_url=f"{server}/{repo}/actions/runs/{run_id}",
        handle=handle,
        cause=cause,
        cause_line=cause_text(
            cause,
            worker_result=worker_result,
            timeout_minutes=timeout_minutes,
            max_turns=max_turns,
        ),
        escalation=escalation,
        fell_back=fell_back,
    )

    drop = IN_PROGRESS in _labels(api, repo, issue)
    api("POST", f"repos/{repo}/issues/{issue}/labels", {"labels": [NEEDS_HUMAN]})
    if drop:
        _load_client().remove_label(api, repo, issue, IN_PROGRESS)
    if _has_marker(_comments(api, repo, issue), bot, run_marker(run_id)):
        print(f"{repo}#{issue}: run {run_id} already escalated; no second comment")
    else:
        # Not retried on a 5xx: one that follows a posted comment would post a second.
        api("POST", f"repos/{repo}/issues/{issue}/comments", {"body": comment}, idempotent=False)
    if handle is None:
        print(
            "::warning::LANE_OPERATOR is not set to a GitHub login and the person who applied"
            " `agent:dispatch` could not be resolved; escalated without a mention"
        )
    print(f"{repo}#{issue}: run {run_id} escalated ({cause})")
    return cause


def settled(code_gate, review_runs):
    """Whether a red `code-gate` is the review's verdict, not the placeholder before it.

    The gate's `pull_request_target` run reports red (`evidence-none`) before the review
    lands. It counts only once a Code Review run for the head SHA exists, none is still
    running, and the gate completed after the last of them.
    """
    if not review_runs or any(r["status"] != "completed" for r in review_runs):
        return False
    return code_gate["completed_at"] >= max(r["updated_at"] for r in review_runs)


def watched_checks(env):
    """The comma-separated `LANE_WATCHED_CHECKS`, in order; none is an error, not a no-op."""
    names = [n.strip() for n in (env.get("LANE_WATCHED_CHECKS") or "").split(",") if n.strip()]
    if not names:
        print("::error::LANE_WATCHED_CHECKS is not set: the watcher needs the checks to watch")
        sys.exit(1)
    return names


def red_checks(check_runs, review_runs, watched):
    """`(name, details_url)` of every watched check whose latest run is red, in name order."""
    latest = {}
    for run in check_runs:
        if run["name"] in watched and (
            run["name"] not in latest or run["id"] > latest[run["name"]]["id"]
        ):
            latest[run["name"]] = run
    red = []
    for name in watched:
        run = latest.get(name)
        if not run or run["status"] != "completed" or run["conclusion"] not in RED_CONCLUSIONS:
            continue
        if name == CODE_GATE and not settled(run, review_runs):
            continue
        red.append((name, run.get("details_url") or ""))
    return red


def red_marker(check, sha):
    return f"<!-- {RED_MARKER} {check} {sha} -->"


def red_comment(*, check, sha, url, handle, fell_back=False):
    link = f" ({url})" if url.startswith("https://") else ""
    note = "".join(f"{line}\n" for line in fallback_note(handle, fell_back))
    return (
        f"{red_marker(check, sha)}\n"
        f"{mention(handle)}required check `{check}` is red on `{sha[:7]}`{link}.\n{note}\n"
        f"Fix it and push, or close the PR. Remove `{NEEDS_HUMAN}` once you have decided.\n"
    )


def run_labeler(api, repo, ref):
    """Who applied `agent:dispatch` for the lane run that opened branch `ref`, or None.

    The watcher runs on `workflow_run`, so no label event is at hand: the run id comes
    from the branch name (lane_publish.branch_name) and the person from that run's
    `actor`, the sender of the event that started it (a re-run changes
    `triggering_actor`, not `actor`). Anything but a user, or an answer that does not
    say, reads as unresolved and the operator is asked instead."""
    match = _LANE_HEAD.match(ref)
    if not match:
        return None
    try:
        actor = api("GET", f"repos/{repo}/actions/runs/{match.group(1)}")["actor"]
        return actor["login"] if actor["type"] == "User" else None
    except (
        urllib.error.URLError,  # HTTPError included
        OSError,  # a timeout
        ValueError,  # an empty body
        KeyError,
        TypeError,  # a null actor
    ):
        return None


def _check_runs(api, repo, sha):
    return _load_client().paged(api, f"repos/{repo}/commits/{sha}/check-runs", key="check_runs")


def _review_runs(api, repo, number, sha):
    """Code Review runs for this head: its `pull_request` runs, and dispatched ones by title."""
    base = f"repos/{repo}/actions/workflows/code-review.yml/runs"

    def runs(query):
        return [
            {"status": r["status"], "updated_at": r["updated_at"], "title": r["display_title"]}
            for r in api("GET", f"{base}?{query}&per_page=100")["workflow_runs"]
        ]

    direct = runs(f"head_sha={sha}")
    dispatched = [
        r
        for r in runs("event=workflow_dispatch")
        if r["title"] == f"Code review PR #{number} @ {sha}"
    ]
    return direct + dispatched


def watch(api, env):
    """Label and comment on every open lane PR with a settled red required check.

    Returns `(flagged, unmentioned)`: the `(PR, check)` pairs flagged, and the PRs whose
    comment could @-mention no one (neither its labeller nor an operator resolved)."""
    repo = env["GH_REPO"]
    operator = operator_handle(env.get("LANE_OPERATOR"))
    bot = lane_publish.require_bot(env, "lane_escalation")
    watched = watched_checks(env)
    client = _load_client()
    truncated = None
    try:
        prs = client.paged(api, f"repos/{repo}/pulls?state=open")
    except client.ListingTruncated as exc:
        # The PRs read are still flagged; the rest went unread, so the run ends red below.
        prs, truncated = exc.items, exc
    flagged, unmentioned = [], []
    for pr in prs:
        head = pr["head"]
        # A fork cannot name its head branch `claude/issue-...` in this repository; a head
        # repository that was deleted (None) is no lane branch either.
        source = (head.get("repo") or {}).get("full_name") or ""
        if source.lower() != repo.lower() or not head["ref"].startswith(LANE_HEAD_PREFIX):
            continue
        number, sha = pr["number"], head["sha"]
        reviews = _review_runs(api, repo, number, sha) if CODE_GATE in watched else []
        red = red_checks(_check_runs(api, repo, sha), reviews, watched)
        if not red:
            continue
        if NEEDS_HUMAN not in [label["name"] for label in pr["labels"]]:
            api("POST", f"repos/{repo}/issues/{number}/labels", {"labels": [NEEDS_HUMAN]})
        # Each PR goes to whoever dispatched its own run (#2051), so it is resolved per PR.
        handle, fell_back = lane_publish.recipient(
            run_labeler(api, repo, head["ref"]), operator, bot
        )
        if handle is None:
            unmentioned.append(number)
        comments = _comments(api, repo, number)
        for check, url in red:
            if not _has_marker(comments, bot, red_marker(check, sha)):
                body = red_comment(
                    check=check, sha=sha, url=url, handle=handle, fell_back=fell_back
                )
                # Not retried on a 5xx: one that follows a posted comment would post a second.
                api(
                    "POST",
                    f"repos/{repo}/issues/{number}/comments",
                    {"body": body},
                    idempotent=False,
                )
            flagged.append((number, check))
    if unmentioned:
        print(
            "::warning::LANE_OPERATOR is not set to a GitHub login and the person who applied"
            f" `agent:dispatch` could not be resolved; flagged without a mention: {unmentioned}"
        )
    print(f"{repo}: red required checks on lane PRs: {flagged or 'none'}")
    if truncated is not None:
        raise truncated
    return flagged, unmentioned


def main(argv, make_client=None):
    command = argv[1] if len(argv) > 1 else ""
    env = os.environ
    if command not in ("run", "watch"):
        sys.exit("usage: lane_escalation.py run|watch")
    lane_publish.require_bot(env, "lane_escalation")
    api = (make_client or _make_client)(env["GH_TOKEN"])
    if command == "run":
        if escalate(api, env, env.get("LANE_OUT", "lane-out")) is None:
            return
        handle, _ = _run_recipient(env, lane_publish.require_bot(env, "lane_escalation"))
        if handle is None:
            sys.exit(1)
    else:
        # Nothing flagged means no one was owed a mention, so no failure either.
        _flagged, unmentioned = watch(api, env)
        if unmentioned:
            sys.exit(1)


if __name__ == "__main__":
    main(sys.argv)
