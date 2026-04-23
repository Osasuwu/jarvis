"""UserPromptSubmit hook: task-aware hybrid recall injected as context.

Phase 3: LLM rewriter + fan-out. On each prompt we do, in parallel:
  1. Embed the prompt (voyage-3-lite) for semantic search.
  2. Call Haiku-4.5 to extract {entities, types} — literal keywords that
     are likely to appear in relevant memories, plus an optional type
     narrowing hint.
Then we run `match_memories` (semantic) and `keyword_search_memories`
(FTS on entities if available, else on the raw prompt) and merge both
ranked lists via Reciprocal Rank Fusion (RRF, k=60).

Why a rewriter? The raw prompt carries a lot of noise ("help me", "can
you", conversational glue). FTS on that gives diluted matches. Haiku
strips the prompt to its literal content signal (proper nouns, paths,
technical identifiers) — the kind of tokens that match memories by
keyword but not semantically.

Types ∈ {feedback, decision, reference}. Scope: current project (cwd
basename) + global. `user` + `project` are already loaded at session
start by scripts/session-context.py and excluded here to avoid
duplication.

Phase 7.2: by default emits **brief** entries (one line per hit —
name + type/project + tags + score + description). The agent previews
what's relevant and calls memory_get(name=...) on anything worth
reading, instead of every UserPromptSubmit paying ~40KB of full
content. Legacy full mode still available via BRIEF_MODE=False for
debugging.

Phase 7.3: per-prompt gate on `known_unknowns`. Before emitting, we
cosine-compare the prompt embedding against open known_unknowns (topics
where recall has been historically weak). A match above threshold
widens this invocation back to full-content + CHAR_BUDGET_FULL — the
signal says "brief isn't enough for this one". Default brief path is
untouched on a miss.

Touches accessed memories via RPC so the ACT-R access-frequency boost
applies. Semantic failure falls back to keyword-only search (still using
rewriter-extracted entities when available); rewriter failure falls back
to raw-prompt keyword search with the default type set. Hook never
blocks the prompt.
"""

import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# ---------------------------------------------------------------------------
# Bootstrap: re-exec under venv if running under system Python
# ---------------------------------------------------------------------------
_root = Path(__file__).resolve().parent.parent
_venv_py = _root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")

# Guard: only re-exec when run as script. When imported (e.g. by tests via
# importlib with a non-"__main__" module name), skip the re-exec so the
# module's top-level sys.exit doesn't kill pytest collection.
if __name__ == "__main__" and _venv_py.exists() and Path(sys.executable).resolve() != _venv_py.resolve():
    sys.exit(subprocess.call([str(_venv_py), str(Path(__file__).resolve())]))

# ---------------------------------------------------------------------------
# Under venv — safe to import deps
# ---------------------------------------------------------------------------
import httpx
from dotenv import load_dotenv

for _env in [_root / ".env", _root.parent / ".env"]:
    if _env.exists():
        # override=True: shells on some devices export empty ANTHROPIC_API_KEY
        # which would otherwise win over the .env value and disable the rewriter.
        load_dotenv(_env, override=True)
        break

from supabase import create_client

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SIMILARITY_THRESHOLD = 0.30  # calibrated 2026-04-17: real user prompts hit 0.35-0.50
# top-similarity on voyage-3-lite/512 with conversational queries. 0.30 catches
# clearly-relevant matches without firing on unrelated memories (which sit <0.25).
# server.py default SIMILARITY_THRESHOLD is also 0.25 for the same reason.
# Phase 7.2 default: brief-mode one-line entries instead of full content. Jarvis
# sees the inventory relevant to the prompt and fetches content via memory_get
# on hits it actually wants. Reduces per-turn rot since we no longer dump
# 5-10 full bodies into every UserPromptSubmit.
BRIEF_MODE = True
CHAR_BUDGET_FULL = 40_000    # ~10K tokens, ~5% of 200K window (legacy path)
CHAR_BUDGET_BRIEF = 12_000   # ~3K tokens ceiling — rarely hit after MAX_BRIEF_ENTRIES cap
CHAR_BUDGET = CHAR_BUDGET_BRIEF if BRIEF_MODE else CHAR_BUDGET_FULL
FETCH_LIMIT = 50             # pull wide per signal, cap by budget in Python
# Cap brief-mode injection at top-N direct hits. Earlier default was char-budget
# only, which let 30-40 entries through every prompt (~4-5KB) — mostly tail
# noise the agent never reads. Top-7 preserves the relevance head; deeper hits
# stay reachable via memory_recall on demand.
MAX_BRIEF_ENTRIES = 7

# Phase 7.3: known-unknowns as per-prompt gate. When the current prompt is
# semantically close to an open known_unknown (a query that previously hit
# a recall gap), switch OFF brief mode for this invocation — the topic has
# historically needed more context than names + descriptions. Fail-soft: any
# DB error returns False and the default brief path runs.
#
# Threshold 0.85 picks "same topic, possibly different phrasing" — calibrated
# against the 0.9 used for known_unknowns semantic dedup in server.py so a
# prompt that would DEDUP to an existing gap also triggers widening, but a
# prompt that's only loosely related doesn't. SCAN_LIMIT caps the client-side
# cosine sweep; open unknowns are bounded by Haiku's recall-gap rate and
# rarely exceed a few hundred, so 200 is a safe cap.
KNOWN_UNKNOWN_GATE_THRESHOLD = 0.85
KNOWN_UNKNOWN_SCAN_LIMIT = 200
# Types loaded per-prompt. Excluded:
#   'user'    — loaded at session start (scripts/session-context.py top-2)
#   'project' — dominated by working_state_* which is session-specific and
#               already session-loaded; broader project memories will be
#               pulled in once Phase 3 gains a proper tag filter.
ALLOWED_TYPES = {"feedback", "decision", "reference"}
MIN_PROMPT_CHARS = 15        # too-short prompts produce noisy embeddings
RRF_K = 60                   # matches _rrf_merge in mcp-memory/server.py
# Rewriter types are applied as a soft rank boost, not a hard filter. An
# earlier version gated rows by requested_types and recall@5 dropped -5pp
# on the eval set whenever Haiku misclassified a feedback/decision query
# as `reference`. The boost keeps misclassified-but-relevant memories in
# the candidate pool; calibrated so a boosted single-signal hit still
# loses to an unboosted dual-signal hit (0.0167*1.5 < 0.0333).
TYPE_BOOST_MULTIPLIER = 1.5

# 1-hop BFS expansion on memory_links — fills coverage gaps where the
# expected memory is linked from a retrieved row but not itself retrieved
# by semantic+keyword fan-out. Seeds are the top-K RRF rows; linked
# neighbors get a decayed RRF-like score so a good link at rank 0 can
# still outrank a weak direct hit at rank 20+.
#   LINK_EXPAND_TOP_K = seeds passed to get_linked_memories
#   LINK_DECAY       = multiplier on the parent's 1/(k+rank) contribution
#                      (0.5 → linked row worth half a direct hit at same rank)
#   LINK_SCORE_FIELD = debug marker + display signal on linked-only rows
LINK_EXPAND_TOP_K = 5
LINK_DECAY = 0.5
LINK_SCORE_FIELD = "_link_score"

# Projects Jarvis tracks — cwd basename must match one of these to scope recall.
# Anything else → no project filter (load from global + all projects).
KNOWN_PROJECTS = {"jarvis", "redrobot"}

VOYAGE_API_URL = "https://api.voyageai.com/v1/embeddings"
VOYAGE_MODEL = "voyage-3-lite"
EMBED_TIMEOUT = 8.0  # keep responsive; hook blocks user prompt

# Haiku rewriter: extracts {entities, types} from the raw prompt.
# Budget is read-path — user is waiting — so 2.5s is the cap. On failure
# we fall back to raw-prompt FTS and the default ALLOWED_TYPES.
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
REWRITER_MODEL = "claude-haiku-4-5"
REWRITER_TIMEOUT = 2.5
REWRITER_MAX_TOKENS = 200
MIN_REWRITE_CHARS = 25   # shorter than this → LLM call not worth the latency
REWRITER_MAX_ENTITIES = 8
REWRITER_MAX_TYPES = 3
# Types the rewriter is allowed to suggest. Subset of {feedback, decision,
# reference} matches ALLOWED_TYPES; "episode" is rejected here because
# episodic memories aren't yet surfaced by this hook (Phase 4 feature,
# separate wiring).
REWRITER_VALID_TYPES = {"feedback", "decision", "reference"}

REWRITER_SYSTEM_PROMPT = """You extract recall signals from a user prompt for a personal AI agent's long-term memory system.

Given the user's raw prompt, output two things:

1. entities: 1-8 literal keywords or short phrases likely to appear verbatim in relevant memories. Prefer:
   - proper nouns (project names, people, tools)
   - file paths, function names, identifiers (e.g. memory_store, classifier.py)
   - technical terms kept as multi-word phrases (e.g. "Phase 3", "RRF merge")
   Drop stopwords, pronouns, conversational glue ("can you", "help me", "I want").
   Lowercase everything. If nothing literal stands out, return an empty list.

2. types: subset of {feedback, decision, reference} when the prompt clearly concerns ONE of them:
   - feedback: user preferences, working style, corrections ("how do I like tests written?")
   - decision: past architectural choices, rationale ("did we decide X?", "why did we pick Y?")
   - reference: pointers to external systems, dashboards, repo links ("where is Z tracked?")
   Empty list = no narrowing (default behavior, use when the prompt is a generic task).

Output strict JSON only, no prose:
{"entities": ["..."], "types": ["..."]}"""


def emit(context: str):
    """Output additionalContext as hookSpecificOutput JSON and exit 0."""
    if not context:
        sys.exit(0)
    out = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": context,
        }
    }
    json.dump(out, sys.stdout)
    sys.exit(0)


def silent_exit():
    sys.exit(0)


def embed(text: str) -> list[float] | None:
    api_key = os.environ.get("VOYAGE_API_KEY")
    if not api_key:
        return None
    try:
        with httpx.Client(timeout=EMBED_TIMEOUT) as client:
            resp = client.post(
                VOYAGE_API_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                json={"model": VOYAGE_MODEL, "input": [text], "input_type": "query"},
            )
            resp.raise_for_status()
            return resp.json()["data"][0]["embedding"]
    except Exception:
        return None


def _parse_rewriter(text: str) -> dict | None:
    """Parse Haiku's JSON reply. Tolerant of stray prose around the object.

    Returns {"entities": [...], "types": [...]} with both lists validated
    and capped, or None when the output is unusable (no JSON, wrong shape,
    both lists empty after validation).
    """
    if not text:
        return None
    first = text.find("{")
    last = text.rfind("}")
    if first < 0 or last <= first:
        return None
    try:
        data = json.loads(text[first : last + 1])
    except json.JSONDecodeError:
        return None

    # Guard against non-dict JSON slipping through brace-matching (e.g. the
    # model wraps a list or string in a way that still brackets with {}).
    # Without this, data.get below raises and the exception propagates out
    # of the future, breaking the hook's fail-soft contract.
    if not isinstance(data, dict):
        return None

    raw_entities = data.get("entities")
    if isinstance(raw_entities, list):
        entities = [
            str(e).strip().lower()
            for e in raw_entities
            if isinstance(e, (str, int, float))
        ]
        entities = [e for e in entities if e][:REWRITER_MAX_ENTITIES]
    else:
        entities = []

    raw_types = data.get("types")
    if isinstance(raw_types, list):
        types = [str(t).strip().lower() for t in raw_types if isinstance(t, str)]
        types = [t for t in types if t in REWRITER_VALID_TYPES][:REWRITER_MAX_TYPES]
    else:
        types = []

    if not entities and not types:
        return None
    return {"entities": entities, "types": types}


def rewrite_prompt(prompt: str) -> dict | None:
    """Ask Haiku to extract {entities, types} for better recall.

    Returns the parsed dict or None on: too-short prompt, missing API key,
    network/timeout error, unparseable output. Caller falls back to the
    raw prompt for keyword search and the default ALLOWED_TYPES.
    """
    if len(prompt) < MIN_REWRITE_CHARS:
        return None
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    try:
        with httpx.Client(timeout=REWRITER_TIMEOUT) as client:
            resp = client.post(
                ANTHROPIC_API_URL,
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": ANTHROPIC_VERSION,
                    "content-type": "application/json",
                },
                json={
                    "model": REWRITER_MODEL,
                    "max_tokens": REWRITER_MAX_TOKENS,
                    "system": REWRITER_SYSTEM_PROMPT,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            resp.raise_for_status()
            payload = resp.json()
    except Exception:
        return None

    blocks = payload.get("content", [])
    text = ""
    for b in blocks:
        if isinstance(b, dict) and b.get("type") == "text":
            text = b.get("text", "")
            break
    return _parse_rewriter(text)


def detect_project(cwd: str) -> str | None:
    """Return project name if cwd is a known project dir, else None."""
    try:
        name = Path(cwd).name.lower()
    except Exception:
        return None
    return name if name in KNOWN_PROJECTS else None


def _parse_embedding(v) -> list[float] | None:
    """Parse a pgvector column as returned by supabase-py.

    PostgREST serializes `vector(N)` as a JSON-array string like "[0.1,0.2,...]"
    rather than a native list — silently zipping that with a real list of
    floats (the fail mode in server.py's _cosine_sim callers) produces 0.0
    similarity instead of an error. Parse to list[float] up front so cosine
    math sees matching shapes.

    Returns None for anything unparseable; callers treat None as "no vector"
    and fall through to a miss.
    """
    if v is None:
        return None
    if isinstance(v, list):
        return v
    if isinstance(v, str):
        try:
            parsed = json.loads(v)
        except (json.JSONDecodeError, ValueError):
            return None
        if isinstance(parsed, list):
            return parsed
    return None


def _cosine_sim(a: list[float] | None, b: list[float] | None) -> float:
    """Cosine similarity. Returns 0.0 on any dim mismatch or missing input.

    Same math as mcp-memory/server.py::_cosine_sim. Duplicated here so the
    hook doesn't import from the MCP server (no Python package structure in
    place yet — Phase 4+ consolidation task).
    """
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def check_known_unknown_gate(client, query_embedding: list[float] | None) -> bool:
    """Phase 7.3 gate: has this prompt's topic been a recall gap before?

    Scans open known_unknowns and returns True on the first row whose stored
    query_embedding has cosine sim >= KNOWN_UNKNOWN_GATE_THRESHOLD with the
    current prompt's embedding. Caller uses the result to switch OFF brief
    mode and widen the char budget for this invocation.

    Fail-soft — returns False on any DB/parse error so the default (brief)
    path still runs. Never raises.
    """
    if not query_embedding:
        return False
    try:
        result = (
            client.table("known_unknowns")
            .select("query_embedding")
            .eq("status", "open")
            .not_.is_("query_embedding", "null")
            .limit(KNOWN_UNKNOWN_SCAN_LIMIT)
            .execute()
        )
    except Exception:
        return False
    for row in result.data or []:
        stored = _parse_embedding(row.get("query_embedding"))
        if stored and _cosine_sim(query_embedding, stored) >= KNOWN_UNKNOWN_GATE_THRESHOLD:
            return True
    return False


def _score_str(m: dict) -> str:
    """Render the ranking signal visible to the reader.

    Shared between `format_memory` (full) and `format_memory_brief`. The
    priority mirrors rrf_merge's field invariants: _rrf_score is set only on
    dual-signal rows; _sort_score only on boosted single-signal rows;
    _link_score only on rows pulled in by 1-hop BFS. Falling through to
    native similarity/rank keeps the displayed score truthful.
    """
    rrf = m.get("_rrf_score")
    sort_score = m.get("_sort_score")
    link_score = m.get(LINK_SCORE_FIELD)
    sim = m.get("similarity")
    rank = m.get("rank")
    if rrf is not None:
        return f" (rrf {rrf:.3f})"
    if sort_score is not None:
        return f" (boost {sort_score:.3f})"
    if link_score is not None:
        return f" (link {link_score:.3f})"
    if sim is not None:
        return f" (sim {sim:.2f})"
    if rank is not None:
        return f" (rank {rank:.2f})"
    return ""


def format_memory_brief(m: dict) -> str:
    """One-line preview for bulk auto-injection (Phase 7.2).

    Format: `- name [type/project] [tags] (score): description`. Similar in
    spirit to the session-start catalog layout
    (scripts/session-context.py::_fmt_catalog_entry) — this hook block adds
    the per-query score so the agent can distinguish hybrid-ranked hits
    from the recency-sorted inventory, and always emits an explicit
    `type/project` scope (the catalog omits project for the current one).
    No content body — agent pulls via memory_get on anything worth reading.
    """
    tags = m.get("tags") or []
    tags_str = f" [{', '.join(tags)}]" if tags else ""
    proj = m.get("project") or "global"
    desc = (m.get("description") or "").strip()
    return f"- {m['name']} [{m['type']}/{proj}]{tags_str}{_score_str(m)}: {desc}"


def format_memory(m: dict) -> str:
    tags = m.get("tags") or []
    tags_str = f" [{', '.join(tags)}]" if tags else ""
    proj = m.get("project") or "global"
    desc = m.get("description") or ""
    content = m.get("content") or ""
    header = f"## {m['name']} ({m['type']}, {proj}){tags_str}{_score_str(m)}"
    body = f"*{desc}*\n\n{content}" if desc else content
    return f"{header}\n{body}"


def rrf_merge(
    semantic_rows: list[dict],
    keyword_rows: list[dict],
    k: int = RRF_K,
    boost_types: set[str] | None = None,
    boost_multiplier: float = TYPE_BOOST_MULTIPLIER,
) -> list[dict]:
    """Reciprocal Rank Fusion over two ranked lists.

    Same RRF math as mcp-memory/server.py::_rrf_merge (k=60, scores additive,
    ranked desc), with two deliberate differences vs. the server:
      - Keep the semantic row in `by_id` when a memory appears in both lists,
        so the row still carries its `similarity` for display fallback. The
        server overwrites with the keyword row; it doesn't care, we do.
      - No `limit` slice. The caller caps by CHAR_BUDGET, not row count.

    Optional `boost_types`: when set, rows whose `type` is in the set get
    their final score multiplied by `boost_multiplier` before the rank sort.
    Used to apply the Haiku rewriter's type hint as a soft nudge rather than
    a hard filter — a type misclassification no longer drops relevant rows.

    Only rows hit by BOTH signals get `_rrf_score` set — that's the semantic
    meaning of "fusion", and `format_memory` depends on it to pick the right
    display (rrf vs sim vs rank). A row seen once keeps its native score
    field untouched, *except* when the boost fires on a single-signal row:
    we set `_sort_score` on it so `format_memory` can show the true sort
    key. Otherwise the displayed sim/rank would contradict the ranking.

    Every row also gets `_final_score` — the unified ranking key after any
    boost. Downstream link expansion (`merge_with_links`) uses this to fold
    linked neighbors into the same sort space without having to recompute
    RRF positions.
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
    return out


def _score_linked_rows(
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
    `get_linked_memories`, which carries `linked_from` pointing at the
    seed id) and returns the subset whose parent is in the top-K seed
    window, deduped against the seeds and against each other.

    Score formula: `(1 / (k + parent_rank)) * decay * link_strength`.
    Mirrors the RRF math in `rrf_merge` so link scores live in the same
    space, then `decay` attenuates them (0.5 → linked hit worth half a
    direct hit at the same rank). `link_strength` (0..1, from DB) scales
    by edge confidence.
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
    """Fetch 1-hop linked neighbors of the top-K rows via `get_linked_memories`.

    Returns annotated linked rows (see `_score_linked_rows`). On RPC failure
    returns []. Hook's fail-soft contract — links are a coverage bonus, not
    a hard requirement.
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
    return _score_linked_rows(top_rows, linked_rows, top_k=top_k, decay=decay)


def merge_with_links(
    ranked_rows: list[dict], linked_rows: list[dict]
) -> list[dict]:
    """Fold linked rows into the already-ranked hybrid result.

    Each `ranked_rows` entry carries `_final_score` (set by `rrf_merge`);
    each `linked_rows` entry carries `_link_score` (set by
    `_score_linked_rows`). Rows that appear in both keep the max. Sort
    key after merge is the resulting score, written back to
    `_final_score` so downstream budget trim + display stay consistent.
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


def main():
    # Force UTF-8 decode: on Windows, sys.stdin default codec is cp1251 which
    # mangles Cyrillic prompts from Claude Code (always UTF-8).
    try:
        raw = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    except Exception:
        silent_exit()
    if not raw.strip():
        silent_exit()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        silent_exit()

    prompt = (data.get("prompt") or "").strip()
    if len(prompt) < MIN_PROMPT_CHARS:
        silent_exit()

    cwd = data.get("cwd") or os.getcwd()
    project = detect_project(cwd)

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        silent_exit()

    # Embed and rewrite run in parallel — both are network-bound, and the
    # rewriter's output only feeds the keyword leg, so Voyage doesn't need
    # to wait. If either fails, the other's result is still useful.
    with ThreadPoolExecutor(max_workers=2) as ex:
        fut_embed = ex.submit(embed, prompt)
        fut_rewrite = ex.submit(rewrite_prompt, prompt)
        query_embedding = fut_embed.result()
        rewritten = fut_rewrite.result()

    entities = (rewritten or {}).get("entities") or []
    requested_types = (rewritten or {}).get("types") or []

    # Keyword query: joined entities (denoised) if rewriter gave us any,
    # else the raw prompt (MVP behavior, still works without Haiku).
    keyword_query = " ".join(entities) if entities else prompt

    # Rewriter's type hint becomes a soft boost (see TYPE_BOOST_MULTIPLIER
    # comment). Intersecting with ALLOWED_TYPES keeps the boost confined
    # to types the hook actually surfaces; an out-of-set suggestion (e.g.
    # the rewriter hallucinates `episode`) resolves to no boost instead
    # of falling through to "boost everything".
    boost_types = (ALLOWED_TYPES & set(requested_types)) if requested_types else None

    try:
        client = create_client(url, key)
    except Exception:
        silent_exit()

    # Phase 7.3: is this prompt a repeat of a topic we've had weak recall on?
    # If yes, widen — disable brief mode for this invocation and raise the
    # char budget to the legacy full-content limit so the agent gets bodies,
    # not just names. Gate is best-effort; any DB error falls back to False.
    widened = (
        BRIEF_MODE
        and check_known_unknown_gate(client, query_embedding)
    )
    brief_mode = BRIEF_MODE and not widened
    char_budget = CHAR_BUDGET_BRIEF if brief_mode else CHAR_BUDGET_FULL

    semantic_rows: list[dict] = []
    if query_embedding is not None:
        try:
            sem = client.rpc("match_memories", {
                "query_embedding": query_embedding,
                "match_limit": FETCH_LIMIT,
                "similarity_threshold": SIMILARITY_THRESHOLD,
                "filter_project": project,  # None → no project filter
                "filter_type": None,        # filter types in Python
            }).execute()
            semantic_rows = sem.data or []
        except Exception:
            semantic_rows = []

    keyword_rows: list[dict] = []
    try:
        kw = client.rpc("keyword_search_memories", {
            "search_query": keyword_query,
            "match_limit": FETCH_LIMIT,
            "filter_project": project,
            "filter_type": None,
        }).execute()
        keyword_rows = kw.data or []
    except Exception:
        keyword_rows = []

    # Level 1 scope: always restrict to types the hook is responsible for.
    # user/project memories are loaded by scripts/session-context.py at
    # session start and excluded here to avoid duplication.
    semantic_rows = [r for r in semantic_rows if r.get("type") in ALLOWED_TYPES]
    keyword_rows = [r for r in keyword_rows if r.get("type") in ALLOWED_TYPES]

    if not semantic_rows and not keyword_rows:
        silent_exit()

    rows = rrf_merge(semantic_rows, keyword_rows, boost_types=boost_types)

    # 1-hop BFS: pull linked neighbors of the top-K RRF rows and fold them
    # into the ranking. Covers the "expected memory is one edge away from
    # a retrieved row" failure mode (q15/q19 in the eval set). Linked rows
    # are type-scoped like direct rows. Fail-soft: RPC or link_score error
    # yields zero linked rows and the ranking is unchanged.
    linked_rows_raw = expand_links(client, rows)
    linked_rows = [r for r in linked_rows_raw if r.get("type") in ALLOWED_TYPES]
    linked_count = len(linked_rows)
    if linked_rows:
        rows = merge_with_links(rows, linked_rows)

    # Accumulate under char budget
    scope = f" (project: {project}+global)" if project else " (all projects)"
    signal = (
        "semantic+keyword (RRF)"
        if semantic_rows and keyword_rows
        else "semantic-only"
        if semantic_rows
        else "keyword-only"
    )
    if linked_count:
        signal += f" + {linked_count} linked"
    rewriter_note = ""
    if rewritten:
        bits = []
        if entities:
            bits.append(f"entities: {', '.join(entities)}")
        if boost_types:
            bits.append(f"boost: {', '.join(sorted(boost_types))}")
        if bits:
            rewriter_note = f" — rewriter: {'; '.join(bits)}"
    mode_tag = ", brief" if brief_mode else ""
    if widened:
        mode_tag += ", widened: known-unknown match"
    hint = (
        "\n\n(Brief mode — names + descriptions only. "
        "Use memory_get(name=...) to fetch full content for any hit worth reading.)"
        if brief_mode
        else ""
    )
    header = (
        f"# Memories on topic{scope}\n\n"
        f"Hybrid recall ({signal}{mode_tag}){rewriter_note}:{hint}\n\n"
    )
    parts = [header]
    total = len(header)
    included_ids = []

    # Full mode separates bodies with `---`; brief mode is one line per entry,
    # so a single newline is enough and keeps the injected block compact.
    separator = "\n" if brief_mode else "\n\n---\n\n"
    formatter = format_memory_brief if brief_mode else format_memory

    for row in rows:
        block = formatter(row) + separator
        if total + len(block) > char_budget:
            break
        if brief_mode and len(included_ids) >= MAX_BRIEF_ENTRIES:
            break
        parts.append(block)
        total += len(block)
        if row.get("id"):
            included_ids.append(row["id"])

    if len(included_ids) == 0:
        silent_exit()

    # Trim trailing separator
    if parts[-1].endswith(separator):
        parts[-1] = parts[-1][: -len(separator)]

    # Touch accessed memories (fire-and-forget; failures ignored)
    try:
        client.rpc("touch_memories", {"memory_ids": included_ids}).execute()
    except Exception:
        pass

    emit("".join(parts))


if __name__ == "__main__":
    main()
