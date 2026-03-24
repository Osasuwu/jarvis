---
name: weekly-report
description: "Weekly delivery report: closed issues, merged PRs, blockers, velocity"
---

# Weekly Report

Read-only delivery report for the last 7 days. Output: markdown report.

## Step 1 — Load repos

Read `skills/triage/repos.conf`. Each non-empty, non-comment line = `owner/repo`.

## Step 2 — Collect per repo

Calculate ISO date 7 days ago.

```bash
# Closed issues
gh issue list --repo <owner/repo> --state closed --json number,title,labels,closedAt,milestone --limit 500
# Filter: closedAt within last 7 days

# Merged PRs
gh pr list --repo <owner/repo> --state merged --json number,title,author,mergedAt --limit 500
# Filter: mergedAt within last 7 days

# Blockers
gh issue list --repo <owner/repo> --state open --label status:blocked --json number,title

# Open count
gh issue list --repo <owner/repo> --state open --json number --limit 1000 --jq 'length'
```

## Step 3 — Format

```markdown
# Weekly Report

**Period:** YYYY-MM-DD — YYYY-MM-DD

| Repo | Closed | PRs | Blockers | Open |
|------|--------|-----|----------|------|
| repo1 | N | N | N | N |
| **Total** | **N** | **N** | **N** | **N** |

## repo1

### Closed Issues (N)
- [x] #42 Title

### Merged PRs (N)
- #10 PR title (@author)

### Blockers (N)
- 🔴 #7 Title

## Velocity
- Throughput: N closed, N PRs merged
- Active blockers: N
```

No activity → "No activity this week." for that repo.
Process repos sequentially. If `gh` fails, log error and continue.

## Constraints
- **Read-only**: do NOT modify repos, create files, run git commands, or install packages.
- Only run `gh` CLI commands as described above.
