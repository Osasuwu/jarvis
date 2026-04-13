# Jarvis Architecture

Version: 4.0
Date: 2026-03-31
Status: Active

## 1. System Overview

Jarvis is a personal AI agent built on top of **Claude Code** — not a custom Python application. Claude Code is the runtime; Jarvis adds identity, memory, and skills on top of it.

```
┌──────────────────────────────────────────────────┐
│                   Claude Code                     │
│                                                   │
│  config/SOUL.md      ← Jarvis identity            │
│  .claude/CLAUDE.md   ← session rules              │
│  .claude/skills/     ← custom slash commands      │
│  .claude/agents/     ← subagent definitions       │
│                                                   │
│  MCP Servers:                                     │
│  ├── memory   ← Supabase (this repo)              │
│  ├── github   ← official MCP                      │
│  └── reddit   ← uvx, no auth                     │
└──────────────────────┬───────────────────────────┘
                       │
                  Supabase DB
           (memory syncs across all devices)
```

## 2. What lives where

### Inside Claude Code (zero custom Python)

| Component | Location | Purpose |
|-----------|----------|---------|
| Identity | `config/SOUL.md` | Personality, tone, behavior rules |
| Session init | `.claude/CLAUDE.md` | What to do at session start |
| Skills | `.claude/skills/*/SKILL.md` | User-invoked slash commands |
| Commands | `.claude/commands/*.md` | Additional slash commands |
| Subagents | `.claude/agents/*.md` | Delegated task runners |

### External Python (only what Claude Code can't do)

| Component | Location | Purpose |
|-----------|----------|---------|
| Memory server | `mcp-memory/server.py` | Cross-device Supabase memory via MCP |
| Risk scanner | `src/risk_radar.py` | Deterministic pattern scan, no LLM |

Everything else (Telegram, scheduling, background tasks) uses Anthropic-native features — not custom code.

## 3. Memory architecture

Cross-device memory is the core value-add over vanilla Claude Code.

```
Device A (home)          Device B (work)          Device C (laptop)
     │                        │                        │
     └────────────────────────┼────────────────────────┘
                              │
                    mcp-memory/server.py
                    (runs in .venv, stdio)
                              │
                         Supabase DB
                    (pgvector + VoyageAI)
```

**How it works:**
- `memory_store` — upsert by `(project, name)`, overwrites on conflict
- `memory_recall` — semantic search via VoyageAI embeddings; falls back to ILIKE keyword search if `VOYAGE_API_KEY` not set
- `memory_list` / `memory_get` / `memory_delete` — standard CRUD

**Memory types:** `user`, `project`, `decision`, `feedback`, `reference`

**Scoping:** `project=null` for cross-project (owner preferences, agent rules), `project="jarvis"` or `project="redrobot"` for project-specific context.

## 4. Agent model

Claude Code is the main agent. Subagents are spawned for isolated tasks.

```
Owner
  │ CLI / Telegram Channels
  ▼
Claude Code (Sonnet — default)
  │ orchestration, planning, architecture
  ├── Explore subagent (Haiku) ← recon, file reads, searches
  └── general-purpose subagent (Sonnet) ← implementation
```

### Model routing

| Model | Use for |
|-------|---------|
| `claude-haiku-4-5` | Triage, reports, searches, simple edits |
| `claude-sonnet-4-6` | Planning, coding, research, debugging |
| `claude-opus-4-6` | Manual-only, high-risk architectural decisions |

### Permission model

| Agent | Writes | Tools |
|-------|--------|-------|
| Main (Sonnet) | Yes — full workspace | All |
| Explore (Haiku) | No | Read, Glob, Grep, WebFetch, WebSearch |
| Coding (Sonnet) | Branch + PR only | Read, Edit, Bash, `gh` |

## 5. Skills

Skills live in `.claude/skills/` and are invoked as `/skill-name`.

| Skill | Model | Purpose |
|-------|-------|---------|
| `triage` | Haiku | GitHub board health, stale issues |
| `research` | Sonnet | Topic investigation, source validation |
| `delegate` | Sonnet | Issue → PR via coding subagent |
| `risk-radar` | Haiku | CI health, security alerts, pattern scan |
| `self-review` | Sonnet | Codebase quality audit |
| `self-improve` | Sonnet | Auto-apply low/medium-risk fixes → PR |
| `intel` | Haiku | Claude/MCP/AI ecosystem digest |

Commands in `.claude/commands/`:

| Command | Purpose |
|---------|---------|
| `end` | Session closure — save unsaved decisions |
| `repo-health` | Structural audit (docs, branches, actions) |

## 6. Mobile access

Telegram via **Claude Code Channels** (official Anthropic plugin) — no custom relay code.

Setup: `claude --channels plugin:telegram@claude-plugins-official`

See `docs/telegram-setup.md` for full guide.

## 7. Scheduling

Recurring tasks via **Claude Code `/loop`** or Desktop scheduled tasks — no custom scheduler.

Nightly research runs at 03:00, topics configured in `config/research-topics.yaml`.

## 8. Safety baseline

- Coder subagent: branch + PR only, never direct push to `main`
- Human review required before merge
- Protected files (never auto-modified): `.mcp.json`, `CLAUDE.md`, `mcp-memory/server.py`, `config/SOUL.md`
- Cost default: Haiku; escalate to Sonnet only when reasoning required

## 9. Project structure

```
jarvis/
├── config/
│   ├── SOUL.md              ← Jarvis personality (loaded every session)
│   ├── SETUP.md             ← First-time device setup
│   └── repos.conf           ← Repos scanned by triage/risk-radar
├── mcp-memory/
│   ├── server.py            ← MCP memory server (Supabase)
│   ├── schema.sql           ← Supabase table + vector index
│   └── requirements.txt     ← Python deps for server.py
├── src/
│   └── risk_radar.py        ← Standalone risk scanner (no LLM)
├── tests/
│   └── test_risk_radar.py
├── docs/
│   ├── PROJECT_PLAN.md      ← Vision, milestones
│   ├── architecture.md      ← This file
│   └── telegram-setup.md    ← Telegram Channels setup
├── .claude/
│   ├── CLAUDE.md            ← Session initialization rules
│   ├── skills/              ← Slash commands (model-invoked)
│   ├── commands/            ← Slash commands (user-invoked)
│   └── agents/              ← Subagent definitions
├── .github/
│   └── workflows/           ← CI (PR checks, issue validation)
├── .mcp.json                ← MCP server registry
├── .env.example             ← Secrets template
└── pyproject.toml           ← Python packaging (memory extra)
```
