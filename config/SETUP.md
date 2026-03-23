# Jarvis Setup Guide (Claude Agent SDK + MCP)

## Prerequisites

- Python 3.11+
- GitHub CLI (`gh`) authenticated
- Claude API key with billing enabled
- Telegram bot token (optional for mobile interface)
- Windows 11 (primary), Linux/macOS supported

## 1. Python Environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

## 2. Install Runtime Dependencies

```powershell
pip install claude-agent-sdk
```

If/when MCP transport libraries are required by implementation, add them to project dependencies.

## 3. Configure Secrets

Set user-level environment variables (persistent):

```powershell
[System.Environment]::SetEnvironmentVariable("ANTHROPIC_API_KEY", "sk-ant-...", "User")
[System.Environment]::SetEnvironmentVariable("TELEGRAM_BOT_TOKEN", "123456:ABC-DEF...", "User")
```

Open a new terminal after setting variables.

Verify API key quickly:

```powershell
python -c "import os; print('ANTHROPIC_API_KEY set:', bool(os.getenv('ANTHROPIC_API_KEY')))"
```

## 4. Model Routing Policy

Use these defaults across Jarvis:

- `claude-haiku-4.5`: triage, reports, self-check, simple routing
- `claude-sonnet-4.6`: planning, research, coding tasks
- `claude-opus-4.6`: manual-only for high-risk architectural decisions

Budget target: $10-$30/month.

## 5. MCP Configuration

Create/update `.mcp.json` in repo root to declare required servers.

Minimum set for M1:

- GitHub MCP (issues, PRs, metadata)
- Filesystem MCP (read/write within workspace)
- Telegram bridge (MCP server or direct handler in `src/handlers/telegram.py`)

Keep access narrow: only required tools per subagent.

## 6. Telegram Integration

Create bot via [@BotFather](https://t.me/BotFather), then configure:

- `TELEGRAM_BOT_TOKEN`
- allowlist of your Telegram user ID in bot handler config

Test flow:

1. Send `/triage`
2. Jarvis receives message
3. Command routes to PM subagent
4. Reply returns to Telegram

## 7. Scheduled Runs (Windows)

Use Task Scheduler for recurring jobs:

- Weekdays 09:00: daily triage
- Friday 17:00: weekly report

Runner command example:

```powershell
python src/main.py --command "/triage"
```

Alternative headless mode (when using CLI-based entrypoints):

```powershell
claude -p "/triage" --bare
```

## 8. Safety Baseline

- Planner subagent: read-only tools
- Coder subagent: branch + PR only, never direct push to `main`
- Human review required before merge
- Branch protections enabled in GitHub

## 9. Quick Validation Checklist

- `gh auth status` is OK
- `ANTHROPIC_API_KEY` is set
- `TELEGRAM_BOT_TOKEN` is set (if Telegram enabled)
- `/triage` runs from CLI
- `/triage` runs from Telegram
- Weekly schedule created and tested

## Key Paths

| What | Path |
|---|---|
| Personality | `config/SOUL.md` |
| Setup | `config/SETUP.md` |
| Strategy | `docs/PROJECT_PLAN.md` |
| Architecture | `docs/architecture.md` |
| Skills | `skills/*/SKILL.md` |
| MCP config | `.mcp.json` |
