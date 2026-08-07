# PR → issue linkage — full reference

Pull-only. Not `@import`ed by anything — read it when a PR absorbs more than one issue, when
you are closing a PR as superseded, or when an issue stayed open after its work shipped. Moved
out of `CLAUDE.md` by [#1418](https://github.com/Osasuwu/jarvis/issues/1418): the rule an agent
must act on is one line (*list `Closes #N` for every absorbed issue*), and everything below is
the mechanism and the failure catalogue behind it — read once, not every session.

## The mechanism

Auto-close (native GitHub *and* `pr-merged.yml`) fires only from the PR's own
`closingIssuesReferences`. That list is built from closing keywords — `Closes` / `Fixes` /
`Resolves #N` and their `close/closed/fix/fixed/resolve/resolved` variants — found in **either
the PR body or any commit message on the branch**, not the body alone. Nothing else feeds it: not
a linked branch name, not the issue's own labels, and not prose without a real keyword.

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
- **Prose is invisible to the linkage — but only if it doesn't contain a real keyword+number
  pair.** The scan is a plain text match over the whole body, not code-span- or
  context-aware. A "shipped via #X" note closes nothing (no keyword). But writing the literal
  substring `Closes #N` *anywhere* — including inside backticks explaining why `Refs`, not
  `Closes`, was chosen — closes #N regardless of the surrounding sentence. Hit live on PR #1468:
  its Decisions section explained "`Refs #1274` instead of `Closes #1274`", and that spelled-out
  alternative alone put #1274 into `closingIssuesReferences` and closed it, despite the PR using
  `Refs #1274` as its actual link and #1274 having unmet AC groups. When a PR body needs to
  explain a Refs-vs-Closes decision, paraphrase the rejected keyword ("the closing keyword")
  instead of spelling out `Closes #N` literally.
- **A commit message is just as live a source as the body, and editing the body doesn't touch
  it.** `closingIssuesReferences` unions keyword hits from the body *and every commit on the
  branch*. Fixing the body while a commit message still contains the literal pair leaves the
  link intact — GitHub's own docs confirm editing the PR description cannot unlink something a
  commit-message keyword established. Hit live while opening *this very PR* (#1472): its first
  commit's message explained the #1468 incident by quoting `"instead of Closes #1274"` — the
  same literal-substring mistake, now in a place a body edit can't reach. The only fix is to
  reword the commit itself (`git commit --amend` if it's HEAD, otherwise rewrite and
  force-push) so the keyword+number pair never lands in git history at all.

## Superseded siblings

When you close a sibling PR as "superseded by #X", carry over **that sibling's own**
issue-closing keywords into #X's body. If the sibling listed `Closes #845, Closes #846`, add
those exact lines — **not** `Closes #<siblingPR-number>`, which resolves to a different object
entirely (the issue that happens to share that number).

## What counts as "absorbed"

An issue is absorbed when its **entire scope** ships in this PR — not when the PR merely
references it, touches the same file, or partially advances it. A partially-advanced issue
keeps its own PR later; listing it here closes it early and loses the remainder.
