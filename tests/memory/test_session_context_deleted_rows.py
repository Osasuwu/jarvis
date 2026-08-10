"""Regression tests: session-start queries must skip soft-deleted memories.

Incident 2026-08-10: a soft-deleted GLOBAL `working_state_jarvis` row
(deleted 2026-08-09, but with a newer updated_at than the live
jarvis-scoped row) shadowed the live row in session-start context —
scripts/session-context.py's `_query_memories` had no `deleted_at`
filter and no project scoping. `_query_always_load` had the same
missing filter. The snapshot query (~line 186) already filtered
correctly; these tests pin the other two plus project scoping on the
working-state lookup.

The fake client below applies eq/is_/contains/order/limit against an
in-memory row list, so the tests exercise filter *semantics* (does a
deleted or wrong-scope row surface?), not just call chains.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace


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


def _load_module(filename, modname):
    path = Path(__file__).resolve().parent.parent.parent / "scripts" / filename
    spec = importlib.util.spec_from_file_location(modname, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod


sc = _load_module("session-context.py", "session_context_deleted_rows")


class FakeQuery:
    """In-memory stand-in for a Supabase table query builder.

    Implements only the operators session-context.py uses, with real
    filter semantics so a missing filter in the code under test lets
    the wrong row through — exactly like production.
    """

    def __init__(self, rows):
        self._rows = list(rows)

    def select(self, *args, **kwargs):
        return self

    def eq(self, col, val):
        self._rows = [r for r in self._rows if r.get(col) == val]
        return self

    def is_(self, col, val):
        assert val == "null", f"unsupported is_ value: {val}"
        self._rows = [r for r in self._rows if r.get(col) is None]
        return self

    def contains(self, col, vals):
        self._rows = [r for r in self._rows if set(vals) <= set(r.get(col) or [])]
        return self

    def order(self, col, desc=False):
        self._rows.sort(key=lambda r: r.get(col) or "", reverse=desc)
        return self

    def limit(self, n):
        self._rows = self._rows[:n]
        return self

    def execute(self):
        return SimpleNamespace(data=self._rows)


def _fake_client(rows):
    return SimpleNamespace(table=lambda name: FakeQuery(rows))


def _row(name, *, project=None, mem_type="project", updated_at, deleted_at=None, tags=()):
    return {
        "id": f"id_{name}_{project}",
        "name": name,
        "type": mem_type,
        "project": project,
        "description": f"desc {name}",
        "content": f"content {name} {project}",
        "tags": list(tags),
        "updated_at": updated_at,
        "deleted_at": deleted_at,
    }


def test_working_state_skips_deleted_global_shadow():
    """The 2026-08-10 incident verbatim: deleted global row is newer than
    the live project-scoped row — the live row must win."""
    live = _row(
        "working_state_jarvis",
        project="jarvis",
        updated_at="2026-08-08T00:00:00+00:00",
    )
    deleted_global = _row(
        "working_state_jarvis",
        project=None,
        updated_at="2026-08-10T00:00:00+00:00",
        deleted_at="2026-08-09T00:00:00+00:00",
    )
    client = _fake_client([deleted_global, live])

    text, ids = sc._query_working_state(client, "jarvis")

    assert ids == [live["id"]]
    assert "content working_state_jarvis jarvis" in text


def test_working_state_skips_live_wrong_scope_row():
    """A live row in another scope (even newer) never shadows the
    canonical project=<project> row that /end's RMW writes."""
    live = _row(
        "working_state_jarvis",
        project="jarvis",
        updated_at="2026-08-08T00:00:00+00:00",
    )
    stray_global = _row(
        "working_state_jarvis",
        project=None,
        updated_at="2026-08-10T00:00:00+00:00",
    )
    client = _fake_client([stray_global, live])

    text, ids = sc._query_working_state(client, "jarvis")

    assert ids == [live["id"]]


def test_working_state_no_live_row_returns_empty():
    deleted = _row(
        "working_state_jarvis",
        project="jarvis",
        updated_at="2026-08-10T00:00:00+00:00",
        deleted_at="2026-08-09T00:00:00+00:00",
    )
    client = _fake_client([deleted])

    text, ids = sc._query_working_state(client, "jarvis")

    assert text is None
    assert ids == []


def test_user_profile_query_skips_deleted():
    live = _row(
        "owner_profile",
        mem_type="user",
        updated_at="2026-08-01T00:00:00+00:00",
    )
    deleted = _row(
        "owner_profile_old",
        mem_type="user",
        updated_at="2026-08-10T00:00:00+00:00",
        deleted_at="2026-08-09T00:00:00+00:00",
    )
    client = _fake_client([deleted, live])

    text, ids = sc._query_memories(client, mem_type="user", limit=2, compact=True)

    assert ids == [live["id"]]


def test_always_load_skips_deleted():
    live = _row(
        "rule_live",
        mem_type="reference",
        updated_at="2026-08-01T00:00:00+00:00",
        tags=["always_load"],
    )
    deleted = _row(
        "rule_deleted",
        mem_type="reference",
        updated_at="2026-08-10T00:00:00+00:00",
        deleted_at="2026-08-09T00:00:00+00:00",
        tags=["always_load"],
    )
    client = _fake_client([deleted, live])

    text, ids = sc._query_always_load(client, compact=True)

    assert ids == [live["id"]]
    assert "rule_deleted" not in (text or "")


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
