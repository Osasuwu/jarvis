"""Fixing step in front of the scheduled CI reader's message (#2226).

The reader (``scripts/scheduled_ci_reader.py``) used to send a red scheduled
run to Telegram as it found it. With this step in front, the morning session
queues the run, an agent reads its log and works under the affected repo's own
rules file, and one message goes out saying what came of it: a PR, a diagnosis
with the rule that needs a person, or that the cause was not found.

This module is the deterministic half. The agent's instructions are
``docs/reference/scheduled-ci-fixer-prompt.md``; nothing here judges a cause.

    python -m scripts.scheduled_ci_fixer start     # send leftovers, read, queue red runs
    python -m scripts.scheduled_ci_fixer next      # the oldest queued item, or "none"
    python -m scripts.scheduled_ci_fixer report --run <id> --outcome pr --pr-url <url>
    python -m scripts.scheduled_ci_fixer report --run <id> --outcome needs-person \\
        --rule "<the rule>" --diagnosis "<two or three lines>"
    python -m scripts.scheduled_ci_fixer report --run <id> --outcome cause-not-found \\
        --diagnosis "<what was checked>"
    python -m scripts.scheduled_ci_fixer finish    # whatever is left goes out as "not diagnosed"

An item's message is sent exactly once, by ``report``, by ``finish`` or by the
next ``start``; its workflow state is committed with it, so no red run stays
silent and none is reported twice. ``--dry-run`` needs an explicit
``--state-dir``, sends nothing and prints the messages; its only write is
``start`` storing ``pending.json`` there.

Reference: docs/reference/scheduled-ci-fixer.md.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Mapping
from datetime import date
from pathlib import Path

from scripts import scheduled_ci_reader as reader
from scripts.gather_common import RunGhFn, _default_run_gh
from scripts.notify_telegram import NotifyError, PostFn, _urllib_post, repo_env_file, resolve_env
from scripts.notify_telegram import send as telegram_send

NAME = "scheduled_ci_fixer"
BRANCH_PREFIX = "scheduled-ci-fix/"  # the one branch the agent may create is <prefix><run id>
OUTCOMES = ("pr", "needs-person", "cause-not-found")
NOT_DIAGNOSED = "not-diagnosed"
RULE_MAX = 200
DIAGNOSIS_MAX = 600
DIAGNOSIS_LINES = 3
# Left free in a queued alert for the outcome block: its fixed words, the rule or
# the PR link, and the diagnosis, each at its limit.
OUTCOME_ROOM = 1000
PUBLIC_KEYS = ("watch_key", "repo", "workflow", "run_id", "html_url", "head_sha", "failing_jobs")


# -- Pure core -------------------------------------------------------------------


def branch_for(item: dict) -> str:
    return f"{BRANCH_PREFIX}{item['run_id']}"


def report_problem(
    item: dict, outcome: str, pr_url: str | None, rule: str | None, diagnosis: str | None
) -> str | None:
    """Why this report cannot be sent as given, or ``None``."""
    if rule is not None and outcome != "needs-person":
        return "--rule goes with needs-person only"
    if pr_url is not None and outcome != "pr":
        return "--pr-url goes with pr only"
    if outcome == "pr":
        wanted = f"https://github.com/{item['repo']}/pull/"
        if pr_url is None or not re.fullmatch(re.escape(wanted) + r"[1-9][0-9]*", pr_url):
            return f"pr needs --pr-url {wanted}<n>"
    if outcome == "needs-person":
        rule_text = (rule or "").strip()
        if not rule_text:
            return "needs-person needs --rule"
        if "\n" in rule_text:
            return "--rule is more than one line"
        if len(rule_text) > RULE_MAX:
            return f"--rule is over {RULE_MAX} characters"
    text = (diagnosis or "").strip()
    if not text and outcome != "pr":
        return f"{outcome} needs --diagnosis"
    if len(text.splitlines()) > DIAGNOSIS_LINES:
        return f"--diagnosis is over {DIAGNOSIS_LINES} lines"
    if len(text) > DIAGNOSIS_MAX:
        return f"--diagnosis is over {DIAGNOSIS_MAX} characters"
    return None


def outcome_message(
    item: dict,
    outcome: str,
    pr_url: str | None = None,
    rule: str | None = None,
    diagnosis: str | None = None,
) -> tuple[str, str]:
    """The item's alert with a last block that says what the agent did.

    The block's first line names the kind, so the reader of the message never
    has to tell a PR from a diagnosis by its wording.
    """
    if outcome == "pr":
        head = f"Outcome: PR opened — {pr_url}"
    elif outcome == "needs-person":
        head = f"Outcome: needs a person — rule: {(rule or '').strip()}"
    elif outcome == "cause-not-found":
        head = "Outcome: cause not found"
    else:
        head = "Outcome: not diagnosed (the fixer session ended without a report)"
        diagnosis = None
    lines = [head, *(diagnosis or "").strip().splitlines()]
    return item["subject"], f"{item['body']}\n\n" + "\n".join(lines)


# -- I/O shell --------------------------------------------------------------------


def _failed(text: str) -> None:
    print(f"{NAME}: FAILED — {text}", file=sys.stderr)


def _gh_list(run_gh: RunGhFn, repo: str, path: str) -> list:
    reply = run_gh(repo, ["api", path])
    if reply.get("returncode") != 0:
        raise reader.ReadError(reply.get("stderr") or f"gh exited {reply.get('returncode')}")
    try:
        data = json.loads(reply.get("stdout") or "")
    except json.JSONDecodeError as exc:
        raise reader.ReadError(f"unparsable gh reply: {exc}") from None
    if not isinstance(data, list):
        raise reader.ReadError("unparsable gh reply: not a list")
    return data


def something_written(run_gh: RunGhFn, item: dict) -> bool:
    """True when the fixer branch of this item, or a PR from it, exists in the repo.

    Two reads, no write. A no-change outcome is refused on it: the message would
    say nothing was written while something was.
    """
    repo, branch = item["repo"], branch_for(item)
    owner = repo.split("/")[0]
    if _gh_list(run_gh, repo, f"repos/{repo}/pulls?head={owner}:{branch}&state=all&per_page=1"):
        return True
    refs = _gh_list(run_gh, repo, f"repos/{repo}/git/matching-refs/heads/{branch}")
    # matching-refs is a prefix match: the branch of run 31 also matches run 3.
    return any(ref.get("ref") == f"refs/heads/{branch}" for ref in refs)


def _settle(
    state_dir: Path,
    item: dict,
    outcome: str,
    *,
    env: Mapping[str, str],
    post: PostFn,
    dry_run: bool,
    pr_url: str | None = None,
    rule: str | None = None,
    diagnosis: str | None = None,
) -> bool:
    """Send the item's message; on success log it, commit its state, drop the item."""
    subject, body = outcome_message(item, outcome, pr_url, rule, diagnosis)
    if dry_run:
        print(f"--- would send (alert, {outcome}) ---\n{subject}\n\n{body}\n")
        return True
    extra = {"run_id": item["run_id"], "outcome": outcome}
    if pr_url is not None:
        extra["pr_url"] = pr_url
    try:
        telegram_send(subject, body, env, post)
    except NotifyError as exc:
        _failed(str(exc))
        reader._log(state_dir, "alert", item["watch_key"], "failed", **extra)
        return False
    reader._log(state_dir, "alert", item["watch_key"], "ok", **extra)
    state = reader._load_state(state_dir)
    state["workflows"][item["watch_key"]] = item["state"]
    reader._save_state(state_dir, state)
    reader.save_pending(
        state_dir, [i for i in reader.load_pending(state_dir) if i["run_id"] != item["run_id"]]
    )
    return True


def _mark_tried(state_dir: Path, item: dict, **tried: str | None) -> None:
    """Remember what a report that did not go out is still owed.

    ``next`` skips a tried item, so one stuck item never hides the ones behind
    it, and ``finish`` sends it with the outcome stored here: the reported one
    when only the send failed, "not diagnosed" when the report was refused.
    """
    items = reader.load_pending(state_dir)
    for queued in items:
        if queued["run_id"] == item["run_id"]:
            queued["tried"] = tried
    reader.save_pending(state_dir, items)


def _settle_all(state_dir: Path, **kwargs) -> int:
    """Everything still pending goes out: as it was reported when a report's send
    failed, else as "not diagnosed". Returns the exit code."""
    code = 0
    for item in reader.load_pending(state_dir):
        owed = item.get("tried") or {"outcome": NOT_DIAGNOSED}
        if not _settle(state_dir, item, **owed, **kwargs):
            code = 1
    return code


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=f"python -m scripts.{NAME}", description=__doc__)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--state-dir", type=Path)
    common.add_argument(
        "--dry-run", action="store_true", help="send nothing, print; needs --state-dir"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    start = sub.add_parser("start", parents=[common], help="send leftovers, read, queue red runs")
    start.add_argument("--since", metavar="YYYY-MM-DD", help="dry run only: replay from this date")
    sub.add_parser("next", parents=[common], help="print the oldest queued item, or none")
    report = sub.add_parser("report", parents=[common], help="send one item's message")
    report.add_argument("--run", type=int, required=True, help="the item's run_id")
    report.add_argument("--outcome", choices=OUTCOMES, required=True)
    report.add_argument("--pr-url")
    report.add_argument("--rule", help="needs-person: the rule that needs a person, one line")
    report.add_argument("--diagnosis", help=f"at most {DIAGNOSIS_LINES} lines")
    sub.add_parser("finish", parents=[common], help='send what is left as "not diagnosed"')
    return parser


def main(
    argv: list[str],
    *,
    root: Path | None = None,
    run_gh: RunGhFn = _default_run_gh,
    post: PostFn = _urllib_post,
    today: date | None = None,
    environ: Mapping[str, str] = os.environ,
    env_file: Path | None | str = "repo",
) -> int:
    args = _parser().parse_args(argv)
    root = root or Path(__file__).resolve().parents[1]

    if args.dry_run and args.state_dir is None:
        # A dry run must never touch the live state: start --dry-run writes pending.json.
        print(f"{NAME}: --dry-run needs an explicit --state-dir", file=sys.stderr)
        return 2
    problem = reader.since_problem(getattr(args, "since", None), args.dry_run)
    if problem:
        print(f"{NAME}: {problem}", file=sys.stderr)
        return 2
    if not args.dry_run and not reader.on_routine_host(root):
        print(reader.HOST_REFUSAL, file=sys.stderr)
        return 1
    state_dir = args.state_dir or reader.DEFAULT_STATE_DIR

    try:
        items = reader.load_pending(state_dir)
    except (OSError, ValueError, KeyError) as exc:
        _failed(f"pending file unreadable: {exc}")
        return 1

    if args.command == "next":
        item = next((i for i in items if "tried" not in i), None)
        if item is None:
            print("none")
            return 0
        public = {**{key: item[key] for key in PUBLIC_KEYS}, "branch": branch_for(item)}
        print(json.dumps(public, indent=2, ensure_ascii=False))
        return 0

    env = resolve_env(environ, repo_env_file() if env_file == "repo" else env_file)
    send = {"env": env, "post": post, "dry_run": args.dry_run}

    if args.command == "report":
        item = next((i for i in items if i["run_id"] == args.run), None)
        problem = (
            f"no pending item for run {args.run}"
            if item is None
            else report_problem(item, args.outcome, args.pr_url, args.rule, args.diagnosis)
        )
        if problem:
            print(f"{NAME}: refused — {problem}", file=sys.stderr)
            return 2
        if args.outcome != "pr":
            label = f"{item['repo']} {item['workflow']}"
            try:
                written = something_written(run_gh, item)
            except reader.ReadError as exc:
                _failed(f"{label}: {exc}")
                written = None
            if written:
                _failed(
                    f"{label}: a PR or branch exists for a no-change outcome ({branch_for(item)})"
                )
            if written is not False:
                if not args.dry_run:
                    _mark_tried(state_dir, item, outcome=NOT_DIAGNOSED)
                return 1
        sent = _settle(
            state_dir,
            item,
            args.outcome,
            pr_url=args.pr_url,
            rule=args.rule,
            diagnosis=args.diagnosis,
            **send,
        )
        if not sent:
            _mark_tried(
                state_dir,
                item,
                outcome=args.outcome,
                pr_url=args.pr_url,
                rule=args.rule,
                diagnosis=args.diagnosis,
            )
        return 0 if sent else 1

    if args.command == "finish":
        return _settle_all(state_dir, **send)

    # start: what an earlier session left unreported goes out first, then the read.
    code = _settle_all(state_dir, **send)
    try:
        watches = reader.parse_watch_conf(
            (root / reader.WATCH_CONF_RELPATH).read_text(encoding="utf-8")
        )
    except (OSError, ValueError) as exc:
        _failed(f"{reader.WATCH_CONF_RELPATH}: {exc}")
        return 1
    read = reader.run(
        watches,
        state_dir=state_dir,
        today=today or date.today(),
        run_gh=run_gh,
        post=post,
        env=env,
        dry_run=args.dry_run,
        since=args.since,
        defer=True,
        outcome_room=OUTCOME_ROOM,
    )
    print(f"{NAME}: {len(reader.load_pending(state_dir))} pending")
    return max(code, read)


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(errors="replace")
    raise SystemExit(main(sys.argv[1:]))
