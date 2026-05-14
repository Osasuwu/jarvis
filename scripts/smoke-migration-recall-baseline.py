#!/usr/bin/env python3
"""Cross-project recall-baseline smoke test for memory-deriver Slice 1 (#552).

Verifies that a typical recall query (the kind redrobot might issue) returns
identical result sets against pre-migration vs post-migration Supabase branch.

Usage:
    # Pre-migration baseline:
    SUPABASE_URL=<url> SUPABASE_KEY=<anon-key> \
        python scripts/smoke-migration-recall-baseline.py baseline

    # Post-migration (same db, after mig):
    SUPABASE_URL=<url> SUPABASE_KEY=<anon-key> \
        python scripts/smoke-migration-recall-baseline.py check
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request

BASELINE_PATH = ".smoke-recall-baseline.json"

# Recall query that redrobot might run — a simple semantic-style select over
# live (non-superseded, non-expired, non-merge-proposal) memories.
RECALL_QUERY = """
SELECT id, type, project, content, created_at, source_provenance,
       confidence, requires_review
FROM memories
WHERE expired_at IS NULL
  AND superseded_by IS NULL
  AND deleted_at IS NULL
  AND (valid_to IS NULL OR valid_to > now())
  AND (merge_targets IS NULL OR merge_targets = '{}')
  AND requires_review = false
ORDER BY created_at DESC
LIMIT 50;
"""

QUERY_COUNT = """
SELECT COUNT(*) AS total_live
FROM memories
WHERE expired_at IS NULL
  AND superseded_by IS NULL
  AND deleted_at IS NULL
  AND (valid_to IS NULL OR valid_to > now())
  AND requires_review = false;
"""


def _query_supabase(sql: str) -> list[dict]:
    url = os.environ["SUPABASE_URL"].rstrip("/") + "/rest/v1/rpc/execute_sql"
    key = os.environ["SUPABASE_KEY"]
    headers = {
        "Content-Type": "application/json",
        "apikey": key,
        "Authorization": f"Bearer {key}",
    }
    req = urllib.request.Request(
        url,
        data=json.dumps({"query": sql}).encode(),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def _check_required_cols(rows: list[dict]) -> None:
    """Ensure the new deriver columns exist and have expected default values."""
    if not rows:
        return
    sample = rows[0]
    for col in ("requires_review", "derivation_run_id", "merge_targets"):
        assert col in sample, (
            f"Column `{col}` missing from recall results — "
            f"migration may not have been applied."
        )

    # Check requires_review default — all existing rows should be false
    for row in rows:
        assert row.get("requires_review") is False or row.get("requires_review") is None, (
            f"Row {row['id']} has requires_review={row['requires_review']}, "
            f"expected false after backfill."
        )


def baseline() -> None:
    """Capture pre-migration recall baseline."""
    print("Capturing recall baseline...", flush=True)
    rows = _query_supabase(RECALL_QUERY)

    # Extract stable identifiers
    ids = sorted(r["id"] for r in rows)
    print(f"  {len(ids)} rows returned, saving...", flush=True)

    baseline = {
        "count": len(ids),
        "ids": ids,
        "sample": rows[:3] if rows else [],
    }

    with open(BASELINE_PATH, "w") as f:
        json.dump(baseline, f, indent=2, default=str)
    print(f"  Baseline saved to {BASELINE_PATH}", flush=True)


def check() -> None:
    """Compare post-migration recall against baseline."""
    if not os.path.exists(BASELINE_PATH):
        print(
            f"No baseline at {BASELINE_PATH}. Run `baseline` command first.",
            file=sys.stderr,
        )
        sys.exit(1)

    with open(BASELINE_PATH) as f:
        baseline = json.load(f)

    rows = _query_supabase(RECALL_QUERY)
    current_ids = sorted(r["id"] for r in rows)

    # Verify new columns exist and are populated correctly
    _check_required_cols(rows)

    count_rows = _query_supabase(QUERY_COUNT)
    total_live = count_rows[0]["total_live"] if count_rows else 0
    print(f"  Baseline: {baseline['count']} rows", flush=True)
    print(f"  Current:  {len(current_ids)} rows (total live: {total_live})", flush=True)

    # Compare IDs
    added = set(current_ids) - set(baseline["ids"])
    removed = set(baseline["ids"]) - set(current_ids)

    issues = []
    if added:
        issues.append(f"  {len(added)} new rows (from other concurrent writes): {list(added)[:3]}...")
    if removed:
        issues.append(f"  {len(removed)} rows disappeared: {list(removed)}")

    for msg in issues:
        print(msg, file=sys.stderr)

    # The true identity check: the baseline set should be a subset of current.
    baseline_set = set(baseline["ids"])
    if not baseline_set.issubset(set(current_ids)):
        missing = baseline_set - set(current_ids)
        print(
            f"\nFAIL: {len(missing)} baseline rows missing. "
            f"Migration changed recall behavior.",
            file=sys.stderr,
        )
        sys.exit(1)

    print("\nOK: recall baseline preserved.", flush=True)


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "baseline":
        baseline()
    elif cmd == "check":
        check()
    else:
        print(
            "Usage:\n"
            "  smoke-migration-recall-baseline.py baseline   # capture pre-migration\n"
            "  smoke-migration-recall-baseline.py check      # verify post-migration\n"
            "\n"
            "Both commands need SUPABASE_URL and SUPABASE_KEY set.\n"
        )
        sys.exit(1 if cmd else 0)


if __name__ == "__main__":
    main()
