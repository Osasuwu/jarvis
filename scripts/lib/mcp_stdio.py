"""Shared stdio-transport wrapper for the MCP servers (#1646).

On Windows, `mcp.server.stdio.stdio_server()`'s `__aexit__` can raise
`OSError: [Errno 22] Invalid argument` from `anyio`'s stdout-flush during
task-group teardown, when the parent process (Claude Code) has already torn
down the stdin pipe to this child before the writer task's cleanup flush
runs. This is cosmetic on shutdown but poisons `.claude/mcp-failures.jsonl`
and is correlated with sessions seeing zero mcp__<server>__* tools when the
crash/handshake timing overlaps tool registration.

`run_stdio_server()` wraps the whole open+run+teardown block and swallows
only that specific errno; any other OSError still propagates.
"""

from __future__ import annotations

from mcp.server.stdio import stdio_server


async def run_stdio_server(server) -> None:
    # ceiling: the try block spans stdio_server() open, server.run(), and its
    # teardown — not just the SDK-internal flush() call — because that
    # internal call graph can shift between mcp/anyio versions and a
    # narrower catch would silently stop matching. If a genuine errno-22
    # OSError ever needs to surface from normal request handling (not
    # teardown), narrow this back down; not expected in practice since the
    # errno only appears in the known teardown-flush case.
    try:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())
    except OSError as exc:
        if exc.errno != 22:
            raise
