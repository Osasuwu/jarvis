"""Tests for the owner-assigned task_queue reader in scripts/session-context.py
(#1392 AC3): escalations dispatch() writes to task_queue with assignee='owner'
had no reader — SESSIONSTART/PARK_MONDAY escalations were invisible until a
session-start surface exists.

Same importlib-loading scaffolding as test_milestone_sweep.py /
test_session_context_recovery.py (hyphenated filename blocks a normal import).
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock


for _stub in ("dotenv", "supabase"):
    mod = sys.modules.setdefault(_stub, types.ModuleType(_stub))
    if _stub == "dotenv":
        mod.load_dotenv = lambda *a, **k: None
    if _stub == "supabase" and not hasattr(mod, "create_client"):
        mod.create_client = MagicMock()

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PATH = _REPO_ROOT / "scripts" / "session-context.py"
_spec = importlib.util.spec_from_file_location("session_context_owner_tasks", _PATH)
sc = importlib.util.module_from_spec(_spec)
_sys_path_restore = list(sys.path)
sys.path.insert(0, str(_REPO_ROOT))
_spec.loader.exec_module(sc)
sys.path = _sys_path_restore


# ---------------------------------------------------------------------------
# Fake client — same chain-recording shape as test_session_context_recovery.py
# ---------------------------------------------------------------------------
class _FakeTable:
    def __init__(self, rows, call_log=None):
        self._rows = rows
        self._call_log = call_log if call_log is not None else []

    def select(self, *a, **kw):
        self._call_log.append(("select", a, kw))
        return self

    def eq(self, *a, **kw):
        self._call_log.append(("eq", a, kw))
        return self

    def order(self, *a, **kw):
        self._call_log.append(("order", a, kw))
        return self

    def execute(self):
        self._call_log.append(("execute", (), {}))
        return types.SimpleNamespace(data=list(self._rows))


class _FakeMemoriesTable:
    """Chain-fake for the `memories` table, covering exactly the
    select/eq/is_/order/limit/execute (read) and update/insert/eq/execute
    (write) chains that scripts/escalation_dedup.py's read_shown/write_shown
    issue against a real Supabase client — so the dedup wiring in
    _query_owner_tasks() is exercised for real instead of silently
    swallowing a "wrong table" AssertionError inside read_shown/write_shown's
    own broad except handlers (#1591 review finding).

    Keyed by dedup `name` (escalation_dedup_YYYY-MM-DD), one row per day,
    mirroring the real table's shape closely enough for these chains.
    """

    def __init__(self, store, call_log):
        self._store = store  # dict[name] -> {"id": str, "content": str}
        self._call_log = call_log
        self._filters = {}
        self._mode = None
        self._update_payload = None
        self._insert_payload = None

    def select(self, *a, **kw):
        self._mode = "select"
        self._call_log.append(("memories.select", a, kw))
        return self

    def eq(self, field, value):
        self._call_log.append(("memories.eq", (field, value), {}))
        self._filters[field] = value
        return self

    def is_(self, *a, **kw):
        self._call_log.append(("memories.is_", a, kw))
        return self

    def order(self, *a, **kw):
        self._call_log.append(("memories.order", a, kw))
        return self

    def limit(self, *a, **kw):
        self._call_log.append(("memories.limit", a, kw))
        return self

    def update(self, payload):
        self._mode = "update"
        self._update_payload = payload
        self._call_log.append(("memories.update", (payload,), {}))
        return self

    def insert(self, payload):
        self._mode = "insert"
        self._insert_payload = payload
        self._call_log.append(("memories.insert", (payload,), {}))
        return self

    def execute(self):
        self._call_log.append(("memories.execute", (), {}))
        if self._mode == "select":
            name = self._filters.get("name")
            row = self._store.get(name)
            data = [{"id": row["id"], "content": row["content"]}] if row else []
            return types.SimpleNamespace(data=data)
        if self._mode == "update":
            row_id = self._filters.get("id")
            for row in self._store.values():
                if row["id"] == row_id:
                    row["content"] = self._update_payload["content"]
                    break
            return types.SimpleNamespace(data=[])
        if self._mode == "insert":
            # Regression guard: memories table enforces source_provenance NOT
            # NULL on raw inserts (see #1591 review finding on write_shown()).
            assert "source_provenance" in self._insert_payload
            name = self._insert_payload["name"]
            self._store[name] = {
                "id": f"row-{len(self._store) + 1}",
                "content": self._insert_payload["content"],
            }
            return types.SimpleNamespace(data=[])
        raise AssertionError(f"unexpected memories table mode: {self._mode}")


class _FakeClient:
    def __init__(self, rows, memories_store=None):
        self._rows = rows
        self.call_log = []
        self._memories_store = memories_store if memories_store is not None else {}

    def table(self, name):
        if name == "task_queue":
            return _FakeTable(self._rows, self.call_log)
        if name == "memories":
            return _FakeMemoriesTable(self._memories_store, self.call_log)
        raise AssertionError(f"unexpected table: {name}")


_ROW = {
    "id": "11111111-1111-1111-1111-111111111111",
    "goal": "review escalated PR #999",
    "assignee": "owner",
    "status": "pending",
    "priority": 5,
    "escalated_reason": "review flagged CRITICAL",
    "created_at": "2026-08-08T00:00:00Z",
}


# ---------------------------------------------------------------------------
# _query_owner_tasks
# ---------------------------------------------------------------------------
def test_query_owner_tasks_returns_formatted_section():
    client = _FakeClient([_ROW])
    result = sc._query_owner_tasks(client)
    assert result is not None
    assert "Owner-Assigned Tasks" in result
    assert "review escalated PR #999" in result
    assert "review flagged CRITICAL" in result


def test_query_owner_tasks_no_rows_returns_none():
    client = _FakeClient([])
    assert sc._query_owner_tasks(client) is None


def test_query_owner_tasks_filters_on_assignee_and_status():
    client = _FakeClient([_ROW])
    sc._query_owner_tasks(client)
    calls = client.call_log
    eq_calls = [(a, kw) for (name, a, kw) in calls if name == "eq"]
    assert (("assignee", "owner"), {}) in eq_calls
    assert (("status", "pending"), {}) in eq_calls


def test_query_owner_tasks_handles_query_error(capsys):
    class _BoomClient:
        def table(self, _):
            raise RuntimeError("boom")

    assert sc._query_owner_tasks(_BoomClient()) is None
    err = capsys.readouterr().err
    assert "owner tasks query failed" in err


# ---------------------------------------------------------------------------
# Escalation dedup wiring (#1591) — exercised against a memories-table-aware
# fake so a wrong table/column/channel constant would actually fail these
# tests, instead of being swallowed by read_shown/write_shown's own
# broad except handlers.
# ---------------------------------------------------------------------------
def test_query_owner_tasks_filters_tasks_already_shown_by_digest_channel():
    from scripts.escalation_dedup import CHANNEL_DIGEST, dedup_name, today_utc

    today = today_utc()
    memories_store = {
        dedup_name(today): {
            "id": "mem-1",
            "content": json.dumps({CHANNEL_DIGEST: [_ROW["id"]]}),
        }
    }
    client = _FakeClient([_ROW], memories_store=memories_store)

    result = sc._query_owner_tasks(client)

    assert result is None


def test_query_owner_tasks_marks_returned_tasks_shown_for_session_start_channel():
    from scripts.escalation_dedup import CHANNEL_SESSION_START, dedup_name, today_utc

    today = today_utc()
    memories_store: dict = {}
    client = _FakeClient([_ROW], memories_store=memories_store)

    result = sc._query_owner_tasks(client)

    assert result is not None
    name = dedup_name(today)
    assert name in memories_store
    content = json.loads(memories_store[name]["content"])
    assert content[CHANNEL_SESSION_START] == [_ROW["id"]]


# ---------------------------------------------------------------------------
# _fmt_owner_task
# ---------------------------------------------------------------------------
def test_fmt_owner_task_includes_goal_and_reason():
    line = sc._fmt_owner_task(_ROW)
    assert "review escalated PR #999" in line
    assert "review flagged CRITICAL" in line


def test_fmt_owner_task_handles_missing_reason():
    row = dict(_ROW)
    row.pop("escalated_reason")
    line = sc._fmt_owner_task(row)
    assert "review escalated PR #999" in line
