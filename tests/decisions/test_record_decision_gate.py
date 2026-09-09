"""Tests for scripts/record-decision-gate.py — Tier 2 hook (#524, #1269)."""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
import types
from pathlib import Path

# Stub optional deps so the module can import without a venv present.
for _stub in ("dotenv",):
    if _stub not in sys.modules:
        try:
            __import__(_stub)
        except ImportError:
            mod = types.ModuleType(_stub)
            mod.load_dotenv = lambda *a, **k: None
            sys.modules[_stub] = mod

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
gate = importlib.import_module("record-decision-gate")

_HOOK = Path(__file__).resolve().parent.parent.parent / "scripts" / "record-decision-gate.py"


# ── Pure evaluator ───────────────────────────────────────────────────


def test_blocks_when_memories_used_missing():
    assert gate.evaluate("mcp__memory__record_decision", {}) is True


def test_blocks_when_memories_used_empty_list():
    assert gate.evaluate("mcp__memory__record_decision", {"memories_used": []}) is True


def test_blocks_when_memories_used_none():
    assert gate.evaluate("mcp__memory__record_decision", {"memories_used": None}) is True


def test_passes_when_memories_used_has_uuids():
    uuids = ["11111111-1111-1111-1111-111111111111"]
    assert gate.evaluate("mcp__memory__record_decision", {"memories_used": uuids}) is False


def test_passes_when_intentionally_empty_true_and_empty_list():
    assert (
        gate.evaluate(
            "mcp__memory__record_decision",
            {"memories_used": [], "intentionally_empty": True},
        )
        is False
    )


def test_passes_when_intentionally_empty_true_and_missing():
    assert (
        gate.evaluate(
            "mcp__memory__record_decision",
            {"intentionally_empty": True},
        )
        is False
    )


def test_intentionally_empty_false_does_not_bypass():
    assert (
        gate.evaluate(
            "mcp__memory__record_decision",
            {"memories_used": [], "intentionally_empty": False},
        )
        is True
    )


def test_other_tool_never_blocks():
    assert gate.evaluate("Bash", {"command": "ls"}) is False
    assert gate.evaluate("mcp__memory__memory_store", {}) is False


def test_intentionally_empty_overrides_even_with_full_list():
    # Flag is checked first; non-empty list also passes — both routes work.
    uuids = ["11111111-1111-1111-1111-111111111111"]
    assert (
        gate.evaluate(
            "mcp__memory__record_decision",
            {"memories_used": uuids, "intentionally_empty": True},
        )
        is False
    )


# ── Session-id sanitizer (#1269) ─────────────────────────────────────


def test_sanitize_accepts_harness_uuid():
    sid = "fe22ddae-340c-4c5b-b8d7-82a4df8396ee"
    assert gate.sanitize_session_id(sid) == sid


def test_sanitize_accepts_underscore_and_dash():
    assert gate.sanitize_session_id("abc_DEF-123") == "abc_DEF-123"


def test_sanitize_rejects_bad_chars():
    assert gate.sanitize_session_id("abc def") is None
    assert gate.sanitize_session_id("abc/../etc") is None
    assert gate.sanitize_session_id("") is None


def test_sanitize_rejects_overlong():
    assert gate.sanitize_session_id("a" * 129) is None
    assert gate.sanitize_session_id("a" * 128) == "a" * 128


def test_sanitize_rejects_non_string():
    assert gate.sanitize_session_id(None) is None
    assert gate.sanitize_session_id(42) is None


# ── End-to-end: subprocess with stdin JSON ───────────────────────────


def _run_hook(input_obj: dict) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, str(_HOOK)],
        input=json.dumps(input_obj),
        text=True,
        capture_output=True,
        timeout=10,
    )
    return proc.returncode, proc.stdout


def test_subprocess_blocks_empty_with_deny_json():
    rc, out = _run_hook(
        {
            "tool_name": "mcp__memory__record_decision",
            "tool_input": {"memories_used": []},
        }
    )
    assert rc == 2
    payload = json.loads(out)
    inner = payload["hookSpecificOutput"]
    assert inner["hookEventName"] == "PreToolUse"
    assert inner["permissionDecision"] == "deny"
    assert "memories_used" in inner["permissionDecisionReason"]
    assert "CLAUDE.md" in inner["permissionDecisionReason"]
    assert "intentionally_empty" in inner["permissionDecisionReason"]


def test_subprocess_passes_with_uuids():
    # No deny — allow path now always stamps cwd (#1423), so this is no
    # longer a fully-silent exit; assert the gate passed, not the wire shape.
    rc, out = _run_hook(
        {
            "tool_name": "mcp__memory__record_decision",
            "tool_input": {"memories_used": ["11111111-1111-1111-1111-111111111111"]},
        }
    )
    assert rc == 0
    inner = json.loads(out)["hookSpecificOutput"]
    assert "permissionDecision" not in inner
    assert inner["updatedInput"]["memories_used"] == ["11111111-1111-1111-1111-111111111111"]


def test_subprocess_passes_with_intentionally_empty():
    rc, out = _run_hook(
        {
            "tool_name": "mcp__memory__record_decision",
            "tool_input": {"memories_used": [], "intentionally_empty": True},
        }
    )
    assert rc == 0
    inner = json.loads(out)["hookSpecificOutput"]
    assert "permissionDecision" not in inner
    assert inner["updatedInput"]["intentionally_empty"] is True


def test_subprocess_silent_on_other_tool():
    rc, out = _run_hook({"tool_name": "Bash", "tool_input": {"command": "ls"}})
    assert rc == 0
    assert out == ""


def test_subprocess_silent_on_malformed_stdin():
    proc = subprocess.run(
        [sys.executable, str(_HOOK)],
        input="not json at all",
        text=True,
        capture_output=True,
        timeout=10,
    )
    assert proc.returncode == 0
    assert proc.stdout == ""


def test_subprocess_silent_on_empty_stdin():
    proc = subprocess.run(
        [sys.executable, str(_HOOK)],
        input="",
        text=True,
        capture_output=True,
        timeout=10,
    )
    assert proc.returncode == 0


# ── Session-id stamping via updatedInput (#1269) ─────────────────────


_SID = "fe22ddae-340c-4c5b-b8d7-82a4df8396ee"
_UUID = "11111111-1111-1111-1111-111111111111"


def test_subprocess_injects_session_id_on_allow():
    rc, out = _run_hook(
        {
            "session_id": _SID,
            "tool_name": "mcp__memory__record_decision",
            "tool_input": {"memories_used": [_UUID]},
        }
    )
    assert rc == 0
    payload = json.loads(out)
    inner = payload["hookSpecificOutput"]
    assert inner["hookEventName"] == "PreToolUse"
    # updatedInput without permissionDecision: transparent input mutation
    # that neither bypasses permission dialogs nor races the recall
    # context this same process may also emit (#1421 — one process now).
    assert "permissionDecision" not in inner
    updated = inner["updatedInput"]
    assert updated["memories_used"] == [_UUID]
    assert updated["session_id"] == _SID


def test_subprocess_injects_on_intentionally_empty_allow():
    rc, out = _run_hook(
        {
            "session_id": _SID,
            "tool_name": "mcp__memory__record_decision",
            "tool_input": {"memories_used": [], "intentionally_empty": True},
        }
    )
    assert rc == 0
    updated = json.loads(out)["hookSpecificOutput"]["updatedInput"]
    assert updated["session_id"] == _SID
    assert updated["intentionally_empty"] is True


def test_subprocess_harness_sid_overrides_model_supplied():
    # The harness stdin sid is ground truth; a model-hallucinated value in
    # tool_input must not survive.
    rc, out = _run_hook(
        {
            "session_id": _SID,
            "tool_name": "mcp__memory__record_decision",
            "tool_input": {"memories_used": [_UUID], "session_id": "made-up"},
        }
    )
    assert rc == 0
    updated = json.loads(out)["hookSpecificOutput"]["updatedInput"]
    assert updated["session_id"] == _SID


def test_subprocess_stamps_cwd_when_sid_missing():
    # #1423: cwd is stamped independently of session_id validity — cwd has
    # no sanitization failure mode (falls back to os.getcwd()), so a missing
    # sid no longer means a fully silent exit.
    rc, out = _run_hook(
        {
            "cwd": "/some/project/path",
            "tool_name": "mcp__memory__record_decision",
            "tool_input": {"memories_used": [_UUID]},
        }
    )
    assert rc == 0
    updated = json.loads(out)["hookSpecificOutput"]["updatedInput"]
    assert updated["cwd"] == "/some/project/path"
    assert "session_id" not in updated


def test_subprocess_stamps_cwd_when_sid_malformed():
    rc, out = _run_hook(
        {
            "session_id": "not a valid sid!",
            "cwd": "/some/project/path",
            "tool_name": "mcp__memory__record_decision",
            "tool_input": {"memories_used": [_UUID]},
        }
    )
    assert rc == 0
    updated = json.loads(out)["hookSpecificOutput"]["updatedInput"]
    assert updated["cwd"] == "/some/project/path"
    assert "session_id" not in updated


def test_subprocess_injects_cwd_alongside_session_id():
    # #1423 AC: cwd stamped alongside session_id — cwd becomes the recovery
    # key (project, cwd, window); session_id stays as forensic metadata.
    rc, out = _run_hook(
        {
            "session_id": _SID,
            "cwd": "/some/project/path",
            "tool_name": "mcp__memory__record_decision",
            "tool_input": {"memories_used": [_UUID]},
        }
    )
    assert rc == 0
    updated = json.loads(out)["hookSpecificOutput"]["updatedInput"]
    assert updated["cwd"] == "/some/project/path"
    assert updated["session_id"] == _SID


def test_subprocess_stamps_project_from_cwd_when_missing():
    # #1587: project is now a hard-required server-side field. detect_project
    # scans cwd's path parts against KNOWN_PROJECTS so the caller doesn't
    # have to remember to pass it explicitly.
    rc, out = _run_hook(
        {
            "cwd": "/home/dev/GitHub/jarvis/.claude/worktrees/some-worktree",
            "tool_name": "mcp__memory__record_decision",
            "tool_input": {"memories_used": [_UUID]},
        }
    )
    assert rc == 0
    updated = json.loads(out)["hookSpecificOutput"]["updatedInput"]
    assert updated["project"] == "jarvis"


def test_subprocess_does_not_override_explicit_project():
    # A deliberate cross-project call (project already set by the caller)
    # must survive untouched, even if cwd would resolve to a different one.
    rc, out = _run_hook(
        {
            "cwd": "/home/dev/GitHub/jarvis/.claude/worktrees/some-worktree",
            "tool_name": "mcp__memory__record_decision",
            "tool_input": {"memories_used": [_UUID], "project": "redrobot"},
        }
    )
    assert rc == 0
    updated = json.loads(out)["hookSpecificOutput"]["updatedInput"]
    assert updated["project"] == "redrobot"


def test_subprocess_no_project_stamp_when_cwd_unresolvable():
    rc, out = _run_hook(
        {
            "cwd": "/some/unrelated/path",
            "tool_name": "mcp__memory__record_decision",
            "tool_input": {"memories_used": [_UUID]},
        }
    )
    assert rc == 0
    updated = json.loads(out)["hookSpecificOutput"]["updatedInput"]
    assert "project" not in updated


def test_subprocess_no_injection_for_other_tools():
    rc, out = _run_hook(
        {
            "session_id": _SID,
            "tool_name": "Bash",
            "tool_input": {"command": "ls"},
        }
    )
    assert rc == 0
    assert out == ""


def test_subprocess_deny_still_wins_with_sid_present():
    rc, out = _run_hook(
        {
            "session_id": _SID,
            "tool_name": "mcp__memory__record_decision",
            "tool_input": {"memories_used": []},
        }
    )
    assert rc == 2
    inner = json.loads(out)["hookSpecificOutput"]
    assert inner["permissionDecision"] == "deny"
    assert "updatedInput" not in inner
