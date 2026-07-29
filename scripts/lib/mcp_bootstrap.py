"""Shared stdlib-only helper for the three MCP bootstrap scripts (#1312 AC#4).

Each launcher (run-memory-server.py, run-status-server.py,
run-telegram-mcp.py) finds the venv python then hands off to
run_server_tracked() here: the child's stdout is left connected to the
parent's (it IS the JSON-RPC transport and must never be touched or
captured), the child's stderr is redirected to a per-server log file instead
of inheriting the parent's, and a non-zero exit appends one breadcrumb line
to .claude/mcp-failures.jsonl for scripts/session-context.py's
_check_mcp_failures to surface.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def run_server_tracked(name, python, server, root, _subprocess_run=None, _now=None) -> int:
    root = Path(root)
    log_dir = root / ".claude" / "logs"
    failures_path = root / ".claude" / "mcp-failures.jsonl"
    run = _subprocess_run or subprocess.run

    errf = None
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        errf = open(log_dir / f"mcp-{name}.stderr.log", "ab")
    except OSError:
        errf = None

    try:
        result = run([python, server], stdout=None, stderr=errf, stdin=None)
    finally:
        if errf is not None:
            errf.close()

    rc = result.returncode
    if rc != 0:
        _record_failure(failures_path, name, rc, _now)
    return rc


def _record_failure(failures_path: Path, name: str, exit_code: int, _now=None) -> None:
    now = _now if _now is not None else datetime.now(timezone.utc)
    entry = {"server": name, "timestamp": now.isoformat(), "exit_code": exit_code}
    try:
        failures_path.parent.mkdir(parents=True, exist_ok=True)
        with open(failures_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass
