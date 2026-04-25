"""Outcome tracking handlers — outcome_record / outcome_update /
outcome_list / memory_calibration_summary (Pillar 3).

Part of #360 server.py split. Calls utilities (`_get_client`,
`_audit_log`, embedding helpers, `EMBEDDING_MODEL_*`, ...) via
the `server` module so test monkeypatches on those names
propagate at call time.
"""

from __future__ import annotations

from datetime import datetime, timezone  # noqa: F401

from mcp.types import TextContent  # noqa: F401

import server  # noqa: F401  — late-bound for monkeypatch propagation


async def _handle_outcome_record(args: dict) -> list[TextContent]:
    """Record a task outcome to task_outcomes table."""
    client = server._get_client()

    row = {
        "task_type": args["task_type"],
        "task_description": args["task_description"],
        "outcome_status": args["outcome_status"],
    }
    # Optional fields
    for key in (
        "outcome_summary",
        "goal_slug",
        "project",
        "issue_url",
        "pr_url",
        "tests_passed",
        "pr_merged",
        "quality_score",
        "lessons",
        "memory_id",
    ):
        if key in args and args[key] is not None:
            row[key] = args[key]
    if "pattern_tags" in args:
        row["pattern_tags"] = args["pattern_tags"]

    result = client.table("task_outcomes").insert(row).execute()
    if result.data:
        oid = result.data[0]["id"]
        return [TextContent(type="text", text=f"Outcome recorded: {oid}")]
    return [TextContent(type="text", text="Failed to record outcome.")]


async def _handle_outcome_update(args: dict) -> list[TextContent]:
    """Update a task outcome (verification, status flip, lessons)."""
    client = server._get_client()
    oid = args["id"]

    updates: dict = {}
    for key in (
        "outcome_status",
        "outcome_summary",
        "pr_merged",
        "tests_passed",
        "quality_score",
        "lessons",
        "pattern_tags",
        "memory_id",
    ):
        if key in args and args[key] is not None:
            updates[key] = args[key]

    # Auto-set verified_at when status changes from pending
    if "outcome_status" in updates and updates["outcome_status"] != "pending":
        if "verified_at" in args and args["verified_at"]:
            updates["verified_at"] = args["verified_at"]
        else:
            updates["verified_at"] = datetime.now(timezone.utc).isoformat()

    if not updates:
        return [TextContent(type="text", text="Nothing to update.")]

    result = client.table("task_outcomes").update(updates).eq("id", oid).execute()
    if result.data:
        return [TextContent(type="text", text=f"Outcome {oid} updated: {list(updates.keys())}")]
    return [TextContent(type="text", text=f"Outcome {oid} not found or update failed.")]


async def _handle_outcome_list(args: dict) -> list[TextContent]:
    """List task outcomes with optional filters."""
    client = server._get_client()
    limit = args.get("limit", 20)

    query = (
        client.table("task_outcomes")
        .select(
            "id, task_type, task_description, outcome_status, outcome_summary, "
            "goal_slug, project, pr_url, tests_passed, pr_merged, quality_score, "
            "lessons, pattern_tags, created_at, verified_at"
        )
        .order("created_at", desc=True)
        .limit(limit)
    )

    if args.get("project"):
        query = query.eq("project", args["project"])
    if args.get("goal_slug"):
        query = query.eq("goal_slug", args["goal_slug"])
    if args.get("outcome_status"):
        query = query.eq("outcome_status", args["outcome_status"])
    if args.get("pattern_tag"):
        query = query.contains("pattern_tags", [args["pattern_tag"]])

    result = query.execute()

    if not result.data:
        return [TextContent(type="text", text="No outcomes found.")]

    lines = [f"# Task Outcomes ({len(result.data)})\n"]
    for o in result.data:
        status_icon = {
            "success": "+",
            "partial": "~",
            "failure": "-",
            "pending": "?",
            "unknown": ".",
        }.get(o["outcome_status"], "?")
        lines.append(f"[{status_icon}] {o['task_type']}: {o['task_description']}")
        if o.get("outcome_summary"):
            lines.append(f"    {o['outcome_summary']}")
        if o.get("goal_slug"):
            lines.append(f"    Goal: {o['goal_slug']}")
        if o.get("lessons"):
            lines.append(f"    Lesson: {o['lessons']}")
        lines.append(f"    {o['created_at'][:10]} | {o['outcome_status']}")
        lines.append("")

    return [TextContent(type="text", text="\n".join(lines))]


async def _handle_memory_calibration_summary(args: dict) -> list[TextContent]:
    """Render the Brier-score calibration summary from the RPC (#251).

    Returns a markdown block with overall Brier, per-type breakdown, and
    explicit over/under-confidence warnings. Callers ( /reflect,
    /self-improve ) surface this to the user or use it for ideation.
    """
    client = server._get_client()
    project = args.get("project")
    if project == "global":
        project = None

    try:
        result = client.rpc("memory_calibration_summary", {"p_project": project}).execute()
    except Exception as exc:
        return [TextContent(type="text", text=f"Error calling memory_calibration_summary: {exc}")]

    # RPCs that `returns table` come back as a list — take [0] like the
    # other RPC handlers in this file.
    rows = result.data or []
    if isinstance(rows, list):
        row = rows[0] if rows else {}
    elif isinstance(rows, dict):
        row = rows
    else:
        row = {}

    overall = row.get("overall_brier")
    total = row.get("total_memories", 0)
    by_type = row.get("by_type") or []
    warnings = row.get("warnings") or []

    if not total:
        scope = f" (project={project})" if project else ""
        return [
            TextContent(
                type="text",
                text=f"No calibration data yet{scope} — need outcomes with memory_id linked.",
            )
        ]

    lines = [
        "# Confidence Calibration",
        "",
        f"**Overall Brier:** {overall:.3f}  (lower is better; 0.25 ≈ boundary)",
        f"**Memories scored:** {total}",
        "",
        "## By type",
    ]
    for t in by_type:
        flag = ""
        if t.get("over_confident"):
            flag = "  **[overconfident]**"
        elif t.get("under_confident"):
            flag = "  **[underconfident]**"
        lines.append(
            f"- `{t['type']}`: brier={t['brier']:.3f}, "
            f"predicted={t['avg_predicted']:.2f}, actual={t['avg_actual']:.2f}, "
            f"n={t['n']}{flag}"
        )

    if warnings:
        lines.append("")
        lines.append("## Warnings")
        for w in warnings:
            lines.append(f"- {w}")

    return [TextContent(type="text", text="\n".join(lines))]
