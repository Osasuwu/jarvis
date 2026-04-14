---
name: verify
description: "Verify pending task outcomes: check PR merge status, test results, update records, extract lessons."
---

# Verify Outcomes

Closes the outcome tracking loop: did the work actually land?

## When to use

- After delegations have had time to merge
- As part of autonomous-loop (scheduled)
- Manual: `/verify` to check all pending outcomes

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

## Step 3 — Update verified outcomes

For each outcome that changed status, run via `execute_sql`:

```sql
UPDATE task_outcomes
SET outcome_status = '<new_status>',
    pr_merged = <true/false>,
    tests_passed = <true/false>,
    verified_at = now(),
    outcome_summary = COALESCE(outcome_summary, '') || E'\n[Verified] <brief result>'
WHERE id = '<outcome_id>';
```

Use Supabase project ID: `svwrzttdkxeselkpxfgm`.

## Step 4 — Extract lessons

Review all outcomes verified in this run. Look for patterns:

1. **Repeated failures** in the same area → save as `feedback` memory
2. **Successful patterns** worth repeating → save as `feedback` memory
3. **Quality trends** (low quality_score clusters) → flag in output

Only save non-obvious patterns. Don't save "PR was merged successfully" — that's expected.

## Step 5 — Output

```
## Outcome Verification — YYYY-MM-DD

### Verified (N)
- [+] <task_description> → success (PR merged, checks passed)
- [-] <task_description> → failure (PR closed without merge)

### Still pending (N)
- [?] <task_description> — PR open, awaiting review

### Patterns found
- <pattern description, or "None">

### Lessons saved (N)
- <memory name> — <one-line>
```
