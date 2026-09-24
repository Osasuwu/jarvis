# Deslop pipeline

This project does not run a mechanised comment-cleanup ("deslop") pipeline — no trace-inventory sweep, no comment classifier, no executable-token diff gate, and no dedicated "slop" dimension in code review.

## Why this is out of scope

The pipeline's tooling (`src/trace_inventory.py`, `src/comment_classifier.py`, `src/diff_gate.py` and their tests) was deleted with the rest of `src/` in 973721e (#1868). That removal was incidental to the reactive-core demolition, not a verdict on deslop — so on 2026-09-24 the direction was reviewed explicitly and closed rather than restored.

Reasons:

- The sweep was built to run AFK through sandcastle, which is gone; the current AFK lane (`agent-dispatch.yml`) has no slot for a repo-wide multi-file sweep.
- A separate "slop" review dimension (#1162) conflicts with code-gate Layer B, which returns a binary verdict over a fixed set of finding classes. Adding a graded style dimension there dilutes the blocking signal.
- The cheap half of the concern — don't write comments that restate the code — is a writing rule, not a pipeline. That part stays alive as #1161 (comment-discipline rule), outside this milestone.

`docs/deslop-standard.md` is kept as a record of the keep/remove taxonomy and is marked retired. If comment rot becomes a measurable problem again, start from the taxonomy there and a one-off `/implement` pass, not from restoring the deleted tooling.

## Prior requests

- #1162 — Deslop E2: slop review-dimension in code-review.yml + #326 meta-test
- #1164 — Deslop sweep: jarvis HEAD, non-protected files (AFK)
- #1212 — comment_classifier: replace rule-based interim v1 with real LLM judge
- #1727 — String/docstring ref scanner + diff_gate hardening
- #1728 — Docs leg: self-contained docs list + core-docs ref cleanup
- #1729 — Propagate trace-ref discipline rule to jarvis-oss template
