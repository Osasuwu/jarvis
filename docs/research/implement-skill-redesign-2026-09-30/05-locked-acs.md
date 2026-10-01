# Interactive `/implement` — locked acceptance criteria (2026-10-01)

Grill rounds 1–3 + Phase 3 dispositions D1–D6. Raw critic verdict: [`04-critic-raw.md`](./04-critic-raw.md) (S1–S7).
Decision journal (operator-local, not published): `decisions.md` entries "`/implement` grill, round 1/2/3", "Phase 3 pivot", "AC-lock".

Scope: the **interactive** skill only. The AFK half (`implement-afk`, auto-pickup, planner, headless gates) is
designed in the jarvis milestone "AFK orchestration". ACs marked **[interim]** sit on one of the four coupling
points that milestone owns — merge policy by risk, risk-line format + `waiting-human-review`, `## Plan` format,
`afk:*`/`needs-*` label contract. They hold until the orchestration contract replaces them; the replacement is
expected, not a regression.

Target: one jarvis-private PR, branched from **master** (472-line SKILL.md with the §4e test gate), not from the
older copy on `claude/skill-survey-grill-implement`.

## Shape and size

- [ ] **AC1 — size.** `skills/implement/SKILL.md` body ≤ 4,000 tokens, measured with Anthropic `count_tokens`;
      the figure is stated in the PR body. Must-not-skip rules come first in the body.
- [ ] **AC1a — late-phase text stays in the body (D5).** The PR template, risk line, merge rule and terminal
      state line live in `SKILL.md` itself, not in sibling files read at the moment of use. Rationale: size is
      necessary, not sufficient (S7) — siblings are not re-attached after compaction.
- [ ] **AC1b — compaction re-inject (D5).** A `SessionStart` hook with matcher `compact` in jarvis-private
      `settings.json` injects one line: "if an `/implement` run is in flight, re-read `skills/implement/SKILL.md`
      before the next step". Interactive only; it does not run headless and is not claimed to.

## Merge [interim — coupling point 1]

- [ ] **AC2 — merge by repo state.** Detect protection and `allow_auto_merge` from the GitHub API, then:
  - protection + auto-merge (jarvis, music-intel-mcp): `gh pr merge --auto --squash`;
  - protection, auto-merge off (like-current-song) **(D2)**: `gh pr checks --watch --required` — one blocking
    command, not a poll loop — then `gh pr merge --squash`; branch protection enforces the gates;
  - no protection: merge only when the review-bot verdict on the head SHA is green, all checks are green, risk is
    LOW/MEDIUM, and no touched path matches the repo rules file's `## Merge denylist`. Heading absent → no merge
    (fail-closed). No review bot (jarvis-private) → manual merge, the session stops at a green PR.
- [ ] **AC2a — `--admin` is forbidden (D4).** Enforced by a `PreToolUse` deny hook on `gh pr merge … --admin`
      in jarvis-private `settings.json`, not by prose alone.

## Risk line [interim — coupling point 2]

- [ ] **AC3 — risk line mandatory in every branch (D3).** The PR body carries the risk line before any merge
      call, whatever the repo state.
- [ ] **AC3a — HIGH/CRITICAL hold (D3).** Create the PR with `gh pr create --label waiting-human-review` (label
      at creation, so no `opened`-time pass can race a queued `--auto`), tell the user in chat, never merge.

## Plan and labels [interim — coupling points 3, 4]

- [ ] **AC4 — plan (D1).** If the issue has a locked `## Plan`, follow it; otherwise follow the ACs. Never invoke
      a planner. `afk:3-human` issues are allowed interactively. The skill carries **no** headless rules
      (`plan_required` exit, `afk:3-human` refusal) — those move to the orchestration milestone.

## Process

- [ ] **AC5 — `grill_required`.** Exit to `/grill` only when ≥ 2 of the 4 grill-checkbox answers are yes; a
      question answerable in one message is asked inline.
- [ ] **AC6 — tests.** Pointer to `~/.claude/reference/test-quality.md`; three TDD rules (red before green; one
      slice at a time; read test-quality.md before the first test edit); a claimed behaviour change shows its red
      run in the PR body. Master's §4e mutation-probe rule is kept by pointer.
- [ ] **AC7 — review.** The gate is a fresh-context reviewer: the CI review bot where one exists, else
      `/code-review` in a subagent. The in-session checklist becomes a pre-push sanity pass. The 12-smells list is
      deleted.
- [ ] **AC8 — worktree.** Detect the default branch; never `git checkout` it inside a worktree; cleanup is a no-op
      there.
- [ ] **AC9 — run lifecycle.** Claim before the first edit; one issue per run (§7 Batch deleted); re-read PR state
      from GitHub after a compaction; a `decisions.md` line; end with exactly one terminal state line.

## Cleanup

- [ ] **AC10 — dead text.** Remove the §4c Supabase write, `config/repos.conf`, "inline, no subagents", the L97
      and L101 citations and the §3b "fail-closed CI backstop" text; fix L89.
- [ ] **AC11 — Exploratory.** The oracle vocabulary moves to `/to-tickets`; `/implement` keeps one line on
      reporting negative results. `/to-tickets` plan-gate mentions at L51, L59, L132 fixed.
- [ ] **AC12 — pinned tests changed deliberately.** `test_keep_set_skills_native_memory.py`,
      `test_exploratory_tasks_skill_docs.py`, `test_implement_plan_gate_skill_structure.py`: each change is named
      and justified in the PR body; per test-quality.md, each surviving test still goes red if its behaviour breaks.

## Post-merge (follow-up issue, not this PR)

- [ ] **AC13 — invariant check (D6).** Over ≥ 6 real interactive runs, extended until ≥ 3 of them have ≥ 4
      compactions. Compared against the audit baseline on heavily compacted runs: Risk Assessment present 49/79,
      merge rule followed 26/55. Plus invariants: claim before first edit, terminal state line, `decisions.md`
      line, no checkout failure in a worktree.

## Deferred to "AFK orchestration"

- `pr-body-check.yml` risk-line gate (S4 deterministic half).
- Headless `afk:3-human` refusal and `plan_required` exit (S1).
- Final form of all four coupling points.
