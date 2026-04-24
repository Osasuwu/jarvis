"""PreCompact hook: capture a durable session snapshot before auto-compaction.

Parses the session JSONL transcript, composes a structured markdown snapshot,
and upserts it to Supabase (name=`session_snapshot_<session_id>`, type=project)
with source_provenance="hook:pre-compact". Falls back to a local file under
`.claude/session-snapshots/<session_id>.md` when Supabase is unreachable.

Invariants:
- **Never** blocks compaction. Exits 0 on all paths, including failures.
- Snapshot content stays under SIZE_BUDGET bytes (~30KB). Long transcripts
  keep only the last TAIL_KEEP entries with a dropped-head counter.

Registered in `.claude/settings.json` under `PreCompact` for both `auto` and
`manual` matchers.

Hook input (stdin, JSON):
  session_id, transcript_path, cwd, hook_event_name, trigger ("auto"|"manual")

Related:
- `scripts/session-context.py` — reads snapshots on resume (Phase 2, #279)
- `.claude-userlevel/skills/end/SKILL.md` (installed to `~/.claude/skills/end/`) — consumes snapshot as primary source (Phase 3, #280)
"""

import json
import os
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
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
from dotenv import load_dotenv

for _env in [_root / ".env", _root.parent / ".env"]:
    if _env.exists():
        # override=True: some shells pre-set empty SUPABASE_*; .env wins.
        load_dotenv(_env, override=True)
        break

# UTF-8 output on Windows — Cyrillic in transcripts must survive the hook log.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SIZE_BUDGET = 30_000  # bytes — content column target
MAX_TRANSCRIPT_LINES = 10_000  # tail-truncate above this
TAIL_KEEP = 8_000  # keep last N lines when truncating
ACTIONS_CAP = 200  # per-section cap on verbose action lines
KNOWN_PROJECTS = {"jarvis", "redrobot"}


# ---------------------------------------------------------------------------
# Helpers (pure — unit-tested in tests/test_pre_compact_backup.py)
# ---------------------------------------------------------------------------
def _detect_project(cwd: str | None) -> str | None:
    if not cwd:
        return None
    try:
        name = Path(cwd).name.lower()
    except Exception:
        return None
    return name if name in KNOWN_PROJECTS else None


def _read_hook_input(stream=None) -> dict:
    """Read hook input JSON from stdin. Tolerate empty / invalid payloads."""
    s = stream if stream is not None else sys.stdin
    try:
        raw = s.read()
        if not raw or not raw.strip():
            return {}
        return json.loads(raw)
    except Exception as e:
        print(f"[pre-compact] bad hook input: {e}", file=sys.stderr)
        return {}


def _parse_transcript(path: Path) -> tuple[list[dict], int, int]:
    """Return (entries, total_seen, dropped_head).

    If the transcript has more than MAX_TRANSCRIPT_LINES lines, keep only the
    last TAIL_KEEP; `dropped_head` reports how many leading entries were cut.
    Malformed lines are silently skipped.
    """
    try:
        with path.open("r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception as e:
        print(f"[pre-compact] read transcript failed: {e}", file=sys.stderr)
        return [], 0, 0

    total = len(lines)
    dropped = 0
    if total > MAX_TRANSCRIPT_LINES:
        dropped = total - TAIL_KEEP
        lines = lines[-TAIL_KEEP:]

    entries: list[dict] = []
    for ln in lines:
        try:
            entries.append(json.loads(ln))
        except Exception:
            continue
    return entries, total, dropped


def _extract_user_messages(entries: list[dict]) -> list[tuple[str, str]]:
    """Real user messages only. Skip command-messages, skill invocations,
    scheduled-task bootstrap, tool_result blocks, and sidechain traffic.
    Dedup on the first 200 chars so repeated prompts don't bloat the snapshot.
    """
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for d in entries:
        if d.get("type") != "user" or d.get("isSidechain"):
            continue
        ts = d.get("timestamp", "")
        c = d.get("message", {}).get("content")
        text = ""
        if isinstance(c, str):
            text = c
        elif isinstance(c, list):
            parts = [
                blk.get("text", "")
                for blk in c
                if isinstance(blk, dict) and blk.get("type") == "text"
            ]
            text = "\n".join(parts)
        text = text.strip()
        if not text:
            continue
        if (
            text.startswith("<command-message>")
            or text.startswith("<command-name>")
            or text.startswith("<scheduled-task")
            or text.startswith("Base directory for this skill:")
        ):
            continue
        key = text[:200]
        if key in seen:
            continue
        seen.add(key)
        out.append((ts, text))
    return out


def _summarize_tool(name: str, inp: dict) -> str:
    """One-line summary of a tool_use block, keyed by tool name."""
    if name == "Bash":
        return (inp.get("command") or "").replace("\n", " ").strip()[:180]
    if name in ("Edit", "Write"):
        return inp.get("file_path") or ""
    if name == "NotebookEdit":
        return inp.get("notebook_path") or ""
    if name == "Read":
        return inp.get("file_path") or ""
    if name in ("Grep", "Glob"):
        return inp.get("pattern") or ""
    if name == "TodoWrite":
        todos = inp.get("todos", []) or []
        n_in = sum(1 for t in todos if t.get("status") == "in_progress")
        n_done = sum(1 for t in todos if t.get("status") == "completed")
        return f"{len(todos)} todos ({n_done} done, {n_in} in progress)"
    if name == "Skill":
        return inp.get("skill") or ""
    if name == "Agent":
        return inp.get("description") or inp.get("subagent_type") or ""
    if name == "mcp__memory__memory_store":
        return f"name={inp.get('name', '?')} type={inp.get('type', '?')}"
    if name == "mcp__memory__record_decision":
        return (inp.get("decision") or "")[:120]
    if name.startswith("mcp__github__"):
        keys = ("owner", "repo", "issue_number", "pull_number", "title")
        return " ".join(f"{k}={inp[k]}" for k in keys if k in inp)[:180]
    if name.startswith("mcp__ccd_session__"):
        return (inp.get("title") or inp.get("reason") or "")[:120]
    for k in ("description", "title", "command", "query", "prompt"):
        v = inp.get(k)
        if isinstance(v, str):
            return v[:120]
    return ""


def _extract_actions(entries: list[dict]) -> list[tuple[str, str]]:
    """(timestamp, 'ToolName: one-line') tuples from assistant tool_use blocks."""
    out: list[tuple[str, str]] = []
    for d in entries:
        if d.get("type") != "assistant":
            continue
        ts = d.get("timestamp", "")
        for blk in d.get("message", {}).get("content", []) or []:
            if not isinstance(blk, dict) or blk.get("type") != "tool_use":
                continue
            name = blk.get("name", "?")
            inp = blk.get("input", {}) or {}
            summary = _summarize_tool(name, inp)
            out.append((ts, f"{name}: {summary}" if summary else name))
    return out


def _extract_last_todos(entries: list[dict]) -> list[dict]:
    """Most-recent TodoWrite payload — the canonical 'open loops' view."""
    last: list[dict] = []
    for d in entries:
        if d.get("type") != "assistant":
            continue
        for blk in d.get("message", {}).get("content", []) or []:
            if (
                isinstance(blk, dict)
                and blk.get("type") == "tool_use"
                and blk.get("name") == "TodoWrite"
            ):
                last = blk.get("input", {}).get("todos", []) or []
    return last


def _extract_last_assistant_text(entries: list[dict]) -> str:
    for d in reversed(entries):
        if d.get("type") != "assistant":
            continue
        parts = [
            blk.get("text", "")
            for blk in d.get("message", {}).get("content", []) or []
            if isinstance(blk, dict) and blk.get("type") == "text"
        ]
        text = "\n".join(parts).strip()
        if text:
            return text
    return ""


def _last_git_branch(entries: list[dict]) -> str:
    for d in reversed(entries):
        br = d.get("gitBranch")
        if br:
            return br
    return ""


def _compose_markdown(
    session_id: str,
    trigger: str,
    cwd: str,
    entries: list[dict],
    total_seen: int,
    dropped_head: int,
) -> str:
    """Compose the snapshot body. Enforces SIZE_BUDGET via hard truncation
    with a visible marker — never silently drops content without notice.
    """
    users = _extract_user_messages(entries)
    actions = _extract_actions(entries)
    todos = _extract_last_todos(entries)
    last_text = _extract_last_assistant_text(entries)
    git_branch = _last_git_branch(entries)
    captured = datetime.now(timezone.utc).isoformat()

    lines: list[str] = []
    lines.append(f"# Session Snapshot — {session_id}")
    lines.append("")
    lines.append(f"- **Captured at:** {captured}")
    lines.append(f"- **Trigger:** {trigger}")
    lines.append(f"- **cwd:** `{cwd}`")
    if git_branch:
        lines.append(f"- **git branch:** `{git_branch}`")
    entries_line = (
        f"- **Entries parsed:** {len(entries)} (total seen: {total_seen}"
        + (f", dropped-head: {dropped_head}" if dropped_head else "")
        + ")"
    )
    lines.append(entries_line)
    lines.append("")

    if users:
        lines.append(f"## User messages ({len(users)})")
        for ts, text in users:
            preview = text.replace("\n", " ").strip()
            if len(preview) > 500:
                preview = preview[:500] + " …"
            lines.append(f"- `{ts}` — {preview}")
        lines.append("")

    if actions:
        lines.append(f"## Actions ({len(actions)})")
        if len(actions) > ACTIONS_CAP:
            earlier = actions[: len(actions) - ACTIONS_CAP]
            by_tool = Counter(a[1].split(":", 1)[0] for a in earlier)
            summ = ", ".join(f"{k}×{v}" for k, v in by_tool.most_common())
            lines.append(f"Earlier actions (summarized): {summ}")
            kept = actions[-ACTIONS_CAP:]
        else:
            kept = actions
        for ts, act in kept:
            a = act.replace("\n", " ").strip()
            if len(a) > 200:
                a = a[:200] + " …"
            lines.append(f"- `{ts}` — {a}")
        lines.append("")

    if todos:
        lines.append(f"## Open loops / todos ({len(todos)})")
        status_mark = {"completed": "x", "in_progress": "~", "pending": " "}
        for t in todos:
            mark = status_mark.get(t.get("status", ""), "?")
            content = t.get("content", "")
            lines.append(f"- [{mark}] {content}")
        lines.append("")

    if last_text:
        lines.append("## Last assistant message (text only)")
        snippet = last_text
        if len(snippet) > 2000:
            snippet = snippet[:2000] + "\n…"
        lines.append(snippet)
        lines.append("")

    md = "\n".join(lines)
    if len(md.encode("utf-8")) > SIZE_BUDGET:
        marker = "\n\n<!-- truncated at size budget -->\n"
        budget = SIZE_BUDGET - len(marker.encode("utf-8"))
        md = md.encode("utf-8")[:budget].decode("utf-8", errors="ignore") + marker
    return md


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------
def _persist_supabase(
    session_id: str,
    project: str | None,
    trigger: str,
    content: str,
) -> bool:
    """Upsert the snapshot to memories. Returns True on success."""
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        return False
    try:
        from supabase import create_client

        client = create_client(url, key)
        payload = {
            "name": f"session_snapshot_{session_id}",
            "type": "project",
            "project": project,
            "tags": ["session-snapshot", "compression-resilience", trigger or "unknown"],
            "source_provenance": "hook:pre-compact",
            "description": (
                f"Pre-compact session snapshot ({trigger or 'unknown'}) — "
                "recovery source for /end post-compact"
            ),
            "content": content,
        }
        client.table("memories").upsert(payload, on_conflict="project,name").execute()
        return True
    except Exception as e:
        print(f"[pre-compact] supabase persist failed: {e}", file=sys.stderr)
        return False


def _persist_local(session_id: str, content: str) -> Path | None:
    try:
        out_dir = _root / ".claude" / "session-snapshots"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / f"{session_id}.md"
        # Use binary write to avoid Windows \n→\r\n translation, which would
        # inflate size past SIZE_BUDGET by one byte per newline.
        out_file.write_bytes(content.encode("utf-8"))
        print(f"[pre-compact] local fallback: {out_file}", file=sys.stderr)
        return out_file
    except Exception as e:
        print(f"[pre-compact] local fallback failed: {e}", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> int:
    try:
        hook = _read_hook_input()
        session_id = hook.get("session_id") or hook.get("sessionId") or "unknown-session"
        transcript_path = hook.get("transcript_path") or hook.get("transcriptPath") or ""
        cwd = hook.get("cwd") or os.getcwd()
        trigger = hook.get("trigger") or hook.get("matcher") or "unknown"

        if not transcript_path:
            print("[pre-compact] no transcript_path in hook input", file=sys.stderr)
            return 0

        p = Path(transcript_path)
        if not p.exists():
            print(f"[pre-compact] transcript not found: {p}", file=sys.stderr)
            return 0

        entries, total, dropped = _parse_transcript(p)
        content = _compose_markdown(session_id, trigger, cwd, entries, total, dropped)
        project = _detect_project(cwd)

        if not _persist_supabase(session_id, project, trigger, content):
            _persist_local(session_id, content)
    except Exception as e:
        # Never block compaction — log and move on.
        print(f"[pre-compact] unhandled error: {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
