"""Shared pytest fixtures + stub modules for the mcp-memory server.

server.py imports `mcp`, `supabase`, `httpx`, and `dotenv` at module
level. Stubbing them here lets all tests in this directory import
`server` without installing the full MCP SDK — historically each test
file duplicated this setup, which drifted and broke when new server
helpers needed testing (see #254 rework).
"""

from __future__ import annotations

import os
import sys
import types
from pathlib import Path

import pytest
from unittest.mock import MagicMock


# ---- mcp.* stubs ----

_mcp_types = types.ModuleType("mcp.types")
_mcp_types.CallToolResult = MagicMock


class _FakeTextContent:
    def __init__(self, type: str = "text", text: str = ""):
        self.type = type
        self.text = text


_mcp_types.TextContent = _FakeTextContent
_mcp_types.Tool = MagicMock


def _noop_decorator(*args, **kwargs):
    def decorator(fn):
        return fn
    return decorator


class _FakeServer:
    def __init__(self, *args, **kwargs):
        pass

    def list_tools(self):
        return _noop_decorator()

    def call_tool(self):
        return _noop_decorator()


_mcp_server = types.ModuleType("mcp.server")
_mcp_server.Server = _FakeServer

_mcp_server_stdio = types.ModuleType("mcp.server.stdio")
_mcp_server_stdio.stdio_server = MagicMock

_mcp = types.ModuleType("mcp")

for _mod_name, _mod in [
    ("mcp", _mcp),
    ("mcp.types", _mcp_types),
    ("mcp.server", _mcp_server),
    ("mcp.server.stdio", _mcp_server_stdio),
]:
    sys.modules.setdefault(_mod_name, _mod)

# ---- Conditional stubs (don't shadow real installs other tests need) ----

try:
    import supabase  # noqa: F401
except ImportError:
    sys.modules["supabase"] = types.ModuleType("supabase")

try:
    import httpx  # noqa: F401
except ImportError:
    sys.modules["httpx"] = types.ModuleType("httpx")

_dotenv = types.ModuleType("dotenv")
_dotenv.load_dotenv = lambda *a, **kw: None
sys.modules.setdefault("dotenv", _dotenv)

# ---- Path + env setup ----

_repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_repo_root / "mcp-memory"))
sys.path.insert(0, str(_repo_root / "scripts"))
sys.path.insert(0, str(_repo_root))
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-key")


# ---------------------------------------------------------------------------
# Contract-style test helpers for memory server tests
# Replace deeply chained MagicMock calls with intent-revealing helpers.
# ---------------------------------------------------------------------------


class _FakeExecute:
    """Wraps .execute() return — avoids client.table.return_value.X.Y.Z chains."""

    def __init__(self, data: list | None = None):
        self._data = data or []
        self.execute_called = False

    def execute(self):
        self.execute_called = True
        return MagicMock(data=self._data)


class _FakeQueryResult:
    """Single .data holder — returned by _FakeTable execute paths."""

    def __init__(self, data: list):
        self.data = data


class _FakeTable:
    """Contract-style Supabase table double: tracks calls, returns predictable
    execute data. Reduces MagicMock call-chain noise in handler tests.

    Usage::

        tbl = _FakeTable(upsert_data=[{"id": "stored-1"}])
        tbl.upsert({"name": "x"}).execute()
        assert tbl.upsert_called_with == {"name": "x"}

        # Access raw execute returns:
        tbl.upsert({"name": "y"}).execute()
        assert len(tbl.upsert_calls) == 2
    """

    def __init__(
        self,
        *,
        upsert_data: list | None = None,
        insert_data: list | None = None,
        select_data: list | None = None,
    ):
        self._upsert_data = upsert_data
        self._insert_data = insert_data
        self._select_data = select_data
        self.upsert_calls: list[dict] = []
        self.insert_calls: list[dict] = []
        self.select_calls: list[tuple] = []
        self.update_calls: list[dict] = []
        self.last_method: str | None = None

    # -- builder chain (return self so chaining works via MagicMock) --

    def upsert(self, data):
        self.upsert_calls.append(data)
        self.last_method = "upsert"
        return self._make_chain()

    def insert(self, data):
        self.insert_calls.append(data)
        self.last_method = "insert"
        return self._make_chain()

    def select(self, *args, **kwargs):
        self.select_calls.append((args, kwargs))
        self.last_method = "select"
        return self._make_chain()

    def update(self, data):
        self.update_calls.append(data)
        self.last_method = "update"
        return self._make_chain()

    def eq(self, *args, **kwargs):
        return self._make_chain()

    def is_(self, *args, **kwargs):
        return self._make_chain()

    def limit(self, *args, **kwargs):
        return self._make_chain()

    def order(self, *args, **kwargs):
        return self._make_chain()

    def execute(self):
        """Direct execute — fallback when chain was never started."""
        return _FakeQueryResult(self._upsert_data or self._insert_data or [])

    def _make_chain(self):
        """Return a MagicMock that .execute() resolves to the pre-set data."""
        m = MagicMock()
        if self.last_method == "upsert" and self._upsert_data is not None:
            m.execute.return_value = _FakeQueryResult(self._upsert_data)
        elif self.last_method == "insert" and self._insert_data is not None:
            m.execute.return_value = _FakeQueryResult(self._insert_data)
        elif self.last_method == "select" and self._select_data is not None:
            m.execute.return_value = _FakeQueryResult(self._select_data)
        else:
            m.execute.return_value = _FakeQueryResult([])
        # Allow further chaining
        m.eq.return_value = m
        m.is_.return_value = m
        m.limit.return_value = m
        m.order.return_value = m
        m.filter.return_value = m
        m.in_.return_value = m
        return m

    @property
    def upsert_called_with(self):
        return self.upsert_calls[-1] if self.upsert_calls else None

    @property
    def insert_called_with(self):
        return self.insert_calls[-1] if self.insert_calls else None


@pytest.fixture
def make_mock_client():
    """Factory fixture: returns a function that creates a contract-style
    mock Supabase client with a _FakeTable wired to table()."""
    def _make(table_kwargs: dict | None = None):
        client = MagicMock()
        client._table = _FakeTable(**(table_kwargs or {}))
        client.table.return_value = client._table
        client.rpc.return_value.execute.return_value = MagicMock(data=[])
        return client
    return _make
