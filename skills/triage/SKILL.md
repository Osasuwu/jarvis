---
name: daily_triage
description: "Daily triage across configured GitHub repos: finds stale issues, missing metadata, blocked items, and status inconsistencies. Produces a markdown summary. Trigger: /triage or on schedule."
metadata:
  openclaw:
    emoji: "📋"
    requires:
      bins:
        - gh
---

# Daily Triage Skill

> **EXECUTE IMMEDIATELY.** This document contains all instructions you need. Do NOT attempt to read, open, or fetch any files (SKILL.md, triage.js, etc.) — the instructions are already in your context right now. Start at Step 1 below and follow each step in order. Use ONLY `gh` CLI commands.

Run a health check across all configured GitHub repositories. Report issues that need attention.

## When to Use

Use this skill when:
- The user asks for a triage, daily report, or board health check
- Triggered by schedule (cron)
- The user says `/triage`

## Configuration

Repositories to check are listed in `repos.conf` (one `owner/repo` per line) in this skill's directory. If the file is missing, ask the user which repos to check.

## Execution Steps

### Step 1 — Load repo list

Read the file `repos.conf` from this skill's directory. Each non-empty, non-comment line is an `owner/repo` to check.

### Step 2 — Fetch open issues for each repo

For each repo, run:

```bash
gh issue list --repo <owner/repo> --state open --json number,title,labels,milestone,state,assignees,updatedAt,createdAt,body --limit 1000
```

### Step 3 — Run checks

For every open issue, run these checks:

#### 3a. Metadata check (ERROR severity)

Non-epic issues must have all three label prefixes:
- `status:*`
- `priority:*`
- `area:*`

An issue is an epic if it has the `epic` label. Epics are exempt from this check.

Report each missing prefix as a separate violation.

#### 3b. Hierarchy check (WARNING severity)

Non-epic issues should be linked to a parent epic. Use this approach:

1. Look for `Parent: #N` or `Parent Epic: #N` in the issue body as a quick signal.
2. If body has no parent hint, check sub-issues: first list all open epics once (`gh issue list --repo <owner/repo> --state open --label epic --json number`), then for each epic call `gh api repos/{owner}/{repo}/issues/{epicNumber}/sub_issues --jq '.[].number'` once to build a local map of child→parent. Do NOT call sub_issues API per child issue.

Exception: issues with `priority:critical` label are allowed without a parent (standalone hotfixes).

#### 3c. Blocked check (ERROR severity)

Issues with the `status:blocked` label require supervisor attention. Report each one with a recommendation to review blockers, resolve, or re-prioritize.

#### 3d. Staleness check (WARNING severity)

Non-epic issues that have not been updated for 14+ days (based on `updatedAt` field) are potentially stale.

Skip issues that are already `status:blocked` (they are reported by the blocked check).

Calculate days since last update and include in the message.

### Step 4 — Format report

Produce a markdown report with this structure:

```markdown
# Daily Triage Report

**Date:** YYYY-MM-DD
**Repos checked:** repo1, repo2, ...

| Metric | Value |
|--------|-------|
| Open issues | N |
| Blocked | N |
| Errors | N |
| Warnings | N |

> No violations — board is healthy.
```

If there are violations, group them by category:

```markdown
## Metadata

- 🔴 **#42** Issue title
  - Missing required label with prefix 'status:'
  - **Action:** Add a 'status:*' label to #42.

## Hierarchy

- 🟡 **#15** Issue title
  - Task has no parent epic linkage.
  - **Action:** Link #15 to a parent epic via GitHub sub-issues, or mark priority:critical if standalone hotfix.

## Blocked

- 🔴 **#7** Issue title
  - Issue is blocked — requires supervisor attention.
  - **Action:** Review #7 blockers, resolve or re-prioritize.

## Staleness

- 🟡 **#23** Issue title
  - No updates for 21 days.
  - **Action:** Review #23: update status, close if done, or mark blocked with a note.
```

### Step 5 — Deliver

Return the full markdown report to the user. The report must be readable in both Telegram (plain text fallback) and web UI (rendered markdown).

## Important Rules

- Use `gh` CLI for all GitHub API calls — no raw HTTP or tokens needed.
- Process repos sequentially to avoid rate limits.
- If `gh` fails for a repo, log the error and continue with other repos.
- Do NOT modify any issues — this skill is read-only.
- Keep the report concise: skip categories with zero violations.

## Strict Constraints

These rules are mandatory. Violating any of them is a critical failure.

- **No file creation.** Do NOT create, write, or modify any files (scripts, configs, reports, etc.).
- **No git operations.** Do NOT run `git init`, `git add`, `git commit`, or any other git command.
- **No script lookup.** This skill has NO executable scripts (.js, .py, .sh, etc.). All logic is in this document — follow the execution steps above directly.
- **No package installs.** Do NOT run `npm`, `pip`, `apt`, or any package manager.
- **Tool calls only.** The only shell commands you should run are `gh` CLI calls as described in the execution steps.
- If you cannot complete a step, report the error in the output and move on — do NOT attempt workarounds that involve creating files or modifying the environment.
