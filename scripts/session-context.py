"""Session context loader for SessionStart hook.

Queries Supabase directly (no MCP) and prints formatted memory + goals.
Output is injected into Claude's context automatically by the hook.

Usage (in hook):  python scripts/session-context.py
Self-bootstraps into venv — works from any Python.
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
# Now running under venv — safe to import dependencies
# ---------------------------------------------------------------------------
from dotenv import load_dotenv

for _env in [_root / ".env", _root.parent / ".env"]:
    if _env.exists():
        load_dotenv(_env)
        break

from supabase import create_client

# Ensure UTF-8 output on Windows (cp1251 can't handle Cyrillic in some contexts)
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8")


KNOWN_PROJECTS = {"jarvis", "redrobot"}


def _detect_project():
    """Return current project name if cwd basename matches a known project, else None."""
    try:
        name = Path(os.getcwd()).name.lower()
    except Exception:
        return None
    return name if name in KNOWN_PROJECTS else None


def main():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        print("[session-context] SUPABASE_URL/KEY not set", file=sys.stderr)
        return

    try:
        client = create_client(url, key)
    except Exception as e:
        print(f"[session-context] Supabase connect failed: {e}", file=sys.stderr)
        return

    project = _detect_project()
    sections = []
    touched_ids: list[str] = []

    # 1. User memories — who is the owner (always)
    section, ids = _query_memories(client, mem_type="user", limit=2)
    if section:
        sections.append("## User Profile\n" + section)
        touched_ids.extend(ids)

    # 2. Always-load memories — evergreen rules not tied to any single project.
    #    Everything else (feedback/decisions) is loaded task-aware via
    #    UserPromptSubmit hook (scripts/memory-recall-hook.py).
    section, ids = _query_always_load(client)
    if section:
        sections.append("## Always-Load Rules\n" + section)
        touched_ids.extend(ids)

    # 3. Working state — ONLY when session is inside a known project dir.
    #    In a non-project cwd (e.g. scheduled research) working_state is noise.
    if project:
        section, ids = _query_memories(
            client, mem_type="project", limit=1,
            extra_filter=lambda q: q.eq("name", f"working_state_{project}"),
        )
        if section:
            sections.append(f"## Working State ({project})\n" + section)
            touched_ids.extend(ids)

    # 4. Active goals (always)
    goal_section = _query_goals(client)
    if goal_section:
        sections.append(goal_section)

    # Bump last_accessed_at for every memory we just loaded. Phase 1 drives the
    # access-frequency boost in temporal scoring off this column, so
    # session-start loads should count as access. The content_updated_at /
    # updated_at trigger is not fired because we go through the touch_memories
    # RPC which updates only last_accessed_at.
    _touch_accessed(client, touched_ids)

    # Output
    if sections:
        print("=" * 60)
        print("MEMORY CONTEXT (auto-loaded — do NOT re-fetch with MCP tools)")
        print("=" * 60)
        print("\n\n".join(sections))
        print("=" * 60)
    else:
        print("[session-context] No memory data available.")


# ---------------------------------------------------------------------------
# Memory queries
# ---------------------------------------------------------------------------

_MEMORY_COLS = "id, name, type, project, description, content, tags, updated_at"


def _query_memories(client, *, mem_type, limit, extra_filter=None):
    """Query memories table with type filter.

    Returns (formatted_text, ids) — ids are used to bump last_accessed_at.
    """
    try:
        q = client.table("memories").select(_MEMORY_COLS).eq("type", mem_type)
        if extra_filter:
            q = extra_filter(q)
        result = q.order("updated_at", desc=True).limit(limit).execute()
        if result.data:
            text = "\n---\n".join(_fmt_memory(m) for m in result.data)
            ids = [m["id"] for m in result.data if m.get("id")]
            return text, ids
    except Exception as e:
        print(f"[session-context] {mem_type} query failed: {e}", file=sys.stderr)
    return None, []


def _query_always_load(client):
    """Query memories tagged 'always_load' (evergreen, cross-project rules).

    Returns (formatted_text, ids).
    """
    try:
        result = (
            client.table("memories")
            .select(_MEMORY_COLS)
            .contains("tags", ["always_load"])
            .order("updated_at", desc=True)
            .execute()
        )
        if result.data:
            text = "\n---\n".join(_fmt_memory(m) for m in result.data)
            ids = [m["id"] for m in result.data if m.get("id")]
            return text, ids
    except Exception as e:
        print(f"[session-context] always_load query failed: {e}", file=sys.stderr)
    return None, []


def _touch_accessed(client, ids):
    """Bump last_accessed_at via the same RPC server.py uses on recall.

    Fire-and-forget — never block session start on this. Failures are
    logged to stderr for visibility but don't surface to the user.
    """
    if not ids:
        return
    try:
        client.rpc("touch_memories", {"memory_ids": ids}).execute()
    except Exception as e:
        print(f"[session-context] touch_memories failed: {e}", file=sys.stderr)


def _fmt_memory(m):
    tags = f" [{', '.join(m.get('tags') or [])}]" if m.get("tags") else ""
    return (
        f"### {m['name']} ({m['type']}, {m.get('project') or 'global'}){tags}\n"
        f"*{m.get('description', '')}*\n"
        f"Updated: {m.get('updated_at', '?')}\n\n"
        f"{m['content']}"
    )


# ---------------------------------------------------------------------------
# Goal queries
# ---------------------------------------------------------------------------

def _query_goals(client):
    """Query active goals, return formatted string or None."""
    try:
        result = (
            client.table("goals")
            .select("*")
            .eq("status", "active")
            .order("priority")
            .order("deadline", desc=False, nullsfirst=False)
            .execute()
        )
        if not result.data:
            return None
        goals = [_fmt_goal(g) for g in result.data]
        return f"## Active Goals ({len(result.data)})\n" + "\n---\n".join(goals)
    except Exception as e:
        print(f"[session-context] goals query failed: {e}", file=sys.stderr)
        return None


def _fmt_goal(g):
    deadline = f" | Deadline: {g['deadline']}" if g.get("deadline") else ""
    direction = f" | Direction: {g['direction']}" if g.get("direction") else ""
    parent = f" | Sub-goal of: {g['parent_id']}" if g.get("parent_id") else ""

    lines = [
        f"### {g['title']}",
        f"`{g['slug']}` | {g.get('project') or 'cross-project'} "
        f"| {g['priority']} | {g['status']}{deadline}{direction}{parent}",
    ]

    if g.get("why"):
        lines.append(f"\n**Why:** {g['why']}")

    # Progress
    pct = g.get("progress_pct", 0)
    progress = _parse_json_field(g.get("progress"))
    if progress:
        remaining = [p for p in progress if not p.get("done")]
        done_count = len(progress) - len(remaining)
        lines.append(f"\n**Progress ({pct}%):** {done_count}/{len(progress)} done")
        if remaining:
            lines.append("**Remaining:**")
            for p in remaining:
                lines.append(f"- [ ] {p.get('item', p)}")

    # Risks
    risks = _parse_json_field(g.get("risks"))
    if risks:
        lines.append("\n**Risks:** " + "; ".join(risks))

    if g.get("owner_focus"):
        lines.append(f"\n**Owner focus:** {g['owner_focus']}")
    if g.get("jarvis_focus"):
        lines.append(f"**Jarvis focus:** {g['jarvis_focus']}")

    return "\n".join(lines)


def _parse_json_field(val):
    """Parse a field that might be JSON string or already a list."""
    if val is None:
        return []
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        try:
            return json.loads(val)
        except (ValueError, TypeError):
            return []
    return []


if __name__ == "__main__":
    main()
