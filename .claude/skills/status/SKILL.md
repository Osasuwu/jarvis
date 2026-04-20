---
name: status
description: "Project dashboard: git state, PRs, issues, CI health, risks, stale/blocked work, goal alerts. Absorbs morning-brief, risk-radar, triage. Use at session start or when needing cross-project awareness."
version: 2.1.0
---

# Status Dashboard

Single command for full project awareness. Replaces morning-brief, risk-radar, and triage.

## Usage

- `/status` — all repos, full dashboard
- `/status <repo>` — single repo focus

## Step 1 — Load repos

Read `config/repos.conf` (one `owner/repo` per line, `#` = comment). This is the single source of truth — no hardcoded repo names.

Local path resolution (portable across 3 devices): `{device.json.repos_path}/{repo-name}` where `repo-name` is the segment after `/`. Example on Main PC: `C:/Users/petrk/GitHub/redrobot`. If the directory doesn't exist (e.g. not cloned on this device), skip local git checks gracefully — GitHub-side checks still run.

## Step 2 — Gather data (parallel)

For each repo, run in parallel:

**Git state** (if local directory exists):
```bash
git -C <path> log --oneline -5
git -C <path> status --short
git -C <path> branch --show-current
```

**GitHub state:**
```bash
gh pr list --repo <R> --state open --json number,title,updatedAt,reviewDecision,isDraft --limit 10
gh issue list --repo <R> --state open --json number,title,labels,updatedAt --limit 20
gh run list --repo <R> --json conclusion,name --limit 10
gh api "repos/<R>/milestones?state=open&per_page=50" --jq '.[] | {number, title, open_issues, closed_issues, due_on}'
```

**Security** (skip silently on 403):
```bash
gh api repos/<R>/dependabot/alerts --jq '[.[] | select(.state=="open")]' 2>/dev/null
```

**Credential expiry** (once, not per repo):
```
credential_check_expiry(days_ahead=14)
```
If results returned, include in output. If no credentials expiring — silent (no noise).

## Step 3 — Analyze

For each repo, compute:

**CI health**: failure rate from last 10 runs. >=50% CRITICAL, 30-49% HIGH, 15-29% MEDIUM.

**Stale issues**: open issues not updated >14 days (skip blocked). Flag count.

**Blocked work**: issues/PRs with `blocked` label or `CHANGES_REQUESTED` review >3 days old.

**Review backlog**: non-draft PRs awaiting review >2 days.

**Repo hygiene** (if local directory exists):
```bash
# Local branches whose remote tracking branch is deleted
git -C <path> branch -vv | grep ': gone]'
# Local branches not merged into master/main
git -C <path> branch --no-merged master 2>/dev/null || git -C <path> branch --no-merged main
# Stashes
git -C <path> stash list
```
Flag: N stale branches (remote gone), M unmerged branches, K stashes.

**Goal alerts** (from session context — goals are already loaded):
- Deadline within 3 days → urgent flag
- P0 goal with no related activity → neglect flag

**Milestone hygiene** (from `gh api .../milestones?state=open`):
- `open_issues == 0 && state == "open"` → **orphan milestone** (work done, milestone never closed). Flag with proposal to close.
- Issue labeled `epic` with "Sprint" in title but `milestone == null` → **orphan sprint** (sprint running without milestone tracking). Flag with proposal to create+attach milestone.
- Milestone `due_on` within 3 days and `open_issues > 0` → **sprint deadline risk**.
- Treat these as actionable items, not just reports — suggest the fix command inline.

## Step 4 — Output

```markdown
# Status — YYYY-MM-DD

## Alerts
- <P0 deadline, neglect warnings, or "Goals on track">
- <Credential expiry warnings, if any>

## <Repo Name>
**Branch:** main | **Clean:** yes/no
**CI:** N/M passed (CRITICAL/HIGH/MEDIUM/ok)
**Recent:** <last 3 commits, one-line>
**PRs:** N open (<titles of notable ones>)
**Issues:** N open, M stale, K blocked
**Security:** N alerts (or clean)
**Hygiene:** N stale branches, M unmerged, K stashes (or clean)

## <Repo 2>
...

## Action items
1. <most urgent thing — fix CI, respond to review, merge ready PR>
2. <next priority>
3. <etc>
```

Keep concise. Skip empty sections. Owner scans in 30 seconds.
## Known unknowns
Top 5 open retrieval gaps (sorted by frequency):
```
[N hits] <query> — last seen <date>
```
(If none: omit section)

These are queries that scored <0.45 semantic similarity — areas Jarvis consistently fails to answer.

---
