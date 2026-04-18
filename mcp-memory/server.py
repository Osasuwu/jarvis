"""Jarvis Memory MCP Server.

Provides persistent, cross-device memory for Claude Code via Supabase.
Tools: memory_store, memory_recall, memory_get, memory_list, memory_delete, memory_restore.
Audit: write operations logged to audit_log table (fire-and-forget).

Semantic search via Voyage AI embeddings (voyage-3-lite, 512 dims).
Uses httpx async HTTP for Voyage AI embedding calls; other Supabase operations are synchronous.
Falls back to ILIKE keyword search if VOYAGE_API_KEY is not set or embedding fails.

Usage in .mcp.json:
{
  "memory": {
    "type": "stdio",
    "command": "python",
    "args": ["mcp-memory/server.py"],
    "env": {
      "SUPABASE_URL": "https://xxx.supabase.co",
      "SUPABASE_KEY": "eyJ...",
      "VOYAGE_API_KEY": "pa-..."
    }
  }
}
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

# Load .env from repo root (two levels up from mcp-memory/server.py)
_env_candidates = [
    Path(__file__).resolve().parent.parent / ".env",  # personal-AI-agent/.env
    Path(__file__).resolve().parent.parent.parent / ".env",  # Github/.env
]
for _env_path in _env_candidates:
    if _env_path.exists():
        load_dotenv(_env_path)
        break

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolResult, TextContent, Tool

# ---------------------------------------------------------------------------
# Supabase client (lazy init)
# ---------------------------------------------------------------------------

_supabase = None


def _get_client():
    global _supabase
    if _supabase is not None:
        return _supabase

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_KEY must be set. "
            "Get them from your Supabase project settings."
        )

    from supabase import create_client

    _supabase = create_client(url, key)

    # One-time migration: normalize legacy project='global' string rows to NULL.
    # Before the 2026-03-31 fix, 'global' was stored as a literal string instead
    # of NULL. This UPDATE is idempotent and safe to run on every startup.
    try:
        _supabase.table("memories").update({"project": None}).eq("project", "global").execute()
    except Exception:
        pass  # non-fatal — server still works without the migration

    return _supabase


# ---------------------------------------------------------------------------
# Audit logging — lightweight, fire-and-forget
# ---------------------------------------------------------------------------


def _audit_log(client, tool_name: str, action: str, target: str | None = None, details: dict | None = None):
    """Fire-and-forget audit log entry. Never fails the caller."""
    try:
        client.table("audit_log").insert({
            "tool_name": tool_name,
            "action": action,
            "target": target,
            "details": details or {},
        }).execute()
    except Exception:
        pass  # audit is best-effort — never block operations


# ---------------------------------------------------------------------------
# Voyage AI embedding — async via httpx (properly cancellable, no thread blocking)
# ---------------------------------------------------------------------------

VOYAGE_API_URL = "https://api.voyageai.com/v1/embeddings"
VOYAGE_MODEL = "voyage-3-lite"
EMBED_TIMEOUT = 30.0  # seconds


async def _embed(text: str, input_type: str = "document") -> list[float] | None:
    """Call Voyage AI REST API asynchronously. Retries up to 3x on 429."""
    api_key = os.environ.get("VOYAGE_API_KEY")
    if not api_key:
        return None
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=EMBED_TIMEOUT) as client:
                resp = await client.post(
                    VOYAGE_API_URL,
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={"model": VOYAGE_MODEL, "input": [text], "input_type": input_type},
                )
                resp.raise_for_status()
                return resp.json()["data"][0]["embedding"]
        except asyncio.CancelledError:
            raise
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429 and attempt < 2:
                await asyncio.sleep(2 ** attempt)
                continue
            return None
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError):
            return None
    return None


async def _embed_batch(texts: list[str], input_type: str = "document") -> list[list[float]] | None:
    """Embed multiple texts in a single API call (up to 1000 per request)."""
    api_key = os.environ.get("VOYAGE_API_KEY")
    if not api_key or not texts:
        return None
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=EMBED_TIMEOUT) as client:
                resp = await client.post(
                    VOYAGE_API_URL,
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={"model": VOYAGE_MODEL, "input": texts, "input_type": input_type},
                )
                resp.raise_for_status()
                data = sorted(resp.json()["data"], key=lambda x: x["index"])
                return [item["embedding"] for item in data]
        except asyncio.CancelledError:
            raise
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429 and attempt < 2:
                await asyncio.sleep(2 ** attempt)
                continue
            return None
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError):
            return None
    return None


async def _embed_query(text: str) -> list[float] | None:
    return await _embed(text, input_type="query")


# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

server = Server("jarvis-memory")

VALID_TYPES = ("user", "project", "decision", "feedback", "reference")

VALID_GOAL_PRIORITIES = ("P0", "P1", "P2")
VALID_GOAL_STATUSES = ("active", "achieved", "paused", "abandoned")

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}

# -- Memory 2.0: temporal scoring + auto-linking ----------------------------
TEMPORAL_HALF_LIVES = {
    "project": 7, "reference": 30, "decision": 60,
    "feedback": 90, "user": 180,
}
DEFAULT_HALF_LIFE = 30
ACCESS_BOOST_MAX = 0.3
ACCESS_HALF_LIFE = 14
LINK_SIM_THRESHOLD = 0.60
SUPERSEDE_SIM_THRESHOLD = 0.85
CONSOLIDATION_SIM_THRESHOLD = 0.80
CONSOLIDATION_COUNT = 3
MAX_AUTO_LINKS = 5


# -- Tool definitions -------------------------------------------------------

@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        # ---- Goal tools ----
        Tool(
            name="goal_set",
            description=(
                "Create or update a goal (upsert by slug). "
                "Goals are strategic objectives that guide Jarvis's priorities and decisions."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "slug": {
                        "type": "string",
                        "description": "Unique identifier (e.g. 'redrobot-demo', 'jarvis-goals-system')",
                    },
                    "title": {"type": "string", "description": "Human-readable goal title"},
                    "project": {
                        "type": ["string", "null"],
                        "description": "Project scope (e.g. 'redrobot', 'jarvis'). null = cross-project.",
                    },
                    "direction": {
                        "type": ["string", "null"],
                        "description": "Strategic direction this goal belongs to",
                    },
                    "priority": {
                        "type": "string",
                        "enum": list(VALID_GOAL_PRIORITIES),
                        "description": "P0 = critical, P1 = important, P2 = nice to have",
                    },
                    "status": {
                        "type": "string",
                        "enum": list(VALID_GOAL_STATUSES),
                    },
                    "why": {"type": "string", "description": "Motivation — why this goal matters"},
                    "success_criteria": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of success criteria",
                    },
                    "deadline": {
                        "type": ["string", "null"],
                        "description": "Deadline date (YYYY-MM-DD)",
                    },
                    "progress": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "item": {"type": "string"},
                                "done": {"type": "boolean"},
                            },
                        },
                        "description": "Progress milestones",
                    },
                    "progress_pct": {
                        "type": "integer",
                        "description": "Overall progress percentage (0-100)",
                    },
                    "risks": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Known risks",
                    },
                    "owner_focus": {"type": "string", "description": "What the owner is working on"},
                    "jarvis_focus": {"type": "string", "description": "What Jarvis should handle"},
                    "parent_id": {
                        "type": ["string", "null"],
                        "description": "Parent goal UUID (for sub-goals)",
                    },
                },
                "required": ["slug", "title"],
            },
        ),
        Tool(
            name="goal_list",
            description=(
                "List goals with optional filters. "
                "Use at session start to load active goals as strategic context."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": list(VALID_GOAL_STATUSES),
                        "description": "Filter by status (default: all)",
                    },
                    "project": {
                        "type": ["string", "null"],
                        "description": "Filter by project",
                    },
                    "priority": {
                        "type": "string",
                        "enum": list(VALID_GOAL_PRIORITIES),
                        "description": "Filter by priority",
                    },
                },
            },
        ),
        Tool(
            name="goal_get",
            description="Get a specific goal by slug with full details.",
            inputSchema={
                "type": "object",
                "properties": {
                    "slug": {"type": "string", "description": "Goal slug"},
                },
                "required": ["slug"],
            },
        ),
        Tool(
            name="goal_update",
            description=(
                "Partial update of a goal. Only provided fields are updated. "
                "Use to update progress, status, focus, risks, etc."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "slug": {"type": "string", "description": "Goal slug to update"},
                    "title": {"type": "string"},
                    "priority": {"type": "string", "enum": list(VALID_GOAL_PRIORITIES)},
                    "status": {"type": "string", "enum": list(VALID_GOAL_STATUSES)},
                    "why": {"type": "string"},
                    "success_criteria": {"type": "array", "items": {"type": "string"}},
                    "deadline": {"type": ["string", "null"]},
                    "progress": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "item": {"type": "string"},
                                "done": {"type": "boolean"},
                            },
                        },
                    },
                    "progress_pct": {"type": "integer"},
                    "risks": {"type": "array", "items": {"type": "string"}},
                    "owner_focus": {"type": "string"},
                    "jarvis_focus": {"type": "string"},
                    "outcome": {"type": "string", "description": "What happened (for closing)"},
                    "lessons": {"type": "string", "description": "What was learned (for closing)"},
                },
                "required": ["slug"],
            },
        ),
        # ---- Memory tools ----
        Tool(
            name="memory_store",
            description=(
                "Save or update a memory. Upserts by (project, name). "
                "Use for: decisions, user preferences, project context, feedback, references. "
                "Set project=null for cross-project memories."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": list(VALID_TYPES),
                        "description": "Memory category",
                    },
                    "name": {
                        "type": "string",
                        "description": "Unique name within project scope (e.g. 'architecture_split', 'user_work_style')",
                    },
                    "content": {
                        "type": "string",
                        "description": "Full memory content. Be specific — this is what future sessions will read.",
                    },
                    "description": {
                        "type": "string",
                        "description": "One-line summary for quick relevance matching.",
                    },
                    "project": {
                        "type": ["string", "null"],
                        "description": "Project scope. null = global/cross-project. 'jarvis' = this project.",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tags for filtering (e.g. ['architecture', 'decision'])",
                    },
                },
                "required": ["type", "name", "content"],
            },
        ),
        Tool(
            name="memory_recall",
            description=(
                "Search memories by keyword or semantic meaning. "
                "Uses vector similarity search when available, falls back to keyword matching. "
                "Use at the START of a session to load relevant context, "
                "or when the user references something discussed before."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query — natural language or keywords",
                    },
                    "project": {
                        "type": ["string", "null"],
                        "description": "Filter by project. null = search all projects.",
                    },
                    "type": {
                        "type": "string",
                        "enum": list(VALID_TYPES),
                        "description": "Filter by memory type.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results (default 10)",
                        "default": 10,
                    },
                    "include_links": {
                        "type": "boolean",
                        "description": "Include 1-hop linked memories in results",
                        "default": False,
                    },
                },
            },
        ),
        Tool(
            name="memory_get",
            description="Get a specific memory by exact name and project.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Exact memory name",
                    },
                    "project": {
                        "type": ["string", "null"],
                        "description": "Project scope. null = global.",
                    },
                },
                "required": ["name"],
            },
        ),
        Tool(
            name="memory_list",
            description=(
                "List all memories, optionally filtered by project and/or type. "
                "Returns name + description (not full content) for quick overview."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "project": {
                        "type": ["string", "null"],
                        "description": "Filter by project. Omit to list all.",
                    },
                    "type": {
                        "type": "string",
                        "enum": list(VALID_TYPES),
                        "description": "Filter by type.",
                    },
                },
            },
        ),
        Tool(
            name="memory_delete",
            description="Soft-delete a memory by name. Recoverable for 30 days via memory_restore.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Memory name to delete",
                    },
                    "project": {
                        "type": ["string", "null"],
                        "description": "Project scope. null = global.",
                    },
                },
                "required": ["name"],
            },
        ),
        Tool(
            name="memory_restore",
            description="Restore a soft-deleted memory within the 30-day retention window.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Memory name to restore",
                    },
                    "project": {
                        "type": ["string", "null"],
                        "description": "Project scope. null = global.",
                    },
                },
                "required": ["name"],
            },
        ),
        # ---- Event tools ----
        Tool(
            name="events_list",
            description=(
                "List events from the event queue. By default returns unprocessed events "
                "sorted by severity. GitHub Actions write events here; the orchestrator reads them."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "repo": {
                        "type": "string",
                        "description": "Filter by repo (e.g. 'Osasuwu/jarvis')",
                    },
                    "event_type": {
                        "type": "string",
                        "description": "Filter by event type (e.g. 'ci_failure', 'pr_approved')",
                    },
                    "severity": {
                        "type": "string",
                        "enum": ["critical", "high", "medium", "low", "info"],
                        "description": "Filter by minimum severity",
                    },
                    "include_processed": {
                        "type": "boolean",
                        "description": "Include already-processed events (default: false)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results (default 20)",
                        "default": 20,
                    },
                },
            },
        ),
        Tool(
            name="events_mark_processed",
            description=(
                "Mark one or more events as processed. "
                "Call after the orchestrator has handled an event."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "event_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of event UUIDs to mark as processed",
                    },
                    "processed_by": {
                        "type": "string",
                        "description": "Who processed it (e.g. 'autonomous-loop', 'risk-radar', 'manual')",
                    },
                    "action_taken": {
                        "type": "string",
                        "description": "What was done in response",
                    },
                },
                "required": ["event_ids", "processed_by"],
            },
        ),
        # ---- Outcome tracking tools (Pillar 3) ----
        Tool(
            name="outcome_record",
            description=(
                "Record a task outcome for tracking and learning. "
                "Call after completing a delegation, fix, research, or autonomous action."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "task_type": {
                        "type": "string",
                        "enum": ["delegation", "research", "fix", "review", "autonomous"],
                        "description": "Type of action performed.",
                    },
                    "task_description": {
                        "type": "string",
                        "description": "What was done (concise).",
                    },
                    "outcome_status": {
                        "type": "string",
                        "enum": ["pending", "success", "partial", "failure", "unknown"],
                        "description": "Outcome: success/partial/failure/pending/unknown.",
                    },
                    "outcome_summary": {
                        "type": "string",
                        "description": "What actually happened.",
                    },
                    "goal_slug": {
                        "type": ["string", "null"],
                        "description": "Related goal slug.",
                    },
                    "project": {
                        "type": ["string", "null"],
                        "description": "Project scope.",
                    },
                    "issue_url": {"type": "string", "description": "GitHub issue URL."},
                    "pr_url": {"type": "string", "description": "GitHub PR URL."},
                    "tests_passed": {"type": "boolean"},
                    "pr_merged": {"type": "boolean"},
                    "quality_score": {
                        "type": "integer",
                        "description": "Quality 0-100.",
                    },
                    "lessons": {"type": "string", "description": "What was learned."},
                    "pattern_tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Pattern tags for learning.",
                    },
                },
                "required": ["task_type", "task_description", "outcome_status"],
            },
        ),
        Tool(
            name="outcome_update",
            description=(
                "Update a task outcome after verification. Use to flip status from pending "
                "to success/failure, record verified_at, pr_merged, lessons, etc."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Outcome UUID to update."},
                    "outcome_status": {
                        "type": "string",
                        "enum": ["pending", "success", "partial", "failure", "unknown"],
                    },
                    "outcome_summary": {"type": "string"},
                    "pr_merged": {"type": "boolean"},
                    "tests_passed": {"type": "boolean"},
                    "quality_score": {"type": "integer", "description": "0-100."},
                    "lessons": {"type": "string"},
                    "pattern_tags": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "verified_at": {
                        "type": "string",
                        "description": "ISO timestamp. Defaults to now() if omitted when status changes.",
                    },
                },
                "required": ["id"],
            },
        ),
        Tool(
            name="outcome_list",
            description=(
                "List recent task outcomes, optionally filtered by project, goal, status, or pattern_tags. "
                "Use to review what worked and what didn't."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "project": {
                        "type": ["string", "null"],
                        "description": "Filter by project.",
                    },
                    "goal_slug": {
                        "type": ["string", "null"],
                        "description": "Filter by goal slug.",
                    },
                    "outcome_status": {
                        "type": "string",
                        "enum": ["pending", "success", "partial", "failure", "unknown"],
                    },
                    "pattern_tag": {
                        "type": "string",
                        "description": "Filter by pattern tag (outcomes containing this tag).",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results (default 20).",
                        "default": 20,
                    },
                },
            },
        ),
        # ---- Graph tools ----
        Tool(
            name="memory_graph",
            description=(
                "Explore the memory link graph. "
                "Modes: 'overview' (stats, top connected, orphans), "
                "'links' (all connections for a specific memory by name), "
                "'clusters' (groups of tightly connected memories for consolidation)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "mode": {
                        "type": "string",
                        "enum": ["overview", "links", "clusters"],
                        "description": (
                            "overview = link stats + top connected + orphans. "
                            "links = all connections for a memory (requires 'name'). "
                            "clusters = tightly connected groups."
                        ),
                    },
                    "name": {
                        "type": "string",
                        "description": "Memory name (required for 'links' mode).",
                    },
                },
                "required": ["mode"],
            },
        ),
        # ---- Credential registry tools (Pillar 9) ----
        Tool(
            name="credential_list",
            description=(
                "List registered credentials (metadata only — never returns secret values). "
                "Shows service name, env var name, storage location, expiry, rotation notes."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "scope": {
                        "type": ["string", "null"],
                        "description": "Filter by scope (e.g. 'jarvis'). null = all.",
                    },
                },
            },
        ),
        Tool(
            name="credential_add",
            description=(
                "Register a credential in the metadata-only registry. "
                "Stores service name, env var name, where it's kept, and rotation info. "
                "NEVER pass actual secret values — the table rejects them."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "service": {"type": "string", "description": "Service name (e.g. 'Supabase', 'GitHub')"},
                    "env_var": {"type": "string", "description": "Env variable NAME, not value (e.g. 'SUPABASE_KEY')"},
                    "stored_in": {
                        "type": "string",
                        "description": "Where the value lives (e.g. '.env', 'GitHub Actions', 'system env')",
                        "default": ".env",
                    },
                    "scope": {
                        "type": "string",
                        "description": "Project scope (e.g. 'jarvis')",
                        "default": "jarvis",
                    },
                    "expires_at": {
                        "type": ["string", "null"],
                        "description": "Expiry date ISO format (null = no expiry)",
                    },
                    "rotation_notes": {
                        "type": ["string", "null"],
                        "description": "How to rotate (e.g. 'Anthropic Console → API Keys')",
                    },
                    "notes": {"type": ["string", "null"], "description": "Additional notes"},
                },
                "required": ["service", "env_var"],
            },
        ),
        Tool(
            name="credential_check_expiry",
            description=(
                "Check for credentials expiring within N days. "
                "Returns list with service, env var, expiry date, and rotation notes. "
                "Use in morning-brief for proactive alerts."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "days_ahead": {
                        "type": "integer",
                        "description": "Alert window in days (default 30)",
                        "default": 30,
                    },
                },
            },
        ),
    ]


# -- Tool handlers ----------------------------------------------------------

MAX_RESULT_CHARS = 100_000  # Claude Code default truncates at ~20k; memories can be large


def _big_result(content: list[TextContent]) -> CallToolResult:
    """Wrap content in CallToolResult with maxResultSizeChars to prevent truncation."""
    return CallToolResult(
        content=content,
        meta={"anthropic/maxResultSizeChars": MAX_RESULT_CHARS},
    )


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent] | CallToolResult:
    try:
        # Goal tools
        if name == "goal_set":
            return await _handle_goal_set(arguments)
        elif name == "goal_list":
            return _big_result(await _handle_goal_list(arguments))
        elif name == "goal_get":
            return _big_result(await _handle_goal_get(arguments))
        elif name == "goal_update":
            return await _handle_goal_update(arguments)
        # Memory tools
        elif name == "memory_store":
            return await _handle_store(arguments)
        elif name == "memory_recall":
            return _big_result(await _handle_recall(arguments))
        elif name == "memory_get":
            return _big_result(await _handle_get(arguments))
        elif name == "memory_list":
            return _big_result(await _handle_list(arguments))
        elif name == "memory_delete":
            return await _handle_delete(arguments)
        elif name == "memory_restore":
            return await _handle_restore(arguments)
        # Graph tools
        elif name == "memory_graph":
            return _big_result(await _handle_graph(arguments))
        # Outcome tracking tools (Pillar 3)
        elif name == "outcome_record":
            return await _handle_outcome_record(arguments)
        elif name == "outcome_update":
            return await _handle_outcome_update(arguments)
        elif name == "outcome_list":
            return _big_result(await _handle_outcome_list(arguments))
        # Credential registry tools (Pillar 9)
        elif name == "credential_list":
            return _big_result(await _handle_credential_list(arguments))
        elif name == "credential_add":
            return await _handle_credential_add(arguments)
        elif name == "credential_check_expiry":
            return _big_result(await _handle_credential_check_expiry(arguments))
        # Event tools
        elif name == "events_list":
            return _big_result(await _handle_events_list(arguments))
        elif name == "events_mark_processed":
            return await _handle_events_mark_processed(arguments)
        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]
    except Exception as exc:
        return [TextContent(type="text", text=f"Error: {exc}")]


# -- Goal handlers ----------------------------------------------------------

GOAL_FIELDS = (
    "slug", "title", "project", "direction", "priority", "status",
    "why", "success_criteria", "deadline", "progress", "progress_pct",
    "risks", "owner_focus", "jarvis_focus", "parent_id", "outcome", "lessons",
)


def _format_goal(g: dict) -> str:
    """Format a single goal for display."""
    deadline_str = f" | Deadline: {g['deadline']}" if g.get("deadline") else ""
    direction_str = f" | Direction: {g['direction']}" if g.get("direction") else ""
    parent_str = f" | Sub-goal of: {g['parent_id']}" if g.get("parent_id") else ""

    lines = [
        f"## {g['title']}",
        f"Slug: `{g['slug']}` | Project: {g.get('project') or 'cross-project'} | "
        f"Priority: {g['priority']} | Status: {g['status']}{deadline_str}{direction_str}{parent_str}",
    ]

    if g.get("why"):
        lines.append(f"\n**Why:** {g['why']}")

    if g.get("success_criteria"):
        criteria = g["success_criteria"]
        if isinstance(criteria, str):
            import json as _json
            try:
                criteria = _json.loads(criteria)
            except (ValueError, TypeError):
                criteria = [criteria]
        if criteria:
            lines.append("\n**Success criteria:**")
            for c in criteria:
                lines.append(f"- {c}")

    if g.get("progress"):
        progress = g["progress"]
        if isinstance(progress, str):
            import json as _json
            try:
                progress = _json.loads(progress)
            except (ValueError, TypeError):
                progress = []
        if progress:
            pct = g.get("progress_pct", 0)
            lines.append(f"\n**Progress ({pct}%):**")
            for p in progress:
                check = "x" if p.get("done") else " "
                lines.append(f"- [{check}] {p.get('item', p)}")

    if g.get("risks"):
        risks = g["risks"]
        if isinstance(risks, str):
            import json as _json
            try:
                risks = _json.loads(risks)
            except (ValueError, TypeError):
                risks = [risks]
        if risks:
            lines.append("\n**Risks:**")
            for r in risks:
                lines.append(f"- {r}")

    if g.get("owner_focus"):
        lines.append(f"\n**Owner focus:** {g['owner_focus']}")
    if g.get("jarvis_focus"):
        lines.append(f"**Jarvis focus:** {g['jarvis_focus']}")

    if g.get("outcome"):
        lines.append(f"\n**Outcome:** {g['outcome']}")
    if g.get("lessons"):
        lines.append(f"**Lessons:** {g['lessons']}")

    return "\n".join(lines)


async def _handle_goal_set(args: dict) -> list[TextContent]:
    client = _get_client()
    slug = args["slug"]

    data = {k: args[k] for k in GOAL_FIELDS if k in args}

    # Convert JSONB fields
    for field in ("success_criteria", "progress", "risks"):
        if field in data and isinstance(data[field], list):
            data[field] = json.dumps(data[field])

    # Upsert by slug
    existing = client.table("goals").select("id").eq("slug", slug).limit(1).execute()
    if existing.data:
        client.table("goals").update(data).eq("slug", slug).execute()
        _audit_log(client, "goal_set", "update", slug)
        return [TextContent(type="text", text=f"Goal '{slug}' updated.")]
    else:
        client.table("goals").insert(data).execute()
        _audit_log(client, "goal_set", "create", slug)
        return [TextContent(type="text", text=f"Goal '{slug}' created.")]


async def _handle_goal_list(args: dict) -> list[TextContent]:
    client = _get_client()

    q = client.table("goals").select("*")

    status = args.get("status")
    project = args.get("project")
    priority = args.get("priority")

    if status:
        q = q.eq("status", status)
    if project:
        q = q.eq("project", project)
    if priority:
        q = q.eq("priority", priority)

    result = q.order("priority").order("deadline", desc=False, nullsfirst=False).execute()

    if not result.data:
        return [TextContent(type="text", text="No goals found.")]

    formatted = [_format_goal(g) for g in result.data]
    return [TextContent(
        type="text",
        text=f"# Goals ({len(result.data)})\n\n" + "\n\n---\n\n".join(formatted),
    )]


async def _handle_goal_get(args: dict) -> list[TextContent]:
    client = _get_client()
    slug = args["slug"]

    result = client.table("goals").select("*").eq("slug", slug).limit(1).execute()

    if not result.data:
        return [TextContent(type="text", text=f"Goal '{slug}' not found.")]

    return [TextContent(type="text", text=_format_goal(result.data[0]))]


async def _handle_goal_update(args: dict) -> list[TextContent]:
    client = _get_client()
    slug = args["slug"]

    data = {k: args[k] for k in GOAL_FIELDS if k in args and k != "slug"}

    if not data:
        return [TextContent(type="text", text="No fields to update.")]

    # Convert JSONB fields
    for field in ("success_criteria", "progress", "risks"):
        if field in data and isinstance(data[field], list):
            data[field] = json.dumps(data[field])

    # Auto-set closed_at when status changes to achieved/abandoned
    if data.get("status") in ("achieved", "abandoned"):
        data["closed_at"] = datetime.now(timezone.utc).isoformat()

    result = client.table("goals").update(data).eq("slug", slug).execute()

    if not result.data:
        return [TextContent(type="text", text=f"Goal '{slug}' not found.")]

    status_note = ""
    if data.get("status") in ("achieved", "abandoned"):
        status_note = f" Status: {data['status']}. closed_at set."

    updated_fields = [k for k in data if k != "closed_at"]
    _audit_log(client, "goal_update", "update", slug, {"fields": updated_fields})
    return [TextContent(type="text", text=f"Goal '{slug}' updated.{status_note}")]


# -- Memory handlers --------------------------------------------------------

async def _handle_store(args: dict) -> list[TextContent]:
    client = _get_client()

    mem_type = args["type"]
    mem_name = args["name"]
    content = args["content"]
    description = args.get("description", "")
    project = args.get("project")
    if project == "global":
        project = None  # "global" and null are synonymous — normalize to NULL in DB
    tags = args.get("tags", [])

    if mem_type not in VALID_TYPES:
        return [TextContent(type="text", text=f"Invalid type: {mem_type}. Must be one of {VALID_TYPES}")]

    # Generate embedding (async httpx — 5s timeout, falls back gracefully)
    embed_text = f"{description}\n{content}".strip() if description else content
    embedding = await _embed(embed_text)

    data = {
        "type": mem_type,
        "name": mem_name,
        "content": content,
        "description": description,
        "project": project,
        "tags": tags,
        "deleted_at": None,  # clear soft-delete on store/upsert
    }

    if embedding is not None:
        data["embedding"] = embedding

    embed_note = " (with embedding)" if embedding is not None else ""

    if project is not None:
        # Atomic upsert via unique constraint on (project, name) — no race condition
        result = client.table("memories").upsert(data, on_conflict="project,name").execute()
        stored_id = result.data[0]["id"] if result.data else None
        action = "saved"
        proj_label = f"project={project}"
    else:
        # Manual upsert for NULL project: PostgreSQL unique constraint doesn't
        # deduplicate NULLs, so we handle this case explicitly.
        q = client.table("memories").select("id").eq("name", mem_name).is_("project", "null")
        existing = q.limit(1).execute()
        if existing.data:
            stored_id = existing.data[0]["id"]
            client.table("memories").update(data).eq("id", stored_id).execute()
            action = "updated"
        else:
            result = client.table("memories").insert(data).execute()
            stored_id = result.data[0]["id"] if result.data else None
            action = "created"
        proj_label = "project=global"

    msg = f"Memory '{mem_name}' {action} ({proj_label}){embed_note}"

    _audit_log(client, "memory_store", action, mem_name, {"project": project or "global", "type": mem_type})

    # -- Memory 2.0: auto-linking + consolidation hints --
    if embedding is not None and stored_id:
        try:
            similar = client.rpc("find_similar_memories", {
                "query_embedding": embedding,
                "exclude_id": stored_id,
                "match_limit": MAX_AUTO_LINKS + 5,
                "similarity_threshold": LINK_SIM_THRESHOLD,
                "filter_type": None,
            }).execute()
            similar_rows = similar.data or []

            # Consolidation hint: 3+ memories above 0.80 similarity
            consolidation_candidates = [
                r for r in similar_rows
                if r.get("similarity", 0) >= CONSOLIDATION_SIM_THRESHOLD
            ]
            if len(consolidation_candidates) >= CONSOLIDATION_COUNT:
                names = [r["name"] for r in consolidation_candidates[:5]]
                msg += f"\n\n⚠ Consolidation hint: {len(consolidation_candidates)} similar memories found: {', '.join(names)}"

            # Fire-and-forget: create links
            if similar_rows:
                asyncio.create_task(_create_auto_links(client, stored_id, similar_rows, mem_type))
        except Exception:
            pass  # auto-linking is best-effort, never blocks store

    return [TextContent(type="text", text=msg)]


SIMILARITY_THRESHOLD = 0.25  # minimum cosine similarity to include in results


async def _handle_recall(args: dict) -> list[TextContent]:
    client = _get_client()

    query_text = args.get("query", "")
    project = args.get("project")
    if project == "global":
        project = None
    mem_type = args.get("type")
    limit = args.get("limit", 10)

    include_links = args.get("include_links", False)

    # Hybrid search: combine semantic + keyword results via RRF + temporal scoring
    if query_text:
        query_embedding = await _embed_query(query_text)
        if query_embedding is not None:
            rows, results = await _hybrid_recall(
                client, query_embedding, query_text, project, mem_type, limit, include_links
            )
            # Track reads (fire-and-forget)
            ids = [r["id"] for r in rows if r.get("id")]
            if ids:
                asyncio.create_task(_touch_memories(client, ids))
            return results

    # Fallback: keyword-only search
    results = await _keyword_recall(client, query_text, project, mem_type, limit)

    # Lazily backfill embeddings for records missing them (fire-and-forget)
    if os.environ.get("VOYAGE_API_KEY"):
        asyncio.create_task(_backfill_missing_embeddings(client, project))

    return results


async def _hybrid_recall(
    client, query_embedding: list[float], query_text: str,
    project, mem_type, limit: int, include_links: bool = False
) -> list[TextContent]:
    """Hybrid search: server-side pgvector semantic + pg_trgm keyword, merged via RRF.

    Memory 2.0: adds temporal scoring (recency × access frequency) and optional
    1-hop link expansion for graph-aware recall.
    """
    try:
        # Fetch double the limit from each source to give RRF good candidates
        fetch_limit = limit * 2

        # Server-side semantic search via pgvector HNSW
        sem_result = client.rpc("match_memories", {
            "query_embedding": query_embedding,
            "match_limit": fetch_limit,
            "similarity_threshold": SIMILARITY_THRESHOLD,
            "filter_project": project,
            "filter_type": mem_type,
        }).execute()
        semantic_rows = sem_result.data or []

        # Server-side keyword search via pg_trgm
        kw_result = client.rpc("keyword_search_memories", {
            "search_query": query_text,
            "match_limit": fetch_limit,
            "filter_project": project,
            "filter_type": mem_type,
        }).execute()
        keyword_rows = kw_result.data or []

        # Reciprocal Rank Fusion (k=60) + temporal scoring
        merged = _rrf_merge(semantic_rows, keyword_rows, limit)

        if not merged:
            return [], await _keyword_recall(client, query_text, project, mem_type, limit)

        _apply_temporal_scoring(merged)

        formatted = _format_memories(merged)
        search_type = "hybrid+temporal" if keyword_rows else "semantic+temporal"
        text = f"Found {len(merged)} memories ({search_type} search):\n\n" + "\n---\n".join(formatted)

        # Optional: expand with 1-hop linked memories
        if include_links:
            ids = [r["id"] for r in merged if r.get("id")]
            if ids:
                linked = await _expand_with_links(client, ids)
                if linked:
                    # Deduplicate against already-found IDs and within linked results
                    found_ids = set(ids)
                    seen_linked = set()
                    unique_linked = []
                    for r in linked:
                        rid = r.get("id")
                        if rid not in found_ids and rid not in seen_linked:
                            seen_linked.add(rid)
                            unique_linked.append(r)
                    if unique_linked:
                        link_formatted = _format_memories(unique_linked, link_info=True)
                        text += f"\n\n### Linked memories ({len(unique_linked)}):\n\n" + "\n---\n".join(link_formatted)

        return merged, [TextContent(type="text", text=text)]

    except asyncio.CancelledError:
        raise
    except Exception:
        # RPC not available (e.g. migration not applied) — fall back to keyword
        return [], await _keyword_recall(client, query_text, project, mem_type, limit)


def _rrf_merge(semantic_rows: list[dict], keyword_rows: list[dict], limit: int, k: int = 60) -> list[dict]:
    """Reciprocal Rank Fusion: combine two ranked lists into one.

    Score = sum(1 / (k + rank)) for each list the item appears in.
    Higher k gives more weight to items appearing in both lists.
    """
    scores: dict[str, float] = {}
    by_id: dict[str, dict] = {}

    for rank, row in enumerate(semantic_rows):
        rid = row.get("id") or row["name"]
        scores[rid] = scores.get(rid, 0.0) + 1.0 / (k + rank)
        by_id[rid] = row

    for rank, row in enumerate(keyword_rows):
        rid = row.get("id") or row["name"]
        scores[rid] = scores.get(rid, 0.0) + 1.0 / (k + rank)
        by_id[rid] = row

    ranked = sorted(scores.keys(), key=lambda r: scores[r], reverse=True)
    result = []
    for rid in ranked[:limit]:
        row = by_id[rid]
        row["_rrf_score"] = scores[rid]
        result.append(row)
    return result


async def _keyword_recall(client, query_text: str, project, mem_type, limit: int) -> list[TextContent]:
    """ILIKE keyword search (fallback when semantic unavailable)."""
    q = client.table("memories").select("name, type, project, description, content, tags, updated_at").is_("deleted_at", "null")

    if project is not None:
        q = q.or_(f"project.eq.{project},project.is.null")
    if mem_type:
        q = q.eq("type", mem_type)

    if query_text:
        terms = query_text.split()
        clauses = ",".join(
            f"name.ilike.%{t}%,description.ilike.%{t}%,content.ilike.%{t}%"
            for t in terms
        )
        q = q.or_(clauses)

    result = q.limit(limit).order("updated_at", desc=True).execute()

    if not result.data:
        return [TextContent(type="text", text="No memories found.")]

    formatted = _format_memories(result.data)
    return [TextContent(type="text", text=f"Found {len(result.data)} memories (keyword search):\n\n" + "\n---\n".join(formatted))]


async def _touch_memories(client, ids: list[str]) -> None:
    """Fire-and-forget: update last_accessed_at for accessed memories via RPC."""
    try:
        client.rpc("touch_memories", {"memory_ids": ids}).execute()
    except Exception:
        pass


def _format_memories(memories: list[dict], link_info: bool = False) -> list[str]:
    formatted = []
    for mem in memories:
        tags_str = f" [{', '.join(mem.get('tags', []))}]" if mem.get("tags") else ""
        link_str = ""
        if link_info and mem.get("link_type"):
            link_str = f" ← {mem['link_type']}"
            if mem.get("link_strength"):
                link_str += f" ({mem['link_strength']:.2f})"
        formatted.append(
            f"## {mem['name']} ({mem['type']}, {mem.get('project') or 'global'}){tags_str}{link_str}\n"
            f"*{mem.get('description', '')}*\n"
            f"Updated: {mem.get('updated_at', '?')}\n\n"
            f"{mem['content']}\n"
        )
    return formatted


async def _backfill_missing_embeddings(client, project) -> None:
    """Fire-and-forget: generate embeddings for records saved without one.

    Batches all missing records into a single Voyage AI call.
    """
    try:
        q = client.table("memories").select("id, description, content")
        q = q.is_("embedding", "null").is_("deleted_at", "null")
        if project is not None:
            q = q.or_(f"project.eq.{project},project.is.null")
        rows = q.execute().data
        if not rows:
            return

        texts = [f"{r.get('description', '')}\n{r['content']}".strip() for r in rows]
        embeddings = await _embed_batch(texts)
        if embeddings is None:
            return

        for mem, embedding in zip(rows, embeddings):
            client.table("memories").update({"embedding": embedding}).eq("id", mem["id"]).execute()
    except Exception:
        pass  # fire-and-forget: silently swallow all errors so caller never fails


async def _create_auto_links(client, stored_id: str, similar_rows: list[dict], mem_type: str) -> None:
    """Fire-and-forget: create links between stored memory and similar ones."""
    try:
        links = []
        for row in similar_rows[:MAX_AUTO_LINKS]:
            sim = row.get("similarity", 0)
            # Supersession: two decisions with very high similarity
            if mem_type == "decision" and row.get("type") == "decision" and sim >= SUPERSEDE_SIM_THRESHOLD:
                link_type = "supersedes"
            else:
                link_type = "related"
            links.append({
                "source_id": stored_id,
                "target_id": row["id"],
                "link_type": link_type,
                "strength": round(sim, 3),
            })
        if links:
            client.table("memory_links").upsert(
                links, on_conflict="source_id,target_id,link_type"
            ).execute()
    except Exception:
        pass


async def _expand_with_links(client, memory_ids: list[str]) -> list[dict]:
    """Fetch 1-hop linked memories via graph traversal RPC."""
    try:
        result = client.rpc("get_linked_memories", {
            "memory_ids": memory_ids,
            "link_types": None,
        }).execute()
        return result.data or []
    except Exception:
        return []


def _apply_temporal_scoring(rows: list[dict]) -> list[dict]:
    """Re-rank rows by combining RRF score with temporal decay and access frequency."""
    now = datetime.now(timezone.utc)
    for row in rows:
        rrf = row.get("_rrf_score", 0.01)
        mem_type = row.get("type", "decision")
        half_life = TEMPORAL_HALF_LIVES.get(mem_type, DEFAULT_HALF_LIFE)

        # Parse updated_at
        updated_str = row.get("updated_at", "")
        try:
            updated = datetime.fromisoformat(updated_str.replace("Z", "+00:00"))
            days_since_update = max(0, (now - updated).total_seconds() / 86400)
        except (ValueError, AttributeError):
            days_since_update = half_life  # assume mid-decay if unparsable

        # Parse last_accessed_at
        accessed_str = row.get("last_accessed_at") or ""
        try:
            accessed = datetime.fromisoformat(accessed_str.replace("Z", "+00:00"))
            days_since_access = max(0, (now - accessed).total_seconds() / 86400)
        except (ValueError, AttributeError):
            days_since_access = days_since_update * 2  # never accessed = low boost

        # Exponential decay: recency factor (0..1)
        recency = math.exp(-0.693 * days_since_update / half_life)
        # Access frequency boost (1..1+ACCESS_BOOST_MAX)
        access = 1.0 + ACCESS_BOOST_MAX * math.exp(-0.693 * days_since_access / ACCESS_HALF_LIFE)

        row["_temporal_score"] = rrf * recency * access

    rows.sort(key=lambda r: r.get("_temporal_score", 0), reverse=True)
    return rows


async def _handle_get(args: dict) -> list[TextContent]:
    client = _get_client()

    mem_name = args["name"]
    project = args.get("project")
    if project == "global":
        project = None

    q = client.table("memories").select("*").eq("name", mem_name).is_("deleted_at", "null")
    if project is not None:
        q = q.eq("project", project)
    else:
        q = q.is_("project", "null")

    result = q.limit(1).execute()

    if not result.data:
        return [TextContent(type="text", text=f"Memory '{mem_name}' not found (project={project or 'global'}).")]

    mem = result.data[0]
    tags_str = f"\nTags: {', '.join(mem.get('tags', []))}" if mem.get("tags") else ""
    return [TextContent(
        type="text",
        text=(
            f"## {mem['name']}\n"
            f"Type: {mem['type']} | Project: {mem.get('project') or 'global'}{tags_str}\n"
            f"Created: {mem.get('created_at')} | Updated: {mem.get('updated_at')}\n"
            f"Description: {mem.get('description', '')}\n\n"
            f"{mem['content']}"
        ),
    )]


async def _handle_list(args: dict) -> list[TextContent]:
    client = _get_client()

    project = args.get("project")
    if project == "global":
        project = None
    mem_type = args.get("type")

    q = client.table("memories").select("name, type, project, description, updated_at").is_("deleted_at", "null")

    if project is not None:
        q = q.or_(f"project.eq.{project},project.is.null")
    if mem_type:
        q = q.eq("type", mem_type)

    result = q.order("type").order("updated_at", desc=True).execute()

    if not result.data:
        return [TextContent(type="text", text="No memories found.")]

    lines = []
    current_type = None
    for mem in result.data:
        if mem["type"] != current_type:
            current_type = mem["type"]
            lines.append(f"\n### {current_type.upper()}")
        proj = mem.get("project") or "global"
        desc = f" — {mem['description']}" if mem.get("description") else ""
        lines.append(f"- **{mem['name']}** ({proj}){desc}")

    return [TextContent(type="text", text=f"## All Memories ({len(result.data)} total)\n" + "\n".join(lines))]


async def _handle_delete(args: dict) -> list[TextContent]:
    client = _get_client()

    mem_name = args["name"]
    project = args.get("project")
    if project == "global":
        project = None  # normalize "global" → NULL, same as in _handle_store

    q = client.table("memories").update({"deleted_at": datetime.now(timezone.utc).isoformat()}).eq("name", mem_name).is_("deleted_at", "null")
    if project is not None:
        q = q.eq("project", project)
    else:
        q = q.is_("project", "null")

    result = q.execute()

    if result.data:
        _audit_log(client, "memory_delete", "soft_delete", mem_name, {"project": project or "global"})
        return [TextContent(type="text", text=f"Soft-deleted memory '{mem_name}' (project={project or 'global'}). Recoverable for 30 days via memory_restore.")]
    return [TextContent(type="text", text=f"Memory '{mem_name}' not found.")]


async def _handle_restore(args: dict) -> list[TextContent]:
    client = _get_client()

    mem_name = args["name"]
    project = args.get("project")
    if project == "global":
        project = None

    q = client.table("memories").update({"deleted_at": None}).eq("name", mem_name).not_.is_("deleted_at", "null")
    if project is not None:
        q = q.eq("project", project)
    else:
        q = q.is_("project", "null")

    result = q.execute()

    if result.data:
        _audit_log(client, "memory_restore", "restore", mem_name, {"project": project or "global"})
        return [TextContent(type="text", text=f"Restored memory '{mem_name}' (project={project or 'global'}).")]
    return [TextContent(type="text", text=f"No soft-deleted memory '{mem_name}' found.")]


# -- Graph handlers ---------------------------------------------------------


async def _handle_graph(args: dict) -> list[TextContent]:
    mode = args.get("mode", "overview")
    client = _get_client()

    if mode == "overview":
        return await _graph_overview(client)
    elif mode == "links":
        name = args.get("name")
        if not name:
            return [TextContent(type="text", text="Error: 'name' is required for 'links' mode.")]
        return await _graph_links(client, name)
    elif mode == "clusters":
        return await _graph_clusters(client)
    else:
        return [TextContent(type="text", text=f"Unknown graph mode: {mode}")]


async def _graph_overview(client) -> list[TextContent]:
    """Graph overview: link stats, top connected memories, orphans."""
    lines = ["## Memory Graph Overview\n"]

    # 1. Link stats by type
    all_links = client.table("memory_links").select("link_type, strength").execute()
    link_data = all_links.data or []
    total = len(link_data)

    if total == 0:
        return [TextContent(type="text", text="No memory links found. Store more memories to build the graph.")]

    type_stats: dict[str, list[float]] = {}
    for row in link_data:
        lt = row["link_type"]
        type_stats.setdefault(lt, []).append(row["strength"])

    lines.append(f"### Link Statistics ({total} total)\n")
    lines.append("| Type | Count | Avg Strength | Min | Max |")
    lines.append("|------|-------|-------------|-----|-----|")
    for lt, strengths in sorted(type_stats.items()):
        avg = sum(strengths) / len(strengths)
        lines.append(f"| {lt} | {len(strengths)} | {avg:.3f} | {min(strengths):.3f} | {max(strengths):.3f} |")

    # 2. Top connected memories
    links_src = client.table("memory_links").select("source_id").execute()
    links_tgt = client.table("memory_links").select("target_id").execute()
    counts: dict[str, int] = {}
    for row in links_src.data or []:
        mid = row["source_id"]
        counts[mid] = counts.get(mid, 0) + 1
    for row in links_tgt.data or []:
        mid = row["target_id"]
        counts[mid] = counts.get(mid, 0) + 1

    top_ids = sorted(counts.keys(), key=lambda k: counts[k], reverse=True)[:10]
    if top_ids:
        # Fetch names for top IDs
        names_result = client.table("memories").select("id, name, type, project").in_("id", top_ids).is_("deleted_at", "null").execute()
        id_to_mem = {r["id"]: r for r in (names_result.data or [])}

        lines.append(f"\n### Top Connected ({len(top_ids)})\n")
        lines.append("| Memory | Type | Project | Links |")
        lines.append("|--------|------|---------|-------|")
        for mid in top_ids:
            mem = id_to_mem.get(mid, {})
            name = mem.get("name", mid[:8])
            mtype = mem.get("type", "?")
            proj = mem.get("project") or "global"
            lines.append(f"| {name} | {mtype} | {proj} | {counts[mid]} |")

    # 3. Orphans (have embedding, no links)
    total_with_emb = client.table("memories").select("id", count="exact").not_.is_("embedding", "null").is_("deleted_at", "null").execute()
    total_emb_count = total_with_emb.count or 0
    linked_ids = set(counts.keys())
    all_emb = client.table("memories").select("id, name, type, project").not_.is_("embedding", "null").is_("deleted_at", "null").execute()
    orphans = [r for r in (all_emb.data or []) if r["id"] not in linked_ids]

    lines.append(f"\n### Orphans ({len(orphans)} of {total_emb_count} embedded memories have no links)\n")
    if orphans:
        for o in orphans[:15]:
            proj = o.get("project") or "global"
            lines.append(f"- **{o['name']}** ({o['type']}, {proj})")
        if len(orphans) > 15:
            lines.append(f"- ... and {len(orphans) - 15} more")

    return [TextContent(type="text", text="\n".join(lines))]


async def _graph_links(client, name: str) -> list[TextContent]:
    """All connections for a specific memory."""
    # Find memory by name
    mem_result = client.table("memories").select("id, name, type, project").eq("name", name).is_("deleted_at", "null").execute()
    if not mem_result.data:
        return [TextContent(type="text", text=f"Memory '{name}' not found.")]

    mem = mem_result.data[0]
    mem_id = mem["id"]
    proj = mem.get("project") or "global"

    lines = [f"## Links for: {name} ({mem['type']}, {proj})\n"]

    # Outgoing links (this memory → others)
    out_result = (
        client.table("memory_links")
        .select("target_id, link_type, strength")
        .eq("source_id", mem_id)
        .order("strength", desc=True)
        .execute()
    )
    out_links = out_result.data or []

    # Incoming links (others → this memory)
    in_result = (
        client.table("memory_links")
        .select("source_id, link_type, strength")
        .eq("target_id", mem_id)
        .order("strength", desc=True)
        .execute()
    )
    in_links = in_result.data or []

    # Resolve target/source names
    all_ids = [r["target_id"] for r in out_links] + [r["source_id"] for r in in_links]
    id_to_name = {}
    if all_ids:
        names = client.table("memories").select("id, name, type, project").in_("id", all_ids).is_("deleted_at", "null").execute()
        id_to_name = {r["id"]: r for r in (names.data or [])}

    # Format outgoing
    lines.append(f"### Outgoing ({len(out_links)})\n")
    if out_links:
        for link in out_links:
            target = id_to_name.get(link["target_id"], {})
            tname = target.get("name", link["target_id"][:8])
            ttype = target.get("type", "?")
            lines.append(f"- → **{tname}** ({ttype}) [{link['link_type']}, {link['strength']:.3f}]")
    else:
        lines.append("- (none)")

    # Format incoming
    lines.append(f"\n### Incoming ({len(in_links)})\n")
    if in_links:
        for link in in_links:
            source = id_to_name.get(link["source_id"], {})
            sname = source.get("name", link["source_id"][:8])
            stype = source.get("type", "?")
            lines.append(f"- ← **{sname}** ({stype}) [{link['link_type']}, {link['strength']:.3f}]")
    else:
        lines.append("- (none)")

    return [TextContent(type="text", text="\n".join(lines))]


async def _graph_clusters(client) -> list[TextContent]:
    """Find clusters of tightly connected memories (mutual links, strength > 0.7)."""
    # Get all strong links
    links_result = (
        client.table("memory_links")
        .select("source_id, target_id, link_type, strength")
        .gte("strength", 0.7)
        .execute()
    )
    links = links_result.data or []

    if not links:
        return [TextContent(type="text", text="No strong links (strength >= 0.7) found.")]

    # Build adjacency: collect neighbors for each memory
    neighbors: dict[str, set[str]] = {}
    link_info: dict[tuple[str, str], dict] = {}
    for link in links:
        s, t = link["source_id"], link["target_id"]
        neighbors.setdefault(s, set()).add(t)
        neighbors.setdefault(t, set()).add(s)
        link_info[(s, t)] = link

    # Simple clustering: connected components via BFS
    visited: set[str] = set()
    clusters: list[set[str]] = []
    for node in neighbors:
        if node in visited:
            continue
        cluster: set[str] = set()
        queue = [node]
        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            cluster.add(current)
            for neighbor in neighbors.get(current, set()):
                if neighbor not in visited:
                    queue.append(neighbor)
        if len(cluster) >= 2:
            clusters.append(cluster)

    # Sort clusters by size (largest first)
    clusters.sort(key=len, reverse=True)

    # Resolve names
    all_ids = list(set().union(*clusters)) if clusters else []
    id_to_mem = {}
    if all_ids:
        mems = client.table("memories").select("id, name, type, project").in_("id", all_ids).is_("deleted_at", "null").execute()
        id_to_mem = {r["id"]: r for r in (mems.data or [])}

    lines = [f"## Memory Clusters ({len(clusters)} clusters, strength >= 0.7)\n"]

    for i, cluster in enumerate(clusters[:10], 1):
        # Calculate average internal strength
        internal_strengths = []
        for s, t in link_info:
            if s in cluster and t in cluster:
                internal_strengths.append(link_info[(s, t)]["strength"])

        avg_str = sum(internal_strengths) / len(internal_strengths) if internal_strengths else 0

        lines.append(f"### Cluster {i} ({len(cluster)} memories, avg strength: {avg_str:.3f})\n")
        for mid in sorted(cluster, key=lambda m: id_to_mem.get(m, {}).get("name", "")):
            mem = id_to_mem.get(mid, {})
            name = mem.get("name", mid[:8])
            mtype = mem.get("type", "?")
            proj = mem.get("project") or "global"
            lines.append(f"- **{name}** ({mtype}, {proj})")
        lines.append("")

    if len(clusters) > 10:
        lines.append(f"... and {len(clusters) - 10} more clusters")

    return [TextContent(type="text", text="\n".join(lines))]


# -- Event handlers ---------------------------------------------------------

async def _handle_events_list(args: dict) -> list[TextContent]:
    client = _get_client()

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
    events = sorted(result.data, key=lambda e: (SEVERITY_ORDER.get(e["severity"], 4), e["created_at"]))

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
    client = _get_client()

    event_ids = args["event_ids"]
    processed_by = args["processed_by"]
    action_taken = args.get("action_taken", "")

    now = datetime.now(timezone.utc).isoformat()

    updated = 0
    for eid in event_ids:
        result = client.table("events").update({
            "processed": True,
            "processed_at": now,
            "processed_by": processed_by,
            "action_taken": action_taken,
        }).eq("id", eid).execute()
        if result.data:
            updated += 1

    return [TextContent(type="text", text=f"Marked {updated}/{len(event_ids)} events as processed.")]


# -- Outcome tracking handlers (Pillar 3) ------------------------------------


async def _handle_outcome_record(args: dict) -> list[TextContent]:
    """Record a task outcome to task_outcomes table."""
    client = _get_client()

    row = {
        "task_type": args["task_type"],
        "task_description": args["task_description"],
        "outcome_status": args["outcome_status"],
    }
    # Optional fields
    for key in (
        "outcome_summary", "goal_slug", "project", "issue_url", "pr_url",
        "tests_passed", "pr_merged", "quality_score", "lessons",
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
    client = _get_client()
    oid = args["id"]

    updates: dict = {}
    for key in (
        "outcome_status", "outcome_summary", "pr_merged", "tests_passed",
        "quality_score", "lessons", "pattern_tags",
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
    client = _get_client()
    limit = args.get("limit", 20)

    query = (
        client.table("task_outcomes")
        .select("id, task_type, task_description, outcome_status, outcome_summary, "
                "goal_slug, project, pr_url, tests_passed, pr_merged, quality_score, "
                "lessons, pattern_tags, created_at, verified_at")
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
        status_icon = {"success": "+", "partial": "~", "failure": "-", "pending": "?", "unknown": "."}.get(
            o["outcome_status"], "?"
        )
        lines.append(
            f"[{status_icon}] {o['task_type']}: {o['task_description']}"
        )
        if o.get("outcome_summary"):
            lines.append(f"    {o['outcome_summary']}")
        if o.get("goal_slug"):
            lines.append(f"    Goal: {o['goal_slug']}")
        if o.get("lessons"):
            lines.append(f"    Lesson: {o['lessons']}")
        lines.append(f"    {o['created_at'][:10]} | {o['outcome_status']}")
        lines.append("")

    return [TextContent(type="text", text="\n".join(lines))]


# -- Credential registry handlers (Pillar 9) --------------------------------


async def _handle_credential_list(args: dict) -> list[TextContent]:
    """List registered credentials — metadata only, never secret values."""
    client = _get_client()
    query = (
        client.table("credential_registry")
        .select("service, env_var, stored_in, scope, expires_at, last_rotated_at, rotation_notes, notes")
        .order("service")
    )
    if args.get("scope"):
        query = query.eq("scope", args["scope"])

    result = query.execute()
    if not result.data:
        return [TextContent(type="text", text="No credentials registered.")]

    lines = [f"# Credential Registry ({len(result.data)} entries)\n"]
    for c in result.data:
        expiry = f" | Expires: {c['expires_at'][:10]}" if c.get("expires_at") else ""
        rotated = f" | Last rotated: {c['last_rotated_at'][:10]}" if c.get("last_rotated_at") else ""
        lines.append(f"**{c['service']}** — `{c['env_var']}`")
        lines.append(f"  Stored in: {c['stored_in']} | Scope: {c['scope']}{expiry}{rotated}")
        if c.get("rotation_notes"):
            lines.append(f"  Rotation: {c['rotation_notes']}")
        if c.get("notes"):
            lines.append(f"  Note: {c['notes']}")
        lines.append("")

    return [TextContent(type="text", text="\n".join(lines))]


async def _handle_credential_add(args: dict) -> list[TextContent]:
    """Register a new credential (metadata only)."""
    client = _get_client()

    row = {
        "service": args["service"],
        "env_var": args["env_var"],
        "stored_in": args.get("stored_in", ".env"),
        "scope": args.get("scope", "jarvis"),
    }
    for key in ("expires_at", "rotation_notes", "notes"):
        if args.get(key):
            row[key] = args[key]

    result = (
        client.table("credential_registry")
        .upsert(row, on_conflict="env_var")
        .execute()
    )
    if result.data:
        return [TextContent(type="text", text=f"Credential registered: {args['service']} ({args['env_var']})")]
    return [TextContent(type="text", text="Failed to register credential.")]


async def _handle_credential_check_expiry(args: dict) -> list[TextContent]:
    """Check for credentials expiring within N days."""
    client = _get_client()
    days = args.get("days_ahead", 30)

    # Calculate the cutoff date
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()

    result = (
        client.table("credential_registry")
        .select("service, env_var, expires_at, rotation_notes")
        .not_.is_("expires_at", "null")
        .lte("expires_at", cutoff)
        .order("expires_at")
        .execute()
    )

    if not result.data:
        return [TextContent(type="text", text=f"No credentials expiring within {days} days.")]

    lines = [f"# Credentials expiring within {days} days ({len(result.data)})\n"]
    for c in result.data:
        exp_date = c["expires_at"][:10] if c.get("expires_at") else "?"
        lines.append(f"**{c['service']}** — `{c['env_var']}` — expires {exp_date}")
        if c.get("rotation_notes"):
            lines.append(f"  How to rotate: {c['rotation_notes']}")
        lines.append("")

    return [TextContent(type="text", text="\n".join(lines))]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
