"""Escalation marker for the AFK lane: `needs-human` plus one @-mention comment (#2011).

A lane run that passes intake and ends without a PR (the worker escalated, crashed, timed
out or ran out of turns) must not leave the issue silently parked. Two commands, each
driven by environment variables so the workflow hands untrusted strings (branch names,
the worker's own `escalation.md`) over as data and never through a shell:

- `run`   (agent-dispatch.yml `escalate` job): when no PR exists for the run, label the
          issue `needs-human`, drop `status:in-progress`, and post one comment that names
          the run, the cause and the operator, quoting `escalation.md` when there is one;
- `watch` (lane-red-check-watcher.yml): label an open `claude/issue-*` PR `needs-human`
          and comment, once per check and head SHA, when a required check on it is red.

Decisions D3, D8, D14 and "Escalation marker" in docs/decisions/2026-Q4.md. The label is
the whole signal: intake refuses an issue that carries it, so a human clears it and
re-applies `agent:dispatch` to re-dispatch. Neither command touches an assignee or the
issue body (a bot edit of the body would trip intake's `bot-edited` rule).

The operator is whoever `LANE_OPERATOR` names (repository variable, no literal here).
Unset or not a GitHub login, the label and comment still land without a mention and the
command exits 1, so the misconfiguration shows red. Stdlib only.
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import lane_publish  # noqa: E402

DEFAULT_BOT_LOGIN = "osasuwu-bot"
NEEDS_HUMAN = "needs-human"
IN_PROGRESS = lane_publish.IN_PROGRESS
RUN_MARKER = "lane-escalation"
RED_MARKER = "lane-red-check"
LANE_HEAD_PREFIX = "claude/issue-"

# The required checks on the default branch, less `waiting-human-review`: that one is red
# by design while a human review is owed, which is the hold working, not a failure. The
# set is pinned to the `required-checks-binding` block of docs/reference/github-repo-setup.md
# by a guard test.
WATCHED_CHECKS = ("require-linked-issue", "pytest", "code-gate", "gitleaks")
CODE_GATE = "code-gate"
RED_CONCLUSIONS = ("failure", "timed_out")

ESCALATED, TIMEOUT, MAX_TURNS = "escalated", "timeout", "max-turns"
CANCELLED, CRASH = "cancelled", "crash"
PUBLISH_FAILED, NO_OUTPUT = "publish-failed", "no-output"

ESCALATION_CAP = 8000
_LOGIN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}$")
_WORD = re.compile(r"^[a-z_]+$")
_BACKTICKS = re.compile(r"`+")


def gh(*args):
    result = subprocess.run(["gh", *args], check=True, capture_output=True, text=True)
    return result.stdout.strip()


def operator_handle(raw):
    """The login in `raw` (a leading `@` allowed), or None when it is not a GitHub login."""
    handle = (raw or "").strip().removeprefix("@")
    return handle if _LOGIN.match(handle) else None


def mention(handle):
    return f"@{handle} " if handle else ""


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


def escalation_comment(*, run_id, run_url, handle, cause, cause_line, escalation):
    """The one comment of a run. `escalation` is untrusted: it is quoted, never interpreted."""
    lines = [
        run_marker(run_id),
        f"{mention(handle)}run [{run_id}]({run_url}) ended without a PR: {cause_line}",
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


def _comments(repo, number):
    out = gh(
        "api",
        "--paginate",
        f"repos/{repo}/issues/{number}/comments",
        "--jq",
        ".[] | {user: .user.login, body} | tojson",
    )
    return [json.loads(line) for line in out.splitlines() if line.strip()]


def _has_marker(comments, bot, marker):
    """Only a comment the bot opened with the marker counts: a quoted copy elsewhere is inert."""
    return any(c.get("user") == bot and (c.get("body") or "").startswith(marker) for c in comments)


def _worker_minutes(repo, run_id):
    """Wall-clock minutes of the `worker` job, or None when the jobs API does not say."""
    try:
        out = gh(
            "api",
            f"repos/{repo}/actions/runs/{run_id}/jobs",
            "--jq",
            '.jobs[] | select(.name == "worker") | [.started_at, .completed_at] | @tsv',
        )
        started, completed = out.splitlines()[0].split("\t")
        stamp = lambda s: datetime.fromisoformat(s.replace("Z", "+00:00"))  # noqa: E731
        return (stamp(completed) - stamp(started)).total_seconds() / 60
    except (subprocess.CalledProcessError, ValueError, IndexError):
        return None


def _pr_exists(repo, branch):
    prs = gh("pr", "list", "--repo", repo, "--head", branch, "--state", "all", "--json", "number")
    return bool(json.loads(prs or "[]"))


def _labels(repo, number):
    out = gh("issue", "view", str(number), "--repo", repo, "--json", "labels", "-q", ".labels")
    return [label["name"] for label in json.loads(out or "[]")]


def escalate(env, out_dir):
    """Label and comment on the issue of a run that ended without a PR. Returns the cause."""
    repo, issue, run_id = env["GH_REPO"], env["ISSUE_NUMBER"], env["RUN_ID"]
    if _pr_exists(repo, lane_publish.branch_name(issue, run_id)):
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
        minutes = _worker_minutes(repo, run_id)
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

    handle = operator_handle(env.get("LANE_OPERATOR"))
    bot = env.get("LANE_BOT_LOGIN") or DEFAULT_BOT_LOGIN
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
    )

    edit = ["issue", "edit", issue, "--repo", repo, "--add-label", NEEDS_HUMAN]
    if IN_PROGRESS in _labels(repo, issue):
        edit += ["--remove-label", IN_PROGRESS]
    gh(*edit)
    if _has_marker(_comments(repo, issue), bot, run_marker(run_id)):
        print(f"{repo}#{issue}: run {run_id} already escalated; no second comment")
    else:
        gh("issue", "comment", issue, "--repo", repo, "--body", comment)
    if handle is None:
        print("::warning::LANE_OPERATOR is not set to a GitHub login; escalated without a mention")
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


def red_checks(check_runs, review_runs):
    """`(name, details_url)` of every watched check whose latest run is red, in name order."""
    latest = {}
    for run in check_runs:
        if run["name"] in WATCHED_CHECKS and (
            run["name"] not in latest or run["id"] > latest[run["name"]]["id"]
        ):
            latest[run["name"]] = run
    red = []
    for name in WATCHED_CHECKS:
        run = latest.get(name)
        if not run or run["status"] != "completed" or run["conclusion"] not in RED_CONCLUSIONS:
            continue
        if name == CODE_GATE and not settled(run, review_runs):
            continue
        red.append((name, run.get("details_url") or ""))
    return red


def red_marker(check, sha):
    return f"<!-- {RED_MARKER} {check} {sha} -->"


def red_comment(*, check, sha, url, handle):
    link = f" ({url})" if url.startswith("https://") else ""
    return (
        f"{red_marker(check, sha)}\n"
        f"{mention(handle)}required check `{check}` is red on `{sha[:7]}`{link}.\n\n"
        f"Fix it and push, or close the PR. Remove `{NEEDS_HUMAN}` once you have decided.\n"
    )


def _jsonl(*args):
    return [json.loads(line) for line in gh(*args).splitlines() if line.strip()]


def _check_runs(repo, sha):
    return _jsonl(
        "api",
        "--paginate",
        f"repos/{repo}/commits/{sha}/check-runs",
        "--jq",
        ".check_runs[] | {id, name, status, conclusion, completed_at, details_url} | tojson",
    )


def _review_runs(repo, number, sha):
    """Code Review runs for this head: its `pull_request` runs, and dispatched ones by title."""
    base = f"repos/{repo}/actions/workflows/code-review.yml/runs"
    jq = ".workflow_runs[] | {status, updated_at, title: .display_title} | tojson"
    direct = _jsonl("api", f"{base}?head_sha={sha}&per_page=100", "--jq", jq)
    dispatched = [
        r
        for r in _jsonl("api", f"{base}?event=workflow_dispatch&per_page=100", "--jq", jq)
        if r["title"] == f"Code review PR #{number} @ {sha}"
    ]
    return direct + dispatched


def watch(env):
    """Label and comment on every open lane PR with a settled red required check."""
    repo = env["GH_REPO"]
    handle = operator_handle(env.get("LANE_OPERATOR"))
    bot = env.get("LANE_BOT_LOGIN") or DEFAULT_BOT_LOGIN
    prs = json.loads(
        gh(
            "pr",
            "list",
            "--repo",
            repo,
            "--state",
            "open",
            "--limit",
            "100",
            "--json",
            "number,headRefName,headRefOid,isCrossRepository,labels",
        )
        or "[]"
    )
    flagged = []
    for pr in prs:
        # A fork cannot name its head branch `claude/issue-...` in this repository.
        if pr["isCrossRepository"] or not pr["headRefName"].startswith(LANE_HEAD_PREFIX):
            continue
        number, sha = pr["number"], pr["headRefOid"]
        red = red_checks(_check_runs(repo, sha), _review_runs(repo, number, sha))
        if not red:
            continue
        if NEEDS_HUMAN not in [label["name"] for label in pr["labels"]]:
            gh("pr", "edit", str(number), "--repo", repo, "--add-label", NEEDS_HUMAN)
        comments = _comments(repo, number)
        for check, url in red:
            if not _has_marker(comments, bot, red_marker(check, sha)):
                body = red_comment(check=check, sha=sha, url=url, handle=handle)
                gh("pr", "comment", str(number), "--repo", repo, "--body", body)
            flagged.append((number, check))
    if flagged and handle is None:
        print("::warning::LANE_OPERATOR is not set to a GitHub login; flagged without a mention")
    print(f"{repo}: red required checks on lane PRs: {flagged or 'none'}")
    return flagged, handle


def main(argv):
    command = argv[1] if len(argv) > 1 else ""
    env = os.environ
    if command == "run":
        if escalate(env, env.get("LANE_OUT", "lane-out")) is None:
            return
        handle = operator_handle(env.get("LANE_OPERATOR"))
    elif command == "watch":
        handle = watch(env)[1]
    else:
        sys.exit("usage: lane_escalation.py run|watch")
    if handle is None:
        sys.exit(1)


if __name__ == "__main__":
    main(sys.argv)
