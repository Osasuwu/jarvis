"""Unit tests for scripts/pre-compact-backup.py.

The Supabase-upsert path is exercised live (not here). This file covers the
deterministic parsing + composition pieces that don't need network, plus the
local fallback and the "never raises" guarantee.

The module filename uses a dash so importlib is required.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
import types
from pathlib import Path


# ---------------------------------------------------------------------------
# Stub optional deps so module import succeeds on minimal CI
# ---------------------------------------------------------------------------
for _stub in ("dotenv", "supabase"):
    if _stub not in sys.modules:
        try:
            __import__(_stub)
        except ImportError:
            mod = types.ModuleType(_stub)
            if _stub == "dotenv":
                mod.load_dotenv = lambda *a, **k: None
            if _stub == "supabase":
                mod.create_client = lambda *a, **k: None
            sys.modules[_stub] = mod


_PATH = Path(__file__).resolve().parent.parent / "scripts" / "pre-compact-backup.py"
_spec = importlib.util.spec_from_file_location("pre_compact_backup", _PATH)
pcb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pcb)


# ---------------------------------------------------------------------------
# Fixtures — synthetic transcript entries
# ---------------------------------------------------------------------------
def _user_entry(ts: str, text, isSidechain: bool = False) -> dict:
    return {
        "type": "user",
        "timestamp": ts,
        "isSidechain": isSidechain,
        "gitBranch": "feat/278-precompact-hook",
        "message": {"content": text},
    }


def _assistant_tool(ts: str, name: str, inp: dict) -> dict:
    return {
        "type": "assistant",
        "timestamp": ts,
        "gitBranch": "feat/278-precompact-hook",
        "message": {"content": [{"type": "tool_use", "id": "t1", "name": name, "input": inp}]},
    }


def _assistant_text(ts: str, text: str) -> dict:
    return {
        "type": "assistant",
        "timestamp": ts,
        "gitBranch": "feat/278-precompact-hook",
        "message": {"content": [{"type": "text", "text": text}]},
    }


# ---------------------------------------------------------------------------
# _detect_project
# ---------------------------------------------------------------------------
class TestDetectProject:
    def test_known_project(self):
        assert pcb._detect_project(r"C:\Users\petrk\GitHub\jarvis") == "jarvis"
        assert pcb._detect_project("/home/x/redrobot") == "redrobot"

    def test_unknown_returns_none(self):
        assert pcb._detect_project("/tmp/random") is None

    def test_none_or_empty(self):
        assert pcb._detect_project(None) is None
        assert pcb._detect_project("") is None


# ---------------------------------------------------------------------------
# _read_hook_input — tolerant JSON
# ---------------------------------------------------------------------------
class TestReadHookInput:
    def test_valid_payload(self):
        payload = {"session_id": "abc", "transcript_path": "/x"}
        r = pcb._read_hook_input(io.StringIO(json.dumps(payload)))
        assert r == payload

    def test_empty_string(self):
        assert pcb._read_hook_input(io.StringIO("")) == {}

    def test_invalid_json(self):
        assert pcb._read_hook_input(io.StringIO("not json")) == {}


# ---------------------------------------------------------------------------
# _parse_transcript — file reading + tail truncation
# ---------------------------------------------------------------------------
class TestParseTranscript:
    def test_small_file(self, tmp_path):
        p = tmp_path / "t.jsonl"
        p.write_text(
            "\n".join(json.dumps({"type": "user", "i": i}) for i in range(3)),
            encoding="utf-8",
        )
        entries, total, dropped = pcb._parse_transcript(p)
        assert total == 3
        assert dropped == 0
        assert [e["i"] for e in entries] == [0, 1, 2]

    def test_truncates_above_max(self, tmp_path, monkeypatch):
        monkeypatch.setattr(pcb, "MAX_TRANSCRIPT_LINES", 10)
        monkeypatch.setattr(pcb, "TAIL_KEEP", 6)
        p = tmp_path / "t.jsonl"
        p.write_text(
            "\n".join(json.dumps({"type": "user", "i": i}) for i in range(15)),
            encoding="utf-8",
        )
        entries, total, dropped = pcb._parse_transcript(p)
        assert total == 15
        assert dropped == 9
        assert len(entries) == 6
        assert entries[0]["i"] == 9  # kept the tail

    def test_skips_malformed_lines(self, tmp_path):
        p = tmp_path / "t.jsonl"
        p.write_text(
            '{"type":"user","i":0}\n<<garbage>>\n{"type":"user","i":1}\n',
            encoding="utf-8",
        )
        entries, total, _ = pcb._parse_transcript(p)
        assert total == 3
        assert [e["i"] for e in entries] == [0, 1]

    def test_missing_file_returns_empty(self, tmp_path):
        entries, total, dropped = pcb._parse_transcript(tmp_path / "missing.jsonl")
        assert entries == [] and total == 0 and dropped == 0


# ---------------------------------------------------------------------------
# _extract_user_messages — filters + dedup
# ---------------------------------------------------------------------------
class TestExtractUserMessages:
    def test_string_content(self):
        entries = [_user_entry("2026-04-21T00:00:00Z", "what did I leave running?")]
        out = pcb._extract_user_messages(entries)
        assert out == [("2026-04-21T00:00:00Z", "what did I leave running?")]

    def test_list_text_blocks(self):
        entries = [
            _user_entry(
                "t",
                [
                    {"type": "text", "text": "hello"},
                    {"type": "tool_result", "tool_use_id": "x", "content": "ignored"},
                ],
            )
        ]
        assert pcb._extract_user_messages(entries) == [("t", "hello")]

    def test_filters_noise(self):
        entries = [
            _user_entry("t1", "<command-message>morning-brief</command-message>"),
            _user_entry("t2", "<command-name>/foo</command-name>"),
            _user_entry("t3", "Base directory for this skill: X"),
            _user_entry("t4", "<scheduled-task name='x'>bootstrap</scheduled-task>"),
            _user_entry("t5", "real question"),
        ]
        out = pcb._extract_user_messages(entries)
        assert [text for _, text in out] == ["real question"]

    def test_dedups_repeats(self):
        entries = [
            _user_entry("t1", "same question"),
            _user_entry("t2", "same question"),
            _user_entry("t3", "different"),
        ]
        out = pcb._extract_user_messages(entries)
        assert [text for _, text in out] == ["same question", "different"]

    def test_skips_sidechain(self):
        entries = [_user_entry("t", "subagent chatter", isSidechain=True)]
        assert pcb._extract_user_messages(entries) == []


# ---------------------------------------------------------------------------
# _summarize_tool + _extract_actions
# ---------------------------------------------------------------------------
class TestSummarizeTool:
    def test_bash_strips_newlines_and_caps(self):
        s = pcb._summarize_tool("Bash", {"command": "echo hi\nsleep 1"})
        assert "\n" not in s
        assert s == "echo hi sleep 1"

    def test_edit_returns_path(self):
        assert pcb._summarize_tool("Edit", {"file_path": "/a/b.py"}) == "/a/b.py"

    def test_todowrite_counts(self):
        s = pcb._summarize_tool(
            "TodoWrite",
            {
                "todos": [
                    {"status": "completed"},
                    {"status": "in_progress"},
                    {"status": "pending"},
                    {"status": "pending"},
                ]
            },
        )
        assert s == "4 todos (1 done, 1 in progress)"

    def test_memory_store(self):
        s = pcb._summarize_tool(
            "mcp__memory__memory_store",
            {"name": "working_state_jarvis", "type": "project"},
        )
        assert "name=working_state_jarvis" in s and "type=project" in s

    def test_record_decision_truncates(self):
        s = pcb._summarize_tool(
            "mcp__memory__record_decision",
            {"decision": "x" * 200},
        )
        assert len(s) <= 120

    def test_unknown_tool_fallback_description(self):
        s = pcb._summarize_tool("SomeNewTool", {"description": "does stuff"})
        assert s == "does stuff"

    def test_unknown_tool_no_useful_field(self):
        assert pcb._summarize_tool("SomeNewTool", {"foo": 1}) == ""


class TestExtractActions:
    def test_collects_tool_uses(self):
        entries = [
            _assistant_tool("t1", "Bash", {"command": "ls"}),
            _assistant_text("t2", "intermediate thought"),
            _assistant_tool("t3", "Edit", {"file_path": "a.py"}),
        ]
        out = pcb._extract_actions(entries)
        assert out == [("t1", "Bash: ls"), ("t3", "Edit: a.py")]


# ---------------------------------------------------------------------------
# _extract_last_todos + _extract_last_assistant_text
# ---------------------------------------------------------------------------
class TestExtractLastTodos:
    def test_picks_last(self):
        first = [{"content": "old", "status": "pending"}]
        last = [{"content": "new", "status": "in_progress"}]
        entries = [
            _assistant_tool("t1", "TodoWrite", {"todos": first}),
            _assistant_tool("t2", "Bash", {"command": "ls"}),
            _assistant_tool("t3", "TodoWrite", {"todos": last}),
        ]
        assert pcb._extract_last_todos(entries) == last

    def test_no_todowrite(self):
        entries = [_assistant_tool("t", "Bash", {"command": "ls"})]
        assert pcb._extract_last_todos(entries) == []


class TestExtractLastAssistantText:
    def test_picks_most_recent(self):
        entries = [
            _assistant_text("t1", "first"),
            _assistant_tool("t2", "Bash", {"command": "ls"}),
            _assistant_text("t3", "second"),
        ]
        assert pcb._extract_last_assistant_text(entries) == "second"

    def test_no_text(self):
        entries = [_assistant_tool("t", "Bash", {"command": "ls"})]
        assert pcb._extract_last_assistant_text(entries) == ""


# ---------------------------------------------------------------------------
# _compose_markdown
# ---------------------------------------------------------------------------
class TestComposeMarkdown:
    def test_structure(self):
        entries = [
            _user_entry("t1", "what's next?"),
            _assistant_tool("t2", "Bash", {"command": "git status"}),
            _assistant_tool(
                "t3", "TodoWrite", {"todos": [{"content": "ship it", "status": "in_progress"}]}
            ),
            _assistant_text("t4", "Done."),
        ]
        md = pcb._compose_markdown("s-1", "manual", "/x/jarvis", entries, 4, 0)
        assert "# Session Snapshot — s-1" in md
        assert "**Trigger:** manual" in md
        assert "**cwd:** `/x/jarvis`" in md
        assert "## User messages (1)" in md
        assert "what's next?" in md
        assert "## Actions" in md
        assert "Bash: git status" in md
        assert "## Open loops / todos" in md
        assert "[~] ship it" in md
        assert "## Last assistant message" in md
        assert "Done." in md

    def test_reports_dropped_head(self):
        md = pcb._compose_markdown("s", "auto", "/x", [], total_seen=15000, dropped_head=7000)
        assert "dropped-head: 7000" in md

    def test_caps_actions_with_summary(self, monkeypatch):
        monkeypatch.setattr(pcb, "ACTIONS_CAP", 3)
        entries = [_assistant_tool(f"t{i}", "Bash", {"command": f"cmd{i}"}) for i in range(10)]
        md = pcb._compose_markdown("s", "auto", "/x", entries, 10, 0)
        assert "Earlier actions (summarized): Bash×7" in md
        # Only last 3 bash lines appear verbose
        assert md.count("`t7` — Bash: cmd7") == 1
        assert md.count("`t9` — Bash: cmd9") == 1
        assert "Bash: cmd0" not in md

    def test_enforces_size_budget(self, monkeypatch):
        monkeypatch.setattr(pcb, "SIZE_BUDGET", 500)
        # Pile of long bash commands — will bust 500B
        entries = [_assistant_tool(f"t{i}", "Bash", {"command": "x" * 100}) for i in range(20)]
        md = pcb._compose_markdown("s", "auto", "/x", entries, 20, 0)
        assert len(md.encode("utf-8")) <= 500
        assert "truncated at size budget" in md


# ---------------------------------------------------------------------------
# _persist_local — fallback file
# ---------------------------------------------------------------------------
class TestPersistLocal:
    def test_writes_snapshot_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(pcb, "_root", tmp_path)
        out = pcb._persist_local("session-xyz", "# Snapshot\n")
        assert out is not None
        assert out.exists()
        assert out.parent.name == "session-snapshots"
        assert out.read_text(encoding="utf-8") == "# Snapshot\n"


# ---------------------------------------------------------------------------
# main — never raises, honours missing/absent inputs
# ---------------------------------------------------------------------------
class TestMain:
    def test_missing_transcript_path_exits_zero(self, monkeypatch):
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"session_id": "x"})))
        # No Supabase creds → would take the fallback branch, but transcript_path is empty
        monkeypatch.setenv("SUPABASE_URL", "")
        monkeypatch.setenv("SUPABASE_KEY", "")
        assert pcb.main() == 0

    def test_missing_transcript_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            sys,
            "stdin",
            io.StringIO(
                json.dumps(
                    {
                        "session_id": "x",
                        "transcript_path": str(tmp_path / "missing.jsonl"),
                        "cwd": str(tmp_path),
                    }
                )
            ),
        )
        assert pcb.main() == 0

    def test_supabase_fail_triggers_local_fallback(self, tmp_path, monkeypatch):
        # Build a tiny transcript
        t = tmp_path / "t.jsonl"
        t.write_text(json.dumps(_user_entry("ts", "hi")) + "\n", encoding="utf-8")
        monkeypatch.setattr(pcb, "_root", tmp_path)
        # Force supabase path to return False → fallback taken
        monkeypatch.setattr(pcb, "_persist_supabase", lambda *a, **k: False)
        monkeypatch.setattr(
            sys,
            "stdin",
            io.StringIO(
                json.dumps(
                    {
                        "session_id": "sess-fallback",
                        "transcript_path": str(t),
                        "cwd": str(tmp_path),
                        "trigger": "manual",
                    }
                )
            ),
        )
        assert pcb.main() == 0
        out = tmp_path / ".claude" / "session-snapshots" / "sess-fallback.md"
        assert out.exists()
        text = out.read_text(encoding="utf-8")
        assert "Session Snapshot — sess-fallback" in text
        assert "**Trigger:** manual" in text

    def test_bad_hook_input_does_not_raise(self, monkeypatch):
        monkeypatch.setattr(sys, "stdin", io.StringIO("definitely not json"))
        assert pcb.main() == 0
