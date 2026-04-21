"""Unit tests for scripts/session-context.py pre-compact recovery (Phase 2, #279).

Covers the deterministic parts that can be exercised without a live Supabase:
  - `_read_hook_input` — stdin parsing (TTY skip, empty, invalid JSON, valid)
  - `_is_compact_resume` — matcher detection across field-name synonyms
  - `_load_snapshot_from_local` — local fallback + freshness
  - `_format_recovery_section` — stable output shape
  - `_load_snapshot_from_supabase` — freshness logic with a fake client

Network-touching paths (live Supabase fetch) and end-to-end stdout rendering
are verified manually via `/compact` on the live session; the design doc
documents the acceptance flow.
"""

from __future__ import annotations

import importlib.util
import io
import sys
import types
from datetime import datetime, timedelta, timezone
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


_PATH = Path(__file__).resolve().parent.parent / "scripts" / "session-context.py"
_spec = importlib.util.spec_from_file_location("session_context", _PATH)
sc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sc)


# ---------------------------------------------------------------------------
# stdin helpers
# ---------------------------------------------------------------------------
class _FakeStdin(io.StringIO):
    """StringIO that lies about being a TTY — mimics a piped hook input."""

    def __init__(self, payload: str = "", isatty: bool = False):
        super().__init__(payload)
        self._isatty = isatty

    def isatty(self) -> bool:  # noqa: D401 — simple override
        return self._isatty


def _with_stdin(monkeypatch, payload: str, isatty: bool = False):
    monkeypatch.setattr(sys, "stdin", _FakeStdin(payload, isatty=isatty))


# ---------------------------------------------------------------------------
# _read_hook_input
# ---------------------------------------------------------------------------
def test_read_hook_input_tty_returns_empty(monkeypatch):
    _with_stdin(monkeypatch, "{\"session_id\": \"x\"}", isatty=True)
    assert sc._read_hook_input() == {}


def test_read_hook_input_empty_stdin(monkeypatch):
    _with_stdin(monkeypatch, "", isatty=False)
    assert sc._read_hook_input() == {}


def test_read_hook_input_whitespace_only(monkeypatch):
    _with_stdin(monkeypatch, "   \n  ", isatty=False)
    assert sc._read_hook_input() == {}


def test_read_hook_input_invalid_json(monkeypatch):
    _with_stdin(monkeypatch, "not json", isatty=False)
    assert sc._read_hook_input() == {}


def test_read_hook_input_non_object_json(monkeypatch):
    # A JSON list is syntactically valid but our contract expects an object.
    _with_stdin(monkeypatch, "[1, 2, 3]", isatty=False)
    assert sc._read_hook_input() == {}


def test_read_hook_input_valid_object(monkeypatch):
    _with_stdin(
        monkeypatch,
        '{"session_id": "abc", "hook_event_name": "SessionStart", "source": "compact"}',
        isatty=False,
    )
    data = sc._read_hook_input()
    assert data["session_id"] == "abc"
    assert data["hook_event_name"] == "SessionStart"
    assert data["source"] == "compact"


# ---------------------------------------------------------------------------
# _is_compact_resume
# ---------------------------------------------------------------------------
def test_is_compact_resume_true_for_source_compact():
    hook = {"hook_event_name": "SessionStart", "source": "compact"}
    assert sc._is_compact_resume(hook) is True


def test_is_compact_resume_true_for_matcher_compact():
    hook = {"hook_event_name": "SessionStart", "matcher": "compact"}
    assert sc._is_compact_resume(hook) is True


def test_is_compact_resume_case_insensitive():
    hook = {"hook_event_name": "SessionStart", "source": "Compact"}
    assert sc._is_compact_resume(hook) is True


def test_is_compact_resume_false_for_startup():
    hook = {"hook_event_name": "SessionStart", "source": "startup"}
    assert sc._is_compact_resume(hook) is False


def test_is_compact_resume_false_for_empty_hook():
    # Standalone run (no hook input) must not trigger recovery.
    assert sc._is_compact_resume({}) is False


def test_is_compact_resume_false_for_wrong_event():
    hook = {"hook_event_name": "PreToolUse", "matcher": "compact"}
    assert sc._is_compact_resume(hook) is False


def test_is_compact_resume_allows_missing_event_name():
    # Some invocations might omit `hook_event_name` — don't reject if the
    # matcher still clearly says compact.
    hook = {"source": "compact"}
    assert sc._is_compact_resume(hook) is True


# ---------------------------------------------------------------------------
# _load_snapshot_from_local
# ---------------------------------------------------------------------------
def _snapshot_dir(tmp_path: Path) -> Path:
    d = tmp_path / ".claude" / "session-snapshots"
    d.mkdir(parents=True, exist_ok=True)
    return d


def test_load_snapshot_from_local_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(sc, "_root", tmp_path)
    assert sc._load_snapshot_from_local("missing-session") is None


def test_load_snapshot_from_local_fresh(monkeypatch, tmp_path):
    monkeypatch.setattr(sc, "_root", tmp_path)
    d = _snapshot_dir(tmp_path)
    f = d / "sid.md"
    f.write_text("# fresh snapshot", encoding="utf-8")
    assert sc._load_snapshot_from_local("sid") == "# fresh snapshot"


def test_load_snapshot_from_local_stale(monkeypatch, tmp_path):
    monkeypatch.setattr(sc, "_root", tmp_path)
    d = _snapshot_dir(tmp_path)
    f = d / "sid.md"
    f.write_text("# stale", encoding="utf-8")
    # Age it well past the freshness window.
    old_ts = (datetime.now(timezone.utc) - timedelta(hours=2)).timestamp()
    import os as _os
    _os.utime(f, (old_ts, old_ts))
    assert sc._load_snapshot_from_local("sid") is None


def test_load_snapshot_from_local_empty_file(monkeypatch, tmp_path):
    monkeypatch.setattr(sc, "_root", tmp_path)
    d = _snapshot_dir(tmp_path)
    f = d / "sid.md"
    f.write_text("", encoding="utf-8")
    # Empty content should not yield a recovery section.
    assert sc._load_snapshot_from_local("sid") is None


# ---------------------------------------------------------------------------
# _load_snapshot_from_supabase
# ---------------------------------------------------------------------------
class _FakeTable:
    def __init__(self, rows, call_log=None):
        self._rows = rows
        self._call_log = call_log if call_log is not None else []

    # Chain methods — just record calls, return self.
    def select(self, *a, **kw):
        self._call_log.append(("select", a, kw))
        return self

    def eq(self, *a, **kw):
        self._call_log.append(("eq", a, kw))
        return self

    def is_(self, *a, **kw):
        self._call_log.append(("is_", a, kw))
        return self

    def order(self, *a, **kw):
        self._call_log.append(("order", a, kw))
        return self

    def limit(self, *a, **kw):
        self._call_log.append(("limit", a, kw))
        return self

    def execute(self):
        self._call_log.append(("execute", (), {}))
        result = types.SimpleNamespace(data=list(self._rows))
        return result


class _FakeClient:
    def __init__(self, rows):
        self._rows = rows
        self.call_log = []

    def table(self, _name):
        return _FakeTable(self._rows, self.call_log)


def test_load_snapshot_from_supabase_fresh_row():
    now = datetime.now(timezone.utc).isoformat()
    client = _FakeClient([{"content": "# snap", "updated_at": now}])
    assert sc._load_snapshot_from_supabase(client, "sid") == "# snap"


def test_load_snapshot_from_supabase_stale_row():
    stale = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    client = _FakeClient([{"content": "# old", "updated_at": stale}])
    assert sc._load_snapshot_from_supabase(client, "sid") is None


def test_load_snapshot_from_supabase_no_rows():
    client = _FakeClient([])
    assert sc._load_snapshot_from_supabase(client, "sid") is None


def test_load_snapshot_from_supabase_handles_query_error(capsys):
    class _BoomClient:
        def table(self, _):
            raise RuntimeError("boom")

    # Must not raise — the session start hook is never blocked by this failure.
    assert sc._load_snapshot_from_supabase(_BoomClient(), "sid") is None
    err = capsys.readouterr().err
    assert "snapshot query failed" in err


def test_load_snapshot_from_supabase_no_updated_at_is_kept():
    # If the row has no updated_at, freshness can't be verified — we
    # optimistically include it. This matches how we wrote the snapshot
    # (upsert always sets updated_at), but guards against schema drift.
    client = _FakeClient([{"content": "# no ts"}])
    assert sc._load_snapshot_from_supabase(client, "sid") == "# no ts"


def test_load_snapshot_from_supabase_with_project_filters_and_orders():
    # Copilot review fix: with project known, ensure we apply eq(project=...)
    # and order by updated_at desc before limit.
    now = datetime.now(timezone.utc).isoformat()
    client = _FakeClient([{"content": "# snap", "updated_at": now}])
    assert sc._load_snapshot_from_supabase(client, "sid", "jarvis") == "# snap"

    ops = client.call_log
    # name filter is there …
    assert ("eq", ("name", "session_snapshot_sid"), {}) in ops
    # deleted_at is_null is there …
    assert ("is_", ("deleted_at", "null"), {}) in ops
    # project filter is applied when supplied …
    assert ("eq", ("project", "jarvis"), {}) in ops
    # order is applied before limit
    order_idx = next(i for i, op in enumerate(ops) if op[0] == "order")
    limit_idx = next(i for i, op in enumerate(ops) if op[0] == "limit")
    assert order_idx < limit_idx
    order_op = ops[order_idx]
    assert order_op[1][0] == "updated_at"
    assert order_op[2].get("desc") is True


def test_load_snapshot_from_supabase_without_project_skips_project_filter():
    now = datetime.now(timezone.utc).isoformat()
    client = _FakeClient([{"content": "# snap", "updated_at": now}])
    assert sc._load_snapshot_from_supabase(client, "sid") == "# snap"

    ops = client.call_log
    # Only the name eq, no project eq.
    eq_calls = [op for op in ops if op[0] == "eq"]
    assert ("eq", ("name", "session_snapshot_sid"), {}) in eq_calls
    assert all(op[1][:1] != ("project",) for op in eq_calls)


def test_load_snapshot_from_supabase_rejects_bad_session_id():
    # Copilot review fix: session_id goes into the Supabase `name` — sanitize
    # before use so a hostile value can't widen the query.
    client = _FakeClient([{"content": "anything", "updated_at": datetime.now(timezone.utc).isoformat()}])
    assert sc._load_snapshot_from_supabase(client, "../escape") is None
    # Supabase must not be queried at all for a rejected id.
    assert client.call_log == []


# ---------------------------------------------------------------------------
# _safe_session_id — path-traversal / injection guard
# ---------------------------------------------------------------------------
def test_safe_session_id_accepts_typical_uuid():
    assert sc._safe_session_id("d47e5fb3-4609-4af1-a271-88a29004c7b3") == "d47e5fb3-4609-4af1-a271-88a29004c7b3"


def test_safe_session_id_accepts_alnum_and_underscore():
    assert sc._safe_session_id("abc_123-XYZ") == "abc_123-XYZ"


def test_safe_session_id_trims_surrounding_whitespace():
    assert sc._safe_session_id("  sid  ") == "sid"


def test_safe_session_id_rejects_path_traversal():
    assert sc._safe_session_id("../../etc/passwd") is None


def test_safe_session_id_rejects_path_separators():
    assert sc._safe_session_id("a/b") is None
    assert sc._safe_session_id("a\\b") is None


def test_safe_session_id_rejects_empty_and_non_str():
    assert sc._safe_session_id("") is None
    assert sc._safe_session_id("   ") is None
    assert sc._safe_session_id(None) is None
    assert sc._safe_session_id(123) is None


def test_safe_session_id_rejects_overlong():
    # Over 128 chars — keep the allowlist tight.
    assert sc._safe_session_id("a" * 129) is None


def test_safe_session_id_rejects_special_chars():
    assert sc._safe_session_id("a b") is None
    assert sc._safe_session_id("a;b") is None
    assert sc._safe_session_id("a$b") is None


# Path-traversal must also be rejected by the local loader, not only the
# sanitizer — this is the end-to-end guarantee.
def test_load_snapshot_from_local_rejects_path_traversal(monkeypatch, tmp_path):
    monkeypatch.setattr(sc, "_root", tmp_path)
    # Seed a file *outside* the snapshots directory that an attacker might
    # try to reach with `../` — confirm we refuse to read it.
    outside = tmp_path / "secrets.md"
    outside.write_text("# sensitive", encoding="utf-8")
    assert sc._load_snapshot_from_local("../secrets") is None


# ---------------------------------------------------------------------------
# _format_recovery_section
# ---------------------------------------------------------------------------
def test_format_recovery_section_has_header_and_body():
    out = sc._format_recovery_section("# body")
    assert out.startswith("## Pre-Compact Recovery\n")
    assert "# body" in out
    assert "pre-compact snapshot" in out.lower()
