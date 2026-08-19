"""I/O adapter for the `morning` daily-digest capability (#1586).

Fan-out gather across ALL repos in config/repos.conf (including any marked
inactive by a trailing repos.conf token — parse_repos_conf already discards
every token but the first, so no new filtering logic is needed here), plus
goals, open milestones, decision-episodes, and owner tasks.

Deliberately built on the SAME injectable I/O callables as status_gather.py
(RunGhFn, QuerySupabaseFn, ReadReposConfFn) and reuses its pure helpers
(parse_repos_conf, _gather_gh_milestones, gather_decisions) rather than
introducing a parallel seam. This module does not modify status_gather.py or
status_engine.py, and their tests are unaffected.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from scripts.detector_gap_log import GapRecord, GapStore
from scripts.escalation_dedup import (
    CHANNEL_DIGEST,
    CHANNEL_SESSION_START,
    filter_for_channel,
    today_utc,
)
from scripts.status_gather import (
    REPOS_CONF_RELPATH,
    SUPABASE_KEY_ENV,
    SUPABASE_URL_ENV,
    DecisionRecord,
    NowFn,
    Provenance,
    QuerySupabaseFn,
    ReadReposConfFn,
    RunGhFn,
    _default_query_supabase,
    _default_read_repos_conf,
    _default_run_gh,
    _gather_gh_milestones,
    gather_decisions,
)

# Injectable type aliases for escalation dedup (both are keyed by date string).
# Read: (date_str) -> {channel: [ids]}; Write: (date_str, channel, ids) -> None.
# Defaults use scripts.escalation_dedup.read_shown/write_shown with a live client;
# tests inject in-memory replacements to avoid network calls.
ReadDedupFn = Callable[[str], dict[str, list[str]]]
WriteDedupFn = Callable[[str, str, list[str]], None]

# ============================================================================
# Canonical source identifiers
# ============================================================================


class MorningSourceKind:
    """Canonical source identifiers for morning-gather provenance tracking."""

    REPOS_CONF = "repos_conf"
    GH_MILESTONES = "gh_milestones"
    CLOSED_MILESTONES = "closed_milestones"
    SUPABASE_DECISIONS = "supabase_decisions"
    GOALS = "goals"
    OWNER_TASKS = "owner_tasks"
    DETECTOR_GAPS = "detector_gaps"


# ============================================================================
# Result container — contract for morning_engine.analyze()
# ============================================================================


@dataclass
class MorningGatherResult:
    repos: list[str] = field(default_factory=list)
    milestones: dict[str, list[dict]] = field(default_factory=dict)
    closed_milestones: dict[str, list[dict]] = field(default_factory=dict)
    decisions: list[DecisionRecord] = field(default_factory=list)
    goals: list[dict] = field(default_factory=list)
    owner_tasks: list[dict] = field(default_factory=list)
    detector_gaps: list[GapRecord] = field(default_factory=list)
    provenance: dict[str, dict] = field(default_factory=dict)
    gathered_at: str = ""
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "repos": self.repos,
            "milestones": self.milestones,
            "closed_milestones": self.closed_milestones,
            "decisions": [d.to_dict() for d in self.decisions],
            "goals": self.goals,
            "owner_tasks": self.owner_tasks,
            "detector_gaps": [
                {"key": g.key, "description": g.description, "count": g.count}
                for g in self.detector_gaps
            ],
            "provenance": self.provenance,
            "gathered_at": self.gathered_at,
            "errors": self.errors,
        }


# ============================================================================
# New sources — goals, owner tasks (no equivalent in status_gather.py)
# ============================================================================


def gather_goals(
    url: str,
    key: str,
    query_fn: QuerySupabaseFn,
    now: float,
) -> tuple[list[dict], Provenance]:
    """Query Supabase `goals` for active goals (mirrors session-context.py's
    _query_goals: status=active, ordered by priority then deadline)."""
    start = time.time()
    params = {
        "status": "eq.active",
        "select": "*",
        "order": "priority.asc,deadline.asc.nullslast",
    }
    rows = query_fn(url, key, "goals", params)
    elapsed = time.time() - start

    if rows is None:
        return [], Provenance(ran=True, ok=False, input_rows=0, age=elapsed)
    return rows, Provenance(ran=True, ok=True, input_rows=len(rows), age=elapsed)


def _gather_gh_closed_milestones(
    repo: str,
    run_gh: RunGhFn,
    now: float,
) -> tuple[list[dict], Provenance]:
    """Fetch closed milestones for one repo (for architecture-sweep detection).

    Returns milestones with {number, title, closed_at, open_issues, closed_issues}.
    """
    start = time.time()
    result = run_gh(
        repo,
        [
            "api",
            f"repos/{repo}/milestones?state=closed&per_page=50",
            "--jq",
            ".[] | {number, title, closed_at, open_issues, closed_issues}",
        ],
    )
    elapsed = time.time() - start
    ok = result["returncode"] == 0
    data: list[dict] = []
    if ok and result["stdout"]:
        for line in result["stdout"].splitlines():
            if line.strip():
                try:
                    data.append(json.loads(line))
                except json.JSONDecodeError:
                    ok = False
    prov = Provenance(ran=True, ok=ok, input_rows=len(data), age=elapsed)
    return data, prov


def gather_owner_tasks(
    url: str,
    key: str,
    query_fn: QuerySupabaseFn,
    now: float,
    *,
    date_str: str | None = None,
    read_dedup_fn: "ReadDedupFn | None" = None,
    write_dedup_fn: "WriteDedupFn | None" = None,
) -> tuple[list[dict], Provenance]:
    """Query Supabase `task_queue` for pending owner tasks (mirrors
    session-context.py's _query_owner_tasks: assignee=owner, status=pending).

    Applies escalation dedup (#1591): filters out tasks already shown by the
    session_start channel today, then marks the returned tasks as shown by the
    digest channel. read_dedup_fn/write_dedup_fn default to no-ops when None
    (production path uses the inject from gather()).
    """
    start = time.time()
    params = {
        "assignee": "eq.owner",
        "status": "eq.pending",
        "select": "*",
        "order": "priority.desc,created_at.asc",
    }
    rows = query_fn(url, key, "task_queue", params)
    elapsed = time.time() - start

    if rows is None:
        return [], Provenance(ran=True, ok=False, input_rows=0, age=elapsed)

    # Dedup: skip tasks already shown by the session_start channel today.
    if read_dedup_fn is not None:
        today = date_str or today_utc()
        shown = read_dedup_fn(today).get(CHANNEL_SESSION_START, [])
        rows = filter_for_channel(rows, shown)

    # Mark the tasks we are about to show as shown by the digest channel.
    if write_dedup_fn is not None and rows:
        today = date_str or today_utc()
        ids = [str(t.get("id", "")) for t in rows if t.get("id")]
        write_dedup_fn(today, CHANNEL_DIGEST, ids)

    return rows, Provenance(ran=True, ok=True, input_rows=len(rows), age=elapsed)


# ============================================================================
# Live dedup factory — creates default read/write fns from live Supabase client
# ============================================================================


def _make_live_dedup_fns(
    url: str, key: str
) -> tuple["ReadDedupFn", "WriteDedupFn"] | tuple[None, None]:
    """Return (read_fn, write_fn) backed by a live Supabase client.

    On client creation failure, returns (None, None) — callers already treat
    a None read/write fn as "dedup unavailable, continue without it" (worst
    case: an escalation shows in both channels once).
    """
    from scripts.escalation_dedup import read_shown, write_shown

    try:
        from supabase import create_client

        client = create_client(url, key)
    except Exception as exc:
        print(f"[morning_gather] dedup client creation failed: {exc}", file=sys.stderr)
        return None, None

    def _read(date_str: str) -> dict[str, list[str]]:
        return read_shown(client, date_str)

    def _write(date_str: str, channel: str, ids: list[str]) -> None:
        write_shown(client, date_str, channel, ids)

    return _read, _write


# ============================================================================
# Main gather orchestrator
# ============================================================================


def gather(
    jarvis_home: str = "",
    *,
    read_repos_conf_fn: ReadReposConfFn | None = None,
    run_gh_fn: RunGhFn | None = None,
    query_supabase_fn: QuerySupabaseFn | None = None,
    now_fn: NowFn | None = None,
    gap_store: GapStore | None = None,
    read_dedup_fn: "ReadDedupFn | None" = None,
    write_dedup_fn: "WriteDedupFn | None" = None,
) -> MorningGatherResult:
    """Gather state for the morning digest.

    Reuses status_gather's injectable callables and pure helpers — no new I/O
    seam. Traverses every repo in repos.conf (including any marked inactive
    by a trailing token, since parse_repos_conf discards all but the first
    token per line).

    read_dedup_fn/write_dedup_fn: injectable escalation dedup state (#1591).
    Defaults to live Supabase dedup when creds are available; pass in-memory
    implementations in tests to avoid network calls.
    """
    _read_conf = read_repos_conf_fn or _default_read_repos_conf
    _run_gh = run_gh_fn or _default_run_gh
    _query_supabase = query_supabase_fn or _default_query_supabase
    _now = now_fn or time.time

    gather_start = _now()
    gathered_at = datetime.fromtimestamp(gather_start, tz=timezone.utc).isoformat()
    result = MorningGatherResult(gathered_at=gathered_at)

    if not jarvis_home:
        jarvis_home = os.environ.get("JARVIS_HOME", "").strip()
    if not jarvis_home:
        try:
            git_result = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                capture_output=True,
                text=True,
                stdin=subprocess.DEVNULL,
                timeout=5,
            )
            if git_result.returncode == 0:
                jarvis_home = git_result.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            pass
    if not jarvis_home:
        jarvis_home = os.getcwd()

    jarvis_path = Path(jarvis_home)

    # --- Repos (all of them, including any marked inactive) ---
    conf_path = str(jarvis_path / REPOS_CONF_RELPATH)
    repos = _read_conf(conf_path)

    if not repos:
        result.provenance[MorningSourceKind.REPOS_CONF] = Provenance(
            ran=True, ok=False, input_rows=0, age=_now() - gather_start
        ).to_dict()
        result.errors.append("repos.conf is empty, unreadable, or not found")
        return result

    result.repos = [r.strip() for r in repos]
    result.provenance[MorningSourceKind.REPOS_CONF] = Provenance(
        ran=True, ok=True, input_rows=len(repos), age=_now() - gather_start
    ).to_dict()

    # --- Open milestones per repo (reused from status_gather unmodified) ---
    milestones_ok_count = 0
    for repo_name in result.repos:
        milestones_state, milestones_prov = _gather_gh_milestones(repo_name, _run_gh, _now())
        result.milestones[repo_name] = milestones_state.get("milestones") or []
        if milestones_prov.ok:
            milestones_ok_count += 1
    result.provenance[MorningSourceKind.GH_MILESTONES] = Provenance(
        ran=True,
        ok=milestones_ok_count > 0,
        input_rows=milestones_ok_count,
        age=_now() - gather_start,
    ).to_dict()

    # --- Closed milestones per repo (for architecture-sweep detection, #1590) ---
    closed_milestones_ok_count = 0
    for repo_name in result.repos:
        closed_ms, closed_prov = _gather_gh_closed_milestones(repo_name, _run_gh, _now())
        result.closed_milestones[repo_name] = closed_ms
        if closed_prov.ok:
            closed_milestones_ok_count += 1
    result.provenance[MorningSourceKind.CLOSED_MILESTONES] = Provenance(
        ran=True,
        ok=closed_milestones_ok_count > 0,
        input_rows=closed_milestones_ok_count,
        age=_now() - gather_start,
    ).to_dict()

    # --- Supabase-backed sources: decisions, goals, owner tasks ---
    supabase_url = os.environ.get(SUPABASE_URL_ENV, "")
    supabase_key = os.environ.get(SUPABASE_KEY_ENV, "")

    if supabase_url and supabase_key:
        decisions, decisions_prov = gather_decisions(
            supabase_url, supabase_key, _query_supabase, _now()
        )
        result.decisions = decisions
        result.provenance[MorningSourceKind.SUPABASE_DECISIONS] = decisions_prov.to_dict()
        if not decisions_prov.ok:
            result.errors.append(
                f"{MorningSourceKind.SUPABASE_DECISIONS}: query returned no data or failed"
            )

        goals, goals_prov = gather_goals(supabase_url, supabase_key, _query_supabase, _now())
        result.goals = goals
        result.provenance[MorningSourceKind.GOALS] = goals_prov.to_dict()
        if not goals_prov.ok:
            result.errors.append(f"{MorningSourceKind.GOALS}: query returned no data or failed")

        # Build default live dedup fns when none injected — requires a full client
        # (not just the RestFn) for UPDATE/INSERT support.
        _read_dedup = read_dedup_fn
        _write_dedup = write_dedup_fn
        if _read_dedup is None or _write_dedup is None:
            _read_dedup, _write_dedup = _make_live_dedup_fns(supabase_url, supabase_key)

        owner_tasks, tasks_prov = gather_owner_tasks(
            supabase_url,
            supabase_key,
            _query_supabase,
            _now(),
            read_dedup_fn=_read_dedup,
            write_dedup_fn=_write_dedup,
        )
        result.owner_tasks = owner_tasks
        result.provenance[MorningSourceKind.OWNER_TASKS] = tasks_prov.to_dict()
        if not tasks_prov.ok:
            result.errors.append(
                f"{MorningSourceKind.OWNER_TASKS}: query returned no data or failed"
            )
    else:
        for kind in (
            MorningSourceKind.SUPABASE_DECISIONS,
            MorningSourceKind.GOALS,
            MorningSourceKind.OWNER_TASKS,
        ):
            result.provenance[kind] = Provenance(
                ran=True, ok=False, input_rows=0, age=_now() - gather_start
            ).to_dict()
            result.errors.append(f"{kind}: {SUPABASE_URL_ENV}/{SUPABASE_KEY_ENV} unset")

    # ceiling: no production GapStore adapter exists yet — gap_store defaults to
    # None so detector_gaps stays empty until a caller injects a real store; the
    # memory-backed adapter wrapping mcp__memory__* is the upgrade path (#1595).
    if gap_store is not None:
        gaps = gap_store.load_all()
        result.detector_gaps = gaps
        result.provenance[MorningSourceKind.DETECTOR_GAPS] = Provenance(
            ran=True, ok=True, input_rows=len(gaps), age=_now() - gather_start
        ).to_dict()
    else:
        result.provenance[MorningSourceKind.DETECTOR_GAPS] = Provenance(
            ran=False, ok=False, input_rows=0, age=_now() - gather_start
        ).to_dict()

    return result


def main(argv: list[str] | None = None) -> int:
    result = gather()
    json.dump(result.to_dict(), sys.stdout, indent=2, default=str)
    return 0 if not result.errors else 1


if __name__ == "__main__":
    sys.exit(main())
