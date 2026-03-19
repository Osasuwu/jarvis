# Jarvis

AI-assisted development management agent (PM + Tech Lead mode).

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## What Jarvis Does

Jarvis is focused on software delivery coordination:
- decomposes work into epics/tasks,
- enforces issue/PR traceability,
- supports controlled Git workflows,
- keeps project execution visible via triage and weekly reports.

## Current Scope

In scope:
- governance-first repository workflow,
- PM + Tech Lead supervision loop,
- one-human-supervisor operating model.

Out of scope for current MVP:
- self_improvement rollout,
- multi-agent/debate,
- vector DB long-term memory,
- plugin marketplace,
- cloud sync.

## Quick Start

```bash
git clone https://github.com/Osasuwu/personal-AI-agent.git
cd personal-AI-agent
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
copy .env.example .env
pytest -q
```

## Key Docs

- Project plan: [docs/PROJECT_PLAN.md](docs/PROJECT_PLAN.md)
- Roadmap: [docs/roadmap.md](docs/roadmap.md)
- Architecture: [docs/architecture.md](docs/architecture.md)
- Process runbook: [.github/github-process-runbook.md](.github/github-process-runbook.md)
- Copilot instructions: [.github/copilot-instructions.md](.github/copilot-instructions.md)

## Development Workflow

1. Plan in issues and epics.
2. Implement one task per PR.
3. Link PR to issue using `Closes #NNN`.
4. Pass checks and merge to `main`.
5. Run daily triage and weekly review.

## License

MIT, see [LICENSE](LICENSE).
