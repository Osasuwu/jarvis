---
name: triage
description: "Daily triage: stale issues, missing metadata, blocked items, status inconsistencies"
---

# Daily Triage

Read-only health check across configured repos. Output: markdown report.

## Step 1 — Load repos

Read `skills/triage/repos.conf`. Each non-empty, non-comment line = `owner/repo`.

## Step 2 — Fetch open issues

Per repo:
```bash
gh issue list --repo <owner/repo> --state open --json number,title,labels,milestone,state,assignees,updatedAt,createdAt,body --limit 1000
```

## Step 3 — Run checks

### 3a. Metadata (ERROR)
Non-epic issues must have labels with prefixes: `status:*`, `priority:*`, `area:*`. Report each missing prefix.

### 3b. Hierarchy (WARNING)
Non-epic issues should link to a parent epic. Check:
1. `Parent: #N` or `Parent Epic: #N` in body
2. If not found — list epics once (`gh issue list --label epic --json number`), then per epic `gh api repos/{owner}/{repo}/issues/{N}/sub_issues --jq '.[].number'` to build child→parent map.

Exception: `priority:critical` issues are allowed without parent.

### 3c. Blocked (ERROR)
Issues with `status:blocked` — report each, recommend review/resolve/reprioritize.

### 3d. Staleness (WARNING)
Non-epic issues not updated 14+ days (skip `status:blocked`). Show days since update.

## Step 4 — Format

```markdown
# Daily Triage Report

**Date:** YYYY-MM-DD
**Repos:** repo1, repo2

| Metric | Value |
|--------|-------|
| Open issues | N |
| Blocked | N |
| Errors | N |
| Warnings | N |

## Metadata
- 🔴 **#42** Title — Missing `status:*` label. **Action:** add label.

## Blocked
- 🔴 **#7** Title — Blocked. **Action:** review blockers.

## Staleness
- 🟡 **#23** Title — No updates 21 days. **Action:** update or close.
```

Skip categories with zero violations. If all clean: "> No violations — board is healthy."
Process repos sequentially. If `gh` fails for a repo, log error and continue.
