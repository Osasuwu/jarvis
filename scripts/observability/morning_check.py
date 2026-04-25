"""Morning check — read audit_log, surface what happened in the last 24h.

Run on any host with Supabase credentials (SUPABASE_URL / SUPABASE_KEY in env
or via agents.config.AgentConfig). Prints a text report; exits 0 on healthy,
1 on alarms, 2 on connection failure.

Usage:
    python -m scripts.observability.morning_check
    python -m scripts.observability.morning_check --hours 6
    python -m scripts.observability.morning_check --agent task-dispatcher
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from agents.supabase_client import get_client


def _fmt_ts(ts: str) -> str:
    return ts.replace("T", " ").split("+")[0].split(".")[0]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--hours", type=int, default=24, help="Lookback window (default 24)")
    parser.add_argument("--agent", default=None, help="Filter to specific agent_id")
    parser.add_argument("--gap-minutes", type=int, default=10,
                        help="Flag gaps in dispatcher heartbeat exceeding N minutes (default 10)")
    args = parser.parse_args(argv)

    try:
        client = get_client()
    except Exception as e:
        print(f"FAILED to connect to Supabase: {e}", file=sys.stderr)
        return 2

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
        print(f"No audit_log rows in the last {args.hours}h"
              + (f" for agent {args.agent}" if args.agent else "")
              + ".")
        print("If the dispatcher should be running, this is a RED FLAG — service may be down.")
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

    alarms: list[str] = []

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
                alarms.append(f"{agent}: {failure_pct:.0f}% failure rate ({len(failures)}/{len(agent_rows)})")

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
                    alarms.append(
                        f"task-dispatcher: {gap_min:.0f}min gap ending at {_fmt_ts(r['timestamp'])}"
                    )
            prev = ts

    # Recent failures (full detail)
    recent_failures = [r for r in rows if _is_failure(r["outcome"])][-10:]
    if recent_failures:
        print(f"Recent failures (last 10):")
        for r in recent_failures:
            print(f"  {_fmt_ts(r['timestamp'])} {r['agent_id']:<25} {r['action']:<15} {r['outcome']}")
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
