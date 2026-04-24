# Autonomous Work Loop — Architecture

> Source of truth for Jarvis Pillar 2: Autonomous Work Loop.
> Created: 2026-04-08. Status: implementing.

## Overview

The autonomous loop makes Jarvis proactive instead of reactive. Instead of waiting for commands, Jarvis perceives events, evaluates them against active goals, decides what to do, acts within safety bounds, and records outcomes for learning.

## Architecture

```
┌─ SCHEDULED PERCEPTION (time-based) ─────────────────────────┐
│                                                               │
│  03:00  nightly-research — gap detection + web research       │
│  08:00  morning-brief    — overnight activity + daily plan    │
│  09:00  risk-radar       — CI, security, stale issues         │
│  14:00  risk-radar       — afternoon check                    │
│  19:00  risk-radar       — evening check                      │
│  Mon    intel            — weekly tech intelligence digest     │
│  Fri    reflect          — weekly outcome review + lessons     │
│                                                               │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│  ORCHESTRATOR (autonomous-loop skill)                        │
│  Runs: daily 09:00 (after morning-brief)                     │
│  Also: manual invocation anytime                             │
│                                                              │
│  1. Load context: goals + brief + risks + research + state   │
│  2. Build action candidates from all perception outputs      │
│  3. Score: goal_alignment × urgency + severity_bonus         │
│  4. Pick top action within autonomy bounds                   │
│  5. Risk-gate: low→auto | medium→auto+record | high→propose │
│  6. Execute & record outcome to memory                       │
│                                                              │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│  REACTIVE LAYER (GitHub Actions — already exists)            │
│                                                              │
│  PR opened    → auto-triage, label, schema check             │
│  PR merged    → linked issue notification                    │
│  Issue opened → schema validation, project sync              │
│  Review done  → auto-apply low-risk Copilot suggestions      │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

## Perceive → Evaluate → Decide → Act → Record

### Perceive (existing skills, now scheduled)

| Skill | What it perceives | Schedule |
|-------|-------------------|----------|
| nightly-research | Knowledge gaps, stalled problems, unacted findings | Daily 03:00 |
| morning-brief | Overnight GitHub activity, PR/issue status, daily plan | Daily 08:00 |
| risk-radar | CI failures, security alerts, stale issues, overdue milestones | 3×/day |
| intel | New Claude/MCP/AI tools and capabilities | Weekly Mon |

### Evaluate (orchestrator Step 2-3)

Action candidates come from perception outputs:
- **Risks** with severity HIGH+ → mitigation actions
- **Goal deadline** < 3 days → escalation
- **Goal progress** stale > 7 days → review and nudge
- **Actionable research** findings not yet acted on
- **Morning-brief** items marked "needs action"

Scoring: `goal_alignment(0-3) × urgency(1-3) + severity_bonus`

- `goal_alignment`: 3 = directly serves P0, 2 = serves P1, 1 = serves P2, 0 = unaligned
- `urgency`: 3 = blocking/deadline, 2 = should be soon, 1 = can wait
- `severity_bonus`: +3 for CRITICAL risk, +2 for HIGH, +1 for MEDIUM

### Decide (orchestrator Step 4-5)

Risk classification (reuses self-improve pattern):

| Risk | Examples | Action |
|------|----------|--------|
| Low | Create issue, fix label, memory cleanup, triage | Auto-execute |
| Medium | Run self-improve, create PR, run triage, goal update | Auto-execute with record |
| High | Architecture change, SOUL.md, memory schema | Save proposal to memory |

### Act (orchestrator Step 6)

Execute the chosen action via:
- Skill invocation (`/triage`, `/self-improve`, `/risk-radar`)
- GitHub CLI (`gh issue create`, `gh pr merge`)
- Memory operations (`memory_store`, `goal_update`)

Safety rules:
- Max 1 PR per autonomous run
- Never touch protected files (`.mcp.json`, `SOUL.md`, `CLAUDE.md`, `mcp-memory/server.py`)
- If no high-priority action found → skip gracefully (don't invent work)

### Record (orchestrator Step 7 + reflect weekly)

Every autonomous action is logged:
```
memory_store(type="project", name="autonomous_action_log", ...)
```

Weekly reflect closes the loop: checks decision outcomes, extracts lessons, updates hypotheses.

## Schedule

| Task | Schedule | Type | Dedup |
|------|----------|------|-------|
| nightly-research | Daily 03:00 | Local scheduled task | `nightly_last_run` date check |
| morning-brief | Daily 08:00 | Local scheduled task | No (idempotent) |
| autonomous-loop | Daily 09:00 | Local scheduled task | `autonomous_loop_last_run` date check |
| risk-radar | 09:00, 14:00, 19:00 | Local scheduled task | `risk_radar_last_run` 4h window |
| intel | Mon 10:00 | Local scheduled task | `intel_last_run` week number |
| reflect | Fri 17:00 | Local scheduled task | `reflect_last_run` week number |

All tasks run locally with full MCP access. Cross-device dedup via Supabase memory.

## Cost

All scheduled tasks use Claude Max subscription limits. No additional API costs.
External services (Supabase) within existing free tier.

## Event-Driven Perception

### Architecture

```
GitHub Event (CI fail, PR approved, security alert)
    │
    ▼
.github/workflows/event-dispatch.yml
    │
    ▼ curl POST → Supabase REST API
    │
    ▼
events table (Supabase)
    │
    ▼
autonomous-loop reads via events_list() at next run
    │
    ▼
events_mark_processed() after handling
```

### Events table (`mcp-memory/schema.sql`)

| Column | Type | Description |
|--------|------|-------------|
| event_type | text | `ci_failure`, `pr_approved`, `ci_success`, `security_alert` |
| severity | text | `critical`, `high`, `medium`, `low`, `info` |
| repo | text | `Osasuwu/jarvis`, `SergazyNarynov/redrobot` |
| payload | jsonb | Event-specific data (PR number, workflow name, URL) |
| processed | boolean | Whether orchestrator has handled it |
| processed_by | text | Who handled it (`autonomous-loop`, `manual`) |

### Event types dispatched

| Event | Trigger | Severity |
|-------|---------|----------|
| `ci_failure` | workflow_run failed on main | `high` |
| `pr_approved` | pull_request_review approved | `info` |
| `ci_success` | workflow_run success on PR | `low` |

### MCP tools (in `mcp-memory/server.py`)

- `events_list(repo?, event_type?, severity?, include_processed?, limit?)` — read events
- `events_mark_processed(event_ids, processed_by, action_taken?)` — mark as handled

### Cross-repo setup

To add event dispatch to another repo (e.g. redrobot):
1. Copy `.github/workflows/event-dispatch.yml`
2. Add `SUPABASE_URL` and `SUPABASE_ANON_KEY` secrets
3. Events land in the same Supabase events table

## Multi-Device Strategy

Scheduled tasks are local (per-device). Three approaches:

1. **Current: Dedup + duplicate** — install tasks on all devices, Supabase dedup prevents double runs
2. **Bootstrap: `/setup-tasks`** — skill that registers all tasks on a new device in one command
3. **Future: Remote triggers** — cloud-based scheduling (requires skills rewrite for execute_sql)

## Files

| File | Purpose |
|------|---------|
| `.claude-userlevel/skills/autonomous-loop/SKILL.md` | Orchestrator skill (manual + scheduled); ships to `~/.claude/skills/autonomous-loop/` |
| `.claude-userlevel/skills/setup-tasks/SKILL.md` | Bootstrap tasks on new device |
| `.github/workflows/event-dispatch.yml` | GitHub Action → Supabase events |
| `mcp-memory/schema.sql` | Events table schema |
| `mcp-memory/server.py` | events_list + events_mark_processed tools |
| `~/.claude/scheduled-tasks/*/SKILL.md` | 6 scheduled task wrappers |
| `.claude-userlevel/skills/status/SKILL.md` | Morning-brief behaviour consolidated here (with goal monitoring) |

## Evolution

Phase 1 (done): Time-based perception + daily orchestrator
Phase 2 (done): Event-driven perception via GitHub Actions + Supabase events queue
Phase 3 (future): Multi-action orchestrator (pick top-N, parallelize low-risk actions)
Phase 4 (future): Remote triggers migration (cloud scheduling, no device dependency)
