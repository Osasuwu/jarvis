"""Event tap handlers — events_list / events_mark_processed.

Surfaces row reads from the events table that drive perception in
Pillar 7.

Part of #360 server.py split. Calls utilities (`_get_client`,
`_audit_log`, embedding helpers, `EMBEDDING_MODEL_*`, ...) via
the `server` module so test monkeypatches on those names
propagate at call time.
"""

from __future__ import annotations

import json

from datetime import datetime, timezone  # noqa: F401

from mcp.types import TextContent  # noqa: F401

import server  # noqa: F401  — late-bound for monkeypatch propagation

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


async def _handle_events_list(args: dict) -> list[TextContent]:
    client = server._get_client()

    q = client.table("events").select("*")

    if not args.get("include_processed", False):
        q = q.eq("processed", False)

    if args.get("repo"):
        q = q.eq("repo", args["repo"])
    if args.get("event_type"):
        q = q.eq("event_type", args["event_type"])

    min_severity = args.get("severity")
    if min_severity and min_severity in SEVERITY_ORDER:
        allowed = [s for s, v in SEVERITY_ORDER.items() if v <= SEVERITY_ORDER[min_severity]]
        q = q.in_("severity", allowed)

    limit = args.get("limit", 20)
    result = q.order("created_at", desc=True).limit(limit).execute()

    if not result.data:
        return [TextContent(type="text", text="No events found.")]

    # Sort by severity (critical first), then by time
    events = sorted(
        result.data, key=lambda e: (SEVERITY_ORDER.get(e["severity"], 4), e["created_at"])
    )

    lines = [f"# Events ({len(events)})\n"]
    for ev in events:
        processed_mark = " [PROCESSED]" if ev.get("processed") else ""
        payload_str = ""
        if ev.get("payload"):
            p = ev["payload"]
            if isinstance(p, str):
                try:
                    p = json.loads(p)
                except (ValueError, TypeError):
                    p = {}
            if p.get("url"):
                payload_str = f"\n  URL: {p['url']}"

        lines.append(
            f"## [{ev['severity'].upper()}] {ev['title']}{processed_mark}\n"
            f"  ID: `{ev['id']}`\n"
            f"  Type: {ev['event_type']} | Repo: {ev['repo']} | Source: {ev['source']}\n"
            f"  Time: {ev.get('event_at', ev['created_at'])}"
            f"{payload_str}\n"
        )

    return [TextContent(type="text", text="\n".join(lines))]


async def _handle_events_mark_processed(args: dict) -> list[TextContent]:
    client = server._get_client()

    event_ids = args["event_ids"]
    processed_by = args["processed_by"]
    action_taken = args.get("action_taken", "")

    now = datetime.now(timezone.utc).isoformat()

    updated = 0
    for eid in event_ids:
        result = (
            client.table("events")
            .update(
                {
                    "processed": True,
                    "processed_at": now,
                    "processed_by": processed_by,
                    "action_taken": action_taken,
                }
            )
            .eq("id", eid)
            .execute()
        )
        if result.data:
            updated += 1

    return [
        TextContent(type="text", text=f"Marked {updated}/{len(event_ids)} events as processed.")
    ]
