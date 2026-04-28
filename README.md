# Jarvis

Personal AI agent built on [Claude Code](https://claude.ai/code) + [MCP](https://modelcontextprotocol.io/).

> **Jarvis -- cognitive extension of a developer: sees the full picture, works while you sleep, argues when you're wrong, and gets more accurate every day.**

Not a tool, not an assistant -- an extension of thinking capacity, memory, and executive function. A solo developer lacks not hands but **breadth**. Jarvis compensates: tracking, researching, monitoring, remembering, prioritizing.

> **Status:** v0.2.0 -- core memory + skills working. [Roadmap below](#roadmap).

## Quick Start

```bash
git clone https://github.com/Osasuwu/jarvis.git
cd jarvis
python scripts/setup-device.py
```

The setup script handles everything interactively:
- Creates Python venv + installs dependencies
- Prompts for Supabase credentials (free tier sufficient)
- Tests the database connection
- Validates all prerequisites and project files

After setup, open in Claude Code and run `/status`.

### Prerequisites

- [Claude Code](https://claude.ai/code) installed and authenticated
- Python 3.11+
- Node.js 18+ (for MCP servers via `npx`)
- [Supabase](https://supabase.com) account (free tier)
- [GitHub CLI](https://cli.github.com) (optional, for GitHub MCP)

## Architecture

```
You (any device)
  |
  |-- Claude Code CLI / Desktop / Web
  |     |
  |     |-- ~/.claude/skills/      12 universal slash commands (user-level, CWD-agnostic)
  |     |-- ~/.claude/SOUL.md      personality (auto-loaded)
  |     |-- ~/.claude/settings.json    hooks (SessionStart, PreToolUse, ...)
  |     |-- ~/.claude/.mcp.json    MCP servers (memory, github, context7, ...)
  |     |
  |     |-- jarvis/CLAUDE.md       project rules + autonomy config
  |     |-- jarvis/.claude/        project-scoped extras (e.g. /sprint-report)
  |     |
  |-- Telegram (via Claude Code Channels, optional)

Supabase DB
  |-- memories    (vector search, graph links)
  |-- goals       (strategic context)
  |-- events      (CI, alerts, deployments)
```

User-level Jarvis is seeded from `.claude-userlevel/` in this repo by
`install.ps1` / `install.sh` (idempotent, backup-first). See
`scripts/install/installer.py`.

**Design principle:** Claude Code native first. The only custom Python is `mcp-memory/server.py` -- everything else uses skills, hooks, and subagents.

## What's Working

| Component | Description |
|-----------|-------------|
| **Cross-device memory** | MCP server syncs memories, goals, events via Supabase. Vector search (Voyage AI) + keyword fallback |
| **8 skills** | `/status`, `/implement`, `/delegate`, `/research`, `/self-improve`, `/goals`, `/end`, `/end-quick` |
| **SOUL.md personality** | Auto-loaded every session via hook. Opinionated, direct, bilingual (RU/EN) |
| **Goal-aware decisions** | Jarvis knows priorities and pushes back when a task conflicts with active goals |
| **Delegation pipeline** | Issue -> branch -> coding agent -> PR, with verification |
| **Setup script** | `python scripts/setup-device.py` -- interactive, validates everything |

## Skills

| Skill | Trigger | What it does |
|-------|---------|-------------|
| `/status` | Session start, "what's happening" | Project dashboard: git, PRs, issues, CI, risks, goals |
| `/implement` | "реализуй #42", "implement #X" | Issue → branch → inline implementation → PR (main session does the work) |
| `/delegate` | "делегируй #X #Y", "раскидай на агентов" | Multiple issues → parallel coding subagents, orchestrator reviews each diff + decides merge |
| `/research` | "research X", "compare A vs B" | Web research with source validation |
| `/self-improve` | "improve yourself" | Gap analysis -> ideation -> research -> implementation |
| `/goals` | "goals", "priorities" | View, set, update strategic goals in Supabase |
| `/end` | End of session | Behavioral reflection, decision log, memory save, commit |
| `/end-quick` | Quick exit | Checkpoint + commit only |

## Memory System

The MCP memory server (`mcp-memory/server.py`) provides persistent memory across all devices and projects.

| Tool | Description |
|------|-------------|
| `memory_store` | Save/update a memory (upserts by project+name) |
| `memory_recall` | Semantic + keyword search across memories |
| `memory_list` | List all memories (name + description) |
| `memory_get` | Fetch a specific memory by name |
| `memory_delete` | Remove a memory |
| `goal_set` / `goal_list` / `goal_update` | Manage strategic goals |

Memory types: `user`, `project`, `decision`, `feedback`, `reference`

All devices connect to the same Supabase instance. No manual sync.

## Roadmap

9 pillars, two layers. Core = how Jarvis thinks. Reach = how Jarvis interacts with the world.

### Core

| Pillar | Status | Description |
|--------|--------|-------------|
| 1. Goals & Strategic Context | Done | Goal-aware decisions, push-back, priority tracking |
| 2. Autonomous Work Loop | ~90% | Event perception, judgment, continuous operation |
| 3. Outcome Tracking & Learning | ~40% | Verify results, learn from patterns |
| 4. Memory 2.0 | ~85% | Graph relations, temporal awareness, auto-hygiene |

### Reach

| Pillar | Status | Description |
|--------|--------|-------------|
| 5. Integrations / Data Access | Early | Read access to owner's accounts and services |
| 6. Data Intelligence | Not started | Cross-platform search, pattern detection |
| 7. Agent System | Prototype | Scalable multi-agent architecture |
| 8. Identity & Interface | Partial | TTS/STT, Telegram, professional document drafting |
| 9. Security & Digital Hygiene | Not started | Password audit, breach monitoring, proactive protection |

Architecture detail (17 capabilities, 5 layers, migration order) — [docs/design/jarvis-v2-redesign.md](docs/design/jarvis-v2-redesign.md). Vision — [docs/VISION.md](docs/VISION.md). Active sprint scope — [GitHub milestones](https://github.com/Osasuwu/jarvis/milestones).

## Project Structure

```
jarvis/
  CLAUDE.md              <- agent rules (auto-loaded by Claude Code)
  .mcp.json              <- MCP server registry
  config/
    SOUL.md              <- personality definition
    repos.conf           <- repos to scan
  .claude/
    skills/              <- 7 custom slash commands
    agents/              <- subagent definitions (coding)
    settings.json        <- project hooks
  mcp-memory/
    server.py            <- MCP memory server (Supabase)
    schema.sql           <- database schema (memories, goals, events)
  scripts/
    setup-device.py      <- interactive device setup
    session-context.py   <- loads context at session start
  src/
    risk_radar.py        <- standalone risk scan (no LLM)
  docs/                  <- vision, architecture, guides
```

## Using on Multiple Devices

1. Clone the repo
2. Run `python scripts/setup-device.py`
3. Open in Claude Code
4. (Optional) Run `/setup-tasks` to register scheduled automation (daily briefs, risk radar, etc.)

Memory syncs automatically via Supabase. All config lives in the repo.

## Contributing

Contributions welcome. See [open issues](https://github.com/Osasuwu/jarvis/issues) and [milestones](https://github.com/Osasuwu/jarvis/milestones) for current priorities.

Issues: [GitHub Issues](https://github.com/Osasuwu/jarvis/issues)

## License

MIT -- see [LICENSE](LICENSE).
