"""Morning check — read audit_log, surface what happened in the last 24h.

Run on any host with Supabase credentials (SUPABASE_URL / SUPABASE_KEY in env
or via agents.config.AgentConfig). Prints a text report; exits 0 on healthy,
1 on alarms, 2 on connection failure.

Usage:
    python -m scripts.observability.morning_check
    python -m scripts.observability.morning_check --hours 6
    python -m scripts.observability.morning_check --agent task-dispatcher
    python -m scripts.observability.morning_check --enqueue-on-alarm
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from agents.executor import _now_iso
from agents.scope_hash import _hash_scope_files
from agents.supabase_client import get_client

# Alarm categories for stable idempotency key generation
_ALARM_CATEGORIES = frozenset(
    {
        "high_failure_rate",
        "dispatcher_gap",
        "no_audit_rows",
        "wake_driver_silence",
        "events_cutover_leak",
    }
)

# #1493 AC5 migration cutover: memory_recall/fok_run rows are backfilled into
# events_canonical and purged from `events` as of this timestamp. Any row of
# these types landing in `events` at/after this point means a producer is
# still writing to the retired queue instead of events_canonical (AC7). This
# is an interim tripwire per decision 56b57d6c -- retired once
# _TELEMETRY_EVENT_TYPES drops these entries in #1524.
_EVENTS_CUTOVER_ISO = "2026-08-11T14:00:00+00:00"

# Repo-root-anchored, mirroring agents/wake_driver.py's _LOG_DIR pattern --
# this file sits two directories under repo root (scripts/observability/)
# vs. wake_driver.py's one (agents/).
_WAKE_DRIVER_LOG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "logs",
    "wake_driver",
    "wake_driver.log",
)


def _wake_driver_log_mtime() -> float | None:
    """Return the wake_driver log file's mtime (epoch seconds), or None if missing.

    A dedicated accessor so tests can mock filesystem state instead of
    depending on a real logs/wake_driver/wake_driver.log (#1479 AC3).
    """
    try:
        return os.path.getmtime(_WAKE_DRIVER_LOG_PATH)
    except OSError:
        return None


def _check_wake_driver_silence(gap_minutes: int) -> tuple[str, str] | None:
    """Return (details_bucket, alarm_message) if wake_driver's log is missing or stale.

    wake_driver never writes audit_log rows (it's an event-driven daemon,
    not a dispatched task) -- unlike dispatcher_gap, this can't be a
    row-timestamp-gap check, so it's file-mtime based instead, and it must
    run independent of whether audit_log has any rows at all (#1479 AC3).

    details_bucket is a coarse, day-stable category (not the elapsed-minute
    count) -- callers use it as _enqueue_alarm's idempotency-key material so
    one ongoing outage dedupes to a single task_queue row per day instead of
    re-keying on every run as the elapsed-time message grows (PR #1483 review).
    """
    mtime = _wake_driver_log_mtime()
    if mtime is None:
        return (
            "wake_driver:missing",
            "wake_driver: log file missing (logs/wake_driver/wake_driver.log) "
            "-- daemon may never have started",
        )
    age_min = (datetime.now(timezone.utc).timestamp() - mtime) / 60
    if age_min > gap_minutes:
        return (
            "wake_driver:stale",
            f"wake_driver: log silent for {age_min:.0f}min "
            f"(threshold {gap_minutes}min) -- daemon may be dead",
        )
    return None


def _check_events_cutover_leak(client: Any) -> tuple[str, str] | None:
    """Return (details_bucket, alarm_message) if memory_recall/fok_run rows have
    landed in `events` at/after the #1493 AC5 cutover.

    Runs against the live client (not audit_log) so it catches a producer
    regression even on a day with zero audit_log activity -- same rationale
    as the wake_driver check above.
    """
    resp = (
        client.table("events")
        .select("event_type")
        .in_("event_type", ["memory_recall", "fok_run"])
        .gte("created_at", _EVENTS_CUTOVER_ISO)
        .execute()
    )
    rows = resp.data or []
    if rows:
        return (
            "events_cutover:leak",
            f"events: {len(rows)} memory_recall/fok_run row(s) landed after the #1493 "
            f"cutover ({_EVENTS_CUTOVER_ISO}) -- a producer is still writing to the "
            "retired queue instead of events_canonical",
        )
    return None


def _fmt_ts(ts: str) -> str:
    return ts.replace("T", " ").split("+")[0].split(".")[0]


def _idempotency_key(category: str, details_summary: str) -> str:
    """Build idempotency key: sha256(YYYY-MM-DD | category | sha256(details_summary)).

    Date in UTC ensures the same alarm on the same day produces the same key,
    but a new day produces a fresh key even if the alarm repeats.
    """
    utc_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    details_hash = hashlib.sha256(details_summary.encode("utf-8")).hexdigest()
    formula = f"{utc_date}|{category}|{details_hash}"
    return hashlib.sha256(formula.encode("utf-8")).hexdigest()


def _enqueue_alarm(
    client: Any,
    category: str,
    details_summary: str,
    goal: str,
) -> None:
    """Enqueue a self-perception alarm as a tier:3-human task_queue row.

    Uses upsert with ignore_duplicates to ensure idempotency: the same alarm
    category + details on the same day produces the same key and never duplicates.
    If the upsert fails (network, auth), log and continue — enqueue is best-effort.
    """
    key = _idempotency_key(category, details_summary)
    now = _now_iso()

    row = {
        "goal": goal,
        "scope_files": [],
        "approved_by": "cron:morning_check",
        "approved_at": now,
        "approved_scope_hash": _hash_scope_files([]),  # sha256 of empty list
        "auto_dispatch": False,
        "idempotency_key": key,
        "status": "pending",
    }

    try:
        client.table("task_queue").upsert(
            row,
            on_conflict="idempotency_key",
            ignore_duplicates=True,
        ).execute()
        # Log first 12 chars of key for re-enqueue pattern detection
        print(f"  [enqueued alarm {key[:12]}... ({category})]", file=sys.stderr)
    except Exception as e:
        # Failure to enqueue doesn't mask the alarm — we already printed it.
        print(f"  [enqueue failed: {e}]", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--hours", type=int, default=24, help="Lookback window (default 24)")
    parser.add_argument("--agent", default=None, help="Filter to specific agent_id")
    parser.add_argument(
        "--gap-minutes",
        type=int,
        default=10,
        help="Flag gaps in dispatcher heartbeat exceeding N minutes (default 10)",
    )
    parser.add_argument(
        "--enqueue-on-alarm",
        action="store_true",
        default=False,
        help="Enqueue alarms as task_queue rows (default: off)",
    )
    parser.add_argument(
        "--wake-driver-gap-minutes",
        type=int,
        default=20,
        help="Flag wake_driver log silence exceeding N minutes (default 20)",
    )
    args = parser.parse_args(argv)

    try:
        client = get_client()
    except Exception as e:
        print(f"FAILED to connect to Supabase: {e}", file=sys.stderr)
        return 2

    alarms: list[str] = []

    # wake_driver never writes audit_log rows, so this check runs up front,
    # independent of the audit_log query below and its own rows/no-rows
    # branches (#1479 AC3).
    wake_driver_check = _check_wake_driver_silence(args.wake_driver_gap_minutes)
    if wake_driver_check:
        wake_driver_details, wake_driver_alarm = wake_driver_check
        alarms.append(wake_driver_alarm)
        if args.enqueue_on_alarm:
            _enqueue_alarm(client, "wake_driver_silence", wake_driver_details, wake_driver_alarm)

    # events cutover tripwire (#1493 AC7) -- also independent of audit_log,
    # runs against the live client directly.
    events_cutover_check = _check_events_cutover_leak(client)
    if events_cutover_check:
        events_cutover_details, events_cutover_alarm = events_cutover_check
        alarms.append(events_cutover_alarm)
        if args.enqueue_on_alarm:
            _enqueue_alarm(
                client, "events_cutover_leak", events_cutover_details, events_cutover_alarm
            )

    cutoff = datetime.now(timezone.utc) - timedelta(hours=args.hours)
    cutoff_iso = cutoff.isoformat()

    q = (
        client.table("audit_log")
        .select("agent_id, tool_name, action, target, outcome, timestamp, details")
        .gte("timestamp", cutoff_iso)
        .order("timestamp", desc=False)
    )
    if args.agent:
        q = q.eq("agent_id", args.agent)

    rows = q.execute().data or []

    if not rows:
        msg = (
            f"No audit_log rows in the last {args.hours}h"
            + (f" for agent {args.agent}" if args.agent else "")
            + "."
        )
        print(msg)
        print("If the dispatcher should be running, this is a RED FLAG — service may be down.")
        if args.enqueue_on_alarm:
            details = "no_audit_rows"
            _enqueue_alarm(client, "no_audit_rows", details, msg)
        if alarms:
            print()
            print("ALARMS:")
            for a in alarms:
                print(f"  - {a}")
        return 1

    # Per-agent rollup
    by_agent: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_agent[r["agent_id"] or "<null>"].append(r)

    print(f"=== Morning check - last {args.hours}h ===")
    print(f"Total rows: {len(rows)}")
    print(f"Window: {_fmt_ts(cutoff_iso)} -> now")
    print()
    print(f"{'agent_id':<30} {'rows':>6} {'failures':>10} {'first':<20} {'last':<20}")
    print("-" * 96)

    def _is_failure(outcome: str | None) -> bool:
        # 'failure:<ExceptionType>' is the canonical failure marker (see
        # agents/dispatcher.py docstring). 'success', 'dry_run', and any
        # other domain-specific outcome are NOT failures.
        return (outcome or "").startswith("failure")

    for agent, agent_rows in sorted(by_agent.items()):
        failures = [r for r in agent_rows if _is_failure(r["outcome"])]
        first = _fmt_ts(agent_rows[0]["timestamp"])
        last = _fmt_ts(agent_rows[-1]["timestamp"])
        print(f"{agent:<30} {len(agent_rows):>6} {len(failures):>10} {first:<20} {last:<20}")
        if len(agent_rows) >= 5:
            failure_pct = 100.0 * len(failures) / len(agent_rows)
            if failure_pct > 25:
                alarm_msg = (
                    f"{agent}: {failure_pct:.0f}% failure rate ({len(failures)}/{len(agent_rows)})"
                )
                alarms.append(alarm_msg)
                if args.enqueue_on_alarm:
                    details = f"{agent}:{failure_pct:.0f}%"
                    _enqueue_alarm(client, "high_failure_rate", details, alarm_msg)

    print()

    # Gap detection on dispatcher heartbeat
    dispatcher_rows = by_agent.get("task-dispatcher", [])
    if dispatcher_rows:
        prev = None
        for r in dispatcher_rows:
            ts = datetime.fromisoformat(r["timestamp"].replace("Z", "+00:00"))
            if prev is not None:
                gap_min = (ts - prev).total_seconds() / 60
                if gap_min > args.gap_minutes:
                    alarm_msg = (
                        f"task-dispatcher: {gap_min:.0f}min gap ending at {_fmt_ts(r['timestamp'])}"
                    )
                    alarms.append(alarm_msg)
                    if args.enqueue_on_alarm:
                        details = "dispatcher:gap"
                        _enqueue_alarm(client, "dispatcher_gap", details, alarm_msg)
            prev = ts

    # Recent failures (full detail)
    recent_failures = [r for r in rows if _is_failure(r["outcome"])][-10:]
    if recent_failures:
        print("Recent failures (last 10):")
        for r in recent_failures:
            print(
                f"  {_fmt_ts(r['timestamp'])} {r['agent_id']:<25} {r['action']:<15} {r['outcome']}"
            )
        print()

    if alarms:
        print("ALARMS:")
        for a in alarms:
            print(f"  - {a}")
        return 1

    print("All clear.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
