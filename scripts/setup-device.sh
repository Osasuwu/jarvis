#!/bin/bash
# setup-device.sh — Configure a new device for Jarvis (personal-AI-agent)
# Run from anywhere. Idempotent — safe to re-run.
#
# What it does:
#   1. Python venv + memory server deps
#   2. .env from template (prompts for missing secrets)
#   3. Git hook (skills sync)
#   4. User-scope MCP servers (shared across all projects)
#   5. Minimal ~/.claude/settings.json
#   6. Validates everything works

set -euo pipefail

# --- Resolve project root ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=== Jarvis device setup ==="
echo "Project: $PROJECT_ROOT"
echo ""

# --- Detect OS ---
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*) OS="windows" ;;
  Darwin*)               OS="macos" ;;
  Linux*)                OS="linux" ;;
  *)                     OS="unknown" ;;
esac
echo "OS: $OS"

# --- 1. Python venv ---
echo ""
echo "--- Step 1: Python venv ---"

VENV_DIR="$PROJECT_ROOT/.venv"
if [ ! -d "$VENV_DIR" ]; then
  echo "Creating venv..."
  python -m venv "$VENV_DIR"
else
  echo "Venv exists, skipping creation"
fi

# Activate and install deps
if [ "$OS" = "windows" ]; then
  PYTHON="$VENV_DIR/Scripts/python.exe"
  PIP="$VENV_DIR/Scripts/pip.exe"
else
  PYTHON="$VENV_DIR/bin/python"
  PIP="$VENV_DIR/bin/pip"
fi

if [ -f "$PROJECT_ROOT/mcp-memory/requirements.txt" ]; then
  echo "Installing memory server deps..."
  "$PIP" install -q -r "$PROJECT_ROOT/mcp-memory/requirements.txt"
else
  echo "Warning: mcp-memory/requirements.txt not found, skipping"
fi
echo "Done: Python=$PYTHON"

# --- 2. .env file ---
echo ""
echo "--- Step 2: Environment variables ---"

ENV_FILE="$PROJECT_ROOT/.env"
if [ ! -f "$ENV_FILE" ]; then
  if [ -f "$PROJECT_ROOT/.env.example" ]; then
    cp "$PROJECT_ROOT/.env.example" "$ENV_FILE"
    echo "Created .env from template — edit it with your secrets:"
    echo "  $ENV_FILE"
  else
    echo "No .env.example found. Creating minimal .env..."
    cat > "$ENV_FILE" << 'ENVEOF'
# Required
SUPABASE_URL=
SUPABASE_KEY=

# Optional
VOYAGE_API_KEY=
GITHUB_TOKEN=
FIRECRAWL_API_KEY=
ENVEOF
    echo "Created .env — fill in your secrets: $ENV_FILE"
  fi
else
  echo ".env exists, skipping"
fi

# Compute MEMORY_PYTHON (cross-platform venv python path)
MEMORY_PYTHON="$PYTHON"
echo "MEMORY_PYTHON=$MEMORY_PYTHON"

# Check if MEMORY_PYTHON is in .env, add if not
if ! grep -q "^MEMORY_PYTHON=" "$ENV_FILE" 2>/dev/null; then
  echo "" >> "$ENV_FILE"
  echo "# Auto-set by setup-device.sh" >> "$ENV_FILE"
  echo "MEMORY_PYTHON=$MEMORY_PYTHON" >> "$ENV_FILE"
  echo "Added MEMORY_PYTHON to .env"
fi

# --- 3. Git hook ---
echo ""
echo "--- Step 3: Git hook (skills sync) ---"

HOOKS_DIR="$PROJECT_ROOT/.git/hooks"
HOOK_FILE="$HOOKS_DIR/post-commit"
if [ -d "$HOOKS_DIR" ]; then
  cp "$PROJECT_ROOT/scripts/post-commit" "$HOOK_FILE"
  chmod +x "$HOOK_FILE"
  echo "Installed post-commit hook"
else
  echo "Warning: .git/hooks not found — not a git repo?"
fi

# --- 4. User-scope MCP servers ---
echo ""
echo "--- Step 4: User-scope MCP servers ---"

# Check if claude CLI is available
if ! command -v claude &> /dev/null; then
  echo "Warning: 'claude' CLI not found — skipping MCP registration"
  echo "After installing Claude Code, run these manually:"
  echo "  claude mcp add --scope user supabase -- npx -y @anthropic-ai/mcp-server-supabase ..."
else
  # Supabase MCP (cloud-hosted, always available — critical for remote sessions)
  echo "Registering user-scope MCP servers..."

  # Note: Supabase MCP is registered via Claude Code settings, not via `claude mcp add`
  # because it requires project-specific config. The .mcp.json handles this.
  echo "  Supabase MCP: handled by project .mcp.json"
  echo "  Memory MCP: handled by project .mcp.json"
  echo "  User-scope MCP: no additional registration needed"
  echo "  (All project-specific MCPs are in .mcp.json, shared MCPs are cloud-hosted)"
fi

# --- 5. Minimal ~/.claude/settings.json ---
echo ""
echo "--- Step 5: User settings ---"

CLAUDE_DIR="$HOME/.claude"
USER_SETTINGS="$CLAUDE_DIR/settings.json"

mkdir -p "$CLAUDE_DIR"

if [ ! -f "$USER_SETTINGS" ]; then
  cat > "$USER_SETTINGS" << 'SETTINGSEOF'
{
  "preferences": {
    "model": "opus"
  }
}
SETTINGSEOF
  echo "Created minimal ~/.claude/settings.json (model pref only)"
else
  echo "~/.claude/settings.json exists, not overwriting"
fi

# --- 6. Validation ---
echo ""
echo "--- Step 6: Validation ---"

ERRORS=0

# Check Python
if "$PYTHON" -c "import supabase" 2>/dev/null; then
  echo "  [OK] supabase Python package"
else
  echo "  [FAIL] supabase Python package not importable"
  ERRORS=$((ERRORS + 1))
fi

# Check .env has required vars
for var in SUPABASE_URL SUPABASE_KEY; do
  val=$(grep "^${var}=" "$ENV_FILE" 2>/dev/null | cut -d= -f2-)
  if [ -n "$val" ] && [ "$val" != "" ]; then
    echo "  [OK] $var is set"
  else
    echo "  [WARN] $var is empty — fill in .env"
  fi
done

# Check CLAUDE.md exists at project root
if [ -f "$PROJECT_ROOT/CLAUDE.md" ]; then
  echo "  [OK] CLAUDE.md present"
else
  echo "  [FAIL] CLAUDE.md missing"
  ERRORS=$((ERRORS + 1))
fi

# Check skills
SKILL_COUNT=$(find "$PROJECT_ROOT/.claude/skills" -name "SKILL.md" 2>/dev/null | wc -l)
echo "  [OK] $SKILL_COUNT skills found"

# Check .mcp.json
if [ -f "$PROJECT_ROOT/.mcp.json" ]; then
  echo "  [OK] .mcp.json present"
else
  echo "  [FAIL] .mcp.json missing"
  ERRORS=$((ERRORS + 1))
fi

# Check git hook
if [ -x "$HOOK_FILE" ]; then
  echo "  [OK] post-commit hook installed"
else
  echo "  [WARN] post-commit hook not executable"
fi

echo ""
if [ $ERRORS -eq 0 ]; then
  echo "=== Setup complete! ==="
  echo ""
  echo "Next steps:"
  echo "  1. Fill in secrets in $ENV_FILE (if not done)"
  echo "  2. cd $PROJECT_ROOT && claude"
  echo "  3. Verify: skills load, memory works, /status runs"
else
  echo "=== Setup completed with $ERRORS error(s) ==="
  echo "Fix the issues above and re-run this script."
fi
