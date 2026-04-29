"""Memory handlers + recall helpers (#360 split).

Hosts every memory_* tool body and its helpers — the recall pipeline
(hybrid + RRF + keyword fallback + temporal scoring), the write
pipeline (auto-link, classifier-decision routing, supersession), the
graph queries, and the known-unknowns gap tracker.

Tests monkeypatch utility names on the `server` module — calls go
through `server.<name>` at runtime to propagate those patches. The
two duplicate definitions of `_cosine_sim` and `_upsert_known_unknown`
that lived in the original server.py (sync versions at L1508/1520
shadowed at runtime by async versions at L2402/2418) are dropped
here — pure dead code per Python module-load semantics. Behavior
preserved.
"""

from __future__ import annotations

import asyncio
import json
import math
import os
from datetime import datetime, timezone

from mcp.types import TextContent

import server  # late-bound — see module docstring

# Phase 2b classifier — same conditional-import pattern as server.py.
try:
    from classifier import (  # type: ignore
        classify_write,
        ClassifierDecision,
        CLASSIFIER_MODEL,
    )
except Exception:  # pragma: no cover
    classify_write = None  # type: ignore
    ClassifierDecision = None  # type: ignore
    CLASSIFIER_MODEL = "claude-haiku-4-5"

# Re-export _canonical_embed_text so callers that previously imported
# it from server still work via server's re-export chain.
from embeddings import _canonical_embed_text, _model_slot, _embed_upsert_fields  # noqa: F401

VALID_TYPES = ("user", "project", "decision", "feedback", "reference")


# #417: operational artifacts like session snapshots carry mixed transcript
# content that semantically matches a wide range of queries. They're meant
# to be fetched by name via memory_get during /end recovery, never to
# compete in normal recall. Filtering at the Python layer keeps the schema
# and RPCs untouched while measurably lifting recall@5.
EXCLUDE_TAGS_FROM_RECALL = frozenset({"session-snapshot"})


def _filter_excluded_tags(rows):
    """Drop rows whose tags overlap EXCLUDE_TAGS_FROM_RECALL. See #417."""
    if not rows or not EXCLUDE_TAGS_FROM_RECALL:
        return rows
    out = []
    for row in rows:
        tags = row.get("tags") or []
        if isinstance(tags, list) and any(t in EXCLUDE_TAGS_FROM_RECALL for t in tags):
            continue
        out.append(row)
    return out


TEMPORAL_HALF_LIVES = {
    "project": 7,
    "reference": 30,
    "decision": 60,
    "feedback": 90,
    "user": 180,
}
DEFAULT_HALF_LIFE = 30
ACCESS_BOOST_MAX = 0.3
ACCESS_HALF_LIFE = 14
# Phase 1 polish (#240): entrenchment multiplier (ACT-R / Gärdenfors). Folds
# memories.confidence into temporal score so low-confidence rows rank lower
# without a hard cutoff. final *= FLOOR + (1 - FLOOR) * confidence.
# NULL confidence → treated as 1.0 (no regression for legacy rows).
CONFIDENCE_FLOOR = 0.5
LINK_SIM_THRESHOLD = 0.60
# Phase 2b: classifier replaces the bare similarity gate. We still keep a
# threshold, but it now decides *when to ask the classifier*, not whether to
# fire supersession. The classifier's decision (with confidence) determines
# the actual ADD/UPDATE/DELETE/NOOP outcome.
SUPERSEDE_SIM_THRESHOLD = 0.85  # legacy heuristic — kept for fallback when classifier unavailable
CLASSIFIER_TRIGGER_SIM = (
    0.70  # invoke classifier above this similarity (voyage-3-lite paraphrases sit ~0.73)
)
CLASSIFIER_APPLY_THRESHOLD = 0.70  # auto-apply UPDATE/DELETE above this confidence; else queue
CONSOLIDATION_SIM_THRESHOLD = 0.80
CONSOLIDATION_COUNT = 3
MAX_AUTO_LINKS = 5
MAX_CLASSIFIER_NEIGHBORS = 5


SIMILARITY_THRESHOLD = 0.25  # minimum cosine similarity to include in results

GAP_THRESHOLD = 0.45  # known-unknowns: log gaps when top_similarity < this
GAP_DEDUP_SIM = 0.9


def _parse_pgvector(v: list[float] | str | None) -> list[float] | None:
    """Normalize a pgvector value returned by supabase-py.

    PostgREST returns vector columns as JSON-encoded strings
    (e.g. ``"[0.1,0.2,...]"``), not Python lists. Callers that pass the raw
    value into `_cosine_sim` hit the len-mismatch guard and silently score 0.
    Return a float list, or None if the value is missing / unparseable.
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


def _cosine_sim(v1: list[float] | None, v2: list[float] | None) -> float:
    """Cosine similarity between two embedding vectors. Returns 0.0 if either
    is None/empty or if lengths differ (dim mismatch would otherwise silently
    truncate via zip — important during embedding-model migrations)."""
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


async def _upsert_known_unknown(
    client,
    query: str,
    query_embedding: list[float] | None,
    top_similarity: float,
    top_memory_id: str | None,
    context: dict | None = None,
) -> None:
    """Insert or update a known unknown, with semantic dedup.

    Semantic dedup: if an open known_unknown exists with cosine sim > 0.9
    on query_embedding, increment hit_count instead of inserting.
    Best-effort; never raises.
    """
    # Schema declares query_embedding vector(512). If PRIMARY model produces
    # a different dim (e.g. voyage-3 = 1024), store without embedding rather
    # than letting the insert fail and get swallowed by the best-effort catch.
    if query_embedding and len(query_embedding) != 512:
        query_embedding = None

    try:
        if not query_embedding:
            # Fallback: upsert without embedding — select hit_count so the
            # increment reflects the stored value (not the default).
            existing = (
                client.table("known_unknowns")
                .select("id, hit_count")
                .eq("query", query)
                .eq("status", "open")
                .limit(1)
                .execute()
            )
            if existing.data:
                row = existing.data[0]
                client.table("known_unknowns").update(
                    {
                        "hit_count": row.get("hit_count", 1) + 1,
                        "last_seen_at": datetime.now(timezone.utc).isoformat(),
                    }
                ).eq("id", row["id"]).execute()
            else:
                client.table("known_unknowns").insert(
                    {
                        "query": query,
                        "query_embedding": None,
                        "top_similarity": top_similarity,
                        "top_memory_id": top_memory_id,
                        "context": context,
                    }
                ).execute()
            return

        # Semantic dedup: fetch open unknowns and check sim > 0.9.
        # Include hit_count in the select so the increment is correct.
        open_unknowns = (
            client.table("known_unknowns")
            .select("id, query_embedding, hit_count")
            .eq("status", "open")
            .execute()
        )
        for row in open_unknowns.data or []:
            stored_embedding = _parse_pgvector(row.get("query_embedding"))
            if stored_embedding and _cosine_sim(query_embedding, stored_embedding) > 0.9:
                # Semantic match: increment hit_count
                client.table("known_unknowns").update(
                    {
                        "hit_count": row.get("hit_count", 1) + 1,
                        "last_seen_at": datetime.now(timezone.utc).isoformat(),
                    }
                ).eq("id", row["id"]).execute()
                return

        # No match: insert new row
        client.table("known_unknowns").insert(
            {
                "query": query,
                "query_embedding": query_embedding,
                "top_similarity": top_similarity,
                "top_memory_id": top_memory_id,
                "context": context,
            }
        ).execute()
    except Exception:
        pass  # best-effort, never block recall on failure


async def _resolve_known_unknowns(client, memory_embedding: list[float], memory_id: str) -> None:
    """Scan open known_unknowns; mark as resolved if cosine(new_embedding, query_embedding) > 0.7.

    Best-effort; never raises.
    """
    try:
        open_unknowns = (
            client.table("known_unknowns")
            .select("id, query_embedding")
            .eq("status", "open")
            .execute()
        )
        now = datetime.now(timezone.utc).isoformat()
        for row in open_unknowns.data or []:
            stored_embedding = _parse_pgvector(row.get("query_embedding"))
            if stored_embedding and _cosine_sim(memory_embedding, stored_embedding) > 0.7:
                client.table("known_unknowns").update(
                    {
                        "status": "resolved",
                        "resolved_at": now,
                        "resolved_by_memory_id": memory_id,
                    }
                ).eq("id", row["id"]).execute()
    except Exception:
        pass  # best-effort, never block store on failure


async def _handle_recall(args: dict) -> list[TextContent]:
    client = server._get_client()

    query_text = args.get("query", "")
    project = args.get("project")
    if project == "global":
        project = None
    mem_type = args.get("type")
    limit = args.get("limit", 10)

    include_links = args.get("include_links", False)
    show_history = args.get("show_history", False)
    brief = args.get("brief", False)

    # Hybrid search: combine semantic + keyword results via RRF + temporal scoring
    if query_text:
        query_embedding = await server._embed_query(query_text)
        if query_embedding is not None:
            rows, results = await _hybrid_recall(
                client,
                query_embedding,
                query_text,
                project,
                mem_type,
                limit,
                include_links,
                show_history,
                brief,
            )
            # Track reads (fire-and-forget)
            ids = [r["id"] for r in rows if r.get("id")]
            if ids:
                asyncio.create_task(_touch_memories(client, ids))
            return results

    # Fallback: keyword-only search
    results = await server._keyword_recall(client, query_text, project, mem_type, limit, brief)

    # Lazily backfill embeddings for records missing them (fire-and-forget)
    if os.environ.get("VOYAGE_API_KEY"):
        asyncio.create_task(_backfill_missing_embeddings(client, project))

    return results


async def _hybrid_recall(
    client,
    query_embedding: list[float],
    query_text: str,
    project,
    mem_type,
    limit: int,
    include_links: bool = False,
    show_history: bool = False,
    brief: bool = False,
) -> tuple[list[dict], list[TextContent]]:
    """Hybrid search: server-side pgvector semantic + pg_trgm keyword, merged via RRF.

    Memory 2.0: adds temporal scoring (recency × access frequency) and optional
    1-hop link expansion for graph-aware recall.

    Phase 1: default filters out superseded/expired/valid_to-past memories via
    the RPC's show_history=false path. Pass show_history=true to bypass.
    """
    try:
        # Fetch double the limit from each source to give RRF good candidates
        fetch_limit = limit * 2

        # Server-side semantic search via pgvector HNSW. #242: the RPC name
        # is selected by PRIMARY model so v1 and v2 columns each use their
        # own HNSW index. query_embedding's dim was already matched to
        # PRIMARY by _embed_query.
        sem_rpc = _model_slot(server.EMBEDDING_MODEL_PRIMARY)["rpc"]
        sem_result = client.rpc(
            sem_rpc,
            {
                "query_embedding": query_embedding,
                "match_limit": fetch_limit,
                "similarity_threshold": SIMILARITY_THRESHOLD,
                "filter_project": project,
                "filter_type": mem_type,
                "show_history": show_history,
            },
        ).execute()
        # #417: filter operational artifacts (session snapshots) at the
        # Python layer so they never compete in semantic recall.
        semantic_rows = _filter_excluded_tags(sem_result.data or [])

        # Server-side keyword search via pg_trgm
        kw_result = client.rpc(
            "keyword_search_memories",
            {
                "search_query": query_text,
                "match_limit": fetch_limit,
                "filter_project": project,
                "filter_type": mem_type,
                "show_history": show_history,
            },
        ).execute()
        keyword_rows = _filter_excluded_tags(kw_result.data or [])

        # Reciprocal Rank Fusion (k=60) + temporal scoring
        merged = _rrf_merge(semantic_rows, keyword_rows, limit)

        if not merged:
            return [], await server._keyword_recall(
                client, query_text, project, mem_type, limit, brief
            )

        # Phase 1 polish (#240): match_memories RPC doesn't project confidence.
        # Enrich merged rows before scoring so entrenchment multiplier has data.
        _enrich_with_confidence(client, merged)
        _apply_temporal_scoring(merged)

        formatted = _format_memories(merged, brief=brief)
        search_type = "hybrid+temporal" if keyword_rows else "semantic+temporal"
        mode_tag = ", brief" if brief else ""
        text = f"Found {len(merged)} memories ({search_type} search{mode_tag}):\n\n" + (
            "\n".join(formatted) if brief else "\n---\n".join(formatted)
        )

        # Phase 5: gap detection — fire-and-forget so we don't add Supabase
        # round-trips to the recall hot path on low-match queries. Single
        # path; an earlier duplicate at GAP_THRESHOLD passed positional
        # Gap recording now owned by FOK batch processor (#445). Removed in 5.3-γ.

        # Optional: expand with 1-hop linked memories
        if include_links:
            ids = [r["id"] for r in merged if r.get("id")]
            if ids:
                linked = await _expand_with_links(client, ids, show_history=show_history)
                if linked:
                    # Deduplicate against already-found IDs and within linked results
                    found_ids = set(ids)
                    seen_linked = set()
                    unique_linked = []
                    for r in linked:
                        rid = r.get("id")
                        if rid not in found_ids and rid not in seen_linked:
                            seen_linked.add(rid)
                            unique_linked.append(r)
                    if unique_linked:
                        link_formatted = _format_memories(
                            unique_linked, link_info=True, brief=brief
                        )
                        text += f"\n\n### Linked memories ({len(unique_linked)}):\n\n" + (
                            "\n".join(link_formatted) if brief else "\n---\n".join(link_formatted)
                        )

        # Phase 5 metacognition: emit memory_recall event for FOK batch processing (#250).
        returned_ids = [r.get("id") for r in merged if r.get("id")]
        # Per-memory similarities (same length + order as returned_ids) so the
        # FOK judge can show true ranking instead of pinning every memory to
        # top_sim.
        returned_similarities = [
            float(r["similarity"]) if isinstance(r.get("similarity"), (int, float)) else None
            for r in merged
            if r.get("id")
        ]
        top_sim = merged[0].get("similarity", 0.0) if merged else 0.0
        payload = {
            "query": query_text,
            "returned_ids": returned_ids,
            "returned_similarities": returned_similarities,
            "returned_count": len(merged),
            "top_sim": float(top_sim),
            "threshold": SIMILARITY_THRESHOLD,
            "project": project,
            "type_filter": mem_type,
            "show_history": show_history,
        }
        asyncio.create_task(_emit_recall_event(client, payload))

        return merged, [TextContent(type="text", text=text)]

    except asyncio.CancelledError:
        raise
    except Exception:
        # RPC not available (e.g. migration not applied) — fall back to keyword
        return [], await server._keyword_recall(client, query_text, project, mem_type, limit, brief)


def _rrf_merge(
    semantic_rows: list[dict], keyword_rows: list[dict], limit: int, k: int = 60
) -> list[dict]:
    """Reciprocal Rank Fusion: combine two ranked lists into one.

    Score = sum(1 / (k + rank)) for each list the item appears in.
    Higher k gives more weight to items appearing in both lists.
    """
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

    ranked = sorted(scores.keys(), key=lambda r: scores[r], reverse=True)
    result = []
    for rid in ranked[:limit]:
        row = by_id[rid]
        row["_rrf_score"] = scores[rid]
        result.append(row)
    return result


async def _keyword_recall(
    client, query_text: str, project, mem_type, limit: int, brief: bool = False
) -> list[TextContent]:
    """ILIKE keyword search (fallback when semantic unavailable).

    In brief mode we skip the `content` column — it's never rendered and
    would bloat the fallback payload, which is hit precisely when the fast
    path failed and we're already on a slower code path.

    Lifecycle filters mirror the show_history=false branch of
    match_memories / keyword_search_memories: exclude soft-deleted,
    expired, superseded, and past-valid_to rows (#284).

    valid_to is filtered client-side (not via .or_()) because PostgREST
    accepts only one `or=` parameter per query, and this path already uses
    .or_() for project scoping and for the keyword ILIKE clauses — adding
    a third would silently overwrite one of them. Same pattern as
    scripts/session-context.py _load_recent_recall_results.
    """
    cols = (
        "id, name, type, project, description, tags, updated_at, valid_to"
        if brief
        else "id, name, type, project, description, content, tags, updated_at, valid_to"
    )
    q = (
        client.table("memories")
        .select(cols)
        .is_("deleted_at", "null")
        .is_("expired_at", "null")
        .is_("superseded_by", "null")
    )

    if project is not None:
        q = q.or_(f"project.eq.{project},project.is.null")
    if mem_type:
        q = q.eq("type", mem_type)

    if query_text:
        terms = query_text.split()
        clauses = ",".join(
            f"name.ilike.%{t}%,description.ilike.%{t}%,content.ilike.%{t}%" for t in terms
        )
        q = q.or_(clauses)

    # Fetch extra rows so the client-side valid_to filter still leaves `limit`
    # live rows in the worst case. 2x is a simple heuristic; tombstoned
    # valid_to rows are rare in practice.
    result = q.limit(limit * 2).order("updated_at", desc=True).execute()

    # #417: drop session-snapshot etc. before valid_to filter so the
    # `live` budget isn't burned on operational artifacts.
    candidate_rows = _filter_excluded_tags(result.data or [])

    now_utc = datetime.now(timezone.utc)
    live: list[dict] = []
    for row in candidate_rows:
        vt = row.get("valid_to")
        if vt is not None:
            try:
                vt_dt = datetime.fromisoformat(vt.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                vt_dt = None
            if vt_dt is not None and vt_dt <= now_utc:
                continue
        live.append(row)
        if len(live) >= limit:
            break

    if not live:
        return [TextContent(type="text", text="No memories found.")]

    formatted = _format_memories(live, brief=brief)
    mode_tag = ", brief" if brief else ""
    return [
        TextContent(
            type="text",
            text=f"Found {len(live)} memories (keyword search{mode_tag}):\n\n"
            + ("\n".join(formatted) if brief else "\n---\n".join(formatted)),
        )
    ]


async def _touch_memories(client, ids: list[str]) -> None:
    """Fire-and-forget: update last_accessed_at for accessed memories via RPC."""
    try:
        client.rpc("touch_memories", {"memory_ids": ids}).execute()
    except Exception:
        pass


async def _emit_recall_event(client, payload: dict) -> None:
    """Fire-and-forget: emit memory_recall event for FOK batch processing (#250)."""
    try:
        client.table("events").insert(
            {
                "event_type": "memory_recall",
                "severity": "info",
                "repo": "Osasuwu/jarvis",
                "source": "mcp_memory",
                "title": f"Memory recall: {payload.get('query', '')[:60]}",
                "payload": payload,
            }
        ).execute()
    except Exception:
        pass


def _format_memories(
    memories: list[dict], link_info: bool = False, brief: bool = False
) -> list[str]:
    """Format memory rows for display.

    brief=False (default): full markdown block with header + description +
    updated_at + content. Suited to a Jarvis-driven targeted recall where the
    whole memory needs to land in the prompt.

    brief=True: single-line `- name [type/project] (score): description`.
    Suited to bulk/auto injection (UserPromptSubmit hook) where the agent
    should preview what's relevant and pull full content via memory_get on
    hits it actually wants. Content-free, so it can't rot long answers.
    """
    formatted = []
    for mem in memories:
        tags_str = f" [{', '.join(mem.get('tags', []))}]" if mem.get("tags") else ""
        link_str = ""
        if link_info and mem.get("link_type"):
            link_str = f" ← {mem['link_type']}"
            if mem.get("link_strength"):
                link_str += f" ({mem['link_strength']:.2f})"
        proj = mem.get("project") or "global"
        if brief:
            # `_temporal_score` (set by _apply_temporal_scoring) is the actual
            # sort key after rrf × recency × access × entrenchment. Show it
            # first so the displayed value matches the displayed order.
            # Retrieval provenance (rrf/sim/rank) follows as secondary signal
            # — useful for debugging why a row surfaced at all.
            temporal = mem.get("_temporal_score")
            rrf = mem.get("_rrf_score")
            sim = mem.get("similarity")
            rank = mem.get("rank")
            base_parts = []
            if rrf is not None:
                base_parts.append(f"rrf {rrf:.3f}")
            elif isinstance(sim, (int, float)):
                base_parts.append(f"sim {sim:.2f}")
            elif isinstance(rank, (int, float)):
                base_parts.append(f"rank {rank:.2f}")
            if isinstance(temporal, (int, float)):
                lead = f"score {temporal:.3f}"
                score_str = f" ({lead}; {base_parts[0]})" if base_parts else f" ({lead})"
            elif base_parts:
                score_str = f" ({base_parts[0]})"
            else:
                score_str = ""
            desc = (mem.get("description") or "").strip()
            formatted.append(
                f"- {mem['name']} [{mem['type']}/{proj}]{tags_str}{score_str}{link_str}: {desc} — id={mem.get('id', '?')}"
            )
        else:
            formatted.append(
                f"## {mem['name']} ({mem['type']}, {proj}){tags_str}{link_str} — id=`{mem.get('id', '?')}`\n"
                f"*{mem.get('description', '')}*\n"
                f"Updated: {mem.get('updated_at', '?')}\n\n"
                f"{mem['content']}\n"
            )
    return formatted


async def _backfill_missing_embeddings(client, project) -> None:
    """Fire-and-forget: generate embeddings for records saved without one.

    Batches all missing records into a single Voyage AI call.
    """
    try:
        # #242: backfill the column that matches PRIMARY — if we've cut over
        # to v2, the "missing embedding" we care about is embedding_v2.
        primary_col = _model_slot(server.EMBEDDING_MODEL_PRIMARY)["embedding_column"]
        q = client.table("memories").select("id, name, description, tags, content")
        q = q.is_(primary_col, "null").is_("deleted_at", "null")
        if project is not None:
            q = q.or_(f"project.eq.{project},project.is.null")
        rows = q.execute().data
        if not rows:
            return

        # Phase 2a: canonical form (name + tags + description + content)
        texts = [
            _canonical_embed_text(
                r.get("name", ""), r.get("description", ""), r.get("tags") or [], r["content"]
            )
            for r in rows
        ]
        # #242: this path only backfills the column for PRIMARY — the legacy
        # "missing embedding" cleanup. v2 corpus-wide backfill is a separate
        # issue per #242 non-goals.
        embeddings = await server._embed_batch(texts, model=server.EMBEDDING_MODEL_PRIMARY)
        if embeddings is None:
            return

        for mem, embedding in zip(rows, embeddings):
            client.table("memories").update(
                _embed_upsert_fields(embedding, server.EMBEDDING_MODEL_PRIMARY)
            ).eq("id", mem["id"]).execute()
    except Exception:
        pass  # fire-and-forget: silently swallow all errors so caller never fails


async def _create_auto_links(
    client,
    stored_id: str,
    similar_rows: list[dict],
    mem_type: str,
    candidate: dict | None = None,
) -> None:
    """Fire-and-forget: create links + apply Phase 2b classifier decision.

    Pipeline:
      1. Always create `related` links to every neighbor (graph signal).
      2. For neighbors above CLASSIFIER_TRIGGER_SIM, ask the Haiku
         classifier to choose ADD / UPDATE / DELETE / NOOP.
      3. confidence >= CLASSIFIER_APPLY_THRESHOLD → apply the decision
         immediately (UPDATE: target.superseded_by = stored_id;
         DELETE: target.expired_at = now()). Record as auto_applied
         in memory_review_queue for audit.
      4. confidence < threshold → record in queue with status=pending,
         do NOT mutate the target. Owner reviews later.
      5. classifier unavailable (no API key, network fail, no candidate
         metadata) → fall back to the legacy SUPERSEDE_SIM_THRESHOLD
         heuristic so we never regress to "do nothing".
    """
    try:
        # --- (1) base links: everything is `related` until a classifier upgrade ---
        links = []
        for row in similar_rows[:MAX_AUTO_LINKS]:
            links.append(
                {
                    "source_id": stored_id,
                    "target_id": row["id"],
                    "link_type": "related",
                    "strength": round(row.get("similarity", 0), 3),
                }
            )
        if links:
            client.table("memory_links").upsert(
                links, on_conflict="source_id,target_id,link_type"
            ).execute()

        # --- (2) classifier or fallback heuristic ---
        # Pick the high-similarity slice we'd consider for supersession.
        candidates_for_classifier = [
            r
            for r in similar_rows[:MAX_CLASSIFIER_NEIGHBORS]
            if r.get("similarity", 0) >= CLASSIFIER_TRIGGER_SIM
        ]
        if not candidates_for_classifier:
            return  # nothing close enough — pure ADD, no supersession to consider

        decision = None
        if candidate is not None and classify_write is not None:
            # Hydrate neighbors with description/content for richer prompting.
            # find_similar_memories only returns id/name/type/similarity.
            hydrated = await _hydrate_neighbors(client, candidates_for_classifier)
            try:
                decision = await classify_write(candidate, hydrated)
            except Exception:
                decision = None

        if decision is not None:
            await _apply_classifier_decision(client, stored_id, decision, candidates_for_classifier)
        else:
            # Legacy heuristic fallback: same-type + sim >= 0.85 → supersede.
            await _apply_legacy_supersede(client, stored_id, candidates_for_classifier, mem_type)
    except Exception:
        pass


async def _hydrate_neighbors(client, rows: list[dict]) -> list[dict]:
    """Fetch description+content for the neighbor rows so the classifier
    prompt has real context, not just names."""
    ids = [r["id"] for r in rows if r.get("id")]
    if not ids:
        return rows
    try:
        full = (
            client.table("memories")
            .select("id, name, type, description, content, tags")
            .in_("id", ids)
            .execute()
        )
        full_by_id = {row["id"]: row for row in (full.data or [])}
    except Exception:
        return rows

    hydrated = []
    for r in rows:
        extra = full_by_id.get(r.get("id"), {})
        hydrated.append(
            {
                "id": r.get("id"),
                "name": r.get("name") or extra.get("name", ""),
                "type": r.get("type") or extra.get("type", ""),
                "similarity": r.get("similarity", 0),
                "description": extra.get("description", ""),
                "content": extra.get("content", ""),
                "tags": extra.get("tags", []) or [],
            }
        )
    return hydrated


async def _apply_classifier_decision(
    client,
    stored_id: str,
    decision,  # ClassifierDecision
    neighbors: list[dict],
) -> None:
    """Apply the classifier's ADD/UPDATE/DELETE/NOOP decision and record
    it in memory_review_queue (auto_applied if high confidence, pending if
    we want a human in the loop).

    The candidate is *already* persisted by the time we get here — that's
    intentional, we never lose data. UPDATE/DELETE only mutate the target.
    """
    apply_now = decision.confidence >= CLASSIFIER_APPLY_THRESHOLD

    target_id = decision.target_id
    if decision.decision in ("UPDATE", "DELETE") and target_id:
        # Sanity check: target_id must be one of the neighbors we showed it.
        # Otherwise the model hallucinated an id — refuse to mutate.
        valid_ids = {n.get("id") for n in neighbors}
        if target_id not in valid_ids:
            target_id = None
            apply_now = False

    if decision.decision == "ADD":
        # ADD just confirms the upsert we already did. No queue entry needed
        # unless the classifier had low confidence (then we want a record).
        if decision.confidence >= CLASSIFIER_APPLY_THRESHOLD:
            return
        queue_status = "pending"
        applied_at = None
    elif apply_now and target_id and decision.decision == "UPDATE":
        # Try to mutate; only mark auto_applied if the row was actually changed.
        # rowcount==0 happens when the target was already superseded by someone
        # else — a real race we want to flag for review, not silently overwrite.
        mutated = False
        try:
            res = (
                client.table("memories")
                .update({"superseded_by": stored_id})
                .eq("id", target_id)
                .is_("superseded_by", "null")
                .execute()
            )
            mutated = bool(getattr(res, "data", None))
        except Exception:
            mutated = False
        if mutated:
            # Upgrade the auto-created `related` link to `supersedes` so the
            # graph reflects the supersession (matches legacy fallback behavior).
            try:
                client.table("memory_links").upsert(
                    {
                        "source_id": stored_id,
                        "target_id": target_id,
                        "link_type": "supersedes",
                        "strength": 1.0,
                    },
                    on_conflict="source_id,target_id,link_type",
                ).execute()
            except Exception:
                pass  # link upgrade is cosmetic; don't roll back the supersession
            queue_status = "auto_applied"
            applied_at = datetime.now(timezone.utc).isoformat()
        else:
            queue_status = "pending"
            applied_at = None
    elif apply_now and target_id and decision.decision == "DELETE":
        mutated = False
        try:
            res = (
                client.table("memories")
                .update(
                    {
                        "expired_at": datetime.now(timezone.utc).isoformat(),
                    }
                )
                .eq("id", target_id)
                .is_("expired_at", "null")
                .execute()
            )
            mutated = bool(getattr(res, "data", None))
        except Exception:
            mutated = False
        if mutated:
            queue_status = "auto_applied"
            applied_at = datetime.now(timezone.utc).isoformat()
        else:
            queue_status = "pending"
            applied_at = None
    elif apply_now and decision.decision == "NOOP":
        # NOOP: nothing to mutate, but the decision was applied (no-op is the
        # desired state). Record as auto_applied for audit.
        queue_status = "auto_applied"
        applied_at = datetime.now(timezone.utc).isoformat()
    else:
        # Low confidence (or UPDATE/DELETE without a valid target) — queue for review.
        queue_status = "pending"
        applied_at = None

    # Record the decision (always — auditability).
    try:
        client.table("memory_review_queue").insert(
            {
                "candidate_id": stored_id,
                "decision": decision.decision,
                "target_id": target_id,
                "confidence": round(decision.confidence, 3),
                "reasoning": decision.reasoning,
                "classifier_model": CLASSIFIER_MODEL,
                "neighbors_seen": [
                    {
                        "id": n.get("id"),
                        "name": n.get("name"),
                        "similarity": round(n.get("similarity", 0), 3),
                    }
                    for n in neighbors
                ],
                "status": queue_status,
                "applied_at": applied_at,
            }
        ).execute()
    except Exception:
        pass


async def _apply_legacy_supersede(
    client, stored_id: str, similar_rows: list[dict], mem_type: str
) -> None:
    """Fallback used when the classifier is unavailable. Same logic as
    pre-Phase-2b: same-type + similarity >= SUPERSEDE_SIM_THRESHOLD →
    mark target.superseded_by = stored_id."""
    supersede_target_ids = [
        r["id"]
        for r in similar_rows
        if r.get("type") == mem_type
        and r.get("similarity", 0) >= SUPERSEDE_SIM_THRESHOLD
        and r.get("id")
    ]
    if not supersede_target_ids:
        return
    try:
        client.table("memories").update({"superseded_by": stored_id}).in_(
            "id", supersede_target_ids
        ).is_("superseded_by", "null").execute()
        # Also upgrade the link type from `related` to `supersedes`.
        for tid in supersede_target_ids:
            client.table("memory_links").upsert(
                {
                    "source_id": stored_id,
                    "target_id": tid,
                    "link_type": "supersedes",
                    "strength": 1.0,
                },
                on_conflict="source_id,target_id,link_type",
            ).execute()
    except Exception:
        pass


async def _expand_with_links(
    client,
    memory_ids: list[str],
    show_history: bool = False,
) -> list[dict]:
    """Fetch 1-hop linked memories via graph traversal RPC.

    show_history mirrors the primary recall flag: when true, skip the
    lifecycle filter so history views don't drop linked neighbors.
    """
    try:
        result = client.rpc(
            "get_linked_memories",
            {
                "memory_ids": memory_ids,
                "link_types": None,
                "show_history": show_history,
            },
        ).execute()
        return result.data or []
    except Exception:
        return []


def _enrich_with_confidence(client, rows: list[dict]) -> None:
    """Backfill `confidence` on rows that came from match_memories (which doesn't
    project it). Batched SELECT keeps this cheap. Best-effort: on error we leave
    rows untouched and scoring falls back to the NULL→1.0 branch.

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


def _apply_temporal_scoring(rows: list[dict]) -> list[dict]:
    """Re-rank rows by combining RRF score with temporal decay and access frequency."""
    now = datetime.now(timezone.utc)
    for row in rows:
        rrf = row.get("_rrf_score", 0.01)
        mem_type = row.get("type", "decision")
        half_life = TEMPORAL_HALF_LIVES.get(mem_type, DEFAULT_HALF_LIFE)

        # Parse content_updated_at (Phase 1: decay is driven by content edits,
        # not any write — touch_memories bumps updated_at on every recall).
        # Fall back to updated_at for rows backfilled before Phase 0.
        updated_str = row.get("content_updated_at") or row.get("updated_at", "")
        try:
            updated = datetime.fromisoformat(updated_str.replace("Z", "+00:00"))
            days_since_update = max(0, (now - updated).total_seconds() / 86400)
        except (ValueError, AttributeError):
            days_since_update = half_life  # assume mid-decay if unparsable

        # Parse last_accessed_at
        accessed_str = row.get("last_accessed_at") or ""
        try:
            accessed = datetime.fromisoformat(accessed_str.replace("Z", "+00:00"))
            days_since_access = max(0, (now - accessed).total_seconds() / 86400)
        except (ValueError, AttributeError):
            days_since_access = days_since_update * 2  # never accessed = low boost

        # Exponential decay: recency factor (0..1)
        recency = math.exp(-0.693 * days_since_update / half_life)
        # Access frequency boost (1..1+ACCESS_BOOST_MAX)
        access = 1.0 + ACCESS_BOOST_MAX * math.exp(-0.693 * days_since_access / ACCESS_HALF_LIFE)

        # Entrenchment multiplier (Phase 1 polish #240). NULL confidence treated
        # as 1.0 so legacy rows don't regress; FLOOR ensures confidence=0 only
        # halves the score rather than zeroing it.
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


async def _handle_store(args: dict) -> list[TextContent]:
    client = server._get_client()

    mem_type = args["type"]
    mem_name = args["name"]
    content = args["content"]
    description = args.get("description", "")
    project = args.get("project")
    if project == "global":
        project = None  # "global" and null are synonymous — normalize to NULL in DB
    tags = args.get("tags", [])
    source_provenance = args.get("source_provenance")

    if mem_type not in VALID_TYPES:
        return [
            TextContent(type="text", text=f"Invalid type: {mem_type}. Must be one of {VALID_TYPES}")
        ]

    # Phase 2c: provenance required. Reject at the MCP boundary so callers get
    # a readable error instead of a NOT NULL violation from Postgres. Strip
    # whitespace so an accidental " " doesn't pass the guard.
    source_provenance = (source_provenance or "").strip()
    if not source_provenance:
        return [
            TextContent(
                type="text",
                text=(
                    "Error: source_provenance is required (Phase 2c). "
                    "Use a namespaced source like 'session:<id>', 'skill:<name>', "
                    "'hook:<name>', 'user:explicit', or 'episode:<id>'. This is the "
                    "JTMS attribution for this memory — without it, future revisions "
                    "can't be traced."
                ),
            )
        ]

    # Phase 2a: canonical-form embedding — include name + tags + description + content.
    # Name and tags carry high-signal lexical cues that raw content often dilutes
    # (long narrative memories where the key topic is only in the name).
    embed_text = _canonical_embed_text(mem_name, description, tags, content)
    # #242: may populate embedding + embedding_v2 in one shot when SECONDARY set.
    embed_fields = await server._compute_write_embeddings(embed_text)

    data = {
        "type": mem_type,
        "name": mem_name,
        "content": content,
        "description": description,
        "project": project,
        "tags": tags,
        "source_provenance": source_provenance,  # Phase 2c: always present, validated above
        "deleted_at": None,  # clear soft-delete on store/upsert
    }
    data.update(embed_fields)

    # Preserve the old "derive embedding column presence" cue for the user
    # message — we care whether PRIMARY landed.
    embedding = data.get(_model_slot(server.EMBEDDING_MODEL_PRIMARY)["embedding_column"])
    embed_note = " (with embedding)" if embedding is not None else ""

    if project is not None:
        # Atomic upsert via unique constraint on (project, name) — no race condition
        result = client.table("memories").upsert(data, on_conflict="project,name").execute()
        stored_id = result.data[0]["id"] if result.data else None
        action = "saved"
        proj_label = f"project={project}"
    else:
        # Manual upsert for NULL project: PostgreSQL unique constraint doesn't
        # deduplicate NULLs, so we handle this case explicitly.
        q = client.table("memories").select("id").eq("name", mem_name).is_("project", "null")
        existing = q.limit(1).execute()
        if existing.data:
            stored_id = existing.data[0]["id"]
            client.table("memories").update(data).eq("id", stored_id).execute()
            action = "updated"
        else:
            result = client.table("memories").insert(data).execute()
            stored_id = result.data[0]["id"] if result.data else None
            action = "created"
        proj_label = "project=global"

    msg = f"Memory '{mem_name}' {action} ({proj_label}){embed_note}"

    server._audit_log(
        client, "memory_store", action, mem_name, {"project": project or "global", "type": mem_type}
    )

    # -- Memory 2.0: auto-linking + consolidation hints --
    if embedding is not None and stored_id:
        try:
            similar = client.rpc(
                "find_similar_memories",
                {
                    "query_embedding": embedding,
                    "exclude_id": stored_id,
                    "match_limit": MAX_AUTO_LINKS + 5,
                    "similarity_threshold": LINK_SIM_THRESHOLD,
                    "filter_type": None,
                },
            ).execute()
            similar_rows = similar.data or []

            # Consolidation hint: 3+ memories above 0.80 similarity
            consolidation_candidates = [
                r for r in similar_rows if r.get("similarity", 0) >= CONSOLIDATION_SIM_THRESHOLD
            ]
            if len(consolidation_candidates) >= CONSOLIDATION_COUNT:
                names = [r["name"] for r in consolidation_candidates[:5]]
                msg += f"\n\n⚠ Consolidation hint: {len(consolidation_candidates)} similar memories found: {', '.join(names)}"

            # Fire-and-forget: classify (Phase 2b) + create links.
            # We pass the candidate so the classifier has full context;
            # _create_auto_links falls back to the legacy heuristic if the
            # classifier is unavailable.
            if similar_rows:
                candidate_for_classifier = {
                    "name": mem_name,
                    "type": mem_type,
                    "description": description,
                    "content": content,
                    "tags": tags,
                }
                asyncio.create_task(
                    _create_auto_links(
                        client,
                        stored_id,
                        similar_rows,
                        mem_type,
                        candidate=candidate_for_classifier,
                    )
                )

            # Phase 5: resolve gaps
            try:
                open_gaps = (
                    client.table("known_unknowns")
                    .select("id, query_embedding")
                    .eq("status", "open")
                    .limit(100)
                    .execute()
                )
                for gap in open_gaps.data or []:
                    gap_emb = _parse_pgvector(gap.get("query_embedding"))
                    if gap_emb and embedding and _cosine_sim(embedding, gap_emb) > 0.7:
                        client.table("known_unknowns").update(
                            {
                                "status": "resolved",
                                "resolved_at": datetime.now(timezone.utc).isoformat(),
                                "resolved_by_memory_id": stored_id,
                            }
                        ).eq("id", gap["id"]).execute()
            except Exception:
                pass
        except Exception:
            pass  # auto-linking is best-effort, never blocks store

        # Resolve known unknowns: if stored memory matches any open unknown > 0.7 similarity,
        # mark as resolved (fire-and-forget, best-effort)
        asyncio.create_task(_resolve_known_unknowns(client, embedding, stored_id))

    return [TextContent(type="text", text=msg)]


async def _handle_get(args: dict) -> list[TextContent]:
    client = server._get_client()

    mem_name = args["name"]
    project = args.get("project")
    if project == "global":
        project = None

    q = client.table("memories").select("*").eq("name", mem_name).is_("deleted_at", "null")
    if project is not None:
        q = q.eq("project", project)
    else:
        q = q.is_("project", "null")

    result = q.limit(1).execute()

    if not result.data:
        return [
            TextContent(
                type="text", text=f"Memory '{mem_name}' not found (project={project or 'global'})."
            )
        ]

    mem = result.data[0]
    tags_str = f"\nTags: {', '.join(mem.get('tags', []))}" if mem.get("tags") else ""
    return [
        TextContent(
            type="text",
            text=(
                f"## {mem['name']}\n"
                f"Type: {mem['type']} | Project: {mem.get('project') or 'global'}{tags_str}\n"
                f"Created: {mem.get('created_at')} | Updated: {mem.get('updated_at')}\n"
                f"Description: {mem.get('description', '')}\n\n"
                f"{mem['content']}"
            ),
        )
    ]


async def _handle_list(args: dict) -> list[TextContent]:
    client = server._get_client()

    project = args.get("project")
    if project == "global":
        project = None
    mem_type = args.get("type")

    q = (
        client.table("memories")
        .select("name, type, project, description, updated_at")
        .is_("deleted_at", "null")
    )

    if project is not None:
        q = q.or_(f"project.eq.{project},project.is.null")
    if mem_type:
        q = q.eq("type", mem_type)

    result = q.order("type").order("updated_at", desc=True).execute()

    if not result.data:
        return [TextContent(type="text", text="No memories found.")]

    lines = []
    current_type = None
    for mem in result.data:
        if mem["type"] != current_type:
            current_type = mem["type"]
            lines.append(f"\n### {current_type.upper()}")
        proj = mem.get("project") or "global"
        desc = f" — {mem['description']}" if mem.get("description") else ""
        lines.append(f"- **{mem['name']}** ({proj}){desc}")

    return [
        TextContent(
            type="text", text=f"## All Memories ({len(result.data)} total)\n" + "\n".join(lines)
        )
    ]


async def _handle_delete(args: dict) -> list[TextContent]:
    client = server._get_client()

    mem_name = args["name"]
    project = args.get("project")
    if project == "global":
        project = None  # normalize "global" → NULL, same as in _handle_store

    q = (
        client.table("memories")
        .update({"deleted_at": datetime.now(timezone.utc).isoformat()})
        .eq("name", mem_name)
        .is_("deleted_at", "null")
    )
    if project is not None:
        q = q.eq("project", project)
    else:
        q = q.is_("project", "null")

    result = q.execute()

    if result.data:
        server._audit_log(
            client, "memory_delete", "soft_delete", mem_name, {"project": project or "global"}
        )
        return [
            TextContent(
                type="text",
                text=f"Soft-deleted memory '{mem_name}' (project={project or 'global'}). Recoverable for 30 days via memory_restore.",
            )
        ]
    return [TextContent(type="text", text=f"Memory '{mem_name}' not found.")]


async def _handle_restore(args: dict) -> list[TextContent]:
    client = server._get_client()

    mem_name = args["name"]
    project = args.get("project")
    if project == "global":
        project = None

    q = (
        client.table("memories")
        .update({"deleted_at": None})
        .eq("name", mem_name)
        .not_.is_("deleted_at", "null")
    )
    if project is not None:
        q = q.eq("project", project)
    else:
        q = q.is_("project", "null")

    result = q.execute()

    if result.data:
        server._audit_log(
            client, "memory_restore", "restore", mem_name, {"project": project or "global"}
        )
        return [
            TextContent(
                type="text", text=f"Restored memory '{mem_name}' (project={project or 'global'})."
            )
        ]
    return [TextContent(type="text", text=f"No soft-deleted memory '{mem_name}' found.")]


# -- Graph handlers ---------------------------------------------------------


async def _handle_graph(args: dict) -> list[TextContent]:
    mode = args.get("mode", "overview")
    client = server._get_client()

    if mode == "overview":
        return await _graph_overview(client)
    elif mode == "links":
        name = args.get("name")
        if not name:
            return [TextContent(type="text", text="Error: 'name' is required for 'links' mode.")]
        return await _graph_links(client, name)
    elif mode == "clusters":
        return await _graph_clusters(client)
    else:
        return [TextContent(type="text", text=f"Unknown graph mode: {mode}")]


async def _graph_overview(client) -> list[TextContent]:
    """Graph overview: link stats, top connected memories, orphans."""
    lines = ["## Memory Graph Overview\n"]

    # 1. Link stats by type
    all_links = client.table("memory_links").select("link_type, strength").execute()
    link_data = all_links.data or []
    total = len(link_data)

    if total == 0:
        return [
            TextContent(
                type="text", text="No memory links found. Store more memories to build the graph."
            )
        ]

    type_stats: dict[str, list[float]] = {}
    for row in link_data:
        lt = row["link_type"]
        type_stats.setdefault(lt, []).append(row["strength"])

    lines.append(f"### Link Statistics ({total} total)\n")
    lines.append("| Type | Count | Avg Strength | Min | Max |")
    lines.append("|------|-------|-------------|-----|-----|")
    for lt, strengths in sorted(type_stats.items()):
        avg = sum(strengths) / len(strengths)
        lines.append(
            f"| {lt} | {len(strengths)} | {avg:.3f} | {min(strengths):.3f} | {max(strengths):.3f} |"
        )

    # 2. Top connected memories
    links_src = client.table("memory_links").select("source_id").execute()
    links_tgt = client.table("memory_links").select("target_id").execute()
    counts: dict[str, int] = {}
    for row in links_src.data or []:
        mid = row["source_id"]
        counts[mid] = counts.get(mid, 0) + 1
    for row in links_tgt.data or []:
        mid = row["target_id"]
        counts[mid] = counts.get(mid, 0) + 1

    top_ids = sorted(counts.keys(), key=lambda k: counts[k], reverse=True)[:10]
    if top_ids:
        # Fetch names for top IDs
        names_result = (
            client.table("memories")
            .select("id, name, type, project")
            .in_("id", top_ids)
            .is_("deleted_at", "null")
            .execute()
        )
        id_to_mem = {r["id"]: r for r in (names_result.data or [])}

        lines.append(f"\n### Top Connected ({len(top_ids)})\n")
        lines.append("| Memory | Type | Project | Links |")
        lines.append("|--------|------|---------|-------|")
        for mid in top_ids:
            mem = id_to_mem.get(mid, {})
            name = mem.get("name", mid[:8])
            mtype = mem.get("type", "?")
            proj = mem.get("project") or "global"
            lines.append(f"| {name} | {mtype} | {proj} | {counts[mid]} |")

    # 3. Orphans (have embedding, no links)
    total_with_emb = (
        client.table("memories")
        .select("id", count="exact")
        .not_.is_("embedding", "null")
        .is_("deleted_at", "null")
        .execute()
    )
    total_emb_count = total_with_emb.count or 0
    linked_ids = set(counts.keys())
    all_emb = (
        client.table("memories")
        .select("id, name, type, project")
        .not_.is_("embedding", "null")
        .is_("deleted_at", "null")
        .execute()
    )
    orphans = [r for r in (all_emb.data or []) if r["id"] not in linked_ids]

    lines.append(
        f"\n### Orphans ({len(orphans)} of {total_emb_count} embedded memories have no links)\n"
    )
    if orphans:
        for o in orphans[:15]:
            proj = o.get("project") or "global"
            lines.append(f"- **{o['name']}** ({o['type']}, {proj})")
        if len(orphans) > 15:
            lines.append(f"- ... and {len(orphans) - 15} more")

    return [TextContent(type="text", text="\n".join(lines))]


async def _graph_links(client, name: str) -> list[TextContent]:
    """All connections for a specific memory."""
    # Find memory by name
    mem_result = (
        client.table("memories")
        .select("id, name, type, project")
        .eq("name", name)
        .is_("deleted_at", "null")
        .execute()
    )
    if not mem_result.data:
        return [TextContent(type="text", text=f"Memory '{name}' not found.")]

    mem = mem_result.data[0]
    mem_id = mem["id"]
    proj = mem.get("project") or "global"

    lines = [f"## Links for: {name} ({mem['type']}, {proj})\n"]

    # Outgoing links (this memory → others)
    out_result = (
        client.table("memory_links")
        .select("target_id, link_type, strength")
        .eq("source_id", mem_id)
        .order("strength", desc=True)
        .execute()
    )
    out_links = out_result.data or []

    # Incoming links (others → this memory)
    in_result = (
        client.table("memory_links")
        .select("source_id, link_type, strength")
        .eq("target_id", mem_id)
        .order("strength", desc=True)
        .execute()
    )
    in_links = in_result.data or []

    # Resolve target/source names
    all_ids = [r["target_id"] for r in out_links] + [r["source_id"] for r in in_links]
    id_to_name = {}
    if all_ids:
        names = (
            client.table("memories")
            .select("id, name, type, project")
            .in_("id", all_ids)
            .is_("deleted_at", "null")
            .execute()
        )
        id_to_name = {r["id"]: r for r in (names.data or [])}

    # Format outgoing
    lines.append(f"### Outgoing ({len(out_links)})\n")
    if out_links:
        for link in out_links:
            target = id_to_name.get(link["target_id"], {})
            tname = target.get("name", link["target_id"][:8])
            ttype = target.get("type", "?")
            lines.append(f"- → **{tname}** ({ttype}) [{link['link_type']}, {link['strength']:.3f}]")
    else:
        lines.append("- (none)")

    # Format incoming
    lines.append(f"\n### Incoming ({len(in_links)})\n")
    if in_links:
        for link in in_links:
            source = id_to_name.get(link["source_id"], {})
            sname = source.get("name", link["source_id"][:8])
            stype = source.get("type", "?")
            lines.append(f"- ← **{sname}** ({stype}) [{link['link_type']}, {link['strength']:.3f}]")
    else:
        lines.append("- (none)")

    return [TextContent(type="text", text="\n".join(lines))]


async def _graph_clusters(client) -> list[TextContent]:
    """Find clusters of tightly connected memories (mutual links, strength > 0.7)."""
    # Get all strong links
    links_result = (
        client.table("memory_links")
        .select("source_id, target_id, link_type, strength")
        .gte("strength", 0.7)
        .execute()
    )
    links = links_result.data or []

    if not links:
        return [TextContent(type="text", text="No strong links (strength >= 0.7) found.")]

    # Build adjacency: collect neighbors for each memory
    neighbors: dict[str, set[str]] = {}
    link_info: dict[tuple[str, str], dict] = {}
    for link in links:
        s, t = link["source_id"], link["target_id"]
        neighbors.setdefault(s, set()).add(t)
        neighbors.setdefault(t, set()).add(s)
        link_info[(s, t)] = link

    # Simple clustering: connected components via BFS
    visited: set[str] = set()
    clusters: list[set[str]] = []
    for node in neighbors:
        if node in visited:
            continue
        cluster: set[str] = set()
        queue = [node]
        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            cluster.add(current)
            for neighbor in neighbors.get(current, set()):
                if neighbor not in visited:
                    queue.append(neighbor)
        if len(cluster) >= 2:
            clusters.append(cluster)

    # Sort clusters by size (largest first)
    clusters.sort(key=len, reverse=True)

    # Resolve names
    all_ids = list(set().union(*clusters)) if clusters else []
    id_to_mem = {}
    if all_ids:
        mems = (
            client.table("memories")
            .select("id, name, type, project")
            .in_("id", all_ids)
            .is_("deleted_at", "null")
            .execute()
        )
        id_to_mem = {r["id"]: r for r in (mems.data or [])}

    lines = [f"## Memory Clusters ({len(clusters)} clusters, strength >= 0.7)\n"]

    for i, cluster in enumerate(clusters[:10], 1):
        # Calculate average internal strength
        internal_strengths = []
        for s, t in link_info:
            if s in cluster and t in cluster:
                internal_strengths.append(link_info[(s, t)]["strength"])

        avg_str = sum(internal_strengths) / len(internal_strengths) if internal_strengths else 0

        lines.append(f"### Cluster {i} ({len(cluster)} memories, avg strength: {avg_str:.3f})\n")
        for mid in sorted(cluster, key=lambda m: id_to_mem.get(m, {}).get("name", "")):
            mem = id_to_mem.get(mid, {})
            name = mem.get("name", mid[:8])
            mtype = mem.get("type", "?")
            proj = mem.get("project") or "global"
            lines.append(f"- **{name}** ({mtype}, {proj})")
        lines.append("")

    if len(clusters) > 10:
        lines.append(f"... and {len(clusters) - 10} more clusters")

    return [TextContent(type="text", text="\n".join(lines))]
