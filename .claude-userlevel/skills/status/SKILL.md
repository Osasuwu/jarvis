---
name: status
description: "Project dashboard: git state, PRs, issues, CI health, risks, stale/blocked work, goal alerts. Absorbs morning-brief, risk-radar, triage. Use at session start or when needing cross-project awareness."
version: 2.2.0
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
**Known unknowns** (memory/recall gaps — once, not per repo):
```sql
SELECT query, hit_count, last_seen_at FROM known_unknowns WHERE status='open' ORDER BY hit_count DESC, last_seen_at DESC LIMIT 5
```
Execute via `execute_sql` MCP. Cloud sessions won't have local memory client. Include in alerts if results returned.

**Stale flag-only findings** (once, not per repo — #327 escalation rung 2):
```sql
SELECT name, created_at, updated_at, content
FROM memories
WHERE name LIKE 'hygiene_sweep_proposals_%'
  AND archived = false
  AND created_at < now() - interval '1 day'
ORDER BY created_at ASC
LIMIT 10;
```
These are flag-only findings autonomous-loop recorded against foreign-owner repos (e.g. redrobot). Each day without principal action compounds — the `/status` prompt is the daily nudge. Compute `days_unaddressed = today - date(created_at)` per memory and group by repo (name format `hygiene_sweep_proposals_<repo>_<date>`).


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

**Milestone hygiene** (from `gh api .../milestones?state=open` + closed milestones when goals reference them):
- `open_issues == 0 && state == "open"` → **orphan milestone** (work done, milestone never closed). Flag with proposal to close.
- Issue labeled `epic` with "Sprint" in title but `milestone == null` → **orphan sprint** (sprint running without milestone tracking). Flag with proposal to create+attach milestone.
- Milestone `due_on` within 3 days and `open_issues > 0` → **sprint deadline risk**.
- **Goal-vs-milestone divergence** (new): for each active goal from session context, find any linked milestone — linkage via `goal.slug` appearing in milestone title/description, or milestone title referenced in `goal.notes`. Then:
  - `goal.progress >= 100` OR `goal.state == completed`, but linked milestone has `state == "open" && open_issues > 0` → flag **"goal done but milestone still open"**: name the goal, milestone, and open-issue count; propose either (a) close open issues first, then close milestone, or (b) reopen the goal if the remaining issues are still real work. Example from M15 Facehugger Foundation (2026-04-21): goal notes said Sprint 15 complete 2026-04-18, GitHub showed #620-#623 still open.
  - Linked milestone has `state == "closed"`, but `goal.progress < 100 && goal.state != completed` → flag **"stale goal — linked milestone already closed"**: review whether remaining goal work is real or just un-updated progress notes.
- Treat all of the above as actionable items, not just reports — suggest the fix command inline.

## Step 4 — Output

**STALE FLAG section goes at the top of Alerts** — these compound daily and the principal needs to see them first. Group by repo; show oldest first so the most-ignored rises to the top:

```
[STALE FLAG] <repo> — <N>d unaddressed (<M> consecutive flags)
  first flagged: YYYY-MM-DD | latest memory: hygiene_sweep_proposals_<repo>_<date>
  top finding: <brief from content>
```

Omit the section if no stale flag-only findings were returned.

```markdown
# Status — YYYY-MM-DD

## Alerts
- [STALE FLAG] <repo> — <N>d unaddressed (<memory>) — see hygiene findings
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

Keep concise. Skip empty sections. Principal scans in 30 seconds.
