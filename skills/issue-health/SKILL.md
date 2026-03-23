---
name: issue-health
description: "Validate issue metadata across configured GitHub repos: required labels, type labels, parent linkage, epic structure, milestones. Trigger: /issue-health"
metadata:
  openclaw:
    emoji: "🩺"
    requires:
      bins:
        - gh
---

# Issue Health Skill

> **EXECUTE IMMEDIATELY.** This document contains all instructions you need. Do NOT attempt to read, open, or fetch any files — the instructions are already in your context right now. Start at Step 1 below and follow each step in order. Use ONLY `gh` CLI commands.

Deep validation of issue metadata and structure across all configured GitHub repositories.

## When to Use

Use this skill when:
- The user asks for an issue health check, metadata audit, or board validation
- The user says `/issue-health`
- Before a milestone review or sprint planning

## Difference from Triage

Triage is a lightweight daily scan (stale, blocked, basic metadata). Issue health is a deeper structural audit: type labels, epic completeness, milestone coverage, orphan detection.

## Configuration

Repositories are listed in the shared `repos.conf` file at `skills/triage/repos.conf` in the Jarvis repo.

## Execution Steps

### Step 1 — Fetch all open issues

For each repo, run:

```bash
gh issue list --repo <owner/repo> --state open --json number,title,labels,milestone,state,assignees,updatedAt,createdAt,body --limit 1000
```

### Step 2 — Run checks

#### 2a. Type label check (ERROR)

This check validates type labels per repository:
- For the Jarvis repo (`personal-AI-agent`), valid type labels are: `epic`, `task`, `bug`.
- For other repos, detect which type labels exist (e.g. `child`, `epic`) and validate against those.

Every issue must have exactly one type label from the repo's type-label set. Report issues with zero or multiple type labels. Do not flag issues solely because they use different type-label names than the Jarvis repo.

#### 2b. Required labels check (ERROR)

Non-epic issues must have labels with these prefixes:
- `status:*`
- `priority:*`
- `area:*`

Report each missing prefix separately.

#### 2c. Parent linkage check (WARNING)

Non-epic issues should be linked to a parent epic via GitHub sub-issues.
- Primary check: verify the issue is linked as a GitHub sub-issue of an epic. To do this efficiently, list all open epics once (`gh issue list --repo <owner/repo> --state open --label epic --json number`), then for each epic call `gh api repos/{owner}/{repo}/issues/{epicNumber}/sub_issues --jq '.[].number'` once to build a local child→parent map.
- Supplemental: look for `Parent: #N` or `Parent Epic: #N` in the body. A body hint without a sub-issue link should be flagged as a mismatch.

Exceptions: issues with `priority:critical` are allowed without a parent.

#### 2d. Epic structure check (WARNING)

Epic issues should have:
- A `## Children` or `## Child Issues` section in the body
- Children listed as markdown checkboxes (`- [ ] #N Description`), at least one
- At least one child reference (`#N`) in checkbox form

Report epics with no children section or with a children section that has no checkbox items.

#### 2e. Milestone check (WARNING)

Non-epic issues should have a milestone assigned. Report issues without a milestone.

Epic issues should also have a milestone.

#### 2f. Assignee check (INFO)

Issues with `status:in-progress` should have an assignee. Report unassigned in-progress issues.

### Step 3 — Format report

```markdown
# Issue Health Report

**Date:** YYYY-MM-DD
**Repos checked:** repo1, repo2, ...

| Repo | Issues | Errors | Warnings | Info |
|------|--------|--------|----------|------|
| repo1 | N | N | N | N |
| repo2 | N | N | N | N |

## repo1

### Errors

- 🔴 **#42** Issue title
  - Missing required label: `priority:*`
  - **Action:** Add a priority label.

### Warnings

- 🟡 **#15** Issue title
  - No parent epic linkage.
  - **Action:** Link to parent epic or mark priority:critical.

### Info

- 🔵 **#8** Issue title
  - In-progress but no assignee.
  - **Action:** Assign someone or update status.

## repo2

...
```

If a repo has no violations, show: "> repo2: All issues healthy."

### Step 4 — Deliver

Return the full markdown report. Keep it readable in both Telegram and web UI.

## Important Rules

- Use `gh` CLI for all GitHub API calls.
- This skill is read-only — no modifications.
- Process repos sequentially.
- If `gh` fails for a repo, log and continue.
- Skip empty categories in the report.
- Different repos may use different label conventions — note mismatches but adapt checks to what exists.

## Strict Constraints

These rules are mandatory. Violating any of them is a critical failure.

- **No file creation.** Do NOT create, write, or modify any files (scripts, configs, reports, etc.).
- **No git operations.** Do NOT run `git init`, `git add`, `git commit`, or any other git command.
- **No script lookup.** This skill has NO executable scripts (.js, .py, .sh, etc.). All logic is in this document — follow the execution steps above directly.
- **No package installs.** Do NOT run `npm`, `pip`, `apt`, or any package manager.
- **Tool calls only.** The only shell commands you should run are `gh` CLI calls as described in the execution steps.
- If you cannot complete a step, report the error in the output and move on — do NOT attempt workarounds that involve creating files or modifying the environment.
