"""PreToolUse hook: semantic dedup check before memory_store.

Embeds the new memory's description+content, searches existing memories of the
same type via match_memories RPC, and blocks if a similar memory exists under
a DIFFERENT name (same name = intended update, pass through).

Graceful degradation: any failure (no API key, network, RPC error) → allow.
We don't want to block legitimate writes due to infra issues.

Exit codes:
  0 + no JSON  → allow silently
  2 + deny JSON → block with reason shown to assistant
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
        load_dotenv(_env)
        break

from supabase import create_client

# recall.py is the deep module (#496-#499) that owns EXCLUDE_TAGS_FROM_RECALL —
# same list used to hide operational artifacts (session snapshots) from
# memory_recall. Reused here so the dedup guard can't drift out of sync with
# the recall path (#1184: snapshot rows were excluded from recall but not
# from dedup, causing false-positive blocks on unrelated working_state writes).
sys.path.insert(0, str(_root / "mcp-memory"))
from recall import (  # noqa: E402
    EXCLUDE_TAGS_FROM_RECALL,  # noqa: F401
    filter_excluded_tags as _filter_excluded_tags,
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
BLOCK_THRESHOLD = 0.75  # different-name match at this similarity → block
# Calibration note (2026-04-17): voyage-3-lite/512 returns ~0.79 for near-
# verbatim concept paraphrases (duplicates) and ~0.54 for related-but-distinct
# (siblings). 0.75 is set between these to catch the 0.79 dup case without
# false-firing on the 0.54 sibling case. The reupdate fallback (#1098) handles
# the separate problem of daily-cron re-stores (~0.98 similarity).

REUPDATE_SIMILARITY_THRESHOLD = 0.95  # extremely-high similarity → likely re-update
# When a match scores >0.95 (e.g., a daily-cron memory at ~0.98), treat it as
# an idempotent re-store rather than a cross-name duplicate. Used as fallback
# if row_exists check fails due to timing/connection issues (#1098).

VOYAGE_API_URL = "https://api.voyageai.com/v1/embeddings"
VOYAGE_MODEL = "voyage-3-lite"
EMBED_TIMEOUT = 10.0  # keep fast — blocks the tool call

# Auto-generated serial memories (e.g. the status-record skill's one-row-per-
# UTC-date snapshots) are intentionally near-identical: a unique date-keyed name
# + upsert, but ~0.98 cosine to the prior day's row. The cross-name dup gate
# catches *accidental* concept duplication, not a deliberate daily series — so
# exempt anything carrying these series tags. Without this, the status-record
# cron is blocked every day after the first, producing false-zero gaps in the
# trend queries those snapshots exist to feed.
SERIES_EXEMPT_TAGS = {"status-snapshot", "auto-generated"}


def is_exempt_series(tags) -> bool:
    """True if the memory carries a tag marking it as an auto-generated serial
    snapshot, which is intentionally near-identical to its siblings."""
    return isinstance(tags, list) and bool(SERIES_EXEMPT_TAGS.intersection(tags))


def levenshtein_distance(s1: str, s2: str) -> int:
    """Compute Levenshtein edit distance between two strings."""
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)

    prev_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        curr_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = prev_row[j + 1] + 1
            deletions = curr_row[j] + 1
            substitutions = prev_row[j] + (c1 != c2)
            curr_row.append(min(insertions, deletions, substitutions))
        prev_row = curr_row
    return prev_row[-1]


def is_likely_reupdate(existing_name: str, new_name: str, similarity: float) -> bool:
    """True if a high-similarity match is likely a re-store of the same memory.

    Re-stores (idempotent updates like daily-cron snapshots) score extremely high
    (>0.95 similarity) and may have minor name variants (date-keyed or versioned).
    This function detects such cases as a fallback when row_exists check fails
    due to timing/connection issues, preventing false-blocks on legitimate
    re-stores (#1098).

    ceiling: Narrow calibration to date-suffix-style recurring names (e.g.
    status_2026-08-11 vs status_2026-08-12). Risk: may also match genuinely-
    distinct short-named similar memories. Upgrade: widen calibration once more
    real cron-recurrence examples are observed, or require an explicit recurrence
    marker in memory metadata instead of inferring from name similarity.
    """
    if similarity < REUPDATE_SIMILARITY_THRESHOLD:
        return False

    # Extremely high similarity (>0.95) is a strong signal. If names are also
    # very similar (edit distance ≤ 5 chars, which covers dates and versions),
    # treat it as a re-update.
    distance = levenshtein_distance(existing_name.lower(), new_name.lower())
    return distance <= 5  # e.g., "status_2026-08-11" vs "status_2026-08-12"


def row_exists(client, name: str, project) -> bool | None:
    """True if a live (project, name) row already exists; None if query failed.

    A memory_store against an existing (project, name) is an upsert of a
    known row, not a candidate for cross-name duplicate detection — the
    unique constraint already owns that identity (#1184).

    Returns:
      True: row found (upsert case)
      False: row not found (new write, proceed to dedup check)
      None: query failed (treat as fallback for reupdate detection)
    """
    norm_project = None if project == "global" else project
    try:
        q = client.table("memories").select("id").eq("name", name).is_("deleted_at", "null")
        q = q.eq("project", norm_project) if norm_project is not None else q.is_("project", "null")
        result = q.limit(1).execute()
        return bool(result.data)
    except Exception:
        # Signal query failure (not "no row found") by returning None
        return None


def allow():
    sys.exit(0)


def block(message: str):
    out = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": message,
        }
    }
    json.dump(out, sys.stdout)
    sys.exit(2)


def embed(text: str) -> list[float] | None:
    """Synchronous Voyage embedding. Returns None on any failure."""
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


def main():
    # Force UTF-8 decode: on Windows, sys.stdin default codec is cp1251 which
    # mangles Cyrillic memory content from Claude Code (always UTF-8).
    try:
        raw = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    except Exception:
        allow()
    if not raw.strip():
        allow()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        allow()

    tool_name = data.get("tool_name", "")
    if "memory_store" not in tool_name:
        allow()

    tool_input = data.get("tool_input", {})
    if not isinstance(tool_input, dict):
        allow()

    new_name = tool_input.get("name") or ""
    new_type = tool_input.get("type") or ""
    new_project = tool_input.get("project")  # may be None
    new_desc = tool_input.get("description") or ""
    new_content = tool_input.get("content") or ""

    if not new_name or not new_type:
        allow()

    # Deliberately-serialized snapshots (status-record etc.) bypass the dup gate.
    if is_exempt_series(tool_input.get("tags")):
        allow()

    embed_text = f"{new_desc}\n{new_content}".strip()
    if not embed_text:
        allow()

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        allow()

    try:
        client = create_client(url, key)
    except Exception:
        allow()

    # (project, name) already exists → this is an upsert of a known row, not
    # a new write to check for duplicates. Skip before spending an embedding
    # call. (#1184)
    row_check = row_exists(client, new_name, new_project)
    if row_check is True:  # Row exists — upsert case, skip dedup
        allow()
    # row_check is False (no row) → continue to dedup check
    # row_check is None (query failed) → continue; may apply reupdate fallback below

    query_embedding = embed(embed_text)
    if query_embedding is None:
        allow()

    try:
        result = client.rpc(
            "match_memories",
            {
                "query_embedding": query_embedding,
                "match_limit": 5,
                "similarity_threshold": BLOCK_THRESHOLD,
                "filter_project": new_project,
                "filter_type": new_type,
            },
        ).execute()
        rows = result.data or []
    except Exception:
        allow()

    # Operational artifacts (session snapshots etc.) are excluded from recall
    # (#417) — exclude them from dedup comparison too, or a snapshot's mixed
    # transcript content false-positives against unrelated writes. (#1184)
    rows = _filter_excluded_tags(rows)

    # Same name = intended update — pass through
    candidates = [r for r in rows if r.get("name") != new_name]
    if not candidates:
        allow()

    top = candidates[0]
    sim = top.get("similarity", 0.0)
    existing_name = top.get("name", "?")
    existing_project = top.get("project") or "global"
    existing_desc = top.get("description") or ""

    # Very high similarity + name correlation = likely re-store (daily-cron, etc.).
    # Allow as idempotent upsert even though names differ, but ONLY if row_exists
    # check failed (query error, not "no row found"). This is the true fallback
    # case for cron re-stores that bypass the unique-key check due to timing issues.
    if row_check is None and is_likely_reupdate(existing_name, new_name, sim):
        allow()

    # Cross-name collision with moderate-to-high similarity. Block with actionable guidance.
    block(
        f"Possible duplicate memory (similarity {sim:.2f} ≥ {BLOCK_THRESHOLD}).\n"
        f"Existing: '{existing_name}' ({new_type}, {existing_project})\n"
        f"  — {existing_desc}\n\n"
        f"Options:\n"
        f"1. If updating the same concept → retry with name='{existing_name}' (that triggers upsert).\n"
        f"2. If this is genuinely distinct → make description/content more specific to differentiate, "
        f"then retry.\n"
        f"3. If old memory is obsolete → memory_delete('{existing_name}') first, then retry.\n"
        f"4. If this is an intentional re-store with a variant name → add a unique suffix or descriptor "
        f"to differentiate from '{existing_name}'."
    )


if __name__ == "__main__":
    main()
