"""Publish step for the AFK lane: every GitHub write the worker may not make.

Runs from the `publish` job of `.github/workflows/lane.yml`, as the bot account
named by `LANE_BOT_LOGIN`, with `AGENT_DISPATCH_PAT` (decisions D1, D4, D10, D14 in
docs/decisions/2026-Q4.md). The worker job holds no token that can write; it leaves
two files in `lane-out/` — `work.bundle` (its commits) and `pr-body.md` (its PR
description) — and this job, on a fresh checkout of the default branch, does the rest:

1. fetch the bundle into `claude/issue-<N>-<run_id>` and push exactly that branch;
2. open the PR with `Closes #<N>` guaranteed in the body;
3. request a review from the operator only when the body's `Risk:` line reads HIGH or
   CRITICAL (a missing line counts as HIGH: fail closed), so LOW/MEDIUM PRs carry no
   pending request for `waiting-human-review` to hold;
4. move the issue from `status:in-progress` to `status:review`.

Auto-merge stays a separate step of the job. No bundle means the worker produced no
commits: nothing is published and the script exits 0.

The worker's output is data, not instructions: the title is the head commit's subject
and the body is passed as a file, never through a shell. Stdlib only.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

IN_PROGRESS = "status:in-progress"
REVIEW = "status:review"
HIGH_RISK = ("HIGH", "CRITICAL")
SEVERITY = ("LOW", "MEDIUM", "HIGH", "CRITICAL")

_RISK_LINE = re.compile(
    r"^[ \t>*_-]*Risk[ \t]*:[ \t*_]*(LOW|MEDIUM|HIGH|CRITICAL)\b", re.IGNORECASE | re.MULTILINE
)


def require_bot(env, script):
    """The bot login the lane acts as; a host names its own, so there is no default."""
    bot = (env.get("LANE_BOT_LOGIN") or "").strip()
    if not bot:
        print(
            f"::error::{script}: LANE_BOT_LOGIN is empty; "
            "the calling workflow must pass the lane's bot login"
        )
        sys.exit(1)
    return bot


def parse_risk(body):
    """The highest tier named on any `Risk:` line of the body, or None if there is none."""
    tiers = [m.group(1).upper() for m in _RISK_LINE.finditer(body or "")]
    return max(tiers, key=SEVERITY.index) if tiers else None


def needs_human_review(risk):
    """HIGH, CRITICAL and an unreadable risk all ask for a human; LOW and MEDIUM do not."""
    return risk is None or risk in HIGH_RISK


def branch_name(issue, run_id):
    return f"claude/issue-{issue}-{run_id}"


def with_closes(body, issue):
    """The body with a `Closes #<issue>` line, added when the worker's text lacks one."""
    closes = re.compile(
        rf"^\s*closes\s+(?:[\w.-]+/[\w.-]+)?#{issue}\b", re.IGNORECASE | re.MULTILINE
    )
    if closes.search(body or ""):
        return body
    return f"{(body or '').rstrip()}\n\nCloses #{issue}\n"


def git(*args, cwd=None):
    # Hooks off: nothing the worker authored may run while its branch is handled.
    result = subprocess.run(
        ["git", "-c", "core.hooksPath=" + os.devnull, *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def gh(*args):
    result = subprocess.run(["gh", *args], check=True, capture_output=True, text=True)
    return result.stdout.strip()


def publish(*, issue, run_id, default_branch, out_dir, reviewer, repo_dir=None):
    """Push the worker's branch, open its PR, move the issue to review. Returns the PR number.

    Returns None when the worker left no bundle.
    """
    out_dir = Path(out_dir)
    bundle = out_dir / "work.bundle"
    if not bundle.exists():
        print(f"#{issue}: no work.bundle, the worker made no commits; nothing to publish")
        return None

    branch = branch_name(issue, run_id)
    git("bundle", "verify", str(bundle), cwd=repo_dir)
    git("fetch", str(bundle), f"HEAD:refs/heads/{branch}", cwd=repo_dir)
    git("push", "origin", f"refs/heads/{branch}:refs/heads/{branch}", cwd=repo_dir)

    description = out_dir / "pr-body.md"
    body = description.read_text(encoding="utf-8") if description.exists() else ""
    risk = parse_risk(body)
    final = out_dir / "pr-body.final.md"
    final.write_text(with_closes(body, issue), encoding="utf-8")

    create = [
        "pr",
        "create",
        "--head",
        branch,
        "--base",
        default_branch,
        "--title",
        git("log", "-1", "--format=%s", f"refs/heads/{branch}", cwd=repo_dir),
        "--body-file",
        str(final),
    ]
    if needs_human_review(risk) and reviewer:
        # No reviewer to ask is not a failure after the branch is pushed: the
        # `waiting-human-review` and `risk-tier` holds still stop the merge.
        create += ["--reviewer", reviewer]
    url = gh(*create)
    gh("issue", "edit", str(issue), "--remove-label", IN_PROGRESS, "--add-label", REVIEW)
    print(f"#{issue}: opened {url} (risk {risk or 'unreadable'})")
    return int(url.rstrip("/").rsplit("/", 1)[1])


def main():
    # Credential helper for the push, backed by GH_TOKEN (the bot PAT).
    gh("auth", "setup-git")
    number = publish(
        issue=os.environ["ISSUE_NUMBER"],
        run_id=os.environ["RUN_ID"],
        default_branch=os.environ["DEFAULT_BRANCH"],
        out_dir=os.environ.get("LANE_OUT", "lane-out"),
        reviewer=os.environ.get("LANE_REVIEWER", ""),
    )
    if number is not None and os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as out:
            out.write(f"pr={number}\n")


if __name__ == "__main__":
    main()
