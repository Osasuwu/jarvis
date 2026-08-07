"""Drift guard for the slim MCP profile (#1464).

config/mcp-slim.json is the work-session profile launched via
`claude --mcp-config config/mcp-slim.json --strict-mcp-config`.
It must stay a strict subset of the canonical registration source
(.claude-userlevel/.mcp.json) and list only the allowed servers —
a server sneaking in silently re-inflates the startup baseline the
profile exists to cut.
"""

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SLIM_PATH = REPO_ROOT / "config" / "mcp-slim.json"
CANONICAL_PATH = REPO_ROOT / ".claude-userlevel" / ".mcp.json"

ALLOWED_SERVERS = {"memory", "github"}


def _servers(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))["mcpServers"]


def test_slim_profile_lists_only_allowed_servers():
    assert set(_servers(SLIM_PATH)) == ALLOWED_SERVERS


def test_slim_profile_definitions_match_canonical():
    slim = _servers(SLIM_PATH)
    canonical = _servers(CANONICAL_PATH)
    for name, definition in slim.items():
        assert name in canonical, f"{name} not registered in canonical .mcp.json"
        assert definition == canonical[name], (
            f"{name} definition drifted from .claude-userlevel/.mcp.json"
        )
