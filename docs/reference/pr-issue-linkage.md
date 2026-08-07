# PR → issue linkage — full reference

Pull-only. Not `@import`ed by anything — read it when a PR absorbs more than one issue, when
you are closing a PR as superseded, or when an issue stayed open after its work shipped. Moved
out of `CLAUDE.md` by [#1418](https://github.com/Osasuwu/jarvis/issues/1418): the rule an agent
must act on is one line (*list `Closes #N` for every absorbed issue*), and everything below is
the mechanism and the failure catalogue behind it — read once, not every session.

## The mechanism

Auto-close (native GitHub *and* `pr-merged.yml`) fires only from the PR's own
`closingIssuesReferences`. That list is built **solely from this PR body's closing keywords** —
`Closes` / `Fixes` / `Resolves #N` and their `close/closed/fix/fixed/resolve/resolved` variants.
Nothing else feeds it: not a linked branch name, not the issue's own labels, and not prose.

Consequences, each of which has bitten at least once:

- **An absorbed issue you don't list gets neither close path.** It stays open with stale
  `sandcastle` / `in-progress` labels. This is #948 Mode 2: PR #900 shipped #845, #846, #847,
  #859 and #860 but listed only `Closes #851`, leaving five issues open.
- **Cross-repo closes are not automated.** `Closes owner/other#N` is not closed by
  `pr-merged.yml` — its `GITHUB_TOKEN` is repo-scoped, so it skips and warns. Close a foreign
  absorbed issue manually.
- **The list is frozen at merge time.** If the PR is already merged, editing its body is
  documentation-only and fires no close. Close the issues directly:
  `gh issue close #N --reason completed`.
- **Prose is invisible to the linkage.** A "shipped via #X" note closes nothing, ever.

## Superseded siblings

When you close a sibling PR as "superseded by #X", carry over **that sibling's own**
issue-closing keywords into #X's body. If the sibling listed `Closes #845, Closes #846`, add
those exact lines — **not** `Closes #<siblingPR-number>`, which resolves to a different object
entirely (the issue that happens to share that number).

## What counts as "absorbed"

An issue is absorbed when its **entire scope** ships in this PR — not when the PR merely
references it, touches the same file, or partially advances it. A partially-advanced issue
keeps its own PR later; listing it here closes it early and loses the remainder.
