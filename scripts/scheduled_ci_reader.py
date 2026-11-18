"""Morning reader of scheduled CI runs (#2225).

A scheduled workflow run (a nightly, a weekly scan) sits on no pull request, so
a red one is seen by nobody. This reader is run once a morning by a desktop
scheduled task on the routine host. For every line of
``config/scheduled-ci.conf`` it reads the workflow's run history through ``gh``
and sends to Telegram, through ``scripts/notify_telegram.py``:

- a message on the first red run of a workflow, and again when the set of
  failing jobs changes — an unchanged red streak stays silent;
- every Monday a summary, one line per watched workflow, also when everything
  is green. A missing Monday summary means the reader itself is down.

It sends messages only: it opens no PR and blocks nothing.

Split: the decision core (``parse_watch_conf``, ``decide``, ``alert_message``,
``weekly_summary``) is pure — no I/O, no clock. ``run`` is the I/O shell: ``gh``
reads, the state and send log on this machine (never in the repo), the sends.
A workflow's state is written only after its message went out, so a failed send
is retried the next morning. A failed send or a failed read prints a
``scheduled_ci_reader: FAILED — …`` line and makes the run exit non-zero.

Usage::

    python -m scripts.scheduled_ci_reader            # live, routine host only
    python -m scripts.scheduled_ci_reader --dry-run  # read, print, send nothing
    python -m scripts.scheduled_ci_reader --dry-run --since 2026-10-31

Reference: docs/reference/scheduled-ci-reader.md.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from scripts.gather_common import RunGhFn, _default_run_gh
from scripts.notify_telegram import NotifyError, PostFn, _urllib_post, repo_env_file, resolve_env
from scripts.notify_telegram import send as telegram_send
from scripts.weekly_release_engine import is_routine_host

NAME = "scheduled_ci_reader"
WATCH_CONF_RELPATH = "config/scheduled-ci.conf"
DEVICE_CONF_RELPATH = "config/device.json"
DEFAULT_STATE_DIR = Path.home() / ".jarvis" / "scheduled-ci"
PER_PAGE = 50

# A run is red on these conclusions and green on `success`. Everything else
# (cancelled, skipped, neutral, ...) neither starts nor ends a red streak.
RED = frozenset({"failure", "timed_out", "startup_failure"})
GREEN = "success"


class ReadError(RuntimeError):
    """A ``gh`` read failed or returned something that is not the expected JSON."""


@dataclass(frozen=True)
class Watch:
    repo: str
    workflow: str
    event: str = "schedule"

    @property
    def label(self) -> str:
        return f"{self.repo} {self.workflow}"

    @property
    def key(self) -> str:
        return f"{self.repo} {self.workflow} {self.event}"


@dataclass(frozen=True)
class Alert:
    run: dict
    jobs: list[str]
    previous: list[str] | None  # None: a new red streak; a list: the set it replaced


@dataclass(frozen=True)
class Decision:
    alerts: list[Alert]
    state: dict


# -- Decision core (pure) -------------------------------------------------------


def parse_watch_conf(text: str) -> list[Watch]:
    """``owner/repo workflow-file [event=<name>]`` per line; blank and ``#`` lines skipped."""
    watches: list[Watch] = []
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        if len(fields) < 2 or "/" not in fields[0] or "=" in fields[1]:
            raise ValueError(
                f"line {number}: expected 'owner/repo workflow-file [event=<name>]', got {line!r}"
            )
        event = "schedule"
        for token in fields[2:]:
            key, _, value = token.partition("=")
            if key != "event" or not value:
                raise ValueError(f"line {number}: unknown token {token!r}")
            event = value
        watches.append(Watch(fields[0], fields[1], event))
    return watches


def _matching(watch: Watch, runs: list[dict]) -> list[dict]:
    """The watch's runs, oldest first."""
    own = [r for r in runs if r.get("event", watch.event) == watch.event]
    return sorted(own, key=lambda r: (r["created_at"], r["id"]))


def _after(cursor: dict, run: dict) -> bool:
    attempt = run.get("run_attempt") or 1
    return run["id"] > cursor["id"] or (run["id"] == cursor["id"] and attempt > cursor["attempt"])


def decide(
    watch: Watch,
    runs: list[dict],
    wstate: dict | None,
    failing_jobs_for: Callable[[dict], list[str]],
    since: str | None = None,
) -> Decision:
    """Walk the runs not handled yet, oldest first, and say what to report.

    ``wstate`` is ``{"cursor": {"id", "attempt"} | None, "red": {"jobs", "since"} | None}``
    or ``None`` on the first read of a workflow. With no cursor only the newest
    completed run is handled, so a first run does not replay history. ``since``
    (a ``YYYY-MM-DD`` date) replaces the stored state: every run created on or
    after it is walked from a green start.
    """
    matching = _matching(watch, runs)
    cursor = (wstate or {}).get("cursor")
    red = (wstate or {}).get("red")
    if since is not None:
        cursor, red = None, None
        new = [r for r in matching if r["created_at"][:10] >= since]
    elif cursor is None:
        new = [r for r in matching if r.get("status") == "completed"][-1:]
    else:
        new = [r for r in matching if _after(cursor, r)]

    alerts: list[Alert] = []
    for run in new:
        if run.get("status") != "completed":
            break  # still running: this run and everything after it wait for a later morning
        cursor = {"id": run["id"], "attempt": run.get("run_attempt") or 1}
        conclusion = run.get("conclusion")
        if conclusion in RED:
            jobs = failing_jobs_for(run)
            if red is None:
                alerts.append(Alert(run, jobs, None))
                red = {"jobs": jobs, "since": run["created_at"][:10]}
            elif red["jobs"] != jobs:
                alerts.append(Alert(run, jobs, red["jobs"]))
                red = {**red, "jobs": jobs}
        elif conclusion == GREEN:
            red = None
    return Decision(alerts, {"cursor": cursor, "red": red})


def failing_jobs(run: dict, jobs: list[dict]) -> list[str]:
    """Sorted names of the run's red jobs; a run with none is named by its conclusion."""
    names = sorted({j["name"] for j in jobs if j.get("conclusion") in RED})
    return names or [f"(no failed job: {run.get('conclusion')})"]


def alert_message(watch: Watch, alerts: list[Alert]) -> tuple[str, str]:
    blocks = []
    for alert in alerts:
        what = (
            "new red run"
            if alert.previous is None
            else f"failing jobs changed (was: {', '.join(alert.previous)})"
        )
        blocks.append(
            f"{alert.run['created_at'][:10]} — {what}\n"
            f"Failing jobs: {', '.join(alert.jobs)}\n"
            f"{alert.run['html_url']}"
        )
    return f"Scheduled CI red: {watch.label}", "\n\n".join(blocks)


def summary_monday(today: date) -> date:
    """The most recent Monday on or before ``today``."""
    return today - timedelta(days=today.weekday())


def weekly_summary(
    watches: list[Watch],
    runs_by_watch: Mapping[str, list[dict] | None],
    today: date,
    last_summary_date: str | None,
) -> tuple[str, str] | None:
    """The Monday summary, or ``None`` when this week's has already gone out.

    Due when the most recent Monday is later than ``last_summary_date``, so a
    host that was off on Monday sends it the next morning. Counts the completed
    runs created in the 7 days before that Monday; ``None`` runs mean the read
    failed. Returned also when every run is green: that is the point of it.
    """
    monday = summary_monday(today)
    if last_summary_date is not None and last_summary_date >= monday.isoformat():
        return None
    start, end = (monday - timedelta(days=7)).isoformat(), monday.isoformat()
    lines = []
    for watch in watches:
        runs = runs_by_watch.get(watch.key)
        if runs is None:
            lines.append(f"{watch.label}: read failed")
            continue
        week = [
            r
            for r in _matching(watch, runs)
            if r.get("status") == "completed" and start <= r["created_at"][:10] < end
        ]
        red = sum(1 for r in week if r.get("conclusion") in RED)
        lines.append(f"{watch.label}: {len(week)} runs, {red} red")
    last_day = (monday - timedelta(days=1)).isoformat()
    return f"Scheduled CI weekly summary: {start}..{last_day}", "\n".join(lines)


# -- I/O shell -------------------------------------------------------------------


def _gh_json(run_gh: RunGhFn, watch: Watch, path: str) -> dict:
    reply = run_gh(watch.repo, ["api", path])
    if reply.get("returncode") != 0:
        raise ReadError(reply.get("stderr") or f"gh exited {reply.get('returncode')}")
    try:
        data = json.loads(reply.get("stdout") or "")
    except json.JSONDecodeError as exc:
        raise ReadError(f"unparsable gh reply: {exc}") from None
    if not isinstance(data, dict):
        raise ReadError("unparsable gh reply: not an object")
    return data


def fetch_runs(run_gh: RunGhFn, watch: Watch) -> list[dict]:
    path = (
        f"repos/{watch.repo}/actions/workflows/{watch.workflow}/runs"
        f"?event={watch.event}&per_page={PER_PAGE}"
    )
    runs = _gh_json(run_gh, watch, path).get("workflow_runs")
    if not isinstance(runs, list):
        raise ReadError("unparsable gh reply: no workflow_runs")
    return runs


def fetch_failing_jobs(run_gh: RunGhFn, watch: Watch, run: dict) -> list[str]:
    path = f"repos/{watch.repo}/actions/runs/{run['id']}/jobs?filter=latest&per_page=100"
    return failing_jobs(run, _gh_json(run_gh, watch, path).get("jobs") or [])


def _load_state(state_dir: Path) -> dict:
    path = state_dir / "state.json"
    state = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    state.setdefault("last_summary", None)
    state.setdefault("workflows", {})
    return state


def _save_state(state_dir: Path, state: dict) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    tmp = state_dir / "state.json.tmp"
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(state_dir / "state.json")


def _log(state_dir: Path, kind: str, workflow: str, result: str) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": datetime.now(UTC).isoformat(timespec="seconds"),
        "kind": kind,
        "workflow": workflow,
        "result": result,
    }
    with (state_dir / "log.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _failed(text: str) -> None:
    print(f"{NAME}: FAILED — {text}", file=sys.stderr)


def run(
    watches: list[Watch],
    *,
    state_dir: Path,
    today: date,
    run_gh: RunGhFn = _default_run_gh,
    post: PostFn = _urllib_post,
    env: Mapping[str, str],
    dry_run: bool = False,
    since: str | None = None,
) -> int:
    """Read every watched workflow, send what is due, remember what was sent.

    Returns the exit code: 0, or 1 when any read or any send failed.
    """
    try:
        state = _load_state(state_dir)
    except (OSError, ValueError) as exc:
        _failed(f"state file unreadable: {exc}")
        return 1
    saved = copy.deepcopy(state)
    code = 0

    def deliver(kind: str, workflow: str, message: tuple[str, str]) -> bool:
        subject, body = message
        if dry_run:
            print(f"--- would send ({kind}) ---\n{subject}\n\n{body}\n")
            return True
        try:
            telegram_send(subject, body, env, post)
        except NotifyError as exc:
            _failed(str(exc))
            _log(state_dir, kind, workflow, "failed")
            return False
        _log(state_dir, kind, workflow, "ok")
        return True

    def commit() -> None:
        nonlocal saved
        if not dry_run and state != saved:
            _save_state(state_dir, state)
            saved = copy.deepcopy(state)

    runs_by_watch: dict[str, list[dict] | None] = {}
    for watch in watches:
        wstate = state["workflows"].get(watch.key)
        try:
            runs = fetch_runs(run_gh, watch)
            decision = decide(
                watch, runs, wstate, lambda r, w=watch: fetch_failing_jobs(run_gh, w, r), since
            )
        except ReadError as exc:
            _failed(f"{watch.label}: {exc}")
            runs_by_watch.setdefault(watch.key, None)
            code = 1
            continue
        runs_by_watch[watch.key] = runs
        cursor = (wstate or {}).get("cursor")
        if since is None and cursor and len(runs) >= PER_PAGE:
            if cursor["id"] < min(r["id"] for r in runs):
                print(
                    f"{NAME}: GAP — {watch.label}: the last handled run is older than the "
                    f"{PER_PAGE} runs read; runs in between were not read"
                )
        if decision.alerts and not deliver(
            "alert", watch.key, alert_message(watch, decision.alerts)
        ):
            code = 1
            continue  # state not committed: the alert is retried on the next run
        state["workflows"][watch.key] = decision.state
        commit()

    summary = weekly_summary(watches, runs_by_watch, today, state["last_summary"])
    if summary is not None:
        if deliver("summary", "all", summary):
            state["last_summary"] = summary_monday(today).isoformat()
            commit()
        else:
            code = 1

    if dry_run:
        print("--- state a live run would write ---")
        print(json.dumps(state, indent=2, ensure_ascii=False))
    return code


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
    parser = argparse.ArgumentParser(prog=f"python -m scripts.{NAME}", description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", help="read and print; send and write nothing"
    )
    parser.add_argument(
        "--since", metavar="YYYY-MM-DD", help="dry run only: replay runs from this date"
    )
    parser.add_argument("--state-dir", type=Path, default=DEFAULT_STATE_DIR)
    args = parser.parse_args(argv)
    root = root or Path(__file__).resolve().parents[1]

    if args.since is not None:
        if not args.dry_run:
            print(f"{NAME}: --since needs --dry-run", file=sys.stderr)
            return 2
        try:
            date.fromisoformat(args.since)
        except ValueError:
            print(f"{NAME}: --since is not a YYYY-MM-DD date", file=sys.stderr)
            return 2

    if not args.dry_run:
        # Same gate as /weekly-release Step 0: one device is the routine host,
        # every other one refuses, so two devices never report the same run.
        try:
            device = json.loads((root / DEVICE_CONF_RELPATH).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            device = {}
        if not isinstance(device, dict) or not is_routine_host(device):
            print(
                f"refused: routines are host-only ({DEVICE_CONF_RELPATH} routine_host != true); "
                "use --dry-run to read without sending.",
                file=sys.stderr,
            )
            return 1

    try:
        watches = parse_watch_conf((root / WATCH_CONF_RELPATH).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _failed(f"{WATCH_CONF_RELPATH}: {exc}")
        return 1

    # A scheduled session has no environment prepared: notify_telegram's loader
    # fills the Telegram keys from the repo's .env, the process environment wins.
    env = resolve_env(environ, repo_env_file() if env_file == "repo" else env_file)
    return run(
        watches,
        state_dir=args.state_dir,
        today=today or date.today(),
        run_gh=run_gh,
        post=post,
        env=env,
        dry_run=args.dry_run,
        since=args.since,
    )


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(errors="replace")
    raise SystemExit(main(sys.argv[1:]))
