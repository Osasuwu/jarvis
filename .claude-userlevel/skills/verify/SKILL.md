---
name: verify
description: "Verify pending task outcomes: check PR merge status, test results, update records, extract lessons."
---

# Verify Outcomes

Closes the outcome tracking loop: did the work actually land?

## When to use

- After delegations have had time to merge
- Manual: `/verify` to check all pending outcomes
- (Pre-2026-05-26: scheduled inside `/autonomous-loop` — superseded.)

## Step 1 — Fetch pending outcomes

```
outcome_list(outcome_status="pending")
```

If none found → report "No pending outcomes" and stop.

## Step 2 — Verify each outcome

For each pending outcome, verify based on available data:

### If `pr_url` exists (delegation/fix):
```bash
gh pr view <pr_url> --json state,mergedAt,statusCheckRollup --jq '{state, mergedAt, checks: [.statusCheckRollup[] | {name: .name, conclusion: .conclusion}]}'
```

Determine:
- **success**: PR merged + checks passed
- **partial**: PR merged but some checks failed, OR PR open but checks pass
- **failure**: PR closed without merge, OR checks failing
- **pending**: PR still open, reviews pending → skip (not yet verifiable)

### If `issue_url` exists (no PR):
```bash
gh issue view <issue_url> --json state,stateReason --jq '{state, stateReason}'
```

- **success**: issue closed as completed
- **failure**: issue closed as not planned
- **pending**: issue still open → skip

### If neither URL exists (autonomous/research):
- Outcomes older than 7 days with no URL → mark as **unknown**
- Otherwise → skip

## Step 2b — Post-merge diligence audit (subagent-dispatched PRs only)

Applies only to outcomes just verified `success` in Step 2 whose `pattern_tags` include `"subagent"` (dispatched via `/dispatch` → `task_queue` → headless spawn — #1085 Slice 2). Inline `/implement` work was written and reviewed live by the operator already; auditing it here would be redundant. Migrated from the pre-Slice-2 `/delegate` §6 synchronous review — that review point no longer exists once dispatch is async and merge happens headlessly, so this is now the first and only diligence pass for subagent output.

```bash
gh pr view <pr_url> --json baseRefName,headRefName --jq '.baseRefName + " " + .headRefName'
git fetch origin
git diff origin/<base>...origin/<head> --stat
git diff origin/<base>...origin/<head>
```

Four checks, run in order — do NOT short-circuit:

- **Value-change audit**: grep the diff for numeric literals, default parameter values, seed arrays, tuple constants, timeouts, thresholds. For each value that changed, confirm the change is explicitly mandated by the issue body. Silent replacements are scope drift. (Lesson #648: subagent silently replaced IK seeds `[0,-30,30,0,-60,0]` with `ready_position` — same shape, different semantics.)
- **Interaction audit**: for every non-trivial edit, trace data flow outward — what callers depend on the pre-existing behavior, what fallbacks or post-processors run after the changed code. Ask "does this still compose correctly?", not just "does the code do what it says?" (Lesson #649 v2: a 6-DOF IK fix was locally correct but the pre-existing J6-pin fallback silently clobbered the result, undoing it.)
- **Divergence audit**: if the diff departs from the AC's literal signature, values, or interpretation and the PR body has no `## Deliberate divergences` section, treat as silent design drift. (Lesson #634: subagent reshaped `decide(...)` from 4 args to 3 and picked a stricter rule than the AC suggested, undeclared.)
- **Drive-by audit**: for any "remove X" / "delete the line about Y" instruction in the issue, confirm the diff deletes rather than replaces. (Lesson #662: subagent replaced a stale bullet with new text that duplicated the next existing line.)

If any check finds a problem:
- Downgrade the outcome's `outcome_status` to `partial` in Step 3 (the PR is already merged — the finding can't retroactively unmerge, only the code can be fixed forward).
- `lessons` records the specific finding.
- Live drift in `main` → fix inline if trivial/reversible (CLAUDE.md "Fix > track"), else `/file-issue`.

## Step 2c — Plan-conformance check (afk:2-plan PRs, #1692)

Applies to outcomes just verified `success` in Step 2 whose `pattern_tags` include `"afk:2-plan"`. Independent detector alongside the CI diff-gate (#1687) and the review gate — this one runs after merge, on the shipped PR body, not before.

```bash
gh pr view <pr_url> --json body --jq '.body'
```

Use `agents.plan_conformance`:

```python
from agents.plan_conformance import missing_sections, extract_divergences, rework_round_count

missing = missing_sections(pr_body, is_class_2=True)      # AC1/AC2
divergences = extract_divergences(pr_body)                # AC3
```

- `missing_sections` non-empty → **finding**: an `afk:2-plan` PR shipped without a `## Plan-conformance` and/or `## Plan-divergences` section where one was required. Downgrade to `partial` in Step 3, `lessons` names which section(s) are missing.
- `extract_divergences` non-empty → surface each `(what, reason)` pair in the Step 5 output verbatim, not just a count. A declared divergence is not itself a defect — reviewing readers judge the reason, `/verify` only makes it visible. An **undeclared** divergence (diff clearly departs from the plan but no `## Plan-divergences` bullet mentions it) is the same silent-drift class as the Step 2b divergence audit; if spotted, treat it the same way (downgrade + `lessons`).

### Rework-round metric (AC4–AC7)

Every `afk:2-plan` PR's rework rounds = `rework_round_count(history)` from `agents.plan_conformance`, reusing `scripts/rework_policy.py`'s own `/rework` attempt history — no parallel counter (see that module's docstring for the full metric definition, baseline linkage to #1683, and rollback plan). Track it via `pattern_tags` (`"afk:2-plan"`) in Step 4's queries below; there is no separate ledger.

When the count of `success`/`partial` `afk:2-plan` outcomes reaches `agents.plan_conformance.CHECKPOINT_THRESHOLD` (~10) — check via:

```sql
SELECT COUNT(*) FROM task_outcomes
WHERE outcome_status IN ('success', 'partial')
  AND 'afk:2-plan' = ANY(pattern_tags);
```

— report it prominently in Step 5 and make exactly one of the three decisions `agents.plan_conformance.CHECKPOINT_DECISIONS` states in advance (`retune` / `keep` / `rollback`), comparing the average rework-round count on this window against the #963 baseline (5 rounds, #1683). `rollback` executes `agents.plan_conformance.ROLLBACK_STEPS` in order. Do not defer the checkpoint decision past the report — an honest "the stage did not pay off" is the point of writing the checkpoint down in advance (#1692 description).

## Step 3 — Update verified outcomes

For each outcome that changed status:

```
outcome_update(
  id="<outcome_id>",
  outcome_status="<new_status>",
  pr_merged=<true/false>,
  tests_passed=<true/false>,
  memory_id="<primary informing memory id>",   # enrich if still unset — see rule
  lessons="<brief result if any>"
)
```

**Enrich `memory_id` if the outcome row has it NULL**: look up the linked `decision_made` episode (same issue/PR) and pass the first entry of `payload.memories_used` that is a **memory-row UUID** (verify with `memory_get` by id, or match it in the session's recall map). If the outcome already has `memory_id`, leave it alone; `/verify` is not where you rewrite attribution. If no decision episode references this issue, omit — the backfill script (`scripts/backfill-outcome-memories.py`) can handle historical rows in bulk.

**Only backfill a verified memory-row UUID.** Two known bad shapes in historical `memories_used` (both write a broken FK or get rejected):
- Memory NAMES, not UUIDs — per #325 audit: of 33 historical `decision_made` episodes, 21 had empty `memories_used` and 12 stored names (zero matched the FK shape). A name fails the `^[0-9a-f]{8}-` shape check; omit and leave for the backfill script's name→id resolution.
- Decision-**episode** UUIDs — shape-valid UUIDs that live in the episodes table, not `memories`; the FK `task_outcomes.memory_id → memories(id)` rejects them with 23503 (bitten 2026-07-02, #971 outcome). Shape checks can't catch these — confirm the id resolves via `memory_get` (or is present in the recall map) before passing it.
If the first entry fails either check, try the next; if none qualify, omit `memory_id`. If no decision episode references this issue, also omit.

**Empty `memories_used` is valid** (per #334 expanded triggers: policy/schema/tag/config decisions may genuinely have no memory basis). If the matching decision episode exists but its `memories_used` list is empty, skip the enrichment — do NOT error, do NOT guess. Outcome stays `memory_id = NULL`; this is the correct representation for a decision that wasn't informed by prior memory.

`verified_at` is set automatically when status changes from pending.

## Step 4 — Detect patterns

**Minimum data**: skip pattern analysis if fewer than 5 total outcomes exist.

Run these queries via `execute_sql` (project: `svwrzttdkxeselkpxfgm`):

### 4a. Success rate by task type
```sql
SELECT task_type,
       COUNT(*) AS total,
       COUNT(*) FILTER (WHERE outcome_status = 'success') AS succeeded,
       ROUND(100.0 * COUNT(*) FILTER (WHERE outcome_status = 'success') / COUNT(*)) AS success_pct
FROM task_outcomes
WHERE outcome_status != 'pending'
GROUP BY task_type
ORDER BY total DESC;
```

### 4b. Failure clusters by pattern_tags
```sql
SELECT tag, COUNT(*) AS failures
FROM task_outcomes, LATERAL unnest(pattern_tags) AS tag
WHERE outcome_status = 'failure'
GROUP BY tag
HAVING COUNT(*) >= 2
ORDER BY failures DESC;
```

### 4c. Repeated lessons (same lesson appearing 2+ times)
```sql
SELECT lessons, COUNT(*) AS occurrences
FROM task_outcomes
WHERE lessons IS NOT NULL AND lessons != ''
GROUP BY lessons
HAVING COUNT(*) >= 2
ORDER BY occurrences DESC
LIMIT 5;
```

### Pattern → feedback memory rules

Save as `feedback` memory when:
- A task type has **success rate < 60%** with 3+ samples → save: "task_type X has low success rate — investigate root cause"
- A pattern_tag appears in **2+ failures** → save: "area X is failure-prone — add extra verification"
- A lesson repeats **3+ times** → save: "recurring lesson — make this a permanent rule"

Only save non-obvious patterns. Don't save "PR was merged successfully" — that's expected.

## Step 5 — Output

```
## Outcome Verification — YYYY-MM-DD

### Verified (N)
- [+] <task_description> → success (PR merged, checks passed)
- [-] <task_description> → failure (PR closed without merge)

### Still pending (N)
- [?] <task_description> — PR open, awaiting review

### Patterns (last 30 days)
| Task Type | Total | Success % |
|-----------|-------|-----------|
| delegation | N | N% |

Failure clusters: <tag1 (N), tag2 (N), or "None">
Repeated lessons: <lesson (Nx), or "None">

### Feedback saved (N)
- <memory name> — <one-line>
```
