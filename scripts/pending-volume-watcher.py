"""Volume-event watcher for the pending-review queue.

Checks the count of pending memories (``requires_review=true``) and emits
a ``candidates_pending`` event when it crosses the fire threshold (>= 10),
with hysteresis to avoid flapping (re-arms when count drops below 8).

Also debounces: skips firing if a ``/learn`` run completed in the last 24
hours (``event_type='learn_run'`` in the ``events`` table).

Designed for the orchestrator-watcher's polling loop. Can be called as a
standalone script or imported as a module.

Usage::

    python scripts/pending-volume-watcher.py            # check + maybe emit
    python scripts/pending-volume-watcher.py --dry-run   # check only, no event

Env: SUPABASE_URL, SUPABASE_KEY. ``.env`` auto-loaded.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

try:
    from dotenv import load_dotenv

    here = Path(__file__).resolve().parent
    for c in (here.parent / ".env", here.parent.parent / ".env"):
        if c.exists():
            load_dotenv(c, override=True)
            break
except ImportError:
    pass

from supabase import create_client


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FIRE_THRESHOLD = 10
REARM_THRESHOLD = 8
DEBOUNCE_HOURS = 24


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------


def count_pending(client) -> int:
    """Count memories with ``requires_review=true`` and not deleted."""
    rows = (
        client.table("memories")
        .select("id", count="exact")
        .eq("requires_review", True)
        .is_("deleted_at", "null")
        .execute()
    )
    return rows.count if hasattr(rows, "count") and rows.count is not None else 0


def last_candidates_pending_event(client) -> dict | None:
    """Return the most recent ``candidates_pending`` event, or None."""
    rows = (
        client.table("events")
        .select("created_at, payload")
        .eq("event_type", "candidates_pending")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    data = rows.data or []
    return data[0] if data else None


def last_learn_run(client) -> dict | None:
    """Return the most recent ``learn_run`` event, or None."""
    rows = (
        client.table("events")
        .select("created_at")
        .eq("event_type", "learn_run")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    data = rows.data or []
    return data[0] if data else None


def emit_event(client, *, pending_count: int, dry_run: bool = False) -> str | None:
    """Emit a ``candidates_pending`` event. Best-effort."""
    if dry_run:
        return None
    try:
        resp = (
            client.table("events")
            .insert(
                {
                    "event_type": "candidates_pending",
                    "severity": "medium",
                    "repo": "Osasuwu/jarvis",
                    "source": "volume_watcher",
                    "title": f"Pending review queue: {pending_count} items",
                    "payload": {
                        "pending_count": pending_count,
                        "state": "fired",
                    },
                }
            )
            .execute()
        )
        data = resp.data or []
        return data[0]["id"] if data else None
    except Exception as e:
        print(f"! event insert failed: {e}", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# Watcher logic
# ---------------------------------------------------------------------------


def check_and_fire(client, *, dry_run: bool = False) -> dict:
    """Run the volume watcher predicate.

    Returns a dict with the decision and metadata.

    Logic::

        1. Count pending. If < FIRE_THRESHOLD → no action.
        2. Check if already fired (last ``candidates_pending`` event has
           ``payload.state='fired'`` and count >= REARM_THRESHOLD).
           If still in the "fired" band → no action.
        3. Check if a ``/learn`` run happened in the last
           ``DEBOUNCE_HOURS`` → no action.
        4. Otherwise → emit ``candidates_pending`` event.
    """
    pending = count_pending(client)

    if pending < FIRE_THRESHOLD:
        return {
            "action": "none",
            "reason": f"pending={pending} < fire={FIRE_THRESHOLD}",
            "pending_count": pending,
        }

    # Check last fired event
    last_event = last_candidates_pending_event(client)
    if last_event:
        payload = last_event.get("payload") or {}
        last_state = payload.get("state", "rearmed")
        if last_state == "fired" and pending >= REARM_THRESHOLD:
            return {
                "action": "none",
                "reason": (
                    f"already fired (pending={pending} >= rearm={REARM_THRESHOLD}), "
                    f"still in hysteresis band"
                ),
                "pending_count": pending,
            }

    # Check 24h debounce
    last_learn = last_learn_run(client)
    if last_learn:
        created = last_learn.get("created_at")
        if created:
            try:
                last_ts = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
                age = datetime.now(timezone.utc) - last_ts
                if age < timedelta(hours=DEBOUNCE_HOURS):
                    return {
                        "action": "none",
                        "reason": (
                            f"/learn ran {age.total_seconds() / 3600:.1f}h ago, "
                            f"within {DEBOUNCE_HOURS}h debounce"
                        ),
                        "pending_count": pending,
                    }
            except (TypeError, ValueError):
                pass

    # Fire!
    event_id = emit_event(client, pending_count=pending, dry_run=dry_run)
    return {
        "action": "fired" if not dry_run else "would_fire",
        "event_id": event_id,
        "pending_count": pending,
        "fire_threshold": FIRE_THRESHOLD,
        "rearm_threshold": REARM_THRESHOLD,
        "dry_run": dry_run,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Check only, do not emit any event.",
    )
    args = p.parse_args()

    sb_url = os.environ.get("SUPABASE_URL")
    sb_key = os.environ.get("SUPABASE_KEY")
    if not sb_url or not sb_key:
        print("SUPABASE_URL / SUPABASE_KEY missing from env", file=sys.stderr)
        return 2

    client = create_client(sb_url, sb_key)
    result = check_and_fire(client, dry_run=args.dry_run)
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
