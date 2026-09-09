"""PreToolUse hook for ``mcp__memory__record_decision`` — sole owner of the
matcher (#1421). Combines two concerns in one process, one emitted
``hookSpecificOutput``:

1. **Gate (#524)** — block calls with empty ``memories_used``.
2. **Session-id stamping (#1269)** — stamp the harness session id into
   allowed calls via ``updatedInput`` so ``decision_list(session_id=...)``
   can recover the episode after context loss/compaction.

A third concern, mid-turn recall (#332), was removed per #1865: it called
the ``keyword_search_memories`` RPC, which no longer exists after the
memory-stack demolition (#1801) — the RPC's sibling hooks
(``memory-recall-hook.py``, ``pretooluse-recall-hook.py``) were already
gone, leaving recall permanently dead code that still paid for a Supabase
client + network round-trip on every call before failing.

Why one process instead of two hooks on the same matcher
----------------------------------------------------------
Until #1421, (2) and the since-removed recall concern were two independent
PreToolUse hooks registered on the same ``mcp__memory__record_decision``
matcher. Claude Code's hooks docs (code.claude.com/docs/en/hooks) confirm
hooks on the same matcher run in parallel and that multiple
``additionalContext`` values accumulate, but do **not** document how two
competing ``updatedInput`` payloads from sibling processes merge. That
undocumented gap let the stamping in (2) go missing for an entire /grill
session (4/4 decisions, not a flake) — consistent with the recall hook's
live Supabase RPC causing its output to land after the gate hook's on
every call. Consolidating into one process removed the race outright:
there is only ever one ``hookSpecificOutput`` for this matcher.

Contract
--------
- Fires on ``mcp__memory__record_decision``.
- Blocks (``permissionDecision=deny``) when ``memories_used`` is missing
  or empty AND ``intentionally_empty`` is not explicitly true.
- Structural escape: pass ``intentionally_empty=true`` in the tool args
  to acknowledge no memory informed the decision. The server emits the
  flag into the episode payload so a later review pass (#526) can track
  the rate.
- Allowed calls: when stdin carries a valid ``session_id``, emit
  ``hookSpecificOutput.updatedInput`` = tool_input + ``session_id``. The
  harness stdin sid overrides any model-supplied ``session_id``. Missing/
  malformed stdin ``session_id`` → no stamping (fail-open; recovery via
  ``decision_list`` simply won't cover that episode).
- Any other tool name → silent exit 0 (defense-in-depth: this hook is
  also registered under a narrow matcher).
- Parse failure / malformed input → silent exit 0. Never block on
  hook-internal bugs; the rule must not become a footgun.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

TOOL_NAME = "mcp__memory__record_decision"

# ---------------------------------------------------------------------------
# Bootstrap: re-exec under venv if running under system Python. Kept for
# consistency with the harness's other hooks even though the gate/stamp
# logic below is pure stdlib and would work without a venv.
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parent.parent
_VENV_PY = _ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")

if (
    __name__ == "__main__"
    and _VENV_PY.exists()
    and Path(sys.executable).resolve() != _VENV_PY.resolve()
):
    sys.exit(subprocess.call([str(_VENV_PY), str(Path(__file__).resolve())]))

# ---------------------------------------------------------------------------
# Gate (#524) / stamping (#1269) constants
# ---------------------------------------------------------------------------

# Matches _safe_session_id in session-context.py / pre-compact-backup.py.
_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")

KNOWN_PROJECTS = {"jarvis", "redrobot"}

BLOCK_REASON = (
    "record_decision blocked: memories_used is empty.\n"
    "\n"
    "Per ~/.claude/CLAUDE.md (Memory & decision protocol, rule 2):\n"
    "  Every record_decision call passes UUIDs in memories_used, not names.\n"
    "  Empty list valid only when nothing in memory informed the choice.\n"
    "\n"
    "Fix one of:\n"
    "  1. Run memory_recall(brief=true), parse name→uuid, pass UUIDs.\n"
    "  2. If genuinely no memory informed this decision, pass\n"
    "     intentionally_empty=true to acknowledge it. The flag is recorded\n"
    "     on the episode payload for review-rate tracking (#524, #526)."
)


def _emit_deny(reason: str) -> None:
    """Output deny JSON and exit 2 (PreToolUse deny convention)."""
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }
    json.dump(payload, sys.stdout)
    sys.exit(2)


def _silent_exit() -> None:
    sys.exit(0)


def sanitize_session_id(raw: object) -> str | None:
    """Return the session id iff it matches the harness sid shape, else None.

    Pure function — testable without stdin/stdout plumbing.
    """
    if not isinstance(raw, str):
        return None
    if not _SESSION_ID_RE.match(raw):
        return None
    return raw


def evaluate(tool_name: str, tool_input: dict) -> bool:
    """Return True iff this call should be blocked.

    Pure function — testable without stdin/stdout plumbing.
    """
    if tool_name != TOOL_NAME:
        return False
    if not isinstance(tool_input, dict):
        return False
    if bool(tool_input.get("intentionally_empty")):
        return False
    memories = tool_input.get("memories_used")
    if isinstance(memories, list) and len(memories) > 0:
        return False
    return True


def detect_project(cwd: str | None) -> str | None:
    """Return the known project a path belongs to, scanning all components.

    Worktree cwds (`<repo>/.claude/worktrees/<name>`) and subdirectories
    resolve to the containing repo; rightmost match wins.
    """
    if not cwd:
        return None
    try:
        parts = Path(cwd).parts
    except (OSError, ValueError):
        return None
    for part in reversed(parts):
        if part.lower() in KNOWN_PROJECTS:
            return part.lower()
    return None


def _emit_allow(tool_input: dict, session_id: str | None, cwd: str | None) -> None:
    """Emit a single combined ``hookSpecificOutput`` for an allowed call.

    ``updatedInput`` carries the ``session_id`` stamp (#1269, forensic
    grouping metadata only), the ``cwd`` stamp (#1423, the actual
    recovery-key component alongside ``project``+``since``), and the
    ``project`` auto-stamp (#1587 — ``project`` is now a hard-required
    server-side field; leaving it to be remembered manually reproduces the
    exact failure mode #1269/#1423 were built to fix) as independent
    optional fields. ``cwd`` has no sanitization failure mode (it falls
    back to ``os.getcwd()`` upstream), so it is stamped independently of
    whether ``session_id`` validated. ``project`` is only auto-stamped
    when the caller left it blank — an explicit non-blank ``project``
    (e.g. a deliberate cross-project call) is never overridden. Silent
    exit when nothing applies, matching the old per-hook silent-exit
    contract.
    """
    inner: dict = {"hookEventName": "PreToolUse"}
    updated: dict | None = None
    if session_id is not None:
        updated = dict(tool_input)
        updated["session_id"] = session_id
    if cwd:
        if updated is None:
            updated = dict(tool_input)
        updated["cwd"] = cwd
    if not (tool_input.get("project") or "").strip():
        detected = detect_project(cwd)
        if detected:
            if updated is None:
                updated = dict(tool_input)
            updated["project"] = detected
    if updated is not None:
        inner["updatedInput"] = updated

    if len(inner) == 1:  # only hookEventName — nothing to report
        _silent_exit()

    json.dump({"hookSpecificOutput": inner}, sys.stdout)
    sys.exit(0)


def main() -> None:
    try:
        raw = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    except Exception:
        _silent_exit()
    if not raw.strip():
        _silent_exit()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        _silent_exit()

    tool_name = data.get("tool_name") or ""
    tool_input = data.get("tool_input") or {}

    if evaluate(tool_name, tool_input):
        _emit_deny(BLOCK_REASON)

    if tool_name != TOOL_NAME or not isinstance(tool_input, dict):
        _silent_exit()

    sid = sanitize_session_id(data.get("session_id"))
    cwd = data.get("cwd") or os.getcwd()

    _emit_allow(tool_input, sid, cwd)


if __name__ == "__main__":
    main()
