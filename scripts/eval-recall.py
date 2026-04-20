"""Memory recall evaluation harness.

Runs the query set in tests/memory-eval/queries.yaml against the live Supabase
corpus, reproduces the server.py recall pipeline (pgvector match_memories +
pg_trgm keyword_search_memories + RRF + temporal scoring), and reports:

    - recall@5, recall@10:  fraction of queries where >=1 expected name is in top-k
    - MRR:                  mean reciprocal rank of the first expected hit
    - must_not violations:  queries where a "should not surface" memory landed
                            in top 5 (tracked separately — this is the lifecycle
                            signal we want to drive to zero)

Usage:
    python scripts/eval-recall.py                 # run, pretty-print, don't save
    python scripts/eval-recall.py --save-baseline # run + overwrite baseline.json
    python scripts/eval-recall.py --diff baseline # run + print delta vs baseline.json
    python scripts/eval-recall.py --quiet         # only print aggregates

No dependency on mcp-memory/server.py: we duplicate the pipeline constants here
so Phase-by-phase server.py changes are measurable as deltas against the
previous baseline. Keep this file's constants in sync with server.py OR, when
pipeline diverges intentionally, the delta in eval output *is* the thing we
wanted to measure.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import math
import os
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

# ---------------------------------------------------------------------------
# Pipeline constants — mirrored from mcp-memory/server.py as of Phase 1.
# When server.py changes, re-sync OR deliberately let them differ to measure.
# ---------------------------------------------------------------------------
SIMILARITY_THRESHOLD = 0.25
RRF_K = 60
# TYPE_BOOST_MULTIPLIER intentionally not duplicated here. When --with-rewriter
# is enabled, we load scripts/memory-recall-hook.py and read its constant,
# so re-tuning the boost only needs to happen in one place.
TEMPORAL_HALF_LIVES = {
    "user": 180,
    "feedback": 90,
    "decision": 60,
    "reference": 30,
    "project": 7,
}
DEFAULT_HALF_LIFE = 30
ACCESS_BOOST_MAX = 0.3
ACCESS_HALF_LIFE = 14
CONFIDENCE_FLOOR = 0.5  # Multiplier floor: score * (floor + (1-floor) * confidence)

VOYAGE_URL = "https://api.voyageai.com/v1/embeddings"
VOYAGE_MODEL = "voyage-3-lite"
EMBED_TIMEOUT = 10.0


def _load_hook_module():
    """Load scripts/memory-recall-hook.py as a module via importlib.

    Hyphen in the hook filename blocks normal imports. Returning the whole
    module lets callers pull both `rewrite_prompt` and `TYPE_BOOST_MULTIPLIER`
    from the same source — eval and hook stay in lockstep when the boost is
    re-tuned. Returns None if the file is missing or import fails.
    """
    here = Path(__file__).resolve().parent
    hook_path = here / "memory-recall-hook.py"
    if not hook_path.exists():
        return None
    try:
        spec = importlib.util.spec_from_file_location("memory_recall_hook", hook_path)
        if spec is None or spec.loader is None:
            return None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception as e:
        print(f"WARN: failed to load hook module: {e}", file=sys.stderr)
        return None


def _load_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    here = Path(__file__).resolve().parent
    for candidate in (here.parent / ".env", here.parent.parent / ".env"):
        if candidate.exists():
            load_dotenv(candidate)
            return


async def _embed_query(text: str) -> list[float]:
    """Sync-in-async Voyage embed. Raises on error — eval should fail loud, not open."""
    import httpx

    api_key = os.environ["VOYAGE_API_KEY"]
    async with httpx.AsyncClient(timeout=EMBED_TIMEOUT) as client:
        resp = await client.post(
            VOYAGE_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": VOYAGE_MODEL,
                "input": [text],
                "input_type": "query",
            },
        )
        resp.raise_for_status()
        return resp.json()["data"][0]["embedding"]


def _rrf_merge(
    semantic_rows: list[dict],
    keyword_rows: list[dict],
    limit: int,
    k: int = RRF_K,
    boost_types: set[str] | None = None,
    boost_multiplier: float = 1.0,
) -> list[dict]:
    scores: dict[str, float] = {}
    by_id: dict[str, dict] = {}
    for rank, row in enumerate(semantic_rows):
        rid = row.get("id") or row["name"]
        scores[rid] = scores.get(rid, 0.0) + 1.0 / (k + rank)
        by_id[rid] = row
    for rank, row in enumerate(keyword_rows):
        rid = row.get("id") or row["name"]
        scores[rid] = scores.get(rid, 0.0) + 1.0 / (k + rank)
        by_id[rid] = row
    if boost_types:
        for rid, row in by_id.items():
            if row.get("type") in boost_types:
                scores[rid] *= boost_multiplier
    ranked = sorted(scores.keys(), key=lambda r: scores[r], reverse=True)
    result = []
    for rid in ranked[:limit]:
        row = by_id[rid]
        row["_rrf_score"] = scores[rid]
        # _final_score is the unified sort key carried through any
        # downstream merge step (e.g. link expansion in --with-links).
        row["_final_score"] = scores[rid]
        result.append(row)
    return result


# 1-hop BFS link expansion. Mirrors memory-recall-hook.py constants/logic
# so eval predicts hook behavior. When both are enabled (--with-rewriter
# --with-links) the combined mode measures the full Phase 3 pipeline.
LINK_EXPAND_TOP_K = 5
LINK_DECAY = 0.5
LINK_SCORE_FIELD = "_link_score"


def _score_linked_rows(
    top_rows: list[dict],
    linked_rows: list[dict],
    *,
    top_k: int = LINK_EXPAND_TOP_K,
    decay: float = LINK_DECAY,
    k: int = RRF_K,
) -> list[dict]:
    if not top_rows or not linked_rows:
        return []
    seed_rank: dict[str, int] = {}
    for i, row in enumerate(top_rows[:top_k]):
        rid = row.get("id")
        if rid is not None and rid not in seed_rank:
            seed_rank[rid] = i
    if not seed_rank:
        return []
    seen: set[str] = set(seed_rank.keys())
    out: list[dict] = []
    for row in linked_rows:
        rid = row.get("id")
        if not rid or rid in seen:
            continue
        parent = row.get("linked_from")
        if parent not in seed_rank:
            continue
        seen.add(rid)
        strength = row.get("link_strength")
        try:
            strength_f = float(strength) if strength is not None else 1.0
        except (TypeError, ValueError):
            strength_f = 1.0
        parent_rank = seed_rank[parent]
        row[LINK_SCORE_FIELD] = (1.0 / (k + parent_rank)) * decay * strength_f
        out.append(row)
    return out


async def _load_session_context(client) -> tuple[list[dict], int]:
    """Load session-start context like session-context.py does.

    Returns (context_items, total_char_count) where context_items is a list
    of dicts with 'id', 'name', 'type', 'project', 'description', 'content'.
    Char count includes formatted markdown output for budget estimation.
    """
    items: list[dict] = []
    char_count = 0

    # 1. User memories (top 2)
    try:
        result = (
            client.table("memories")
            .select("id, name, type, project, description, content, tags, updated_at")
            .eq("type", "user")
            .order("updated_at", desc=True)
            .limit(2)
            .execute()
        )
        if result.data:
            items.extend(result.data)
            for m in result.data:
                char_count += (
                    len(m.get("name", ""))
                    + len(m.get("description", ""))
                    + len(m.get("content", ""))
                )
    except Exception:
        pass

    # 2. Always-load memories (evergreen rules)
    try:
        result = (
            client.table("memories")
            .select("id, name, type, project, description, content, tags, updated_at")
            .contains("tags", ["always_load"])
            .order("updated_at", desc=True)
            .execute()
        )
        if result.data:
            items.extend(result.data)
            for m in result.data:
                char_count += (
                    len(m.get("name", ""))
                    + len(m.get("description", ""))
                    + len(m.get("content", ""))
                )
    except Exception:
        pass

    # 3. Working state (if available; we don't know project in eval, skip)
    # Not critical for measurement

    # 4. Active goals
    try:
        result = (
            client.table("goals")
            .select("*")
            .eq("status", "active")
            .order("priority")
            .order("deadline", desc=False, nullsfirst=False)
            .execute()
        )
        if result.data:
            for g in result.data:
                items.append(
                    {
                        "id": g.get("id"),
                        "name": g.get("title", ""),
                        "type": "goal",
                        "project": g.get("project"),
                        "description": g.get("slug"),
                        "content": g.get("why", ""),
                    }
                )
                char_count += len(g.get("title", "")) + len(g.get("why", ""))
    except Exception:
        pass

    # Count items by type
    item_counts: dict[str, int] = {}
    for item in items:
        item_type = item.get("type", "unknown")
        item_counts[item_type] = item_counts.get(item_type, 0) + 1

    return items, char_count, item_counts


def _expand_links(client, top_rows: list[dict]) -> list[dict]:
    seed_ids = [r["id"] for r in top_rows[:LINK_EXPAND_TOP_K] if r.get("id")]
    if not seed_ids:
        return []
    try:
        result = client.rpc(
            "get_linked_memories",
            {"memory_ids": seed_ids, "link_types": None, "show_history": False},
        ).execute()
        linked_rows = result.data or []
    except Exception:
        return []
    return _score_linked_rows(top_rows, linked_rows)


def _merge_with_links(ranked_rows: list[dict], linked_rows: list[dict]) -> list[dict]:
    if not linked_rows:
        return ranked_rows
    by_id: dict[str, dict] = {}
    scores: dict[str, float] = {}
    for row in ranked_rows:
        rid = row.get("id")
        if not rid:
            continue
        by_id[rid] = row
        scores[rid] = float(row.get("_final_score") or 0.0)
    for row in linked_rows:
        rid = row.get("id")
        if not rid:
            continue
        link_s = float(row.get(LINK_SCORE_FIELD) or 0.0)
        if rid in scores:
            scores[rid] = max(scores[rid], link_s)
        else:
            by_id[rid] = row
            scores[rid] = link_s
    final_ids = sorted(scores.keys(), key=lambda r: scores[r], reverse=True)
    out: list[dict] = []
    for rid in final_ids:
        row = by_id[rid]
        row["_final_score"] = scores[rid]
        out.append(row)
    return out


def _apply_temporal_scoring(rows: list[dict]) -> list[dict]:
    """Mirror of mcp-memory/server.py _apply_temporal_scoring with confidence multiplier."""
    now = datetime.now(timezone.utc)
    for row in rows:
        rrf = row.get("_rrf_score", 0.01)
        mem_type = row.get("type", "decision")
        half_life = TEMPORAL_HALF_LIVES.get(mem_type, DEFAULT_HALF_LIFE)

        # Phase 1: decay is driven by content_updated_at (content changes),
        # not updated_at (which gets bumped by every recall's touch_memories).
        # Fall back to updated_at for rows without backfilled content_updated_at.
        updated_str = row.get("content_updated_at") or row.get("updated_at") or ""
        try:
            updated = datetime.fromisoformat(updated_str.replace("Z", "+00:00"))
            days_since_update = max(0, (now - updated).total_seconds() / 86400)
        except (ValueError, AttributeError):
            days_since_update = half_life

        accessed_str = row.get("last_accessed_at") or ""
        try:
            accessed = datetime.fromisoformat(accessed_str.replace("Z", "+00:00"))
            days_since_access = max(0, (now - accessed).total_seconds() / 86400)
        except (ValueError, AttributeError):
            days_since_access = days_since_update * 2

        recency = math.exp(-0.693 * days_since_update / half_life)
        access = 1.0 + ACCESS_BOOST_MAX * math.exp(-0.693 * days_since_access / ACCESS_HALF_LIFE)

        # Confidence multiplier: (CONFIDENCE_FLOOR + (1-CONFIDENCE_FLOOR) * confidence)
        # NULL confidence → 1.0 (legacy memories don't regress)
        confidence = row.get("confidence")
        if confidence is None:
            confidence_mult = 1.0
        else:
            confidence_mult = CONFIDENCE_FLOOR + (1.0 - CONFIDENCE_FLOOR) * confidence

        row["_temporal_score"] = rrf * recency * access * confidence_mult

    rows.sort(key=lambda r: r.get("_temporal_score", 0), reverse=True)
    return rows


# ---------------------------------------------------------------------------
# Eval core
# ---------------------------------------------------------------------------


@dataclass
class QueryResult:
    id: str
    query: str
    kind: str
    expected: list[str]
    must_not: list[str]
    top_names: list[str]  # top-10 names in order
    first_hit_rank: int | None  # 1-indexed, None if no expected hit in top-10
    hits_at_5: list[str]  # expected names that appeared in top-5
    hits_at_10: list[str]
    must_not_violations_at_5: list[str]  # must_not names that appeared in top-5
    passed: bool  # recall@5 >= 1 AND no must_not violations
    rewriter_entities: list[str] = field(default_factory=list)
    rewriter_types: list[str] = field(default_factory=list)
    rewriter_fired: bool = False  # True when rewriter returned a non-null result
    links_added: int = 0  # new rows added via 1-hop BFS
    # Context rot measurement (--with-session-context mode)
    context_delta_at_5: float = (
        0.0  # plain recall@5 - (with context) recall@5, in percentage points
    )
    context_top_names: list[str] = field(default_factory=list)  # top-10 names with context injected
    context_hits_at_5: list[str] = field(default_factory=list)  # hits with context


@dataclass
class EvalReport:
    timestamp: str
    mode: str  # e.g. "server_only", "with_rewriter+links"
    corpus_size: int
    total_queries: int
    recall_at_5: float
    recall_at_10: float
    mrr: float
    must_not_violations: int
    passed: int
    failed: int
    rewriter_fired_count: int = 0  # queries where rewriter produced output
    links_added_total: int = 0  # total new rows pulled in via link expansion
    results: list[dict] = field(default_factory=list)
    # Context rot measurement (--with-session-context mode)
    context_aggregate_delta: float = 0.0  # mean context_delta_at_5 across all queries, in pp
    context_budget_chars: int = 0  # total characters in injected context
    context_budget_tokens: int = 0  # estimated tokens (chars/4)
    context_budget_items: dict = field(default_factory=dict)  # item counts by type


def _build_mode_string(with_rewriter: bool, with_links: bool) -> str:
    parts: list[str] = []
    if with_rewriter:
        parts.append("with_rewriter")
    if with_links:
        parts.append("links")
    return "+".join(parts) if parts else "server_only"


async def run_query(
    client,
    q: dict,
    rewriter: Callable[[str], dict | None] | None = None,
    boost_multiplier: float = 1.0,
    with_links: bool = False,
    context_items: list[dict] | None = None,
) -> QueryResult:
    embedding = await _embed_query(q["query"])

    # Phase 3: if a rewriter is supplied, use it to denoise the keyword leg
    # (entities substitute for the raw prompt) and optionally narrow types.
    # Matches the hook contract: entities-only → kw query substitution, types
    # list → Python-side filter on BOTH semantic and keyword rows before RRF.
    rw_entities: list[str] = []
    rw_types: list[str] = []
    rw_fired = False
    if rewriter is not None:
        rw = rewriter(q["query"])
        if rw:
            rw_fired = True
            rw_entities = list(rw.get("entities") or [])
            rw_types = list(rw.get("types") or [])

    keyword_query = " ".join(rw_entities) if rw_entities else q["query"]

    sem = client.rpc(
        "match_memories",
        {
            "query_embedding": embedding,
            "match_limit": 20,
            "similarity_threshold": SIMILARITY_THRESHOLD,
            "filter_project": None,
            "filter_type": None,
            "show_history": False,
        },
    ).execute()
    sem_rows = sem.data or []

    kw = client.rpc(
        "keyword_search_memories",
        {
            "search_query": keyword_query,
            "match_limit": 20,
            "filter_project": None,
            "filter_type": None,
            "show_history": False,
        },
    ).execute()
    kw_rows = kw.data or []

    # Rewriter types → soft boost (matches hook behavior after the
    # type-narrowing regression fix). No default scope filter — eval
    # doesn't model the hook's exclusion of user/project memories.
    boost_types = set(rw_types) if rw_types else None
    # Pull a wider window (25) when link expansion is on so the BFS can
    # reach the right seeds. Without this, top-5 seeds miss the parents
    # that edge toward the expected memory.
    merge_limit = 25 if with_links else 10
    merged = _rrf_merge(
        sem_rows,
        kw_rows,
        limit=merge_limit,
        boost_types=boost_types,
        boost_multiplier=boost_multiplier,
    )

    links_added = 0
    if with_links:
        linked = _expand_links(client, merged)
        if linked:
            before_ids = {r.get("id") for r in merged}
            merged = _merge_with_links(merged, linked)
            links_added = sum(1 for r in merged if r.get("id") and r.get("id") not in before_ids)
        # Trim back to top-10 for metrics; any linked row that made it
        # into top-10 has earned its place via the unified _final_score.
        merged = merged[:10]

    _apply_temporal_scoring(merged)

    top_names = [r.get("name", "?") for r in merged]
    expected = set(q.get("expected") or [])
    must_not = set(q.get("must_not") or [])

    top5 = top_names[:5]
    top10 = top_names[:10]
    hits_5 = [n for n in top5 if n in expected]
    hits_10 = [n for n in top10 if n in expected]
    mn_viol = [n for n in top5 if n in must_not]

    first_hit_rank = None
    for i, name in enumerate(top10, start=1):
        if name in expected:
            first_hit_rank = i
            break

    passed = bool(hits_5) and not mn_viol

    # Context rot measurement: if context_items provided, run recall again
    # with context injected into keyword search (simulates hook adding noise)
    context_delta = 0.0
    context_top_names: list[str] = []
    context_hits_5: list[str] = []
    if context_items:
        # Inject context into keyword search: append context item names to query
        context_names = " ".join(item.get("name", "") for item in context_items if item.get("name"))
        context_keyword_query = f"{keyword_query} {context_names}".strip()
        # Re-run keyword search with injected context
        kw_ctx = client.rpc(
            "keyword_search_memories",
            {
                "search_query": context_keyword_query,
                "match_limit": 20,
                "filter_project": None,
                "filter_type": None,
                "show_history": False,
            },
        ).execute()
        kw_ctx_rows = kw_ctx.data or []
        # Re-merge with context-augmented keyword rows
        merged_ctx = _rrf_merge(
            sem_rows,
            kw_ctx_rows,
            limit=merge_limit,
            boost_types=boost_types,
            boost_multiplier=boost_multiplier,
        )
        if with_links:
            linked_ctx = _expand_links(client, merged_ctx)
            if linked_ctx:
                merged_ctx = _merge_with_links(merged_ctx, linked_ctx)
            merged_ctx = merged_ctx[:10]
        _apply_temporal_scoring(merged_ctx)
        context_top_names = [r.get("name", "?") for r in merged_ctx]
        context_top5 = context_top_names[:5]
        context_hits_5 = [n for n in context_top5 if n in expected]
        # Compute delta: plain recall@5 vs with_context recall@5
        plain_recall_5 = 1.0 if hits_5 else 0.0
        context_recall_5 = 1.0 if context_hits_5 else 0.0
        context_delta = (plain_recall_5 - context_recall_5) * 100.0  # in percentage points

    return QueryResult(
        id=q["id"],
        query=q["query"],
        kind=q.get("kind", ""),
        expected=sorted(expected),
        must_not=sorted(must_not),
        top_names=top_names,
        first_hit_rank=first_hit_rank,
        hits_at_5=hits_5,
        hits_at_10=hits_10,
        must_not_violations_at_5=mn_viol,
        passed=passed,
        rewriter_entities=rw_entities,
        rewriter_types=rw_types,
        rewriter_fired=rw_fired,
        links_added=links_added,
        context_delta_at_5=context_delta,
        context_top_names=context_top_names,
        context_hits_at_5=context_hits_5,
    )


async def run_all(
    queries: list[dict],
    client,
    rewriter: Callable[[str], dict | None] | None = None,
    boost_multiplier: float = 1.0,
    with_links: bool = False,
    context_items: list[dict] | None = None,
) -> EvalReport:
    results = []
    for q in queries:
        r = await run_query(
            client,
            q,
            rewriter=rewriter,
            boost_multiplier=boost_multiplier,
            with_links=with_links,
            context_items=context_items,
        )
        results.append(r)

    total = len(results)
    r5 = sum(1 for r in results if r.hits_at_5) / total if total else 0.0
    r10 = sum(1 for r in results if r.hits_at_10) / total if total else 0.0
    mrr = sum(1.0 / r.first_hit_rank for r in results if r.first_hit_rank) / total if total else 0.0
    mn_viol = sum(1 for r in results if r.must_not_violations_at_5)
    passed = sum(1 for r in results if r.passed)
    rw_fired = sum(1 for r in results if r.rewriter_fired)
    links_added_total = sum(r.links_added for r in results)

    # corpus size for context
    cs = (
        client.table("memories")
        .select("id", count="exact")
        .is_("deleted_at", "null")
        .limit(1)
        .execute()
    )
    corpus_size = cs.count or 0

    # Context rot aggregates
    context_agg_delta = 0.0
    context_budget_chars = 0
    context_budget_items: dict[str, int] = {}
    if context_items:
        context_agg_delta = sum(r.context_delta_at_5 for r in results) / total if total else 0.0
        context_budget_chars = sum(
            len(item.get("name", ""))
            + len(item.get("description", ""))
            + len(item.get("content", ""))
            for item in context_items
        )
        for item in context_items:
            item_type = item.get("type", "unknown")
            context_budget_items[item_type] = context_budget_items.get(item_type, 0) + 1

    return EvalReport(
        timestamp=datetime.now(timezone.utc).isoformat(),
        mode=_build_mode_string(rewriter is not None, with_links),
        corpus_size=corpus_size,
        total_queries=total,
        recall_at_5=r5,
        recall_at_10=r10,
        mrr=mrr,
        must_not_violations=mn_viol,
        passed=passed,
        failed=total - passed,
        rewriter_fired_count=rw_fired,
        links_added_total=links_added_total,
        results=[asdict(r) for r in results],
        context_aggregate_delta=context_agg_delta,
        context_budget_chars=context_budget_chars,
        context_budget_tokens=max(1, context_budget_chars // 4),  # estimate: chars/4
        context_budget_items=context_budget_items,
    )


# ---------------------------------------------------------------------------
# Formatting / CLI
# ---------------------------------------------------------------------------


def _fmt_pct(x: float) -> str:
    return f"{x * 100:5.1f}%"


def print_report(report: EvalReport, quiet: bool = False) -> None:
    if not quiet:
        print(
            f"\nQueries: {report.total_queries}   Corpus: {report.corpus_size} memories   Mode: {report.mode}\n"
        )
        print(f"{'id':<5} {'kind':<10} {'rank':>5}  {'hit5':>5}  {'viol':>5}  {'rw':>3}  query")
        print("-" * 100)
        for r in report.results:
            rank_s = str(r["first_hit_rank"]) if r["first_hit_rank"] else "-"
            hit = "Y" if r["hits_at_5"] else " "
            viol = "!" if r["must_not_violations_at_5"] else " "
            rw = "*" if r.get("rewriter_fired") else " "
            q = r["query"] if len(r["query"]) <= 60 else r["query"][:57] + "..."
            print(f"{r['id']:<5} {r['kind']:<10} {rank_s:>5}  {hit:>5}  {viol:>5}  {rw:>3}  {q}")

        # fail details
        fails = [r for r in report.results if not r["passed"]]
        if fails:
            print("\nFAILED queries (recall@5 miss or must_not violation):")
            for r in fails:
                print(f"\n  [{r['id']}] {r['query']}")
                print(f"    expected:  {r['expected']}")
                if r["must_not"]:
                    print(f"    must_not:  {r['must_not']}")
                print(f"    top-5:     {r['top_names'][:5]}")
                if r["must_not_violations_at_5"]:
                    print(f"    violated:  {r['must_not_violations_at_5']}")
                if r.get("rewriter_fired"):
                    print(
                        f"    rewriter:  entities={r.get('rewriter_entities') or []} types={r.get('rewriter_types') or []}"
                    )

    print("\n=== AGGREGATES ===")
    print(f"mode               : {report.mode}")
    print(
        f"recall@5           : {_fmt_pct(report.recall_at_5)}  ({report.passed}/{report.total_queries} queries retrieved at least one expected memory in top-5)"
    )
    print(f"recall@10          : {_fmt_pct(report.recall_at_10)}")
    print(f"MRR                : {report.mrr:.3f}")
    print(
        f"must_not violations: {report.must_not_violations}  (lifecycle signal — should be 0 after Phase 1)"
    )
    print(f"passed / failed    : {report.passed} / {report.failed}")
    if "with_rewriter" in report.mode:
        print(f"rewriter fired     : {report.rewriter_fired_count}/{report.total_queries}")
    if "links" in report.mode:
        print(f"links added (sum)  : {report.links_added_total}  (rows added via 1-hop BFS)")
    # Context rot metrics
    if report.context_budget_chars > 0:
        print("\nCONTEXT ROT MEASUREMENT")
        print(
            f"aggregate delta    : {report.context_aggregate_delta:+.2f} pp  (plain recall@5 - with_context recall@5)"
        )
        if report.context_aggregate_delta < -5.0:
            interpretation = "context ROT CONFIRMED (negative impact)"
        elif report.context_aggregate_delta > 5.0:
            interpretation = "context HELPS (positive impact)"
        else:
            interpretation = "context roughly NEUTRAL"
        print(f"  interpretation   : {interpretation}")
        print(
            f"context budget     : {report.context_budget_tokens} tokens (~{report.context_budget_chars} chars)"
        )
        print(f"context items      : {report.context_budget_items}")
    print()


def print_diff(current: EvalReport, baseline: dict) -> None:
    def delta(k: str) -> str:
        cur = getattr(current, k)
        base = baseline.get(k, 0)
        d = cur - base
        sign = "+" if d >= 0 else ""
        return f"{cur:.3f}  (baseline {base:.3f}, {sign}{d:.3f})"

    print("=== DELTA vs baseline.json ===")
    print(f"baseline saved : {baseline.get('timestamp', '?')}")
    base_mode = baseline.get("mode", "server_only")
    if base_mode != current.mode:
        print(
            f"MODE MISMATCH  : current={current.mode}  baseline={base_mode}  — delta mixes pipeline changes with mode change"
        )
    else:
        print(f"mode           : {current.mode}")
    print(f"recall@5       : {delta('recall_at_5')}")
    print(f"recall@10      : {delta('recall_at_10')}")
    print(f"MRR            : {delta('mrr')}")
    print(
        f"must_not viol  : {current.must_not_violations}  (baseline {baseline.get('must_not_violations', '?')})"
    )
    print()

    # per-query regression
    base_results = {r["id"]: r for r in baseline.get("results", [])}
    regressed = []
    improved = []
    for r in current.results:
        br = base_results.get(r["id"])
        if not br:
            continue
        if br["passed"] and not r["passed"]:
            regressed.append(r["id"])
        elif not br["passed"] and r["passed"]:
            improved.append(r["id"])
    if regressed:
        print(f"REGRESSIONS: {regressed}")
    if improved:
        print(f"IMPROVEMENTS: {improved}")
    if not regressed and not improved:
        print("(no per-query status changes vs baseline)")
    print()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--save-baseline",
        action="store_true",
        help="Overwrite tests/memory-eval/baseline.json with this run's results",
    )
    ap.add_argument("--diff", choices=["baseline"], help="Print delta vs baseline.json")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument(
        "--queries",
        default=None,
        help="Path to queries.yaml (default: tests/memory-eval/queries.yaml)",
    )
    ap.add_argument(
        "--with-rewriter",
        action="store_true",
        help="Run the hook's Haiku rewriter on each query — entities "
        "substitute for the raw prompt in keyword search, and "
        "returned types narrow both RPC result sets Python-side. "
        "Requires ANTHROPIC_API_KEY; falls back per-query to raw "
        "prompt when the rewriter returns None.",
    )
    ap.add_argument(
        "--with-links",
        action="store_true",
        help="Expand top-5 RRF rows with a 1-hop BFS on memory_links — "
        "closes coverage gaps where the expected memory is one "
        "edge away from a retrieved row. Uses get_linked_memories "
        "RPC with a decayed RRF score (decay=0.5); fails soft if "
        "the RPC is unavailable.",
    )
    ap.add_argument(
        "--with-session-context",
        action="store_true",
        help="Measure context rot: run each query twice (plain + with session-start "
        "context injected). Reports per-query delta (plain recall@5 - with_context "
        "recall@5) and aggregate delta. Positive = context helps; negative = "
        "context rot confirmed.",
    )
    ap.add_argument(
        "--context-warn-threshold",
        type=float,
        default=-5.0,
        help="Warn if aggregate context delta falls below this pp (default: -5.0). "
        "Set to None for advisory-only on first run.",
    )
    ap.add_argument(
        "--context-fail-threshold",
        type=float,
        default=None,
        help="Exit with code 1 if aggregate context delta falls below this pp. "
        "Default None (advisory-only). Set to -10.0 for CI gating after baseline.",
    )
    args = ap.parse_args()

    _load_env()

    repo = Path(__file__).resolve().parent.parent
    queries_path = (
        Path(args.queries) if args.queries else repo / "tests" / "memory-eval" / "queries.yaml"
    )
    baseline_path = repo / "tests" / "memory-eval" / "baseline.json"

    import yaml

    with queries_path.open("r", encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    queries = doc["queries"]

    try:
        from supabase import create_client
    except ImportError:
        print("ERROR: supabase package not installed in venv", file=sys.stderr)
        return 2

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        print("ERROR: SUPABASE_URL / SUPABASE_KEY not set", file=sys.stderr)
        return 2
    client = create_client(url, key)

    rewriter = None
    boost_multiplier = 1.0  # no-op when rewriter disabled
    if args.with_rewriter:
        hook_mod = _load_hook_module()
        if hook_mod is None:
            print(
                "ERROR: --with-rewriter set but scripts/memory-recall-hook.py "
                "could not be loaded as a module",
                file=sys.stderr,
            )
            return 2
        rewriter = getattr(hook_mod, "rewrite_prompt", None)
        if rewriter is None:
            print(
                "ERROR: --with-rewriter set but rewrite_prompt not found in hook module",
                file=sys.stderr,
            )
            return 2
        # Source boost calibration from the hook — single source of truth.
        boost_multiplier = float(getattr(hook_mod, "TYPE_BOOST_MULTIPLIER", 1.5))
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print(
                "WARN: --with-rewriter set but ANTHROPIC_API_KEY missing — "
                "rewriter will return None for every query (degrades to server_only).",
                file=sys.stderr,
            )

    # Load session-start context if requested
    context_items: list[dict] | None = None
    if args.with_session_context:
        try:
            context_items, char_count, item_counts = asyncio.run(_load_session_context(client))
            print(
                f"[context-rot] Loaded {len(context_items)} context items, "
                f"~{char_count} chars, {item_counts}",
                file=sys.stderr,
            )
        except Exception as e:
            print(f"WARN: --with-session-context set but context load failed: {e}", file=sys.stderr)
            context_items = None

    report = asyncio.run(
        run_all(
            queries,
            client,
            rewriter=rewriter,
            boost_multiplier=boost_multiplier,
            with_links=args.with_links,
            context_items=context_items,
        )
    )
    print_report(report, quiet=args.quiet)

    if args.diff == "baseline":
        if not baseline_path.exists():
            print(f"(no baseline at {baseline_path} — run --save-baseline first)")
        else:
            with baseline_path.open("r", encoding="utf-8") as f:
                baseline = json.load(f)
            print_diff(report, baseline)

    if args.save_baseline:
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        with baseline_path.open("w", encoding="utf-8") as f:
            json.dump(asdict(report), f, indent=2, ensure_ascii=False)
        print(f"Baseline saved to {baseline_path}")

    # Context rot thresholding
    exit_code = 0 if report.failed == 0 else 1
    if args.with_session_context and report.context_budget_chars > 0:
        agg_delta = report.context_aggregate_delta
        if args.context_warn_threshold is not None and agg_delta < args.context_warn_threshold:
            print(
                f"\nWARN: context aggregate delta {agg_delta:.2f}pp < warn threshold {args.context_warn_threshold}pp",
                file=sys.stderr,
            )
        if args.context_fail_threshold is not None and agg_delta < args.context_fail_threshold:
            print(
                f"\nFAIL: context aggregate delta {agg_delta:.2f}pp < fail threshold {args.context_fail_threshold}pp",
                file=sys.stderr,
            )
            exit_code = 1

    # exit code: 0 if all queries passed, 1 otherwise — CI-friendly
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
