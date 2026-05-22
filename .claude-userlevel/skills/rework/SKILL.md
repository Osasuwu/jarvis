---
name: rework
description: Reactive TDD loop against PR review findings — parse structured verdict, fix CRITICAL/MAJOR issues via TDD, invoke loop-stop guard policy, emit terminal artifacts.
version: 1.0.0
---

# Rework Skill

Reactive TDD loop against a structured code-review verdict on a PR. Takes a PR
number, fetches the structured review, classifies findings (CRITICAL/MAJOR/MINOR),
applies fixes with TDD discipline per CRITICAL finding, then invokes the loop-stop
guard policy to decide whether the loop has converged or must terminate.

Realises decision `9884299d-999c-4863-8b56-235fd09ec6e2` (Q6 — separate `/rework` skill).
Loop-stop guard policy (Q4) is decision `8e757f01-839b-4be2-a98b-a479452b5ec1`, implemented
at `scripts/rework_policy.py`.

## Usage

```
/rework <PR_NUMBER>
```

Single positional argument — the GitHub PR number to rework.

## Contract

This skill deliberately **skips** the SOUL.md grill-me checkbox. Findings are
explicit reviewer signals; assumptions were already grilled (or not) when the
initial `/implement` ran. Re-litigating findings as implicit assumptions adds
no value and duplicates the review cycle.

It **reuses** `_shared/tdd/` reference docs (`tdd-loop.md`, `tests.md`,
`mocking.md`, `refactoring.md`) for the red→green→refactor discipline inside
CRITICAL-finding fixes. Load them as operating procedure per finding — do not
reinvent the TDD loop inline.

**Territory boundaries** (what the skill does NOT touch):
- PR title — never modified
- `Closes #NNN` line in the PR body — never modified
- Labels other than `status:rework-in-progress` (entry) and `status:needs-human` (terminal stuck)

## Pipeline

### 1. Pre-flight

```bash
# Validate PR exists, is open, belongs to a tracked repo
gh pr view <N> --json number,title,state,headRefName,baseRefName,body,labels

# Check per-PR lock via outcome_records
# If an outcome row with pattern_tags=['pr-<N>', 'rework', 'in_flight'] exists
# and is <2h old → abort, another rework session is active
```

- Abort if PR state ≠ `OPEN`.
- Abort if per-PR lock with `in_flight` found and TTL not expired.
- On abort: write a GitHub comment explaining the skip, then exit.

### 2. Acquire lock + set entry label

```bash
gh pr edit <N> --add-label "status:rework-in-progress"
```

Record the per-PR lock:

```
outcome_record(
  task_type: "fix",
  task_description: "Rework PR #<N> — <PR title>",
  outcome_status: "pending",
  project: "<repo>",
  issue_url: "<PR URL>",
  pattern_tags: ["pr-<N>", "rework", "in_flight"],
  lessons: ""
)
```

The lock TTL is 2 hours. The orchestrator checks `in_flight` before dispatching
a new `/rework` for the same PR and skips if the lock is live.

### 3. Fetch PR state + review verdict

```bash
gh pr view <N> --json title,body,headRefName,baseRefName,additions,deletions,files
gh pr diff <N> -- <initial_diff_files>
```

- Save the initial PR diff file set and LOC count — these feed the scope-creep guard.
- Count existing `## Rework history` sections in the PR body to determine the attempt
  number. Attempt 1 has zero existing sections.

Fetch structured Claude code-review verdict (the most recent review comment
with a structured finding list). Parse findings per reviewer. Expected format:

```
## Findings

### CRITICAL
- **Description**: ...
  **File**: `path/to/file.py`
  **Line**: 42

### MAJOR
- **Description**: ...
  **File**: `path/to/file.py`
  **Line**: 85

### MINOR
- **Description**: ...
```

If no structured verdict exists on the PR, there is nothing to rework — push a
comment explaining that and exit with `rework_stuck` (as `stuck_no_findings`).

Classify each finding into CRITICAL / MAJOR / MINOR. Count totals:
`n_critical`, `n_major`, `n_minor`.

### 4. Reactive TDD per CRITICAL finding

For **each** CRITICAL finding, in order of appearance:

1. **RED** — Write a failing test that captures the finding. The test should fail
   with the current code to demonstrate the bug/issue.

   Load `_shared/tdd/tdd-loop.md` as the procedure. Follow vertical-slice
   discipline: one finding → one test → one fix at a time.

2. **GREEN** — Implement the fix. Run the test to confirm green.

3. **REFACTOR** — Clean up only what is under green coverage. Do not refactor
   adjacent untested code (per the refactor-permission clause in `tdd-loop.md`).

Record each fix's file:line in the attempt's `conflicts` map for the conflict
detection guard.

### 5. Apply MAJOR fixes

For each MAJOR finding:
- Apply the fix directly. No test mandate, but adding or updating tests around
  the touched code is encouraged.
- If a MAJOR finding touches code already covered by CRITICAL TDD tests, verify
  those tests still pass.
- Record each fix's file:line in the attempt's `conflicts` map.

### 6. Flag out-of-scope findings

Any CRITICAL or HIGH finding that the skill judges outside the scope of the
original PR diff:

```bash
gh issue comment <N> --body "Out-of-scope finding flagged: <description> — not addressed in this rework loop."
```

Do not silently drop non-obvious findings. A MINOR suggestion about naming or
style can be silently skipped.

### 7. Diff statistics

```bash
git diff <base>...HEAD --stat
```

Compute:
- `files_touched`: set of file paths changed in this attempt (union of CRITICAL
  and MAJOR fix files).
- `loc_delta`: total lines changed (additions + deletions from diff stat).

### 8. Invoke loop-stop guard policy

Load the history of all attempts (from `## Rework history` sections in the PR
body, plus the current attempt):

```python
from scripts.rework_policy import decide, PolicyResult

result: PolicyResult = decide(
    attempts=<current_attempt_number>,
    history=[
        {
            "attempt": 1,
            "n_critical": <int>,
            "n_major": <int>,
            "files_touched": {"set", "of", "paths"},
            "loc_delta": <int>,
            "conflicts": {"file.py": {42, 85}},
        },
        # ... per attempt
    ],
    initial_files={"set", "of", "files", "from", "initial", "PR", "diff"},
)
```

The policy returns one of:
- `CONTINUE` — loop may proceed to next attempt
- `CONVERGED` — targets met (n_critical==0, n_major≤2)
- `STUCK_ATTEMPTS` — ≥3 attempts without convergence
- `STUCK_SCOPE` — LOC delta >50% or files outside initial diff
- `STUCK_NO_CONVERGENCE` — critical+major not strictly decreasing
- `STUCK_CONFLICT` — same file:line touched in multiple attempts

### 9. Act on verdict

#### 9a. CONTINUE

```bash
git add <specific files>
git commit -m "fix(rework): attempt <N> — <brief summary>"
git push origin <headRefName>
```

Remove `status:rework-in-progress` label. Leave the PR open for the next
rework dispatch (orchestrator will re-dispatch on next `review_negative` event).

Exit cleanly.

#### 9b. CONVERGED

Converged means the findings targets are met. The caller (sandcastle / orchestrator)
handles the `## Rework history` PR body append (see issue #638 for the format).

The skill records the outcome:

```
outcome_record(
  task_type: "fix",
  task_description: "Rework PR #<N> — converged",
  outcome_status: "success",
  outcome_summary: "Loop converged: n_critical=0, n_major≤2 after <N> attempts",
  project: "<repo>",
  issue_url: "<PR URL>",
  pr_url: "<PR URL>",
  tests_passed: true,
  pattern_tags: ["pr-<N>", "rework", "terminal"],
)
```

Remove `status:rework-in-progress` label.
Do NOT merge. The PR stays open for human merge.
Release the per-PR lock by updating the `in_flight` outcome record.

#### 9c. STUCK_* (any stuck verdict)

Emit `rework_stuck` event via Supabase `events_canonical` table. Insert with:

```sql
INSERT INTO events_canonical (trace_id, actor, action, payload)
VALUES (
  gen_random_uuid(),
  'sandcastle:agent',
  'rework_stuck',
  jsonb_build_object(
    'pr', <N>,
    'verdict', '<loop_decision>',
    'reason', '<policy_reason>',
    'attempts', <N>,
    'reviewer_kind', '<reviewer_kind from verdict>'
  )
);
```

Alternatively, if the sandcastle anon key does not have INSERT on
`events_canonical`, use `memory_store` as a fallback:

```
memory_store(
  type: "project",
  name: "rework_stuck_pr_<N>",
  description: "Rework stuck signal for PR #<N>",
  content: "Verdict: <decision>. Reason: <reason>. Attempts: <N>.",
  project: "jarvis",
  tags: ["rework", "stuck", "pr-<N>"],
  source_provenance: "skill:rework"
)
```

Apply terminal labels and comment:

```bash
gh pr edit <N> --add-label "status:needs-human"
gh pr comment <N> --body "## Rework loop terminated\n\n**Verdict**: <decision>\n**Reason**: <policy_reason>\n\n### Attempts\n\n| Attempt | CRITICAL | MAJOR | Verdict |\n|---|---|---|---|\n| 1 | <N> | <N> | <verdict> |\n| 2 | <N> | <N> | <verdict> |\n| 3 | <N> | <N> | <verdict> |\n\nThis PR needs human review."
```

Record the outcome:

```
outcome_record(
  task_type: "fix",
  task_description: "Rework PR #<N> — stuck (<decision>)",
  outcome_status: "partial",
  outcome_summary: "Loop stuck: <decision> — <policy_reason>",
  project: "<repo>",
  issue_url: "<PR URL>",
  tests_passed: false,
  pattern_tags: ["pr-<N>", "rework", "terminal"],
)
```

Remove `status:rework-in-progress` label.
Release the per-PR lock by updating the `in_flight` outcome record.

#### 9d. Edge: no structured findings

If step 3 finds no structured review verdict at all:

```
outcome_record(
  task_type: "fix",
  task_description: "Rework PR #<N> — no findings",
  outcome_status: "failure",
  outcome_summary: "No structured review verdict found on PR #<N>; nothing to rework",
  project: "<repo>",
  issue_url: "<PR URL>",
  tests_passed: false,
  pattern_tags: ["pr-<N>", "rework", "terminal", "no-findings"],
)
```

Remove `status:rework-in-progress` label.
Release lock.

## Safety rules

- Never modify PR title, `Closes #NNN` line, or labels other than
  `status:rework-in-progress` (entry) and `status:needs-human` (terminal stuck).
- Never merge the PR — leave it open for human or orchestrator merge.
- Never invoke the SOUL.md grill-me checkbox or any `/grill` skill.
- Never push to `main` / `master` — only to the PR's `headRefName` branch.
- If CI fails after a rework push, comment on the PR with the failure details
  but do not revert. The orchestrator or owner handles CI failures.

## Diff review (before commit)

Before each commit:

```bash
git diff <base>...HEAD --stat
git diff <base>...HEAD
```

Check for:
- Scope fit: do changed files match the findings being addressed?
- Debug code, console.log, print statements left behind
- Unrelated changes that crept in
- Secrets or credentials in any form
- Symmetric patterns: when fixing a class of finding, grep for sibling instances
  across the file AND related files

## Recovery playbook

- **Push rejected** (force-push protection, non-fast-forward) → `git pull --rebase`
  and retry push.
- **Lock collision** (another session holds `in_flight` lock with TTL not expired)
  → post a comment and exit. The stale lock is the orchestrator's problem.
- **Test failure on a fix that worked locally** → check environment mismatch
  (Python version, database state, fixture data). If the test failure is real,
  fix it; if environmental, skip the test and note in the commit.
- **Mid-session context loss** → push whatever commits exist, remove label, release
  lock, mark outcome as `partial` with summary "context lost mid-rework".
