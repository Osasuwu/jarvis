---
name: status-record
description: "Periodic state snapshot to memory: per-repo git/CI/PR/issue/milestone state, written as a structured event under tag `status-snapshot`. Type 1 (cron-triggered). Records only — no decisions, no actions. Owner reads back inline via `memory_recall(query=\"status-snapshot\", type=reference)`."
---

# Status Record

Type 1 skill. Fires on cron, scans tracked repos, writes one structured snapshot per run to memory. Replaces the read+output half of the old `/status` skill — the read side is now `memory_recall` over these snapshots.

**Boundary:** this skill is pure recording. No analysis, no proposals, no actions. Decisions and acting on findings belong to the sandcastle orchestrator (#531) and the owner reading the snapshot.

## Step 1 — Load repos

Read `config/repos.conf` (one `owner/repo` per line, `#` = comment).

Local path resolution: `{device.json.repos_path}/{repo-name}` where `repo-name` is the segment after `/`. If the directory doesn't exist on this device, skip local git checks gracefully — GitHub-side checks still run.

## Step 2 — Gather data per repo (parallel)

Run in parallel across repos. For each repo, collect:

**Git state** (if local directory exists):

```bash
git -C <path> branch --show-current
git -C <path> status --short
git -C <path> log --oneline -5
git -C <path> branch -vv | grep ': gone]' | wc -l   # stale branches
git -C <path> stash list | wc -l                    # stashes
```

**GitHub state:**

```bash
gh pr list --repo <R> --state open --json number,title,updatedAt,reviewDecision,isDraft --limit 20
gh issue list --repo <R> --state open --json number,title,labels,updatedAt --limit 50
gh run list --repo <R> --json conclusion --limit 10
gh api "repos/<R>/milestones?state=open&per_page=50" --jq '.[] | {number, title, open_issues, closed_issues, due_on}'
gh api "repos/<R>/dependabot/alerts" --jq '[.[] | select(.state=="open")] | length' 2>/dev/null
```

**Global state** (once, not per repo):

```
credential_check_expiry(days_ahead=14)
```

## Step 3 — Compute derived fields

Per repo:

- **`ci_failure_rate`** — proportion of `failure`/`cancelled` in last 10 runs.
- **`stale_issues`** — open issues not updated in >14 days, excluding `blocked` label.
- **`blocked`** — issues/PRs with `blocked` label or `CHANGES_REQUESTED` review.
- **`review_backlog`** — non-draft PRs awaiting review >2 days.

No thresholds, no severity tagging, no proposals. Just numbers.

## Step 4 — Write the snapshot

One memory per run, upserted by name. Schema:

- **`name`**: `status_snapshot_<YYYY-MM-DD>` (one per UTC date — re-runs same day overwrite).
- **`type`**: `reference`
- **`project`**: `jarvis`
- **`tags`**: `["status-snapshot", "auto-generated"]`
- **`source_provenance`**: `skill:status-record`
- **`description`**: `Status snapshot YYYY-MM-DD — N repos, M open PRs, K open issues`

**Content** — YAML front-matter block (machine-parseable) followed by human-readable markdown body. Stable shape:

````markdown
```yaml
schema_version: 1
generated_at: <ISO 8601 UTC>
device: <device.json.name>
repos:
  - name: owner/repo
    branch: main
    clean: true
    ci:
      recent_runs: 10
      failure_count: 0
      cancelled_count: 0
    prs:
      open: 3
      draft: 1
      review_pending_2d: 1
    issues:
      open: 17
      stale_14d: 4
      blocked: 0
    milestones:
      - number: 37
        title: Skill set redesign
        open_issues: 7
        closed_issues: 5
        due_on: null
    hygiene:
      stale_branches: 0
      stashes: 0
    security:
      dependabot_open: 0
global:
  credential_expiry:
    - name: voyageai
      expires_at: 2026-06-15
```

# Status snapshot — YYYY-MM-DD

## Osasuwu/jarvis
…human-readable per-repo paragraph for memory_recall consumers…

## SergazyNarynov/redrobot
…
````

Call:

```
memory_store(
  type="reference",
  name="status_snapshot_<YYYY-MM-DD>",
  project="jarvis",
  tags=["status-snapshot", "auto-generated"],
  source_provenance="skill:status-record",
  content=<the markdown block above>,
  description="<one-liner>"
)
```

## Step 5 — Output

Single line, machine-parseable:

```
status_snapshot_<YYYY-MM-DD> stored. <N> repos, <M> open PRs, <K> open issues.
```

That's it. No table, no analysis, no recommendations.

## Failure modes

- `repos.conf` unreadable → log error, exit non-zero. The cron run is logged failed.
- `gh` rate-limit on a single repo → record what was gathered, mark missing fields as `null` in YAML, note in description (`partial: rate-limit on owner/repo`).
- `credential_check_expiry` fails → omit `global.credential_expiry`, continue.
- `memory_store` fails → exit non-zero. Don't try alternative storage; the next cron tick will overwrite.

## Reading these snapshots

Owner / orchestrator reads inline:

```
memory_recall(query="status-snapshot", project="jarvis", type="reference", limit=7)
```

For a specific date: `memory_get(name="status_snapshot_2026-05-10", project="jarvis")`.

For trend analysis (e.g. "milestone 37 burndown over 7 days"): pull last 7 by tag, parse the YAML block.
