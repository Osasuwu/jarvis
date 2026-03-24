---
name: weekly-report
description: "Weekly delivery report across configured GitHub repos: closed issues, merged PRs, blockers, velocity summary. Trigger: /weekly-report or on schedule."
---

# Weekly Report Skill

> **EXECUTE IMMEDIATELY.** This document contains all instructions you need. Do NOT attempt to read, open, or fetch any files — the instructions are already in your context right now. Start at Step 1 below and follow each step in order. Use ONLY `gh` CLI commands.

Generate a weekly delivery report across all configured GitHub repositories.

## When to Use

Use this skill when:
- The user asks for a weekly report, weekly summary, or delivery update
- Triggered by schedule (cron, typically Friday afternoon)
- The user says `/weekly-report`

## Configuration

Repositories to report on are listed in the shared `repos.conf` file located at `skills/triage/repos.conf` in the Jarvis repo. If the file is missing, ask the user which repos to report on.

## Execution Steps

### Step 1 — Determine time window

The report covers the last 7 days. Calculate the date 7 days ago from now in ISO format (YYYY-MM-DDTHH:MM:SSZ).

### Step 2 — Collect data for each repo

For each repo in the config, run these commands:

#### Closed issues (last 7 days)

```bash
gh issue list --repo <owner/repo> --state closed --json number,title,labels,closedAt,milestone --limit 500
```

Filter results to only include issues where `closedAt` is within the last 7 days.

#### Merged PRs (last 7 days)

```bash
gh pr list --repo <owner/repo> --state merged --json number,title,author,mergedAt --limit 500
```

Filter results to only include PRs where `mergedAt` is within the last 7 days.

#### Current blockers

```bash
gh issue list --repo <owner/repo> --state open --label status:blocked --json number,title
```

#### Open issues count

```bash
# Note: --limit 1000 caps the count; increase if repo may have >1000 open issues.
gh issue list --repo <owner/repo> --state open --json number --limit 1000 --jq 'length'
```

### Step 3 — Format report

Produce a markdown report with this structure:

```markdown
# Weekly Report

**Period:** YYYY-MM-DD — YYYY-MM-DD
**Generated:** YYYY-MM-DD

## Summary

| Repo | Closed | Merged PRs | Blockers | Open |
|------|--------|------------|----------|------|
| repo1 | N | N | N | N |
| repo2 | N | N | N | N |
| **Total** | **N** | **N** | **N** | **N** |

## repo1

### Closed Issues (N)

- [x] #42 Issue title
- [x] #43 Issue title

### Merged PRs (N)

- #10 PR title (@author)
- #11 PR title (@author)

### Blockers (N)

- 🔴 #7 Blocked issue title

## repo2

### Closed Issues (N)

...

## Velocity Notes

- Total throughput: N items closed, N PRs merged
- Active blockers requiring attention: N
```

### Step 4 — Handle edge cases

- If a repo has no activity in the period, include it with zeros in the summary table and note "No activity this week" in its section.
- If `gh` fails for a repo, log the error and continue with other repos.
- If no repos had any activity, report "Quiet week — no closed issues or merged PRs across all repos."

### Step 5 — Deliver

Return the full markdown report to the user. The report must be readable in both Telegram (plain text fallback) and web UI (rendered markdown).

## Important Rules

- Use `gh` CLI for all GitHub API calls.
- Process repos sequentially to avoid rate limits.
- This skill is read-only — no modifications to any repos.
- Keep the report concise: skip empty subsections within repos that had some activity.
- Use the shared `repos.conf` from `skills/triage/repos.conf`.

## Strict Constraints

These rules are mandatory. Violating any of them is a critical failure.

- **No file creation.** Do NOT create, write, or modify any files (scripts, configs, reports, etc.).
- **No git operations.** Do NOT run `git init`, `git add`, `git commit`, or any other git command.
- **No script lookup.** This skill has NO executable scripts (.js, .py, .sh, etc.). All logic is in this document — follow the execution steps above directly.
- **No package installs.** Do NOT run `npm`, `pip`, `apt`, or any package manager.
- **Tool calls only.** The only shell commands you should run are `gh` CLI calls as described in the execution steps.
- If you cannot complete a step, report the error in the output and move on — do NOT attempt workarounds that involve creating files or modifying the environment.
