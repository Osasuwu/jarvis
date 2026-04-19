"""Unit tests for scripts/memory-recall-hook.py — parser + RRF merge.

The HTTP paths (`embed`, `rewrite_prompt`) are exercised live in dev and
excluded here. This file covers the deterministic pieces that don't need
network: parsing Haiku's JSON output and the RRF fusion logic.

The module filename uses a dash so importlib is required instead of a
plain import statement.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path


# Stub httpx / dotenv / supabase if not installed — we only test pure
# helpers here, the module-level imports must still succeed.
for _stub in ("httpx", "dotenv", "supabase"):
    if _stub not in sys.modules:
        try:
            __import__(_stub)
        except ImportError:
            mod = types.ModuleType(_stub)
            if _stub == "dotenv":
                mod.load_dotenv = lambda *a, **k: None
            if _stub == "supabase":
                mod.create_client = lambda *a, **k: None
            sys.modules[_stub] = mod


_HOOK_PATH = Path(__file__).resolve().parent.parent / "scripts" / "memory-recall-hook.py"
_spec = importlib.util.spec_from_file_location("memory_recall_hook", _HOOK_PATH)
mrh = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mrh)


# ---------------------------------------------------------------------------
# _parse_rewriter — tolerant JSON extraction
# ---------------------------------------------------------------------------


class TestParseRewriter:
    def test_clean_json(self):
        r = mrh._parse_rewriter('{"entities": ["Phase 3", "RRF"], "types": ["decision"]}')
        assert r == {"entities": ["phase 3", "rrf"], "types": ["decision"]}

    def test_empty_lists_returns_none(self):
        assert mrh._parse_rewriter('{"entities": [], "types": []}') is None

    def test_tolerates_surrounding_prose(self):
        r = mrh._parse_rewriter(
            'Here is the JSON:\n{"entities":["memory_store"],"types":[]}\nDone.'
        )
        assert r == {"entities": ["memory_store"], "types": []}

    def test_filters_invalid_types(self):
        r = mrh._parse_rewriter(
            '{"entities": ["x"], "types": ["garbage", "feedback", "episode"]}'
        )
        # "episode" is not in REWRITER_VALID_TYPES for the hook (Phase 4 wiring
        # is separate); "feedback" survives, "garbage" is dropped.
        assert r == {"entities": ["x"], "types": ["feedback"]}

    def test_no_json_returns_none(self):
        assert mrh._parse_rewriter("just prose") is None

    def test_malformed_json_returns_none(self):
        assert mrh._parse_rewriter("{not json") is None

    def test_caps_entities_at_limit(self):
        entities = [f"e{i}" for i in range(20)]
        import json as _json
        r = mrh._parse_rewriter(_json.dumps({"entities": entities, "types": []}))
        assert r is not None
        assert len(r["entities"]) == mrh.REWRITER_MAX_ENTITIES

    def test_caps_types_at_limit(self):
        # All three valid types — cap is 3, so all should survive.
        r = mrh._parse_rewriter(
            '{"entities": ["x"], "types": ["feedback", "decision", "reference"]}'
        )
        assert r is not None
        assert set(r["types"]) == {"feedback", "decision", "reference"}

    def test_entities_lowercased_and_stripped(self):
        r = mrh._parse_rewriter('{"entities": ["  FooBar  ", "BAZ"], "types": []}')
        assert r == {"entities": ["foobar", "baz"], "types": []}

    def test_drops_empty_entity_strings(self):
        r = mrh._parse_rewriter('{"entities": ["", "   ", "real"], "types": []}')
        assert r == {"entities": ["real"], "types": []}

    def test_non_list_entities_coerced_to_empty(self):
        r = mrh._parse_rewriter('{"entities": "not-a-list", "types": ["feedback"]}')
        assert r == {"entities": [], "types": ["feedback"]}

    def test_empty_string_returns_none(self):
        assert mrh._parse_rewriter("") is None

    def test_valid_non_object_json_array_returns_none(self):
        # Array is valid JSON but the parser is dict-shaped — must not crash.
        assert mrh._parse_rewriter("[]") is None

    def test_valid_non_object_json_null_returns_none(self):
        assert mrh._parse_rewriter("null") is None

    def test_object_wrapping_non_dict_payload_returns_none(self):
        # Pathological: braces matched but content is not a JSON object.
        # The inner `{42}` is invalid JSON → JSONDecodeError → None.
        assert mrh._parse_rewriter("prose {42} trailing") is None


# ---------------------------------------------------------------------------
# rrf_merge — same math as server._rrf_merge, must tag only dual-hit rows
# ---------------------------------------------------------------------------


class TestRrfMerge:
    def test_rrf_score_only_on_dual_hits(self):
        semantic = [{"id": "a", "similarity": 0.9}, {"id": "b", "similarity": 0.8}]
        keyword = [{"id": "b", "rank": 0.5}, {"id": "c", "rank": 0.3}]
        out = mrh.rrf_merge(semantic, keyword)
        by_id = {r["id"]: r for r in out}
        assert "_rrf_score" in by_id["b"]
        assert "_rrf_score" not in by_id["a"]
        assert "_rrf_score" not in by_id["c"]

    def test_preserves_semantic_row_when_duplicated(self):
        # When memory is in both lists, the semantic row wins (keeps similarity).
        semantic = [{"id": "x", "similarity": 0.77}]
        keyword = [{"id": "x", "rank": 0.1}]
        out = mrh.rrf_merge(semantic, keyword)
        assert out[0]["similarity"] == 0.77

    def test_empty_inputs(self):
        assert mrh.rrf_merge([], []) == []

    def test_rows_without_id_skipped(self):
        semantic = [{"similarity": 0.9}]  # no id or name
        keyword = [{"id": "real", "rank": 0.5}]
        out = mrh.rrf_merge(semantic, keyword)
        assert len(out) == 1
        assert out[0]["id"] == "real"

    def test_ordering_reflects_rrf_score(self):
        # Higher-ranked positions in both lists → higher RRF score.
        semantic = [{"id": "top"}, {"id": "mid"}, {"id": "bot"}]
        keyword = [{"id": "top"}, {"id": "mid"}, {"id": "bot"}]
        out = mrh.rrf_merge(semantic, keyword)
        assert [r["id"] for r in out] == ["top", "mid", "bot"]


# ---------------------------------------------------------------------------
# rrf_merge — type boost behavior (Phase 3 soft-boost replaces hard filter)
# ---------------------------------------------------------------------------


class TestRrfMergeBoost:
    def test_boost_none_matches_default(self):
        # boost_types=None must behave identically to the default arg.
        semantic = [{"id": "a", "type": "feedback"}, {"id": "b", "type": "decision"}]
        keyword = []
        out_none = mrh.rrf_merge(semantic, keyword, boost_types=None)
        out_default = mrh.rrf_merge(semantic, keyword)
        assert [r["id"] for r in out_none] == [r["id"] for r in out_default]

    def test_empty_boost_set_treated_as_no_boost(self):
        # Falsy set → boost branch skipped. Verifies `if boost_types:` guard.
        semantic = [{"id": "a", "type": "feedback"}, {"id": "b", "type": "decision"}]
        keyword = []
        out_empty = mrh.rrf_merge(semantic, keyword, boost_types=set())
        out_none = mrh.rrf_merge(semantic, keyword, boost_types=None)
        assert [r["id"] for r in out_empty] == [r["id"] for r in out_none]

    def test_boost_reorders_single_hits(self):
        # `a` at semantic rank 0 (1/60 ≈ 0.01667) beats `b` at rank 1 (1/61 ≈
        # 0.01639) without boost. Boosting `b`'s type (1.5×) flips the order.
        semantic = [{"id": "a", "type": "decision"}, {"id": "b", "type": "feedback"}]
        keyword = []
        out = mrh.rrf_merge(semantic, keyword, boost_types={"feedback"})
        assert [r["id"] for r in out] == ["b", "a"]

    def test_boosted_single_hit_below_unboosted_dual_hit(self):
        # Calibration invariant (see TYPE_BOOST_MULTIPLIER comment):
        # boosted single-hit (1/60 × 1.5 = 0.025) must stay under unboosted
        # dual-hit (2/60 = 0.0333). This guards the 1.5 default against
        # future re-tuning that would break the fusion ordering.
        semantic = [
            {"id": "single", "type": "feedback"},
            {"id": "dual", "type": "decision"},
        ]
        keyword = [{"id": "dual", "type": "decision"}]
        out = mrh.rrf_merge(semantic, keyword, boost_types={"feedback"})
        assert [r["id"] for r in out] == ["dual", "single"]

    def test_non_matching_types_unchanged(self):
        # No row has type="feedback" → boost is a no-op.
        semantic = [{"id": "a", "type": "decision"}, {"id": "b", "type": "reference"}]
        keyword = []
        out = mrh.rrf_merge(semantic, keyword, boost_types={"feedback"})
        assert [r["id"] for r in out] == ["a", "b"]

    def test_sort_score_set_on_boosted_single_hit(self):
        # _sort_score transparency: single-hit rows that got boosted must
        # carry the actual sort key, because their native sim/rank is now
        # out of sync with the display order.
        semantic = [{"id": "a", "type": "feedback"}]
        keyword = []
        out = mrh.rrf_merge(semantic, keyword, boost_types={"feedback"})
        assert "_sort_score" in out[0]
        assert abs(out[0]["_sort_score"] - (1.0 / 60 * mrh.TYPE_BOOST_MULTIPLIER)) < 1e-9

    def test_sort_score_absent_on_unboosted_single_hit(self):
        # Boost active, but row type doesn't match → no _sort_score written.
        # (Native sim/rank still reflects ranking for that row.)
        semantic = [{"id": "a", "type": "decision"}]
        keyword = []
        out = mrh.rrf_merge(semantic, keyword, boost_types={"feedback"})
        assert "_sort_score" not in out[0]

    def test_sort_score_absent_on_boosted_dual_hit(self):
        # Dual-hits use _rrf_score (set after the boost multiply, so the
        # value already reflects the boost). _sort_score is single-hit-only.
        semantic = [{"id": "x", "type": "feedback"}]
        keyword = [{"id": "x", "type": "feedback"}]
        out = mrh.rrf_merge(semantic, keyword, boost_types={"feedback"})
        assert "_sort_score" not in out[0]
        assert "_rrf_score" in out[0]

    def test_custom_multiplier_overrides_default(self):
        # Multiplier large enough (3×) that boosted single-hit now beats
        # unboosted dual-hit — verifies the knob actually reaches the math.
        semantic = [
            {"id": "single", "type": "feedback"},
            {"id": "dual", "type": "decision"},
        ]
        keyword = [{"id": "dual", "type": "decision"}]
        out = mrh.rrf_merge(
            semantic, keyword, boost_types={"feedback"}, boost_multiplier=3.0
        )
        assert [r["id"] for r in out] == ["single", "dual"]


# ---------------------------------------------------------------------------
# detect_project — cwd basename matching
# ---------------------------------------------------------------------------


class TestDetectProject:
    def test_known_project(self):
        assert mrh.detect_project(r"C:\Users\x\GitHub\jarvis") == "jarvis"

    def test_case_insensitive(self):
        assert mrh.detect_project(r"C:\Users\x\GitHub\Jarvis") == "jarvis"

    def test_unknown_project_returns_none(self):
        assert mrh.detect_project(r"C:\Users\x\GitHub\random-repo") is None


# ---------------------------------------------------------------------------
# format_memory — score display falls through correctly
# ---------------------------------------------------------------------------


class TestFormatMemory:
    def test_rrf_score_wins_over_similarity(self):
        m = {"name": "n", "type": "decision", "_rrf_score": 0.42, "similarity": 0.8}
        out = mrh.format_memory(m)
        assert "rrf 0.420" in out
        assert "sim" not in out

    def test_sort_score_displays_boost_over_similarity(self):
        # Boosted single-hit rows: sim is stale vs. ranking, so _sort_score
        # must win the display chain (before sim/rank, after _rrf_score).
        m = {"name": "n", "type": "feedback", "_sort_score": 0.025, "similarity": 0.5}
        out = mrh.format_memory(m)
        assert "boost 0.025" in out
        assert "sim" not in out

    def test_rrf_score_wins_over_sort_score(self):
        # If both fields are somehow set, _rrf_score wins — that's the
        # dual-hit case, and its value already folds in any boost.
        m = {"name": "n", "type": "feedback", "_rrf_score": 0.08, "_sort_score": 0.025}
        out = mrh.format_memory(m)
        assert "rrf 0.080" in out
        assert "boost" not in out

    def test_similarity_fallback(self):
        m = {"name": "n", "type": "decision", "similarity": 0.73}
        out = mrh.format_memory(m)
        assert "sim 0.73" in out

    def test_rank_fallback(self):
        m = {"name": "n", "type": "decision", "rank": 0.25}
        out = mrh.format_memory(m)
        assert "rank 0.25" in out

    def test_no_score_no_parens(self):
        m = {"name": "n", "type": "decision"}
        out = mrh.format_memory(m)
        assert "(decision" in out  # type still rendered
        assert "rrf" not in out and "sim" not in out and "rank" not in out
