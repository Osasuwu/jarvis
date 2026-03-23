# Jarvis

Universal personal AI agent built on [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk-python) + [MCP](https://modelcontextprotocol.io/).

## What Jarvis Does

Jarvis is a personal assistant that manages development workflows, helps with research, and adapts to whatever its owner is working on. It communicates via Telegram (mobile) and CLI (workstation), and uses Claude API for intelligence.

Current focus: PM skills for managing multiple GitHub projects.

## Architecture

- **Runtime**: Claude Agent SDK (same engine as Claude Code)
- **LLM**: Claude API — Haiku (routine), Sonnet (planning/code), Opus (rare)
- **Integrations**: MCP servers (GitHub, Telegram, filesystem, web)
- **Communication**: Telegram Bot + CLI
- **Personality**: defined in `config/SOUL.md`

Jarvis uses a tiered subagent architecture: a read-only planner for analysis and a write-capable coder that only works through branches and PRs. Human reviews all code changes.

## Project Structure

```
├── config/              # Jarvis personality, identity, setup
├── skills/              # Skill definitions (subagent instructions)
│   ├── triage/          # Daily triage across GitHub projects
│   ├── weekly-report/   # Weekly delivery report
│   └── issue-health/    # Issue metadata validation
├── src/                 # Agent SDK application code (future)
├── docs/                # Project documentation
│   ├── PROJECT_PLAN.md  # Strategic plan
│   └── architecture.md  # Technical architecture
└── .github/             # Dev process (CI, PR checks — NOT Jarvis features)
```

## Key Docs

- [Project Plan](docs/PROJECT_PLAN.md) — vision, scope, delivery milestones
- [Architecture](docs/architecture.md) — how it works
- [GitHub Discussions](https://github.com/Osasuwu/personal-AI-agent/discussions) — ideas and brainstorming

## Development

This repo is developed with Claude Code. The `.github/` workflows handle CI and process checks for the repo itself.

```bash
git clone https://github.com/Osasuwu/personal-AI-agent.git
cd personal-AI-agent
```

## License

MIT, see [LICENSE](LICENSE).
