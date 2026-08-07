# Path-filtered CI guards — meta-test reference

Pull-only. Not `@import`ed by anything — read it when adding, renaming, or repointing a
blocking workflow under `.github/workflows/` that carries a `paths:` filter. Moved out of
`CLAUDE.md` by [#1418](https://github.com/Osasuwu/jarvis/issues/1418); the one-line convention
stays there, the reasoning lives here.

## The convention

`.github/workflows/X-guard.yml` ⇒ `tests/ci/test_X_guard.py`. Co-located, one meta-test per
path-filtered blocking guard.

## Why a path filter needs its own test

A `paths:` filter is a silent failure mode by construction. When the filter stops matching the
file it was meant to watch, the workflow does not error — it simply never runs, and every PR it
should have blocked goes green. Nothing in CI notices, because "did not run" and "ran and
passed" are indistinguishable at the branch-protection layer.

This is the exact class of bug behind #289 / #310 / #311: the guard watched
`supabase/schema.sql` while the canonical file was `mcp-memory/schema.sql`. It passed silently
for a sprint.

## The two dimensions a meta-test must cover

- **Config** — assert the workflow's `paths:` filter references the canonical file(s) by their
  real path. If the canonical path later moves, this assertion goes red and forces the workflow
  to move with it. That red is the entire point: it converts a silent miss into a build break.
- **Logic** — reimplement the guard's decision rule in Python and assert it blocks and allows
  the scenarios it claims to. `schema-drift-check` is the proof-of-concept; new guards follow
  the same shape.

## Where the meta-tests run

`.github/workflows/ci-meta.yml`, on every PR. Deliberately **not** itself path-filtered —
path-filtering the suite that exists to catch path-filter bugs would be self-undermining.

## Related

The same rename-in-lockstep hazard applies to a guard's **check name**: branch protection
references the job name, so renaming the job without updating the protection rule makes the
gate silently disappear. See `~/.claude/reference/merge-gates.md` → *Required files per repo*.
