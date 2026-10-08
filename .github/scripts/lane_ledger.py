"""N-run gate ledger for the AFK lane: one bot comment row per run that passed intake.

The gate (D13 in docs/decisions/2026-Q4.md) counts the first 10 runs that pass intake
and asks how many of them ended in a PR merged with no human code edit. The count is
kept on one tracking issue, named by operator configuration (`LANE_LEDGER_ISSUE`,
`owner/repo#N`; unset means no ledger and the script only warns). Each run adds one
comment as the bot, and the comment is edited once more when its PR closes. The rows
alone are enough to read the verdict: `python lane_ledger.py tally` does it.

Three commands, each driven by environment variables so the workflow passes untrusted
strings (branch names, labels) as data and never through a shell:

- `add`   (agent-dispatch.yml `ledger` job): the row for a run that passed intake;
- `close` (lane-ledger-close.yml): finalise the row of a lane PR that just closed;
- `tally` (by hand): print the running count and verdict from the tracking issue.

A row is a visible one-line table plus a JSON object in an HTML comment. The JSON is the
record; the table is rendered from it. Only comments authored by the bot count, so a
forged row from anyone else is ignored. Stdlib only.
"""

import json
import os
import re
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import lane_publish  # noqa: E402

DEFAULT_BOT_LOGIN = "osasuwu-bot"
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


def tally(comments, now, bot=DEFAULT_BOT_LOGIN):
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


def final_outcome(merged, commit_authors, bot=DEFAULT_BOT_LOGIN):
    """How a closed lane PR ended. An unreadable commit author counts as a human edit."""
    if not merged:
        return CLOSED_UNMERGED
    if commit_authors and all(author == bot for author in commit_authors):
        return MERGED_UNEDITED
    return MERGED_EDITED


def class_of(labels):
    return next((name for name in CLASS_LABELS if name in labels), NONE)


def split_ref(ref):
    match = _REF.match((ref or "").strip())
    return (match.group(1), int(match.group(2))) if match else None


def gh(*args):
    result = subprocess.run(["gh", *args], check=True, capture_output=True, text=True)
    return result.stdout.strip()


def _comments(ledger_repo, ledger_issue):
    out = gh(
        "api",
        "--paginate",
        f"repos/{ledger_repo}/issues/{ledger_issue}/comments",
        "--jq",
        ".[] | {id, user: .user.login, body} | tojson",
    )
    return [json.loads(line) for line in out.splitlines() if line.strip()]


def _find_row(comments, bot, repo, run_id):
    for comment in comments:
        row = parse(comment["body"]) if comment.get("user") == bot else None
        if row and str(row["run_id"]) == str(run_id) and row.get("repo") == repo:
            return comment["id"], row
    return None


def _write(ledger_repo, ledger_issue, comment_id, row):
    body = render(row)
    if comment_id is None:
        gh("api", f"repos/{ledger_repo}/issues/{ledger_issue}/comments", "-f", f"body={body}")
    else:
        gh(
            "api",
            "-X",
            "PATCH",
            f"repos/{ledger_repo}/issues/comments/{comment_id}",
            "-f",
            f"body={body}",
        )


def add_row(env, out_dir, now):
    """Add (or, on a re-run of the same run, refresh) the row for one run past intake."""
    ledger = split_ref(env.get("LANE_LEDGER_ISSUE"))
    if ledger is None:
        print("::warning::LANE_LEDGER_ISSUE is not set to owner/repo#N; no ledger row written")
        return None
    host, issue, run_id = env["GH_REPO"], env["ISSUE_NUMBER"], env["RUN_ID"]
    bot = env.get("LANE_BOT_LOGIN") or DEFAULT_BOT_LOGIN

    branch = lane_publish.branch_name(issue, run_id)
    prs = json.loads(
        gh(
            "pr",
            "list",
            "--repo",
            host,
            "--head",
            branch,
            "--state",
            "all",
            "--json",
            "number,additions,deletions,body",
            "--limit",
            "1",
        )
        or "[]"
    )
    pr = prs[0] if prs else None
    labels = [
        label["name"]
        for label in json.loads(
            gh("issue", "view", issue, "--repo", host, "--json", "labels", "-q", ".labels")
        )
    ]

    smoke = split_ref(env.get("LANE_LEDGER_SMOKE_ISSUE"))
    if smoke is None:
        print("::warning::LANE_LEDGER_SMOKE_ISSUE is not owner/repo#N; every run counts")
    in_smoke = smoke is not None and (
        gh("issue", "view", str(smoke[1]), "--repo", smoke[0], "--json", "state", "-q", ".state")
        == "OPEN"
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
    existing = _find_row(_comments(*ledger), bot, host, run_id)
    if existing:
        # A re-run must not undo what the PR close already settled, or the smoke call.
        for key in ("at", "final", "window"):
            row[key] = existing[1].get(key, row[key])
    _write(*ledger, existing[0] if existing else None, row)
    print(f"{host}#{issue}: ledger row for run {run_id} ({row['outcome']}, {row['window']})")
    return row


def close_row(env):
    """Finalise the ledger row of a lane PR that just closed."""
    ledger = split_ref(env.get("LANE_LEDGER_ISSUE"))
    match = _LANE_BRANCH.match(env["PR_HEAD_REF"])
    if ledger is None or match is None:
        print("not a ledgered lane PR; nothing to finalise")
        return None
    host, number = env["GH_REPO"], int(env["PR_NUMBER"])
    bot = env.get("LANE_BOT_LOGIN") or DEFAULT_BOT_LOGIN

    found = _find_row(_comments(*ledger), bot, host, match.group(2))
    # The PR number in the row must match: a branch name alone is easy to imitate.
    if not found or str(found[1].get("pr")) != str(number):
        print(f"{host}#{number}: no ledger row for this PR; nothing to finalise")
        return None
    authors = gh(
        "api",
        "--paginate",
        f"repos/{host}/pulls/{number}/commits",
        "--jq",
        '.[].author.login // ""',
    ).splitlines()
    final = final_outcome(env["PR_MERGED"] == "true", authors, bot)
    row = {**found[1], "final": final}
    _write(*ledger, found[0], row)
    print(f"{host}#{number}: ledger row for run {row['run_id']} is {final}")
    return row


def main(argv):
    command = argv[1] if len(argv) > 1 else ""
    env = os.environ
    now = datetime.now(timezone.utc)
    if command == "add":
        add_row(env, env.get("LANE_OUT", "lane-out"), now)
    elif command == "close":
        close_row(env)
    elif command == "tally":
        ledger = split_ref(env.get("LANE_LEDGER_ISSUE"))
        if ledger is None:
            sys.exit("LANE_LEDGER_ISSUE must be owner/repo#N")
        print(
            json.dumps(
                tally(_comments(*ledger), now, env.get("LANE_BOT_LOGIN") or DEFAULT_BOT_LOGIN)
            )
        )
    else:
        sys.exit("usage: lane_ledger.py add|close|tally")


if __name__ == "__main__":
    main(sys.argv)
