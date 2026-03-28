# Jarvis

Universal personal AI agent built on [Claude Code](https://code.claude.com) + [MCP](https://modelcontextprotocol.io/).

Jarvis extends Claude Code with persistent cross-device memory, a Telegram interface, and an autonomous self-improvement loop — turning it from a workstation tool into a personal assistant you can reach from anywhere.

> **Status:** Active development. Core memory system functional. Reboot to Claude Code native architecture in progress.

## What makes this different

Claude Code is powerful but has limitations for personal assistant use:
- Memory is local to one machine
- No mobile interface
- No autonomous background operation
- No self-improvement loop

Jarvis adds exactly these missing pieces as a thin layer on top of Claude Code.

## Architecture

```
┌─────────────┐    ┌─────────────────────────────────────┐
│   Telegram  │    │           Claude Code                │
│  (mobile)   │    │                                      │
└──────┬──────┘    │  .claude/skills/   ← PM, research,  │
       │           │  .claude/agents/      delegation     │
       ▼           │  .claude/CLAUDE.md ← identity+rules  │
┌─────────────┐    │                                      │
│ Python      │    │  MCP Servers:                        │
│ relay       │───▶│  - memory    ← Supabase (this repo) │
│ service     │    │  - github    ← official MCP          │
└─────────────┘    │  - filesystem ← official MCP         │
                   └─────────────────────────────────────┘
                                    │
                              Supabase DB
                         (memory syncs across
                          all devices/projects)
```

**Inside Claude Code** (native features — zero Python needed):
- Skills: triage, weekly-report, issue-health, research, delegate, self-review
- Subagents with model routing (Haiku for cheap tasks, Sonnet for complex)
- Hooks for lifecycle automation
- SOUL.md personality loaded into every session

**External Python service** (only what Claude Code can't do):
- `mcp-memory/` — MCP server for cross-device Supabase memory ✅
- `src/telegram/` — Telegram → Claude SDK relay *(planned)*
- `src/scheduler/` — autonomous background tasks *(planned)*

## Features

| Feature | Status |
|---------|--------|
| Cross-device memory (Supabase MCP) | ✅ Working |
| PM skills (triage, weekly-report, issue-health) | ✅ Working |
| Research skill (web search + source validation) | ✅ Working |
| Delegation pipeline (issue → PR via coding agent) | ✅ Working |
| Self-review + self-improve loop | 🔧 In progress |
| Telegram interface | 📋 Planned |
| Autonomous scheduler | 📋 Planned |

## Prerequisites

- [Claude Code](https://code.claude.com) installed and authenticated
- Python 3.11+
- [Supabase](https://supabase.com) account (free tier sufficient)
- [GitHub CLI](https://cli.github.com) authenticated
- Claude API key (for delegation pipeline)

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

### Verify

Open the project in Claude Code and run:
```
/memory-list
```

Or ask Claude Code directly — it should call `memory_recall` at session start and have context about the project.

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
docs/
  PROJECT_PLAN.md   ← vision, milestones, architecture decisions
src/                ← external Python services (telegram, scheduler)
.mcp.json           ← MCP server registry
pyproject.toml      ← Python packaging
```

## Using on multiple devices

1. Clone the repo on each device
2. Set `SUPABASE_URL` and `SUPABASE_KEY` env vars on each device
3. `pip install -e ".[memory]"` on each device
4. Open in Claude Code — memory syncs automatically

No other setup needed. All context lives in Supabase, all instructions live in the repo.

## Contributing

This project is open source and welcomes contributions. See [docs/PROJECT_PLAN.md](docs/PROJECT_PLAN.md) for the vision and current priorities.

Before contributing, check existing GitHub Discussions for similar ideas. Issues are tracked in [GitHub Issues](https://github.com/Osasuwu/personal-AI-agent/issues).

## License

MIT — see [LICENSE](LICENSE).
