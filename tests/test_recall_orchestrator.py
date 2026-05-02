"""Golden test for the recall() orchestrator (#498).

Locks the slice-3 contract: same mocked retrieval rows + same RecallConfig
should produce a stable ranked list of RecallHits with full score-stack
attribution. If a future slice quietly changes pipeline order or scoring,
these three fixed scenarios fail loudly.

The "pre-refactor _hybrid_recall" parity check is implicit: the scenarios are
constructed so the expected ordering is what rrf_merge → enrich →
apply_temporal_scoring produced before the public seam was introduced. The
helpers themselves are unchanged in slice 3 (slice 2 already extracted them);
slice 3 only wired the orchestrator on top.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _iso_days_ago(days: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def _row(
    id: str,
    name: str,
    *,
    similarity: float | None = None,
    rank: float | None = None,
    days_old: float = 1.0,
    mem_type: str = "decision",
    confidence: float = 1.0,
) -> dict:
    """Build a memory row shaped like what match_memories / keyword_search_memories
    return. Confidence is pre-set so enrich_with_confidence skips the table
    lookup; updated_at + last_accessed_at are pinned so apply_temporal_scoring
    is deterministic relative to call time."""
    row: dict = {
        "id": id,
        "name": name,
        "type": mem_type,
        "project": None,
        "tags": [],
        "description": "",
        "content": "",
        "updated_at": _iso_days_ago(days_old),
        "last_accessed_at": _iso_days_ago(days_old),
        "confidence": confidence,
    }
    if similarity is not None:
        row["similarity"] = similarity
    if rank is not None:
        row["rank"] = rank
    return row


def _make_client(sem_rows, kw_rows, linked_rows=None):
    """Mock supabase client routing each RPC name to the right canned data."""
    client = MagicMock()

    def _rpc(name, _args):
        result = MagicMock()
        if name.startswith("match_memories"):
            result.execute.return_value = MagicMock(data=list(sem_rows))
        elif name == "keyword_search_memories":
            result.execute.return_value = MagicMock(data=list(kw_rows))
        elif name == "get_linked_memories":
            result.execute.return_value = MagicMock(data=list(linked_rows or []))
        else:
            result.execute.return_value = MagicMock(data=[])
        return result

    client.rpc.side_effect = _rpc
    # enrich_with_confidence calls client.table("memories").select(...).in_(...).execute().
    # All test rows pre-declare confidence, so no ids reach the SELECT — but the
    # chain still has to resolve to an empty result without raising.
    table = MagicMock()
    table.select.return_value.in_.return_value.execute.return_value = MagicMock(data=[])
    client.table.return_value = table
    return client


# ---------------------------------------------------------------------------
# Golden scenarios
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recall_semantic_only_orders_by_rrf_then_temporal(monkeypatch):
    """Semantic leg only: rrf_merge ranks by 1/(k+rank), temporal scoring
    breaks any ties via recency. Expected order = semantic input order
    when days_old also strictly increases."""
    import server
    from server import recall, PROD_RECALL_CONFIG, RecallHit

    async def _stub_embed(_text):
        return [0.0] * 512

    monkeypatch.setattr(server, "_embed_query", _stub_embed)

    sem = [
        _row("a", "alpha", similarity=0.80, days_old=1),
        _row("b", "bravo", similarity=0.70, days_old=2),
        _row("c", "charlie", similarity=0.60, days_old=3),
    ]
    client = _make_client(sem, kw_rows=[])

    cfg = dataclasses.replace(PROD_RECALL_CONFIG, use_links=False, limit=10)
    hits = await recall(client, "anything", config=cfg)

    assert [h.memory["name"] for h in hits] == ["alpha", "bravo", "charlie"]
    assert all(isinstance(h, RecallHit) for h in hits)
    assert [h.source for h in hits] == ["semantic", "semantic", "semantic"]
    # All five score fields land typed and finite.
    for h in hits:
        assert isinstance(h.semantic_score, float)
        assert isinstance(h.keyword_score, float)
        assert isinstance(h.rrf_score, float)
        assert isinstance(h.temporal_score, float)
        assert isinstance(h.final_score, float)
        assert h.linked_via is None
    # Semantic score round-trips from the input row.
    assert hits[0].semantic_score == pytest.approx(0.80)
    # final_score is monotonic with input order under matching age progression.
    assert hits[0].final_score > hits[1].final_score > hits[2].final_score


@pytest.mark.asyncio
async def test_recall_hybrid_overlap_dual_hit_ranks_first(monkeypatch):
    """Dual-hit (semantic + keyword) gets rrf_merge fusion bonus; downstream
    rank must place that row first regardless of single-leg order. Source
    attribution: dual-hit takes "semantic" (the leg whose row rrf_merge keeps
    for similarity-fallback display)."""
    import server
    from server import recall, PROD_RECALL_CONFIG

    async def _stub_embed(_text):
        return [0.0] * 512

    monkeypatch.setattr(server, "_embed_query", _stub_embed)

    sem = [
        _row("a", "alpha", similarity=0.75, days_old=1),
        _row("b", "bravo", similarity=0.65, days_old=2),
    ]
    kw = [
        _row("a", "alpha", rank=0.50, days_old=1),
        _row("c", "charlie", rank=0.40, days_old=2),
    ]
    client = _make_client(sem, kw)

    cfg = dataclasses.replace(PROD_RECALL_CONFIG, use_links=False, limit=10)
    hits = await recall(client, "anything", config=cfg)

    names = [h.memory["name"] for h in hits]
    sources = {h.memory["name"]: h.source for h in hits}

    # alpha appears in both legs — fusion bonus puts it on top.
    assert names[0] == "alpha"
    assert sources["alpha"] == "semantic"
    assert sources["bravo"] == "semantic"
    assert sources["charlie"] == "keyword"
    assert set(names) == {"alpha", "bravo", "charlie"}
    # Dual-hit rrf_score must exceed any single-hit rrf_score in the result.
    alpha_hit = next(h for h in hits if h.memory["name"] == "alpha")
    other_rrfs = [h.rrf_score for h in hits if h.memory["name"] != "alpha"]
    assert alpha_hit.rrf_score > max(other_rrfs)


@pytest.mark.asyncio
async def test_recall_with_links_attributes_linked_source(monkeypatch):
    """use_links=True wires expand_links → merge_with_links into the rank.
    Pure-link rows (parent in seed window, not in either retrieval leg)
    surface with source="linked" and linked_via pointing at the parent UUID."""
    import server
    from server import recall, PROD_RECALL_CONFIG

    async def _stub_embed(_text):
        return [0.0] * 512

    monkeypatch.setattr(server, "_embed_query", _stub_embed)

    sem = [
        _row("a", "alpha", similarity=0.80, days_old=1),
        _row("b", "bravo", similarity=0.70, days_old=2),
    ]
    # Linked row: get_linked_memories returns rows tagged with linked_from
    # (the seed id) and link_strength.
    linked = [
        {
            **_row("z", "zulu_linked", days_old=1),
            "linked_from": "a",
            "link_type": "related",
            "link_strength": 0.9,
        }
    ]
    client = _make_client(sem, kw_rows=[], linked_rows=linked)

    cfg = dataclasses.replace(PROD_RECALL_CONFIG, use_links=True, limit=10)
    hits = await recall(client, "anything", config=cfg)

    by_name = {h.memory["name"]: h for h in hits}
    assert "alpha" in by_name and "bravo" in by_name and "zulu_linked" in by_name
    assert by_name["alpha"].source == "semantic"
    assert by_name["bravo"].source == "semantic"
    assert by_name["zulu_linked"].source == "linked"
    assert by_name["zulu_linked"].linked_via == "a"
    # rrf_score on the linked hit reflects merge_with_links's score, not 0.
    assert by_name["zulu_linked"].rrf_score > 0


# ---------------------------------------------------------------------------
# Surface-area sanity: RecallConfig is frozen, replace works, defaults match
# the issue spec (#498 acceptance criteria).
# ---------------------------------------------------------------------------


def test_recall_config_is_frozen_and_replaceable():
    from server import RecallConfig, PROD_RECALL_CONFIG

    cfg = RecallConfig()
    with pytest.raises(dataclasses.FrozenInstanceError):
        cfg.use_links = False  # type: ignore[misc]

    flipped = dataclasses.replace(PROD_RECALL_CONFIG, use_links=False, limit=3)
    assert flipped.use_links is False
    assert flipped.limit == 3
    # Original unchanged.
    assert PROD_RECALL_CONFIG.use_links is True
    assert PROD_RECALL_CONFIG.limit == 10


def test_prod_recall_config_all_on_defaults():
    from server import PROD_RECALL_CONFIG

    assert PROD_RECALL_CONFIG.use_rewriter is True
    assert PROD_RECALL_CONFIG.use_links is True
    assert PROD_RECALL_CONFIG.use_classifier is True
    assert PROD_RECALL_CONFIG.use_temporal is True
