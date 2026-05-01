"""Recall pipeline: deep module behind every recall call site.

Single source of truth for the constants and primitive helpers that
shape the hybrid-recall pipeline (semantic + keyword fusion + temporal
scoring + link expansion + known-unknown gate). Three adapters live
elsewhere and import from here:

    - mcp-memory/handlers/memory.py  — MCP `recall` tool
    - scripts/memory-recall-hook.py  — UserPromptSubmit hook
    - scripts/eval-recall.py         — eval harness

Slice 1 of 4 (issue #496): constants and primitive filter/math helpers.
Subsequent slices migrate scoring, merge, link-expansion, and finally
the public `RecallConfig` / `RecallHit` / `recall()` orchestrator.
See CONTEXT.md (Recall, RecallConfig, RecallHit) for the deep-module
contract.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone


# Reciprocal-Rank-Fusion constant. Higher k flattens rank weighting; k=60
# is the canonical value from the original RRF paper and matches every
# existing call site.
RRF_K = 60

# Minimum cosine similarity for a semantic hit to count. Calibrated
# against voyage-3-lite/512 on the canonical eval set: rows below 0.25 are
# overwhelmingly unrelated, rows above 0.30 are strongly relevant.
# Adapter-level overrides exist (the UserPromptSubmit hook tightens this
# to 0.30 for conversational prompts, which carry more glue tokens) — those
# stay local to the adapter until slice 3 expresses them as RecallConfig
# flags.
SIMILARITY_THRESHOLD = 0.25

# Per-type half-life (days) for the temporal-decay component. Shorter
# half-lives for fast-moving content (project state, references), longer
# for slow-moving content (user profile, behavioral feedback). Memories
# with a type not in this map use DEFAULT_HALF_LIFE at the call site.
TEMPORAL_HALF_LIVES: dict[str, float] = {
    "project": 7,
    "reference": 30,
    "decision": 60,
    "feedback": 90,
    "user": 180,
}

# #417: operational artifacts like session snapshots carry mixed
# transcript content that semantically matches a wide range of queries.
# They're meant to be fetched by name via memory_get during /end recovery,
# never to compete in normal recall. Filtering at the Python layer keeps
# the schema and RPCs untouched while measurably lifting recall@5.
EXCLUDE_TAGS_FROM_RECALL: frozenset[str] = frozenset({"session-snapshot"})


def filter_excluded_tags(rows):
    """Drop rows whose tags overlap EXCLUDE_TAGS_FROM_RECALL. See #417.

    Preserves input ordering. Pass-through for falsy input.
    """
    if not rows or not EXCLUDE_TAGS_FROM_RECALL:
        return rows
    out = []
    for row in rows:
        tags = row.get("tags") or []
        if isinstance(tags, list) and any(t in EXCLUDE_TAGS_FROM_RECALL for t in tags):
            continue
        out.append(row)
    return out


def parse_pgvector(v: list[float] | str | None) -> list[float] | None:
    """Normalize a pgvector value returned by supabase-py.

    PostgREST returns vector columns as JSON-encoded strings
    (e.g. ``"[0.1,0.2,...]"``), not Python lists. Callers that pass the
    raw value into ``cosine_sim`` hit the len-mismatch guard and silently
    score 0. Return a float list, or None if the value is missing /
    unparseable.
    """
    if v is None:
        return None
    if isinstance(v, list):
        return v
    if isinstance(v, str):
        try:
            parsed = json.loads(v)
        except (ValueError, TypeError):
            return None
        return parsed if isinstance(parsed, list) else None
    return None


def cosine_sim(v1: list[float] | None, v2: list[float] | None) -> float:
    """Cosine similarity between two embedding vectors.

    Returns 0.0 if either is None/empty or if lengths differ. The
    length-mismatch guard is load-bearing during embedding-model
    migrations: zip would silently truncate to the shorter vector and
    yield a meaningless score.
    """
    if v1 is None or v2 is None or len(v1) == 0 or len(v2) == 0:
        return 0.0
    if len(v1) != len(v2):
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2))
    mag1 = math.sqrt(sum(a * a for a in v1))
    mag2 = math.sqrt(sum(b * b for b in v2))
    if mag1 == 0 or mag2 == 0:
        return 0.0
    return dot / (mag1 * mag2)


# ---------------------------------------------------------------------------
# Slice 2 of 4 (issue #497): scoring, merge, and link-expansion functions.
# ---------------------------------------------------------------------------

# Temporal decay constants. DEFAULT_HALF_LIFE applies when a memory type is
# absent from TEMPORAL_HALF_LIVES. ACCESS_* tune the ACT-R access-frequency
# boost; CONFIDENCE_FLOOR ensures a zero-confidence memory still ranks at 50%
# of its temporal score rather than zeroing out.
DEFAULT_HALF_LIFE = 30
ACCESS_BOOST_MAX = 0.3
ACCESS_HALF_LIFE = 14
CONFIDENCE_FLOOR = 0.5

# Link-expansion constants for 1-hop BFS via get_linked_memories.
# LINK_DECAY attenuates a linked row's score relative to its parent's direct
# hit (0.5 → linked row worth half a direct hit at the same rank). LINK_SCORE_FIELD
# marks linked-only rows for display and downstream merge logic.
# Default 1.5 for boost_multiplier in rrf_merge matches TYPE_BOOST_MULTIPLIER in
# the hook adapter — re-tune both together if the calibration changes.
LINK_EXPAND_TOP_K = 5
LINK_DECAY = 0.5
LINK_SCORE_FIELD = "_link_score"


def rrf_merge(
    semantic_rows: list[dict],
    keyword_rows: list[dict],
    limit: int | None = None,
    k: int = RRF_K,
    boost_types: set[str] | None = None,
    boost_multiplier: float = 1.5,
) -> list[dict]:
    """Reciprocal Rank Fusion over two ranked lists.

    Score = sum(1 / (k + rank)) for each list the item appears in. Higher k
    flattens rank weighting; k=60 is the canonical value from the RRF paper.

    Semantics: only rows hit by BOTH signals get ``_rrf_score`` — that is the
    semantic meaning of fusion and is used by downstream display logic to pick
    the right score label. Every row gets ``_final_score`` (the unified sort key
    consumed by ``merge_with_links``). Single-hit rows that receive a type boost
    also get ``_sort_score`` so the displayed score stays in sync with the ranking.

    ``boost_types``: when set, rows whose ``type`` is in the set get their score
    multiplied by ``boost_multiplier`` before the rank sort. The default 1.5
    matches the hook's ``TYPE_BOOST_MULTIPLIER`` — a boosted single-hit (0.025)
    stays below an unboosted dual-hit (0.0333), preserving fusion ordering.

    ``limit``: if provided, the result is sliced to at most this many rows.
    Pass ``None`` (default) to let the caller cap by budget or row count.

    Divergences vs. the three pre-slice-2 copies documented in the slice-2 PR:
    - handler/memory.py always set ``_rrf_score`` on every row; canonical
      matches the hook (dual-hit only) which is semantically correct.
    - handler's ``by_id`` kept the keyword row when a memory appeared in both
      lists; canonical keeps the semantic row (hook behavior) to preserve the
      ``similarity`` field for display fallback.
    """
    scores: dict[str, float] = {}
    hits: dict[str, int] = {}
    by_id: dict[str, dict] = {}
    for rank, row in enumerate(semantic_rows):
        rid = row.get("id") or row.get("name")
        if not rid:
            continue
        scores[rid] = scores.get(rid, 0.0) + 1.0 / (k + rank)
        hits[rid] = hits.get(rid, 0) + 1
        by_id[rid] = row
    for rank, row in enumerate(keyword_rows):
        rid = row.get("id") or row.get("name")
        if not rid:
            continue
        scores[rid] = scores.get(rid, 0.0) + 1.0 / (k + rank)
        hits[rid] = hits.get(rid, 0) + 1
        by_id.setdefault(rid, row)
    if boost_types:
        for rid, row in by_id.items():
            if row.get("type") in boost_types:
                scores[rid] *= boost_multiplier
                if hits[rid] == 1:
                    row["_sort_score"] = scores[rid]
    ranked_ids = sorted(scores.keys(), key=lambda r: scores[r], reverse=True)
    out = []
    for rid in ranked_ids:
        row = by_id[rid]
        if hits[rid] >= 2:
            row["_rrf_score"] = scores[rid]
        row["_final_score"] = scores[rid]
        out.append(row)
    if limit is not None:
        out = out[:limit]
    return out


def score_linked_rows(
    top_rows: list[dict],
    linked_rows: list[dict],
    *,
    top_k: int = LINK_EXPAND_TOP_K,
    decay: float = LINK_DECAY,
    k: int = RRF_K,
) -> list[dict]:
    """Annotate linked_rows with a synthetic RRF-like score derived from
    their parent's rank in top_rows.

    Pure function — takes already-fetched link rows (from
    ``get_linked_memories``, which carries ``linked_from`` pointing at the seed
    id) and returns the subset whose parent is in the top-K seed window,
    deduped against the seeds and against each other.

    Score formula: ``(1 / (k + parent_rank)) * decay * link_strength``.
    Mirrors the RRF math in ``rrf_merge`` so link scores live in the same
    space; ``decay`` attenuates them (0.5 → linked hit worth half a direct hit
    at the same rank). ``link_strength`` (0..1, from DB) scales by edge
    confidence.
    """
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


def expand_links(
    client,
    top_rows: list[dict],
    *,
    link_types: list[str] | None = None,
    top_k: int = LINK_EXPAND_TOP_K,
    decay: float = LINK_DECAY,
) -> list[dict]:
    """Fetch 1-hop linked neighbors of the top-K rows via ``get_linked_memories``.

    Returns annotated linked rows (see ``score_linked_rows``). On RPC failure
    returns []. Fail-soft contract — links are a coverage bonus, not a hard
    requirement.
    """
    seed_ids = [r["id"] for r in top_rows[:top_k] if r.get("id")]
    if not seed_ids:
        return []
    try:
        result = client.rpc(
            "get_linked_memories",
            {
                "memory_ids": seed_ids,
                "link_types": link_types,
                "show_history": False,
            },
        ).execute()
        linked_rows = result.data or []
    except Exception:
        return []
    return score_linked_rows(top_rows, linked_rows, top_k=top_k, decay=decay)


def merge_with_links(ranked_rows: list[dict], linked_rows: list[dict]) -> list[dict]:
    """Fold linked rows into the already-ranked hybrid result.

    Each ``ranked_rows`` entry carries ``_final_score`` (set by ``rrf_merge``);
    each ``linked_rows`` entry carries ``_link_score`` (set by
    ``score_linked_rows``). Rows that appear in both keep the max. Sort key
    after merge is the resulting score, written back to ``_final_score`` so
    downstream budget trim and display stay consistent.
    """
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


def enrich_with_confidence(client, rows: list[dict]) -> None:
    """Backfill ``confidence`` on rows that came from match_memories (which
    doesn't project it). Batched SELECT keeps this cheap. Best-effort: on
    error we leave rows untouched and scoring falls back to the NULL→1.0
    branch in ``apply_temporal_scoring``.

    Phase 1 polish (#240).
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


def apply_temporal_scoring(rows: list[dict]) -> list[dict]:
    """Re-rank rows by combining RRF score with temporal decay and access frequency.

    Reads ``_rrf_score`` (or ``_final_score`` as fallback; 0.01 if absent) as
    the base fusion weight, then multiplies by:
    - recency:       exponential decay since last content update
    - access boost:  ACT-R frequency boost since last access
    - entrenchment:  confidence-derived multiplier (Phase 1 polish #240)

    Writes ``_temporal_score`` and re-sorts rows in-place (descending).
    """
    now = datetime.now(timezone.utc)
    for row in rows:
        rrf = row.get("_rrf_score") or row.get("_final_score") or 0.01
        mem_type = row.get("type", "decision")
        half_life = TEMPORAL_HALF_LIVES.get(mem_type, DEFAULT_HALF_LIFE)

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
