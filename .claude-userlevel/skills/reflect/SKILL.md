---
name: reflect
description: "Learning loop: review recent decisions, check outcomes via GitHub PRs, extract lessons, update memory. Integrates with the Outcome Tracking & Learning pillar."
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

## Step 5.25 — Recall audit aggregate (#333)

Roll the per-session recall audit across the last ~20 sessions to surface cross-session patterns (one session's gap is noise; a persistent trend is a fixable process leak):

```bash
python scripts/recall-audit.py --project jarvis --limit 20 --aggregate
```

Output is a single JSON dict with `sessions`, `record_decision_calls`, `flags_total`, `flags_by_kind`, and `empty_memories_used_pct`.

Interpretation rules:

- `empty_memories_used_pct >= 30%` over 20 sessions → **process leak**, not noise. Save a `feedback` memory naming the pattern (e.g. "record_decision calls drop memories_used when args are passed via <tool invocation style>"). Reference the audit output in the memory content.
- `flags_by_kind.decision_text_no_recall > 10` over 20 sessions → recall-before-deciding habit is not stable. Consider: is this a rule we already have? If yes, why is it being missed? If no, propose one.
- `flags_by_kind.store_no_recall > 5` → dedup-before-store is failing. Check if `memory-dedup-check.py` hook is firing (it should gate `memory_store`). If it is and the signal still shows up, maybe the hook's dedup threshold is too strict.
- All three under threshold → report "recall hygiene healthy" in Step 9 and skip to the next step.

If the aggregate script fails for any reason → skip silently, note in Step 9 output.

## Step 5.5 — Calibration check (#251)

After outcomes are verified, check memory calibration:

```
mcp__memory__memory_calibration_summary(project="jarvis")
```

Renders per-type Brier score (mean squared error of `confidence - actual_outcome`). For each type with `n >= 20`, flag:
- `brier > 0.25` AND `avg_predicted > avg_actual` → **overconfident** (confidence in these memories exceeds their track record)
- `brier > 0.25` AND `avg_predicted < avg_actual` → **underconfident**
- `n < 20` → warning (insufficient data, skip calibration-based action)

Surface flagged types in Step 9 output under "Calibration". Poor-calibration types become ideation seeds for `/self-improve` — the root cause is usually a specific pattern (e.g. "my `decision` memories in jarvis are overconfident when they rely on research memories without principal confirmation").

## Step 5.75 — FoK calibration + insufficient clusters (#445, Phase 5.3-δ)

Two parallel scans on `fok_judgments` (the canonical store written by `scripts/fok-batch.py`).

**A. Calibration drift via RPC.** Call:

```
mcp__memory__execute_sql(query="SELECT * FROM fok_calibration_summary('jarvis')")
```

Returns `{n, brier, by_verdict, drift_signal}`. Apply:
- `n < 30` → not enough joined verdict↔outcome pairs yet, skip surfacing.
- `n >= 30 AND drift_signal = true` → flag in Step 9 under "FoK calibration drift" with `brier` value and `by_verdict` breakdown. Also pull the 5 most-divergent rows for the report:

  ```sql
  SELECT fj.query, fj.verdict, tout.outcome_status, fj.project, fj.judged_at
  FROM fok_judgments fj
  LEFT JOIN task_outcomes tout ON fj.outcome_id = tout.id
  WHERE fj.outcome_id IS NOT NULL AND fj.project = 'jarvis'
  ORDER BY POWER(
    CASE fj.verdict WHEN 'sufficient' THEN 1.0 WHEN 'partial' THEN 0.5 WHEN 'insufficient' THEN 0.0 END
    -
    CASE tout.outcome_status WHEN 'success' THEN 1.0 WHEN 'partial' THEN 0.5 WHEN 'failure' THEN 0.0 END
  , 2) DESC
  LIMIT 5;
  ```

**B. Insufficient-knowledge clusters.** Group last-7d `insufficient` verdicts by normalized query:

```sql
SELECT
  lower(regexp_replace(query, '\s+', ' ', 'g')) AS norm_query,
  count(*) AS hits,
  array_agg(DISTINCT rationale) FILTER (WHERE rationale IS NOT NULL) AS rationales
FROM fok_judgments
WHERE verdict = 'insufficient'
  AND judged_at >= now() - interval '7 days'
  AND project = 'jarvis'
GROUP BY norm_query
HAVING count(*) >= 3
ORDER BY hits DESC;
```

Each cluster = a recurring gap. Surface in Step 9 with query + hit count + a sample rationale.

**Empty state**: if both scans return nothing, print "No FoK clusters or calibration drift this period." — explicit, not silence.

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

### FoK calibration & clusters (#445)
- **Calibration**: Brier <score>, n=<n>, drift=<true|false>, by_verdict=<...>
- **Insufficient clusters (last 7d)**:
  - "<normalized query>" — <hits> hits, sample: <rationale>
- *(or)* "No FoK clusters or calibration drift this period."

### Recall audit aggregate (last 20 sessions)
- sessions=N, decisions=M, flags=<breakdown>
- <"healthy" | specific leak pattern + proposed fix>
```
