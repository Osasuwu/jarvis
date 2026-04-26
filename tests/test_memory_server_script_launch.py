"""Smoke test: launch mcp-memory/server.py as a script (the way MCP clients do).

The pytest path imports server.py as module `server`, which masks the
circular-import class of bug — handlers do `import server` at module top to
reach shared utilities, and that resolves trivially when `server` is already
in sys.modules. When MCP launches the file as a script, Python sets
`__name__='__main__'` and handlers' `import server` triggers a fresh re-execution
that re-enters the partially-loaded handler chain → ImportError.

This test reproduces the script launch and asserts: process survives import +
no traceback on stderr.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
SERVER = REPO_ROOT / "mcp-memory" / "server.py"


def test_server_script_launch_does_not_crash_on_import():
    proc = subprocess.Popen(
        [sys.executable, str(SERVER)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(REPO_ROOT),
    )
    try:
        time.sleep(3)
        if proc.poll() is not None:
            stderr = proc.stderr.read().decode("utf-8", errors="replace") if proc.stderr else ""
            stdout = proc.stdout.read().decode("utf-8", errors="replace") if proc.stdout else ""
            pytest.fail(
                f"server.py exited during import (rc={proc.returncode})\n"
                f"--- stderr ---\n{stderr}\n--- stdout ---\n{stdout}"
            )
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)

    stderr = proc.stderr.read().decode("utf-8", errors="replace") if proc.stderr else ""
    assert "ImportError" not in stderr, f"ImportError on script launch:\n{stderr}"
    assert "Traceback" not in stderr, f"Unexpected traceback on script launch:\n{stderr}"
