---
name: reflect
description: "Learning loop: review recent decisions, check outcomes via GitHub PRs, extract lessons, update memory"
---

# Reflect

Reviews recent decisions, checks outcomes (via GitHub PRs or user confirmation), extracts lessons as feedback memories.

## When to run

- After a PR is merged or closed
- After an approach failed or succeeded unexpectedly
- Weekly (e.g. as part of `/end`)
- When the user says "that didn't work" or "that was the right call"

## Step 1 — Load recent decisions

```
memory_recall(query="decision approach chosen rejected", type="decision")
```

Focus on last 2 weeks. Skip decisions that already have an `## Outcome` section.

## Step 2 — Check GitHub outcomes

For each decision referencing a PR (`#NNN` in content):

```bash
gh pr view <number> --json state,mergedAt,closedAt,title --repo <owner/repo>
```

Determine `owner/repo` from context or `config/repos.conf`.

Classify: `merged` → accepted, `closed` → rejected, `open` → skip.

## Step 3 — Check non-PR decisions

Ask the user:
> "Decision: **<name>** — <summary>. How did it turn out? (worked / didn't work / ongoing / skip)"

## Step 4 — Update decision memory

For each resolved decision, upsert with appended `## Outcome`:
```markdown
## Outcome
- **Result:** merged / rejected / worked / failed
- **Date:** YYYY-MM-DD
- **What actually happened:** <one sentence>
```

## Step 5 — Extract lessons

For each resolved decision, ask: *what's the generalizable lesson?*

If non-obvious:
```
memory_store(
  name="lesson_<slug>", type="feedback",
  project=<same as decision or "global">,
  content="<rule>\n\n**Why:** <what happened>\n**How to apply:** <when this kicks in>"
)
```

Only save if it would change future behavior. Don't save platitudes.

## Step 6 — Hypothesis review

```
memory_recall(query="hypothesis", type="project", limit=20)
```

For each `hypothesis_<slug>` with `status: testing`:
- Check if enough evidence to resolve
- If resolved: update status to `confirmed`/`rejected`, add evidence
- If open: surface in output

Creating new hypotheses (when user says "I think X might be true"):
```
memory_store(
  name="hypothesis_<slug>", type="project",
  content="claim: <X>\nmetric: <how to verify>\nstatus: testing\nevidence: none yet"
)
```

## Step 7 — Flag stale memories

`memory_recall(type="project", limit=20)` — flag any not updated in 14+ days (except hypotheses).

## Step 8 — Output

```markdown
## Reflect — YYYY-MM-DD

### Resolved (N)
- **<name>**: <outcome> — lesson: <one-liner or "none">

### Lessons saved (N)
- <name>: <rule>

### Hypotheses (N testing, N resolved)
- <status emoji> **<slug>**: <claim> — <status>

### Stale project memories (N)
- <name> (last updated <date>)
```
