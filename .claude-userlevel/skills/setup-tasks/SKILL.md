---
name: setup-tasks
description: "Bootstrap all scheduled tasks on a new device. Idempotent — safe to re-run."
version: 1.0.0
---

# Setup Tasks

Bootstrap all 5 scheduled tasks on a new device in one command.

## Usage

`/setup-tasks`

This skill idempotently registers all scheduled tasks. If a task already exists, it's skipped. Safe to re-run on the same device.

## Implementation

1. Call `list_scheduled_tasks` to see what's already registered
2. **Deregister obsolete tasks** before adding new ones:
   - If `morning-brief` exists → call `delete_scheduled_task` (or the MCP equivalent). On success, count it under `removed`. **On failure, do NOT count it as removed** — print `warn: failed to remove morning-brief (<error>) — check manually` instead. A silent-fail would leave both `morning-brief` (07:43) and `status-record` (07:00) firing, defeating the migration.
3. For each of the 5 required tasks:
   - If exists with matching name → skip ("already registered")
   - If missing → `create_scheduled_task` with cron + prompt
4. Print summary: N created, N skipped, N removed.

## Tasks to Register

| Task ID | Cron | Prompt |
|---------|------|--------|
| nightly-research | `17 7 * * *` | Run `/research` — no topic argument; the skill auto-selects discovery mode from arg shape. |
| status-record | `0 7 * * *` | Run `/status-record` — write daily snapshot of repo/CI/PR/issue/milestone state to memory under tag `status-snapshot`. |
| risk-radar | `7 9,14,19 * * *` | Quick risk scan: check CI status, stale issues, security alerts across repos in `config/repos.conf` |
| intel | `12 10 * * 1` | Weekly tech intelligence: search for new Claude Code features, MCP servers, AI agent patterns. Save findings to memory. |
| verify | `47 16 * * 5` | Run `/verify` — verify pending outcomes, detect patterns, save lessons. |

> `autonomous-loop` cron entry was removed 2026-05-26 (decision `a70c4460`). The skill itself is retained as opt-in pre-M44 catch-up baseline but is not bootstrapped on new devices. Existing cron jobs on prior devices must be unregistered manually (`Unregister-ScheduledTask -TaskName "jarvis-autonomous-loop"` on Windows, `crontab -e` on Linux/Mac).

> `status-record` supersedes the old `morning-brief`/`/status` slot — the skill records state only, owner reads inline via `memory_recall(query="status-snapshot")`. Decisions/actions on findings belong to the sandcastle orchestrator (#531).

## Notes

- All tasks run locally with full MCP access
- Times are in local timezone (not UTC)
- Cron dedup via Supabase memory: scheduled tasks check `*_last_run` markers to prevent duplicate runs across devices
- Prompts reference skill files so updates to skills automatically update scheduled task behavior

## Workshop-only: Windows Task Scheduler entries

When invoked on the Workshop PC (`config/device.json` name = `VividFormsPC4Workshop`), `/setup-tasks` also registers the Task Scheduler entries below. Different infra from the five tasks above (those use `create_scheduled_task` MCP; these use `Register-ScheduledTask`).

### Sandcastle AFK loops

| Task name | Schedule | Window end | Slice |
|---|---|---|---|
| `Sandcastle-Jarvis` | Daily 18:00 | 01:00 | [#545](https://github.com/Osasuwu/jarvis/issues/545) |
| `Sandcastle-Redrobot` | Daily 01:00 | 08:00 | [#546](https://github.com/Osasuwu/jarvis/issues/546) |

Non-overlapping by design. (The earlier 22:00/02:00 start times were driven by Ollama VRAM contention; that constraint was relaxed in [#711](https://github.com/Osasuwu/jarvis/issues/711), and the script defaults moved to 18:00/01:00 — these are the source of truth.)

Implementation: invoke the registration script directly (idempotent, replaces existing entry):

```powershell
.\scripts\sandcastle\Register-SandcastleTask.ps1 -Repo jarvis
.\scripts\sandcastle\Register-SandcastleTask.ps1 -Repo redrobot
```

### Quota probe (#635)

| Task name | Schedule | Interval |
|---|---|---|
| `Quota-Probe` | Daily (repeating) | Every 30 min |

Polls `claude -p "/usage"` and broadcasts the `CLAUDE_QUOTA_PRESSURE` repo variable with hysteresis (trip ≥80%, release <70%), and writes a `quota_pressure` row to the `events` table so the #327 telegram escalation hook can notify the owner. See issue #635.

**Prerequisite:** `.sandcastle/.env` must carry `SUPABASE_URL` + `SUPABASE_KEY` (the probe reads it via `-DotEnvPath`, default `.sandcastle/.env`) — without them the `events` write is skipped and a pressure trip never reaches Telegram. The `gh variable` broadcast still works (uses the gh auth, not the .env).

```powershell
.\scripts\sandcastle\Register-SandcastleTask.ps1 -QuotaProbe
```

On non-Workshop devices the script refuses unless `-Force` (dev rehearsal). Full setup + troubleshooting: [`docs/agents/sandcastle-setup.md`](../../../docs/agents/sandcastle-setup.md).

Decisions: `4890aa35` (Workshop = prod), `0c3017c6` (failure modes), `f8e27d53` (escalation), `58670ea5` (model tier), `46830b4e` (80/70 hysteresis, SUPERSEDES `d5b3fdd3` initial 90% gate).
