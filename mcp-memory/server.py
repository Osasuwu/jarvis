"""Jarvis Memory MCP Server.

Provides persistent, cross-device memory for Claude Code via Supabase.
Tools: memory_store, memory_recall, memory_get, memory_list, memory_delete.

Usage in .mcp.json:
{
  "memory": {
    "type": "stdio",
    "command": "python",
    "args": ["mcp-memory/server.py"],
    "env": {
      "SUPABASE_URL": "https://xxx.supabase.co",
      "SUPABASE_KEY": "eyJ..."
    }
  }
}
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

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
    return _supabase


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
                "Search memories by keyword. Returns matching memories ranked by relevance. "
                "Use at the START of a session to load relevant context, "
                "or when the user references something discussed before."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search keywords (matched against name, description, content)",
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

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        if name == "memory_store":
            return await _handle_store(arguments)
        elif name == "memory_recall":
            return await _handle_recall(arguments)
        elif name == "memory_get":
            return await _handle_get(arguments)
        elif name == "memory_list":
            return await _handle_list(arguments)
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
    tags = args.get("tags", [])

    if mem_type not in VALID_TYPES:
        return [TextContent(type="text", text=f"Invalid type: {mem_type}. Must be one of {VALID_TYPES}")]

    data = {
        "type": mem_type,
        "name": mem_name,
        "content": content,
        "description": description,
        "project": project,
        "tags": tags,
    }

    # Upsert: if (project, name) exists, update; else insert
    result = (
        client.table("memories")
        .upsert(data, on_conflict="project,name")
        .execute()
    )

    if result.data:
        action = "updated" if result.data[0].get("updated_at") != result.data[0].get("created_at") else "created"
        return [TextContent(type="text", text=f"Memory '{mem_name}' {action} (project={project or 'global'})")]

    return [TextContent(type="text", text="Memory stored.")]


async def _handle_recall(args: dict) -> list[TextContent]:
    client = _get_client()

    query_text = args.get("query", "")
    project = args.get("project")
    mem_type = args.get("type")
    limit = args.get("limit", 10)

    q = client.table("memories").select("name, type, project, description, content, tags, updated_at")

    if project is not None:
        # Include both project-specific and global memories
        q = q.or_(f"project.eq.{project},project.is.null")
    if mem_type:
        q = q.eq("type", mem_type)

    if query_text:
        # ILIKE search across name, description, content.
        # Split multi-word queries and OR all terms so "jarvis reboot" matches
        # records containing "jarvis" OR "reboot", not only the exact phrase.
        terms = query_text.split()
        clauses = ",".join(
            f"name.ilike.%{t}%,description.ilike.%{t}%,content.ilike.%{t}%"
            for t in terms
        )
        q = q.or_(clauses)

    result = q.limit(limit).order("updated_at", desc=True).execute()

    if not result.data:
        return [TextContent(type="text", text="No memories found.")]

    formatted = []
    for mem in result.data:
        tags_str = f" [{', '.join(mem.get('tags', []))}]" if mem.get("tags") else ""
        formatted.append(
            f"## {mem['name']} ({mem['type']}, {mem.get('project') or 'global'}){tags_str}\n"
            f"*{mem.get('description', '')}*\n"
            f"Updated: {mem.get('updated_at', '?')}\n\n"
            f"{mem['content']}\n"
        )

    return [TextContent(type="text", text=f"Found {len(result.data)} memories:\n\n" + "\n---\n".join(formatted))]


async def _handle_get(args: dict) -> list[TextContent]:
    client = _get_client()

    mem_name = args["name"]
    project = args.get("project")

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
    import asyncio
    asyncio.run(main())
