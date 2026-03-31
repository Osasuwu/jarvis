---
name: reflect
description: "Learning loop: review recent decisions, check outcomes, extract lessons → update memory"
---

# Reflect

Reviews recent decisions stored in memory, checks their outcomes (via GitHub PRs or user confirmation), and saves lessons as feedback memories. Run after completing a feature, closing a sprint, or when something went unexpectedly.

## When to run

- After a PR is merged or closed
- After an approach failed or succeeded unexpectedly
- Weekly (e.g. as part of `/end` on Fridays)
- Whenever the user says "that didn't work" or "that was the right call"

## Pipeline

### Step 1 — Load recent decisions

```
memory_recall(query="decision approach chosen rejected", type="decision")
```

Focus on decisions from the last 2 weeks (check `Updated` timestamp). Skip decisions that already have an `## Outcome` section.

### Step 2 — Check GitHub outcomes automatically

For each decision that references a PR number (look for `#NNN` or `PR #NNN` in the content):

```bash
gh pr view <number> --json state,mergedAt,closedAt,title,body --repo <owner/repo>
```

Classify outcome:
- `merged` → approach was accepted
- `closed` (not merged) → approach was rejected or abandoned
- `open` → still in progress, skip for now

### Step 3 — Check non-PR decisions

For decisions without a PR reference, ask the user:
> "Decision: **<name>** — <one-line summary>. How did it turn out? (worked / didn't work / still ongoing / skip)"

Skip if the user says "skip" or "ongoing".

### Step 4 — Update the decision memory

For each resolved decision, update it via `memory_store` (upsert) by appending an `## Outcome` section:

```markdown
## Outcome
- **Result:** merged / rejected / worked / failed
- **Date:** YYYY-MM-DD
- **What actually happened:** <one sentence>
```

### Step 5 — Extract lessons

For each resolved decision, ask: *what's the generalizable lesson here?*

If there's a clear lesson (not obvious, something Jarvis should remember for future decisions):

```
memory_store(
  name="lesson_<short_slug>",
  project=<same project as the decision, or "global">,
  type="feedback",
  content="<rule>\n\n**Why:** <what happened>\n**How to apply:** <when this lesson kicks in>"
)
```

Only save if the lesson is non-obvious and would change future behavior. Don't save platitudes ("test your code").

### Step 6 — Output

```
## Reflect — YYYY-MM-DD

### Resolved (N decisions)
- **<decision_name>**: <outcome> — lesson: <one-liner or "none">

### Lessons saved (N)
- <lesson_name>: <rule>

### Still open (N)
- <decision_name>: <why skipped>
```

## Example

Decision: `redrobot_trajectory_multipass` → PR #438 merged → lesson: "multi-pass X→Y→X trajectory is correct for sand leveling, single-pass was wrong assumption" → saved as feedback.
