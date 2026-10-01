# Skill roster survey — which skills need work

Date: 2026-09-30. Scope: all 14 skills under `skills/`. Method: invocation counts from local
transcripts, a full read of every `SKILL.md`, and a check of every file, workflow and label the
skills reference against the repos they point at. This is a survey, not a design: it ranks what
to touch. Deep evidence for `/grill` and `/implement` lives beside this file in
`grill-skill-redesign-2026-09-30/` and `implement-skill-redesign-2026-09-30/`, with a
grill-ready brief for each in `grill-skill-redesign-2026-09-30.md` and
`implement-skill-redesign-2026-09-30.md`.

## Usage

Invocations per month, counted from `<command-name>` tags in non-meta user messages plus `Skill`
tool calls, deduplicated per skill/date/session file, over 705 transcripts in
`~/.claude/projects/*/*.jsonl` on one device. July is a lower bound (the oldest transcript files
start 2026-08-03). Other devices are not counted.

| skill | 07 | 08 | 09 | last used |
|---|---|---|---|---|
| implement | 23 | 191 | 158 | 09-30 |
| file-issue | 29 | 145 | 65 | 09-30 |
| end | 48 | 260 | 38 | **09-07** |
| grill | 9 | 80 | 23 | 09-30 |
| to-tickets | 3 | 14 | 8 | 09-29 |
| research | 5 | 12 | 7 | 09-30 |
| triage | 0 | 3 | 6 | 09-29 |
| diagnose | 1 | 7 | 0 | 08-31 |
| dispatch | 0 | 5 | 2 | 09-22 |
| improve-codebase-architecture | 0 | 4 | 0 | 08-17 |
| to-spec | 1 | 3 | 0 | 08-24 |
| prototype | 0 | 2 | 0 | 08-17 |
| weekly-release | 0 | 1 | 0 | 08-24 |
| wayfinder | 0 | 0 | 0 | never |

## Cross-cutting findings

1. **The decision-UUID contract is orphaned.** `/grill`, `/to-tickets`, `/dispatch` and
   `/wayfinder` require or cite decision UUIDs from the Supabase memory store. The store is gone;
   nothing generates UUIDs. `/grill` cites seven such UUIDs as the authority for its own rules —
   none can be resolved. `/to-tickets` makes a full UUID citation mandatory at publish.
2. **`handoff.md` exists in no project memory directory.** `/end`, `/implement` and `/dispatch`
   prescribe it as the working-state carrier. `decisions.md` is alive (redrobot 502 lines,
   jarvis-oss 106, jarvis 101, all touched in the last week).
3. **Two decision formats.** `CLAUDE.md` prescribes a dated entry with answer / why /
   alternatives / reversibility / confidence; the skills prescribe a one-line
   `- YYYY-MM-DD — <decision> — <why> — <#issue or PR>`.
4. **User-level skills import jarvis-only code.** `/implement`'s plan gate
   (`agents/implement_plan_gate.py`, `agents/plan_classifier.py`, `agents/plan_lock.py`,
   `config/plan_review.yaml`, `config/repos.conf`), `/to-tickets`' AFK-fit classifier and
   `/weekly-release`'s engine exist in `Osasuwu/jarvis` only. 187 of 365 distinct `/implement`
   executions ran in other repos (an earlier version of this line said 295 of 663; that index
   counted compaction replays as runs). Measured in the implement session audit: the plan-gate
   snippet fails on the first attempt in 23 of 23 observed attempts — a str-vs-`Path`
   `AttributeError`, not a missing module; outside jarvis 91 of 92 post-gate work runs get no
   verdict; inside jarvis 16 of 45 skip the gate without a trace.
5. **Wording drift.** "owner" throughout (the identity file forbids it); `main` vs `master`;
   references to `CLAUDE.md` sections that no longer exist (`### Memory & decision protocol`,
   "milestone-vs-slice hygiene"); paragraphs describing the demolished reactive-core
   (`emit_task`, `task_queue`, `events`).

## Per skill

| skill | verdict | evidence |
|---|---|---|
| **implement** | rewrite — highest priority | Most used, 454 lines. Jarvis-only plan-gate imports; §4c "run the write against live Supabase"; outcome fields of the dead memory store; `handoff.md`; mutation-probe gate points at the wrong section; §7.5 lets the authoring session self-merge LOW/MEDIUM PRs, against the "review in a fresh session" principle and impossible with `--auto` on Private+Free repos. |
| **grill** | rewrite | Second most consequential. Seven unresolvable UUIDs as authority; research-pass gate names Firecrawl; 269 lines + 629 in siblings. Its external numbers were audited after this survey: arXiv 2506.04907 is an unrelated paper (the 64.5% figure is from 2507.02778), "~64%" is an "up to 63.8%" figure for a different intervention, "-1..-12%" is half of a table. Session audit of 113 invocations: the sampling critic changed the design in 19 of 19 sampled runs; the coverage tier produces 32–144 items per run that the user refuses to read. Brief: `grill-skill-redesign-2026-09-30.md`. |
| **end** | retire | Not run since 09-07. Its main product (`handoff.md`) never exists; decisions are written on resolution under `CLAUDE.md` anyway; uses bare `git stash`/`git stash pop`, which the worktree rules forbid. Costs a roster slot and two test files (`tests/test_end_working_state_rmw.py`, keep-set in `tests/test_keep_set_skills_native_memory.py`). |
| **to-tickets / triage / dispatch** | one contract pass | They contradict each other: `/triage` says `/to-tickets` §5 applies the automation-queue label at Class 1, `/to-tickets` applies none. `/to-tickets` demands the UUID citation. `/dispatch` states that no executor workflow exists — `agent-dispatch.yml` has existed in jarvis since 2026-09-07 (223 runs: 1 success, 1 failure, the rest skipped/cancelled for other labels; 2 issues ever carried `agent:dispatch`). |
| **wayfinder** | retire or prove | Never invoked. Its own "dry-run before relying on this skill" was never done. Says `/to-spec` removes `needs-prd`; `/to-tickets` says no skill does. |
| **weekly-release** | fix one step or accept | Hidden, jarvis-only. Step 5 notify is broken (`agents/notify.py` is gone, disclosed as KNOWN GAP). Releases keep shipping weekly (jarvis v0.10.0 on 09-29), so the routine works without the local skill being invoked. |
| **to-spec, improve-codebase-architecture, prototype** | leave; wording only | 2–4 uses each, none in September. `to-spec` cites an identity-file sentence that no longer exists. Low value per edit. |
| **file-issue, diagnose** | leave | Generic and clean. `file-issue` is the second most used skill and has no stale reference. |
| **research** | in progress | Reddit removal merged (PR #1). Redesign brief in `research-skill-redesign-2026-09-30.md`. |

## Side finding outside this repo

`jarvis/.github/workflows/agent-dispatch.yml` sets workflow-level
`concurrency: agent-dispatch-issue-<n>` with `cancel-in-progress: true` and triggers on every
`issues: labeled` event. Workflow-level concurrency is evaluated before the job-level `if`, so
any other label added to the issue while a worker runs starts a run in the same group and
cancels the worker, then skips itself. 53 of 223 runs are `cancelled`. Not reproduced on a live
dispatch — inferred from the workflow text and the run history.
