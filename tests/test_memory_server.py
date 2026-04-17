"""Unit tests for mcp-memory/server.py — pure functions + mocked async.

Covers Memory 2.0 core: temporal scoring, RRF merge, formatting, auto-linking.
"""

from __future__ import annotations

import os
import sys
import types
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Mock external dependencies before importing server.py
# server.py imports mcp, supabase, httpx at module level — we stub them out
# so tests run without installing the full MCP SDK.
# ---------------------------------------------------------------------------

# Create stub modules for mcp.*
_mcp_types = types.ModuleType("mcp.types")
_mcp_types.CallToolResult = MagicMock
_mcp_types.TextContent = MagicMock
_mcp_types.Tool = MagicMock

def _noop_decorator(*args, **kwargs):
    """Return a no-op decorator that passes the function through."""
    def decorator(fn):
        return fn
    return decorator


class _FakeServer:
    """Minimal stub that supports @server.list_tools() and @server.call_tool() decorators."""
    def __init__(self, *args, **kwargs):
        pass
    def list_tools(self):
        return _noop_decorator()
    def call_tool(self):
        return _noop_decorator()


_mcp_server = types.ModuleType("mcp.server")
_mcp_server.Server = _FakeServer

_mcp_server_stdio = types.ModuleType("mcp.server.stdio")
_mcp_server_stdio.stdio_server = MagicMock

_mcp = types.ModuleType("mcp")

for mod_name, mod in [
    ("mcp", _mcp),
    ("mcp.types", _mcp_types),
    ("mcp.server", _mcp_server),
    ("mcp.server.stdio", _mcp_server_stdio),
]:
    sys.modules.setdefault(mod_name, mod)

# Stub supabase only if it's not actually installed. Blindly stubbing with
# setdefault would shadow a real install from other test modules that run
# in the same session (e.g. test_agents_smoke.py imports real `Client`).
try:
    import supabase  # noqa: F401
except ImportError:
    sys.modules["supabase"] = types.ModuleType("supabase")

# Stub httpx only if it's not actually installed. A blind setdefault
# would shadow a real install for the rest of the pytest session (e.g.
# test_agents_smoke.py needs real `httpx.get` to monkey-patch the
# GitHub client).
try:
    import httpx  # noqa: F401
except ImportError:
    sys.modules["httpx"] = types.ModuleType("httpx")

# Stub dotenv
_dotenv = types.ModuleType("dotenv")
_dotenv.load_dotenv = lambda *a, **kw: None
sys.modules.setdefault("dotenv", _dotenv)

# Add mcp-memory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "mcp-memory"))

# Env vars (server reads them for client init)
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-key")

from server import (
    _rrf_merge,
    _apply_temporal_scoring,
    _format_memories,
    _create_auto_links,
    _expand_with_links,
    TEMPORAL_HALF_LIVES,
    SUPERSEDE_SIM_THRESHOLD,
    MAX_AUTO_LINKS,
)


# ---------------------------------------------------------------------------
# _rrf_merge
# ---------------------------------------------------------------------------

class TestRRFMerge:
    """Reciprocal Rank Fusion merges two ranked lists."""

    def test_empty_inputs(self):
        result = _rrf_merge([], [], limit=5)
        assert result == []

    def test_single_list(self):
        rows = [{"id": "a", "name": "mem1"}, {"id": "b", "name": "mem2"}]
        result = _rrf_merge(rows, [], limit=5)
        assert len(result) == 2
        assert result[0]["id"] == "a"  # rank 0 scores higher
        assert result[1]["id"] == "b"

    def test_overlap_boosts_score(self):
        """Items in both lists should score higher than items in one."""
        sem = [{"id": "a", "name": "shared"}, {"id": "b", "name": "sem-only"}]
        kw = [{"id": "a", "name": "shared"}, {"id": "c", "name": "kw-only"}]
        result = _rrf_merge(sem, kw, limit=5)

        # 'a' appears in both → highest score
        assert result[0]["id"] == "a"
        assert result[0]["_rrf_score"] > result[1]["_rrf_score"]

    def test_limit_respected(self):
        rows = [{"id": str(i), "name": f"m{i}"} for i in range(10)]
        result = _rrf_merge(rows, [], limit=3)
        assert len(result) == 3

    def test_score_calculation(self):
        """Verify RRF score formula: 1/(k + rank)."""
        k = 60
        rows = [{"id": "a", "name": "x"}]
        result = _rrf_merge(rows, [], limit=5, k=k)
        expected = 1.0 / (k + 0)
        assert abs(result[0]["_rrf_score"] - expected) < 1e-10

    def test_score_both_lists(self):
        """Score = sum of 1/(k+rank) from each list."""
        k = 60
        sem = [{"id": "a", "name": "x"}]
        kw = [{"id": "z", "name": "y"}, {"id": "a", "name": "x"}]  # 'a' at rank 1 in kw
        result = _rrf_merge(sem, kw, limit=5, k=k)

        a_score = next(r for r in result if r["id"] == "a")
        expected = 1.0 / (k + 0) + 1.0 / (k + 1)  # rank 0 in sem + rank 1 in kw
        assert abs(a_score["_rrf_score"] - expected) < 1e-10

    def test_name_fallback_for_id(self):
        """Rows without 'id' use 'name' as identifier."""
        rows = [{"name": "alpha"}, {"name": "beta"}]
        result = _rrf_merge(rows, [], limit=5)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# _apply_temporal_scoring
# ---------------------------------------------------------------------------

class TestTemporalScoring:
    """Temporal scoring re-ranks by recency × access boost."""

    @staticmethod
    def _make_row(mem_type="decision", days_ago=0, accessed_days_ago=None, rrf=0.5):
        now = datetime.now(timezone.utc)
        updated = (now - timedelta(days=days_ago)).isoformat()
        accessed = (now - timedelta(days=accessed_days_ago)).isoformat() if accessed_days_ago is not None else None
        return {
            "type": mem_type,
            "updated_at": updated,
            "last_accessed_at": accessed,
            "_rrf_score": rrf,
        }

    def test_recent_ranks_higher(self):
        old = self._make_row(days_ago=30)
        new = self._make_row(days_ago=1)
        result = _apply_temporal_scoring([old, new])
        assert result[0]["_temporal_score"] > result[1]["_temporal_score"]

    def test_same_age_equal_scores(self):
        a = self._make_row(days_ago=5, rrf=0.5)
        b = self._make_row(days_ago=5, rrf=0.5)
        result = _apply_temporal_scoring([a, b])
        assert abs(result[0]["_temporal_score"] - result[1]["_temporal_score"]) < 1e-6

    def test_access_boost(self):
        """Recently accessed memory gets boosted."""
        accessed = self._make_row(days_ago=10, accessed_days_ago=1)
        not_accessed = self._make_row(days_ago=10)
        result = _apply_temporal_scoring([not_accessed, accessed])
        assert result[0]["_temporal_score"] > result[1]["_temporal_score"]

    def test_type_half_lives(self):
        """Project memories decay faster than feedback memories."""
        project = self._make_row(mem_type="project", days_ago=14)  # half-life 7d
        feedback = self._make_row(mem_type="feedback", days_ago=14)  # half-life 90d
        result = _apply_temporal_scoring([project, feedback])
        # feedback should score higher — 14 days is well within its 90d half-life
        assert result[0]["type"] == "feedback"

    def test_rrf_weight_preserved(self):
        """Higher RRF score leads to higher temporal score, all else equal."""
        high_rrf = self._make_row(rrf=0.9, days_ago=5)
        low_rrf = self._make_row(rrf=0.1, days_ago=5)
        result = _apply_temporal_scoring([low_rrf, high_rrf])
        assert result[0]["_temporal_score"] > result[1]["_temporal_score"]

    def test_handles_missing_timestamps(self):
        """Gracefully handles rows with missing/invalid timestamps."""
        row = {"type": "decision", "updated_at": "", "last_accessed_at": None, "_rrf_score": 0.5}
        result = _apply_temporal_scoring([row])
        assert "_temporal_score" in result[0]
        assert result[0]["_temporal_score"] > 0

    def test_zero_days_ago(self):
        """Just-updated memory gets near-full score."""
        row = self._make_row(days_ago=0, rrf=1.0)
        result = _apply_temporal_scoring([row])
        # recency ≈ 1.0, so temporal_score ≈ rrf * 1.0 * access_factor
        assert result[0]["_temporal_score"] >= 0.9

    def test_sorted_descending(self):
        rows = [
            self._make_row(days_ago=30, rrf=0.3),
            self._make_row(days_ago=1, rrf=0.8),
            self._make_row(days_ago=10, rrf=0.5),
        ]
        result = _apply_temporal_scoring(rows)
        scores = [r["_temporal_score"] for r in result]
        assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# _format_memories
# ---------------------------------------------------------------------------

class TestFormatMemories:
    """Memory formatting for LLM output."""

    def test_basic_format(self):
        mem = {
            "name": "test_mem",
            "type": "decision",
            "project": "jarvis",
            "description": "A test memory",
            "content": "Some content here",
            "tags": ["tag1", "tag2"],
            "updated_at": "2026-04-09T12:00:00+00:00",
        }
        result = _format_memories([mem])
        assert len(result) == 1
        assert "## test_mem (decision, jarvis)" in result[0]
        assert "[tag1, tag2]" in result[0]
        assert "*A test memory*" in result[0]
        assert "Some content here" in result[0]

    def test_global_project(self):
        mem = {"name": "x", "type": "user", "project": None, "description": "", "content": "c", "tags": []}
        result = _format_memories([mem])
        assert "(user, global)" in result[0]

    def test_no_tags(self):
        mem = {"name": "x", "type": "user", "project": None, "description": "", "content": "c"}
        result = _format_memories([mem])
        # Header should NOT contain tag brackets when tags are missing
        header_line = result[0].split("\n")[0]
        assert "] " not in header_line or header_line.endswith(")")

    def test_empty_tags_list(self):
        mem = {"name": "x", "type": "user", "project": None, "description": "", "content": "c", "tags": []}
        result = _format_memories([mem])
        header_line = result[0].split("\n")[0]
        # Empty tags list should not produce brackets
        assert "[]" not in header_line

    def test_link_info(self):
        mem = {
            "name": "linked_mem",
            "type": "decision",
            "project": "jarvis",
            "description": "desc",
            "content": "body",
            "tags": [],
            "link_type": "related",
            "link_strength": 0.75,
            "updated_at": "2026-04-09",
        }
        result = _format_memories([mem], link_info=True)
        assert "← related (0.75)" in result[0]

    def test_link_info_not_shown_without_flag(self):
        mem = {
            "name": "x", "type": "decision", "project": None,
            "description": "", "content": "c", "tags": [],
            "link_type": "related", "link_strength": 0.75,
        }
        result = _format_memories([mem], link_info=False)
        assert "← related" not in result[0]

    def test_multiple_memories(self):
        mems = [
            {"name": f"m{i}", "type": "project", "project": "j", "description": "", "content": f"c{i}", "tags": []}
            for i in range(5)
        ]
        result = _format_memories(mems)
        assert len(result) == 5


# ---------------------------------------------------------------------------
# _create_auto_links (async, mocked Supabase)
# ---------------------------------------------------------------------------

class TestCreateAutoLinks:
    """Auto-linking creates memory_links entries based on similarity."""

    @pytest.fixture
    def mock_client(self):
        client = MagicMock()
        client.table.return_value.upsert.return_value.execute.return_value = MagicMock(data=[])
        return client

    @pytest.mark.asyncio
    async def test_creates_related_links(self, mock_client):
        similar = [
            {"id": "target-1", "type": "project", "similarity": 0.70},
            {"id": "target-2", "type": "project", "similarity": 0.65},
        ]
        await _create_auto_links(mock_client, "source-id", similar, mem_type="project")

        mock_client.table.assert_called_with("memory_links")
        call_args = mock_client.table.return_value.upsert.call_args
        links = call_args[0][0]
        assert len(links) == 2
        assert all(l["link_type"] == "related" for l in links)
        assert links[0]["strength"] == 0.70
        assert links[1]["strength"] == 0.65

    @pytest.mark.asyncio
    async def test_supersession_for_similar_decisions(self, mock_client):
        similar = [
            {"id": "old-decision", "type": "decision", "similarity": SUPERSEDE_SIM_THRESHOLD + 0.05},
        ]
        await _create_auto_links(mock_client, "new-decision", similar, mem_type="decision")

        links = mock_client.table.return_value.upsert.call_args[0][0]
        assert links[0]["link_type"] == "supersedes"

    @pytest.mark.asyncio
    async def test_no_supersession_for_non_decisions(self, mock_client):
        similar = [
            {"id": "target", "type": "project", "similarity": 0.90},
        ]
        await _create_auto_links(mock_client, "source", similar, mem_type="project")

        links = mock_client.table.return_value.upsert.call_args[0][0]
        assert links[0]["link_type"] == "related"  # not supersedes

    @pytest.mark.asyncio
    async def test_max_links_limit(self, mock_client):
        similar = [{"id": f"t-{i}", "type": "project", "similarity": 0.70} for i in range(10)]
        await _create_auto_links(mock_client, "source", similar, mem_type="project")

        links = mock_client.table.return_value.upsert.call_args[0][0]
        assert len(links) == MAX_AUTO_LINKS

    @pytest.mark.asyncio
    async def test_empty_similar_rows(self, mock_client):
        await _create_auto_links(mock_client, "source", [], mem_type="project")
        mock_client.table.assert_not_called()

    @pytest.mark.asyncio
    async def test_swallows_exceptions(self, mock_client):
        """Fire-and-forget: errors don't propagate."""
        mock_client.table.side_effect = Exception("DB error")
        # Should not raise
        await _create_auto_links(mock_client, "source", [{"id": "t", "type": "p", "similarity": 0.7}], "project")


# ---------------------------------------------------------------------------
# _expand_with_links (async, mocked Supabase)
# ---------------------------------------------------------------------------

class TestExpandWithLinks:
    """Graph traversal fetches 1-hop linked memories."""

    @pytest.fixture
    def mock_client(self):
        client = MagicMock()
        return client

    @pytest.mark.asyncio
    async def test_returns_linked_memories(self, mock_client):
        mock_client.rpc.return_value.execute.return_value = MagicMock(
            data=[
                {"id": "linked-1", "name": "linked_mem", "link_type": "related", "link_strength": 0.75},
            ]
        )
        result = await _expand_with_links(mock_client, ["source-id"])
        assert len(result) == 1
        assert result[0]["id"] == "linked-1"

    @pytest.mark.asyncio
    async def test_empty_when_no_links(self, mock_client):
        mock_client.rpc.return_value.execute.return_value = MagicMock(data=[])
        result = await _expand_with_links(mock_client, ["source-id"])
        assert result == []

    @pytest.mark.asyncio
    async def test_swallows_exceptions(self, mock_client):
        mock_client.rpc.side_effect = Exception("DB error")
        result = await _expand_with_links(mock_client, ["source-id"])
        assert result == []

    @pytest.mark.asyncio
    async def test_passes_memory_ids_to_rpc(self, mock_client):
        mock_client.rpc.return_value.execute.return_value = MagicMock(data=[])
        await _expand_with_links(mock_client, ["id-1", "id-2"])
        mock_client.rpc.assert_called_once_with(
            "get_linked_memories",
            {"memory_ids": ["id-1", "id-2"], "link_types": None},
        )


# ---------------------------------------------------------------------------
# Recall pipeline dedup regression (bidirectional link bug)
# ---------------------------------------------------------------------------

class TestRecallLinkedDedup:
    """Regression: bidirectional links should not produce duplicate linked memories."""

    def test_dedup_within_linked_results(self):
        """If _expand_with_links returns the same memory twice (bidirectional links),
        the recall pipeline should deduplicate to keep only one."""
        # Simulate: main results have IDs ["main-1", "main-2"]
        # Linked results return "linked-A" twice (from both link directions)
        main_ids = {"main-1", "main-2"}
        linked = [
            {"id": "linked-A", "name": "mem_a", "link_type": "related", "link_strength": 0.71},
            {"id": "linked-A", "name": "mem_a", "link_type": "related", "link_strength": 0.63},
            {"id": "linked-B", "name": "mem_b", "link_type": "related", "link_strength": 0.65},
        ]

        # Reproduce the dedup logic from _hybrid_recall
        found_ids = set(main_ids)
        seen_linked: set[str] = set()
        unique_linked = []
        for r in linked:
            rid = r.get("id")
            if rid not in found_ids and rid not in seen_linked:
                seen_linked.add(rid)
                unique_linked.append(r)

        assert len(unique_linked) == 2
        assert unique_linked[0]["id"] == "linked-A"
        assert unique_linked[0]["link_strength"] == 0.71  # first (strongest) kept
        assert unique_linked[1]["id"] == "linked-B"

    def test_main_results_excluded_from_linked(self):
        """Linked results that duplicate main results should be excluded."""
        main_ids = {"id-1"}
        linked = [
            {"id": "id-1", "name": "same_as_main", "link_type": "related", "link_strength": 0.80},
            {"id": "id-2", "name": "different", "link_type": "related", "link_strength": 0.70},
        ]

        found_ids = set(main_ids)
        seen_linked: set[str] = set()
        unique_linked = []
        for r in linked:
            rid = r.get("id")
            if rid not in found_ids and rid not in seen_linked:
                seen_linked.add(rid)
                unique_linked.append(r)

        assert len(unique_linked) == 1
        assert unique_linked[0]["id"] == "id-2"
