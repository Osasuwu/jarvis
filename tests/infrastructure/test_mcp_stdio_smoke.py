"""Subprocess-level smoke test for run_stdio_server() (#1646).

Spawns each MCP server as a real script process (the way Claude Code launches
them) with stdin closed immediately (stdin=DEVNULL) — the exact condition
that reproduces the Windows `OSError: [Errno 22] Invalid argument` teardown
crash the mcp_stdio.run_stdio_server() wrapper exists to swallow. Asserts the
process exits cleanly (rc=0) and stderr contains no OSError/errno-22 trace.

Known environment gap (unrelated to this fix, pre-existing): the `mcp` SDK
installed in this dev environment does not export `ServerRequestContext` from
`mcp.server` (v1.27.0's `__all__` omits it — see
tests/memory/test_memory_server_script_launch.py's docstring/history for the
same gap surfacing there). That makes every real (non-stubbed) script launch
of these servers fail at import time in this environment, regardless of the
stdio-teardown fix under test. These tests document the intended contract and
will pass once that SDK/environment mismatch is resolved separately.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SERVERS = [
    REPO_ROOT / "mcp-memory" / "server.py",
    REPO_ROOT / "mcp-status" / "server.py",
    REPO_ROOT / "mcp-morning" / "server.py",
]


@pytest.mark.parametrize("server_path", SERVERS, ids=lambda p: p.parent.name)
def test_server_exits_cleanly_on_immediate_stdin_close(server_path):
    proc = subprocess.Popen(
        [sys.executable, str(server_path)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(REPO_ROOT),
    )
    try:
        rc = proc.wait(timeout=10)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)

    stderr = proc.stderr.read().decode("utf-8", errors="replace") if proc.stderr else ""

    assert "OSError" not in stderr, f"unswallowed OSError on clean stdin-close:\n{stderr}"
    assert "Errno 22" not in stderr, f"errno-22 teardown crash leaked to stderr:\n{stderr}"
    assert rc == 0, f"server.py exited rc={rc} on immediate stdin close\n--- stderr ---\n{stderr}"
