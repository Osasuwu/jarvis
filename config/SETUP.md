# Jarvis Setup Guide

## Prerequisites

- Python 3.11+
- Claude Code CLI (`claude`) installed and authenticated
- GitHub CLI (`gh`) authenticated
- Node.js 18+ (for MCP servers via `npx`)
- Windows 11 (primary), Linux/macOS supported

## 1. Python Environment

```powershell
cd personal-AI-agent
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

## 2. Install Dependencies

```powershell
# MCP memory server (the only Python runtime component)
pip install -r mcp-memory/requirements.txt

# Or via pyproject.toml optional deps:
pip install -e ".[memory]"

# Dev tools (pytest, ruff)
pip install -e ".[dev]"
```

The only justified Python in this project is `mcp-memory/server.py`. Everything else is Claude Code native (skills, hooks, subagents).

## 3. Configure Secrets

Create a `.env` file in the **parent directory** (`~/Github/.env`) — this is shared across projects and loaded by the MCP memory server via `python-dotenv`:

```ini
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=eyJ...
VOYAGE_API_KEY=pa-...
```

Optional (set as system env vars if needed):
- `ANTHROPIC_API_KEY` — only if using Claude API directly (not needed for Claude Code CLI)
- `GITHUB_TOKEN` — for GitHub MCP server (falls back to `gh auth`)
- `TELEGRAM_BOT_TOKEN` — for Telegram Channels integration

> **Note:** `.env` is in `.gitignore`. Never commit secrets.

## 4. Supabase Setup

1. Create a Supabase project at [supabase.com](https://supabase.com)
2. Run the schema from `mcp-memory/schema.sql` in the SQL editor
3. Copy the project URL and anon key to `.env`

This is the **only cross-device persistent memory** — local `~/.claude/` memory doesn't sync.

## 5. MCP Configuration

MCP servers are declared in `.mcp.json` (repo root). Current setup:

| Server | Purpose | Command |
|--------|---------|---------|
| `memory` | Supabase persistent memory | `python mcp-memory/server.py` |
| `github` | Issues, PRs, metadata | `npx @modelcontextprotocol/server-github` |
| `filesystem` | Read/write workspace files | `npx @modelcontextprotocol/server-filesystem` |
| `reddit` | Reddit browsing (no auth) | `uvx reddit-no-auth-mcp-server` |

The same `.mcp.json` is also symlinked/copied to `~/Github/.mcp.json` for cross-project access.

## 6. Telegram Integration

Telegram access uses **Claude Code Channels** (not custom Python):

1. Create bot via [@BotFather](https://t.me/BotFather)
2. Set `TELEGRAM_BOT_TOKEN` in `.env` or system env
3. See `docs/telegram-setup.md` for detailed instructions

## 7. Model Routing Policy

| Task type | Model |
|-----------|-------|
| Triage, reports, searches, simple edits | Haiku |
| Planning, coding, research, debugging | Sonnet (default) |
| Deep architectural reasoning (manual only) | Opus |

Budget target: ~$20/month.

## 8. Skills

Skills live in `.claude/skills/*/SKILL.md`:

| Skill | Purpose |
|-------|---------|
| `triage` | Board health, issue triage |
| `delegate` | Autonomous issue implementation |
| `research` | Topic investigation, comparison |
| `risk-radar` | CI health, security alerts, risk scan |
| `self-review` | Codebase quality audit |

Invoked via `/skill-name` in Claude Code.

## 9. Quick Validation Checklist

- [ ] `gh auth status` — GitHub CLI authenticated
- [ ] `.venv` created and `mcp-memory/requirements.txt` installed
- [ ] `.env` exists with `SUPABASE_URL`, `SUPABASE_KEY`
- [ ] `python mcp-memory/server.py` starts without errors (Ctrl+C to stop)
- [ ] `claude` CLI opens and MCP memory tools appear (check with `/mcp`)
- [ ] `memory_store` / `memory_recall` work in a Claude Code session

## Key Paths

| What | Path |
|------|------|
| Personality | `config/SOUL.md` |
| Setup | `config/SETUP.md` (this file) |
| Strategy | `docs/PROJECT_PLAN.md` |
| Architecture | `docs/architecture.md` |
| Telegram guide | `docs/telegram-setup.md` |
| Skills | `.claude/skills/*/SKILL.md` |
| MCP config | `.mcp.json` |
| Memory server | `mcp-memory/server.py` |
| Supabase schema | `mcp-memory/schema.sql` |
| Python deps | `pyproject.toml` |
