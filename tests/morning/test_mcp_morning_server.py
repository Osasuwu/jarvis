"""Tests for mcp-morning/server.py morning_digest tool (#1588).

Simpler than mcp-status's test suite: morning_gather.gather() already returns
a MorningGatherResult that morning_engine.analyze() consumes directly, so
there is no conversion-layer or contradiction-cache surface to test here.
Covers: tool schema shape, handler coroutine-ness, timeout/exception one-line
error dispatch (mirrors #1017/#1083 regressions in the status server).
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

# Load mcp-morning/server.py under a UNIQUE module name ("morning_server"), not
# the bare "server" or "status_server". mcp-memory's and mcp-status's test
# suites also claim module names for their own server.py; grabbing a name
# already in sys.modules would silently return the WRONG module on collection
# (full-suite collision, #1017). importlib with an explicit unique name and no
# sys.path mutation keeps all three server.py files isolated.
_morning_server_path = Path(__file__).parent.parent.parent / "mcp-morning" / "server.py"
_spec = importlib.util.spec_from_file_location("morning_server", _morning_server_path)
morning_server = importlib.util.module_from_spec(_spec)
sys.modules["morning_server"] = morning_server
_spec.loader.exec_module(morning_server)


def _sources(**overrides):
    from scripts.morning_gather import MorningGatherResult

    defaults = dict(
        repos=["Osasuwu/jarvis"],
        milestones={"Osasuwu/jarvis": [{"number": 64, "title": "M64"}]},
        decisions=[],
        goals=[],
        owner_tasks=[],
        provenance={"gh_milestones": {"ran": True, "ok": True, "input_rows": 1}},
        gathered_at="2026-08-18T09:00:00+00:00",
        errors=[],
    )
    defaults.update(overrides)
    return MorningGatherResult(**defaults)


# ============================================================================
# Test: Tool schema compliance
# ============================================================================


def test_tool_schema_structure():
    """Verify list_tools returns a schema naming the tool, gather and jarvis_home."""
    import inspect

    src = inspect.getsource(morning_server.list_tools)
    assert "morning_digest" in src
    assert "jarvis_home" in src


def test_handlers_are_coroutines():
    """The MCP SDK awaits every registered handler — a sync `def list_tools`
    connects fine but makes `tools/list` raise
    `object list can't be used in 'await' expression` at runtime, silently
    dropping every tool from the server (#1017 regression in mcp-status,
    same failure mode applies here).
    """
    import inspect

    assert inspect.iscoroutinefunction(morning_server.list_tools), (
        "list_tools must be `async def` — the MCP SDK awaits it"
    )
    assert inspect.iscoroutinefunction(morning_server.call_tool), (
        "call_tool must be `async def` — the MCP SDK awaits it"
    )


# ============================================================================
# Test: Integration — gather result flows through analyze() to a Digest
# ============================================================================


def test_end_to_end_gather_to_digest():
    """gather() -> analyze() directly, no conversion layer (unlike status)."""
    from scripts.morning_engine import analyze

    sources = _sources()
    digest = analyze(sources)

    assert digest.schema_version == 2
    assert digest.section("repo_hygiene") is not None


# ============================================================================
# Test: Off-event-loop gather with timeout / exception dispatch (#1083 pattern)
# ============================================================================


def test_gather_timeout_returns_one_line_error():
    """When gather() exceeds the timeout, return a one-line error (no traceback)."""

    async def _test():
        params = SimpleNamespace(name="morning_digest", arguments={"jarvis_home": ""})
        with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError()):
            result = await morning_server.call_tool(None, params)
            assert len(result.content) == 1
            assert "timed out" in result.content[0].text
            assert "Traceback" not in result.content[0].text

    asyncio.run(_test())


def test_exception_returns_one_line_error_no_traceback():
    """Exception in gather returns one-line error; traceback is server-side only."""

    async def _test():
        params = SimpleNamespace(name="morning_digest", arguments={"jarvis_home": ""})
        with patch.object(morning_server, "gather", side_effect=ValueError("test error")):
            result = await morning_server.call_tool(None, params)
            assert len(result.content) == 1
            assert "Error in morning_digest" in result.content[0].text
            assert "Traceback" not in result.content[0].text

    asyncio.run(_test())


def test_unknown_tool_returns_one_line_message():
    async def _test():
        params = SimpleNamespace(name="not_a_real_tool", arguments={})
        result = await morning_server.call_tool(None, params)
        assert len(result.content) == 1
        assert "Unknown tool" in result.content[0].text

    asyncio.run(_test())
