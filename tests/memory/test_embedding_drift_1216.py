"""Unit tests for issue #1216: VoyageAI embedding drift check over eval snapshot vectors.

Cosine-distance fingerprinting between two embedding runs for the same query
set, persisted alongside the recall baseline (AC1), reported independently of
recall metrics (AC2), reusing the canonical _embed_query() call site so no
extra VoyageAI calls are introduced (AC3).
"""

from __future__ import annotations

import asyncio
import importlib.util
import math
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, patch


for _stub in ("dotenv", "supabase"):
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


def _load_module(filename, modname):
    path = Path(__file__).resolve().parent.parent.parent / "scripts" / filename
    spec = importlib.util.spec_from_file_location(modname, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod  # dataclass() needs cls.__module__ in sys.modules
    spec.loader.exec_module(mod)
    return mod


erc = _load_module("eval-recall.py", "eval_recall_1216")


def test_cosine_distance_identical_vectors_is_zero():
    v = [1.0, 2.0, 3.0]
    assert erc._cosine_distance(v, v) == 0.0


def test_cosine_distance_orthogonal_vectors_is_one():
    assert erc._cosine_distance([1.0, 0.0], [0.0, 1.0]) == 1.0


def test_cosine_distance_opposite_vectors_is_two():
    assert erc._cosine_distance([1.0, 0.0], [-1.0, 0.0]) == 2.0


def test_cosine_distance_zero_vector_is_nan():
    assert math.isnan(erc._cosine_distance([0.0, 0.0], [1.0, 0.0]))


def test_fingerprint_sink_calls_embed_query_once_per_query():
    """AC1/AC3: run_query() must not make a second _embed_query() call per
    query beyond the one it already makes for recall() — the fingerprint is
    captured from that same call via fingerprint_sink, not a separate pass."""
    queries = [{"id": "q01", "query": "foo"}, {"id": "q02", "query": "bar"}]
    fake_embed = AsyncMock(side_effect=[[1.0, 0.0], [0.0, 1.0]])
    fake_recall = AsyncMock(return_value=[])

    sink: dict = {}
    with (
        patch.object(erc, "_embed_query", fake_embed),
        patch.object(erc, "recall", fake_recall),
    ):
        for q in queries:
            asyncio.run(erc.run_query(None, q, fingerprint_sink=sink))

    assert fake_embed.await_count == 2
    fake_embed.assert_any_await("foo")
    fake_embed.assert_any_await("bar")
    assert sink == {"q01": [1.0, 0.0], "q02": [0.0, 1.0]}

    # The embedding captured in the sink is the same one passed to recall()
    # via query_embedding= — never a second, independently-computed vector.
    call_embeddings = [call.kwargs["query_embedding"] for call in fake_recall.await_args_list]
    assert call_embeddings == [[1.0, 0.0], [0.0, 1.0]]


def test_print_drift_report_flags_query_over_threshold(capsys):
    current = {"q01": [1.0, 0.0], "q02": [1.0, 0.0]}
    baseline = {"q01": [1.0, 0.0], "q02": [0.0, 1.0]}  # q02 fully drifted

    drifted = erc.print_drift_report(current, baseline, threshold=0.01)

    out = capsys.readouterr().out
    assert drifted == ["q02"]
    assert "q02" in out
    assert "DRIFT" in out


def test_print_drift_report_none_over_threshold(capsys):
    current = {"q01": [1.0, 0.0]}
    baseline = {"q01": [1.0, 0.0]}

    drifted = erc.print_drift_report(current, baseline, threshold=0.01)

    out = capsys.readouterr().out
    assert drifted == []
    assert "no queries" in out.lower()


def test_print_drift_report_missing_baseline_fingerprints_skips_cleanly(capsys):
    drifted = erc.print_drift_report({"q01": [1.0, 0.0]}, None, threshold=0.01)

    out = capsys.readouterr().out
    assert drifted == []
    assert "embedding_fingerprints" in out


def test_russian_queries_covered_with_no_special_casing():
    """AC6: q03/q12/q19 are genuine RU-language queries in queries.yaml; the
    fingerprint pass iterates every query with no language branching, so they
    are covered automatically."""
    import yaml

    queries_path = (
        Path(__file__).resolve().parent.parent.parent / "tests" / "memory-eval" / "queries.yaml"
    )
    with queries_path.open("r", encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    by_id = {q["id"]: q for q in doc["queries"]}

    ru_ids = ["q03", "q12", "q19"]
    for qid in ru_ids:
        assert qid in by_id, f"{qid} missing from queries.yaml"
        assert any(ord(ch) > 0x400 for ch in by_id[qid]["query"]), (
            f"{qid} expected to contain Cyrillic text"
        )

    fake_embed = AsyncMock(return_value=[0.0])
    fake_recall = AsyncMock(return_value=[])
    sink: dict = {}
    with (
        patch.object(erc, "_embed_query", fake_embed),
        patch.object(erc, "recall", fake_recall),
    ):
        for q in doc["queries"]:
            asyncio.run(erc.run_query(None, q, fingerprint_sink=sink))

    for qid in ru_ids:
        assert qid in sink
        fake_embed.assert_any_await(by_id[qid]["query"])


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
