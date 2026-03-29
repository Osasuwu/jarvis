---
name: repo-health
description: "Structural health audit per repo: doc consistency, branch hygiene, structure compliance, stale data, actions health"
---

# Repo Health

Structural and hygiene audit across configured repos. Broader than risk-radar (which covers operational/runtime risks) — this covers structure, docs, and cleanliness.

## Usage

`/repo-health` — audit all repos from repos.conf
`/repo-health <owner/repo>` — single repo

## Step 1 — Load repos

Read `config/repos.conf`. Each non-empty, non-comment line = `owner/repo`.
If argument provided, use only that repo.

---

## Step 2 — Run checks per repo

### Check 1: Doc consistency (LLM)

Read the following files if they exist: `README.md`, `CLAUDE.md`, `docs/PROJECT_PLAN.md`.
Compare for contradictions:
- Project name, version, tech stack
- Architecture descriptions (does README match CLAUDE.md?)
- Listed file/directory structure vs what actually exists (`ls` key dirs)
- Any "current status" sections that conflict

Flag: contradictions between docs, claims about files/dirs that don't exist.

### Check 2: Branch hygiene

```bash
# All remote branches with last commit date
gh api repos/<owner/repo>/branches \
  --jq '[.[] | {name:.name, protected:.protected, sha:.commit.sha}]'

# Recently merged PRs (to find branches that should be deleted)
gh pr list --repo <owner/repo> --state merged \
  --json headRefName,mergedAt --limit 30
```

Flag:
- Branches with last commit >30 days ago and no open PR
- Branches whose PR was merged but branch still exists
- More than 10 stale branches total

### Check 3: Structure compliance

Read `CLAUDE.md` for expected file/directory structure.
Check that key paths exist:
```bash
ls <expected dirs from CLAUDE.md>
```

Flag: expected files missing, unexpected large directories (potential cruft from old iterations).

### Check 4: Stale data

```bash
# Issues with no activity >60 days
gh issue list --repo <owner/repo> --state open \
  --json number,title,updatedAt,labels --limit 200

# Overdue milestones
gh api repos/<owner/repo>/milestones \
  --jq '[.[] | select(.state=="open")]'

# Discussions (if enabled) — unresolved >60 days
gh api repos/<owner/repo>/discussions \
  --jq '[.[] | select(.answered_by == null)]' 2>/dev/null || echo "discussions_disabled"
```

Flag:
- Issues with no activity >60 days (not just staleness, but likely forgotten)
- Milestones past due date with <50% completion
- Unresolved Discussions older than 60 days

### Check 5: Actions health

```bash
# List workflow files
gh api repos/<owner/repo>/contents/.github/workflows \
  --jq '[.[].name]' 2>/dev/null || echo "no_workflows"

# Recent run history per workflow
gh run list --repo <owner/repo> \
  --json conclusion,workflowName,createdAt --limit 30
```

For each workflow file, read its content and check:
- Deprecated action versions: `actions/checkout@v1`, `actions/checkout@v2`, `actions/setup-python@v3` etc. → flag, suggest `@v4`
- `continue-on-error: true` at job or step level → flag (hides failures)
- Workflows that haven't run in >30 days (possibly broken trigger)
- Steps that consistently fail but workflow still passes (masked failures)

---

## Step 3 — Format report

```markdown
# Repo Health — YYYY-MM-DD
**Repos audited:** N

---

## <owner/repo>

### Doc Consistency
- ⚠️ README says X, CLAUDE.md says Y — [quote both]
- ✅ No contradictions found

### Branch Hygiene
- 🔴 `feature/old-thing` — merged 45 days ago, branch not deleted
- 🟡 `fix/stale-branch` — no commits in 38 days, no PR
- ✅ N branches, all clean

### Structure Compliance
- 🔴 `src/legacy/` exists — not in CLAUDE.md, possible cruft from old iteration
- ✅ All expected paths present

### Stale Data
- 🟡 #42 "Old idea" — no activity 73 days
- 🟡 Milestone "M3" — past due, 40% complete
- ✅ No unresolved Discussions

### Actions Health
- 🔴 `.github/workflows/ci.yml` — uses `actions/checkout@v2` (deprecated → @v4)
- 🟡 `deploy.yml` — hasn't run in 35 days
- ✅ No masked failures detected
```

Skip clean categories. If all clean: `> <repo>: No issues found.`

## Constraints
- **Read-only**: do NOT modify files, issues, branches, or workflows.
- If `gh api` fails for a check, skip it and note "check skipped: <reason>".
- LLM doc analysis: quote specific conflicting lines, don't paraphrase.
