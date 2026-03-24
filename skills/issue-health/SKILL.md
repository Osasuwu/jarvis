---
name: issue-health
description: "Deep issue metadata audit: labels, types, hierarchy, milestones, epic structure"
---

# Issue Health

Deep structural audit of issue metadata. More thorough than triage. Output: markdown report.

## Step 1 — Fetch open issues

Read `skills/triage/repos.conf` for repo list. Per repo:
```bash
gh issue list --repo <owner/repo> --state open --json number,title,labels,milestone,state,assignees,updatedAt,createdAt,body --limit 1000
```

## Step 2 — Run checks

### 2a. Type label (ERROR)
Every issue needs exactly one type label:
- Jarvis repo (`personal-AI-agent`): `epic`, `task`, `bug`
- Other repos: detect existing type labels and validate against those

Report zero or multiple type labels.

### 2b. Required labels (ERROR)
Non-epic issues must have: `status:*`, `priority:*`, `area:*`. Report each missing prefix.

### 2c. Parent linkage (WARNING)
Non-epic issues should be sub-issues of an epic.
1. List epics: `gh issue list --label epic --json number`
2. Per epic: `gh api repos/{owner}/{repo}/issues/{N}/sub_issues --jq '.[].number'` → build child→parent map
3. Also check body for `Parent: #N` hints. Body hint without sub-issue link = mismatch warning.

Exception: `priority:critical` allowed without parent.

### 2d. Epic structure (WARNING)
Epics should have `## Children` section with `- [ ] #N` checkboxes. Report epics with missing/empty children.

### 2e. Milestone (WARNING)
All issues (including epics) should have a milestone.

### 2f. Assignee (INFO)
`status:in-progress` issues should have an assignee.

## Step 3 — Format

```markdown
# Issue Health Report

**Date:** YYYY-MM-DD
**Repos:** repo1, repo2

| Repo | Issues | Errors | Warnings | Info |
|------|--------|--------|----------|------|
| repo1 | N | N | N | N |

## repo1

### Errors
- 🔴 **#42** Title — Missing `priority:*`. **Action:** add priority label.

### Warnings
- 🟡 **#15** Title — No parent epic. **Action:** link to epic or mark critical.

### Info
- 🔵 **#8** Title — In-progress, no assignee. **Action:** assign or update status.
```

No violations → "> repo: All issues healthy."
Skip empty categories. Process repos sequentially. If `gh` fails, log and continue.
