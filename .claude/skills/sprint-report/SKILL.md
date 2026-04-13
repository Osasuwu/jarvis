---
name: sprint-report
description: "Sprint report + GitHub release for redrobot. Collects closed issues, merged PRs, benchmarks. Creates pre-release and draft report for Sergazy."
version: 1.0.0
---

# Sprint Report

Generates a sprint report and GitHub release for redrobot at the end of each sprint.

## Usage

- `/sprint-report` — current sprint
- `/sprint-report N` — specific sprint number

## Step 0 — Determine sprint

If sprint number provided, use it. Otherwise, determine current sprint:
1. Check redrobot CLAUDE.md "Текущий контекст" section for active sprint info
2. If not found, ask owner

Record: sprint name, date range, sprint goals.

## Step 1 — Gather data (parallel)

All commands target `SergazyNarynov/redrobot`.

**Closed issues this sprint:**
```bash
gh issue list --repo SergazyNarynov/redrobot --state closed --json number,title,labels,closedAt --limit 50
```
Filter by sprint date range.

**Merged PRs this sprint:**
```bash
gh pr list --repo SergazyNarynov/redrobot --state merged --json number,title,mergedAt,body --limit 30
```
Filter by sprint date range.

**Test results** (from local repo if available):
```bash
cd /c/Users/petrk/GitHub/redrobot && python -m pytest tests/ --tb=no -q 2>&1 | tail -5
```

**Benchmark results** (if available in recent commits/PRs):
Search PR bodies and commit messages for benchmark metrics (mean_dev, tolerance %, pass count).

**Memory context:**
```
memory_recall(query="sprint redrobot", project="redrobot", limit=5)
```

## Step 2 — Compile release notes

Format:

```markdown
## What's New

### Features
- <new capabilities added>

### Improvements
- <enhancements to existing features>

### Bug Fixes
- <bugs fixed>

### Infrastructure
- <CI, tooling, refactoring changes>

## Metrics
- Tests: N/N passing
- Benchmark: <key metrics if available>

## Issues Closed
- #N — title
- #N — title

## PRs Merged
- #N — title
- #N — title

## Known Issues
- <open blockers, regressions, limitations>
```

## Step 3 — Create GitHub release

```bash
# Determine next version tag
gh release list --repo SergazyNarynov/redrobot --limit 5
# If no prior releases, start with v0.1.0
# Otherwise increment patch (or minor if significant features)

git -C /c/Users/petrk/GitHub/redrobot tag <version>
git -C /c/Users/petrk/GitHub/redrobot push origin <version>

gh release create <version> \
  --repo SergazyNarynov/redrobot \
  --title "Sprint N — <sprint name>" \
  --notes "$(cat <<'EOF'
<release notes from Step 2>
EOF
)" \
  --prerelease
```

Use `--prerelease` flag — this is a research project, no stable releases yet.

## Step 4 — Draft report for Sergazy

Generate a concise summary in Russian, focused on what matters to a project lead:

```markdown
## Отчёт по спринту N — <даты>

### Что сделано
- <2-5 ключевых результатов, понятным языком, не техническим>

### Метрики
- Тесты: N/N
- <бенчмарки если есть>

### Проблемы и риски
- <блокеры, что не успели, что вызвало трудности>

### План на следующий спринт
- <предложения, основанные на бэклоге и приоритетах>
```

Output this to the user for review and adjustment before sending.

## Step 5 — Save to memory

```
memory_store(
  type="project",
  name="sprint_N_report_redrobot",
  project="redrobot",
  description="Sprint N results: <one-line summary>",
  tags=["sprint", "report", "release"],
  content=<sprint summary with key metrics and decisions>
)
```

## Rules

- Don't guess sprint boundaries — use dates from CLAUDE.md or ask
- Pre-release only — no stable releases without owner's explicit decision
- Report draft is for owner to review — don't send anywhere automatically
- If benchmarks are unavailable, note it and skip — don't block the release
