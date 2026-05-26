---
name: setup-tasks
description: "Bootstrap all scheduled tasks on a new device. Idempotent — safe to re-run."
version: 2.0.0
---

# Setup Tasks

Bootstrap Jarvis's scheduled tasks on a device. Idempotent.

## Routine host policy (2026-05-26)

**Workshop PC is the sole routine host.** All `create_scheduled_task` MCP routines and Workshop-only Task Scheduler entries register **only** when `config/device.json` reports `name == "VividFormsPC4Workshop"`. On any other device the skill refuses with a message pointing here.

Rationale: removes per-device cron-dedup complexity, eliminates double-dispatch risk (two devices firing the same job seconds apart), centralises observability (one log surface), and aligns routines with the 24/7 sandcastle/orchestrator infra already living on Workshop. SPOF tradeoff accepted — Workshop offline = routines pause until restart; status-record gap on next SessionStart is the canary.

Decision: `1b7ff8d1-bbca-4207-a7e4-4c1edddef67e`.

## Usage

`/setup-tasks`

## Implementation

1. Read `config/device.json`. If `name != "VividFormsPC4Workshop"` → print:
   ```
   refused: routines are Workshop-only as of 2026-05-26.
   To clean up legacy entries on this device, run:
     /setup-tasks --cleanup
   ```
   and exit. The `--cleanup` flag (separate path below) deletes any MCP scheduled tasks this skill previously registered here.
2. On Workshop: call `list_scheduled_tasks` to see what's already registered.
3. **Deregister obsolete tasks** before adding new ones. For each entry in the *Obsolete* table below:
   - If present → call `delete_scheduled_task`. On success count under `removed`. On failure print `warn: failed to remove <taskId> (<error>) — check manually` and DO NOT count it.
4. For each task in the *Routines (MCP)* table:
   - If exists with matching name → skip ("already registered").
   - If missing → `create_scheduled_task` with cron + prompt.
5. Run the Workshop Task Scheduler registration commands in the *Workshop Task Scheduler* section below (each script is itself idempotent).
6. Print summary: `N created, N skipped, N removed, N task-scheduler-entries`.

### `--cleanup` mode (non-Workshop devices)

Pure removal. For each task in *Routines (MCP)* + *Obsolete*:
- If present → `delete_scheduled_task`.
Print summary: `N removed`.

Use after migrating off a device that previously hosted these routines.

## Routines (MCP) — Workshop-only

Registered via `create_scheduled_task` MCP. All run on Workshop with full local MCP access (Supabase, memory, ccd_session, scheduled-tasks).

| Task ID | Cron | Prompt |
|---|---|---|
| status-record | `0 7 * * *` | Run `/status-record` — write daily snapshot of repo/CI/PR/issue/milestone state to memory under tag `status-snapshot`. |
| intel | `12 10 * * 1` | Weekly tech intelligence: search for new Claude Code features, MCP servers, AI agent patterns. Save findings to memory. |
| verify | `47 16 * * 5` | Run `/verify` — verify pending outcomes, detect patterns, save lessons. |
| memory-consolidation-weekly | `1 10 * * 0` | Run `/memory-consolidation-weekly` — weekly A-MEM Phase 5.1d-α consolidation apply (`scripts/consolidation-run.py`). |
| memory-evolve-weekly | `0 11 * * 0` | Run `/memory-evolve-weekly` — weekly A-MEM Phase 5.2-γ neighbor-evolve apply (`scripts/evolve-run.py`, one hour after consolidation). |

## Obsolete (deregister)

| Task ID | Why removed |
|---|---|
| morning-brief | superseded by `status-record` (2026-04 migration). |
| autonomous-loop | superseded 2026-05-26 by reactive-core M44 (`wake_driver` + `task_queue`); cron pacing replaced by event-trigger (decision `a70c4460`). Skill file retained as pre-M44 catch-up baseline; cron entry removed. |
| nightly-research | removed 2026-05-26 — `/research` is a user-driven flow, scheduled blind discovery produced low-value noise. |
| risk-radar | removed 2026-05-26 — overlapped with `status-record` + sandcastle-orchestrator gating; signal-to-noise was poor. |

## Workshop Task Scheduler entries

Different infra from the MCP routines above (these use `Register-ScheduledTask` via PowerShell). All also Workshop-only.

### Sandcastle AFK loops

| Task name | Schedule | Window end | Slice |
|---|---|---|---|
| `Sandcastle-Jarvis` | Daily 18:00 | 01:00 | [#545](https://github.com/Osasuwu/jarvis/issues/545) |
| `Sandcastle-Redrobot` | Daily 01:00 | 08:00 | [#546](https://github.com/Osasuwu/jarvis/issues/546) |

Non-overlapping by design (#711 relaxed the earlier Ollama-VRAM constraint).

```powershell
.\scripts\sandcastle\Register-SandcastleTask.ps1 -Repo jarvis
.\scripts\sandcastle\Register-SandcastleTask.ps1 -Repo redrobot
```

### Quota probe (#635)

| Task name | Schedule | Interval |
|---|---|---|
| `Quota-Probe` | Daily (repeating) | Every 30 min |

Polls `claude -p "/usage"`, broadcasts `CLAUDE_QUOTA_PRESSURE` repo variable with hysteresis (trip ≥80%, release <70%), writes `quota_pressure` events for telegram escalation (#327).

**Prerequisite:** `.sandcastle/.env` carries `SUPABASE_URL` + `SUPABASE_KEY` (read via `-DotEnvPath`, default `.sandcastle/.env`).

```powershell
.\scripts\sandcastle\Register-SandcastleTask.ps1 -QuotaProbe
```

### Orchestrator watcher daemon (M41/#639)

| Task name | Schedule | Notes |
|---|---|---|
| `Orchestrator-Watcher` | At Workshop startup, restart on failure | Continuous poll (45s) of `events` table for `review_negative`; dispatches `claude -p "/rework <N>"` on hit. Gated by quota probe cache. |

**Registration script:** **NOT YET WRITTEN** — tracked as a follow-up to the routine-cleanup migration. Manual registration in the interim:

```powershell
$action = New-ScheduledTaskAction -Execute "python" -Argument "C:\Users\<user>\GitHub\jarvis\scripts\orchestrator\watcher.py" -WorkingDirectory "C:\Users\<user>\GitHub\jarvis"
$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 5)
Register-ScheduledTask -TaskName "Orchestrator-Watcher" -Action $action -Trigger $trigger -Settings $settings -RunLevel Highest
```

Prerequisites for the watcher to actually dispatch:
- `SUPABASE_URL` + `SUPABASE_KEY` in the watcher's environment
- `~/.jarvis/orchestrator/usage.json` present and fresh (written by Quota-Probe)
- `/rework` skill installed (`install.ps1 -Apply`)

## Notes

- All routine times are local timezone (Asia/Almaty on Workshop).
- Prompts reference skill files; skill updates take effect on next run.
- Source of truth for this file: `.claude-userlevel/skills/setup-tasks/SKILL.md`. Live mirror at `~/.claude/skills/setup-tasks/SKILL.md` is propagated by `install.ps1 -Apply`.

Decisions: `4890aa35` (Workshop = prod), `0c3017c6` (failure modes), `f8e27d53` (escalation), `58670ea5` (model tier), `46830b4e` (80/70 hysteresis), `a70c4460` (autonomous-loop superseded), `1b7ff8d1` (Workshop = sole routine host).
