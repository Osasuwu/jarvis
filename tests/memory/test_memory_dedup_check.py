"""Unit tests for scripts/memory-dedup-check.py.

The dedup hook blocks a memory_store when a same-type/same-project memory with a
DIFFERENT name sits above the cosine threshold. That gate must NOT fire on
deliberately-serialized snapshots (the status-record skill writes one row per
UTC date, each ~0.98 similar to the prior day's but with a unique date-keyed
name). These carry `status-snapshot` / `auto-generated` tags and are exempted.

Regression for: status-record cron blocked every day after the first because the
cross-name dup gate treated yesterday's snapshot as a duplicate of today's.

Loads the hook by path because its filename uses a dash.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, call

import pytest

# Stub optional deps so the module imports without a venv present.
for _stub in ("dotenv", "supabase", "httpx"):
    if _stub not in sys.modules:
        try:
            __import__(_stub)
        except ImportError:
            mod = types.ModuleType(_stub)
            if _stub == "dotenv":
                mod.load_dotenv = lambda *a, **k: None
            if _stub == "supabase":
                mod.create_client = lambda *a, **k: MagicMock()
            if _stub == "httpx":
                mod.Client = MagicMock()
            sys.modules[_stub] = mod


_HOOK_PATH = Path(__file__).resolve().parent.parent.parent / "scripts" / "memory-dedup-check.py"
_spec = importlib.util.spec_from_file_location("memory_dedup_check", _HOOK_PATH)
hook = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hook)


# ---------------------------------------------------------------------------
# is_exempt_series — pure predicate
# ---------------------------------------------------------------------------


class TestIsExemptSeries:
    def test_status_snapshot_tag_exempt(self):
        assert hook.is_exempt_series(["status-snapshot", "auto-generated"]) is True

    def test_auto_generated_alone_exempt(self):
        assert hook.is_exempt_series(["auto-generated"]) is True

    def test_ordinary_tags_not_exempt(self):
        assert hook.is_exempt_series(["decision", "architecture"]) is False

    def test_empty_not_exempt(self):
        assert hook.is_exempt_series([]) is False

    def test_none_not_exempt(self):
        assert hook.is_exempt_series(None) is False

    def test_non_list_not_exempt(self):
        # Defensive: a malformed tags value must not crash or falsely exempt.
        assert hook.is_exempt_series("status-snapshot") is False


# ---------------------------------------------------------------------------
# main() — exempt path short-circuits before any network/embedding
# ---------------------------------------------------------------------------


def _run_main(stdin_payload, monkeypatch, embed_fn=None):
    raw = json.dumps(stdin_payload).encode("utf-8")
    fake_stdin = MagicMock()
    fake_stdin.buffer.read.return_value = raw
    monkeypatch.setattr("sys.stdin", fake_stdin)

    buf = io.StringIO()
    monkeypatch.setattr("sys.stdout", buf)

    # Force-fail embedding so that, IF the exempt short-circuit ever regresses,
    # the test still wouldn't reach a real network call — but a block() would
    # require embedding to succeed, so a regression surfaces as exit!=0 below.
    # Callers that need dedup to actually run past the embed step pass embed_fn.
    monkeypatch.setattr(
        hook, "embed", embed_fn or (lambda *a, **k: pytest.fail("embed called for exempt series"))
    )

    exit_code = 0
    try:
        hook.main()
    except SystemExit as e:
        exit_code = int(e.code) if e.code is not None else 0
    return exit_code, buf.getvalue()


class TestMainExemption:
    def test_status_snapshot_store_passes_through(self, monkeypatch):
        code, out = _run_main(
            {
                "tool_name": "mcp__memory__memory_store",
                "tool_input": {
                    "name": "status_snapshot_2026-06-05",
                    "type": "reference",
                    "project": "jarvis",
                    "tags": ["status-snapshot", "auto-generated"],
                    "description": "Status snapshot 2026-06-05",
                    "content": "```yaml\nschema_version: 1\n```",
                },
            },
            monkeypatch,
        )
        # allow() -> exit 0, no deny JSON emitted.
        assert code == 0
        assert out == ""


# ---------------------------------------------------------------------------
# main() — #1184 regressions: upsert short-circuit + session-snapshot exclusion
# ---------------------------------------------------------------------------


def _fake_client(*, existing_row: bool = False, existing_row_error: bool = False, rpc_rows: list[dict]):
    """Build a MagicMock supabase client for the two query chains main() uses.

    Args:
      existing_row: True if row exists (upsert case)
      existing_row_error: True if row_exists query should raise an exception (fallback case)
      rpc_rows: rows returned by match_memories RPC

    - client.table("memories").select("id").eq("name",...).is_("deleted_at","null")
      .eq("project",...).limit(1).execute()   (row_exists check, project truthy branch)
    - client.rpc("match_memories", {...}).execute()
    """
    client = MagicMock()

    row_exists_chain = (
        client.table.return_value.select.return_value.eq.return_value.is_.return_value
    )

    if existing_row_error:
        # Simulate query failure (exception)
        row_exists_chain.eq.return_value.limit.return_value.execute.side_effect = Exception("Query timeout")
    else:
        # Simulate successful query result
        row_exists_chain.eq.return_value.limit.return_value.execute.return_value.data = (
            [{"id": "existing-id"}] if existing_row else []
        )

    client.rpc.return_value.execute.return_value.data = rpc_rows
    return client


class TestMainUpsertShortCircuit:
    def test_existing_project_name_row_skips_dedup_entirely(self, monkeypatch):
        """AC1: memory_store against an existing (project, name) upserts without
        consulting the dedup guard — embed() must never be called."""
        fake_client = _fake_client(existing_row=True, rpc_rows=[])
        monkeypatch.setattr(hook, "create_client", lambda *a, **k: fake_client)
        monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
        monkeypatch.setenv("SUPABASE_KEY", "test-key")

        code, out = _run_main(
            {
                "tool_name": "mcp__memory__memory_store",
                "tool_input": {
                    "name": "working_state_jarvis",
                    "type": "project",
                    "project": "jarvis",
                    "description": "Working state checkpoint",
                    "content": "some working state content",
                },
            },
            monkeypatch,
        )
        assert code == 0
        assert out == ""


class TestMainSessionSnapshotExclusion:
    def test_working_state_store_survives_similar_session_snapshot(self, monkeypatch):
        """AC2/AC3: a highly-similar session_snapshot_<id> row must not block an
        unrelated working_state_<project> store — it's excluded from the dedup
        candidate set the same way it's excluded from memory_recall (#417)."""
        fake_client = _fake_client(
            existing_row=False,
            rpc_rows=[
                {
                    "name": "session_snapshot_6cda4c6f-0000-0000-0000-000000000000",
                    "project": "jarvis",
                    "type": "project",
                    "description": "Session snapshot",
                    "similarity": 0.79,
                    "tags": ["session-snapshot"],
                }
            ],
        )
        monkeypatch.setattr(hook, "create_client", lambda *a, **k: fake_client)
        monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
        monkeypatch.setenv("SUPABASE_KEY", "test-key")

        code, out = _run_main(
            {
                "tool_name": "mcp__memory__memory_store",
                "tool_input": {
                    "name": "working_state_jarvis",
                    "type": "project",
                    "project": "jarvis",
                    "description": "Working state checkpoint",
                    "content": "some working state content",
                },
            },
            monkeypatch,
            embed_fn=lambda *a, **k: [0.1, 0.2, 0.3],
        )
        # allow() -> exit 0, no deny JSON — the snapshot candidate was filtered
        # out before the same-name check, so no candidates remain to block on.
        assert code == 0
        assert out == ""


# ---------------------------------------------------------------------------
# Levenshtein distance — pure predicate
# ---------------------------------------------------------------------------


class TestLevenshteinDistance:
    def test_identical_strings(self):
        assert hook.levenshtein_distance("test", "test") == 0

    def test_empty_string(self):
        assert hook.levenshtein_distance("test", "") == 4
        assert hook.levenshtein_distance("", "test") == 4

    def test_single_character_diff(self):
        # Date variants: 2026-08-11 vs 2026-08-12
        assert hook.levenshtein_distance("status_2026-08-11", "status_2026-08-12") == 1

    def test_multiple_diffs(self):
        assert hook.levenshtein_distance("abc", "def") == 3
        assert hook.levenshtein_distance("kitten", "sitting") == 3


# ---------------------------------------------------------------------------
# is_likely_reupdate — fallback for row_exists failures
# ---------------------------------------------------------------------------


class TestIsLikelyReupdate:
    def test_daily_cron_snapshot_reruns(self):
        """AC1: Extremely high similarity + name variant (date shift) = reupdate."""
        # Daily snapshots score ~0.98, names differ only by date
        assert (
            hook.is_likely_reupdate("status_2026-08-11", "status_2026-08-12", 0.98) is True
        )

    def test_version_variant_reruns(self):
        """AC1: Version-keyed reruns with high similarity = reupdate."""
        assert hook.is_likely_reupdate("memory_v1", "memory_v2", 0.96) is True

    def test_case_insensitive_matching(self):
        """Reupdate detection compares names case-insensitively."""
        assert hook.is_likely_reupdate("Status_Snap", "status_snap", 0.98) is True

    def test_below_reupdate_threshold_blocks(self):
        """Similarity below 0.95 = cross-name duplicate check, not reupdate."""
        assert hook.is_likely_reupdate("status_2026-08-11", "status_2026-08-12", 0.94) is False

    def test_high_similarity_but_distant_names_blocks(self):
        """High similarity but names too different = genuine cross-name collision."""
        # Names differ by much more than 5 chars
        assert (
            hook.is_likely_reupdate("long_memory_description_v1", "short_mem_v2", 0.96) is False
        )

    def test_boundary_edit_distance_5_allows(self):
        """Edit distance exactly 5 is at boundary — allows."""
        # "mem_12345" vs "mem_67890" = 5 chars diff (exactly at boundary)
        assert hook.levenshtein_distance("mem_12345", "mem_67890") == 5
        assert hook.is_likely_reupdate("mem_12345", "mem_67890", 0.95) is True

    def test_boundary_edit_distance_6_blocks(self):
        """Edit distance 6 exceeds threshold — blocks."""
        # "mem_123456" vs "mem_789012" = 6 chars diff (exceeds boundary)
        assert hook.levenshtein_distance("mem_123456", "mem_789012") == 6
        assert hook.is_likely_reupdate("mem_123456", "mem_789012", 0.96) is False


# ---------------------------------------------------------------------------
# main() — #1098 regressions: reupdate detection
# ---------------------------------------------------------------------------


class TestMainReupdateDetection:
    def test_daily_cron_reupdate_allowed_on_query_failure(self, monkeypatch):
        """AC1: Daily-cron memory re-storing with date-variant name + 0.98 similarity
        is allowed as idempotent re-store ONLY when row_exists query fails (not when
        row simply doesn't exist). This is the true fallback case for timing issues."""
        fake_client = _fake_client(
            existing_row_error=True,  # row_exists check fails (timeout/error) → None
            rpc_rows=[
                {
                    "name": "status_snapshot_2026-08-11",
                    "project": "jarvis",
                    "type": "reference",
                    "description": "Status snapshot from 2026-08-11",
                    "similarity": 0.98,  # Near-identical reruns
                    "tags": [],
                }
            ],
        )
        monkeypatch.setattr(hook, "create_client", lambda *a, **k: fake_client)
        monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
        monkeypatch.setenv("SUPABASE_KEY", "test-key")

        code, out = _run_main(
            {
                "tool_name": "mcp__memory__memory_store",
                "tool_input": {
                    "name": "status_snapshot_2026-08-12",  # Different name, same content
                    "type": "reference",
                    "project": "jarvis",
                    "description": "Status snapshot from 2026-08-12",
                    "content": "Status snapshot from yesterday (near-identical)",
                },
            },
            monkeypatch,
            embed_fn=lambda *a, **k: [0.1, 0.2, 0.3],
        )
        # row_exists fails (None), is_likely_reupdate triggers (0.98 > 0.95 + names differ by 1 char)
        # → allow() → exit 0, no deny JSON
        assert code == 0
        assert out == ""

    def test_query_failure_with_non_reupdate_blocks(self, monkeypatch):
        """AC1 extended: Query failure alone does NOT cause allow — only when
        combined with is_likely_reupdate. A dissimilar match should still block."""
        fake_client = _fake_client(
            existing_row_error=True,  # row_exists check fails → None
            rpc_rows=[
                {
                    "name": "session_notes",
                    "project": "jarvis",
                    "type": "decision",
                    "description": "Session decision notes",
                    "similarity": 0.81,  # Above BLOCK_THRESHOLD but below REUPDATE_SIMILARITY_THRESHOLD (0.95)
                    "tags": [],
                }
            ],
        )
        monkeypatch.setattr(hook, "create_client", lambda *a, **k: fake_client)
        monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
        monkeypatch.setenv("SUPABASE_KEY", "test-key")

        code, out = _run_main(
            {
                "tool_name": "mcp__memory__memory_store",
                "tool_input": {
                    "name": "session_decisions",
                    "type": "decision",
                    "project": "jarvis",
                    "description": "Session decision summary",
                    "content": "Different content",
                },
            },
            monkeypatch,
            embed_fn=lambda *a, **k: [0.1, 0.2, 0.3],
        )
        # row_exists fails (None), but similarity 0.81 < 0.95 (REUPDATE_SIMILARITY_THRESHOLD)
        # → is_likely_reupdate returns False → block() is called
        assert code == 2
        assert "Possible duplicate memory" in out

    def test_cross_name_collision_still_blocks(self, monkeypatch):
        """AC2: Genuinely distinct memories with same-type but high similarity still
        get blocked (not allowed by reupdate detection)."""
        fake_client = _fake_client(
            existing_row=False,
            rpc_rows=[
                {
                    "name": "session_notes",
                    "project": "jarvis",
                    "type": "decision",
                    "description": "Session decision notes",
                    "similarity": 0.81,  # Above BLOCK_THRESHOLD (0.80)
                    "tags": [],
                }
            ],
        )
        monkeypatch.setattr(hook, "create_client", lambda *a, **k: fake_client)
        monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
        monkeypatch.setenv("SUPABASE_KEY", "test-key")

        code, out = _run_main(
            {
                "tool_name": "mcp__memory__memory_store",
                "tool_input": {
                    "name": "session_decisions",  # Different name, different content
                    "type": "decision",
                    "project": "jarvis",
                    "description": "Session decision summary",
                    "content": "Similar but genuinely distinct content",
                },
            },
            monkeypatch,
            embed_fn=lambda *a, **k: [0.1, 0.2, 0.3],
        )
        # 0.81 > 0.80 threshold, but not high enough for reupdate (0.95)
        # + names differ by >5 chars → block
        assert code == 2
        assert "Possible duplicate memory" in out
        assert "session_notes" in out

    def test_boundary_threshold_0_80(self, monkeypatch):
        """Verify BLOCK_THRESHOLD is 0.80 and passed to RPC call.
        Similarity 0.79 should pass (above the dup threshold we're fixing).
        Similarity 0.81 is caught at 0.80 threshold."""
        fake_client = _fake_client(
            existing_row=False,
            rpc_rows=[],  # Simulating that RPC finds nothing at 0.80 threshold
        )
        monkeypatch.setattr(hook, "create_client", lambda *a, **k: fake_client)
        monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
        monkeypatch.setenv("SUPABASE_KEY", "test-key")

        code, out = _run_main(
            {
                "tool_name": "mcp__memory__memory_store",
                "tool_input": {
                    "name": "different_memory",
                    "type": "reference",
                    "project": "jarvis",
                    "description": "Different memory",
                    "content": "Distinct concept",
                },
            },
            monkeypatch,
            embed_fn=lambda *a, **k: [0.1, 0.2, 0.3],
        )
        # Verify threshold value
        assert hook.BLOCK_THRESHOLD == 0.80

        # Verify RPC was called with correct threshold
        fake_client.rpc.assert_called_once()
        rpc_call_args = fake_client.rpc.call_args
        assert rpc_call_args[0][0] == "match_memories"
        assert rpc_call_args[0][1]["similarity_threshold"] == 0.80

        # RPC returned empty → no candidates remain → allow()
        assert code == 0
        assert out == ""
