"""Jarvis Memory MCP Server.

Provides persistent, cross-device memory for Claude Code via Supabase.
Tools: memory_store, memory_recall, memory_get, memory_list, memory_delete.

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


# -- Tool definitions -------------------------------------------------------

@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
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
            description="Delete a memory by name and project scope.",
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
        if name == "memory_store":
            return await _handle_store(arguments)
        elif name == "memory_recall":
            return _big_result(await _handle_recall(arguments))
        elif name == "memory_get":
            return _big_result(await _handle_get(arguments))
        elif name == "memory_list":
            return _big_result(await _handle_list(arguments))
        elif name == "memory_delete":
            return await _handle_delete(arguments)
        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]
    except Exception as exc:
        return [TextContent(type="text", text=f"Error: {exc}")]


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
    }

    if embedding is not None:
        data["embedding"] = embedding

    embed_note = " (with embedding)" if embedding is not None else ""

    if project is not None:
        # Atomic upsert via unique constraint on (project, name) — no race condition
        client.table("memories").upsert(data, on_conflict="project,name").execute()
        return [TextContent(type="text", text=f"Memory '{mem_name}' saved (project={project}){embed_note}")]
    else:
        # Manual upsert for NULL project: PostgreSQL unique constraint doesn't
        # deduplicate NULLs, so we handle this case explicitly.
        q = client.table("memories").select("id").eq("name", mem_name).is_("project", "null")
        existing = q.limit(1).execute()
        if existing.data:
            client.table("memories").update(data).eq("id", existing.data[0]["id"]).execute()
            return [TextContent(type="text", text=f"Memory '{mem_name}' updated (project=global){embed_note}")]
        else:
            client.table("memories").insert(data).execute()
            return [TextContent(type="text", text=f"Memory '{mem_name}' created (project=global){embed_note}")]


SIMILARITY_THRESHOLD = 0.25  # minimum cosine similarity to include in results


async def _handle_recall(args: dict) -> list[TextContent]:
    client = _get_client()

    query_text = args.get("query", "")
    project = args.get("project")
    if project == "global":
        project = None
    mem_type = args.get("type")
    limit = args.get("limit", 10)

    # Hybrid search: combine semantic + keyword results via RRF
    if query_text:
        query_embedding = await _embed_query(query_text)
        if query_embedding is not None:
            rows, results = await _hybrid_recall(client, query_embedding, query_text, project, mem_type, limit)
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
    project, mem_type, limit: int
) -> list[TextContent]:
    """Hybrid search: server-side pgvector semantic + pg_trgm keyword, merged via RRF.

    Uses Supabase RPC functions (match_memories, keyword_search_memories) to
    push all computation to the database. No embeddings fetched to client.
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

        # Reciprocal Rank Fusion (k=60)
        merged = _rrf_merge(semantic_rows, keyword_rows, limit)

        if not merged:
            return [], await _keyword_recall(client, query_text, project, mem_type, limit)

        formatted = _format_memories(merged)
        search_type = "hybrid" if keyword_rows else "semantic"
        return merged, [TextContent(type="text", text=f"Found {len(merged)} memories ({search_type} search):\n\n" + "\n---\n".join(formatted))]

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
    return [by_id[rid] for rid in ranked[:limit]]


async def _keyword_recall(client, query_text: str, project, mem_type, limit: int) -> list[TextContent]:
    """ILIKE keyword search (fallback when semantic unavailable)."""
    q = client.table("memories").select("name, type, project, description, content, tags, updated_at")

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


def _format_memories(memories: list[dict]) -> list[str]:
    formatted = []
    for mem in memories:
        tags_str = f" [{', '.join(mem.get('tags', []))}]" if mem.get("tags") else ""
        formatted.append(
            f"## {mem['name']} ({mem['type']}, {mem.get('project') or 'global'}){tags_str}\n"
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
        q = q.is_("embedding", "null")
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


async def _handle_get(args: dict) -> list[TextContent]:
    client = _get_client()

    mem_name = args["name"]
    project = args.get("project")
    if project == "global":
        project = None

    q = client.table("memories").select("*").eq("name", mem_name)
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

    q = client.table("memories").select("name, type, project, description, updated_at")

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

    q = client.table("memories").delete().eq("name", mem_name)
    if project is not None:
        q = q.eq("project", project)
    else:
        q = q.is_("project", "null")

    result = q.execute()

    if result.data:
        return [TextContent(type="text", text=f"Deleted memory '{mem_name}' (project={project or 'global'}).")]
    return [TextContent(type="text", text=f"Memory '{mem_name}' not found.")]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
