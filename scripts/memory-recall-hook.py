"""UserPromptSubmit hook: task-aware semantic recall injected as context.

Reads the user's prompt, embeds it, and returns all memories (type ∈
{feedback, decision}) above similarity threshold 0.7, scoped to current project
(from cwd basename) + global. Result is injected as additionalContext under a
'# Memories on topic' header, capped at ~40K chars (~10K tokens, ~5% of 200K
context window — owner's budget).

Also touches accessed memories (access_count++) via RPC.

Graceful degradation: any failure → empty context, prompt proceeds unaffected.
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
FETCH_LIMIT = 50             # pull wide, cap by budget in Python
ALLOWED_TYPES = {"feedback", "decision"}
MIN_PROMPT_CHARS = 15        # too-short prompts produce noisy embeddings

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
    sim = m.get("similarity")
    sim_str = f" (sim {sim:.2f})" if sim is not None else ""
    proj = m.get("project") or "global"
    desc = m.get("description") or ""
    content = m.get("content") or ""
    header = f"## {m['name']} ({m['type']}, {proj}){tags_str}{sim_str}"
    body = f"*{desc}*\n\n{content}" if desc else content
    return f"{header}\n{body}"


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
    if query_embedding is None:
        silent_exit()

    try:
        client = create_client(url, key)
        result = client.rpc("match_memories", {
            "query_embedding": query_embedding,
            "match_limit": FETCH_LIMIT,
            "similarity_threshold": SIMILARITY_THRESHOLD,
            "filter_project": project,  # None → no project filter
            "filter_type": None,        # filter types in Python
        }).execute()
        rows = result.data or []
    except Exception:
        silent_exit()

    # Filter to allowed types, sort by similarity desc
    rows = [r for r in rows if r.get("type") in ALLOWED_TYPES]
    rows.sort(key=lambda r: r.get("similarity", 0.0), reverse=True)

    if not rows:
        silent_exit()

    # Accumulate under char budget
    scope = f" (project: {project}+global)" if project else " (all projects)"
    header = f"# Memories on topic{scope}\n\nSemantic recall, threshold={SIMILARITY_THRESHOLD}:\n\n"
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
