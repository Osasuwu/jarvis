# Development process details

Pull-only detail for CLAUDE.md → *Development process*.

## Design RFC / proposal / debate

Goes to **GitHub Discussions, not an issue and not a PR.** Approval = thread resolution by the task initiator (user if user-started; orchestrator/PM if agent-started). Stable post-decision artifacts may land in `docs/design/` via direct commit; no PR ceremony.

## Fix > track for trivial reversible (#428)

Trivial, reversible, scope-obvious change (<30 min, own repo): **fix inline**. Don't open a tracking issue you'll close in 5 minutes — that's paperwork. Issues are for things you can't finish now, want to discuss, or that will outlive this session.

- **Fix inline**: stale doc fragment (broken link, version mismatch); missing test for newly-touched code; typo/comment cleanup adjacent to other work; config drift between two files; lint warning on a file you just touched.
- **Open issue**: architectural reshape >1h; cross-cutting refactor needing coordination; behavior change user should weigh in on; anything touching another active area mid-flight; foreign-owner repo where Jarvis can't merge.

The `Fix > track` rule does **not** override the rest of the development process — fixes still go through PR review, with the `[no-issue]` commit-msg marker.

## Other pointers

- Decisions-to-memory rule: [`.claude/rules/decisions-to-memory-not-markdown.md`](../../.claude/rules/decisions-to-memory-not-markdown.md) (path-gated, #1274).
- Path-filtered CI guards require a meta-test (#326): [`.claude/rules/path-filtered-ci-guards-meta-test.md`](../../.claude/rules/path-filtered-ci-guards-meta-test.md) (path-gated, #1274).
