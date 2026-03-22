---
name: issue_health
description: "Validate issue metadata across configured GitHub repos: required labels, type labels, parent linkage, epic structure, milestones. Trigger: /issue-health"
metadata:
  {
    "openclaw":
      {
        "emoji": "🩺",
        "requires": { "bins": ["gh"] },
      },
  }
---

# Issue Health Skill

Deep validation of issue metadata and structure across all configured GitHub repositories.

## When to Use

Use this skill when:
- The user asks for an issue health check, metadata audit, or board validation
- The user says `/issue-health`
- Before a milestone review or sprint planning

## Difference from Triage

Triage is a lightweight daily scan (stale, blocked, basic metadata). Issue health is a deeper structural audit: type labels, epic completeness, milestone coverage, orphan detection.

## Configuration

Repositories are listed in `repos.conf` in the `triage` skill directory (shared config).

## Execution Steps

### Step 1 — Fetch all open issues

For each repo, run:

```bash
gh issue list --repo <owner/repo> --state open --json number,title,labels,milestone,state,assignees,updatedAt,createdAt,body --limit 200
```

### Step 2 — Run checks

#### 2a. Type label check (ERROR)

Every issue must have exactly one type label: `epic`, `task`, or `bug`.
If the repo uses a different type convention (e.g. `child` instead of `task`), note it but do not flag as error.

Report issues with zero or multiple type labels.

#### 2b. Required labels check (ERROR)

Non-epic issues must have labels with these prefixes:
- `status:*`
- `priority:*`
- `area:*`

Report each missing prefix separately.

#### 2c. Parent linkage check (WARNING)

Non-epic issues should be linked to a parent epic. Check for:
- `Parent: #N` or `Parent Epic: #N` in the issue body
- Or presence as a GitHub sub-issue

Exceptions: issues with `priority:critical` are allowed without a parent.

#### 2d. Epic structure check (WARNING)

Epic issues should have:
- A `## Children` or `## Child Issues` section in the body
- At least one child reference (`#N`)

Report epics with no children section or empty children list.

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

- :red_circle: **#42** Issue title
  - Missing required label: `priority:*`
  - **Action:** Add a priority label.

### Warnings

- :yellow_circle: **#15** Issue title
  - No parent epic linkage.
  - **Action:** Link to parent epic or mark priority:critical.

### Info

- :large_blue_circle: **#8** Issue title
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
