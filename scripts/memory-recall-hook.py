"""UserPromptSubmit hook: task-aware hybrid recall injected as context.

Phase 3 MVP (fan-out, no LLM rewriter yet): embeds the prompt AND runs a
keyword/FTS search over the same text, then merges both ranked lists via
Reciprocal Rank Fusion. This catches memories that match by literal terms
but sit below the semantic threshold (e.g. proper nouns, rare keywords)
without the cost of an LLM call on every prompt.

Types ∈ {feedback, decision}. Scope: current project (cwd basename) +
global. Capped at ~40K chars (~10K tokens, ~5% of 200K context).

Touches accessed memories via RPC so the ACT-R access-frequency boost
applies. Any failure → empty context, prompt proceeds unaffected.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Bootstrap: re-exec under venv if running under system Python
# ---------------------------------------------------------------------------
_root = Path(__file__).resolve().parent.parent
_venv_py = _root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")

if _venv_py.exists() and Path(sys.executable).resolve() != _venv_py.resolve():
    sys.exit(subprocess.call([str(_venv_py), str(Path(__file__).resolve())]))

# ---------------------------------------------------------------------------
# Under venv — safe to import deps
# ---------------------------------------------------------------------------
import httpx
from dotenv import load_dotenv

for _env in [_root / ".env", _root.parent / ".env"]:
    if _env.exists():
        load_dotenv(_env)
        break

from supabase import create_client

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SIMILARITY_THRESHOLD = 0.30  # calibrated 2026-04-17: real user prompts hit 0.35-0.50
# top-similarity on voyage-3-lite/512 with conversational queries. 0.30 catches
# clearly-relevant matches without firing on unrelated memories (which sit <0.25).
# server.py default SIMILARITY_THRESHOLD is also 0.25 for the same reason.
CHAR_BUDGET = 40_000         # ~10K tokens, ~5% of 200K window
FETCH_LIMIT = 50             # pull wide per signal, cap by budget in Python
# Types loaded per-prompt. Excluded:
#   'user'    — loaded at session start (scripts/session-context.py top-2)
#   'project' — dominated by working_state_* which is session-specific and
#               already session-loaded; broader project memories will be
#               pulled in once Phase 3 gains a proper tag filter.
ALLOWED_TYPES = {"feedback", "decision", "reference"}
MIN_PROMPT_CHARS = 15        # too-short prompts produce noisy embeddings
RRF_K = 60                   # matches _rrf_merge in mcp-memory/server.py

# Projects Jarvis tracks — cwd basename must match one of these to scope recall.
# Anything else → no project filter (load from global + all projects).
KNOWN_PROJECTS = {"jarvis", "redrobot"}

VOYAGE_API_URL = "https://api.voyageai.com/v1/embeddings"
VOYAGE_MODEL = "voyage-3-lite"
EMBED_TIMEOUT = 8.0  # keep responsive; hook blocks user prompt


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


def detect_project(cwd: str) -> str | None:
    """Return project name if cwd is a known project dir, else None."""
    try:
        name = Path(cwd).name.lower()
    except Exception:
        return None
    return name if name in KNOWN_PROJECTS else None


def format_memory(m: dict) -> str:
    tags = m.get("tags") or []
    tags_str = f" [{', '.join(tags)}]" if tags else ""
    # Phase 3: fan-out signal — prefer RRF score if present, else fall back to
    # raw similarity (semantic-only path) or rank (keyword-only).
    rrf = m.get("_rrf_score")
    sim = m.get("similarity")
    if rrf is not None:
        score_str = f" (rrf {rrf:.3f})"
    elif sim is not None:
        score_str = f" (sim {sim:.2f})"
    else:
        score_str = ""
    proj = m.get("project") or "global"
    desc = m.get("description") or ""
    content = m.get("content") or ""
    header = f"## {m['name']} ({m['type']}, {proj}){tags_str}{score_str}"
    body = f"*{desc}*\n\n{content}" if desc else content
    return f"{header}\n{body}"


def rrf_merge(semantic_rows: list[dict], keyword_rows: list[dict], k: int = RRF_K) -> list[dict]:
    """Reciprocal Rank Fusion over two ranked lists.

    Mirrors mcp-memory/server.py::_rrf_merge so the hook and the recall RPC
    use the same scoring. A row appearing in both lists scores roughly
    double vs. a row in only one — catches terms the embedding missed
    (rare keywords, proper nouns) without letting pure-keyword hits
    dominate over relevant semantic matches.
    """
    scores: dict[str, float] = {}
    by_id: dict[str, dict] = {}
    for rank, row in enumerate(semantic_rows):
        rid = row.get("id") or row.get("name")
        if not rid:
            continue
        scores[rid] = scores.get(rid, 0.0) + 1.0 / (k + rank)
        by_id[rid] = row
    for rank, row in enumerate(keyword_rows):
        rid = row.get("id") or row.get("name")
        if not rid:
            continue
        scores[rid] = scores.get(rid, 0.0) + 1.0 / (k + rank)
        # Keep the row we already have (semantic has similarity score); only
        # overwrite if this is a keyword-only hit.
        by_id.setdefault(rid, row)
    ranked_ids = sorted(scores.keys(), key=lambda r: scores[r], reverse=True)
    out = []
    for rid in ranked_ids:
        row = by_id[rid]
        row["_rrf_score"] = scores[rid]
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

    query_embedding = embed(prompt)
    # Semantic can fail-soft (no API key / timeout): still run keyword search
    # on the prompt. Keyword-only is better than silent_exit — a user typing a
    # literal identifier should still get relevant memories surfaced.

    try:
        client = create_client(url, key)
    except Exception:
        silent_exit()

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
            "search_query": prompt,
            "match_limit": FETCH_LIMIT,
            "filter_project": project,
            "filter_type": None,
        }).execute()
        keyword_rows = kw.data or []
    except Exception:
        keyword_rows = []

    # Filter both lists to allowed types BEFORE merging, so RRF scores are
    # computed only over candidates we'll actually surface.
    semantic_rows = [r for r in semantic_rows if r.get("type") in ALLOWED_TYPES]
    keyword_rows = [r for r in keyword_rows if r.get("type") in ALLOWED_TYPES]

    if not semantic_rows and not keyword_rows:
        silent_exit()

    rows = rrf_merge(semantic_rows, keyword_rows)

    # Accumulate under char budget
    scope = f" (project: {project}+global)" if project else " (all projects)"
    signal = (
        "semantic+keyword (RRF)"
        if semantic_rows and keyword_rows
        else "semantic-only"
        if semantic_rows
        else "keyword-only"
    )
    header = f"# Memories on topic{scope}\n\nHybrid recall ({signal}):\n\n"
    parts = [header]
    total = len(header)
    included_ids = []

    for row in rows:
        block = format_memory(row) + "\n\n---\n\n"
        if total + len(block) > CHAR_BUDGET:
            break
        parts.append(block)
        total += len(block)
        if row.get("id"):
            included_ids.append(row["id"])

    if len(included_ids) == 0:
        silent_exit()

    # Trim trailing separator
    if parts[-1].endswith("---\n\n"):
        parts[-1] = parts[-1][: -len("---\n\n")]

    # Touch accessed memories (fire-and-forget; failures ignored)
    try:
        client.rpc("touch_memories", {"memory_ids": included_ids}).execute()
    except Exception:
        pass

    emit("".join(parts))


if __name__ == "__main__":
    main()
