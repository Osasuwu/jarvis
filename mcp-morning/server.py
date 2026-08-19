"""Jarvis Morning MCP Server — morning_digest tool (#1588).

Thin wrapper around morning_gather (I/O adapter) and morning_engine (pure
function). Unlike mcp-status/server.py, no conversion layer is needed —
morning_gather.gather() already returns a MorningGatherResult that
morning_engine.analyze() consumes directly.

This module is deliberately NOT registered in .claude-userlevel/.mcp.json
yet — that registration is a separate, later slice (see #1588 body).

Usage in .mcp.json (future slice):
{
  "morning": {
    "type": "stdio",
    "command": "python",
    "args": ["mcp-morning/server.py"],
    "env": {
      "SUPABASE_URL": "https://xxx.supabase.co",
      "SUPABASE_KEY": "eyJ...",
    }
  }
}
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import traceback
from pathlib import Path

# Timeout for synchronous gather() running off the event loop.
# A hung subprocess (gh/git) should not block the MCP server indefinitely.
_GATHER_TIMEOUT = 30.0  # seconds

# Repo root must be on sys.path BEFORE the `from scripts.*` imports below.
# When launched as a script (`python mcp-morning/server.py`), sys.path[0] is
# the script's own dir (mcp-morning/), NOT the repo root — so `scripts.*`
# would not resolve. pytest masks this because it injects rootdir. Insert
# the repo root (parent of mcp-morning/) explicitly.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# NOTE: deliberately NOT aliasing this module to the global name "server".
# mcp-memory/server.py and mcp-status/server.py both need to avoid colliding
# on that name too — see mcp-status/server.py's identical note (#1017). This
# server is launched as `__main__` and nothing internally imports "server",
# so the alias serves no purpose here. Tests load it under a unique module
# name ("morning_server").

# noqa: E402 — .env loaded before MCP/script imports (follows mcp-status pattern)
from dotenv import load_dotenv  # noqa: E402

# Load .env from repo root (two levels up from mcp-morning/server.py).
#
# override=True lets .env win for SUPABASE_* (the vars this server actually
# needs), but it must NOT clobber auth tokens the harness/shell already
# injected: a stale GITHUB_TOKEN/GH_TOKEN in .env would 401 every gh call in
# gather(), silently degrading the digest to empty. Snapshot the pre-existing
# tokens and restore them after the load.
_preserved_tokens = {_k: os.environ[_k] for _k in ("GITHUB_TOKEN", "GH_TOKEN") if _k in os.environ}
_env_candidates = [
    Path(__file__).resolve().parent.parent / ".env",
    Path(__file__).resolve().parent.parent.parent / ".env",
]
for _env_path in _env_candidates:
    if _env_path.exists():
        load_dotenv(_env_path, override=True)
        break
os.environ.update(_preserved_tokens)

from mcp.server import Server, ServerRequestContext  # noqa: E402
from mcp.types import (  # noqa: E402
    CallToolRequestParams,
    CallToolResult,
    ListToolsResult,
    PaginatedRequestParams,
    TextContent,
    Tool,
)

from scripts.morning_gather import gather  # noqa: E402
from scripts.morning_engine import analyze  # noqa: E402
from scripts.lib.mcp_stdio import run_stdio_server  # noqa: E402

# ============================================================================
# Tool registration
#
# `Server(...)` is constructed at the bottom of this module — the 2.x
# constructor-param API (`on_list_tools=`, `on_call_tool=`) needs `list_tools`
# and `call_tool` already defined, unlike the 1.x decorator API.
# ============================================================================


async def list_tools(
    ctx: ServerRequestContext, params: PaginatedRequestParams | None
) -> ListToolsResult:
    """Return the single morning_digest tool."""
    return ListToolsResult(
        tools=[
            Tool(
                name="morning_digest",
                description=(
                    "Synthesize a morning digest by gathering current repo, goal, "
                    "task and decision state and analyzing it into a day plan. "
                    "Wraps gather() -> engine.analyze() in a single call. Returns "
                    "the Digest schema (schema_version, sections, plan, degradation, "
                    "origin)."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "jarvis_home": {
                            "type": "string",
                            "description": (
                                "Root path of the jarvis repo. If empty, auto-detects "
                                "from CWD via git rev-parse."
                            ),
                        },
                    },
                    "required": [],
                },
            ),
        ]
    )


# ============================================================================
# Tool dispatch
# ============================================================================


async def call_tool(ctx: ServerRequestContext, params: CallToolRequestParams) -> CallToolResult:
    """Dispatch to the morning_digest tool."""
    name = params.name
    arguments = params.arguments or {}
    try:
        if name == "morning_digest":
            jarvis_home = arguments.get("jarvis_home", "")

            # Call gather off the event loop via thread pool, with a timeout.
            # gather() makes blocking subprocess/HTTP calls (gh, Supabase); running
            # it on the event loop would stall the MCP server for all other requests.
            try:
                gather_result = await asyncio.wait_for(
                    asyncio.to_thread(gather, jarvis_home),
                    timeout=_GATHER_TIMEOUT,
                )
            except asyncio.TimeoutError:
                result = [
                    TextContent(
                        type="text",
                        text="morning gather timed out after 30s",
                    )
                ]
                return CallToolResult(content=result, isError=True)

            digest = analyze(gather_result)

            result_text = json.dumps(digest.to_dict(), indent=2, default=str)
            return CallToolResult(content=[TextContent(type="text", text=result_text)])

        else:
            return CallToolResult(
                content=[TextContent(type="text", text=f"Unknown tool: {name}")], isError=True
            )

    except Exception as exc:
        traceback.print_exc()  # Log full traceback server-side
        return CallToolResult(
            content=[TextContent(type="text", text=f"Error in {name}: {exc}")], isError=True
        )


# `Server(...)` constructed here (not near the top) because the 2.x
# constructor-param API needs `list_tools`/`call_tool` already defined — see
# the "Tool registration" comment above.
server = Server("jarvis-morning", on_list_tools=list_tools, on_call_tool=call_tool)


# ============================================================================
# Main
# ============================================================================


async def main():
    await run_stdio_server(server)


if __name__ == "__main__":
    asyncio.run(main())
