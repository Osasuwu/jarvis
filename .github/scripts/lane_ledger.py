"""N-run gate ledger for the AFK lane: one bot comment row per run that passed intake.

The gate (D13 in docs/decisions/2026-Q4.md) counts the first 10 runs that pass intake
and asks how many of them ended in a PR merged with no human code edit. The count is
kept on one tracking issue, named by operator configuration (`LANE_LEDGER_ISSUE`,
`owner/repo#N`; unset means no ledger and the script only warns). Each run adds one
comment as the bot, and the comment is edited once more when its PR closes. The rows
alone are enough to read the verdict: `python lane_ledger.py tally` does it.

Four commands, each driven by environment variables so the workflow passes untrusted
strings (branch names, labels) as data and never through a shell:

- `add`     (agent-dispatch.yml `ledger` job): the row for a run that passed intake;
- `close`   (lane-ledger-close.yml): finalise the row of a lane PR that just closed;
- `tally`   (by hand): print the running count and verdict from the tracking issue;
- `touched` (by hand, `touched owner/repo#N`): print `human-touched: yes|no` for a PR and
  list each non-bot commit, comment or review that makes it `yes` (#1999 AP4).

The gate counts a run as a success only when its PR merged with `human-touched: no`: no
commit, comment or non-approving review by anyone but the bot or a `*[bot]` login.

A row is a visible one-line table plus a JSON object in an HTML comment. The JSON is the
record; the table is rendered from it. Only comments authored by the bot count, so a
forged row from anyone else is ignored.

Every GitHub call goes through `github_client.py` beside this script (#2068), with the
token in `GH_TOKEN`; by hand that is `GH_TOKEN=$(gh auth token)`. Stdlib only.
"""

import json
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import lane_publish  # noqa: E402

MARKER = "lane-ledger"
NONE = "—"

# Gate constants, fixed by D13. Changing a fixed axis of the lane starts a new tracking
# issue rather than editing these.
GATE_RUNS = 10
GATE_FAIL_AT_OR_BELOW = 5
GATE_DEADLINE = date(2026, 11, 18)
HIGH_HOLD_DAYS = 7

CLASS_LABELS = ("afk:2-plan", "afk:1-auto")
HIGH_TIERS = ("HIGH", "CRITICAL")

# Run outcomes (set when the row is added) and PR final outcomes (set when it closes).
PR_OPENED, ESCALATED, NO_ARTIFACT = "pr-opened", "escalated", "no-artifact"
PENDING = "pending"
MERGED_UNEDITED, MERGED_EDITED, CLOSED_UNMERGED = (
    "merged-unedited",
    "merged-edited",
    "closed-unmerged",
)
WINDOW_SMOKE, WINDOW_COUNTED = "smoke", "counted"

COLUMNS = (
    "run_id",
    "repo",
    "issue",
    "pr",
    "lane_sha",
    "class",
    "tier",
    "diff",
    "outcome",
    "final",
    "window",
    "at",
)

_ROW = re.compile(rf"<!--\s*{MARKER}\s+(\{{.*?\}})\s*-->", re.DOTALL)
_REF = re.compile(r"^([\w.-]+/[\w.-]+)#(\d+)$")
_LANE_BRANCH = re.compile(r"^claude/issue-(\d+)-(\d+)(?:-.*)?$")


def render(row):
    """The comment body for a row: the JSON record plus a one-line table of it."""
    # `<` and `>` escaped so no value can close the HTML comment early.
    record = json.dumps(row, ensure_ascii=True).replace("<", "\\u003c").replace(">", "\\u003e")
    cells = " | ".join(str(row.get(col, NONE)) for col in COLUMNS)
    head = " | ".join(COLUMNS)
    rule = " | ".join("---" for _ in COLUMNS)
    return f"<!-- {MARKER} {record} -->\n| {head} |\n| {rule} |\n| {cells} |\n"


def parse(body):
    """The row recorded in a comment body, or None when it holds no valid row."""
    match = _ROW.search(body or "")
    if not match:
        return None
    try:
        row = json.loads(match.group(1))
    except ValueError:
        return None
    return row if isinstance(row, dict) and "run_id" in row else None


def _when(row):
    return datetime.fromisoformat(row["at"])


def _is_hold_expired(row, now):
    """A HIGH PR with no decision for 7 days counts as not merged (D13)."""
    return row.get("tier") in HIGH_TIERS and now - _when(row) >= timedelta(days=HIGH_HOLD_DAYS)


def tally(comments, now, bot):
    """The running count over a ledger issue's comments, oldest first.

    `comments` is a list of `{"user": login, "body": text}`. Returns the counted rows
    (the first GATE_RUNS non-smoke ones), how many succeeded, how many are settled
    failures, how many are still open, and the verdict: `pass`, `fail` or `open`.
    """
    rows = [
        row for c in comments if c.get("user") == bot and (row := parse(c.get("body"))) is not None
    ]
    smoke = [r for r in rows if r.get("window") == WINDOW_SMOKE]
    counted = [r for r in rows if r.get("window") != WINDOW_SMOKE][:GATE_RUNS]

    successes = failures = pending = 0
    for row in counted:
        if row.get("final") == MERGED_UNEDITED:
            successes += 1
        elif row.get("outcome") != PR_OPENED or row.get("final") != PENDING:
            failures += 1
        elif _is_hold_expired(row, now):
            failures += 1
        else:
            pending += 1

    # D13 judges ten counted runs: six clean ones out of six is still short of the window.
    if successes > GATE_FAIL_AT_OR_BELOW and len(counted) >= GATE_RUNS:
        verdict = "pass"
    elif failures >= GATE_RUNS - GATE_FAIL_AT_OR_BELOW:
        verdict = "fail"
    elif len(counted) < GATE_RUNS and now.date() > GATE_DEADLINE:
        verdict = "fail"
    else:
        verdict = "open"
    return {
        "counted": len(counted),
        "smoke": len(smoke),
        "successes": successes,
        "failures": failures,
        "pending": pending,
        "verdict": verdict,
    }


def run_outcome(has_pr, escalated):
    if has_pr:
        return PR_OPENED
    return ESCALATED if escalated else NO_ARTIFACT


def _is_bot(login, bot):
    login = login.casefold()
    return login == bot.casefold() or login.endswith("[bot]")


def _login(user):
    return (user or {}).get("login") or ""


def human_touches(commits, issue_comments, review_comments, reviews, bot):
    """One line per non-bot touch on a PR; an empty list means `human-touched: no`.

    The arguments are the REST lists of the PR's commits, issue comments, review comments
    and reviews. A commit counts when its author, or its committer other than GitHub's
    `web-flow`, is not the bot: an unlinked author or committer (no login) is a touch, the
    fail-closed reading. A human approval alone is not a touch: it edits nothing. An empty
    commit list is a touch too, since a merged PR without readable commits cannot be shown clean.
    """
    touches = []
    if not commits:
        touches.append("no commits readable; cannot show the PR is untouched")
    for commit in commits:
        sha = (commit.get("sha") or "")[:7]
        author = _login(commit.get("author"))
        committer = _login(commit.get("committer"))
        if not author or not _is_bot(author, bot):
            touches.append(f"commit {sha}: author {author or 'unlinked'}")
        if committer != "web-flow" and (not committer or not _is_bot(committer, bot)):
            touches.append(f"commit {sha}: committer {committer or 'unlinked'}")
    for kind, items in (("issue comment", issue_comments), ("review comment", review_comments)):
        for item in items:
            login = _login(item.get("user"))
            if not _is_bot(login, bot):
                touches.append(f"{kind} by {login or 'unknown'}")
    for review in reviews:
        login = _login(review.get("user"))
        if review.get("state") != "APPROVED" and not _is_bot(login, bot):
            touches.append(f"review ({review.get('state')}) by {login or 'unknown'}")
    return touches


def final_outcome(merged, touches):
    """How a closed lane PR ended. `merged-unedited` is exactly `human-touched: no`."""
    if not merged:
        return CLOSED_UNMERGED
    return MERGED_EDITED if touches else MERGED_UNEDITED


def class_of(labels):
    return next((name for name in CLASS_LABELS if name in labels), NONE)


def split_ref(ref):
    match = _REF.match((ref or "").strip())
    return (match.group(1), int(match.group(2))) if match else None


# `github_client.py`, loaded once under the key every lane script shares.
_load_client = lane_publish._load_client


def _make_client(token):
    return _load_client().Client(token, user_agent="lane-ledger")


def _comments(api, ledger_repo, ledger_issue):
    # Capped (ListingTruncated): a partly read ledger would miss a row or miscount the gate.
    return _load_client().comments(api, ledger_repo, ledger_issue)


def fetch_touches(api, host, number, bot):
    """The non-bot touches on a PR, read from GitHub (see `human_touches`)."""
    paged = _load_client().paged
    return human_touches(
        paged(api, f"repos/{host}/pulls/{number}/commits"),
        paged(api, f"repos/{host}/issues/{number}/comments"),
        paged(api, f"repos/{host}/pulls/{number}/comments"),
        paged(api, f"repos/{host}/pulls/{number}/reviews"),
        bot,
    )


def report_touches(touches):
    """The `human-touched` line plus one line per touch, as `close` and `touched` print it."""
    return "\n".join([f"human-touched: {'yes' if touches else 'no'}", *touches])


def _find_row(comments, bot, repo, run_id):
    for comment in comments:
        row = parse(comment["body"]) if comment.get("user") == bot else None
        if row and str(row["run_id"]) == str(run_id) and row.get("repo") == repo:
            return comment["id"], row
    return None


def _write(api, ledger_repo, ledger_issue, comment_id, row):
    body = {"body": render(row)}
    if comment_id is None:
        # Not retried on a 5xx: one after a posted row would add a second row for the run.
        api("POST", f"repos/{ledger_repo}/issues/{ledger_issue}/comments", body, idempotent=False)
    else:
        api("PATCH", f"repos/{ledger_repo}/issues/comments/{comment_id}", body)


def add_row(api, env, out_dir, now):
    """Add (or, on a re-run of the same run, refresh) the row for one run past intake."""
    ledger = split_ref(env.get("LANE_LEDGER_ISSUE"))
    if ledger is None:
        print("::warning::LANE_LEDGER_ISSUE is not set to owner/repo#N; no ledger row written")
        return None
    host, issue, run_id = env["GH_REPO"], env["ISSUE_NUMBER"], env["RUN_ID"]
    bot = lane_publish.require_bot(env, "lane_ledger")

    branch = lane_publish.branch_name(issue, run_id)
    owner = host.split("/", 1)[0]
    # The list answer lacks the size, so the PR found is read once more on its own.
    found = api("GET", f"repos/{host}/pulls?head={owner}:{branch}&state=all&per_page=1")
    pr = api("GET", f"repos/{host}/pulls/{found[0]['number']}") if found else None
    labels = [label["name"] for label in api("GET", f"repos/{host}/issues/{issue}")["labels"]]

    smoke = split_ref(env.get("LANE_LEDGER_SMOKE_ISSUE"))
    if smoke is None:
        print("::warning::LANE_LEDGER_SMOKE_ISSUE is not owner/repo#N; every run counts")
    in_smoke = (
        smoke is not None and api("GET", f"repos/{smoke[0]}/issues/{smoke[1]}")["state"] == "open"
    )

    row = {
        "run_id": str(run_id),
        "repo": host,
        "issue": f"#{issue}",
        "pr": pr["number"] if pr else NONE,
        "lane_sha": env["LANE_SHA"][:12],
        "class": class_of(labels),
        # An unreadable `Risk:` line is HIGH, as in lane_publish: the fail-closed reading.
        "tier": (lane_publish.parse_risk(pr["body"]) or "HIGH") if pr else NONE,
        "diff": pr["additions"] + pr["deletions"] if pr else NONE,
        "outcome": run_outcome(pr is not None, (Path(out_dir) / "escalation.md").exists()),
        "final": PENDING,
        "window": WINDOW_SMOKE if in_smoke else WINDOW_COUNTED,
        "at": now.isoformat(timespec="seconds"),
    }
    existing = _find_row(_comments(api, *ledger), bot, host, run_id)
    if existing:
        # A re-run must not undo what the PR close already settled, or the smoke call.
        for key in ("at", "final", "window"):
            row[key] = existing[1].get(key, row[key])
    _write(api, *ledger, existing[0] if existing else None, row)
    print(f"{host}#{issue}: ledger row for run {run_id} ({row['outcome']}, {row['window']})")
    return row


def close_row(api, env):
    """Finalise the ledger row of a lane PR that just closed."""
    ledger = split_ref(env.get("LANE_LEDGER_ISSUE"))
    match = _LANE_BRANCH.match(env["PR_HEAD_REF"])
    if ledger is None or match is None:
        print("not a ledgered lane PR; nothing to finalise")
        return None
    host, number = env["GH_REPO"], int(env["PR_NUMBER"])
    bot = lane_publish.require_bot(env, "lane_ledger")

    found = _find_row(_comments(api, *ledger), bot, host, match.group(2))
    # The PR number in the row must match: a branch name alone is easy to imitate.
    if not found or str(found[1].get("pr")) != str(number):
        print(f"{host}#{number}: no ledger row for this PR; nothing to finalise")
        return None
    touches = fetch_touches(api, host, number, bot)
    print(report_touches(touches))
    final = final_outcome(env["PR_MERGED"] == "true", touches)
    row = {**found[1], "final": final}
    _write(api, *ledger, found[0], row)
    print(f"{host}#{number}: ledger row for run {row['run_id']} is {final}")
    return row


def main(argv, make_client=None):
    command = argv[1] if len(argv) > 1 else ""
    env = os.environ
    now = datetime.now(timezone.utc)
    if command not in ("add", "close", "tally", "touched"):
        sys.exit("usage: lane_ledger.py add|close|tally|touched")
    target = ledger = None
    if command == "touched":  # the usage first, as before: it needs no environment
        target = split_ref(argv[2] if len(argv) > 2 else "")
        if target is None:
            sys.exit("usage: lane_ledger.py touched owner/repo#N")
    bot = lane_publish.require_bot(env, "lane_ledger")
    if command == "tally":
        ledger = split_ref(env.get("LANE_LEDGER_ISSUE"))
        if ledger is None:
            sys.exit("LANE_LEDGER_ISSUE must be owner/repo#N")
    token = env.get("GH_TOKEN")
    if not token:
        # By hand, gh's stored login used to be read implicitly; the client needs it named.
        sys.exit("GH_TOKEN must be set (e.g. GH_TOKEN=$(gh auth token))")
    api = (make_client or _make_client)(token)
    if command == "add":
        add_row(api, env, env.get("LANE_OUT", "lane-out"), now)
    elif command == "close":
        close_row(api, env)
    elif command == "touched":
        print(report_touches(fetch_touches(api, *target, bot)))
    else:
        print(json.dumps(tally(_comments(api, *ledger), now, bot)))


if __name__ == "__main__":
    main(sys.argv)
