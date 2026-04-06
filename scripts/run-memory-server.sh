#!/bin/bash
# Cross-platform wrapper for mcp-memory server.
# Finds the venv python automatically — no env vars needed.
# Used by .mcp.json as the memory server command.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

if [ -f "$PROJECT_ROOT/.venv/Scripts/python.exe" ]; then
  exec "$PROJECT_ROOT/.venv/Scripts/python.exe" "$PROJECT_ROOT/mcp-memory/server.py"
elif [ -f "$PROJECT_ROOT/.venv/bin/python" ]; then
  exec "$PROJECT_ROOT/.venv/bin/python" "$PROJECT_ROOT/mcp-memory/server.py"
else
  echo "Error: no venv found at $PROJECT_ROOT/.venv" >&2
  echo "Run: scripts/setup-device.sh" >&2
  exit 1
fi
