# Jarvis

Universal personal AI agent built on [OpenClaw](https://github.com/openclaw/openclaw).

## What Jarvis Does

Jarvis is a personal assistant that manages development workflows, helps with research, and adapts to whatever its owner is working on. It communicates via Telegram (mobile) and direct UI (workstation), runs locally, and uses free LLM models.

Current focus: PM skills for managing multiple GitHub projects.

## Architecture

- **Platform**: OpenClaw (gateway, messaging, skills framework, dashboard)
- **LLM**: Ollama local (7B models) with free cloud fallback
- **Communication**: Telegram Bot + OpenClaw direct UI
- **Skills**: custom OpenClaw skills in `skills/` directory
- **Personality**: defined in `SOUL.md`

Jarvis does not fork OpenClaw — it extends it with custom skills and configuration.

## Project Structure

```
├── SOUL.md              # Jarvis personality and behavior
├── skills/              # Custom OpenClaw skills
│   ├── triage/          # Daily triage across GitHub projects
│   ├── weekly-report/   # Weekly delivery report
│   └── issue-health/    # Issue metadata validation
├── config/              # OpenClaw configuration
├── docs/                # Project documentation
│   ├── PROJECT_PLAN.md  # Strategic plan
│   ├── roadmap.md       # Delivery phases
│   └── architecture.md  # Technical architecture
└── .github/             # Dev process (CI, PR checks — NOT Jarvis features)
```

## Key Docs

- [Project Plan](docs/PROJECT_PLAN.md) — vision, scope, delivery phases
- [Roadmap](docs/roadmap.md) — what's next
- [Architecture](docs/architecture.md) — how it works
- [Ideas](docs/archive/legacy-design/Ideas.md) — long-term vision

## Development

This repo is developed with Claude Code. The `.github/` workflows handle CI and process checks for the repo itself.

```bash
git clone https://github.com/Osasuwu/personal-AI-agent.git
cd personal-AI-agent
```

## License

MIT, see [LICENSE](LICENSE).
