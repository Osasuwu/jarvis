# Review rules

The rules a reviewer applies to a pull request in this repo. Two readers use this file:

- the CI reviewer in `.github/workflows/code-review.yml`, which reads the copy on the PR's base
  commit;
- the local pass `/implement` runs before `gh pr ready`, which reads the copy on a freshly
  fetched `origin/main`.

Both read the base copy, never the PR's: a PR that edits this file is reviewed under the rules
it is changing, and its new text is part of the diff under review. Each review's evidence
records the blob SHA of the copy it used (#2204).

This file holds what to look for. Each reader keeps its own workspace limits, tool grants and
output format; nothing here changes them.

## What the review is for

Ruff runs as a separate check (`.github/workflows/ruff.yml`, exit code only: `ruff check` rule
groups F/B/E722 plus `ruff format --check`). It covers syntax, unused code, bare `except`,
mutable default arguments and formatting. Do not report those again.

This review covers the defects that need judgment rather than a deterministic tool: git history,
reasoning across files, and comparing the diff with the linked issue's stated intent.

## How to review

1. Read the PR title and body for the linked issue, then the issue itself for its intent and
   acceptance criteria. Read the diff, the changed files in full for context, and callers and
   history on the base with `Grep`, `git log` and `git blame`.
2. Judge the diff against exactly the finding classes below. Raise nothing else: no severity
   ladder, no nitpicks.
3. Keep history narrow: blame only the lines the diff touches, plus the message of a fix commit
   that blame finds. Do not load whole files or the import graph into your context: the diff plus
   narrow blame reviews better than full context.

## Finding classes

- `regression` — reintroduces a bug a prior commit fixed. Use `git log` or `git blame` on the
  touched lines before raising it: it is the one class that needs blame context, not only the
  diff.
- `exception-handling` — the caught type is right but the recovery is wrong for this domain, or
  a failure is silently swallowed instead of surfacing. This is about meaning, not the bare
  `except` form that ruff already catches.
- `intent-vs-logic` — the code does not do what the linked issue or the PR description says it
  should.
- `breaking-contract` — a signature or behaviour change breaks a caller outside this diff. Grep
  the repo for call sites before raising it.
- `concurrency` — a race, a deadlock or an ordering bug.
- `requirement-semantics` — the diff does not actually meet an acceptance criterion of the linked
  issue.
- `design-modularity` — real erosion of module boundaries or cohesion that this diff introduces,
  not a style preference.
- `performance` — an N+1, or an O(n²) the diff adds, that a reader would flag; not a
  micro-optimisation.

The class names are also the CI gate's schema: `FINDING_CLASSES` in
`.github/scripts/code_gate_verdict.py` accepts exactly these, and a test pins the two lists
together. Adding, renaming or removing a class therefore changes that script too, which is gate
machinery and merges only by the review-blind admin-merge.
