# Jarvis Setup Guide

> First-time setup on a new device. Takes ~10 minutes.

## Prerequisites

> **Cost of entry:** Claude Code requires a paid Claude.ai plan (Pro, Max, or Team) or Anthropic API billing. There is no free tier that covers Claude Code. Budget this before starting.

- Python 3.11+
- [Claude Code](https://claude.ai/code) installed and authenticated (`claude --version`)
- [GitHub CLI](https://cli.github.com) installed and authenticated (`gh auth status`)
- [Supabase](https://supabase.com) account (free tier sufficient)
- Claude Code CLI (`claude`) installed and authenticated
- GitHub CLI (`gh`) authenticated
- Node.js 18+ (for MCP servers via `npx`)
- Windows 11 (primary), Linux/macOS supported

---

## 1. Clone, configure repos, and create virtual environment

```bash
git clone https://github.com/Osasuwu/jarvis.git
cd jarvis
```

**Edit `config/repos.conf` before running `/status` or `/triage`** — it ships with the original author's repos. Replace those lines with your own (`owner/repo` format, one per line) so skill output refers to your projects, not someone else's.

```bash
# Windows
notepad config\repos.conf

# Linux / macOS
nano config/repos.conf
```

```powershell
cd jarvis
python -m venv .venv

# Windows
.\.venv\Scripts\Activate.ps1

# Linux / macOS
source .venv/bin/activate

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

> **Why not `pip install -r mcp-memory/requirements.txt`?**
> `pyproject.toml` is the single source of truth. `requirements.txt` is a convenience mirror — keep them in sync.

## 3. Configure secrets

The memory server loads `.env` from two locations (first match wins):

1. `jarvis/.env` — project-level (recommended)
2. Parent directory `.env` — shared secrets for all projects

Copy the example and fill in values:

```bash
cp .env.example .env   # run from jarvis/
```

Minimum required values:

```env
ANTHROPIC_API_KEY=sk-ant-...
SUPABASE_URL=https://your-project-id.supabase.co
SUPABASE_KEY=your-anon-key-here
```

No Windows environment variables needed — `python-dotenv` handles it.

> **Where to get Supabase credentials:**
> Supabase dashboard → your project → Settings → API → Project URL + anon public key

### Semantic search — Voyage AI or Ollama (choose one)

Memory recall degrades to keyword-only without a vector embedding provider. Two options:

**Option A — Voyage AI** (cloud, free tier available):
```env
VOYAGE_API_KEY=pa-...
```
Get a key at [voyageai.com](https://www.voyageai.com). Free tier covers typical personal use.

**Option B — Ollama** (local, GPU recommended, no external API needed):
```env
OLLAMA_EMBED_URL=http://localhost:11434
OLLAMA_EMBED_MODEL=mxbai-embed-large
EMBEDDING_MODEL_PRIMARY=mxbai-embed-large
```
Pull the model: `ollama pull mxbai-embed-large`. Requires [Ollama](https://ollama.com) running locally. The `mxbai-embed-large` model uses 1024-dim vectors stored in the `embedding_v2` Supabase column (created by the schema in step 4 below). Do not mix providers in the same database instance — vectors are model-specific.

## 4. Set up Supabase schema

Run `mcp-memory/schema.sql` in the Supabase SQL Editor:

1. Open your Supabase project → SQL Editor
2. Paste contents of `mcp-memory/schema.sql`
3. Click Run

This creates the `memories` table and vector search function.

## 5. Verify MCP memory server

```bash
python mcp-memory/server.py
```

Expected: server starts and waits (no error). Press Ctrl+C to stop.

If you see `SUPABASE_URL and SUPABASE_KEY must be set` — check your `.env`.

## 6. Seed user-level Claude Code config

Run the installer to copy skills, hooks, and MCP config from `.claude-userlevel/` into `~/.claude/`:

```powershell
# Windows
.\install.ps1 -Apply

# Linux / macOS
bash install.sh --apply
```

**What this overwrites vs. preserves in an existing `~/.claude/`:**

| Path | Behaviour |
|---|---|
| `~/.claude/skills/` | **Replaced** — skill files are synced from `.claude-userlevel/skills/` |
| `~/.claude/CLAUDE.md`, `SOUL.md`, `DOCTRINE.md` | **Replaced** — sourced from `.claude-userlevel/` |
| `~/.claude/settings.json` | **Merged** — keys from `.claude-userlevel/settings.json` added, your existing keys preserved |
| `~/.claude/.mcp.json` | **Replaced** — MCP server list is synced from `.claude-userlevel/.mcp.json` |
| `~/.claude/projects/` | **Not touched** — your project memories stay |
| Everything else in `~/.claude/` | **Not touched** |

The installer backs up the existing `~/.claude/` to a timestamped directory before applying. If you already use Claude Code for other projects, the install is safe — only the files listed above change.

`~/.claude/settings.json` is device-local and not synced. The installer seeds it; you can also create it manually:

```json
{
  "effortLevel": "low",
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup",
        "hooks": [
          {
            "type": "command",
            "command": "echo '=== SESSION START CONTEXT ===' && echo '--- jarvis ---' && git -C /path/to/jarvis status --short && echo '========================='"
          }
        ]
      }
    ]
  }
}
```

> Adjust paths to match your device. The hook shows repo status at session start.

## 7. Telegram (optional)

1. Create a bot via [@BotFather](https://t.me/BotFather) → get `TELEGRAM_BOT_TOKEN`
2. Add to `.env`: `TELEGRAM_BOT_TOKEN=123456:ABC-DEF...`
3. Install Claude Code Channels plugin: `/plugin install telegram@claude-plugins-official`
4. Start with Channels: `claude --channels plugin:telegram@claude-plugins-official`
5. Pair: `/telegram:access pair` → send the code to your bot → `/telegram:access policy allowlist`

## 8. Model routing policy

| Tier | Use for |
|------|---------|
| Haiku | Triage, reports, searches, simple edits |
| Sonnet | Planning, coding, complex debugging |
| Opus | Manual-only, high-risk architectural decisions |

Budget target: ~$20/month.

## 9. Safety baseline

- Planner subagent: read-only tools only
- Coder subagent: branch + PR only, never direct push to `main`
- Human review required before merge

## Validation checklist

After setup, verify everything works:

```bash
# Python dependencies
python -c "import mcp, supabase, httpx; print('deps OK')"

# Supabase connection
python -c "
from dotenv import load_dotenv; load_dotenv()
import os; from supabase import create_client
c = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_KEY'])
print('Supabase OK:', c.table('memories').select('id').limit(1).execute())
"

# Claude Code
claude --version

# GitHub CLI
gh auth status
```

Then open the project in Claude Code and run `/triage`.

---

## Key paths

| What | Path |
|------|------|
| Secrets | `.env` (not committed) |
| Secrets template | `.env.example` |
| Personality | `config/SOUL.md` |
| MCP config | `.mcp.json` (repo root) |
| Memory server | `mcp-memory/server.py` |
| Memory schema | `mcp-memory/schema.sql` |
| Claude Code global config | `~/.claude/settings.json` (seeded from `.claude-userlevel/settings.json` by installer) |
| Universal skills (source) | `.claude-userlevel/skills/` (installs to `~/.claude/skills/`) |
| Project-scoped skills | `.claude/skills/` (jarvis-only — currently just `/sprint-report`) |
| Installer | `scripts/install/installer.py`, entry points `install.ps1` / `install.sh` |
