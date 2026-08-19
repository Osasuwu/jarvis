"""Tests for scripts/lib/mcp_stdio.py (#1646).

Covers: OSError(errno=22) raised from stdio_server()'s teardown is swallowed
(Windows stdin-pipe-already-closed crash); any other OSError still
propagates (proves errno-specific scoping, not blanket OSError suppression).
"""

import errno
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "scripts" / "lib"))

import mcp_stdio  # noqa: E402


class _RaisingStdioCM:
    """Fake stand-in for stdio_server() that raises `err` from __aexit__,
    mimicking anyio's flush()-during-teardown OSError."""

    def __init__(self, err):
        self._err = err

    async def __aenter__(self):
        return (object(), object())

    async def __aexit__(self, exc_type, exc, tb):
        if self._err is not None:
            raise self._err
        return False


class _FakeServer:
    def __init__(self):
        self.ran = False

    async def run(self, read_stream, write_stream, init_options):
        self.ran = True

    def create_initialization_options(self):
        return "opts"


async def test_run_stdio_server_swallows_errno_22(monkeypatch):
    err = OSError(errno.EINVAL, "Invalid argument")
    assert err.errno == 22
    monkeypatch.setattr(mcp_stdio, "stdio_server", lambda: _RaisingStdioCM(err))

    server = _FakeServer()
    await mcp_stdio.run_stdio_server(server)  # must not raise

    assert server.ran is True


async def test_run_stdio_server_propagates_other_errno(monkeypatch):
    err = OSError(errno.EACCES, "Permission denied")
    monkeypatch.setattr(mcp_stdio, "stdio_server", lambda: _RaisingStdioCM(err))

    server = _FakeServer()
    try:
        await mcp_stdio.run_stdio_server(server)
    except OSError as exc:
        assert exc.errno == errno.EACCES
    else:
        raise AssertionError("expected OSError to propagate")


async def test_run_stdio_server_calls_run_with_streams_and_init_options(monkeypatch):
    monkeypatch.setattr(mcp_stdio, "stdio_server", lambda: _RaisingStdioCM(None))

    calls = []

    class _Server(_FakeServer):
        async def run(self, read_stream, write_stream, init_options):
            calls.append((read_stream, write_stream, init_options))

    server = _Server()
    await mcp_stdio.run_stdio_server(server)

    assert len(calls) == 1
    _, _, init_options = calls[0]
    assert init_options == "opts"
