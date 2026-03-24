# Jarvis Architecture

Version: 3.0
Date: 2026-03-23
Status: Active

## 1. System Overview

Jarvis is a universal personal AI agent built on Claude Agent SDK with MCP integrations. The Agent SDK provides the core agent loop (same engine as Claude Code), while MCP servers connect Jarvis to external services (GitHub, Telegram, filesystem, etc.).

## 2. Platform: Claude Agent SDK

The Agent SDK handles:
- **Agent loop**: prompt → tool calls → results → repeat until done
- **Subagents**: specialized agents with isolated contexts and permissions
- **MCP integration**: connect to any MCP-compatible service
- **Model selection**: Haiku, Sonnet, or Opus per task
- **Context management**: auto-compaction, sessions, streaming
- **Headless mode**: `claude -p` for scripted/cron execution

Jarvis is a Python/TypeScript application that uses the Agent SDK as its runtime.

## 3. Tiered Agent Architecture

```
┌─────────────────────────────────────┐
│            Owner (Human)            │
│  Strategy, PR review, Go/No-Go     │
└──────────┬──────────────────────────┘
           │ Telegram / CLI
           ▼
┌─────────────────────────────────────┐
│     Jarvis Main Agent (Sonnet)      │
│  Command routing, orchestration     │
│                                     │
│  ┌───────────┐  ┌───────────────┐   │
│  │ Subagent: │  │ Subagent:     │   │
│  │ PM/Triage │  │ Code Writer   │   │
│  │ (Haiku)   │  │ (Sonnet)      │   │
│  │ read-only │  │ branch+PR only│   │
│  └───────────┘  └───────────────┘   │
│  ┌───────────┐  ┌───────────────┐   │
│  │ Subagent: │  │ Subagent:     │   │
│  │ Researcher│  │ Self-check    │   │
│  │ (Sonnet)  │  │ (Haiku)       │   │
│  │ web search│  │ read-only     │   │
│  └───────────┘  └───────────────┘   │
│                                     │
│  MCP: GitHub, Telegram, Filesystem  │
└─────────────────────────────────────┘
```

### Permission Model

| Subagent | Model | Tools | Writes |
|----------|-------|-------|--------|
| PM/Triage | Haiku | `gh` (read), Glob, Grep, Read | No |
| Code Writer | Sonnet | Read, Edit, Bash, `gh` | Branches + PR only |
| Researcher | Sonnet | WebSearch, WebFetch, Read | Notes only |
| Self-check | Haiku | Read, Glob, Grep | No |

### Safety Layers

1. **Subagent permissions**: each agent has only the tools it needs.
2. **Branch protection**: code changes go through PR, never direct to main.
3. **CLAUDE.md instructions**: repos have conservative-mode rules for agent-generated tasks.
4. **Human review**: owner reviews PRs before merge.
5. **Cost controls**: Haiku by default, Sonnet/Opus only when needed.

## 4. Communication Flow

```
User (Telegram / CLI)
    ↓
Jarvis Main Agent
    ↓ routes command
Appropriate Subagent (with restricted tools)
    ↓ uses MCP servers
GitHub API / Web / Filesystem
    ↓
Response back to user (Telegram / CLI)
```

## 5. LLM Strategy

| Model | Cost (per 1M tokens) | Use case |
|-------|---------------------|----------|
| Haiku 4.5 | $1 input / $5 output | Triage, reports, self-check, simple routing |
| Sonnet 4.6 | $3 input / $15 output | Planning, code writing, research, complex reasoning |
| Opus 4.6 | $5 input / $25 output | Critical architecture decisions (rare, manual only) |

Budget: $10-30/month. Default to Haiku; escalate to Sonnet when task requires reasoning.

### Future: Local LLM as Auxiliary

When ready, Ollama on work PC (RTX 4070) can be wrapped as a custom MCP server. Claude delegates simple tasks (summarization, formatting) to `ollama__*` tools. Not planned for M1/M2.

## 6. Scheduled Execution

Recurring tasks run via system cron (Windows Task Scheduler) or GitHub Actions:

| Task | Schedule | Command |
|------|----------|---------|
| Daily triage | Weekdays 09:00 | `claude -p "/triage" --bare` |
| Weekly report | Friday 17:00 | `claude -p "/weekly-report" --bare` |

Results delivered to Telegram.

## 7. Data and State

- **Conversation context**: managed by Agent SDK (auto-compaction)
- **Session persistence**: Agent SDK sessions (resume conversations)
- **GitHub data**: accessed live via MCP GitHub server (no local cache)
- **Configuration**: `.mcp.json`, `config/`, skill definitions
- **Ideas/brainstorming**: GitHub Discussions on this repo

## 8. Project Structure

```
├── config/
│   ├── SOUL.md              # Jarvis personality and behavior
│   ├── IDENTITY.md          # Core identity
│   ├── USER.md              # Owner profile for personalization
│   └── SETUP.md             # Setup instructions
├── skills/                  # Skill definitions (subagent instructions)
│   ├── triage/              # Daily triage across GitHub projects
│   ├── weekly-report/       # Weekly delivery report
│   └── issue-health/        # Issue metadata validation
├── src/                     # Agent SDK application code
│   ├── main.py              # Entry point
│   ├── jarvis/              # Runtime config and command dispatcher
│   ├── handlers/            # Telegram, cron, webhook handlers (planned)
│   └── agents/              # Subagent definitions (planned)
├── docs/                    # Project documentation
│   ├── PROJECT_PLAN.md      # Strategic plan
│   └── architecture.md      # This file
└── .github/                 # Dev process (CI, PR checks — NOT Jarvis features)
```

## 9. Development Workflow

This repository is developed using Claude Code. The `.github/` directory contains workflows and templates for developing Jarvis itself — they are NOT Jarvis features.

Jarvis features = skills and agent code in `skills/` and `src/`.
Dev process tools = `.github/` workflows, issue templates, PR checks.
