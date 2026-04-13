---
name: setup-tasks
description: "Bootstrap all scheduled tasks on a new device. Idempotent — safe to re-run."
version: 1.0.0
---

# Setup Tasks

Bootstrap all 6 scheduled tasks on a new device in one command.

## Usage

`/setup-tasks`

This skill idempotently registers all scheduled tasks. If a task already exists, it's skipped. Safe to re-run on the same device.

## Implementation

1. Call `list_scheduled_tasks` to see what's already registered
2. For each of the 6 required tasks:
   - If exists with matching name → skip ("already registered")
   - If missing → `create_scheduled_task` with cron + prompt
3. Print summary: N created, N skipped (already existed)

## Tasks to Register

| Task ID | Cron | Prompt |
|---------|------|--------|
| nightly-research | `17 7 * * *` | Read `.claude/skills/research/SKILL.md` and run in `--mode=autonomous` |
| morning-brief | `43 7 * * *` | Read and run `.claude/skills/status/SKILL.md` |
| risk-radar | `7 9,14,19 * * *` | Quick risk scan: check CI status, stale issues, security alerts across repos in `config/repos.conf` |
| autonomous-loop | `3 9 * * *` | Read and run `.claude/skills/autonomous-loop/SKILL.md` |
| intel | `12 10 * * 1` | Weekly tech intelligence: search for new Claude Code features, MCP servers, AI agent patterns. Save findings to memory. |
| reflect | `47 16 * * 5` | Weekly reflection: review decisions made this week, check outcomes, extract lessons, update hypotheses. |

## Notes

- All tasks run locally with full MCP access
- Times are in local timezone (not UTC)
- Cron dedup via Supabase memory: scheduled tasks check `*_last_run` markers to prevent duplicate runs across devices
- Prompts reference skill files so updates to skills automatically update scheduled task behavior
