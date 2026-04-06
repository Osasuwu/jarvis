# Setup — personal-AI-agent

## Quick start (new device)

```bash
git clone https://github.com/Osasuwu/personal-AI-agent ~/GitHub/personal-AI-agent
cd ~/GitHub/personal-AI-agent
bash scripts/setup-device.sh
```

The script is idempotent — safe to re-run anytime.

## What the script does

1. **Python venv** — creates `.venv/`, installs `mcp-memory/requirements.txt`
2. **`.env`** — copies from `.env.example`, adds `MEMORY_PYTHON` path
3. **Git hook** — installs `post-commit` for skills sync to parent `~/GitHub`
4. **User settings** — creates minimal `~/.claude/settings.json` (model pref only)
5. **Validation** — checks Python packages, env vars, config files

## Manual steps after script

1. **Fill secrets** in `.env`:
   - `SUPABASE_URL` / `SUPABASE_KEY` — required (get from Supabase dashboard)
   - `GITHUB_TOKEN` — for MCP GitHub server
   - `FIRECRAWL_API_KEY` — for web research
   - `VOYAGE_API_KEY` — optional, for semantic memory search

2. **Verify**: `cd ~/GitHub/personal-AI-agent && claude` — check skills load, `/status` works

## Architecture

```
personal-AI-agent/           ← self-contained, this is Jarvis
├── CLAUDE.md                ← all rules (identity, autonomy, memory, delegation)
├── config/SOUL.md           ← personality
├── .mcp.json                ← project-scope MCP servers (env vars, no hardcoded paths)
├── .env                     ← secrets (gitignored)
├── .claude/
│   ├── skills/              ← all skills (checkpoint, delegate, research, etc.)
│   ├── settings.json        ← project hooks (git-tracked)
│   └── settings.local.json  ← device overrides (gitignored)
├── mcp-memory/              ← Supabase memory MCP server (Python)
├── scripts/
│   ├── setup-device.sh      ← this setup script
│   └── post-commit          ← git hook for skills sync
└── .github/workflows/       ← CI/CD
```

## Parent repo (optional, local workspace only)

If you also use the parent `~/GitHub` workspace for cross-project work:

```bash
git clone https://github.com/Osasuwu/GitHub ~/GitHub
```

The parent repo provides local cross-project awareness but is NOT required — `personal-AI-agent` is fully self-contained.
