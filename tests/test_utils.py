"""Shared test utilities for mcp-memory tests.

Contains reusable stub classes that replace Supabase client patterns
across multiple test modules (test_memory_recall_hook.py,
test_memory_server.py, etc.).
"""

from __future__ import annotations

import types


class StubClient:
    """Minimal supabase-client stand-in for expand_links-style tests.

    Records RPC call params and supports both success and exception paths.
    """

    def __init__(self, *, data=None, raise_exc=None):
        self._data = data or []
        self._raise = raise_exc
        self.rpc_calls: list[tuple[str, dict]] = []

    def rpc(self, name, params):
        self.rpc_calls.append((name, params))
        return self

    def execute(self):
        if self._raise:
            raise self._raise
        return types.SimpleNamespace(data=self._data)


class TableStub:
    """Supabase table/select-chain stand-in for table-query tests.

    Supports the ``.table().select().eq().not_.is_().limit().execute()``
    chain used by gates and CRUD-style helpers.  ``data`` is the rows
    returned; ``raise_exc`` bubbles through any method to exercise the
    fail-soft path.
    """

    def __init__(self, *, data=None, raise_exc=None):
        self._data = data or []
        self._raise = raise_exc
        self.calls: list[tuple[str, tuple]] = []
        # ``.not_`` is an accessor on the query builder, not a method, so
        # expose it as an attribute that chains back to self.
        self.not_ = self

    def table(self, name):
        self.calls.append(("table", (name,)))
        return self

    def select(self, *cols):
        self.calls.append(("select", cols))
        return self

    def eq(self, col, val):
        self.calls.append(("eq", (col, val)))
        return self

    def is_(self, col, val):
        self.calls.append(("is_", (col, val)))
        return self

    def limit(self, n):
        self.calls.append(("limit", (n,)))
        return self

    def execute(self):
        if self._raise:
            raise self._raise
        return types.SimpleNamespace(data=self._data)
