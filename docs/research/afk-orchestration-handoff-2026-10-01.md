# Handoff — AFK orchestration and the `/implement` rewrite (2026-10-01)

Two fresh sessions start from here. Each one is self-contained. Pick one per session, and do not run both in the
same session.

The `docs/research/…` paths below are in this repo. `decisions.md` is the operator's decision journal; it is
machine-local and not published, so on another device read this file instead.

## Session A — AFK orchestration (jarvis milestone 71)

**Goal:** one orchestration contract that starts the right skill by conditions: implement, plan, research, and
anything else that runs unattended. Interactive skills should fit the contract, not fight it. The user wants this
done once, so that the automation is not rebuilt a fourth time.

**Order:**
1. Run #1957 (retrospective of the 8 designs) and #1958 (external research, 9 topics) in parallel. Use `/research`
   for both.
2. Run #1959 (cleanup) at any time. It is independent; keep it to its in-scope list.
3. Run #1960 (architecture `/grill`). It is blocked by #1957 and #1958, and the native `blocked_by` edges are set.
   Phase 3 coverage and grounding tiers are mandatory, because this is milestone-level.
4. After the grill, run `/to-tickets` and then `/wayfinder`.

**Read first:**
- `docs/research/afk-orchestration-inventory-2026-10-01.md`: leftovers of the previous designs, verified run
  counts, and the 10 open questions.
- `docs/research/implement-skill-redesign-2026-09-30/05-locked-acs.md`: the 4 coupling points this milestone owns,
  and the interim rules `/implement` uses until then.
- `docs/research/implement-skill-redesign-2026-09-30/04-critic-raw.md`: S1 (the headless rules are unreachable)
  and S4 (deterministic carriers).
- The milestone 71 description (PRD stub).
- `decisions.md`, every 2026-10-01 entry from "Phase 3 pivot" onward.

**Lessons the design must answer, not only cite:**
- **This is the 8th attempt.** Every earlier design built infrastructure before a lane had been proven at volume.
  The current lane's `agent-dispatch` runs: 1 success, 1 failure, 54 cancelled, 222 skipped. #1809 (the quota
  baseline) has not started. A rule is proposed and must be decided: no new infrastructure until the current lane
  has passed N real runs.
- **Inflexibility is structural.** The user observed that any large enough change goes through very slowly. One
  contract (labels, `## Plan`, risk line, merge policy) is restated in prose across about 7 skills and several
  workflows. Every change has to touch all of them, and they drift: `status:owner-queue` has 3 meanings, and three
  labels referenced in skills exist in no repo. Research topic 6 (one source of truth) exists for this. Treat it as
  a design requirement, not a nice-to-have.
- **Two lanes already diverge.** jarvis-oss has a forked lane with human merge, pytest, machinery-guard and an
  authority detector. jarvis has the opposite. Which one is canon is open question 2. Settle it early, together
  with repo scope (question 1).
- **Identity.** The PAT, the review bot and the user share one account, so the agent can release its own holds
  (#1894). Any hold the design relies on has to survive this.

**Premises to test, not assume:**
- "Automation runs on claude-code-action" is the user's current intent. #1958 topic 2 compares it with `claude -p`
  on a self-hosted runner, with the Agent SDK, and with Claude Code cloud sessions. Let the evidence confirm or
  overturn it.
- "AFK starts by conditions, not via `/dispatch`" is the user's direction. The fate of `/dispatch` is still open
  question 3.

**Active constraints:**
- Merge freezes on fail-open review gates: jarvis#1073 (non-`CODE_PATHSPECS` diffs) and music-intel-mcp#226 (a
  stale `code-review.yml` gives a green check with no review; this applies to like-current-song as well). Do not
  build a lane that merges through these classes before they are fixed.
- Milestone 68 "Plan-review stage" is closed as superseded. Whether its code (`agents/plan_*.py`,
  `scripts/plan_review_diff_gate.py`, `config/plan_review.yaml`) is revived is open question 4. #1959 must not
  touch it.

## Session B — interactive `/implement` rewrite (jarvis-private)

**Goal:** implement `05-locked-acs.md` (AC1–AC12) in **one** jarvis-private PR.

**Mechanics:**
- Branch from **master**. Master's `skills/implement/SKILL.md` is 472 lines and has the §4e test gate. The copy on
  `claude/skill-survey-grill-implement` is older; do not start from it.
- Measure the size with Anthropic `count_tokens` and state the figure in the PR body. Body ≤ 4,000 tokens.
  Late-phase text (PR template, risk line, merge rule, terminal state) stays in the body.
- Hooks go in jarvis-private `settings.json` (`"hooks": {"PreToolUse": []}` already exists):
  - a PreToolUse deny on `gh pr merge … --admin`;
  - a SessionStart hook with matcher `compact` that injects one re-read line.
  Confirm the matcher semantics against Claude Code docs before writing it.
- `/to-tickets` edits are in the same PR: the Exploratory vocabulary, and the plan-gate mentions at L51, L59, L132.
- Read `~/.claude/reference/test-quality.md` before touching the three pinned tests
  (`test_keep_set_skills_native_memory.py`, `test_exploratory_tasks_skill_docs.py`,
  `test_implement_plan_gate_skill_structure.py`). Name and justify each change in the PR body.
- Review: jarvis-private has no review bot, so use `/code-review` in a fresh-context subagent. The merge is manual
  (by the user).
- Reference jarvis#1961 (the post-merge check) in the PR body.

**Do not:**
- re-open the four coupling points: they are interim by design;
- add headless rules: they belong to milestone 71.

## Loose ends outside both sessions

- Docs placement, decided 2026-10-01: the research is published here with the user's quotes paraphrased; the 01
  session audits stay in jarvis-private `evidence/`. The staging copy in jarvis-private
  (`claude/skill-survey-grill-implement`, draft PR 6) is removed once this lands.
