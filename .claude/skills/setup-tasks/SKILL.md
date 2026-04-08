---
name: setup-tasks
description: "Bootstrap scheduled tasks on a new device. Registers all autonomous tasks with correct cron schedules. Run once per device."
---

# Setup Tasks

Registers all Jarvis scheduled tasks on the current device. Run this once on each new device to enable autonomous operation.

**All tasks have cross-device dedup** — running the same task on multiple devices won't cause duplicates. Each task checks Supabase before executing.

## Step 1 — Check current tasks

```
mcp__scheduled-tasks__list_scheduled_tasks()
```

List existing tasks. Compare against the manifest below.

## Step 2 — Register missing tasks

For each task NOT already registered, call `create_scheduled_task`. Skip tasks that already exist.

### Task manifest

| taskId | cronExpression | description |
|--------|---------------|-------------|
| `nightly-research` | `17 7 * * *` | Morning research: identify knowledge gaps, research 3 topics, save findings |
| `morning-brief` | `43 7 * * *` | Morning brief: check overnight GitHub activity, save daily plan |
| `risk-radar` | `7 9,14,19 * * *` | Risk scan 3x/day: CI health, security, stale issues, overdue milestones |
| `autonomous-loop` | `3 9 * * *` | Daily orchestrator: load perception, score actions, execute within safety bounds |
| `intel` | `12 10 * * 1` | Weekly Monday: tech intelligence digest |
| `reflect` | `47 16 * * 5` | Weekly Friday: review decisions, check outcomes, extract lessons |

### Task prompts

Prompts are stored in `~/.claude/scheduled-tasks/{taskId}/SKILL.md`. When `create_scheduled_task` is called, it creates these files automatically.

For each task, use the prompt from the corresponding file in the repo's `~/.claude/scheduled-tasks/` directory. If the file doesn't exist locally, use this fallback:

```
Read and follow .claude/skills/{taskId}/SKILL.md
DO NOT output interactively. Save results to memory and exit.
```

## Step 3 — Verify

```
mcp__scheduled-tasks__list_scheduled_tasks()
```

Confirm all 6 tasks are registered and enabled. Output summary.

## Output

```markdown
## Setup Tasks — Complete

### Registered (N new, N existing)
| Task | Schedule | Status |
|------|----------|--------|
| nightly-research | 07:17 daily | already existed |
| morning-brief | 07:43 daily | already existed |
| risk-radar | 09:07, 14:07, 19:07 daily | NEW |
| autonomous-loop | 09:03 daily | NEW |
| intel | Mon 10:12 | NEW |
| reflect | Fri 16:47 | NEW |

All tasks have cross-device dedup via Supabase. Safe to run on multiple devices.
```
