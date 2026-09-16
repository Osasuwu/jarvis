# PR #963 rework blowup

**Date:** 2026-06-12 → 2026-06-29 (17 days, merged 2026-06-29)
**PR:** [`Osasuwu/jarvis#963`](https://github.com/Osasuwu/jarvis/pull/963) — `fix(install): health-check timeout no longer wedges or rolls back apply`

## What happened

A real, well-scoped bug fix (installer health-check hangs on Windows when a
health command re-execs into a venv grandchild that inherits stdout/stderr
pipe handles) took 33 commits and at least 21 separate automated code-review
passes over 17 days to land. The review bot re-ran on essentially every push,
each time as an independent 8-dimensional parallel review with no memory of
prior rounds' resolutions — so fixed findings were sometimes re-raised, and
each round could surface *new* findings in code the previous round had
already approved, keeping the PR in a churn loop rather than converging.
Multiple rounds are explicitly tagged "post-rework pass" or "re-review" in
the PR's own history, and one MAJOR (a `timed_out` flag masking a non-zero
self-exit code) took a dedicated rework-and-re-review cycle by itself.

The PR finally landed via **admin-merge bypassing the `review` gate**: on the
last head commit the review action ran twice, posted no comment either time
("No buffered inline comments" plus a failed summary-post with 9 permission
denials), and the `Verify review verdict` guard correctly failed closed. The
last *substantive* review (2026-06-22) was already APPROVE with its one
MAJOR fixed, all functional gates (`pytest`, `pytest-db`, `meta-tests`,
`gitleaks`, `owner-queue-guard`, `require-linked-issue`) were green, and
local suites passed — so the merge was judged safe, but only a human
reading the full 17-day thread could tell that a failing gate on this commit
was infra flake and not a real finding.

## Cost

- 33 commits and 21+ review rounds to ship a fix whose core design was
  judged sound in the **first** review pass (2026-06-12).
- 17 days elapsed between first review and merge.
- Final merge required a manual admin-merge decision and a written
  broken-gate justification, because the gate itself failed closed with no
  actionable signal.

## Rule / decision that came out of it

This incident is cited as founding evidence for the code-gate redesign
(`CONTEXT.md` → *Merge-gate vocabulary* → **Code-gate (target state, #1816)**):
replace the 12-parallel-reviewer `review` check with one blocking required
check split into a deterministic Layer A (lint + diff-shape verifier, no PR
comments) and an LLM Layer B whose findings are closed to eight fixed
classes and carry one binary blocking bit — no severity ladder, no
re-litigating already-approved code on every push. It is also the
evidence-base incident referenced by the jarvis-oss boundary-clause work
(`docs/decisions/2026-Q3.md` D21, D35): boundary clauses that warn readers
about review-gate churn or admin-merge-around-a-broken-gate point here
instead of to an untracked memory file.
