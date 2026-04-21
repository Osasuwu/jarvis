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
        # override=True: a blank OS-level export (e.g. ANTHROPIC_API_KEY="")
        # would otherwise shadow the real value in .env. Repo .env is the
        # source of truth for this server's secrets.
        load_dotenv(_env_path, override=True)
        break

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolResult, TextContent, Tool

# Phase 2b classifier — local module, optional at runtime.
# If ANTHROPIC_API_KEY is unset or the import fails (e.g. in unit tests that
# stub httpx) we silently fall back to the legacy heuristic.
try:
    from classifier import (  # type: ignore
        classify_write,
        ClassifierDecision,
        CLASSIFIER_MODEL,
    )
except Exception:  # pragma: no cover — defensive
    classify_write = None  # type: ignore
    ClassifierDecision = None  # type: ignore
    CLASSIFIER_MODEL = "claude-haiku-4-5"

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


def _audit_log(
    client, tool_name: str, action: str, target: str | None = None, details: dict | None = None
):
    """Fire-and-forget audit log entry. Never fails the caller."""
    try:
        client.table("audit_log").insert(
            {
                "tool_name": tool_name,
                "action": action,
                "target": target,
                "details": details or {},
            }
        ).execute()
    except Exception:
        pass  # audit is best-effort — never block operations


# ---------------------------------------------------------------------------
# Voyage AI embedding — async via httpx (properly cancellable, no thread blocking)
# ---------------------------------------------------------------------------

VOYAGE_API_URL = "https://api.voyageai.com/v1/embeddings"
VOYAGE_MODEL = "voyage-3-lite"
EMBED_TIMEOUT = 30.0  # seconds

# #242 dual-embedding machinery. PRIMARY drives reads (which RPC is called
# + what model embeds the query). SECONDARY, if set, enables dual-write so
# the v2 column fills up in parallel without touching the read path.
# When SECONDARY is unset, behavior is bit-identical to pre-#242.
EMBEDDING_MODEL_PRIMARY = os.environ.get("EMBEDDING_MODEL_PRIMARY", VOYAGE_MODEL)
EMBEDDING_MODEL_SECONDARY = os.environ.get("EMBEDDING_MODEL_SECONDARY") or None

# Model → (column, RPC, version-tag) mapping. Extend here when adding a
# new supported model. Keep the table read-only at runtime.
EMBEDDING_MODELS = {
    "voyage-3-lite": {
        "embedding_column": "embedding",
        "model_column": "embedding_model",
        "version_column": "embedding_version",
        "rpc": "match_memories",
        "version_tag": "v2",  # Phase 2a canonical form
    },
    "voyage-3": {
        "embedding_column": "embedding_v2",
        "model_column": "embedding_model_v2",
        "version_column": "embedding_version_v2",
        "rpc": "match_memories_v2",
        "version_tag": "v2",
    },
}


def _model_slot(model: str) -> dict:
    """Look up the column/RPC slot for a model. Falls back to PRIMARY for
    unknown models so misconfiguration never crashes startup — it just
    degrades to legacy behavior."""
    return EMBEDDING_MODELS.get(model) or EMBEDDING_MODELS[VOYAGE_MODEL]


async def _embed(
    text: str, input_type: str = "document", model: str | None = None
) -> list[float] | None:
    """Call Voyage AI REST API asynchronously. Retries up to 3x on 429."""
    api_key = os.environ.get("VOYAGE_API_KEY")
    if not api_key:
        return None
    use_model = model or VOYAGE_MODEL
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=EMBED_TIMEOUT) as client:
                resp = await client.post(
                    VOYAGE_API_URL,
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={"model": use_model, "input": [text], "input_type": input_type},
                )
                resp.raise_for_status()
                return resp.json()["data"][0]["embedding"]
        except asyncio.CancelledError:
            raise
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429 and attempt < 2:
                await asyncio.sleep(2**attempt)
                continue
            return None
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError):
            return None
    return None


async def _embed_batch(
    texts: list[str], input_type: str = "document", model: str | None = None
) -> list[list[float]] | None:
    """Embed multiple texts in a single API call (up to 1000 per request)."""
    api_key = os.environ.get("VOYAGE_API_KEY")
    if not api_key or not texts:
        return None
    use_model = model or VOYAGE_MODEL
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=EMBED_TIMEOUT) as client:
                resp = await client.post(
                    VOYAGE_API_URL,
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={"model": use_model, "input": texts, "input_type": input_type},
                )
                resp.raise_for_status()
                data = sorted(resp.json()["data"], key=lambda x: x["index"])
                return [item["embedding"] for item in data]
        except asyncio.CancelledError:
            raise
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429 and attempt < 2:
                await asyncio.sleep(2**attempt)
                continue
            return None
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError):
            return None
    return None


def _embed_upsert_fields(embedding: list[float], model: str) -> dict:
    """Build the dict of columns to upsert for a (embedding, model) pair.
    Returns {} if model is unknown (shouldn't happen at write time; silently
    degrades so we never corrupt rows)."""
    slot = EMBEDDING_MODELS.get(model)
    if not slot:
        return {}
    return {
        slot["embedding_column"]: embedding,
        slot["model_column"]: model,
        slot["version_column"]: slot["version_tag"],
    }


async def _compute_write_embeddings(text: str) -> dict:
    """Produce the full write-side embedding payload for one row.

    Always embeds with PRIMARY. If SECONDARY is set AND different from
    PRIMARY, also embeds with SECONDARY and merges columns. Returns a dict
    ready to splat into the upsert `data`.

    Failure mode: if PRIMARY embed fails → return {} (skip embedding). If
    PRIMARY succeeds but SECONDARY fails → write PRIMARY only (single-leg
    recovery; a future consolidation/backfill can fill the gap).
    """
    primary_vec = await _embed(text, model=EMBEDDING_MODEL_PRIMARY)
    if primary_vec is None:
        return {}
    fields = _embed_upsert_fields(primary_vec, EMBEDDING_MODEL_PRIMARY)
    if EMBEDDING_MODEL_SECONDARY and EMBEDDING_MODEL_SECONDARY != EMBEDDING_MODEL_PRIMARY:
        secondary_vec = await _embed(text, model=EMBEDDING_MODEL_SECONDARY)
        if secondary_vec is not None:
            fields.update(_embed_upsert_fields(secondary_vec, EMBEDDING_MODEL_SECONDARY))
    return fields


async def _embed_query(text: str) -> list[float] | None:
    # #242: read path embeds with PRIMARY so the vector matches whichever
    # column we're about to query via _hybrid_recall's RPC selection.
    return await _embed(text, input_type="query", model=EMBEDDING_MODEL_PRIMARY)


# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

server = Server("jarvis-memory")

VALID_TYPES = ("user", "project", "decision", "feedback", "reference")

VALID_GOAL_PRIORITIES = ("P0", "P1", "P2")
VALID_GOAL_STATUSES = ("active", "achieved", "paused", "abandoned")

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}

# -- Canonical embed form (Phase 2a) ---------------------------------------


def _canonical_embed_text(name: str, description: str, tags: list[str], content: str) -> str:
    """Build the text used for embedding. Structured so name/tags get weight.

    Why: a long-form memory whose key topic is in the name but whose content
    drifts into narrative detail embeds poorly — name/tags get drowned out.
    Prefixing them in a separate line gives them comparable weight under the
    tokenizer.
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


# -- Memory 2.0: temporal scoring + auto-linking ----------------------------
TEMPORAL_HALF_LIVES = {
    "project": 7,
    "reference": 30,
    "decision": 60,
    "feedback": 90,
    "user": 180,
}
DEFAULT_HALF_LIFE = 30
ACCESS_BOOST_MAX = 0.3
ACCESS_HALF_LIFE = 14
# Phase 1 polish (#240): entrenchment multiplier (ACT-R / Gärdenfors). Folds
# memories.confidence into temporal score so low-confidence rows rank lower
# without a hard cutoff. final *= FLOOR + (1 - FLOOR) * confidence.
# NULL confidence → treated as 1.0 (no regression for legacy rows).
CONFIDENCE_FLOOR = 0.5
LINK_SIM_THRESHOLD = 0.60
# Phase 2b: classifier replaces the bare similarity gate. We still keep a
# threshold, but it now decides *when to ask the classifier*, not whether to
# fire supersession. The classifier's decision (with confidence) determines
# the actual ADD/UPDATE/DELETE/NOOP outcome.
SUPERSEDE_SIM_THRESHOLD = 0.85  # legacy heuristic — kept for fallback when classifier unavailable
CLASSIFIER_TRIGGER_SIM = (
    0.70  # invoke classifier above this similarity (voyage-3-lite paraphrases sit ~0.73)
)
CLASSIFIER_APPLY_THRESHOLD = 0.70  # auto-apply UPDATE/DELETE above this confidence; else queue
CONSOLIDATION_SIM_THRESHOLD = 0.80
CONSOLIDATION_COUNT = 3
MAX_AUTO_LINKS = 5
MAX_CLASSIFIER_NEIGHBORS = 5


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
                    "owner_focus": {
                        "type": "string",
                        "description": "What the owner is working on",
                    },
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
                    "source_provenance": {
                        "type": "string",
                        "description": (
                            "Where this memory came from. Required as of Phase 2c — "
                            "JTMS attribution, we can't revise what we can't attribute. "
                            "Use a namespaced form: 'session:<id>', 'skill:<name>', "
                            "'hook:<name>', 'user:explicit', 'episode:<episode_id>' "
                            "(Phase 4), or a URL/tool-name when external."
                        ),
                    },
                },
                "required": ["type", "name", "content", "source_provenance"],
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
                    "show_history": {
                        "type": "boolean",
                        "description": (
                            "Include superseded/expired memories. Default false "
                            "(live memory only). Set true for audit/debug to see "
                            "what beliefs were once held."
                        ),
                        "default": False,
                    },
                    "brief": {
                        "type": "boolean",
                        "description": (
                            "When true, omit full content — return only name, "
                            "type, project, tags, description, and score. Use to "
                            "preview what's relevant before committing prompt "
                            "budget; call memory_get for full content on hits."
                        ),
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
        Tool(
            name="memory_calibration_summary",
            description=(
                "Confidence calibration summary: Brier score of predicted vs actual outcomes, "
                "bucketed by memory type. Reveals systemic over- or under-confidence. "
                "Used by /reflect and /self-improve (#251)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "project": {
                        "type": ["string", "null"],
                        "description": "Optional project filter. null/omitted = global.",
                    },
                },
            },
        ),
        Tool(
            name="record_decision",
            description=(
                "Record a decision made by the agent as a 'decision_made' episode. "
                "Captures decision text, rationale, memory/outcome IDs that informed it, "
                "predicted confidence (0.0-1.0), alternatives, and reversibility. "
                "Feeds the reasoning-trace for later /reflect analysis (#252)."
            ),
            inputSchema={
                "type": "object",
                "required": ["decision", "rationale", "reversibility"],
                "properties": {
                    "decision": {
                        "type": "string",
                        "description": "Short statement of what was decided.",
                    },
                    "rationale": {
                        "type": "string",
                        "description": "One-paragraph why — the basis for the choice.",
                    },
                    "memories_used": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Memory IDs that informed this decision (from recall).",
                    },
                    "outcomes_referenced": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "task_outcomes IDs that informed this decision.",
                    },
                    "confidence": {
                        "type": "number",
                        "minimum": 0.0,
                        "maximum": 1.0,
                        "description": "Predicted confidence the decision is correct (0.0-1.0).",
                    },
                    "alternatives_considered": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Options rejected and briefly why.",
                    },
                    "reversibility": {
                        "type": "string",
                        "enum": ["reversible", "hard", "irreversible"],
                        "description": "How easily this decision can be undone.",
                    },
                    "actor": {
                        "type": ["string", "null"],
                        "description": "Source of the decision (e.g. 'skill:delegate', 'session:<id>'). Defaults to 'skill:unknown'.",
                    },
                    "project": {
                        "type": ["string", "null"],
                        "description": "Optional project scope for the decision payload.",
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
                    "service": {
                        "type": "string",
                        "description": "Service name (e.g. 'Supabase', 'GitHub')",
                    },
                    "env_var": {
                        "type": "string",
                        "description": "Env variable NAME, not value (e.g. 'SUPABASE_KEY')",
                    },
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
        elif name == "record_decision":
            return await _handle_record_decision(arguments)
        elif name == "outcome_update":
            return await _handle_outcome_update(arguments)
        elif name == "outcome_list":
            return _big_result(await _handle_outcome_list(arguments))
        elif name == "memory_calibration_summary":
            return _big_result(await _handle_memory_calibration_summary(arguments))
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
    "slug",
    "title",
    "project",
    "direction",
    "priority",
    "status",
    "why",
    "success_criteria",
    "deadline",
    "progress",
    "progress_pct",
    "risks",
    "owner_focus",
    "jarvis_focus",
    "parent_id",
    "outcome",
    "lessons",
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
    return [
        TextContent(
            type="text",
            text=f"# Goals ({len(result.data)})\n\n" + "\n\n---\n\n".join(formatted),
        )
    ]


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
    source_provenance = args.get("source_provenance")

    if mem_type not in VALID_TYPES:
        return [
            TextContent(type="text", text=f"Invalid type: {mem_type}. Must be one of {VALID_TYPES}")
        ]

    # Phase 2c: provenance required. Reject at the MCP boundary so callers get
    # a readable error instead of a NOT NULL violation from Postgres. Strip
    # whitespace so an accidental " " doesn't pass the guard.
    source_provenance = (source_provenance or "").strip()
    if not source_provenance:
        return [
            TextContent(
                type="text",
                text=(
                    "Error: source_provenance is required (Phase 2c). "
                    "Use a namespaced source like 'session:<id>', 'skill:<name>', "
                    "'hook:<name>', 'user:explicit', or 'episode:<id>'. This is the "
                    "JTMS attribution for this memory — without it, future revisions "
                    "can't be traced."
                ),
            )
        ]

    # Phase 2a: canonical-form embedding — include name + tags + description + content.
    # Name and tags carry high-signal lexical cues that raw content often dilutes
    # (long narrative memories where the key topic is only in the name).
    embed_text = _canonical_embed_text(mem_name, description, tags, content)
    # #242: may populate embedding + embedding_v2 in one shot when SECONDARY set.
    embed_fields = await _compute_write_embeddings(embed_text)

    data = {
        "type": mem_type,
        "name": mem_name,
        "content": content,
        "description": description,
        "project": project,
        "tags": tags,
        "source_provenance": source_provenance,  # Phase 2c: always present, validated above
        "deleted_at": None,  # clear soft-delete on store/upsert
    }
    data.update(embed_fields)

    # Preserve the old "derive embedding column presence" cue for the user
    # message — we care whether PRIMARY landed.
    embedding = data.get(_model_slot(EMBEDDING_MODEL_PRIMARY)["embedding_column"])
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

    _audit_log(
        client, "memory_store", action, mem_name, {"project": project or "global", "type": mem_type}
    )

    # -- Memory 2.0: auto-linking + consolidation hints --
    if embedding is not None and stored_id:
        try:
            similar = client.rpc(
                "find_similar_memories",
                {
                    "query_embedding": embedding,
                    "exclude_id": stored_id,
                    "match_limit": MAX_AUTO_LINKS + 5,
                    "similarity_threshold": LINK_SIM_THRESHOLD,
                    "filter_type": None,
                },
            ).execute()
            similar_rows = similar.data or []

            # Consolidation hint: 3+ memories above 0.80 similarity
            consolidation_candidates = [
                r for r in similar_rows if r.get("similarity", 0) >= CONSOLIDATION_SIM_THRESHOLD
            ]
            if len(consolidation_candidates) >= CONSOLIDATION_COUNT:
                names = [r["name"] for r in consolidation_candidates[:5]]
                msg += f"\n\n⚠ Consolidation hint: {len(consolidation_candidates)} similar memories found: {', '.join(names)}"

            # Fire-and-forget: classify (Phase 2b) + create links.
            # We pass the candidate so the classifier has full context;
            # _create_auto_links falls back to the legacy heuristic if the
            # classifier is unavailable.
            if similar_rows:
                candidate_for_classifier = {
                    "name": mem_name,
                    "type": mem_type,
                    "description": description,
                    "content": content,
                    "tags": tags,
                }
                asyncio.create_task(
                    _create_auto_links(
                        client,
                        stored_id,
                        similar_rows,
                        mem_type,
                        candidate=candidate_for_classifier,
                    )
                )

            # Phase 5: resolve gaps
            try:
                open_gaps = (
                    client.table("known_unknowns")
                    .select("id, query_embedding")
                    .eq("status", "open")
                    .limit(100)
                    .execute()
                )
                for gap in open_gaps.data or []:
                    gap_emb = _parse_pgvector(gap.get("query_embedding"))
                    if gap_emb and embedding and _cosine_sim(embedding, gap_emb) > 0.7:
                        client.table("known_unknowns").update(
                            {
                                "status": "resolved",
                                "resolved_at": datetime.now(timezone.utc).isoformat(),
                                "resolved_by_memory_id": stored_id,
                            }
                        ).eq("id", gap["id"]).execute()
            except Exception:
                pass
        except Exception:
            pass  # auto-linking is best-effort, never blocks store

        # Resolve known unknowns: if stored memory matches any open unknown > 0.7 similarity,
        # mark as resolved (fire-and-forget, best-effort)
        asyncio.create_task(_resolve_known_unknowns(client, embedding, stored_id))

    return [TextContent(type="text", text=msg)]


SIMILARITY_THRESHOLD = 0.25  # minimum cosine similarity to include in results

GAP_THRESHOLD = 0.45  # known-unknowns: log gaps when top_similarity < this
GAP_DEDUP_SIM = 0.9


def _parse_pgvector(v: list[float] | str | None) -> list[float] | None:
    """Normalize a pgvector value returned by supabase-py.

    PostgREST returns vector columns as JSON-encoded strings
    (e.g. ``"[0.1,0.2,...]"``), not Python lists. Callers that pass the raw
    value into `_cosine_sim` hit the len-mismatch guard and silently score 0.
    Return a float list, or None if the value is missing / unparseable.
    """
    if v is None:
        return None
    if isinstance(v, list):
        return v
    if isinstance(v, str):
        try:
            parsed = json.loads(v)
        except (ValueError, TypeError):
            return None
        return parsed if isinstance(parsed, list) else None
    return None


def _cosine_sim(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _upsert_known_unknown(
    client,
    query_text: str,
    query_embedding: list[float] | None,
    top_similarity: float,
    top_memory_id: str | None,
    project: str | None,
    skill: str | None,
) -> None:
    """Upsert gap into known_unknowns table. Best-effort, never breaks recall."""
    try:
        if not query_embedding:
            existing = (
                client.table("known_unknowns")
                .select("id, hit_count")
                .eq("query", query_text)
                .eq("status", "open")
                .limit(1)
                .execute()
            )
            if existing.data:
                row = existing.data[0]
                client.table("known_unknowns").update(
                    {
                        "hit_count": row["hit_count"] + 1,
                        "last_seen_at": datetime.now(timezone.utc).isoformat(),
                        "top_similarity": top_similarity,
                        "top_memory_id": top_memory_id,
                    }
                ).eq("id", row["id"]).execute()
            else:
                client.table("known_unknowns").insert(
                    {
                        "query": query_text,
                        "top_similarity": top_similarity,
                        "top_memory_id": top_memory_id,
                        "context": json.dumps(
                            {"source": "recall", "project": project, "skill": skill}
                        ),
                    }
                ).execute()
            return

        open_gaps = (
            client.table("known_unknowns")
            .select("id, query_embedding, hit_count")
            .eq("status", "open")
            .limit(100)
            .execute()
        )
        best_match = None
        best_sim = GAP_DEDUP_SIM
        for gap in open_gaps.data or []:
            gap_emb = _parse_pgvector(gap.get("query_embedding"))
            if gap_emb:
                sim = _cosine_sim(query_embedding, gap_emb)
                if sim > best_sim:
                    best_sim = sim
                    best_match = gap

        if best_match:
            client.table("known_unknowns").update(
                {
                    "hit_count": best_match["hit_count"] + 1,
                    "last_seen_at": datetime.now(timezone.utc).isoformat(),
                    "top_similarity": max(top_similarity, best_match.get("top_similarity", 0)),
                    "top_memory_id": top_memory_id,
                }
            ).eq("id", best_match["id"]).execute()
        else:
            client.table("known_unknowns").insert(
                {
                    "query": query_text,
                    "query_embedding": query_embedding,
                    "top_similarity": top_similarity,
                    "top_memory_id": top_memory_id,
                    "context": json.dumps({"source": "recall", "project": project, "skill": skill}),
                }
            ).execute()
    except Exception:
        pass


async def _handle_recall(args: dict) -> list[TextContent]:
    client = _get_client()

    query_text = args.get("query", "")
    project = args.get("project")
    if project == "global":
        project = None
    mem_type = args.get("type")
    limit = args.get("limit", 10)

    include_links = args.get("include_links", False)
    show_history = args.get("show_history", False)
    brief = args.get("brief", False)

    # Hybrid search: combine semantic + keyword results via RRF + temporal scoring
    if query_text:
        query_embedding = await _embed_query(query_text)
        if query_embedding is not None:
            rows, results = await _hybrid_recall(
                client,
                query_embedding,
                query_text,
                project,
                mem_type,
                limit,
                include_links,
                show_history,
                brief,
            )
            # Track reads (fire-and-forget)
            ids = [r["id"] for r in rows if r.get("id")]
            if ids:
                asyncio.create_task(_touch_memories(client, ids))
            return results

    # Fallback: keyword-only search
    results = await _keyword_recall(client, query_text, project, mem_type, limit, brief)

    # Lazily backfill embeddings for records missing them (fire-and-forget)
    if os.environ.get("VOYAGE_API_KEY"):
        asyncio.create_task(_backfill_missing_embeddings(client, project))

    return results


async def _hybrid_recall(
    client,
    query_embedding: list[float],
    query_text: str,
    project,
    mem_type,
    limit: int,
    include_links: bool = False,
    show_history: bool = False,
    brief: bool = False,
) -> tuple[list[dict], list[TextContent]]:
    """Hybrid search: server-side pgvector semantic + pg_trgm keyword, merged via RRF.

    Memory 2.0: adds temporal scoring (recency × access frequency) and optional
    1-hop link expansion for graph-aware recall.

    Phase 1: default filters out superseded/expired/valid_to-past memories via
    the RPC's show_history=false path. Pass show_history=true to bypass.
    """
    try:
        # Fetch double the limit from each source to give RRF good candidates
        fetch_limit = limit * 2

        # Server-side semantic search via pgvector HNSW. #242: the RPC name
        # is selected by PRIMARY model so v1 and v2 columns each use their
        # own HNSW index. query_embedding's dim was already matched to
        # PRIMARY by _embed_query.
        sem_rpc = _model_slot(EMBEDDING_MODEL_PRIMARY)["rpc"]
        sem_result = client.rpc(
            sem_rpc,
            {
                "query_embedding": query_embedding,
                "match_limit": fetch_limit,
                "similarity_threshold": SIMILARITY_THRESHOLD,
                "filter_project": project,
                "filter_type": mem_type,
                "show_history": show_history,
            },
        ).execute()
        semantic_rows = sem_result.data or []

        # Server-side keyword search via pg_trgm
        kw_result = client.rpc(
            "keyword_search_memories",
            {
                "search_query": query_text,
                "match_limit": fetch_limit,
                "filter_project": project,
                "filter_type": mem_type,
                "show_history": show_history,
            },
        ).execute()
        keyword_rows = kw_result.data or []

        # Reciprocal Rank Fusion (k=60) + temporal scoring
        merged = _rrf_merge(semantic_rows, keyword_rows, limit)

        if not merged:
            return [], await _keyword_recall(
                client, query_text, project, mem_type, limit, brief
            )

        # Phase 1 polish (#240): match_memories RPC doesn't project confidence.
        # Enrich merged rows before scoring so entrenchment multiplier has data.
        _enrich_with_confidence(client, merged)
        _apply_temporal_scoring(merged)

        # Phase 5: gap detection — fire-and-forget so we don't add Supabase
        # round-trips to the recall hot path on low-match queries.
        top_sim = merged[0].get("similarity", 0.0) if merged else 0.0
        top_mem_id = merged[0].get("id") if merged else None
        if not show_history and top_sim < GAP_THRESHOLD:
            asyncio.create_task(
                asyncio.to_thread(
                    _upsert_known_unknown,
                    client,
                    query_text,
                    query_embedding,
                    top_sim,
                    top_mem_id,
                    project,
                    "recall",
                )
            )

        formatted = _format_memories(merged, brief=brief)
        search_type = "hybrid+temporal" if keyword_rows else "semantic+temporal"
        mode_tag = ", brief" if brief else ""
        text = (
            f"Found {len(merged)} memories ({search_type} search{mode_tag}):\n\n"
            + ("\n".join(formatted) if brief else "\n---\n".join(formatted))
        )

        # Track known unknowns: if top similarity < 0.45, log as a potential gap
        # (best-effort, non-blocking)
        if not show_history and merged:
            top_sim = merged[0].get("similarity", 0.0)
            if top_sim < 0.45:
                top_mem_id = merged[0].get("id")
                asyncio.create_task(_upsert_known_unknown(
                    client, query_text, query_embedding, top_sim, top_mem_id, context={"project": project}
                ))

        # Optional: expand with 1-hop linked memories
        if include_links:
            ids = [r["id"] for r in merged if r.get("id")]
            if ids:
                linked = await _expand_with_links(client, ids, show_history=show_history)
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
                        link_formatted = _format_memories(
                            unique_linked, link_info=True, brief=brief
                        )
                        text += (
                            f"\n\n### Linked memories ({len(unique_linked)}):\n\n"
                            + ("\n".join(link_formatted) if brief else "\n---\n".join(link_formatted))
                        )

        # Phase 5 metacognition: emit memory_recall event for FOK batch processing (#250).
        returned_ids = [r.get("id") for r in merged if r.get("id")]
        # Per-memory similarities (same length + order as returned_ids) so the
        # FOK judge can show true ranking instead of pinning every memory to
        # top_sim.
        returned_similarities = [
            float(r["similarity"]) if isinstance(r.get("similarity"), (int, float)) else None
            for r in merged
            if r.get("id")
        ]
        top_sim = merged[0].get("similarity", 0.0) if merged else 0.0
        payload = {
            "query": query_text,
            "returned_ids": returned_ids,
            "returned_similarities": returned_similarities,
            "returned_count": len(merged),
            "top_sim": float(top_sim),
            "threshold": SIMILARITY_THRESHOLD,
            "project": project,
            "type_filter": mem_type,
            "show_history": show_history,
        }
        asyncio.create_task(_emit_recall_event(client, payload))

        return merged, [TextContent(type="text", text=text)]

    except asyncio.CancelledError:
        raise
    except Exception:
        # RPC not available (e.g. migration not applied) — fall back to keyword
        return [], await _keyword_recall(
            client, query_text, project, mem_type, limit, brief
        )


def _rrf_merge(
    semantic_rows: list[dict], keyword_rows: list[dict], limit: int, k: int = 60
) -> list[dict]:
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


async def _keyword_recall(
    client, query_text: str, project, mem_type, limit: int, brief: bool = False
) -> list[TextContent]:
    """ILIKE keyword search (fallback when semantic unavailable).

    In brief mode we skip the `content` column — it's never rendered and
    would bloat the fallback payload, which is hit precisely when the fast
    path failed and we're already on a slower code path.

    Lifecycle filters mirror the show_history=false branch of
    match_memories / keyword_search_memories: exclude soft-deleted,
    expired, superseded, and past-valid_to rows (#284).

    valid_to is filtered client-side (not via .or_()) because PostgREST
    accepts only one `or=` parameter per query, and this path already uses
    .or_() for project scoping and for the keyword ILIKE clauses — adding
    a third would silently overwrite one of them. Same pattern as
    scripts/session-context.py _load_recent_recall_results.
    """
    cols = (
        "name, type, project, description, tags, updated_at, valid_to"
        if brief
        else "name, type, project, description, content, tags, updated_at, valid_to"
    )
    q = (
        client.table("memories")
        .select(cols)
        .is_("deleted_at", "null")
        .is_("expired_at", "null")
        .is_("superseded_by", "null")
    )

    if project is not None:
        q = q.or_(f"project.eq.{project},project.is.null")
    if mem_type:
        q = q.eq("type", mem_type)

    if query_text:
        terms = query_text.split()
        clauses = ",".join(
            f"name.ilike.%{t}%,description.ilike.%{t}%,content.ilike.%{t}%" for t in terms
        )
        q = q.or_(clauses)

    # Fetch extra rows so the client-side valid_to filter still leaves `limit`
    # live rows in the worst case. 2x is a simple heuristic; tombstoned
    # valid_to rows are rare in practice.
    result = q.limit(limit * 2).order("updated_at", desc=True).execute()

    now_utc = datetime.now(timezone.utc)
    live: list[dict] = []
    for row in result.data or []:
        vt = row.get("valid_to")
        if vt is not None:
            try:
                vt_dt = datetime.fromisoformat(vt.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                vt_dt = None
            if vt_dt is not None and vt_dt <= now_utc:
                continue
        live.append(row)
        if len(live) >= limit:
            break

    if not live:
        return [TextContent(type="text", text="No memories found.")]

    formatted = _format_memories(live, brief=brief)
    mode_tag = ", brief" if brief else ""
    return [
        TextContent(
            type="text",
            text=f"Found {len(live)} memories (keyword search{mode_tag}):\n\n"
            + ("\n".join(formatted) if brief else "\n---\n".join(formatted)),
        )
    ]


async def _touch_memories(client, ids: list[str]) -> None:
    """Fire-and-forget: update last_accessed_at for accessed memories via RPC."""
    try:
        client.rpc("touch_memories", {"memory_ids": ids}).execute()
    except Exception:
        pass


async def _emit_recall_event(client, payload: dict) -> None:
    """Fire-and-forget: emit memory_recall event for FOK batch processing (#250)."""
    try:
        client.table("events").insert(
            {
                "event_type": "memory_recall",
                "severity": "info",
                "repo": "Osasuwu/jarvis",
                "source": "mcp_memory",
                "title": f"Memory recall: {payload.get('query', '')[:60]}",
                "payload": payload,
            }
        ).execute()
    except Exception:
        pass


def _format_memories(
    memories: list[dict], link_info: bool = False, brief: bool = False
) -> list[str]:
    """Format memory rows for display.

    brief=False (default): full markdown block with header + description +
    updated_at + content. Suited to a Jarvis-driven targeted recall where the
    whole memory needs to land in the prompt.

    brief=True: single-line `- name [type/project] (score): description`.
    Suited to bulk/auto injection (UserPromptSubmit hook) where the agent
    should preview what's relevant and pull full content via memory_get on
    hits it actually wants. Content-free, so it can't rot long answers.
    """
    formatted = []
    for mem in memories:
        tags_str = f" [{', '.join(mem.get('tags', []))}]" if mem.get("tags") else ""
        link_str = ""
        if link_info and mem.get("link_type"):
            link_str = f" ← {mem['link_type']}"
            if mem.get("link_strength"):
                link_str += f" ({mem['link_strength']:.2f})"
        proj = mem.get("project") or "global"
        if brief:
            # `_temporal_score` (set by _apply_temporal_scoring) is the actual
            # sort key after rrf × recency × access × entrenchment. Show it
            # first so the displayed value matches the displayed order.
            # Retrieval provenance (rrf/sim/rank) follows as secondary signal
            # — useful for debugging why a row surfaced at all.
            temporal = mem.get("_temporal_score")
            rrf = mem.get("_rrf_score")
            sim = mem.get("similarity")
            rank = mem.get("rank")
            base_parts = []
            if rrf is not None:
                base_parts.append(f"rrf {rrf:.3f}")
            elif isinstance(sim, (int, float)):
                base_parts.append(f"sim {sim:.2f}")
            elif isinstance(rank, (int, float)):
                base_parts.append(f"rank {rank:.2f}")
            if isinstance(temporal, (int, float)):
                lead = f"score {temporal:.3f}"
                score_str = f" ({lead}; {base_parts[0]})" if base_parts else f" ({lead})"
            elif base_parts:
                score_str = f" ({base_parts[0]})"
            else:
                score_str = ""
            desc = (mem.get("description") or "").strip()
            formatted.append(
                f"- {mem['name']} [{mem['type']}/{proj}]{tags_str}{score_str}{link_str}: {desc}"
            )
        else:
            formatted.append(
                f"## {mem['name']} ({mem['type']}, {proj}){tags_str}{link_str}\n"
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
        # #242: backfill the column that matches PRIMARY — if we've cut over
        # to v2, the "missing embedding" we care about is embedding_v2.
        primary_col = _model_slot(EMBEDDING_MODEL_PRIMARY)["embedding_column"]
        q = client.table("memories").select("id, name, description, tags, content")
        q = q.is_(primary_col, "null").is_("deleted_at", "null")
        if project is not None:
            q = q.or_(f"project.eq.{project},project.is.null")
        rows = q.execute().data
        if not rows:
            return

        # Phase 2a: canonical form (name + tags + description + content)
        texts = [
            _canonical_embed_text(
                r.get("name", ""), r.get("description", ""), r.get("tags") or [], r["content"]
            )
            for r in rows
        ]
        # #242: this path only backfills the column for PRIMARY — the legacy
        # "missing embedding" cleanup. v2 corpus-wide backfill is a separate
        # issue per #242 non-goals.
        embeddings = await _embed_batch(texts, model=EMBEDDING_MODEL_PRIMARY)
        if embeddings is None:
            return

        for mem, embedding in zip(rows, embeddings):
            client.table("memories").update(
                _embed_upsert_fields(embedding, EMBEDDING_MODEL_PRIMARY)
            ).eq("id", mem["id"]).execute()
    except Exception:
        pass  # fire-and-forget: silently swallow all errors so caller never fails


async def _create_auto_links(
    client,
    stored_id: str,
    similar_rows: list[dict],
    mem_type: str,
    candidate: dict | None = None,
) -> None:
    """Fire-and-forget: create links + apply Phase 2b classifier decision.

    Pipeline:
      1. Always create `related` links to every neighbor (graph signal).
      2. For neighbors above CLASSIFIER_TRIGGER_SIM, ask the Haiku
         classifier to choose ADD / UPDATE / DELETE / NOOP.
      3. confidence >= CLASSIFIER_APPLY_THRESHOLD → apply the decision
         immediately (UPDATE: target.superseded_by = stored_id;
         DELETE: target.expired_at = now()). Record as auto_applied
         in memory_review_queue for audit.
      4. confidence < threshold → record in queue with status=pending,
         do NOT mutate the target. Owner reviews later.
      5. classifier unavailable (no API key, network fail, no candidate
         metadata) → fall back to the legacy SUPERSEDE_SIM_THRESHOLD
         heuristic so we never regress to "do nothing".
    """
    try:
        # --- (1) base links: everything is `related` until a classifier upgrade ---
        links = []
        for row in similar_rows[:MAX_AUTO_LINKS]:
            links.append(
                {
                    "source_id": stored_id,
                    "target_id": row["id"],
                    "link_type": "related",
                    "strength": round(row.get("similarity", 0), 3),
                }
            )
        if links:
            client.table("memory_links").upsert(
                links, on_conflict="source_id,target_id,link_type"
            ).execute()

        # --- (2) classifier or fallback heuristic ---
        # Pick the high-similarity slice we'd consider for supersession.
        candidates_for_classifier = [
            r
            for r in similar_rows[:MAX_CLASSIFIER_NEIGHBORS]
            if r.get("similarity", 0) >= CLASSIFIER_TRIGGER_SIM
        ]
        if not candidates_for_classifier:
            return  # nothing close enough — pure ADD, no supersession to consider

        decision = None
        if candidate is not None and classify_write is not None:
            # Hydrate neighbors with description/content for richer prompting.
            # find_similar_memories only returns id/name/type/similarity.
            hydrated = await _hydrate_neighbors(client, candidates_for_classifier)
            try:
                decision = await classify_write(candidate, hydrated)
            except Exception:
                decision = None

        if decision is not None:
            await _apply_classifier_decision(client, stored_id, decision, candidates_for_classifier)
        else:
            # Legacy heuristic fallback: same-type + sim >= 0.85 → supersede.
            await _apply_legacy_supersede(client, stored_id, candidates_for_classifier, mem_type)
    except Exception:
        pass


async def _hydrate_neighbors(client, rows: list[dict]) -> list[dict]:
    """Fetch description+content for the neighbor rows so the classifier
    prompt has real context, not just names."""
    ids = [r["id"] for r in rows if r.get("id")]
    if not ids:
        return rows
    try:
        full = (
            client.table("memories")
            .select("id, name, type, description, content, tags")
            .in_("id", ids)
            .execute()
        )
        full_by_id = {row["id"]: row for row in (full.data or [])}
    except Exception:
        return rows

    hydrated = []
    for r in rows:
        extra = full_by_id.get(r.get("id"), {})
        hydrated.append(
            {
                "id": r.get("id"),
                "name": r.get("name") or extra.get("name", ""),
                "type": r.get("type") or extra.get("type", ""),
                "similarity": r.get("similarity", 0),
                "description": extra.get("description", ""),
                "content": extra.get("content", ""),
                "tags": extra.get("tags", []) or [],
            }
        )
    return hydrated


async def _apply_classifier_decision(
    client,
    stored_id: str,
    decision,  # ClassifierDecision
    neighbors: list[dict],
) -> None:
    """Apply the classifier's ADD/UPDATE/DELETE/NOOP decision and record
    it in memory_review_queue (auto_applied if high confidence, pending if
    we want a human in the loop).

    The candidate is *already* persisted by the time we get here — that's
    intentional, we never lose data. UPDATE/DELETE only mutate the target.
    """
    apply_now = decision.confidence >= CLASSIFIER_APPLY_THRESHOLD

    target_id = decision.target_id
    if decision.decision in ("UPDATE", "DELETE") and target_id:
        # Sanity check: target_id must be one of the neighbors we showed it.
        # Otherwise the model hallucinated an id — refuse to mutate.
        valid_ids = {n.get("id") for n in neighbors}
        if target_id not in valid_ids:
            target_id = None
            apply_now = False

    if decision.decision == "ADD":
        # ADD just confirms the upsert we already did. No queue entry needed
        # unless the classifier had low confidence (then we want a record).
        if decision.confidence >= CLASSIFIER_APPLY_THRESHOLD:
            return
        queue_status = "pending"
        applied_at = None
    elif apply_now and target_id and decision.decision == "UPDATE":
        # Try to mutate; only mark auto_applied if the row was actually changed.
        # rowcount==0 happens when the target was already superseded by someone
        # else — a real race we want to flag for review, not silently overwrite.
        mutated = False
        try:
            res = (
                client.table("memories")
                .update({"superseded_by": stored_id})
                .eq("id", target_id)
                .is_("superseded_by", "null")
                .execute()
            )
            mutated = bool(getattr(res, "data", None))
        except Exception:
            mutated = False
        if mutated:
            # Upgrade the auto-created `related` link to `supersedes` so the
            # graph reflects the supersession (matches legacy fallback behavior).
            try:
                client.table("memory_links").upsert(
                    {
                        "source_id": stored_id,
                        "target_id": target_id,
                        "link_type": "supersedes",
                        "strength": 1.0,
                    },
                    on_conflict="source_id,target_id,link_type",
                ).execute()
            except Exception:
                pass  # link upgrade is cosmetic; don't roll back the supersession
            queue_status = "auto_applied"
            applied_at = datetime.now(timezone.utc).isoformat()
        else:
            queue_status = "pending"
            applied_at = None
    elif apply_now and target_id and decision.decision == "DELETE":
        mutated = False
        try:
            res = (
                client.table("memories")
                .update(
                    {
                        "expired_at": datetime.now(timezone.utc).isoformat(),
                    }
                )
                .eq("id", target_id)
                .is_("expired_at", "null")
                .execute()
            )
            mutated = bool(getattr(res, "data", None))
        except Exception:
            mutated = False
        if mutated:
            queue_status = "auto_applied"
            applied_at = datetime.now(timezone.utc).isoformat()
        else:
            queue_status = "pending"
            applied_at = None
    elif apply_now and decision.decision == "NOOP":
        # NOOP: nothing to mutate, but the decision was applied (no-op is the
        # desired state). Record as auto_applied for audit.
        queue_status = "auto_applied"
        applied_at = datetime.now(timezone.utc).isoformat()
    else:
        # Low confidence (or UPDATE/DELETE without a valid target) — queue for review.
        queue_status = "pending"
        applied_at = None

    # Record the decision (always — auditability).
    try:
        client.table("memory_review_queue").insert(
            {
                "candidate_id": stored_id,
                "decision": decision.decision,
                "target_id": target_id,
                "confidence": round(decision.confidence, 3),
                "reasoning": decision.reasoning,
                "classifier_model": CLASSIFIER_MODEL,
                "neighbors_seen": [
                    {
                        "id": n.get("id"),
                        "name": n.get("name"),
                        "similarity": round(n.get("similarity", 0), 3),
                    }
                    for n in neighbors
                ],
                "status": queue_status,
                "applied_at": applied_at,
            }
        ).execute()
    except Exception:
        pass


async def _apply_legacy_supersede(
    client, stored_id: str, similar_rows: list[dict], mem_type: str
) -> None:
    """Fallback used when the classifier is unavailable. Same logic as
    pre-Phase-2b: same-type + similarity >= SUPERSEDE_SIM_THRESHOLD →
    mark target.superseded_by = stored_id."""
    supersede_target_ids = [
        r["id"]
        for r in similar_rows
        if r.get("type") == mem_type
        and r.get("similarity", 0) >= SUPERSEDE_SIM_THRESHOLD
        and r.get("id")
    ]
    if not supersede_target_ids:
        return
    try:
        client.table("memories").update({"superseded_by": stored_id}).in_(
            "id", supersede_target_ids
        ).is_("superseded_by", "null").execute()
        # Also upgrade the link type from `related` to `supersedes`.
        for tid in supersede_target_ids:
            client.table("memory_links").upsert(
                {
                    "source_id": stored_id,
                    "target_id": tid,
                    "link_type": "supersedes",
                    "strength": 1.0,
                },
                on_conflict="source_id,target_id,link_type",
            ).execute()
    except Exception:
        pass


async def _expand_with_links(
    client,
    memory_ids: list[str],
    show_history: bool = False,
) -> list[dict]:
    """Fetch 1-hop linked memories via graph traversal RPC.

    show_history mirrors the primary recall flag: when true, skip the
    lifecycle filter so history views don't drop linked neighbors.
    """
    try:
        result = client.rpc(
            "get_linked_memories",
            {
                "memory_ids": memory_ids,
                "link_types": None,
                "show_history": show_history,
            },
        ).execute()
        return result.data or []
    except Exception:
        return []


def _enrich_with_confidence(client, rows: list[dict]) -> None:
    """Backfill `confidence` on rows that came from match_memories (which doesn't
    project it). Batched SELECT keeps this cheap. Best-effort: on error we leave
    rows untouched and scoring falls back to the NULL→1.0 branch.

    Phase 1 polish (#240).
    """
    ids = [r["id"] for r in rows if r.get("id") and "confidence" not in r]
    if not ids:
        return
    try:
        result = client.table("memories").select("id, confidence").in_("id", ids).execute()
    except Exception:
        return
    conf_map = {r["id"]: r.get("confidence") for r in (result.data or [])}
    for row in rows:
        rid = row.get("id")
        if rid in conf_map and "confidence" not in row:
            row["confidence"] = conf_map[rid]


def _apply_temporal_scoring(rows: list[dict]) -> list[dict]:
    """Re-rank rows by combining RRF score with temporal decay and access frequency."""
    now = datetime.now(timezone.utc)
    for row in rows:
        rrf = row.get("_rrf_score", 0.01)
        mem_type = row.get("type", "decision")
        half_life = TEMPORAL_HALF_LIVES.get(mem_type, DEFAULT_HALF_LIFE)

        # Parse content_updated_at (Phase 1: decay is driven by content edits,
        # not any write — touch_memories bumps updated_at on every recall).
        # Fall back to updated_at for rows backfilled before Phase 0.
        updated_str = row.get("content_updated_at") or row.get("updated_at", "")
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

        # Entrenchment multiplier (Phase 1 polish #240). NULL confidence treated
        # as 1.0 so legacy rows don't regress; FLOOR ensures confidence=0 only
        # halves the score rather than zeroing it.
        confidence_raw = row.get("confidence")
        if confidence_raw is None:
            conf = 1.0
        else:
            try:
                conf = float(confidence_raw)
            except (TypeError, ValueError):
                conf = 1.0
        conf = max(0.0, min(1.0, conf))
        entrenchment = CONFIDENCE_FLOOR + (1.0 - CONFIDENCE_FLOOR) * conf

        row["_temporal_score"] = rrf * recency * access * entrenchment

    rows.sort(key=lambda r: r.get("_temporal_score", 0), reverse=True)
    return rows


def _cosine_sim(v1: list[float] | None, v2: list[float] | None) -> float:
    """Cosine similarity between two embedding vectors. Returns 0.0 if either
    is None/empty or if lengths differ (dim mismatch would otherwise silently
    truncate via zip — important during embedding-model migrations)."""
    if v1 is None or v2 is None or len(v1) == 0 or len(v2) == 0:
        return 0.0
    if len(v1) != len(v2):
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2))
    mag1 = math.sqrt(sum(a * a for a in v1))
    mag2 = math.sqrt(sum(b * b for b in v2))
    if mag1 == 0 or mag2 == 0:
        return 0.0
    return dot / (mag1 * mag2)


async def _upsert_known_unknown(
    client, query: str, query_embedding: list[float] | None,
    top_similarity: float, top_memory_id: str | None, context: dict | None = None
) -> None:
    """Insert or update a known unknown, with semantic dedup.

    Semantic dedup: if an open known_unknown exists with cosine sim > 0.9
    on query_embedding, increment hit_count instead of inserting.
    Best-effort; never raises.
    """
    # Schema declares query_embedding vector(512). If PRIMARY model produces
    # a different dim (e.g. voyage-3 = 1024), store without embedding rather
    # than letting the insert fail and get swallowed by the best-effort catch.
    if query_embedding and len(query_embedding) != 512:
        query_embedding = None

    try:
        if not query_embedding:
            # Fallback: upsert without embedding — select hit_count so the
            # increment reflects the stored value (not the default).
            existing = client.table("known_unknowns").select("id, hit_count").eq("query", query).eq("status", "open").limit(1).execute()
            if existing.data:
                row = existing.data[0]
                client.table("known_unknowns").update({
                    "hit_count": row.get("hit_count", 1) + 1,
                    "last_seen_at": datetime.now(timezone.utc).isoformat(),
                }).eq("id", row["id"]).execute()
            else:
                client.table("known_unknowns").insert({
                    "query": query,
                    "query_embedding": None,
                    "top_similarity": top_similarity,
                    "top_memory_id": top_memory_id,
                    "context": context,
                }).execute()
            return

        # Semantic dedup: fetch open unknowns and check sim > 0.9.
        # Include hit_count in the select so the increment is correct.
        open_unknowns = client.table("known_unknowns").select("id, query_embedding, hit_count").eq("status", "open").execute()
        for row in open_unknowns.data or []:
            stored_embedding = _parse_pgvector(row.get("query_embedding"))
            if stored_embedding and _cosine_sim(query_embedding, stored_embedding) > 0.9:
                # Semantic match: increment hit_count
                client.table("known_unknowns").update({
                    "hit_count": row.get("hit_count", 1) + 1,
                    "last_seen_at": datetime.now(timezone.utc).isoformat(),
                }).eq("id", row["id"]).execute()
                return

        # No match: insert new row
        client.table("known_unknowns").insert({
            "query": query,
            "query_embedding": query_embedding,
            "top_similarity": top_similarity,
            "top_memory_id": top_memory_id,
            "context": context,
        }).execute()
    except Exception:
        pass  # best-effort, never block recall on failure


async def _resolve_known_unknowns(client, memory_embedding: list[float], memory_id: str) -> None:
    """Scan open known_unknowns; mark as resolved if cosine(new_embedding, query_embedding) > 0.7.

    Best-effort; never raises.
    """
    try:
        open_unknowns = client.table("known_unknowns").select("id, query_embedding").eq("status", "open").execute()
        now = datetime.now(timezone.utc).isoformat()
        for row in open_unknowns.data or []:
            stored_embedding = _parse_pgvector(row.get("query_embedding"))
            if stored_embedding and _cosine_sim(memory_embedding, stored_embedding) > 0.7:
                client.table("known_unknowns").update({
                    "status": "resolved",
                    "resolved_at": now,
                    "resolved_by_memory_id": memory_id,
                }).eq("id", row["id"]).execute()
    except Exception:
        pass  # best-effort, never block store on failure


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
        return [
            TextContent(
                type="text", text=f"Memory '{mem_name}' not found (project={project or 'global'})."
            )
        ]

    mem = result.data[0]
    tags_str = f"\nTags: {', '.join(mem.get('tags', []))}" if mem.get("tags") else ""
    return [
        TextContent(
            type="text",
            text=(
                f"## {mem['name']}\n"
                f"Type: {mem['type']} | Project: {mem.get('project') or 'global'}{tags_str}\n"
                f"Created: {mem.get('created_at')} | Updated: {mem.get('updated_at')}\n"
                f"Description: {mem.get('description', '')}\n\n"
                f"{mem['content']}"
            ),
        )
    ]


async def _handle_list(args: dict) -> list[TextContent]:
    client = _get_client()

    project = args.get("project")
    if project == "global":
        project = None
    mem_type = args.get("type")

    q = (
        client.table("memories")
        .select("name, type, project, description, updated_at")
        .is_("deleted_at", "null")
    )

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

    return [
        TextContent(
            type="text", text=f"## All Memories ({len(result.data)} total)\n" + "\n".join(lines)
        )
    ]


async def _handle_delete(args: dict) -> list[TextContent]:
    client = _get_client()

    mem_name = args["name"]
    project = args.get("project")
    if project == "global":
        project = None  # normalize "global" → NULL, same as in _handle_store

    q = (
        client.table("memories")
        .update({"deleted_at": datetime.now(timezone.utc).isoformat()})
        .eq("name", mem_name)
        .is_("deleted_at", "null")
    )
    if project is not None:
        q = q.eq("project", project)
    else:
        q = q.is_("project", "null")

    result = q.execute()

    if result.data:
        _audit_log(
            client, "memory_delete", "soft_delete", mem_name, {"project": project or "global"}
        )
        return [
            TextContent(
                type="text",
                text=f"Soft-deleted memory '{mem_name}' (project={project or 'global'}). Recoverable for 30 days via memory_restore.",
            )
        ]
    return [TextContent(type="text", text=f"Memory '{mem_name}' not found.")]


async def _handle_restore(args: dict) -> list[TextContent]:
    client = _get_client()

    mem_name = args["name"]
    project = args.get("project")
    if project == "global":
        project = None

    q = (
        client.table("memories")
        .update({"deleted_at": None})
        .eq("name", mem_name)
        .not_.is_("deleted_at", "null")
    )
    if project is not None:
        q = q.eq("project", project)
    else:
        q = q.is_("project", "null")

    result = q.execute()

    if result.data:
        _audit_log(client, "memory_restore", "restore", mem_name, {"project": project or "global"})
        return [
            TextContent(
                type="text", text=f"Restored memory '{mem_name}' (project={project or 'global'})."
            )
        ]
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
        return [
            TextContent(
                type="text", text="No memory links found. Store more memories to build the graph."
            )
        ]

    type_stats: dict[str, list[float]] = {}
    for row in link_data:
        lt = row["link_type"]
        type_stats.setdefault(lt, []).append(row["strength"])

    lines.append(f"### Link Statistics ({total} total)\n")
    lines.append("| Type | Count | Avg Strength | Min | Max |")
    lines.append("|------|-------|-------------|-----|-----|")
    for lt, strengths in sorted(type_stats.items()):
        avg = sum(strengths) / len(strengths)
        lines.append(
            f"| {lt} | {len(strengths)} | {avg:.3f} | {min(strengths):.3f} | {max(strengths):.3f} |"
        )

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
        names_result = (
            client.table("memories")
            .select("id, name, type, project")
            .in_("id", top_ids)
            .is_("deleted_at", "null")
            .execute()
        )
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
    total_with_emb = (
        client.table("memories")
        .select("id", count="exact")
        .not_.is_("embedding", "null")
        .is_("deleted_at", "null")
        .execute()
    )
    total_emb_count = total_with_emb.count or 0
    linked_ids = set(counts.keys())
    all_emb = (
        client.table("memories")
        .select("id, name, type, project")
        .not_.is_("embedding", "null")
        .is_("deleted_at", "null")
        .execute()
    )
    orphans = [r for r in (all_emb.data or []) if r["id"] not in linked_ids]

    lines.append(
        f"\n### Orphans ({len(orphans)} of {total_emb_count} embedded memories have no links)\n"
    )
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
    mem_result = (
        client.table("memories")
        .select("id, name, type, project")
        .eq("name", name)
        .is_("deleted_at", "null")
        .execute()
    )
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
        names = (
            client.table("memories")
            .select("id, name, type, project")
            .in_("id", all_ids)
            .is_("deleted_at", "null")
            .execute()
        )
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
        mems = (
            client.table("memories")
            .select("id, name, type, project")
            .in_("id", all_ids)
            .is_("deleted_at", "null")
            .execute()
        )
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
    client = _get_client()

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
        "outcome_summary",
        "goal_slug",
        "project",
        "issue_url",
        "pr_url",
        "tests_passed",
        "pr_merged",
        "quality_score",
        "lessons",
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
        "outcome_status",
        "outcome_summary",
        "pr_merged",
        "tests_passed",
        "quality_score",
        "lessons",
        "pattern_tags",
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
    client = _get_client()
    project = args.get("project")
    if project == "global":
        project = None

    try:
        result = client.rpc(
            "memory_calibration_summary", {"p_project": project}
        ).execute()
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
        return [TextContent(
            type="text",
            text=f"No calibration data yet{scope} — need outcomes with memory_id linked.",
        )]

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


# -- Credential registry handlers (Pillar 9) --------------------------------


async def _handle_credential_list(args: dict) -> list[TextContent]:
    """List registered credentials — metadata only, never secret values."""
    client = _get_client()
    query = (
        client.table("credential_registry")
        .select(
            "service, env_var, stored_in, scope, expires_at, last_rotated_at, rotation_notes, notes"
        )
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
        rotated = (
            f" | Last rotated: {c['last_rotated_at'][:10]}" if c.get("last_rotated_at") else ""
        )
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

    result = client.table("credential_registry").upsert(row, on_conflict="env_var").execute()
    if result.data:
        return [
            TextContent(
                type="text", text=f"Credential registered: {args['service']} ({args['env_var']})"
            )
        ]
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


async def _handle_record_decision(args: dict) -> list[TextContent]:
    """Insert a 'decision_made' episode with structured payload (#252).

    The episode is the agent's reasoning trace: what was decided, why,
    which memories/outcomes informed it, predicted confidence, and
    reversibility. /reflect reads these back via the episodes table to
    analyze whether the basis was sound when outcomes come in.
    """
    decision = (args.get("decision") or "").strip()
    rationale = (args.get("rationale") or "").strip()
    reversibility = args.get("reversibility")

    if not decision:
        return [TextContent(type="text", text="Error: decision is required")]
    if not rationale:
        return [TextContent(type="text", text="Error: rationale is required")]
    if reversibility not in ("reversible", "hard", "irreversible"):
        return [TextContent(
            type="text",
            text="Error: reversibility must be one of reversible|hard|irreversible",
        )]

    confidence = args.get("confidence")
    if confidence is not None:
        try:
            confidence = float(confidence)
        except (TypeError, ValueError):
            return [TextContent(type="text", text="Error: confidence must be a number")]
        if not (0.0 <= confidence <= 1.0):
            return [TextContent(type="text", text="Error: confidence must be in [0.0, 1.0]")]

    actor = args.get("actor") or "skill:unknown"

    payload = {
        "decision": decision,
        "rationale": rationale,
        "memories_used": args.get("memories_used") or [],
        "outcomes_referenced": args.get("outcomes_referenced") or [],
        "alternatives_considered": args.get("alternatives_considered") or [],
        "reversibility": reversibility,
    }
    if confidence is not None:
        payload["confidence"] = confidence
    if args.get("project"):
        payload["project"] = args["project"]

    client = _get_client()
    try:
        result = client.table("episodes").insert({
            "actor": actor,
            "kind": "decision_made",
            "payload": payload,
        }).execute()
    except Exception as exc:
        return [TextContent(type="text", text=f"Error recording decision: {exc}")]

    if result.data:
        eid = result.data[0].get("id", "?")
        return [TextContent(type="text", text=f"Decision recorded: episode {eid}")]
    return [TextContent(type="text", text="Failed to record decision.")]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
