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
