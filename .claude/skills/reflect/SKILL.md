---
name: reflect
description: "Learning loop: review recent decisions, check outcomes via GitHub PRs, extract lessons, update memory. Integrates with outcome tracking (Pillar 3)."
---

# Reflect

Reviews recent decisions and task outcomes, checks results (via GitHub PRs or user confirmation), extracts lessons as feedback memories.

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

## Step 2 — Review task outcomes

```
outcome_list(outcome_status="pending", limit=10)
```

For each pending outcome with a `pr_url`:

```bash
gh pr view <number> --json state,mergedAt,closedAt,title --repo <owner/repo>
```

Update resolved outcomes:
```
outcome_update(
  id="<outcome_id>",
  outcome_status="success"/"failure"/"partial",
  outcome_summary="<what happened>",
  pr_merged=true/false,
  lessons="<lesson if any>",
  pattern_tags=["<relevant tags>"]
)
```

## Step 3 — Check GitHub outcomes for decisions

For each decision referencing a PR (`#NNN` in content):

```bash
gh pr view <number> --json state,mergedAt,closedAt,title --repo <owner/repo>
```

Determine `owner/repo` from context or `config/repos.conf`.

Classify: `merged` → accepted, `closed` → rejected, `open` → skip.

## Step 4 — Check non-PR decisions

Ask the user:
> "Decision: **<name>** — <summary>. How did it turn out? (worked / didn't work / ongoing / skip)"

## Step 5 — Update decision memory + load basis

For each resolved decision, upsert with appended `## Outcome`:
```markdown
## Outcome
- **Result:** merged / rejected / worked / failed
- **Date:** YYYY-MM-DD
- **What actually happened:** <one sentence>
- **Decision basis:** <rationale + memories_used from matching decision_made episode, if found>
```

**Load decision basis (#252):** before writing the outcome, query for a `decision_made` episode within ±24h of the decision's `created_at`:

```sql
SELECT id, payload FROM episodes
WHERE kind = 'decision_made'
  AND created_at BETWEEN (<decision_created_at> - interval '24 hours')
                     AND (<decision_created_at> + interval '24 hours')
ORDER BY abs(extract(epoch FROM created_at - <decision_created_at>)) ASC
LIMIT 1;
```

If found, include `payload.rationale` and `payload.memories_used` in the outcome block. When the outcome is a failure, classify using the basis:
- Memories listed in `memories_used` were wrong → supersede them
- `memories_used` was empty AND top-similarity was low at decision time → known-unknown (auto-tracked via #249)
- Basis looks sound but execution failed → not a memory problem, flag as reasoning or execution failure

## Step 5.5 — Calibration check (#251)

After outcomes are verified, check memory calibration:

```
mcp__memory__memory_calibration_summary(project="jarvis")
```

Renders per-type Brier score (mean squared error of `confidence - actual_outcome`). For each type with `n >= 20`, flag:
- `brier > 0.25` AND `avg_predicted > avg_actual` → **overconfident** (confidence in these memories exceeds their track record)
- `brier > 0.25` AND `avg_predicted < avg_actual` → **underconfident**
- `n < 20` → warning (insufficient data, skip calibration-based action)

Surface flagged types in Step 9 output under "Calibration". Poor-calibration types become ideation seeds for `/self-improve` — the root cause is usually a specific pattern (e.g. "my `decision` memories in jarvis are overconfident when they rely on research memories without owner confirmation").

## Step 6 — Extract lessons + patterns

For each resolved decision and outcome, ask: *what's the generalizable lesson?*

**From outcomes** — look for patterns across multiple outcomes:
```
outcome_list(limit=20)
```
- Which task_types succeed most? Which fail?
- Common pattern_tags on successful vs failed outcomes?
- Are certain goal areas consistently under-delivered?

If a pattern is non-obvious, save it:
```
memory_store(
  name="lesson_<slug>", type="feedback",
  project=<same as decision or "global">,
  content="<rule>\n\n**Why:** <what happened>\n**How to apply:** <when this kicks in>",
  source_provenance="skill:reflect"
)
```

Only save if it would change future behavior. Don't save platitudes.

## Step 7 — Hypothesis review

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
  content="claim: <X>\nmetric: <how to verify>\nstatus: testing\nevidence: none yet",
  source_provenance="skill:reflect"
)
```

## Step 8 — Flag stale memories

`memory_recall(type="project", limit=20)` — flag any not updated in 14+ days (except hypotheses).

## Step 9 — Output

```markdown
## Reflect — YYYY-MM-DD

### Outcomes Verified (N)
- [+] <task_type>: <description> — <outcome_status>
- [-] <task_type>: <description> — <outcome_status>, lesson: <one-liner>

### Decisions Resolved (N)
- **<name>**: <outcome> — lesson: <one-liner or "none">

### Patterns Detected
- <pattern description, e.g. "delegation tasks in jarvis repo: 80% success rate">

### Lessons Saved (N)
- <name>: <rule>

### Hypotheses (N testing, N resolved)
- <status emoji> **<slug>**: <claim> — <status>

### Stale Project Memories (N)
- <name> (last updated <date>)

### Calibration (flagged types only)
- **<type>**: Brier <score>, n=<n>, <overconfident|underconfident> (avg_predicted=<p> vs avg_actual=<a>)
```
