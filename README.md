# Jarvis

Universal personal AI agent built on [Claude Code](https://code.claude.com) + [MCP](https://modelcontextprotocol.io/).

Jarvis extends Claude Code with persistent cross-device memory, a Telegram interface, and an autonomous self-improvement loop — turning it from a workstation tool into a personal assistant you can reach from anywhere.

> **Status:** Active development. Core memory system and Claude Code native architecture functional.

## What makes this different

Claude Code is powerful but has limitations for personal assistant use:
- Memory is local to one machine
- No mobile interface
- No autonomous background operation
- No self-improvement loop

Jarvis adds exactly these missing pieces as a thin layer on top of Claude Code.

## Architecture

```
┌─────────────┐         ┌─────────────────────────────────────┐
│   Telegram  │         │           Claude Code                │
│  (mobile)   │         │                                      │
└──────┬──────┘         │  .claude/skills/   ← PM, research,  │
       │ Claude Code    │  .claude/agents/      delegation     │
       │ Channels       │  .claude/CLAUDE.md ← identity+rules  │
       └───────────────▶│  config/SOUL.md    ← personality     │
                        │                                      │
                        │  MCP Servers:                        │
                        │  - memory    ← Supabase (this repo) │
                        │  - github    ← official MCP          │
                        │  - filesystem ← official MCP         │
                        └─────────────────────────────────────┘
                                         │
                                   Supabase DB
                              (memory syncs across
                               all devices/projects)
```

**Inside Claude Code** (native features — zero Python needed):
- Skills: triage, issue-health, research, delegate, self-review, self-improve, risk-radar
- Subagents with model routing (Haiku for cheap tasks, Sonnet for complex)
- SOUL.md personality loaded into every session
- Telegram/Discord/iMessage via [Claude Code Channels](https://code.claude.com/docs/en/channels)

**External Python** (only what Claude Code genuinely can't do):
- `mcp-memory/` — MCP server for cross-device Supabase memory ✅
- `src/risk_radar.py` — standalone deterministic risk scan (no LLM) ✅
- `src/scheduler/` — autonomous background tasks *(planned)*

## Features

| Feature | Status |
|---------|--------|
| Cross-device memory (Supabase MCP) | ✅ Working |
| PM skills (triage, issue-health, risk-radar) | ✅ Working |
| Research skill (web search + source validation) | ✅ Working |
| Delegation pipeline (issue → PR via coding agent) | ✅ Working |
| Telegram interface (Claude Code Channels) | ✅ Working |
| Self-review + self-improve loop | 🔧 In progress |
| Autonomous scheduler | 📋 Planned |

## Prerequisites

- [Claude Code](https://code.claude.com) v2.1.80+ installed and authenticated
- [Bun](https://bun.sh) (required for Claude Code Channels plugins)
- Python 3.11+
- [Supabase](https://supabase.com) account (free tier sufficient)
- [GitHub CLI](https://cli.github.com) authenticated

## Quick Start

```bash
git clone https://github.com/Osasuwu/personal-AI-agent.git
cd personal-AI-agent
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[memory]"
```

### Set up Supabase memory

1. Create a free project at [supabase.com](https://supabase.com)
2. Run `mcp-memory/schema.sql` in the Supabase SQL Editor
3. Set environment variables:

```bash
# Linux/macOS
export SUPABASE_URL=https://your-project.supabase.co
export SUPABASE_KEY=your-anon-key

# Windows (PowerShell, persistent)
[System.Environment]::SetEnvironmentVariable("SUPABASE_URL", "https://your-project.supabase.co", "User")
[System.Environment]::SetEnvironmentVariable("SUPABASE_KEY", "your-anon-key", "User")
```

4. The memory MCP server is already configured in `.mcp.json`. Claude Code will auto-connect when you open the project.

### Set up Telegram

See [docs/telegram-setup.md](docs/telegram-setup.md) for the full guide. Short version:

1. Create a bot via [@BotFather](https://t.me/botfather) on Telegram → get `TELEGRAM_BOT_TOKEN`
2. Install the plugin in Claude Code: `/plugin install telegram@claude-plugins-official`
3. Set the token: write `TELEGRAM_BOT_TOKEN=<your-token>` to `~/.claude/channels/telegram/.env`
4. Start with Channels: `claude --channels plugin:telegram@claude-plugins-official`
5. Pair your account: `/telegram:access pair` → send the code to your bot → `/telegram:access policy allowlist`

### Verify

Open the project in Claude Code and run `/triage` or ask "check risks". The agent should read `config/SOUL.md`, recall memory, and behave as Jarvis.

## Memory system

The MCP memory server (`mcp-memory/server.py`) provides persistent memory across all devices and projects via Supabase.

**Available tools in Claude Code:**

| Tool | Description |
|------|-------------|
| `memory_store` | Save/update a memory (upserts by project+name) |
| `memory_recall` | Search memories by keyword |
| `memory_get` | Fetch a specific memory by name |
| `memory_list` | List all memories (name + description) |
| `memory_delete` | Remove a memory |

**Memory types:** `user`, `project`, `decision`, `feedback`, `reference`

**Cross-device sync:** all devices connect to the same Supabase instance. No manual sync needed.

**Cross-project:** set `project=null` for memories that apply everywhere (user preferences, agent behavior rules), or `project="your-project"` for project-specific context.

## Project structure

```
.claude/
  CLAUDE.md         ← agent instructions (auto-loaded by Claude Code)
  skills/           ← custom slash commands (Claude Code native)
  agents/           ← subagent definitions
mcp-memory/
  server.py         ← MCP memory server
  schema.sql        ← Supabase table schema
  requirements.txt  ← mcp, supabase, python-dotenv
config/
  SOUL.md           ← Jarvis personality definition
  repos.conf        ← repos to scan (triage, risk-radar)
docs/
  PROJECT_PLAN.md   ← vision, milestones, architecture decisions
  telegram-setup.md ← step-by-step Telegram setup
src/
  risk_radar.py     ← standalone risk scan script
.mcp.json           ← MCP server registry
pyproject.toml      ← Python packaging
```

## Using on multiple devices

1. Clone the repo on each device
2. Set `SUPABASE_URL` and `SUPABASE_KEY` env vars on each device
3. `pip install -e ".[memory]"` on each device
4. Open in Claude Code — memory syncs automatically via Supabase

No other setup needed. All context lives in Supabase, all instructions live in the repo.

## Contributing

This project is open source and welcomes contributions. See [docs/PROJECT_PLAN.md](docs/PROJECT_PLAN.md) for the vision and current priorities.

Before contributing, check existing GitHub Discussions for similar ideas. Issues are tracked in [GitHub Issues](https://github.com/Osasuwu/personal-AI-agent/issues).

## License

MIT — see [LICENSE](LICENSE).
