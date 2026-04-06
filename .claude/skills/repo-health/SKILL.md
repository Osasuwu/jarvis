---
name: repo-health
description: "Structural health audit per repo: doc consistency, branch hygiene, structure compliance, stale data, actions health"
---

# Repo Health

Structural and hygiene audit across configured repos. Broader than risk-radar (operational risks) — this covers structure, docs, and cleanliness.

## Usage

- `/repo-health` — audit all repos from `config/repos.conf`
- `/repo-health <owner/repo>` — single repo

## Step 0 — Load repos

Read `config/repos.conf`. Each non-empty, non-comment line = `owner/repo`.

## Checks per repo

### Check 1: Doc consistency (LLM)

Read `README.md`, `CLAUDE.md`, `docs/PROJECT_PLAN.md` if they exist. Compare for:
- Contradictions in project name, stack, architecture
- Claims about files/dirs that don't exist
- Conflicting "current status" sections

### Check 2: Branch hygiene

```bash
gh api repos/<owner/repo>/branches --jq '[.[] | {name:.name, protected:.protected}]'
gh pr list --repo <owner/repo> --state merged --json headRefName,mergedAt --limit 30
```

Flag: branches >30 days old with no open PR, merged PR branches not deleted, >10 stale branches.

### Check 3: Structure compliance

Read `CLAUDE.md` for expected structure. Check key paths exist.
Flag: missing expected files, unexpected large directories.

### Check 4: Stale data

```bash
gh issue list --repo <owner/repo> --state open --json number,title,updatedAt --limit 200
gh api repos/<owner/repo>/milestones --jq '[.[] | select(.state=="open")]'
```

Flag: issues >60 days no activity, overdue milestones <50% complete.

### Check 5: Actions health

```bash
gh api repos/<owner/repo>/contents/.github/workflows --jq '[.[].name]' 2>/dev/null
gh run list --repo <owner/repo> --json conclusion,workflowName,createdAt --limit 30
```

Flag: deprecated action versions, `continue-on-error: true`, workflows not run in >30 days.

## Output

```markdown
# Repo Health — YYYY-MM-DD

## <owner/repo>
### Doc Consistency — OK / issues
### Branch Hygiene — N stale
### Structure — OK / missing files
### Stale Data — N stale issues
### Actions — OK / deprecated
```

Skip clean categories. Read-only — do NOT modify anything.
