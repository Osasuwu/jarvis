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
from typing import Any, Callable

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
# Phase 1 polish (#240): mirror of server.py — entrenchment multiplier.
CONFIDENCE_FLOOR = 0.5

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


def _merge_with_links(
    ranked_rows: list[dict], linked_rows: list[dict]
) -> list[dict]:
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


def _enrich_with_confidence(client, rows: list[dict]) -> None:
    """Mirror of server.py helper (#240). match_memories doesn't project
    confidence; enrich rows before scoring so eval numbers match production.
    """
    ids = [r["id"] for r in rows if r.get("id") and "confidence" not in r]
    if not ids:
        return
    try:
        result = client.table("memories").select("id, confidence").in_("id", ids).execute()
    except Exception:
        return
    conf_map = {r["id"]: r.get("confidence") for r in (result.data or [])}
    for row in rows:
        rid = row.get("id")
        if rid in conf_map and "confidence" not in row:
            row["confidence"] = conf_map[rid]


def _apply_temporal_scoring(rows: list[dict]) -> list[dict]:
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

        # Entrenchment multiplier (Phase 1 polish #240). NULL → 1.0 no-regression.
        confidence_raw = row.get("confidence")
        if confidence_raw is None:
            conf = 1.0
        else:
            try:
                conf = float(confidence_raw)
            except (TypeError, ValueError):
                conf = 1.0
        conf = max(0.0, min(1.0, conf))
        entrenchment = CONFIDENCE_FLOOR + (1.0 - CONFIDENCE_FLOOR) * conf

        row["_temporal_score"] = rrf * recency * access * entrenchment

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
    top_names: list[str]                 # top-10 names in order
    first_hit_rank: int | None           # 1-indexed, None if no expected hit in top-10
    hits_at_5: list[str]                 # expected names that appeared in top-5
    hits_at_10: list[str]
    must_not_violations_at_5: list[str]  # must_not names that appeared in top-5
    passed: bool                         # recall@5 >= 1 AND no must_not violations
    rewriter_entities: list[str] = field(default_factory=list)
    rewriter_types: list[str] = field(default_factory=list)
    rewriter_fired: bool = False         # True when rewriter returned a non-null result
    links_added: int = 0                 # new rows added via 1-hop BFS


@dataclass
class EvalReport:
    timestamp: str
    mode: str                            # e.g. "server_only", "with_rewriter+links"
    corpus_size: int
    total_queries: int
    recall_at_5: float
    recall_at_10: float
    mrr: float
    must_not_violations: int
    passed: int
    failed: int
    rewriter_fired_count: int = 0        # queries where rewriter produced output
    links_added_total: int = 0           # total new rows pulled in via link expansion
    results: list[dict] = field(default_factory=list)


# -- #241: context-rot measurement -----------------------------------------

@dataclass
class ContextRotResult:
    """Per-query comparison of plain vs. context-injected recall."""
    id: str
    query: str
    plain_top_names: list[str]
    context_top_names: list[str]
    plain_hits_at_5: list[str]
    context_hits_at_5: list[str]
    plain_first_hit_rank: int | None
    context_first_hit_rank: int | None
    plain_must_not_viol: list[str]
    context_must_not_viol: list[str]
    plain_passed: bool
    context_passed: bool


@dataclass
class ContextRotReport:
    """Aggregate context-rot metrics.

    Sign convention (spec #241): `delta_* = with_context − plain`.
    Positive → context HELPS recall. Negative → retrieval-induced
    forgetting ("context rot"), as in LongMemEval.
    """
    timestamp: str
    corpus_size: int
    total_queries: int
    plain_recall_at_5: float
    context_recall_at_5: float
    delta_recall_at_5_pp: float           # (context - plain) * 100
    plain_recall_at_10: float
    context_recall_at_10: float
    delta_recall_at_10_pp: float
    plain_mrr: float
    context_mrr: float
    delta_mrr: float
    plain_must_not_violations: int
    context_must_not_violations: int
    only_plain_passed: list[str]          # query ids where plain passed but context didn't (= rot)
    only_context_passed: list[str]        # query ids where context passed but plain didn't (= helps)
    context_budget: dict                  # chars, tokens, item counts
    per_query: list[dict] = field(default_factory=list)


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
    context_blob: str | None = None,
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

    # #241: simulate session-start context pollution by appending the loaded
    # blob to the keyword query. pg_trgm similarity on a longer, noisier
    # string dilutes matches against the target row. Does not affect the
    # semantic leg — isolates one signal (keyword dilution).
    if context_blob:
        keyword_query = f"{keyword_query} {context_blob}"

    sem = client.rpc("match_memories", {
        "query_embedding": embedding,
        "match_limit": 20,
        "similarity_threshold": SIMILARITY_THRESHOLD,
        "filter_project": None,
        "filter_type": None,
        "show_history": False,
    }).execute()
    sem_rows = sem.data or []

    kw = client.rpc("keyword_search_memories", {
        "search_query": keyword_query,
        "match_limit": 20,
        "filter_project": None,
        "filter_type": None,
        "show_history": False,
    }).execute()
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
            links_added = sum(
                1 for r in merged if r.get("id") and r.get("id") not in before_ids
            )
        # Trim back to top-10 for metrics; any linked row that made it
        # into top-10 has earned its place via the unified _final_score.
        merged = merged[:10]

    # #240: enrich with confidence before scoring (match_memories doesn't project it).
    _enrich_with_confidence(client, merged)
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
    )


async def run_all(
    queries: list[dict],
    client,
    rewriter: Callable[[str], dict | None] | None = None,
    boost_multiplier: float = 1.0,
    with_links: bool = False,
) -> EvalReport:
    results = []
    for q in queries:
        r = await run_query(
            client,
            q,
            rewriter=rewriter,
            boost_multiplier=boost_multiplier,
            with_links=with_links,
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
    cs = client.table("memories").select("id", count="exact").is_("deleted_at", "null").limit(1).execute()
    corpus_size = cs.count or 0

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
    )


# ---------------------------------------------------------------------------
# #241: session-start context rot measurement
# ---------------------------------------------------------------------------

# ~4 chars per token is a rough-but-stable estimate for mixed EN/RU text.
CONTEXT_CHARS_PER_TOKEN = 4
CONTEXT_USER_LIMIT = 2  # match scripts/session-context.py


def _load_session_context(client) -> tuple[str, dict]:
    """Load the items the SessionStart hook injects, return a single keyword
    blob + budget metrics. Mirrors scripts/session-context.py:
      - top 2 user memories (by updated_at)
      - all memories tagged `always_load`
      - active goals

    Skips working_state (tied to cwd, not meaningful in the eval harness).
    The blob is plain text — name + description + tags + content — because
    injection goes into pg_trgm keyword search, which tokenises on whitespace.
    """
    parts: list[str] = []
    counts = {"user": 0, "always_load": 0, "goals": 0}

    def _mem_text(m: dict) -> str:
        pieces = [
            m.get("name") or "",
            m.get("description") or "",
            " ".join(m.get("tags") or []),
            m.get("content") or "",
        ]
        return " ".join(p for p in pieces if p)

    # 1. Top-2 user memories
    try:
        r = (
            client.table("memories")
            .select("name, description, tags, content")
            .eq("type", "user")
            .is_("deleted_at", "null")
            .order("updated_at", desc=True)
            .limit(CONTEXT_USER_LIMIT)
            .execute()
        )
        for m in r.data or []:
            parts.append(_mem_text(m))
            counts["user"] += 1
    except Exception as e:
        print(f"[context-rot] user query failed: {e}", file=sys.stderr)

    # 2. always_load memories (evergreen rules)
    try:
        r = (
            client.table("memories")
            .select("name, description, tags, content")
            .contains("tags", ["always_load"])
            .is_("deleted_at", "null")
            .order("updated_at", desc=True)
            .execute()
        )
        for m in r.data or []:
            parts.append(_mem_text(m))
            counts["always_load"] += 1
    except Exception as e:
        print(f"[context-rot] always_load query failed: {e}", file=sys.stderr)

    # 3. Active goals — flatten title + why + jarvis_focus into blob
    try:
        r = (
            client.table("goals")
            .select("title, why, jarvis_focus, owner_focus")
            .eq("status", "active")
            .execute()
        )
        for g in r.data or []:
            pieces = [
                g.get("title") or "",
                g.get("why") or "",
                g.get("jarvis_focus") or "",
                g.get("owner_focus") or "",
            ]
            parts.append(" ".join(p for p in pieces if p))
            counts["goals"] += 1
    except Exception as e:
        print(f"[context-rot] goals query failed: {e}", file=sys.stderr)

    # 4. Memory catalog (Phase 7.1) — lazy-index entries (name + description +
    #    tags) for live, in-scope memories. Mirrors scripts/session-context.py
    #    :_query_catalog. Eval runs project-agnostic, so we scope to global
    #    (project IS NULL) only — matches the non-project cwd session case.
    try:
        r = (
            client.table("memories")
            .select("name, description, tags, type, project")
            .is_("expired_at", "null")
            .is_("superseded_by", "null")
            .is_("project", "null")
            .order("last_accessed_at", desc=True, nullsfirst=False)
            .limit(200)
            .execute()
        )
        for m in r.data or []:
            if m.get("type") == "user":
                continue
            tags = m.get("tags") or []
            if "always_load" in tags:
                continue
            pieces = [
                m.get("name") or "",
                m.get("description") or "",
                " ".join(tags),
            ]
            parts.append(" ".join(p for p in pieces if p))
            counts["catalog"] = counts.get("catalog", 0) + 1
    except Exception as e:
        print(f"[context-rot] catalog query failed: {e}", file=sys.stderr)

    blob = " ".join(p.strip() for p in parts if p.strip())
    chars = len(blob)
    budget = {
        "chars": chars,
        "tokens_approx": chars // CONTEXT_CHARS_PER_TOKEN,
        "item_count": sum(counts.values()),
        **counts,
    }
    return blob, budget


def _metrics_from_results(results: list[QueryResult], total: int) -> tuple[float, float, float, int]:
    r5 = sum(1 for r in results if r.hits_at_5) / total if total else 0.0
    r10 = sum(1 for r in results if r.hits_at_10) / total if total else 0.0
    mrr = sum(1.0 / r.first_hit_rank for r in results if r.first_hit_rank) / total if total else 0.0
    mn = sum(1 for r in results if r.must_not_violations_at_5)
    return r5, r10, mrr, mn


async def run_context_rot_eval(
    queries: list[dict],
    client,
    context_blob: str,
    budget: dict,
) -> ContextRotReport:
    """Run each query twice — plain then with context blob injected into the
    keyword leg — and return aggregate + per-query deltas.

    Sign convention: delta = with_context − plain. Positive = context helps;
    negative = retrieval-induced forgetting (rot).
    """
    plain_results: list[QueryResult] = []
    context_results: list[QueryResult] = []
    per_query: list[dict] = []

    for q in queries:
        plain = await run_query(client, q, context_blob=None)
        with_ctx = await run_query(client, q, context_blob=context_blob)
        plain_results.append(plain)
        context_results.append(with_ctx)
        per_query.append(asdict(ContextRotResult(
            id=q["id"],
            query=q["query"],
            plain_top_names=plain.top_names[:5],
            context_top_names=with_ctx.top_names[:5],
            plain_hits_at_5=plain.hits_at_5,
            context_hits_at_5=with_ctx.hits_at_5,
            plain_first_hit_rank=plain.first_hit_rank,
            context_first_hit_rank=with_ctx.first_hit_rank,
            plain_must_not_viol=plain.must_not_violations_at_5,
            context_must_not_viol=with_ctx.must_not_violations_at_5,
            plain_passed=plain.passed,
            context_passed=with_ctx.passed,
        )))

    total = len(queries)
    p_r5, p_r10, p_mrr, p_mn = _metrics_from_results(plain_results, total)
    c_r5, c_r10, c_mrr, c_mn = _metrics_from_results(context_results, total)

    only_plain = [
        q["id"] for q, p, c in zip(queries, plain_results, context_results)
        if p.passed and not c.passed
    ]
    only_context = [
        q["id"] for q, p, c in zip(queries, plain_results, context_results)
        if c.passed and not p.passed
    ]

    cs = client.table("memories").select("id", count="exact").is_("deleted_at", "null").limit(1).execute()

    return ContextRotReport(
        timestamp=datetime.now(timezone.utc).isoformat(),
        corpus_size=cs.count or 0,
        total_queries=total,
        plain_recall_at_5=p_r5,
        context_recall_at_5=c_r5,
        delta_recall_at_5_pp=(c_r5 - p_r5) * 100,
        plain_recall_at_10=p_r10,
        context_recall_at_10=c_r10,
        delta_recall_at_10_pp=(c_r10 - p_r10) * 100,
        plain_mrr=p_mrr,
        context_mrr=c_mrr,
        delta_mrr=c_mrr - p_mrr,
        plain_must_not_violations=p_mn,
        context_must_not_violations=c_mn,
        only_plain_passed=only_plain,
        only_context_passed=only_context,
        context_budget=budget,
        per_query=per_query,
    )


def print_context_rot_report(report: ContextRotReport, quiet: bool = False) -> None:
    if not quiet:
        print(f"\nQueries: {report.total_queries}   Corpus: {report.corpus_size} memories   Mode: context-rot\n")
        print(f"Context budget: {report.context_budget['chars']} chars "
              f"(~{report.context_budget['tokens_approx']} tokens), "
              f"{report.context_budget['item_count']} items "
              f"(user={report.context_budget['user']}, "
              f"always_load={report.context_budget['always_load']}, "
              f"goals={report.context_budget['goals']}, "
              f"catalog={report.context_budget.get('catalog', 0)})\n")

        # Per-query table: plain rank → context rank, mark regressions/wins
        print(f"{'id':<5} {'plain':>6}  {'ctx':>6}  drank  result   query")
        print("-" * 100)
        for r in report.per_query:
            p_rank = r["plain_first_hit_rank"]
            c_rank = r["context_first_hit_rank"]
            p_s = str(p_rank) if p_rank else "-"
            c_s = str(c_rank) if c_rank else "-"
            # drank: positive if context ranked worse (higher number)
            if p_rank and c_rank:
                drank = c_rank - p_rank
                d_s = f"{drank:+d}" if drank else "  0"
            else:
                d_s = "  ."
            if r["plain_passed"] and not r["context_passed"]:
                verdict = "ROT  "
            elif r["context_passed"] and not r["plain_passed"]:
                verdict = "HELP "
            elif r["plain_passed"] and r["context_passed"]:
                verdict = "both "
            else:
                verdict = "miss "
            q = r["query"] if len(r["query"]) <= 55 else r["query"][:52] + "..."
            print(f"{r['id']:<5} {p_s:>6}  {c_s:>6}  {d_s:>5}  {verdict}   {q}")

    print("\n=== CONTEXT-ROT AGGREGATES ===")
    print(f"plain    recall@5 : {_fmt_pct(report.plain_recall_at_5)}")
    print(f"context  recall@5 : {_fmt_pct(report.context_recall_at_5)}")
    sign = "+" if report.delta_recall_at_5_pp >= 0 else ""
    print(f"delta recall@5        : {sign}{report.delta_recall_at_5_pp:.1f} pp   "
          f"({'context helps' if report.delta_recall_at_5_pp > 0 else 'context rot' if report.delta_recall_at_5_pp < 0 else 'no effect'})")
    sign10 = "+" if report.delta_recall_at_10_pp >= 0 else ""
    print(f"delta recall@10       : {sign10}{report.delta_recall_at_10_pp:.1f} pp")
    sign_mrr = "+" if report.delta_mrr >= 0 else ""
    print(f"delta MRR             : {sign_mrr}{report.delta_mrr:.3f}")
    print(f"must_not (p/c)    : {report.plain_must_not_violations} / {report.context_must_not_violations}")
    if report.only_plain_passed:
        print(f"lost with context : {report.only_plain_passed}  (rot — passed plain, failed with context)")
    if report.only_context_passed:
        print(f"won  with context : {report.only_context_passed}  (helps — passed only with context)")
    print()


# ---------------------------------------------------------------------------
# Formatting / CLI
# ---------------------------------------------------------------------------

def _fmt_pct(x: float) -> str:
    return f"{x*100:5.1f}%"


def print_report(report: EvalReport, quiet: bool = False) -> None:
    if not quiet:
        print(f"\nQueries: {report.total_queries}   Corpus: {report.corpus_size} memories   Mode: {report.mode}\n")
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
                    print(f"    rewriter:  entities={r.get('rewriter_entities') or []} types={r.get('rewriter_types') or []}")

    print("\n=== AGGREGATES ===")
    print(f"mode               : {report.mode}")
    print(f"recall@5           : {_fmt_pct(report.recall_at_5)}  ({report.passed}/{report.total_queries} queries retrieved at least one expected memory in top-5)")
    print(f"recall@10          : {_fmt_pct(report.recall_at_10)}")
    print(f"MRR                : {report.mrr:.3f}")
    print(f"must_not violations: {report.must_not_violations}  (lifecycle signal — should be 0 after Phase 1)")
    print(f"passed / failed    : {report.passed} / {report.failed}")
    if "with_rewriter" in report.mode:
        print(f"rewriter fired     : {report.rewriter_fired_count}/{report.total_queries}")
    if "links" in report.mode:
        print(f"links added (sum)  : {report.links_added_total}  (rows added via 1-hop BFS)")
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
        print(f"MODE MISMATCH  : current={current.mode}  baseline={base_mode}  — delta mixes pipeline changes with mode change")
    else:
        print(f"mode           : {current.mode}")
    print(f"recall@5       : {delta('recall_at_5')}")
    print(f"recall@10      : {delta('recall_at_10')}")
    print(f"MRR            : {delta('mrr')}")
    print(f"must_not viol  : {current.must_not_violations}  (baseline {baseline.get('must_not_violations', '?')})")
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
    ap.add_argument("--save-baseline", action="store_true",
                    help="Overwrite tests/memory-eval/baseline.json with this run's results")
    ap.add_argument("--diff", choices=["baseline"],
                    help="Print delta vs baseline.json")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--queries", default=None,
                    help="Path to queries.yaml (default: tests/memory-eval/queries.yaml)")
    ap.add_argument("--with-rewriter", action="store_true",
                    help="Run the hook's Haiku rewriter on each query — entities "
                         "substitute for the raw prompt in keyword search, and "
                         "returned types narrow both RPC result sets Python-side. "
                         "Requires ANTHROPIC_API_KEY; falls back per-query to raw "
                         "prompt when the rewriter returns None.")
    ap.add_argument("--with-links", action="store_true",
                    help="Expand top-5 RRF rows with a 1-hop BFS on memory_links — "
                         "closes coverage gaps where the expected memory is one "
                         "edge away from a retrieved row. Uses get_linked_memories "
                         "RPC with a decayed RRF score (decay=0.5); fails soft if "
                         "the RPC is unavailable.")
    ap.add_argument("--with-session-context", action="store_true",
                    help="#241 context-rot mode: measure whether session-start "
                         "context injection helps or hurts recall. Runs each query "
                         "twice — plain vs. with the SessionStart hook's blob "
                         "appended to the keyword leg — and reports delta "
                         "(positive = helps, negative = rot).")
    ap.add_argument("--save-context-rot-baseline", action="store_true",
                    help="Write tests/memory-eval/context-rot-baseline.json from "
                         "this run (only valid with --with-session-context).")
    ap.add_argument("--context-warn-threshold", type=float, default=-5.0,
                    help="Warn if delta recall@5 < this (pp). Default -5.")
    ap.add_argument("--context-fail-threshold", type=float, default=None,
                    help="Exit 1 if delta recall@5 < this (pp). Advisory-only by "
                         "default (spec #241: flip to blocking after 2-week "
                         "baseline).")
    args = ap.parse_args()

    _load_env()

    repo = Path(__file__).resolve().parent.parent
    queries_path = Path(args.queries) if args.queries else repo / "tests" / "memory-eval" / "queries.yaml"
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
            print("ERROR: --with-rewriter set but scripts/memory-recall-hook.py "
                  "could not be loaded as a module", file=sys.stderr)
            return 2
        rewriter = getattr(hook_mod, "rewrite_prompt", None)
        if rewriter is None:
            print("ERROR: --with-rewriter set but rewrite_prompt not found in hook "
                  "module", file=sys.stderr)
            return 2
        # Source boost calibration from the hook — single source of truth.
        boost_multiplier = float(getattr(hook_mod, "TYPE_BOOST_MULTIPLIER", 1.5))
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print("WARN: --with-rewriter set but ANTHROPIC_API_KEY missing — "
                  "rewriter will return None for every query (degrades to server_only).",
                  file=sys.stderr)

    # #241 context-rot path: dual-run plain vs context-injected and exit
    if args.with_session_context:
        if args.with_rewriter or args.with_links:
            print("ERROR: --with-session-context is exclusive with --with-rewriter / "
                  "--with-links (baseline signal only). Run separately.", file=sys.stderr)
            return 2
        blob, budget = _load_session_context(client)
        if not blob:
            print("ERROR: loaded empty session context — nothing to inject.", file=sys.stderr)
            return 2
        rot_report = asyncio.run(run_context_rot_eval(queries, client, blob, budget))
        print_context_rot_report(rot_report, quiet=args.quiet)

        if args.save_context_rot_baseline:
            rot_path = repo / "tests" / "memory-eval" / "context-rot-baseline.json"
            rot_path.parent.mkdir(parents=True, exist_ok=True)
            with rot_path.open("w", encoding="utf-8") as f:
                json.dump(asdict(rot_report), f, indent=2, ensure_ascii=False)
            print(f"Context-rot baseline saved to {rot_path}")

        delta = rot_report.delta_recall_at_5_pp
        if delta < args.context_warn_threshold:
            print(f"WARN: delta recall@5 = {delta:+.1f} pp below warn threshold "
                  f"({args.context_warn_threshold:+.1f} pp) — context rot present.",
                  file=sys.stderr)
        if args.context_fail_threshold is not None and delta < args.context_fail_threshold:
            print(f"FAIL: delta recall@5 = {delta:+.1f} pp below fail threshold "
                  f"({args.context_fail_threshold:+.1f} pp).", file=sys.stderr)
            return 1
        return 0

    report = asyncio.run(
        run_all(queries, client, rewriter=rewriter,
                boost_multiplier=boost_multiplier, with_links=args.with_links)
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

    # exit code: 0 if all queries passed, 1 otherwise — CI-friendly
    return 0 if report.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
