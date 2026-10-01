# `/implement` skill redesign — brief for `/grill`

Date: 2026-09-30. Status: **research done, no direction approved, design not locked.** This file
is the input to the `/grill` session that locks the design; it is not the design. Evidence lives
beside it in [`implement-skill-redesign-2026-09-30/`](./implement-skill-redesign-2026-09-30/).

## The job the skill has to keep doing

Take one GitHub issue, by bare number, from "open" to "reviewable PR" with nobody watching: check
it is not already being worked, claim it, change the code, prove the change with tests, open a PR
whose body lets a reader decide on the merge without re-deriving the work, and leave a one-line
decision record. The session audit shows this core works: a run with zero human messages reaches
a PR 152 times out of 153, at a median of 93 tool calls and 33 active minutes. The redesign must
not trade that for ceremony.

## What was examined

| # | File | What it is |
|---|---|---|
| 01 | jarvis-private `evidence/implement-skill-redesign-2026-09-30/01-session-audit.md` (private: local transcripts) | Every `/implement` execution in the local transcripts of one device, 2026-07-22 → 09-30: 365 distinct executions (the earlier index's 663 rows were inflated by compaction replays), 262 of them work runs, 257 with a PR; 42 deep-read. |
| 02 | `02-external-evidence.md` | The skill's own four external citations checked against their sources, plus 2025–26 evidence on eight practices the skill encodes, each claim with URL and direct quote. |
| 03 | `03-citation-audit.md` | Independent fresh-context check of all 186 claims in 02: 151 supported, 29 supported with a caveat, 5 overstated, 1 wrong source, 0 quotes not found. Where 02 and 03 disagree, this brief follows 03. |

Limits that apply to everything below: one device, all 365 runs desktop-launched (no headless
evidence), audit numbers come from a subagent's scan and were not re-counted by a second one.

## Findings that drive the design

1. **The skill is longer than what survives compaction, and compaction is the normal case.**
   `SKILL.md` is 454 lines, 30,955 bytes (≈7.7k tokens by byte estimate). Claude Code re-attaches
   "the first 5,000 tokens" of a skill after a summary (02 B6; wording confirmed in 03). By that
   estimate the cut falls inside §4-TDD; §5 (PR template), §7.5 (merge policy), §8 (cleanup) and
   the safety rules are not re-attached. 254 of 365 runs compact at least once; work runs compact
   a median of 4 times. The late sections decay in step: a PR body carries *Risk Assessment* in
   18/19 runs with no compaction, 76/109 with 1–3, 49/79 with 4–9, 26/55 with 10+. Mechanical
   early steps (claim, tests, CI polling, the `decisions.md` line) do not decay. (01 §Q5. The
   exact cut line is an estimate. The decay is measured but confounded: heavily compacted runs
   are also the multi-PR ones, and only the first PR body was checked.)

2. **The plan gate (§3b) is broken as written and unbounded when it runs.** The Python snippet
   fails on the first attempt in 23 of 23 observed attempts (`AttributeError: 'str' object has no
   attribute 'exists'`). Of 137 work runs after the gate was added: inside jarvis 17/45 reach a
   verdict and 16/45 leave no trace of the gate; outside jarvis 1/92 reaches a verdict — the
   modules it imports exist only in `Osasuwu/jarvis`. When it does fire it is the single largest
   cost in the run: over 3 hours and 5 planner rounds in one run, about 4 hours of gate for about
   12 minutes of coding in another, "plan round 8" in a third. (01 §4.1.1.) Externally, no source
   measures a plan gate fired by a trigger; what is measured is that "a subpar plan hurts
   performance even more than no plan at all" and that Anthropic's own guidance is "if you could
   describe the diff in one sentence, skip the plan" (02 B1; 03 marks the broader "planning buys
   cost, not correctness" reading as one study on other models).

3. **`grill_required` exits to an orchestrator that is usually not there.** 72 of 365 runs end
   with `EXIT: grill_required`; 58 of those were typed by a human, so the "orchestrator" is the
   same person in the same window. `/grill` follows in the same session in 60 of 72, and in 15
   the grill span then does the implementation itself. 38 issues are never re-submitted to
   `/implement`. One trigger ("public API / contract") accounts for 54 of 72. The exit itself is
   cheap (median 6 tool calls). User reactions on record: "это tier:1-auto задача, какой grill?",
   "grill не нужен, решение лёгкое", "запусти /grill но быстро" twice. (01 §Q3.)

4. **The merge rule keys on a label that half the PRs do not carry.** §7.5 lets the authoring
   session merge LOW and MEDIUM. 129 of 257 PR bodies state no risk level; 59 of those were
   merged by the agent with no human message in between. No HIGH or CRITICAL PR was merged by the
   agent without a human message — that refusal holds. `--admin` was used in 15 runs, 10 without
   a human message; the carve-outs that would justify it live in `CLAUDE.md`, not in the skill.
   (01 §2.6–2.7, §4.1.6.) Externally: no source measures the accuracy of a self-assigned risk
   label; Meta's published auto-land system scores risk with a separate model, requires a
   track record and keeps blocklists (02 B5; per 03, its P5 threshold is for human diffs — agent
   diffs start at P20).

5. **The route table is mostly unused and "TDD-mode" is an announcement, not a behaviour.** 191
   of 365 runs state no route. Of 76 runs that announce TDD, 45 write the test first and 18 write
   source first. Across runs with code edits, source-first (92) outnumbers red-first (75); only
   one repo (music-intel-mcp, 21 red-first to 10) has test-first as the norm. (01 §2.3, §4.1.3,
   §Q6.)
   What the external evidence supports is narrower than "TDD": tests that exist before and
   independently of the implementation help; tests written after faulty code detect less (14% vs
   25% in one study); and both read-only tests and explicit prompt wording reduce test tampering
   (02 B2, with 03's corrections: the prompt effect is real, the "escape hatch" effect is near
   zero for Claude models).

6. **The mutation probe is done where it applies.** Every one of the 33 red-first runs after the
   step existed mentions it, and it was actually executed in 7 of 7 deep-read checks. (01 §4.1.4.)
   Industrial evidence supports a few targeted mutants over coverage as the check on generated
   tests; nothing measures a single mutant chosen by the test's own author. (02 B3.)

7. **Review before merge is same-session self-review.** The skill's diff review and checklist run
   in the context that wrote the code. External measurements: LLM reviewers show self-preference
   on their own output; fresh-context automated reviewers find a minority of what humans find
   (20–32% per tool in one benchmark, 41.5% for the union) at low precision; "a reviewer prompted
   to find gaps will usually report some". (02 B4; 03 removes the unsupported claim that another
   model family beats a fresh context of the same model, and narrows the "recall under 10%"
   figure to PRs with five or more changes.)

8. **§3 and §8 assume a plain checkout on `main`.** `git checkout main` followed by
   `git branch -d` fails in every deep-read worktree run; this repo's default branch is `master`.
   A new branch is created in 150 of 262 work runs — the rest are already on one. (01 §4.1.7.)

9. **Dead and unverifiable text.** `handoff.md`: 0 writes in 365 runs. `config/repos.conf`: read
   in 19. §4c's live-Supabase write: the store is gone. "Inline, no subagents": `Agent` is used
   in 63 of 262 work runs. Of four external citations in the skill, L89 is partly supported (four
   of the five oracle terms appear in the cited survey), L101's claim is not in the cited paper,
   L97 has no source, and L426's "Fowler's 12 code smells" is a subset copied from a third-party
   skill without its "always a judgement call" qualifier. (01 §4.1.8–4.1.9; 02 Part A.)

10. **Ordering and terminal state.** The claim lands after the first edit in 36 of 232 editing
    runs. 328 of 365 runs overlap another `/implement` run in time; one duplicate PR resulted.
    The agent loses track of merge state across compactions; 44 human messages are a bare
    "merged" sign-off and 42 are "continue" nudges. (01 §2.2, §Q4, §Q7.)

11. **Cost sits in a tail.** The top 10% of runs account for 40% of tool calls; 46 runs open more
    than one PR; the maximum is 1,332 tool calls and 67 compactions in one run. (01 §Q5.)

12. **What already works and should not be touched.** Pre-flight and claim (261 and 249 of 262);
    the refusal to self-merge HIGH/CRITICAL; the `decisions.md` line (56 of 59 work runs since the
    memory switch, and it survives compaction); the cheap early exit; `/file-issue` for
    follow-ups (49 runs); bare-number invocation (336 of 365); a test run before the PR (240 of
    262). (01 §5.2.)

13. **Prior art is an order of magnitude shorter and none of it merges to the default branch.**
    Comparable `implement` skills run 15–40 lines with separate `tdd` and `code-review` skills;
    the long ones (200–570 lines) ship scripts and a ledger. None publishes an evaluation.
    (02 B8; the last point is an absence claim that 03 could not audit.)

## Open forks for the grill

Each carries the proposer's recommendation; none is decided.

1. **Shape of the file.** One long `SKILL.md`, or a short orchestrating body that fits the
   re-attachment window with late-phase text in sibling files read at the moment of use.
   Recommendation: the second — must-not-skip rules first, PR template and merge rule in siblings
   the body tells the agent to read immediately before `gh pr create` and before any merge call.
   Open sub-question: whether a `SessionStart`/`compact` hook should re-inject the skill instead;
   the docs offer it, nothing here has tested it.

2. **Plan gate.** Repair, bound, or remove. Recommendation: remove it from the user-level skill.
   It produces a verdict in 1 of 92 runs outside jarvis and costs hours when it fires; jarvis can
   carry a repo-local override if the gate is wanted there. If kept: one planner round, no critic
   loop, and a snippet that is tested. Seven tests in
   `tests/test_implement_plan_gate_skill_structure.py` pin the current wiring and would go with it.

3. **`grill_required` hand-off.** Keep the hard exit, or allow a sanctioned inline path.
   Recommendation: keep the cheap exit for real design forks; add an explicit inline path for a
   question the human can answer in one message; narrow the "public API / contract" trigger;
   state who resumes `/implement` afterwards. This fork depends on whether `/grill` gets a quick
   tier (see the `/grill` brief).

4. **Merge rule.** Self-assigned risk label, or a rule computed from something always present.
   Recommendation: a script-computed gate (path denylist plus diff size) decides eligibility; the
   risk line becomes mandatory before any merge call; the HIGH/CRITICAL refusal stays; admin-merge
   is either spelled out in the skill with its two `CLAUDE.md` carve-outs or forbidden to the
   skill. Note that on Private+Free repos there is no `--auto`, and that `SOUL.md` asks for review
   in a fresh session — so "the authoring session never merges" is a live option.

5. **Test-first.** Keep the route table, or replace it with an evidence requirement.
   Recommendation: drop the mode announcement; where a behaviour change is claimed, the PR body
   must show the red run that preceded the fix. Keep the prompt instruction not to weaken tests.

6. **Mutation probe.** Recommendation: keep for test-first runs, add an "equivalent mutant,
   skipped" outcome so the step cannot force a meaningless edit.

7. **Review.** Same-session checklist, or a fresh-context reviewer as the gate. Recommendation:
   fresh-context review (the bundled `/code-review` or the CI review bot) is the gate; the
   in-session checklist shrinks to a pre-push sanity pass; the "12 code smells" list goes or gets
   its qualifier back. The evidence does not say this catches most defects — only that
   same-session review has no measurement behind it at all.

8. **Worktrees and default branch.** Recommendation: detect the default branch, never
   `git checkout` it inside a worktree, and make cleanup a no-op there.

9. **Dead text.** Recommendation: delete `handoff.md`, the Supabase write, `config/repos.conf`
   and "inline, no subagents"; fix or drop the four citations. `## Exploratory tasks` is pinned
   by a golden-text test including the five oracle terms — a deliberate test change.

10. **Claim order and terminal state.** Recommendation: claim before the first edit; end every
    run with one explicit state line (PR open / merged / blocked on X), and re-read PR state from
    GitHub before acting on it after a compaction.

11. **Multi-issue runs.** Recommendation: one issue per run; a cascade is split into separate
    runs rather than capped inside one.

## Constraints the redesign must respect

- `tests/test_keep_set_skills_native_memory.py` pins `implement` in the keep set: no legacy
  memory vocabulary, `decisions.md` named, every relative link resolves (sibling files must
  exist).
- `tests/test_exploratory_tasks_skill_docs.py` pins the `## Exploratory tasks` section, the
  strings `mechanical-mode`, `TDD-mode`, `grill_required`, and six numbered pipeline headings.
  Forks 5 and 9 cannot land without changing it.
- `tests/test_implement_plan_gate_skill_structure.py` pins the plan-gate wiring (fork 2).
- Tests change deliberately, with the reason recorded — never loosened to make an edit pass.
- `/dispatch`, `/to-tickets` and `/triage` name `/implement` and its exit contract; a changed
  exit needs the same pass over them.
- The skill is user-level: it runs in repos that have none of jarvis's modules, on `main` and on
  `master`, in worktrees and in plain checkouts.
- Skills are read from the master checkout; nothing is live until merged.
