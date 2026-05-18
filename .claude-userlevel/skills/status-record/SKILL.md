---
name: status-record
description: "Periodic state snapshot to memory: per-repo git/CI/PR/issue/milestone state, written as a structured event under tag `status-snapshot`. Type 1 (cron-triggered). Records only — no decisions, no actions. Owner reads back inline via `memory_recall(query=\"status-snapshot\", type=reference)`."
---

# Status Record

Type 1 skill. Fires on cron, scans tracked repos, writes one structured snapshot per run to memory. Replaces the read+output half of the old `/status` skill — the read side is now `memory_recall` over these snapshots.

**Boundary:** this skill is pure recording. No analysis, no proposals, no actions. Decisions and acting on findings belong to the sandcastle orchestrator (#531) and the owner reading the snapshot.

## Step 1 — Load repos

Read `$JARVIS_HOME/config/repos.conf` (one `owner/repo` per line, `#` = comment). The skill runs under cron with no guaranteed CWD, so resolve via `JARVIS_HOME` (set by the installer per `install-manifest.yaml` `env_vars`). If `JARVIS_HOME` is unset, fall back to scanning the running process's repo root via `git rev-parse --show-toplevel` only if the CWD is already inside the jarvis repo; otherwise exit non-zero with a clear error.

**Empty file is an error**: after parsing, if zero repo entries remain, exit non-zero with `error: repos.conf has no entries`. A zero-repo run would silently store an empty snapshot and trend queries would show false zeroes.

Local path resolution: read `$JARVIS_HOME/config/device.json` for `{repos_path, name}`. Per-repo local path is `{repos_path}/{repo-name}` where `repo-name` is the segment after `/`. If the directory doesn't exist on this device, skip local git checks gracefully — GitHub-side checks still run. If `device.json` is unreadable, omit `device` from the snapshot YAML and continue (don't fail the run).

## Step 2 — Gather data per repo (parallel)

Run in parallel across repos. For each repo, collect:

**Git state** (if local directory exists; `<path>` always quoted to tolerate spaces):

```bash
git -C "<path>" branch --show-current
git -C "<path>" status --short                                 # empty stdout → clean=true (any output, incl. untracked-only, → clean=false)
git -C "<path>" log --oneline -5                               # prose only — surfaced in markdown body, NOT in YAML
git -C "<path>" for-each-ref --format='%(upstream:track)' refs/heads/ | grep -c '\[gone\]'   # stale branches (locale-independent)
git -C "<path>" stash list | wc -l                             # stashes
```

`git log` output is for the human-readable markdown body only — not part of the v1 YAML contract.

**Preflight** (before any external invocations):

```bash
command -v gh >/dev/null 2>&1 || { echo "error: gh not in PATH" >&2; exit 1; }
gh auth status --hostname github.com >/dev/null 2>&1 || { echo "error: gh not authenticated" >&2; exit 1; }
```

Cron strips PATH; an unauthenticated `gh` silently 401s on every call and produces an empty-but-not-erroring snapshot. Fail fast on either.

**GitHub state:**

```bash
gh pr list --repo <R> --state open --json number,title,createdAt,updatedAt,reviewDecision,isDraft --limit 100
gh issue list --repo <R> --state open --json number,title,labels,updatedAt --limit 100
gh run list --repo <R> --json conclusion --limit 10
gh api "repos/<R>/milestones?state=open&per_page=50" --jq '.[] | {number, title, open_issues, closed_issues, due_on}'
gh api "repos/<R>/dependabot/alerts" --jq '[.[] | select(.state=="open")] | length' 2>/dev/null
```

If any list returns exactly its `--limit` size (or `per_page` for `gh api`), set the corresponding `*.truncated: true` field in the YAML and append `partial: <kind> truncated at <limit> for <repo>` to `global.partial`. Limits are sized for current usage (≤100 open issues per repo); a truncation event is itself a signal worth surfacing.

**Global state** (once, not per repo):

```
mcp__memory__credential_check_expiry(days_ahead=14)
```

## Step 3 — Compute derived counts

Per repo, compute counts only (no rates, no severity tagging, no proposals). Each count maps 1:1 to a YAML field in Step 4:

| YAML field | Derivation |
|------------|------------|
| `ci.failure_count` | runs with `conclusion=failure` in last 10 |
| `ci.cancelled_count` | runs with `conclusion=cancelled` in last 10 |
| `prs.open` | total open PRs |
| `prs.draft` | open PRs with `isDraft=true` |
| `prs.review_pending_2d` | non-draft open PRs with no review and `createdAt` >2 days ago (uses `createdAt` not `updatedAt` — the latter resets on every push/comment/label and would mask genuinely-stale review state) |
| `prs.blocked` | open PRs with `blocked` label or `CHANGES_REQUESTED` review |
| `issues.open` | total open issues |
| `issues.stale_14d` | open issues with `updatedAt` >14 days ago, excluding `blocked` label |
| `issues.blocked` | open issues with `blocked` label |

Thresholds (`>14d`, `>2d`) are policy constants. If a future tweak is needed, change here and bump `schema_version`.

Rates (e.g. failure %) are deliberately not stored — the consumer computes them at recall time so policy lives in the reader, not in N days of frozen snapshots.

## Step 4 — Write the snapshot

One memory per run. The `memories` table has a unique constraint on `(project, name)` and `_handle_store` (in `mcp-memory/handlers/memory.py`) upserts via `on_conflict="project,name"` — same-day re-runs cleanly overwrite. No manual dedup needed.

Schema:

- **`name`**: `status_snapshot_<YYYY-MM-DD>` where the date is derived from `generated_at` in **UTC** (not local wall-clock — avoids divergence between name and `generated_at` for non-UTC devices). One per UTC date; re-runs same day overwrite.
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
      blocked: 0
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
  partial: null   # string reason if any data was skipped/rate-limited; null on a complete run
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

If any data was skipped (rate-limit, 404, 403, parse error) append a `partial:` clause so cron monitors can detect:

```
status_snapshot_<YYYY-MM-DD> stored. <N> repos, <M> open PRs, <K> open issues. partial: <reason>
```

That's it. No table, no analysis, no recommendations.

## Failure modes

- `repos.conf` unreadable → log error, exit non-zero. The cron run is logged failed.
- `gh` rate-limit on a single repo → record what was gathered, mark missing fields as `null` in YAML, set `global.partial: <reason>`, **and append `partial: <reason>` to the Step 5 stdout line** so cron monitors can detect.
- `mcp__memory__credential_check_expiry` fails → omit `global.credential_expiry`, set `global.partial: credential_check_expiry unavailable`. Don't fall silent — an expiring credential is exactly the signal this field exists to surface, so absence-of-data deserves a flag.
- `mcp__memory__credential_check_expiry` returns zero results → set `global.credential_expiry: []` (empty list, not omitted) so consumers can skip presence checks.
- `mcp__memory__memory_store` fails → exit non-zero. Don't try alternative storage; the next cron tick will overwrite.
- `dependabot/alerts` returns 403 (non-admin scope) → set `security.dependabot_open: null` (not `0`); document this in the YAML body so consumers don't conflate "no alerts" with "no permission".
- `gh pr list` / `gh issue list` returns 404 (repo gone or renamed) → fall through to the `null`-fields path: emit the repo entry with `prs: null`, `issues: null`, set `global.partial: 404 on owner/repo`.
- `device.json` exists but is malformed JSON → treat identically to "missing": omit the `device` field, continue. Don't fail the whole run on a single broken config file.
- `git -C` exits non-zero on a corrupted local repo → emit the repo entry with `branch: null`, `clean: null`, `hygiene: null`, set `global.partial: corrupted local repo: <name>`. GitHub-side fields still gather.

## Derivations not in the YAML field table

A few fields are computed but their derivation is implicit; spelled out here so consumers don't guess:

- **`clean: bool`** — `true` iff `git status --short` produces empty stdout. Untracked-only state still produces output → `clean=false`. Intentional: an untracked `.lock` file is a hygiene signal, not noise.
- **`branch: string`** — output of `git branch --show-current`; empty on detached-HEAD checkouts.
- **`device: string`** — `device.json.name`, omitted entirely if `device.json` is missing or unparseable.

## Schema versioning

`schema_version: 1` is the current contract. Bump to `2` when:
- Any YAML field is renamed or removed.
- A field's type changes (count → list, scalar → object, etc.).
- A threshold constant changes semantically (e.g. `stale_14d` → `stale_30d`) — same field name with new meaning is a breaking change for trend queries.

Adding new optional fields is **not** a version bump. Consumers reading `schema_version: 1` data must tolerate extra unknown fields.

## Reading these snapshots

Owner / orchestrator reads inline:

```
memory_recall(query="status-snapshot", project="jarvis", type="reference", limit=7)
```

For a specific date: `memory_get(name="status_snapshot_2026-05-10", project="jarvis")`.

For trend analysis (e.g. "milestone 37 burndown over 7 days"): pull last 7 by tag, parse the YAML block.
