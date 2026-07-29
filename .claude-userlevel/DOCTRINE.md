# DOCTRINE.md — shared cross-repo norms

Loaded via `@import` from user-level `CLAUDE.md` in every top-level session, every repo. **Carve-out**: cloud/scheduled runners and non-top-level readers (subagents, headless workflow steps) skip the user-level directory — this file is interactive-session guidance, not an enforcement mechanism; that lives in each repo's own `.github/workflows/code-review.yml` and `scripts/rework_policy.py`.

Every line clears the always-loaded bar (≥30% of tasks, decision `ff994ca2`). A repo's own tooling internals, issue history, or incident logs stay in that repo's `CONTEXT.md`, cited as e.g. "jarvis `CONTEXT.md` → *X*" — a qualified pointer fails visibly instead of misdirecting a different repo's session.

## Protocol layers

Durable behavior rules live in three tiers, each a backstop for the one above:

- **Tier 1 — durable prompt rules.** User-level `CLAUDE.md`, loaded every session. Default home for cross-skill rules — soft, judgment-based.
- **Tier 2 — mechanical hooks.** `PreToolUse`/`PostToolUse` deterministic fences for binary checks a prompt rule might be skipped on.
- **Tier 3 — skill-specific gates.** Belong to one skill; never duplicate Tier 1 content.

A rule escalates Tier 1 → Tier 2 when soft enforcement measurably fails (e.g. compliance dropping despite the rule existing) — the escalation call and its tracking are repo-specific.

## status:owner-queue label

A label any owned repo can apply meaning "park this for me — not autonomous-safe right now." On a PR it fails the repo's `owner-queue-guard` CI check, making the label a hard merge block, not just an FYI. Cleared by whatever resolves the reason it was applied. Distinct from `status:ready`/`status:in-progress` (claim state) — this tracks "needs a human before automation resumes."

## Review-blind carve-out

Some PRs are structurally unreviewable by the code-review bot — most commonly one that edits the review workflow itself. Mark such a PR review-blind rather than treating a missing review as a passed one. "Gate cannot run" is not "gate ran and raised no objection" — only the former grounds the admin-merge carve-out below.

## Sanctioned stop-gap merge

Admin-merge around a gate is normalized in exactly two cases: (a) the review-blind carve-out above, or (b) a *false-failing* gate (bug in the gate, not the PR) — valid once, with a tracking issue for the root cause linked in the merge comment. A second admin-merge around the same gate means stop and fix the gate, not normalize the bypass. Never for a gate that's merely inconvenient or slow.

## Merge-freeze doctrine

Symmetric partner to the rule above: a **known fail-OPEN bug** in a required check — silently passing PRs it should block — must **suspend auto-merge (freeze) for that check-class** until fixed, not just get a tracking issue while merges keep shipping past the hole. A false-failing gate blocks you, so it's noticed; a false-passing gate is silently relied on by every merge meanwhile — "file an issue and move on" isn't enough. Freeze-then-fix is the fail-open analog of fix-don't-bypass.
