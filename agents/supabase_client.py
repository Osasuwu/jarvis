"""Supabase bridge for LangGraph agents.

LangGraph agents call Supabase directly via ``supabase-py`` — MCP is
Claude Code's protocol and isn't available inside graph nodes. The
read/write helpers here mirror a subset of ``mcp-memory/server.py`` so
data written by an agent shows up in Claude Code's ``memory_recall`` /
``events_list`` / ``goal_list`` and vice versa.

Scope (Sprint 1, issue #173):
  * Reads — ``list_memories``, ``list_events``, ``list_goals``
  * Writes — ``store_event``, ``mark_event_processed``,
    ``update_goal_progress``, ``audit``

Anything more (memory_store, task_outcomes, consolidation, …) stays in
Claude Code for now. Agents are consumers of the event inbox, not full
owners of the knowledge base.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from supabase import Client, create_client

from agents.config import AgentConfig, load_config


def get_client(config: AgentConfig | None = None) -> Client:
    """Return a supabase-py client bound to the agent config.

    Raises ``RuntimeError`` with a pointer to ``.env.example`` if the
    caller hasn't set ``SUPABASE_URL`` / ``SUPABASE_KEY`` — a silent
    default would let bad config reach production unnoticed.
    """
    cfg = config or load_config()
    if not cfg.supabase_url or not cfg.supabase_key:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_KEY must be set for the agent Supabase "
            "bridge — see .env.example."
        )
    return create_client(cfg.supabase_url, cfg.supabase_key)


# -- Read helpers -----------------------------------------------------------


def list_memories(
    *,
    project: str | None = None,
    type: str | None = None,
    limit: int = 10,
    client: Client | None = None,
    config: AgentConfig | None = None,
) -> list[dict[str, Any]]:
    """Return memory rows — same table Claude Code reads via ``memory_recall``.

    Ordering matches the MCP server's default: most recently updated first.
    """
    cli = client or get_client(config)
    q = (
        cli.table("memories")
        .select("id, name, type, project, description, content, tags, updated_at")
        .order("updated_at", desc=True)
        .limit(limit)
    )
    if project is not None:
        q = q.eq("project", project)
    if type is not None:
        q = q.eq("type", type)
    return q.execute().data or []


def list_events(
    *,
    processed: bool | None = False,
    repo: str | None = None,
    event_type: str | None = None,
    limit: int = 20,
    client: Client | None = None,
    config: AgentConfig | None = None,
) -> list[dict[str, Any]]:
    """Return event rows.

    ``processed=False`` (default) returns the unprocessed inbox, matching
    the MCP ``events_list`` default. Pass ``processed=None`` to include
    both.
    """
    cli = client or get_client(config)
    q = cli.table("events").select("*").order("created_at", desc=True).limit(limit)
    if processed is not None:
        q = q.eq("processed", processed)
    if repo is not None:
        q = q.eq("repo", repo)
    if event_type is not None:
        q = q.eq("event_type", event_type)
    return q.execute().data or []


def list_goals(
    *,
    status: str | None = "active",
    project: str | None = None,
    limit: int = 50,
    client: Client | None = None,
    config: AgentConfig | None = None,
) -> list[dict[str, Any]]:
    """Return goals — strategic context Claude Code loads at session start."""
    cli = client or get_client(config)
    q = (
        cli.table("goals")
        .select(
            "slug, title, project, status, priority, why, "
            "success_criteria, progress_pct, updated_at"
        )
        .order("priority")
        .limit(limit)
    )
    if status is not None:
        q = q.eq("status", status)
    if project is not None:
        q = q.eq("project", project)
    return q.execute().data or []


# -- Write helpers ----------------------------------------------------------


def store_event(
    *,
    event_type: str,
    repo: str,
    title: str,
    severity: str = "info",
    payload: dict[str, Any] | None = None,
    source: str = "langgraph-agent",
    client: Client | None = None,
    config: AgentConfig | None = None,
) -> dict[str, Any]:
    """Insert a row into the ``events`` inbox.

    Same queue Claude Code polls via ``events_list`` — agents can emit
    findings here and the orchestrator picks them up in its next loop.
    Returns the inserted row (includes the generated ``id``).
    """
    cli = client or get_client(config)
    row = {
        "event_type": event_type,
        "severity": severity,
        "repo": repo,
        "source": source,
        "title": title,
        "payload": payload or {},
    }
    result = cli.table("events").insert(row).execute()
    data = result.data or []
    if not data:
        raise RuntimeError(f"Supabase returned no row after inserting event: {row!r}")
    return data[0]


def mark_event_processed(
    event_id: str,
    *,
    processed_by: str,
    action_taken: str | None = None,
    client: Client | None = None,
    config: AgentConfig | None = None,
) -> None:
    """Close an event — mirrors the MCP ``events_mark_processed`` tool."""
    cli = client or get_client(config)
    update: dict[str, Any] = {
        "processed": True,
        "processed_at": datetime.now(timezone.utc).isoformat(),
        "processed_by": processed_by,
    }
    if action_taken is not None:
        update["action_taken"] = action_taken
    cli.table("events").update(update).eq("id", event_id).execute()


def update_goal_progress(
    slug: str,
    progress_entry: dict[str, Any],
    *,
    client: Client | None = None,
    config: AgentConfig | None = None,
) -> None:
    """Append an entry to ``goals.progress`` (jsonb list).

    Matches the MCP ``goal_update`` semantics: progress is an append-only
    log of timestamped observations, not an overwrite.
    """
    cli = client or get_client(config)
    current = cli.table("goals").select("progress").eq("slug", slug).limit(1).execute()
    rows = current.data or []
    if not rows:
        raise RuntimeError(f"Goal not found: slug={slug!r}")
    prior = rows[0].get("progress")
    if not isinstance(prior, list):
        prior = []
    prior.append(progress_entry)
    cli.table("goals").update({"progress": prior}).eq("slug", slug).execute()


def audit(
    *,
    agent_id: str,
    tool_name: str,
    action: str,
    target: str | None = None,
    details: dict[str, Any] | None = None,
    outcome: str = "success",
    client: Client | None = None,
    config: AgentConfig | None = None,
) -> None:
    """Best-effort audit entry — never raises.

    The ``agent_id`` column on ``audit_log`` is how agents identify
    themselves (e.g. ``"langgraph-monitor"``). Matches the server.py
    ``_audit_log()`` convention, with ``agent_id`` filled in — MCP writes
    leave it NULL, so the column doubles as the actor differentiator.
    """
    try:
        cli = client or get_client(config)
        cli.table("audit_log").insert(
            {
                "agent_id": agent_id,
                "tool_name": tool_name,
                "action": action,
                "target": target,
                "details": details or {},
                "outcome": outcome,
            }
        ).execute()
    except Exception:
        # Audit is best-effort — never block operations on logging failure.
        pass
