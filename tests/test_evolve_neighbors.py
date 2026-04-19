"""Unit tests for scripts/evolve-neighbors.py — parse + prompt assembly.

The HTTP path (call_haiku) and Supabase fetch paths are exercised in
integration tests or by manual smoke runs; here we cover the deterministic
pieces that don't need network or DB.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

# Stub httpx / supabase / dotenv if not installed so the module import works
# in minimal CI. They're only consulted by the HTTP/DB paths we don't test.
for name in ("httpx", "supabase", "dotenv"):
    try:
        __import__(name)
    except ImportError:
        mod = types.ModuleType(name)
        if name == "supabase":
            mod.create_client = lambda *a, **k: None  # type: ignore[attr-defined]
        if name == "dotenv":
            mod.load_dotenv = lambda *a, **k: None  # type: ignore[attr-defined]
        sys.modules[name] = mod


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "evolve-neighbors.py"

# Hyphen in filename means we can't use normal `import evolve_neighbors`.
spec = importlib.util.spec_from_file_location("evolve_neighbors", SCRIPT_PATH)
assert spec and spec.loader
evo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evo)


# ---------------------------------------------------------------------------
# _truncate
# ---------------------------------------------------------------------------


class TestTruncate:
    def test_short_unchanged(self):
        assert evo._truncate("hello") == "hello"

    def test_empty_string(self):
        assert evo._truncate("") == ""

    def test_none_passthrough(self):
        assert evo._truncate(None) == ""

    def test_truncates_with_ellipsis(self):
        text = "x" * (evo.MAX_CONTENT_CHARS + 100)
        out = evo._truncate(text)
        assert out.endswith("…")
        assert len(out) == evo.MAX_CONTENT_CHARS + 1  # +1 for the ellipsis char


# ---------------------------------------------------------------------------
# _parse_response — Haiku output parsing with defensive downgrades
# ---------------------------------------------------------------------------


class TestParseResponse:
    def test_garbage_returns_none(self):
        assert evo._parse_response("this is not json", {"x"}) is None

    def test_missing_proposals_key_returns_none(self):
        assert evo._parse_response('{"foo": 1}', {"x"}) is None

    def test_empty_proposals_list(self):
        assert evo._parse_response('{"proposals": []}', {"x"}) == []

    def test_valid_update_tags(self):
        text = (
            '{"proposals": [{"neighbor_id": "abc-123", "action": "UPDATE_TAGS", '
            '"new_tags": ["a", "b"], "confidence": 0.88, "reasoning": "tags stale"}]}'
        )
        r = evo._parse_response(text, {"abc-123"})
        assert r is not None
        assert len(r) == 1
        assert r[0]["action"] == "UPDATE_TAGS"
        assert r[0]["new_tags"] == ["a", "b"]
        assert r[0]["new_description"] is None
        assert r[0]["confidence"] == 0.88
        assert r[0]["reasoning"] == "tags stale"

    def test_update_desc_strips_description(self):
        text = (
            '{"proposals": [{"neighbor_id": "abc-123", "action": "UPDATE_DESC", '
            '"new_description": "  a new line.  ", "confidence": 0.8}]}'
        )
        r = evo._parse_response(text, {"abc-123"})
        assert r and r[0]["action"] == "UPDATE_DESC"
        assert r[0]["new_description"] == "a new line."
        assert r[0]["new_tags"] is None

    def test_update_tags_without_tags_downgrades_to_keep(self):
        # Contradictory output: action says update tags but no tags provided.
        text = (
            '{"proposals": [{"neighbor_id": "abc-123", "action": "UPDATE_TAGS", '
            '"new_tags": null, "confidence": 0.7}]}'
        )
        r = evo._parse_response(text, {"abc-123"})
        assert r and r[0]["action"] == "KEEP"
        assert "downgraded" in r[0]["reasoning"]

    def test_update_both_without_desc_downgrades_to_update_tags(self):
        text = (
            '{"proposals": [{"neighbor_id": "abc-123", "action": "UPDATE_BOTH", '
            '"new_tags": ["t1"], "new_description": null, "confidence": 0.9}]}'
        )
        r = evo._parse_response(text, {"abc-123"})
        assert r and r[0]["action"] == "UPDATE_TAGS"
        assert r[0]["new_tags"] == ["t1"]
        assert r[0]["new_description"] is None

    def test_update_both_without_tags_downgrades_to_update_desc(self):
        text = (
            '{"proposals": [{"neighbor_id": "abc-123", "action": "UPDATE_BOTH", '
            '"new_tags": null, "new_description": "d", "confidence": 0.9}]}'
        )
        r = evo._parse_response(text, {"abc-123"})
        assert r and r[0]["action"] == "UPDATE_DESC"
        assert r[0]["new_description"] == "d"

    def test_hallucinated_neighbor_id_dropped(self):
        text = '{"proposals": [{"neighbor_id": "fake-999", "action": "KEEP"}]}'
        r = evo._parse_response(text, {"abc-123"})
        # fake-999 is not in the known set → filter out; nothing left.
        assert r == []

    def test_unknown_action_becomes_keep(self):
        text = (
            '{"proposals": [{"neighbor_id": "abc-123", "action": "DELETE_IT", '
            '"confidence": 0.8}]}'
        )
        r = evo._parse_response(text, {"abc-123"})
        assert r and r[0]["action"] == "KEEP"

    def test_confidence_clamped_to_unit_interval(self):
        text = (
            '{"proposals": [{"neighbor_id": "abc-123", "action": "KEEP", '
            '"confidence": 2.5}]}'
        )
        r = evo._parse_response(text, {"abc-123"})
        assert r and r[0]["confidence"] == 1.0

        text_neg = (
            '{"proposals": [{"neighbor_id": "abc-123", "action": "KEEP", '
            '"confidence": -0.3}]}'
        )
        r = evo._parse_response(text_neg, {"abc-123"})
        assert r and r[0]["confidence"] == 0.0

    def test_tolerates_prose_around_json(self):
        text = (
            "Sure, here's my assessment:\n\n"
            '{"proposals": [{"neighbor_id": "abc-123", "action": "KEEP", '
            '"confidence": 0.9}]}\n\n'
            "Let me know if you need more."
        )
        r = evo._parse_response(text, {"abc-123"})
        assert r and r[0]["action"] == "KEEP"

    def test_non_string_tag_items_reject_all_tags(self):
        # Haiku occasionally emits mixed-type arrays — treat as invalid so we
        # never write partial tag lists.
        text = (
            '{"proposals": [{"neighbor_id": "abc-123", "action": "UPDATE_TAGS", '
            '"new_tags": ["a", 42, null], "confidence": 0.9}]}'
        )
        r = evo._parse_response(text, {"abc-123"})
        assert r and r[0]["action"] == "KEEP"
        assert "downgraded" in r[0]["reasoning"]

    def test_strips_whitespace_tags(self):
        text = (
            '{"proposals": [{"neighbor_id": "abc-123", "action": "UPDATE_TAGS", '
            '"new_tags": ["  tag1  ", "", "tag2"], "confidence": 0.9}]}'
        )
        r = evo._parse_response(text, {"abc-123"})
        assert r and r[0]["action"] == "UPDATE_TAGS"
        assert r[0]["new_tags"] == ["tag1", "tag2"]

    def test_empty_description_downgrades(self):
        text = (
            '{"proposals": [{"neighbor_id": "abc-123", "action": "UPDATE_DESC", '
            '"new_description": "   ", "confidence": 0.7}]}'
        )
        r = evo._parse_response(text, {"abc-123"})
        assert r and r[0]["action"] == "KEEP"

    def test_multiple_proposals_filtered_individually(self):
        text = (
            '{"proposals": ['
            '{"neighbor_id": "a", "action": "KEEP", "confidence": 0.9},'
            '{"neighbor_id": "not-real", "action": "UPDATE_TAGS", "new_tags": ["x"]},'
            '{"neighbor_id": "b", "action": "UPDATE_TAGS", "new_tags": ["y"], "confidence": 0.7}'
            ']}'
        )
        r = evo._parse_response(text, {"a", "b"})
        assert len(r) == 2  # not-real dropped
        by_id = {p["neighbor_id"]: p for p in r}
        assert by_id["a"]["action"] == "KEEP"
        assert by_id["b"]["action"] == "UPDATE_TAGS"


# ---------------------------------------------------------------------------
# _fallback_keep — last-resort safe output when the API fails
# ---------------------------------------------------------------------------


class TestFallbackKeep:
    def test_returns_keep_for_every_neighbor(self):
        neighbors = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
        out = evo._fallback_keep(neighbors, "test-reason")
        assert len(out) == 3
        for p in out:
            assert p["action"] == "KEEP"
            assert p["confidence"] == 0.0
            assert p["new_tags"] is None
            assert p["new_description"] is None
            assert "fallback" in p["reasoning"]
            assert "test-reason" in p["reasoning"]

    def test_empty_input(self):
        assert evo._fallback_keep([], "no-op") == []


# ---------------------------------------------------------------------------
# build_user_message — prompt assembly
# ---------------------------------------------------------------------------


class TestBuildUserMessage:
    def _old(self) -> dict:
        return {
            "id": "old-id",
            "name": "old_memory",
            "type": "decision",
            "tags": ["t1", "t2"],
            "description": "Old description",
            "content": "Old content body",
        }

    def _new(self) -> dict:
        return {
            "id": "new-id",
            "name": "new_memory",
            "type": "decision",
            "tags": ["t3"],
            "description": "New description",
            "content": "New content body",
        }

    def test_includes_both_memories_and_neighbors(self):
        neighbors = [
            {
                "id": "n1",
                "name": "neighbor_one",
                "type": "project",
                "tags": ["t"],
                "description": "Neighbor one",
                "link_type": "related",
            },
            {
                "id": "n2",
                "name": "neighbor_two",
                "type": "reference",
                "tags": [],
                "description": "",
                "link_type": "supersedes",
            },
        ]
        msg = evo.build_user_message(self._old(), self._new(), neighbors)
        assert "OLD_MEMORY" in msg
        assert "NEW_MEMORY" in msg
        assert "old_memory" in msg
        assert "new_memory" in msg
        assert "neighbor_one" in msg
        assert "neighbor_two" in msg
        assert "NEIGHBOR 1" in msg
        assert "NEIGHBOR 2" in msg

    def test_no_neighbors_still_renders_both_sides(self):
        msg = evo.build_user_message(self._old(), self._new(), [])
        assert "OLD_MEMORY" in msg
        assert "NEW_MEMORY" in msg
        assert "NEIGHBOR" not in msg

    def test_truncates_long_content(self):
        long_old = self._old()
        long_old["content"] = "x" * (evo.MAX_CONTENT_CHARS + 500)
        msg = evo.build_user_message(long_old, self._new(), [])
        # Message must contain the ellipsis marker, proving truncation fired
        # before it hit the Haiku prompt.
        assert "…" in msg

    def test_no_tags_rendered_as_none(self):
        neighbors = [
            {"id": "n1", "name": "bare", "type": "project", "tags": [], "description": ""}
        ]
        msg = evo.build_user_message(self._old(), self._new(), neighbors)
        assert "tags: (none)" in msg
