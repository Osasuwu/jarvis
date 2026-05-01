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
