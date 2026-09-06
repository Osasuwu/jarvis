# Development process details

Pull-only detail for CLAUDE.md → *Development process*.

## Design RFC / proposal / debate

Goes to **GitHub Discussions, not an issue and not a PR.** Approval = thread resolution by the task initiator (user if user-started; orchestrator/PM if agent-started). Stable post-decision artifacts may land in `docs/design/` via direct commit; no PR ceremony.

## Fix > track for trivial reversible (#428)

Trivial, reversible, scope-obvious change (<30 min, own repo): **fix inline**. Don't open a tracking issue you'll close in 5 minutes — that's paperwork. Issues are for things you can't finish now, want to discuss, or that will outlive this session.

- **Fix inline**: stale doc fragment (broken link, version mismatch); missing test for newly-touched code; typo/comment cleanup adjacent to other work; config drift between two files; lint warning on a file you just touched.
- **Open issue**: architectural reshape >1h; cross-cutting refactor needing coordination; behavior change user should weigh in on; anything touching another active area mid-flight; foreign-owner repo where Jarvis can't merge.

The `Fix > track` rule does **not** override the rest of the development process — fixes still go through PR review, with the `[no-issue]` commit-msg marker.

## Checking the code-review verdict before merging

The Claude code-review bot reviews every PR (via `code-review.yml`). It posts as an
**issue-comment**, not a PR review, so it does NOT appear in the Reviews tab:

```bash
gh api --paginate repos/Osasuwu/jarvis/issues/NUMBER/comments
```

Use `--paginate` so a comment past the first page isn't missed. Address valid findings with code
changes, or explain why no change is needed — don't assume the Reviews tab is the only place
feedback lands.

## Linking a sub-issue to a parent epic via API

```bash
# Get the internal ID of the child issue (NOT the issue number)
CHILD_ID=$(gh api repos/OWNER/REPO/issues/CHILD_NUMBER --jq '.id')

# Add it as a sub-issue to the parent
gh api repos/OWNER/REPO/issues/PARENT_NUMBER/sub_issues \
  --method POST \
  -F sub_issue_id="$CHILD_ID"
```

Use `-F` (not `-f`) so the ID is sent as an integer.

## Other pointers

- Decisions belong in the queryable memory store, not a markdown file (#1274).
- Path-filtered CI guards require a meta-test (#326): [`tests/ci/test_guard_test_convention.py`](../../tests/ci/test_guard_test_convention.py), detail in [`docs/reference/ci-guard-meta-tests.md`](ci-guard-meta-tests.md).
