"""Consolidation review CLI — Phase 5.1d-β (#226).

Owner-review companion to `consolidation-rollback.py`. Works through
`memory_review_queue` rows left in `status='pending'` by the weekly
`consolidation-merge-plan.py --apply` run (i.e. below the 0.85 confidence
gate), without SQL:

  list      show pending rows (id / decision / conf / members / reasoning)
  diff      show what would change — canonical vs member contents
  approve   apply the stored plan (no Haiku re-call), transition to approved,
            backfill canonical embedding on MERGE, emit event
  reject    mark rejected (blocks re-planning forever), emit event

The approve/reject paths are single-transaction RPCs
(`approve_consolidation` / `reject_consolidation`) so concurrent CLI runs
can't double-apply the same row. For MERGE, the canonical is written by
the RPC with `embedding IS NULL`; this script backfills via VoyageAI
immediately after — same contract as the auto_applied path.

Usage:
    python scripts/consolidation-review.py --list
    python scripts/consolidation-review.py --list --limit 50
    python scripts/consolidation-review.py <queue_id> --diff
    python scripts/consolidation-review.py <queue_id> --approve
    python scripts/consolidation-review.py <queue_id> --reject --reason "off-topic"
    python scripts/consolidation-review.py ... --json   # any mode

Env: SUPABASE_URL, SUPABASE_KEY, VOYAGE_API_KEY (for MERGE approve).
.env auto-loaded.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
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

import httpx
from supabase import create_client


VOYAGE_API_URL = "https://api.voyageai.com/v1/embeddings"
VOYAGE_MODEL = "voyage-3-lite"
VOYAGE_TIMEOUT = 30.0


def _canonical_embed_text(name: str, description: str, tags: list[str], content: str) -> str:
    """Mirror of mcp-memory/server.py:_canonical_embed_text.

    Duplicated from consolidation-merge-plan.py so this script can backfill
    approved MERGE canonicals on the same axis. Both copies mirror server.py
    byte-for-byte (tracked in a follow-up issue if either drifts).
    """
    parts: list[str] = []
    if name:
        parts.append(name.replace("_", " "))
    if tags:
        parts.append("tags: " + ", ".join(tags))
    if description:
        parts.append(description)
    if content:
        parts.append(content)
    return "\n".join(p for p in parts if p).strip()


def embed_document(text: str, *, timeout: float = VOYAGE_TIMEOUT) -> list[float] | None:
    """Sync VoyageAI call. Returns None on any failure (caller logs + continues)."""
    api_key = os.environ.get("VOYAGE_API_KEY")
    if not api_key or not text:
        return None
    try:
        with httpx.Client(timeout=timeout) as http:
            resp = http.post(
                VOYAGE_API_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                json={"model": VOYAGE_MODEL, "input": [text], "input_type": "document"},
            )
            resp.raise_for_status()
            return resp.json()["data"][0]["embedding"]
    except (httpx.HTTPError, KeyError, IndexError, ValueError, TypeError):
        return None


def _fetch_queue_row(client, queue_id: str) -> dict | None:
    rows = (
        client.table("memory_review_queue")
        .select(
            "id, decision, status, confidence, reasoning, classifier_model, "
            "consolidation_payload, target_id, created_at, reviewed_at, "
            "reviewed_by, applied_at"
        )
        .eq("id", queue_id)
        .limit(1)
        .execute()
        .data
    ) or []
    return rows[0] if rows else None


def list_pending(client, limit: int) -> list[dict]:
    rows = (
        client.table("memory_review_queue")
        .select(
            "id, decision, confidence, reasoning, created_at, "
            "consolidation_payload, classifier_model"
        )
        .eq("status", "pending")
        .in_("decision", ["MERGE", "SUPERSEDE_CONSOLIDATION"])
        .order("created_at", desc=False)
        .limit(limit)
        .execute()
        .data
    ) or []
    return rows


def print_listing(rows: list[dict]) -> None:
    if not rows:
        print("No pending MERGE/SUPERSEDE_CONSOLIDATION rows.")
        return
    print(f"{'id':36}  {'decision':24}  {'conf':>5}  {'created':19}  members")
    print("-" * 128)
    for r in rows:
        payload = r.get("consolidation_payload") or {}
        names = payload.get("member_names") or []
        names_str = ", ".join(names[:3]) + (f" +{len(names) - 3}" if len(names) > 3 else "")
        created = (r.get("created_at") or "")[:19].replace("T", " ")
        reasoning = (r.get("reasoning") or "").split("\n", 1)[0][:80]
        print(
            f"{r['id']:36}  {r['decision']:24}  {float(r['confidence']):5.2f}  "
            f"{created:19}  {names_str}"
        )
        if reasoning:
            print(f"{'':36}    why: {reasoning}")


def _fetch_members(client, member_ids: list[str]) -> list[dict]:
    if not member_ids:
        return []
    rows = (
        client.table("memories")
        .select("id, name, type, description, content, tags, created_at")
        .in_("id", member_ids)
        .execute()
        .data
    ) or []
    order = {mid: i for i, mid in enumerate(member_ids)}
    rows.sort(key=lambda r: order.get(r["id"], len(order)))
    return rows


def render_diff(row: dict, members: list[dict]) -> str:
    payload = row.get("consolidation_payload") or {}
    lines: list[str] = []
    lines.append(f"Queue entry: {row['id']}")
    lines.append(
        f"Decision: {row['decision']}  confidence={float(row['confidence']):.2f}  "
        f"model={row.get('classifier_model') or '?'}"
    )
    if row.get("reasoning"):
        lines.append(f"Reasoning: {row['reasoning']}")
    lines.append("")

    if row["decision"] == "MERGE":
        lines.append("--- Proposed canonical (new row) ---")
        lines.append(f"name: {payload.get('canonical_name')}")
        lines.append(f"type: {payload.get('canonical_type')}")
        tags = payload.get("canonical_tags") or []
        lines.append(f"tags: {', '.join(tags) if tags else '(none)'}")
        if payload.get("canonical_description"):
            lines.append(f"description: {payload['canonical_description']}")
        lines.append("content:")
        for ln in (payload.get("canonical_content") or "").splitlines():
            lines.append(f"  {ln}")
    else:  # SUPERSEDE_CONSOLIDATION
        lines.append(
            f"--- Canonical (winner): {row.get('target_id') or payload.get('canonical_id')} ---"
        )

    lines.append("")
    lines.append(f"--- Members ({len(members)}) ---")
    for m in members:
        lines.append(
            f"* {m['name']} ({m['type']})  id={m['id']}  created={m.get('created_at', '')[:10]}"
        )
        tags = m.get("tags") or []
        if tags:
            lines.append(f"  tags: {', '.join(tags)}")
        if m.get("description"):
            lines.append(f"  description: {m['description']}")
        if m.get("content"):
            lines.append("  content:")
            for ln in (m.get("content") or "").splitlines():
                lines.append(f"    {ln}")
        lines.append("")
    return "\n".join(lines)


def _write_event(
    client, *, event_type: str, severity: str, title: str, payload: dict
) -> str | None:
    try:
        resp = (
            client.table("events")
            .insert(
                {
                    "event_type": event_type,
                    "severity": severity,
                    "repo": "Osasuwu/jarvis",
                    "source": "cli_review",
                    "title": title,
                    "payload": payload,
                }
            )
            .execute()
        )
        data = resp.data or []
        return data[0]["id"] if data else None
    except Exception as e:
        print(f"! event insert failed ({event_type}): {e}", file=sys.stderr)
        return None


def approve(client, queue_id: str, *, as_json: bool) -> int:
    row = _fetch_queue_row(client, queue_id)
    if not row:
        msg = f"Queue entry {queue_id} not found"
        print(msg, file=sys.stderr)
        if as_json:
            print(json.dumps({"status": "not_found", "queue_id": queue_id}))
        return 1

    if row["status"] != "pending":
        msg = f"Queue entry {queue_id} has status={row['status']} (expected pending)"
        print(msg, file=sys.stderr)
        if as_json:
            print(
                json.dumps(
                    {"status": "not_pending", "queue_id": queue_id, "actual_status": row["status"]}
                )
            )
        return 1

    try:
        resp = client.rpc("approve_consolidation", {"queue_id": queue_id}).execute()
        result = resp.data or {}
    except Exception as e:
        msg = f"approve_consolidation failed: {e}"
        print(msg, file=sys.stderr)
        if as_json:
            print(json.dumps({"status": "rpc_failed", "queue_id": queue_id, "error": str(e)}))
        return 1

    canonical_id = result.get("canonical_id")
    decision = result.get("decision")
    embedded = None

    # MERGE: backfill embedding on synthesized canonical. SUPERSEDE doesn't
    # need a backfill — no new memory row was created.
    if decision == "MERGE" and canonical_id:
        payload = row.get("consolidation_payload") or {}
        text = _canonical_embed_text(
            payload.get("canonical_name") or "",
            payload.get("canonical_description") or "",
            list(payload.get("canonical_tags") or []),
            payload.get("canonical_content") or "",
        )
        emb = embed_document(text)
        if emb is not None:
            try:
                client.table("memories").update(
                    {
                        "embedding": emb,
                        "embedding_model": VOYAGE_MODEL,
                        "embedding_version": "v1",
                    }
                ).eq("id", canonical_id).execute()
                embedded = True
            except Exception as e:
                print(f"! embedding backfill failed for {canonical_id}: {e}", file=sys.stderr)
                embedded = False
        else:
            print(
                f"! VoyageAI returned no embedding for {canonical_id} — canonical left with embedding=NULL",
                file=sys.stderr,
            )
            embedded = False

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    event_payload = {
        "queue_id": queue_id,
        "decision": decision,
        "canonical_id": canonical_id,
        "superseded_count": result.get("superseded_count"),
        "embedded": embedded,
        "source_provenance": f"cli:review:{today}",
    }
    event_id = _write_event(
        client,
        event_type="consolidation_applied",
        severity="info",
        title=f"Consolidation approved via CLI — {decision} ({canonical_id})",
        payload=event_payload,
    )

    out = {
        "status": "approved",
        "decision": decision,
        "canonical_id": canonical_id,
        "superseded_count": result.get("superseded_count"),
        "embedded": embedded,
        "queue_id": queue_id,
        "event_id": event_id,
    }
    if as_json:
        print(json.dumps(out, indent=2, default=str))
    else:
        print(f"Approved queue entry {queue_id}")
        print(f"  decision:         {decision}")
        print(f"  canonical_id:     {canonical_id}")
        print(f"  superseded_count: {result.get('superseded_count')}")
        print(f"  embedded:         {embedded}")
        print(f"  event_id:         {event_id}")
    return 0


def reject(client, queue_id: str, *, reason: str | None, as_json: bool) -> int:
    row = _fetch_queue_row(client, queue_id)
    if not row:
        print(f"Queue entry {queue_id} not found", file=sys.stderr)
        if as_json:
            print(json.dumps({"status": "not_found", "queue_id": queue_id}))
        return 1

    if row["status"] != "pending":
        print(
            f"Queue entry {queue_id} has status={row['status']} (expected pending)",
            file=sys.stderr,
        )
        if as_json:
            print(
                json.dumps(
                    {"status": "not_pending", "queue_id": queue_id, "actual_status": row["status"]}
                )
            )
        return 1

    try:
        args: dict = {"queue_id": queue_id}
        if reason:
            args["reason"] = reason
        resp = client.rpc("reject_consolidation", args).execute()
        result = resp.data or {}
    except Exception as e:
        print(f"reject_consolidation failed: {e}", file=sys.stderr)
        if as_json:
            print(json.dumps({"status": "rpc_failed", "queue_id": queue_id, "error": str(e)}))
        return 1

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    event_payload = {
        "queue_id": queue_id,
        "decision": result.get("decision"),
        "reason": reason,
        "source_provenance": f"cli:review:{today}",
    }
    event_id = _write_event(
        client,
        event_type="consolidation_rejected",
        severity="info",
        title=f"Consolidation rejected via CLI — {result.get('decision')}",
        payload=event_payload,
    )

    out = {
        "status": "rejected",
        "decision": result.get("decision"),
        "queue_id": queue_id,
        "reason": reason,
        "event_id": event_id,
    }
    if as_json:
        print(json.dumps(out, indent=2, default=str))
    else:
        print(f"Rejected queue entry {queue_id}")
        print(f"  decision: {result.get('decision')}")
        print(f"  reason:   {reason or '(none)'}")
        print(f"  event_id: {event_id}")
    return 0


def show_diff(client, queue_id: str, *, as_json: bool) -> int:
    row = _fetch_queue_row(client, queue_id)
    if not row:
        print(f"Queue entry {queue_id} not found", file=sys.stderr)
        if as_json:
            print(json.dumps({"status": "not_found", "queue_id": queue_id}))
        return 1

    payload = row.get("consolidation_payload") or {}
    member_ids = list(payload.get("member_ids") or [])
    members = _fetch_members(client, member_ids)

    if as_json:
        print(
            json.dumps(
                {
                    "queue_id": queue_id,
                    "decision": row["decision"],
                    "confidence": float(row["confidence"]),
                    "status": row["status"],
                    "reasoning": row.get("reasoning"),
                    "canonical_project": payload.get("canonical_project"),
                    "canonical_name": payload.get("canonical_name"),
                    "canonical_type": payload.get("canonical_type"),
                    "canonical_description": payload.get("canonical_description"),
                    "canonical_content": payload.get("canonical_content"),
                    "canonical_tags": payload.get("canonical_tags") or [],
                    "members": members,
                },
                indent=2,
                default=str,
            )
        )
    else:
        print(render_diff(row, members))
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("queue_id", nargs="?", help="memory_review_queue.id to operate on")
    p.add_argument("--list", action="store_true", help="List pending MERGE/SUPERSEDE rows")
    p.add_argument("--limit", type=int, default=20, help="Rows shown by --list (default 20)")
    p.add_argument("--diff", action="store_true", help="Show canonical vs members for queue_id")
    p.add_argument("--approve", action="store_true", help="Approve queue_id (applies the plan)")
    p.add_argument("--reject", action="store_true", help="Reject queue_id (blocks re-planning)")
    p.add_argument("--reason", help="Optional reason text (used with --reject)")
    p.add_argument("--json", action="store_true", help="Emit JSON instead of text")
    args = p.parse_args()

    sb_url = os.environ.get("SUPABASE_URL")
    sb_key = os.environ.get("SUPABASE_KEY")
    if not sb_url or not sb_key:
        print("SUPABASE_URL / SUPABASE_KEY missing from env", file=sys.stderr)
        return 2

    client = create_client(sb_url, sb_key)

    action_flags = [args.list, args.diff, args.approve, args.reject]
    if sum(1 for f in action_flags if f) > 1:
        p.error("pick exactly one of --list / --diff / --approve / --reject")

    if args.list:
        rows = list_pending(client, args.limit)
        if args.json:
            print(json.dumps(rows, indent=2, default=str))
        else:
            print_listing(rows)
        return 0

    if not args.queue_id:
        p.print_usage(sys.stderr)
        print("error: queue_id required unless --list is passed", file=sys.stderr)
        return 2

    if args.diff:
        return show_diff(client, args.queue_id, as_json=args.json)
    if args.approve:
        return approve(client, args.queue_id, as_json=args.json)
    if args.reject:
        return reject(client, args.queue_id, reason=args.reason, as_json=args.json)

    # No action flag — default to --diff for bare queue_id.
    return show_diff(client, args.queue_id, as_json=args.json)


if __name__ == "__main__":
    sys.exit(main())
