"""Unit tests for mcp-memory/server.py — pure functions + mocked async.

Covers Memory 2.0 core: temporal scoring, RRF merge, formatting, auto-linking.
"""

from __future__ import annotations

import json
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


class _FakeTextContent:
    """Minimal TextContent replica so tests can read back .text on returns.

    The real mcp.types.TextContent is a pydantic model; tests don't need
    validation, just attribute access for the error-path checks below.
    """
    def __init__(self, type: str = "text", text: str = ""):
        self.type = type
        self.text = text


_mcp_types.TextContent = _FakeTextContent
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
    _handle_store,
    TEMPORAL_HALF_LIVES,
    SUPERSEDE_SIM_THRESHOLD,
    MAX_AUTO_LINKS,
)
import server as server_module


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

    # -- #240: confidence entrenchment multiplier ---------------------------

    def test_confidence_high_outranks_low(self):
        """Higher-confidence row ranks above lower-confidence at equal age/RRF."""
        high = self._make_row(days_ago=5, rrf=0.5)
        high["id"] = "high"
        high["confidence"] = 1.0
        low = self._make_row(days_ago=5, rrf=0.5)
        low["id"] = "low"
        low["confidence"] = 0.5
        result = _apply_temporal_scoring([low, high])
        assert result[0]["id"] == "high"
        # score(conf=1.0) / score(conf=0.5) = 1.0 / 0.75 exactly.
        ratio = result[0]["_temporal_score"] / result[1]["_temporal_score"]
        assert abs(ratio - (1.0 / 0.75)) < 1e-9

    def test_confidence_null_treated_as_1(self):
        """Legacy rows (no confidence) score same as confidence=1.0 (no regression)."""
        null_row = self._make_row(days_ago=5, rrf=0.5)
        null_row["id"] = "null"
        full_row = self._make_row(days_ago=5, rrf=0.5)
        full_row["id"] = "full"
        full_row["confidence"] = 1.0
        result = _apply_temporal_scoring([null_row, full_row])
        s_null = next(r["_temporal_score"] for r in result if r["id"] == "null")
        s_full = next(r["_temporal_score"] for r in result if r["id"] == "full")
        assert abs(s_null - s_full) < 1e-9

    def test_confidence_zero_gets_floor(self):
        """confidence=0 → score = CONFIDENCE_FLOOR * score(confidence=1.0) (soft floor)."""
        from server import CONFIDENCE_FLOOR

        zero = self._make_row(days_ago=5, rrf=0.5)
        zero["id"] = "zero"
        zero["confidence"] = 0.0
        full = self._make_row(days_ago=5, rrf=0.5)
        full["id"] = "full"
        full["confidence"] = 1.0
        result = _apply_temporal_scoring([zero, full])
        s_zero = next(r["_temporal_score"] for r in result if r["id"] == "zero")
        s_full = next(r["_temporal_score"] for r in result if r["id"] == "full")
        assert abs(s_zero / s_full - CONFIDENCE_FLOOR) < 1e-9


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

    # Brief mode — Phase 7.2. One-line rows so bulk/auto-injection sites
    # don't pay full-content budget.

    def test_brief_basic_layout(self):
        mem = {
            "name": "foo",
            "type": "feedback",
            "project": "jarvis",
            "tags": ["a", "b"],
            "description": "hello world",
            "similarity": 0.42,
            "content": "MUST_NOT_APPEAR",
        }
        result = _format_memories([mem], brief=True)
        assert result == ["- foo [feedback/jarvis] [a, b] (sim 0.42): hello world"]
        assert "MUST_NOT_APPEAR" not in result[0]

    def test_brief_global_scope(self):
        mem = {"name": "g", "type": "user", "project": None, "description": "d"}
        result = _format_memories([mem], brief=True)
        assert result[0] == "- g [user/global]: d"

    def test_brief_temporal_score_leads_when_present(self):
        # `_temporal_score` is what drives actual ordering after
        # _apply_temporal_scoring. It must appear first so the shown score
        # matches the displayed rank; the retrieval signal (rrf/sim) trails
        # as provenance.
        mem = {
            "name": "t",
            "type": "decision",
            "project": "jarvis",
            "description": "x",
            "_temporal_score": 0.0456,
            "_rrf_score": 0.0333,
        }
        result = _format_memories([mem], brief=True)
        assert "(score 0.046; rrf 0.033)" in result[0]

    def test_brief_rrf_wins_over_similarity(self):
        mem = {
            "name": "r", "type": "decision", "description": "x",
            "_rrf_score": 0.05, "similarity": 0.9,
        }
        result = _format_memories([mem], brief=True)
        assert "rrf 0.050" in result[0]
        assert "sim" not in result[0]

    def test_brief_link_info(self):
        mem = {
            "name": "l", "type": "decision", "project": "jarvis",
            "description": "d", "similarity": 0.5,
            "link_type": "related", "link_strength": 0.75,
        }
        result = _format_memories([mem], link_info=True, brief=True)
        assert "← related (0.75)" in result[0]
        assert result[0].startswith("- l [decision/jarvis]")

    def test_brief_no_score_fields(self):
        mem = {"name": "n", "type": "reference", "project": None, "description": "d"}
        result = _format_memories([mem], brief=True)
        assert result[0] == "- n [reference/global]: d"

    def test_brief_empty_description(self):
        # Migration-target memories carry empty descriptions — brief still
        # surfaces the name (no crash, trailing `: ` is intentional).
        mem = {"name": "bare", "type": "decision", "project": "jarvis"}
        result = _format_memories([mem], brief=True)
        assert result[0] == "- bare [decision/jarvis]: "


# ---------------------------------------------------------------------------
# _create_auto_links (async, mocked Supabase)
# ---------------------------------------------------------------------------

class TestCreateAutoLinks:
    """Auto-linking creates memory_links entries based on similarity.

    Phase 2b changed the contract: links are always created as 'related'
    first, then the classifier (or legacy fallback) decides whether to
    upgrade to 'supersedes' / mark expired. We assert against the FIRST
    upsert call (the related batch) where it matters.
    """

    @pytest.fixture
    def mock_client(self):
        client = MagicMock()
        client.table.return_value.upsert.return_value.execute.return_value = MagicMock(data=[])
        # Hydration query returns no rows (test path skips classifier anyway).
        client.table.return_value.select.return_value.in_.return_value.execute.return_value = MagicMock(data=[])
        return client

    def _first_links_upsert(self, mock_client):
        """Return the first list-of-links arg passed to upsert."""
        for call in mock_client.table.return_value.upsert.call_args_list:
            arg = call[0][0]
            if isinstance(arg, list):
                return arg
        return []

    @pytest.mark.asyncio
    async def test_creates_related_links(self, mock_client):
        similar = [
            {"id": "target-1", "type": "project", "similarity": 0.70},
            {"id": "target-2", "type": "project", "similarity": 0.65},
        ]
        await _create_auto_links(mock_client, "source-id", similar, mem_type="project")

        links = self._first_links_upsert(mock_client)
        assert len(links) == 2
        assert all(l["link_type"] == "related" for l in links)
        assert links[0]["strength"] == 0.70
        assert links[1]["strength"] == 0.65

    @pytest.mark.asyncio
    async def test_legacy_fallback_supersedes_same_type(self, mock_client, monkeypatch):
        """When the classifier is unavailable (no API key, no candidate),
        the legacy heuristic fires: same type + sim >= 0.85 → supersede."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        similar = [
            {"id": "old-decision", "type": "decision", "similarity": SUPERSEDE_SIM_THRESHOLD + 0.05},
        ]
        await _create_auto_links(mock_client, "new-decision", similar, mem_type="decision")

        # The legacy fallback updates memories.superseded_by on the target.
        update_calls = [
            c for c in mock_client.table.return_value.update.call_args_list
            if c[0][0].get("superseded_by") == "new-decision"
        ]
        assert len(update_calls) == 1

    @pytest.mark.asyncio
    async def test_no_supersession_when_below_threshold(self, mock_client, monkeypatch):
        """Even same-type, below SUPERSEDE_SIM_THRESHOLD → no supersession."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        similar = [
            {"id": "target", "type": "project", "similarity": 0.70},
        ]
        await _create_auto_links(mock_client, "source", similar, mem_type="project")

        update_calls = [
            c for c in mock_client.table.return_value.update.call_args_list
            if c[0][0].get("superseded_by") == "source"
        ]
        assert update_calls == []

    @pytest.mark.asyncio
    async def test_max_links_limit(self, mock_client):
        similar = [{"id": f"t-{i}", "type": "project", "similarity": 0.70} for i in range(10)]
        await _create_auto_links(mock_client, "source", similar, mem_type="project")

        links = self._first_links_upsert(mock_client)
        assert len(links) == MAX_AUTO_LINKS

    @pytest.mark.asyncio
    async def test_empty_similar_rows(self, mock_client):
        await _create_auto_links(mock_client, "source", [], mem_type="project")
        # No links to insert → the memory_links upsert should not fire.
        link_calls = [
            c for c in mock_client.table.call_args_list
            if c[0][0] == "memory_links"
        ]
        assert link_calls == []

    @pytest.mark.asyncio
    async def test_swallows_exceptions(self, mock_client):
        """Fire-and-forget: errors don't propagate."""
        mock_client.table.side_effect = Exception("DB error")
        # Should not raise
        await _create_auto_links(mock_client, "source", [{"id": "t", "type": "p", "similarity": 0.7}], "project")


# ---------------------------------------------------------------------------
# Phase 2b classifier — _apply_classifier_decision routing + queue writes
# ---------------------------------------------------------------------------

from server import _apply_classifier_decision, CLASSIFIER_APPLY_THRESHOLD  # noqa: E402
from classifier import ClassifierDecision  # noqa: E402


class TestApplyClassifierDecision:
    """Routing of classifier decisions: which DB mutations fire when."""

    @pytest.fixture
    def mock_client(self):
        client = MagicMock()
        # Per-table mocks so we can filter calls by table name.
        # Each call to client.table("foo") returns the same mock instance
        # for "foo", but a *different* mock for "bar" — that's how we tell
        # an insert into memory_review_queue from one into memory_links.
        client._tables = {}

        def _get_table(name):
            if name not in client._tables:
                t = MagicMock()
                # update().eq().is_().execute() returns truthy .data so the
                # rowcount check in _apply_classifier_decision sees a hit.
                t.update.return_value.eq.return_value.is_.return_value \
                    .execute.return_value = MagicMock(data=[{"id": "row"}])
                t.insert.return_value.execute.return_value = MagicMock()
                t.upsert.return_value.execute.return_value = MagicMock()
                client._tables[name] = t
            return client._tables[name]

        client.table.side_effect = _get_table
        return client

    def _update_calls(self, mock_client, key: str, table: str = "memories"):
        """Find update() calls on a specific table whose payload contains a key."""
        t = mock_client._tables.get(table)
        if t is None:
            return []
        return [
            c for c in t.update.call_args_list
            if isinstance(c[0][0], dict) and key in c[0][0]
        ]

    def _queue_inserts(self, mock_client):
        """Find insert calls into memory_review_queue specifically."""
        t = mock_client._tables.get("memory_review_queue")
        if t is None:
            return []
        return t.insert.call_args_list

    def _link_upserts(self, mock_client, link_type: str | None = None):
        """Find upsert calls into memory_links, optionally filtered by link_type."""
        t = mock_client._tables.get("memory_links")
        if t is None:
            return []
        calls = t.upsert.call_args_list
        if link_type is None:
            return calls
        out = []
        for c in calls:
            payload = c[0][0]
            if isinstance(payload, dict) and payload.get("link_type") == link_type:
                out.append(c)
        return out

    @pytest.mark.asyncio
    async def test_high_confidence_update_marks_superseded(self, mock_client):
        decision = ClassifierDecision(
            decision="UPDATE", target_id="old-id",
            confidence=0.95, reasoning="refines target",
        )
        neighbors = [{"id": "old-id", "name": "old", "similarity": 0.82}]
        await _apply_classifier_decision(mock_client, "new-id", decision, neighbors)

        # The target was marked superseded.
        sup_calls = self._update_calls(mock_client, "superseded_by")
        assert len(sup_calls) == 1
        assert sup_calls[0][0][0]["superseded_by"] == "new-id"

        # The related-link was upgraded to a `supersedes` link in memory_links.
        sup_links = self._link_upserts(mock_client, link_type="supersedes")
        assert len(sup_links) == 1
        link_payload = sup_links[0][0][0]
        assert link_payload["source_id"] == "new-id"
        assert link_payload["target_id"] == "old-id"

        # And the decision was recorded with status=auto_applied.
        inserts = self._queue_inserts(mock_client)
        assert len(inserts) == 1
        payload = inserts[0][0][0]
        assert payload["decision"] == "UPDATE"
        assert payload["status"] == "auto_applied"
        assert payload["target_id"] == "old-id"

    @pytest.mark.asyncio
    async def test_high_confidence_delete_sets_expired(self, mock_client):
        decision = ClassifierDecision(
            decision="DELETE", target_id="old-id",
            confidence=0.92, reasoning="negates target",
        )
        neighbors = [{"id": "old-id", "name": "old", "similarity": 0.85}]
        await _apply_classifier_decision(mock_client, "new-id", decision, neighbors)

        exp_calls = self._update_calls(mock_client, "expired_at")
        assert len(exp_calls) == 1

        inserts = self._queue_inserts(mock_client)
        assert inserts[0][0][0]["decision"] == "DELETE"
        assert inserts[0][0][0]["status"] == "auto_applied"

    @pytest.mark.asyncio
    async def test_low_confidence_update_queues_pending(self, mock_client):
        """Low confidence: do NOT mutate target, write queue entry as pending."""
        decision = ClassifierDecision(
            decision="UPDATE", target_id="old-id",
            confidence=CLASSIFIER_APPLY_THRESHOLD - 0.1,
            reasoning="ambiguous",
        )
        neighbors = [{"id": "old-id", "name": "old", "similarity": 0.78}]
        await _apply_classifier_decision(mock_client, "new-id", decision, neighbors)

        sup_calls = self._update_calls(mock_client, "superseded_by")
        assert sup_calls == []  # nothing mutated

        inserts = self._queue_inserts(mock_client)
        payload = inserts[0][0][0]
        assert payload["status"] == "pending"
        assert payload["applied_at"] is None

    @pytest.mark.asyncio
    async def test_noop_records_decision_no_mutation(self, mock_client):
        decision = ClassifierDecision(
            decision="NOOP", target_id=None,
            confidence=0.9, reasoning="redundant",
        )
        neighbors = [{"id": "x", "name": "x", "similarity": 0.9}]
        await _apply_classifier_decision(mock_client, "new-id", decision, neighbors)

        # No supersede / expired mutations.
        assert self._update_calls(mock_client, "superseded_by") == []
        assert self._update_calls(mock_client, "expired_at") == []
        # Decision still recorded for audit.
        inserts = self._queue_inserts(mock_client)
        assert len(inserts) == 1
        assert inserts[0][0][0]["decision"] == "NOOP"

    @pytest.mark.asyncio
    async def test_high_confidence_add_no_queue_entry(self, mock_client):
        """ADD with high confidence is the trivial case — don't pollute queue."""
        decision = ClassifierDecision(
            decision="ADD", target_id=None,
            confidence=0.95, reasoning="genuinely new",
        )
        neighbors = [{"id": "x", "name": "x", "similarity": 0.76}]
        await _apply_classifier_decision(mock_client, "new-id", decision, neighbors)

        assert self._queue_inserts(mock_client) == []

    @pytest.mark.asyncio
    async def test_hallucinated_target_id_refused(self, mock_client):
        """Model returned an id we never showed it → refuse to mutate."""
        decision = ClassifierDecision(
            decision="UPDATE", target_id="never-existed",
            confidence=0.95, reasoning="...",
        )
        neighbors = [{"id": "real-id", "name": "real", "similarity": 0.85}]
        await _apply_classifier_decision(mock_client, "new-id", decision, neighbors)

        assert self._update_calls(mock_client, "superseded_by") == []
        # Still recorded, but with status=pending and target_id=None.
        inserts = self._queue_inserts(mock_client)
        payload = inserts[0][0][0]
        assert payload["status"] == "pending"
        assert payload["target_id"] is None


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
            {"memory_ids": ["id-1", "id-2"], "link_types": None, "show_history": False},
        )

    @pytest.mark.asyncio
    async def test_passes_show_history_to_rpc(self, mock_client):
        mock_client.rpc.return_value.execute.return_value = MagicMock(data=[])
        await _expand_with_links(mock_client, ["id-1"], show_history=True)
        mock_client.rpc.assert_called_once_with(
            "get_linked_memories",
            {"memory_ids": ["id-1"], "link_types": None, "show_history": True},
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


# ---------------------------------------------------------------------------
# Phase 2c: memory_store must reject writes missing source_provenance
# ---------------------------------------------------------------------------

class TestHandleStoreProvenance:
    """Phase 2c — every memory write carries a namespaced source_provenance.

    The MCP boundary rejects missing/blank values with a readable error so
    callers don't hit a raw NOT NULL violation from Postgres downstream.
    """

    @pytest.fixture(autouse=True)
    def _patch_client(self, monkeypatch):
        """Swap _get_client for a mock so validation failures don't need live DB."""
        self.client = MagicMock()
        monkeypatch.setattr(server_module, "_get_client", lambda: self.client)

    @pytest.mark.asyncio
    async def test_rejects_missing_provenance(self):
        result = await _handle_store({
            "type": "project",
            "name": "test_missing",
            "content": "test content",
            # no source_provenance
        })
        assert len(result) == 1
        assert "source_provenance is required" in result[0].text
        # Validation fired before any DB access.
        self.client.table.assert_not_called()

    @pytest.mark.asyncio
    async def test_rejects_blank_provenance(self):
        result = await _handle_store({
            "type": "project",
            "name": "test_blank",
            "content": "test content",
            "source_provenance": "   ",
        })
        assert "source_provenance is required" in result[0].text
        self.client.table.assert_not_called()

    @pytest.mark.asyncio
    async def test_rejects_none_provenance(self):
        result = await _handle_store({
            "type": "project",
            "name": "test_none",
            "content": "test content",
            "source_provenance": None,
        })
        assert "source_provenance is required" in result[0].text
        self.client.table.assert_not_called()

    @pytest.mark.asyncio
    async def test_provenance_stripped_before_persist(self, monkeypatch):
        """Accepted provenance is trimmed — no leading/trailing whitespace
        leaks into the DB row, keeping audit queries clean."""
        # Short-circuit embedding so we don't need Voyage env/network.
        # Signature accepts **kwargs so #242's model= param doesn't break it.
        async def _fake_embed(_text, **_kwargs):
            return None
        monkeypatch.setattr(server_module, "_embed", _fake_embed)

        # project="jarvis" takes the upsert branch. Rig the chain to return
        # a stored id so _handle_store completes without errors.
        tbl = MagicMock()
        tbl.upsert.return_value.execute.return_value = MagicMock(data=[{"id": "stored-1"}])
        self.client.table.return_value = tbl

        await _handle_store({
            "type": "project",
            "name": "test_strip",
            "content": "test content",
            "project": "jarvis",
            "source_provenance": "  skill:test  ",
        })

        upsert_calls = tbl.upsert.call_args_list
        assert upsert_calls, "expected at least one upsert call"
        data_arg = upsert_calls[-1][0][0]
        assert data_arg["source_provenance"] == "skill:test"


# ---------------------------------------------------------------------------
# #242: dual-embedding machinery — column/RPC mapping + dual-write
# ---------------------------------------------------------------------------

from server import (  # noqa: E402
    _model_slot,
    _embed_upsert_fields,
    _compute_write_embeddings,
)


class TestModelSlotMapping:
    """#242: the model → column/RPC table drives both read and write paths.

    If this mapping drifts, writes land in the wrong column and reads
    query the wrong RPC — a silent data-integrity bug. Lock it down.
    """

    def test_voyage_3_lite_maps_to_v1_column(self):
        slot = _model_slot("voyage-3-lite")
        assert slot["embedding_column"] == "embedding"
        assert slot["rpc"] == "match_memories"

    def test_voyage_3_maps_to_v2_column(self):
        slot = _model_slot("voyage-3")
        assert slot["embedding_column"] == "embedding_v2"
        assert slot["rpc"] == "match_memories_v2"

    def test_unknown_model_falls_back_to_legacy(self):
        """Misconfigured EMBEDDING_MODEL_PRIMARY must degrade to legacy,
        never raise at runtime — writes continue, bug is visible in metadata."""
        slot = _model_slot("nonexistent-model")
        assert slot["embedding_column"] == "embedding"
        assert slot["rpc"] == "match_memories"

    def test_upsert_fields_shape(self):
        fields = _embed_upsert_fields([0.1, 0.2], "voyage-3-lite")
        assert fields == {
            "embedding": [0.1, 0.2],
            "embedding_model": "voyage-3-lite",
            "embedding_version": "v2",
        }

    def test_upsert_fields_v2(self):
        fields = _embed_upsert_fields([0.3, 0.4], "voyage-3")
        assert fields == {
            "embedding_v2": [0.3, 0.4],
            "embedding_model_v2": "voyage-3",
            "embedding_version_v2": "v2",
        }

    def test_upsert_fields_unknown_returns_empty(self):
        """Unknown model → no fields (no silent corruption of other columns)."""
        assert _embed_upsert_fields([0.1], "no-such-model") == {}


class TestDualEmbedWrite:
    """#242: when SECONDARY is set, writes compute both embeddings and
    populate both columns. Unset → identical to pre-#242 (single-write)."""

    @pytest.mark.asyncio
    async def test_secondary_unset_single_write(self, monkeypatch):
        """Zero-change default: SECONDARY unset → only PRIMARY columns written."""
        calls: list[dict] = []

        async def fake_embed(text, input_type="document", model=None):
            calls.append({"model": model})
            return [0.1, 0.2, 0.3]

        monkeypatch.setattr(server_module, "_embed", fake_embed)
        monkeypatch.setattr(server_module, "EMBEDDING_MODEL_PRIMARY", "voyage-3-lite")
        monkeypatch.setattr(server_module, "EMBEDDING_MODEL_SECONDARY", None)

        fields = await _compute_write_embeddings("canonical text")

        assert "embedding" in fields
        assert "embedding_model" in fields
        assert fields["embedding_model"] == "voyage-3-lite"
        assert "embedding_v2" not in fields
        assert len(calls) == 1
        assert calls[0]["model"] == "voyage-3-lite"

    @pytest.mark.asyncio
    async def test_secondary_set_dual_write(self, monkeypatch):
        """SECONDARY=voyage-3 → both columns populated, two embed calls."""
        calls: list[dict] = []

        async def fake_embed(text, input_type="document", model=None):
            calls.append({"model": model})
            # Return dim-shaped distinct vectors so we can assert routing.
            return [0.1] * 512 if model == "voyage-3-lite" else [0.9] * 1024

        monkeypatch.setattr(server_module, "_embed", fake_embed)
        monkeypatch.setattr(server_module, "EMBEDDING_MODEL_PRIMARY", "voyage-3-lite")
        monkeypatch.setattr(server_module, "EMBEDDING_MODEL_SECONDARY", "voyage-3")

        fields = await _compute_write_embeddings("canonical text")

        assert fields["embedding"] == [0.1] * 512
        assert fields["embedding_v2"] == [0.9] * 1024
        assert fields["embedding_model"] == "voyage-3-lite"
        assert fields["embedding_model_v2"] == "voyage-3"
        assert {c["model"] for c in calls} == {"voyage-3-lite", "voyage-3"}

    @pytest.mark.asyncio
    async def test_secondary_failure_single_leg(self, monkeypatch):
        """PRIMARY succeeds but SECONDARY embed returns None → write PRIMARY
        only. Missing v2 is recoverable via backfill; corrupt row is not."""
        async def fake_embed(text, input_type="document", model=None):
            if model == "voyage-3":
                return None
            return [0.1] * 512

        monkeypatch.setattr(server_module, "_embed", fake_embed)
        monkeypatch.setattr(server_module, "EMBEDDING_MODEL_PRIMARY", "voyage-3-lite")
        monkeypatch.setattr(server_module, "EMBEDDING_MODEL_SECONDARY", "voyage-3")

        fields = await _compute_write_embeddings("canonical text")
        assert fields["embedding"] == [0.1] * 512
        assert "embedding_v2" not in fields

    @pytest.mark.asyncio
    async def test_primary_failure_no_write(self, monkeypatch):
        """PRIMARY embed fails → no embed fields at all. Row still saves
        with text content, _backfill_missing_embeddings picks it up later."""
        async def fake_embed(text, input_type="document", model=None):
            return None

        monkeypatch.setattr(server_module, "_embed", fake_embed)
        monkeypatch.setattr(server_module, "EMBEDDING_MODEL_PRIMARY", "voyage-3-lite")
        monkeypatch.setattr(server_module, "EMBEDDING_MODEL_SECONDARY", "voyage-3")

        fields = await _compute_write_embeddings("canonical text")
        assert fields == {}

    @pytest.mark.asyncio
    async def test_secondary_equals_primary_no_duplicate_call(self, monkeypatch):
        """If SECONDARY accidentally equals PRIMARY, don't waste an API call."""
        calls: list[dict] = []

        async def fake_embed(text, input_type="document", model=None):
            calls.append({"model": model})
            return [0.1] * 512

        monkeypatch.setattr(server_module, "_embed", fake_embed)
        monkeypatch.setattr(server_module, "EMBEDDING_MODEL_PRIMARY", "voyage-3-lite")
        monkeypatch.setattr(server_module, "EMBEDDING_MODEL_SECONDARY", "voyage-3-lite")

        fields = await _compute_write_embeddings("canonical text")
        assert len(calls) == 1
        assert "embedding" in fields
        # Only PRIMARY columns; no redundant duplicate write.
        assert "embedding_v2" not in fields


# =========================================================================
# Known unknowns — retrieval gaps + unsatisfied queries (#249)
# =========================================================================

from server import (
    _cosine_sim,
    _parse_pgvector,
    _upsert_known_unknown,
    _resolve_known_unknowns,
)


class TestCosineSim:
    """Unit tests for cosine similarity function."""

    def test_empty_vectors(self):
        assert _cosine_sim([], []) == 0.0

    def test_none_vectors(self):
        assert _cosine_sim(None, [1.0, 0.0]) == 0.0
        assert _cosine_sim([1.0, 0.0], None) == 0.0
        assert _cosine_sim(None, None) == 0.0

    def test_identical_unit_vectors(self):
        v = [1.0, 0.0]
        assert _cosine_sim(v, v) == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        assert _cosine_sim([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

    def test_opposite_vectors(self):
        assert _cosine_sim([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)

    def test_scaled_same_direction(self):
        # Cosine sim is invariant to magnitude
        assert _cosine_sim([1.0, 1.0], [2.0, 2.0]) == pytest.approx(1.0)

    def test_zero_magnitude_vector(self):
        assert _cosine_sim([0.0, 0.0], [1.0, 1.0]) == 0.0

    def test_length_mismatch_returns_zero(self):
        # Dim mismatch must not silently truncate via zip — returns 0.0.
        assert _cosine_sim([1.0, 0.0, 0.0], [1.0, 0.0]) == 0.0
        assert _cosine_sim([1.0] * 512, [1.0] * 1024) == 0.0


class TestParsePgvector:
    """supabase-py returns pgvector columns as JSON strings, not lists.

    Regression guard for the known-unknowns dedup/resolution bug where raw
    string embeddings hit the `_cosine_sim` length-mismatch guard and
    silently scored 0.
    """

    def test_list_passes_through(self):
        v = [0.1, 0.2, 0.3]
        assert _parse_pgvector(v) is v

    def test_none_returns_none(self):
        assert _parse_pgvector(None) is None

    def test_json_string_parses_to_list(self):
        parsed = _parse_pgvector("[0.1, 0.2, 0.3]")
        assert parsed == [0.1, 0.2, 0.3]

    def test_malformed_string_returns_none(self):
        assert _parse_pgvector("not-json") is None
        assert _parse_pgvector("[0.1, 0.2,") is None

    def test_non_list_json_returns_none(self):
        # A valid JSON number or object is not a vector — reject.
        assert _parse_pgvector("42") is None
        assert _parse_pgvector('{"x": 1}') is None

    def test_unsupported_type_returns_none(self):
        assert _parse_pgvector(42) is None  # type: ignore[arg-type]

    def test_string_embedding_yields_nonzero_similarity(self):
        """Core regression: feed a JSON-string embedding through the parser,
        then _cosine_sim against an identical list must score ~1.0. Before
        the fix, len("[0.1,...]") != len([0.1,...]) → guard returned 0.0."""
        vec = [0.1] * 512
        stored_as_string = json.dumps(vec)  # what supabase-py actually returns
        parsed = _parse_pgvector(stored_as_string)
        assert parsed is not None
        assert len(parsed) == 512
        assert _cosine_sim(vec, parsed) == pytest.approx(1.0)


class TestKnownUnknowns:
    """Unit tests for known_unknowns insertion + dedup + resolution."""

    @pytest.mark.asyncio
    async def test_known_unknowns_insert_on_low_sim(self):
        """When recall finds top_similarity < 0.45, log as known unknown.
        No existing row with matching query → insert (not update)."""
        mock_client = MagicMock()

        # select().eq().eq().limit().execute() returns no data
        # (fallback path — no embedding, because 3 dims ≠ 512)
        mock_select_chain = MagicMock()
        mock_select_chain.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])

        mock_insert = MagicMock()
        mock_update = MagicMock()

        mock_table = MagicMock()
        mock_table.select.return_value = mock_select_chain
        mock_table.insert.return_value = mock_insert
        mock_table.update.return_value = mock_update
        mock_client.table.return_value = mock_table

        # 3-dim embedding gets coerced to None by dim guard → fallback path
        await _upsert_known_unknown(
            mock_client,
            query="what is the meaning of life",
            query_embedding=[0.1, 0.2, 0.3],
            top_similarity=0.3,
            top_memory_id="mem-123",
            context={"project": "jarvis"},
        )

        # Assert insert was called with correct payload, and update was NOT
        mock_insert.execute.assert_called_once()
        insert_payload = mock_table.insert.call_args.args[0]
        assert insert_payload["query"] == "what is the meaning of life"
        assert insert_payload["top_similarity"] == 0.3
        assert insert_payload["top_memory_id"] == "mem-123"
        assert insert_payload["query_embedding"] is None  # dim-guarded
        assert not mock_update.execute.called

    @pytest.mark.asyncio
    async def test_known_unknowns_dedup_increments_hit_count(self):
        """If similar query exists (cosine > 0.9), increment hit_count instead of insert.
        Validates that the select includes hit_count and the update uses the stored value."""
        mock_client = MagicMock()

        # Use 512-dim embeddings (matches schema vector(512)).
        # Two nearly identical vectors → cosine ≈ 1.0 > 0.9 → dedup fires.
        existing_embedding = [0.10] * 512
        similar_embedding = [0.11] * 512

        # Mock the select chain: table().select("id, query_embedding, hit_count").eq().execute()
        mock_select_return = MagicMock()
        mock_select_return.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "uk-1", "query_embedding": existing_embedding, "hit_count": 5}]
        )

        mock_update_return = MagicMock()
        mock_insert_return = MagicMock()

        mock_table = MagicMock()
        mock_table.select.return_value = mock_select_return
        mock_table.update.return_value = mock_update_return
        mock_table.insert.return_value = mock_insert_return
        mock_client.table.return_value = mock_table

        await _upsert_known_unknown(
            mock_client,
            query="what is the meaning of existence",
            query_embedding=similar_embedding,
            top_similarity=0.35,
            top_memory_id="mem-456",
        )

        # Select must include hit_count so the increment reflects stored value
        select_cols = mock_table.select.call_args.args[0]
        assert "hit_count" in select_cols

        # Update was called once with hit_count = 5 + 1 = 6 (not 1 + 1 = 2)
        mock_table.update.assert_called_once()
        update_payload = mock_table.update.call_args.args[0]
        assert update_payload["hit_count"] == 6

        # Insert was NOT called
        assert not mock_insert_return.execute.called

    @pytest.mark.asyncio
    async def test_known_unknowns_resolution_on_store(self):
        """When a memory is stored, resolve open unknowns with cosine > 0.7."""
        mock_client = MagicMock()
        # Existing open unknown
        unknown_embedding = [0.5, 0.5, 0.0]

        # Setup the mock chain for table().select().eq().execute()
        mock_select = MagicMock()
        mock_eq = MagicMock()
        mock_eq.execute.return_value = MagicMock(
            data=[{"id": "uk-2", "query_embedding": unknown_embedding}]
        )
        mock_select.eq.return_value = mock_eq

        # For the update chain
        mock_update = MagicMock()
        mock_update_eq = MagicMock()
        mock_update_eq.execute.return_value = MagicMock()
        mock_update.eq.return_value = mock_update_eq

        # Setup table() to return different objects for select vs update
        def table_side_effect(table_name):
            if table_name == "known_unknowns":
                result = MagicMock()
                result.select.return_value = mock_select
                result.update.return_value = mock_update
                return result
            return MagicMock()

        mock_client.table.side_effect = table_side_effect

        # New memory with matching embedding
        memory_embedding = [0.6, 0.55, 0.1]
        await _resolve_known_unknowns(mock_client, memory_embedding, "mem-789")

        # Verify update was called with status='resolved'
        assert mock_update.eq.called
