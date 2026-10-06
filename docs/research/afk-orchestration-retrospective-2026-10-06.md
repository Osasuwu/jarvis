---
topic: afk-orchestration-retrospective
tags: [area:infrastructure, research, afk-orchestration]
source_provenance: https://github.com/Osasuwu/jarvis/issues/1957
status: open
audit: 2026-10-06 — 75 claims: 60 SUPPORTED, 14 PARTIAL, 1 UNSUPPORTED, 0 UNCHECKABLE
---

# Retrospective — the eight previous AFK orchestration designs (2026-10-06)

## Question

Why did each of the eight unattended-orchestration designs that Jarvis built before milestone 71 stop?
The eight are: (1) autonomous loop v1, (2) Pillar 7 LangGraph, (3) sandcastle, (4) ralph-loop,
(5) reactive-core (M44), (6) convergence (M58), (7) plan-review (M68), (8) the rebuild on
claude-code-action (M70). The answer feeds the architecture grill #1960.

Narrowing:
- A "real unattended run" is an agent run that a trigger started (a timer, a label, an event) without a
  human launching it in a terminal, and that reached the model. It excludes skipped workflow runs,
  concurrency cancellations, attended smoke tests and webhook forwarders. Where a design left no run
  trace, the count is given as "not countable" with the reason.
- Run counts come from the GitHub API (Actions runs, PR head branches, claim comments). Prose in docs is
  not used for counts.
- The jarvis repo is public. Operator statements are paraphrased. Quotes come only from agent-written,
  commit, issue or code text. Local journal lines are cited as machine-local sources without paths.

Sub-questions:
1. For each design: when was it active, what was built, how many real unattended runs did it make, why
   did it stop (with evidence), and what residue remains?
2. Which failure patterns repeat across designs? Each pattern needs at least two designs or is marked
   single-instance.
3. What preconditions must #1960 check before it approves any new infrastructure?
4. What can be reconstructed of the lost M70 `spec_locked.md`, and what cannot?

## Summary

Across eight designs (2026-04-08 to 2026-10-01), measured unattended output is concentrated in one design. Sandcastle claimed 88 jarvis issues; its claimed branches produced 61 PRs, 53 of them merged, plus 13 merged watchdog PRs and 158 redrobot claims. It kept running until the stack it lived in was demolished [C20][C21][C23][C27]. Two designs were never proven unattended at all. Pillar 7's three
dispatches were each rescued by hand [C10][C11]. The autonomous loop left one recorded live test; its
scheduled runs are not countable [C2][C3]. The rest stopped after a handful of runs. Ralph-loop had one validation run
[C31]. Reactive-core produced 20 PRs and had not cleared its own 5-completion ship gate when last recorded [C36][C37][C38]. The
current claude-code-action lane has 7 real runs and 3 merged PRs in four weeks [C55][C56][C57].

**No design was stopped by a measured failure verdict.** Each one was superseded or folded into the
next design's premise, usually before it had run at volume [C7][C15][C24][C33][C45]. The one design
with real volume, sandcastle, was removed in the #1802 demolition of the reactive-core stack
[C24][C27].

**Four patterns repeat across designs** [C64][C65][C66][C67], and one is single-instance [C68]; supersession, not these failures, ended most designs [C69]:
1. Infrastructure was built before the lane was proven at volume, and success gates were not recorded as cleared.
2. Local Windows runtimes failed silently.
3. Runs reported "done" with no artifact.
4. Admission and review gates failed open.
5. (Single-instance, design 1) Residue stayed running after its design stopped.

The recommendation is a set of preconditions that #1960 must check before approving any new
infrastructure (Q3). A 76-line copy of the lost M70 spec is recoverable from a session transcript; its
disposition files were not found [C61][C62].

## Findings

### Q1 — Per-design record — answered with a gap

| # | Design | Active | Real unattended runs (measured) | Stop reason (one line) | Residue |
|---|---|---|---|---|---|
| 1 | Autonomous loop v1 | 2026-04-08 → cron removed 2026-05-26 (skill deleted 2026-08-08) | not countable: one recorded live test (#133), no run trace; event-dispatch forwards are not agent runs | superseded by reactive-core; time-triggered pacing judged wrong | design doc; event-dispatch ran until 2026-09-07 |
| 2 | Pillar 7 LangGraph | 2026-04-15 → 2026-04-25 (retired 05-24..07-08) | 0 fully unattended; 3 smoke dispatches (#400/#402/#404), each needing manual help | runtime could not run `claude` as a service; superseded by reactive-core | perception.md trace, task_queue migrations |
| 3 | Sandcastle | 2026-05-07 → 2026-09-09 (demolition PR #1868 merged) | 97 claims on 88 issues (jarvis); 53 merged PRs from claimed branches; 13 watchdog PRs; redrobot 158 claims | demolished with the reactive-core stack (#1802), output tapering | design doc, migrations, labels |
| 4 | ralph-loop | 2026-08-07 → 2026-08-08 | 1 validation run | superseded by reactive-core Path B within a day | reference doc |
| 5 | Reactive-core (M44) | 2026-05-21 → 2026-09-09 | 20 `task/<uuid>` PRs, 16 merged (2026-08-12..19) | 5-completion ship gate not recorded as cleared; demolished in #1802 | Wake-Driver task left running; heartbeat polling |
| 6 | Convergence (M58) | 2026-07-07 → 2026-09-09 | 3 `task/jarvis-worker-*` PRs, 2 merged | demolished in #1802; 9 of 23 issues closed not-planned | out-of-scope note |
| 7 | Plan-review (M68) | 2026-08-24 → 2026-10-01 | not an agent lane; its CI gate ran 141 times, 16 failures | gate deleted in the 13-workflow cleanup; class-2 gate left unenforced | 6 `agents/plan_*` modules, config, script |
| 8 | Rebuild on claude-code-action (M70) | 2026-09-08 → open | 7 (jarvis 2, jarvis-oss 5); 3 merged PRs | not stopped; the 10-run quota baseline never reached | the lane itself |

**Design 1 — autonomous loop v1**

- **C1** [quoted] The setup-tasks table registered the loop as a daily cron job (`3 9 * * *`). — "| `autonomous-loop` | `3 9 * * *` | Daily orchestrator: load perception, score actions, execute within safety bounds |" — [S3], setup-tasks table
- **C2** [quoted] Its milestone description rates it about 90% done, with live validation still outstanding. — "~90% done — needs live validation and stabilization." — [S1], milestone description
- **C3** [quoted] A live test of a full perceive→evaluate→decide→act→record cycle is recorded on issue #133. — "**Live test passed** — full perceive→evaluate→decide→act→record cycle:" — [S2], issue body
- **C4** [measured] event-dispatch.yml ran 7,440 times between 2026-04-08 and 2026-09-07: 1,687 success, 5,735 skipped, 17 failure, 1 startup_failure. 292 of the successes fall before 2026-05-05. Each run is a webhook forwarder, not an agent run. — see Own measurements M1
- **C5** [quoted] The forwarder wrote events into a database table for the orchestrator to read. — "# Captures critical GitHub events and writes them to Supabase events table." — [S4], file header
- **C6** [quoted] The consumer of those events died on 2026-05-04. — "its consumer died 2026-05-04" — [S7], issue body
- **C7** [quoted] The daily cron was removed because time-triggered pacing was judged wrong. — "Even pre-M44 ship, the daily cron is no longer the right pacing primitive — work is event-triggered, not time-triggered." — [S5], commit message
- **C8** [quoted] The skill was deleted once reactive-core shipped. — "M44 has now fully shipped (#1390/#1391/#1392/#1393 merged), so the skill has no live callers left." — [S6], commit message

**Design 2 — Pillar 7 LangGraph**

- **C9** [quoted] The goal was a no-human dispatch path from a message to a merged PR. — "produces a row that flows all the way through the existing dispatcher → safety gate → claude -p → PR → merge, with no human in the loop except the initial message." — [S9], issue body
- **C10** [quoted] The NSSM service ran as LocalSystem, which had no access to the user profile holding the `claude` credentials. — "NSSM service runs as `LocalSystem`, which has no access to the user profile where `claude` stores Max session creds." — [S10], smoke-test trace
- **C11** [quoted] Rows were closed by hand after the PRs merged. — "The orchestrator manually flipped each row to `done` after merging the resulting PR." — [S10], smoke-test trace
- **C12** [quoted] The service reported Running while crashing in a loop. — "produced a service that **NSSM reported `Running`** while the wrapped Python crashed every ~5s in an auto-restart loop." — [S11], issue body
- **C13** [quoted] Dispatch recorded success while no PR was ever opened. — "Net effect: rows transition `pending → dispatched` (audit_log records `outcome=success`), but no PR is ever opened" — [S12], issue body
- **C14** [quoted] The task queue held only three disposable smoke rows when reactive-core was planned. — "the TASK queue table exists but is empty of real data (`task_queue`, 3 disposable smoke rows) and is reshaped" — [S8], milestone description
- **C15** [quoted] The Pillar-7 scaffolding was retired under reactive-core's reversed premise. — "the Pillar-7 LangGraph/APScheduler scaffolding (`scheduler.py`, dispatcher graph, `event_monitor.py`, `main.py`) is dead under the reversed premise and is retired" — [S8], milestone description
- **C16** [quoted] The scheduler module and its service installer were removed on 2026-05-31. — "Retire: agents/scheduler.py + apscheduler/sqlalchemy deps + install-scheduler-service.ps1" — [S13], commit message
- **C17** [measured] The three Pillar-7 smoke dispatches are PRs #400, #402 and #404, all on `smoke/*` branches, opened 2026-04-25. — see Own measurements M5

**Design 3 — sandcastle**

- **C18** [quoted] Sandcastle containers picked labelled issues and opened PRs without merging. — "Containers pick issues labelled `sandcastle` from the queue, work on one issue per iteration, **open PRs but never merge**." — [S17], issue body
- **C20** [measured] In jarvis there are 97 such claim comments on 88 issues, from 2026-05-14 to 2026-09-02, by month May 48 / Jun 16 / Jul 19 / Aug 6 / Sep 8. 69 name a branch (65 unique); 61 of those branches have a PR: 53 merged, 8 closed. — see Own measurements M4
- **C21** [measured] In redrobot there are 158 claim comments on 133 issues from 2026-05-18 to 2026-08-07. — see Own measurements M4
- **C22** [quoted] The sandcastle watchdog named each run `<repo>-watchdog-<stamp>`, the same stem as the `task/jarvis-watchdog-*` branches measured in M5. — "$Repo-watchdog-$stamp" — [S49], line 1213
- **C23** [measured] 13 `task/jarvis-watchdog-*` PRs, all merged, 2026-07-09..2026-08-07. — see Own measurements M5
- **C24** [quoted] The #1802 demolition was widened to cascade the deletion to the entire reactive-core agent stack. — "cascade the deletion to the entire reactive-core agent stack rather than leaving it half-demolished" — [S23], commit message
- **C25** [quoted] A claim could produce nothing at all. — "The 2026-07-31 \"Claimed by sandcastle agent.\" comment produced no branch, no PR, no assignee" — [S21], issue body
- **C26** [quoted] A run that exited cleanly with zero commits left the issue claimed forever with no requeue and no alert (fixed in #1785). — "leaving the GitHub issue claimed forever with no requeue and no Telegram alert" — [S22], commit message
- **C27** [inference] Sandcastle's claim volume fell from 48 in May to 6 in August (8 in September) before it was deleted in the #1802 demolition. — from [C20], [C24]
- **C28** [quoted] Running on a Windows host broke the container's git worktree path. — "[sandcastle] Windows host: git worktree .git path unresolvable inside Linux container" — [S18], issue title
- **C29** [quoted] The admission gate failed open: plan-class issues were indistinguishable in the pick queue for two weeks. — "every class-2 issue was indistinguishable from class-1 in the sandcastle pick queue since #1707 merged (2026-08-25)" — [S50], line 42
- **C30** [quoted] redrobot deleted its sandcastle runtime directory as well. — "Deleted `.sandcastle/` (jarvis epic #534 / slice #546 AFK auto-pickup runtime)" — [S24], PR body

**Design 4 — ralph-loop**

- **C31** [quoted] The loop held up under one validation run. — "held up under one real validation run (task: jarvis#1455, needs-grill," — [S26], line 41
- **C32** [quoted] A benign hook warning killed the driver mid-iteration. — "A benign `SessionEnd hook ... failed` warning killed the driver mid-iteration - after the child had done 9 minutes of good work" — [S27], commit message
- **C33** [quoted] It was retired as a manual imitation of what reactive-core's Path B is built to solve. — "a manual imitation of exactly what reactive core's Path B (park on blocked_by_task_id, event wakes the task) is built to solve" — [S27], commit message
- **C34** [quoted] The retirement date and successor. — "Retired 2026-08-08 in favor of the reactive-core orchestrator (M44," — [S26], line 5
- **C35** [measured] Issue #1461 was opened 2026-08-07T19:18Z and PR #1463 merged 23:03Z the same day. — see Own measurements M6

**Design 5 — reactive-core (M44)**

- **C36** [measured] 20 PRs on `task/<uuid>` branches, 16 merged and 4 closed (#1562, #1563, #1603, #1653), created 2026-08-12..2026-08-19. — see Own measurements M5
- **C37** [quoted] The ship gate required 5 clean executor completions counted from 2026-08-10. — "keeps `status:owner-queue` on issue #1085 until **5 clean executor completions**, counted cumulatively from **2026-08-10**, are observed." — [S28], ship-gate rule
- **C38** [quoted] As of the last status recorded on #1085, the gate had not cleared. — "hasn't had time to clear yet" — [S29], issue body
- **C39** [quoted] The executor named its branches `task/<task id>`, matching the measured PR branches. — "task/{task_id}" — [S31], line 104
- **C40** [quoted] A stale resident process broke re-dispatch. — "Root-caused the r4 re-dispatch failure to a stale resident wake_driver process" — [S51], line 46
- **C41** [quoted] Queue rows for #1123/#1124 showed done with no artifact. — "showed status=done with no PR/branch/comment" — [S51], line 56
- **C42** [quoted] On 2026-09-08 the Windows Scheduled Task `Wake-Driver` was found still running. — "Windows Scheduled Task `Wake-Driver` (`State: Running`)" — [S50], line 20
- **C43** [quoted] Heartbeat polling of the queue was still active. — "sandcastle task-dispatcher/`agents/driver_heartbeat.py` still polling `task_queue`/`rpc/driver_heartbeat_tick`/`audit_log` every ~5min" — [S50], line 24
- **C44** [quoted] The demolition asked for a rebuild from scratch on native primitives. — "Issue #1802 asked to rebuild the agent system from scratch (Telegram now via the official Channels plugin, memory now native/file-based)." — [S35], PR body

**Design 6 — convergence (M58)**

- **C45** [measured] Milestone 58 closed 23 issues: 14 completed, 9 not-planned (#959, #1123, #1124, #1125, #1619, #1623, #1651, #1759, #1788). — see Own measurements M7
- **C46** [quoted] Unattended work refused protected-file scope and handed it back. — "**Sandcastle agent — refusing to owner queue (protected-file scope + shared-surface reshape).**" — [S33], issue comment
- **C47** [quoted] A container lost its memory server. — "The MCP memory server failed to connect (`CONNECTION_CLOSED`) for this container" — [S34], issue body
- **C48** [quoted] Open M58 items were closed as obsolete by the rebuild. — "Closing as **obsolete**: what this issue targets was retired in the milestone #70 native rebuild (Supabase stopped per decision F1;" — [S36], issue comment
- **C49** [measured] 3 `task/jarvis-worker-*` PRs (#1768, #1769, #1771), 2 merged. — see Own measurements M5

**Design 7 — plan-review (M68)**

- **C50** [quoted] The milestone's motivating incident. — "the PR #963 incident cost 5 rework rounds, 23 comments, 17 days" — [S38], milestone description
- **C51** [measured] plan-review-diff-gate ran 141 times from 2026-08-24 to 2026-09-07: 123 success, 16 failure, 1 cancelled, 1 startup_failure. — see Own measurements M2
- **C52** [quoted] The CI gate checked only that a lock was valid, not that critics agreed. — "`scripts/plan_review_diff_gate.py`'s `evaluate()` only calls `verify_lock(issue_body)` — a syntactically valid, hash-locked `## Plan` section — it never checks for critic-panel consensus" — [S50], line 44
- **C53** [quoted] The gate workflow was deleted in a bulk cleanup. — "Deleted 13 workflows superseded by #1816's two-layer code-gate" — [S39], PR body
- **C54** [quoted] The class-2 plan gate is not enforced anywhere. — "The class-2 (`afk:2-plan`) plan gate is not enforced anywhere." — [S41], issue body

**Design 8 — rebuild on claude-code-action (M70)**

- **C55** [measured] jarvis agent-dispatch: 320 runs, 264 skipped, 54 cancelled, 1 success, 1 failure. Both real runs are on 2026-09-08 and none since. — see Own measurements M3
- **C56** [measured] jarvis-oss agent-dispatch: 237 runs, 217 skipped, 15 cancelled, 3 success, 2 failure. All 5 real runs are on 2026-09-22 between 09:23Z and 09:52Z. — see Own measurements M3
- **C57** [measured] The 7 real runs produced 3 merged PRs (jarvis #1845, #1855; jarvis-oss #119). The two jarvis-oss issues the lane did not finish (#101 hit the turn limit, #102 stopped as blocked) were merged the same day through PRs whose commits postdate the runs. Logged model cost totals about $16, of which one run that hit the 100-turn limit cost $10.88. — see Own measurements M3, M8
- **C58** [measured] Run 34197144614 was marked failed after a successful result, because it exceeded max-turns; its PR #1845 still merged. Log line: "Claude reported a successful result after 51 turns, exceeding the configured maximum of 40". — see Own measurements M3, M8
- **C59** [quoted] Issue #1936 traced the cancellations to the workflow-level concurrency group, which is resolved before the job `if`. — "Workflow-level concurrency is resolved when the run is queued, before any job `if` is evaluated." — [S45], issue body
- **C60** [quoted] The jarvis-oss lane forked toward human merge. — "**No auto-merge.** The worker opens a PR and stops; the human merges (#38, #99)." — [S46], PR body

### Q2 — Failure patterns across designs — answered

- **C64** [inference] **Built before proven at volume; success gates not recorded as cleared** (designs 1, 2, 5, 8). Design 1 closed "needs live validation" [C2]; design 2 had three smoke rows [C14]; design 5's 5-completion gate had not cleared at its last recorded status [C37][C38]; design 8 has 7 real runs and has not run its 10-run baseline [C55][C56]. — from [C2], [C14], [C37], [C38], [C55], [C56]
- **C65** [inference] **Local Windows runtime failed silently** (designs 2, 3, 4, 5). Service account without credentials and a "Running" service crash-looping [C10][C12]; a Windows host path that broke inside the container [C28]; a hook warning killing the driver [C32]; a stale resident process and a scheduled task left running [C40][C42]. — from [C10], [C12], [C28], [C32], [C40], [C42]
- **C66** [inference] **"Done" with no artifact** (designs 2, 3, 5; inverted in 8). Success recorded with no PR [C13]; claims producing nothing and never requeued [C25][C26]; queue rows marked done with no branch [C41]. Design 8 shows the inverse: a run that produced a merged PR was marked failed [C58]. — from [C13], [C25], [C26], [C41], [C58]
- **C67** [inference] **Gates that failed open** (designs 3/6 admission, 7 plan gate). A plan-class label that did not exist let class-2 work into the pick queue [C29]; the plan gate verified a lock, not consensus [C52]; the class-2 gate is now enforced nowhere [C54]. — from [C29], [C52], [C54]
- **C68** [inference] **Residue outlived the design** (single-instance, design 1). event-dispatch ran until 2026-09-07, months after its consumer died 2026-05-04 [C4][C6]. — from [C4], [C6]
- **C69** [inference] **Supersession, not failure, ended designs** (designs 1, 2, 4 → 5; 3, 5, 6 → 8). Each stop cites a new premise rather than a measured verdict on the old lane [C7][C15][C33][C24][C44]. — from [C7], [C15], [C24], [C33], [C44]

### Q3 — Preconditions for #1960 — answered

Derived from Q2. Each one is a check #1960 runs before it approves new infrastructure, not a design
choice.

- **C71** [inference] **Volume gate.** Before any new infrastructure, the current lane (design 8) must reach a stated number of real unattended runs with a recorded outcome per run; the existing 10-run baseline (#1809) is the natural first threshold. Rationale: four designs were replaced before reaching volume. — from [C64], [C69]
- **C72** [inference] **Success is an artifact check.** Any "done" state must be verified from the artifact (PR exists, CI result), never from the runner's own report, in both directions. — from [C66]
- **C73** [inference] **No local resident runtime without a liveness signal visible off-machine.** A local daemon, service or scheduled task must surface its own failure where the operator looks; otherwise run on hosted runners. — from [C65]
- **C74** [inference] **Gates must fail closed and be tested against a missing input** (a label that does not exist, a check that cannot run). — from [C67]
- **C75** [inference] **Retirement includes a stop step.** Every superseded design's scheduled tasks, workflows and polling must be listed and stopped when it is retired, with a check that they no longer run. This rests on a single instance (design 1's event-dispatch). — from [C68]
- **C76** [inference] **A new premise must name the measured shortfall of the lane it replaces.** "Supersede" without a measured verdict on the current lane is the recurring stop reason, and it reset the run count each time. — from [C69]

### Q4 — The lost M70 `spec_locked.md` — answered with a gap

- **C61** [quoted] A copy of the spec was recovered from a session transcript (a Write call on 2026-09-06, 76 lines). Its core decision reads: — "Unattended-воркер = claude-code-action по метке issue, PAT во входе github_token, чтобы пуши воркера запускали CI и auto-merge (Q4=a)." — [S53], line 12
- **C62** [quoted] The spec's follow-up (Phase 6) and known-limitations sections are recoverable; the latter includes the label rule: — "issue-checks ставит метки ботом — воркер триггерится только человеческой меткой" — [S53], line 76
- **C63** [quoted] Spec acceptance criterion AC-4.1 called for per-issue `concurrency` with cancel-in-progress. — "`concurrency` по issue с cancel-in-progress" — [S53], AC-4.1

Not recoverable: the per-question disposition files (`dispositions_r*.md`, 192 dispositions). No copy was
found in the transcript or the repo. One spec item has since been reversed: AC-1.3 (archive
jarvis-oss) was overturned on 2026-09-12 when jarvis-oss became a docs and examples repo.

## Disconfirming evidence

- **Sandcastle had real volume.** Design 3 merged 53 PRs from claimed branches in jarvis plus 13 watchdog
  PRs, and redrobot took 158 claims [C20][C21][C23]. "Built before proven at volume" does not describe
  it. It is the counter-example: the one lane that reached volume was removed in the #1802 demolition
  of the whole reactive-core stack [C24][C27]. The precondition list keeps that in view (C76).
- **Stop reasons were strategic, not failure verdicts.** None of the stop sources records a measured
  verdict that a lane did not work [C69]. The failures in Q2 are documented incidents, not proven
  causes of any stop. The report does not claim that they caused the stops.
- **Design 8 is not stopped.** Its low run count reflects few labelled issues, not a lane that ran and
  failed [C55][C56].

## Coverage

- Sources read: milestones 14, 20, 31, 32, 38, 41, 44, 58, 68, 70, 71; about 40 issues and PRs; commit
  messages at the cited SHAs; raw files at cited SHAs; Actions run lists for event-dispatch,
  plan-review-diff-gate and agent-dispatch (jarvis and jarvis-oss); run logs of all 7 real design-8 runs;
  the operator's machine-local decision journal and its 2026-09-06 recovery file; one session
  transcript for the spec.
- The handoff (2026-10-01) gave 222 skipped agent-dispatch runs; the count on 2026-10-06 is 264. Counts here are as
  of 2026-10-06.
- Not available: the Supabase `task_queue` and `audit_log` tables (Supabase is stopped), so the
  reactive-core and Pillar 7 counts rest on PR branches only.

## Own measurements

**M1 — event-dispatch runs** (design 1)

```
gh api "repos/Osasuwu/jarvis/actions/workflows/event-dispatch.yml/runs?per_page=1" --jq .total_count
7440
gh api --paginate "repos/Osasuwu/jarvis/actions/workflows/event-dispatch.yml/runs?per_page=100" \
  --jq '.workflow_runs[]|[.created_at,.event,.conclusion]|@tsv' > edruns.tsv
cut -f3 edruns.tsv | sort | uniq -c
     17 failure
   5735 skipped
      1 startup_failure
   1687 success
cut -f1 edruns.tsv | sort | sed -n '1p;$p'
2026-04-08T09:48:23Z
2026-09-07T18:11:14Z
awk -F'\t' '$3=="success" && $1<"2026-05-05"' edruns.tsv | wc -l
292
```

**M2 — plan-review-diff-gate runs** (design 7)

```
gh api --paginate "repos/Osasuwu/jarvis/actions/workflows/plan-review-diff-gate.yml/runs?per_page=100" \
  --jq '.workflow_runs[] | [.created_at,.conclusion]|@tsv' > prdg.tsv
cut -f2 prdg.tsv | sort | uniq -c
      1 cancelled
     16 failure
      1 startup_failure
    123 success
cut -f1 prdg.tsv | sort | sed -n '1p;$p'
2026-08-24T18:37:59Z
2026-09-07T17:55:34Z
```

**M3 — agent-dispatch runs** (design 8)

```
for r in Osasuwu/jarvis Osasuwu/jarvis-oss; do
  gh api --paginate "repos/$r/actions/workflows/agent-dispatch.yml/runs?per_page=100" --jq '.workflow_runs[] | .conclusion' | sort | uniq -c
done
== Osasuwu/jarvis
     54 cancelled
      1 failure
    264 skipped
      1 success
== Osasuwu/jarvis-oss
     15 cancelled
      2 failure
    217 skipped
      3 success

# real runs (success or failure)
== Osasuwu/jarvis
34207276184	2026-09-08T08:56:49Z	success	issues
34197144614	2026-09-08T06:59:24Z	failure	issues
== Osasuwu/jarvis-oss
35712788633	2026-09-22T09:51:55Z	success	issues
35710996155	2026-09-22T09:32:47Z	success	issues
35710992984	2026-09-22T09:32:45Z	failure	issues
35710710890	2026-09-22T09:29:51Z	success	issues
35710146847	2026-09-22T09:23:56Z	failure	issues

gh pr view <n> --json number,state,mergedAt,headRefName
1845 MERGED 2026-09-08T07:03:54Z claude/issue-1844-context-readiness-axis-sync
1855 MERGED 2026-09-08T09:03:21Z claude/issue-1854-dev-process-details-install-ps1
oss 119 MERGED 2026-09-22T09:46:04Z claude/issue-103-doc-error-reader-channel
```

Run → issue (from `gh api repos/<r>/actions/runs/<id> --jq .display_title`) and outcome:

```
34197144614 failure  jarvis #1844 -> PR #1845 merged
34207276184 success  jarvis #1854 -> PR #1855 merged
35710146847 failure  oss #103 "Reader channel..." (PAT permission error)
35710710890 success  oss #103 -> PR #119 merged (created 2026-09-22T09:34:35Z)
35710992984 failure  oss #101 "Agent review: calibration corpus..." (100-turn limit; run ended 09:46:40Z)
35710996155 success  oss #102 "review-doc: blocking per the negative guarantee..." (no PR)
35712788633 success  oss #102 (no PR; posted a blocked comment)

gh api repos/Osasuwu/jarvis-oss/pulls/<n>/commits --jq '.[].commit.author.date'
PR #126 (claude/issue-101-corpus): first commit 2026-09-22T10:17:22Z, merged 11:22:37Z
PR #130 (claude/issue-102-review-doc-reconcile): commit 2026-09-22T11:30:24Z, merged 11:32:36Z
```

3 of the 7 real runs produced a merged PR. Issues #101 and #102 were finished outside the lane after their runs ended.

**M4 — sandcastle claim comments** (design 3)

```
gh search issues --repo Osasuwu/jarvis '"Claimed by sandcastle agent"'   # 92 candidates
# then per issue: gh api repos/Osasuwu/jarvis/issues/<n>/comments, keep bodies starting "Claimed by sandcastle agent."
wc -l < claims_strict.txt                        -> 97
cut -d' ' -f1 claims_strict.txt | sort -u | wc -l  -> 88
first / last                                     -> 2026-05-14T07:45:14Z / 2026-09-02T14:43:52Z
by month: 48 2026-05, 16 2026-06, 19 2026-07, 6 2026-08, 8 2026-09
claims naming a branch: 69; unique branches: 65; with a PR: 61 (53 merged, 8 closed)
redrobot (same method, search limit 200): 158 claim comments on 133 issues, 2026-05-18..2026-08-07
```

**M5 — PRs by head-branch fingerprint**

```
gh pr list --repo Osasuwu/jarvis --state all --limit 2000 --json number,headRefName,createdAt,mergedAt > prs2.json  # 893 PRs
task/<uuid>            : 20 PRs, 16 merged, 2026-08-12..2026-08-19; closed unmerged [1562, 1563, 1603, 1653]
task/jarvis-worker-*   : 3 PRs [1768, 1769, 1771], 2 merged
task/jarvis-watchdog-* : 13 PRs, 13 merged, #1173 (2026-07-09) .. #1432 (2026-08-07)
smoke/*                : #400, #402, #404 (2026-04-25)
```

**M6 — ralph-loop timing**

```
gh issue view 1461 --json createdAt   -> 2026-08-07T19:18Z
gh pr view 1463 --json createdAt,mergedAt -> created 2026-08-07T20:04:50Z, merged 2026-08-07T23:03:23Z
```

**M7 — milestones**

```
gh api repos/Osasuwu/jarvis/milestones/<n> --jq '"\(.number) | \(.title) | created \(.created_at[:10]) | closed \(.closed_at // "open" | .[:10]) | open \(.open_issues) closed \(.closed_issues)"'
14 | Autonomous Loop v1 | created 2026-04-13 | closed 2026-04-17 | open 1 closed 4
20 | Pillar 7 Sprint 1: LangGraph + Ollama foundation | created 2026-04-17 | closed 2026-04-17 | open 0 closed 12
31 | Pillar 7 Sprint 3: dispatcher in prod | created 2026-04-25 | closed 2026-04-25 | open 0 closed 4
32 | Pillar 7 Sprint 4: perception → task_queue ingest | created 2026-04-25 | closed 2026-04-25 | open 0 closed 6
38 | Sandcastle integration | created 2026-05-08 | closed 2026-05-17 | open 0 closed 12
41 | AFK PR-rework loop | created 2026-05-14 | closed 2026-05-26 | open 0 closed 10
44 | Reactive-core: event-woken orchestrator + durable queues | created 2026-05-21 | closed 2026-08-08 | open 0 closed 39
58 | Executor→sandcastle convergence | created 2026-07-07 | closed 2026-09-24 | open 0 closed 23
68 | Plan-review stage | created 2026-08-24 | closed 2026-10-01 | open 0 closed 15
70 | Rebuild: native Claude Code | created 2026-09-06 | closed open | open 1 closed 50
71 | AFK orchestration | created 2026-10-01 | closed open | open 14 closed 0

gh issue list --milestone "Executor→sandcastle convergence" --state closed --json number,stateReason
COMPLETED 14 [1777,1775,1774,1617,1491,1403,1383,1382,1133,1122,1121,1120,1119,1118]
NOT_PLANNED 9 [1788,1759,1651,1623,1619,1125,1124,1123,959]
```

**M8 — design-8 run logs** (`gh run view <id> --log`, grep for turns, cost, error)

```
run 34197144614 (jarvis):  "num_turns": 51   "total_cost_usd": 0.8178   "exceeding the configured maximum of 40"
run 34207276184 (jarvis):  "num_turns": 39   "total_cost_usd": 0.5149
run 35710146847 (oss):     "Resource not accessible by personal access token"
run 35710710890 (oss):     "num_turns": 71   "total_cost_usd": 1.3092
run 35710992984 (oss):     "num_turns": 101  "total_cost_usd": 10.8767  "Reached maximum number of turns (100)"
run 35710996155 (oss):     "num_turns": 42   "total_cost_usd": 0.8891
run 35712788633 (oss):     "num_turns": 63   "total_cost_usd": 1.5857
sum of total_cost_usd: 15.99
```

**M9 — plan-class label existence**

```
gh label list --repo Osasuwu/jarvis --search afk --json name,createdAt
afk:2-plan 2026-09-08T10:40:07Z
afk:3-human 2026-09-08T10:40:08Z
```

## Open questions

- Design 1's real unattended run count is not countable: no run trace survives, and the orchestration
  table (Supabase) is stopped. Restoring a Supabase dump of `task_queue`/`audit_log`/`events` would
  settle it for designs 1, 2 and 5.
- The 192 spec dispositions (`dispositions_r*.md`) are lost. Only a backup of the 2026-09-06 grill
  session's working directory, if one exists on another device, could recover them.
- Why the jarvis-oss lane ran nothing between 2026-09-15 and 2026-09-22 is not verified; its run list
  shows only skipped and cancelled runs in that window.
- Q1 gap: whether reactive-core's 5-completion ship gate ever cleared is not settled. The last recorded
  status on #1085 says it had not, yet 16 `task/<uuid>` PRs merged 2026-08-12..19. Later #1085 comments or a
  `task_queue` dump with per-task outcomes from 2026-08-10 on would settle it. If it cleared, pattern 1 loses
  design 5.
- Q1 gap: the cause of the #1123/#1124 done-with-no-artifact rows and of the stale wake_driver re-dispatch
  failure rests on two journal-recovery lines that are truncated mid-sentence ([S51] lines 46, 56); the full
  original entries would settle it.
- Q1 gap: M5 does not show that the `task/jarvis-worker-*` PRs (design 6) are sandcastle output or overlap
  design 3's claim count; matching their head branches against the M4 claim-comment branch list would settle it.
- Q4 gap: the recovered spec is the single Write of `spec_locked.md` at 2026-09-06T11:10Z in one transcript;
  whether a later locked revision exists in another session is not checked, and the "192 dispositions" count
  has no cited source. A search of the other 2026-09-06..08 transcripts for `spec_locked` would settle both.

## Sources

- [S1] https://github.com/Osasuwu/jarvis/milestone/14
- [S2] https://github.com/Osasuwu/jarvis/issues/133
- [S3] https://raw.githubusercontent.com/Osasuwu/jarvis/44baf9a0e996bb79b07881fd7765303c6d02dfd2/.claude/skills/setup-tasks/SKILL.md
- [S4] https://raw.githubusercontent.com/Osasuwu/jarvis/44baf9a0e996bb79b07881fd7765303c6d02dfd2/.github/workflows/event-dispatch.yml
- [S5] https://github.com/Osasuwu/jarvis/commit/a2b108741787feb9a0c4966fe10003398e828b35
- [S6] https://github.com/Osasuwu/jarvis/commit/961aae13a147f9f01bd2e81d12f0b0ed1b97d803
- [S7] https://github.com/Osasuwu/jarvis/issues/739
- [S8] https://github.com/Osasuwu/jarvis/milestone/44
- [S9] https://github.com/Osasuwu/jarvis/issues/390
- [S10] https://raw.githubusercontent.com/Osasuwu/jarvis/24529d835bcc374f1e001317f6c8c98a897a22ec/docs/agents/perception.md
- [S11] https://github.com/Osasuwu/jarvis/issues/394
- [S12] https://github.com/Osasuwu/jarvis/issues/407
- [S13] https://github.com/Osasuwu/jarvis/commit/ca0f8c64e03c6c344637ff9049f2bc835c45c5e9
- [S17] https://github.com/Osasuwu/jarvis/issues/534
- [S18] https://github.com/Osasuwu/jarvis/issues/607
- [S21] https://github.com/Osasuwu/jarvis/issues/1324
- [S22] https://github.com/Osasuwu/jarvis/commit/5509f1369923dd53460d74bf9c10206d5812c302
- [S23] https://github.com/Osasuwu/jarvis/commit/103d2ead8bb6949803a5eb135322c44fc381ef1e
- [S24] https://github.com/SergazyNarynov/redrobot/pull/2169
- [S26] https://raw.githubusercontent.com/Osasuwu/jarvis/c6c848f/docs/reference/ralph-loop.md
- [S27] https://github.com/Osasuwu/jarvis/commit/96dd4cb585349ebb38e954d8e7fd869ce0590ada
- [S28] https://raw.githubusercontent.com/Osasuwu/jarvis/c6c848f/docs/reference/dispatch-ship-gate.md
- [S29] https://github.com/Osasuwu/jarvis/issues/1085
- [S31] https://raw.githubusercontent.com/Osasuwu/jarvis/7fadc25105278270785853438756fc4bdfdcf7de/agents/task_worktree.py
- [S33] https://github.com/Osasuwu/jarvis/issues/1124
- [S34] https://github.com/Osasuwu/jarvis/issues/1623
- [S35] https://github.com/Osasuwu/jarvis/pull/1868
- [S36] https://github.com/Osasuwu/jarvis/issues/959
- [S38] https://github.com/Osasuwu/jarvis/milestone/68
- [S39] https://github.com/Osasuwu/jarvis/pull/1835
- [S41] https://github.com/Osasuwu/jarvis/issues/1918
- [S45] https://github.com/Osasuwu/jarvis/issues/1936
- [S46] https://github.com/Osasuwu/jarvis-oss/pull/113
- [S49] https://raw.githubusercontent.com/Osasuwu/jarvis/7fadc25105278270785853438756fc4bdfdcf7de/scripts/sandcastle/Run-Sandcastle.ps1
- [S50] decisions.md — operator decision journal, machine-local, not published
- [S51] decisions-raw-recovery-2026-09-06.txt — operator journal recovery file, machine-local, not published
- [S53] spec_locked.md recovered from a 2026-09-06 session transcript (Write call, 76 lines) — machine-local, not published

## Audit

| Claim | Verdict | Note |
|---|---|---|
| C1 | SUPPORTED |  |
| C2 | SUPPORTED |  |
| C3 | PARTIAL | quote present via the GitHub API (HTML render fails the quote check); #133 also says a scheduled task runs daily at 09:10; "only" and "attended" unsupported. Claim narrowed; Summary and table row adjusted |
| C4 | SUPPORTED |  |
| C5 | SUPPORTED |  |
| C6 | SUPPORTED |  |
| C7 | SUPPORTED |  |
| C8 | SUPPORTED | quote-check NOT FOUND on the rendered HTML (markdown/entities rendered); present verbatim in the raw text via the GitHub API |
| C9 | SUPPORTED |  |
| C10 | PARTIAL | quote states the LocalSystem/credentials fact only; "dispatch redone from a user shell" dropped |
| C11 | SUPPORTED |  |
| C12 | SUPPORTED |  |
| C13 | SUPPORTED | quote present; gh output escapes the backticks (\`), matched after unescaping |
| C14 | SUPPORTED |  |
| C15 | SUPPORTED |  |
| C16 | SUPPORTED |  |
| C17 | SUPPORTED |  |
| C18 | SUPPORTED |  |
| C20 | SUPPORTED |  |
| C21 | SUPPORTED |  |
| C22 | PARTIAL | quote is the watchdog run-name pattern `$Repo-watchdog-$stamp`; claim narrowed to the naming stem (PR #1173 branch is task/jarvis-watchdog-20260709-180001) |
| C23 | SUPPORTED |  |
| C24 | PARTIAL | quote says the demolition was widened to the whole reactive-core stack; sandcastle (`.sandcastle/`, `scripts/sandcastle/`, `sandcastle_supervisor.py`) was already in the locked plan's original scope, so "collateral" is unsupported. Claim, Summary and Disconfirming evidence narrowed |
| C25 | SUPPORTED | quote-check NOT FOUND on the rendered HTML (markdown/entities rendered); present verbatim in the raw text via the GitHub API |
| C26 | PARTIAL | commit describes one condition (clean exit, zero commits) and its fix (#1785); claim restored to that condition |
| C27 | PARTIAL | "only sustained volume of the eight" needs per-design claims it does not name; "no source records a failure verdict" is an absence the cited claims do not show. Narrowed to the tapering numbers and the demolition |
| C28 | SUPPORTED |  |
| C29 | SUPPORTED |  |
| C30 | SUPPORTED | page unfetchable by the quote check over plain HTTP; read via the `gh` API |
| C31 | SUPPORTED |  |
| C32 | SUPPORTED |  |
| C33 | PARTIAL | "the next day" unsupported: #1463 merged 2026-08-07, same day as #1461 opened (M6); dropped |
| C34 | SUPPORTED |  |
| C35 | SUPPORTED |  |
| C36 | SUPPORTED |  |
| C37 | SUPPORTED |  |
| C38 | SUPPORTED | quote-check NOT FOUND on the rendered HTML (markdown/entities rendered); present verbatim in the raw text via the GitHub API |
| C39 | SUPPORTED |  |
| C40 | SUPPORTED | [S51] line is truncated with "..." after the quoted span; quote itself present |
| C41 | SUPPORTED | [S51] line is truncated with "..." after the quoted span; quote itself present |
| C42 | PARTIAL | journal entry is dated 2026-09-08; demolition PR #1868 merged 2026-09-09, so "after the demolition" is wrong; dated instead |
| C43 | SUPPORTED |  |
| C44 | SUPPORTED |  |
| C45 | SUPPORTED |  |
| C46 | SUPPORTED | quote-check NOT FOUND on the rendered HTML (markdown/entities rendered); present verbatim in the raw text via the GitHub API |
| C47 | SUPPORTED | quote-check NOT FOUND on the rendered HTML (markdown/entities rendered); present verbatim in the raw text via the GitHub API |
| C48 | SUPPORTED | quote-check NOT FOUND on the rendered HTML (markdown/entities rendered); present verbatim in the raw text via the GitHub API |
| C49 | PARTIAL | M5 output shows neither the 2026-09-02 date nor sandcastle attribution/overlap; both dropped, table row adjusted |
| C50 | SUPPORTED |  |
| C51 | SUPPORTED |  |
| C52 | SUPPORTED |  |
| C53 | SUPPORTED | quote-check NOT FOUND on the rendered HTML (markdown/entities rendered); present verbatim in the raw text via the GitHub API |
| C54 | SUPPORTED |  |
| C55 | SUPPORTED |  |
| C56 | SUPPORTED |  |
| C57 | SUPPORTED |  |
| C58 | SUPPORTED |  |
| C59 | SUPPORTED |  |
| C60 | SUPPORTED | quote-check NOT FOUND on the rendered HTML (markdown/entities rendered); present verbatim in the raw text via the GitHub API |
| C61 | SUPPORTED | read from the transcript's Write call (2026-09-06T11:10:33Z), line 12 |
| C62 | PARTIAL | quote is the label rule only; the AC-6.x → #1808/#1809/#1810 mapping is not in it (states verified separately: 1808 closed 2026-10-06, 1809 and 1810 open). Mapping dropped |
| C63 | PARTIAL | quote is AC-4.1 text; "produced the cancellations" is not in it — #1936 traces them to the workflow-level placement. Narrowed to what AC-4.1 says |
| C64 | PARTIAL | C38 is a status two days into the gate window (2026-08-12) while 16 task/<uuid> PRs merged 08-12..19; "never cleared" → "not recorded as cleared" |
| C65 | SUPPORTED |  |
| C66 | SUPPORTED |  |
| C67 | SUPPORTED |  |
| C68 | PARTIAL | Wake-Driver (2026-09-08) and heartbeat polling predate demolition PR #1868 (2026-09-09), so they are not residue after stop; C54 does not show plan-review modules surviving. Narrowed to single-instance design 1; Summary item 5 adjusted |
| C69 | SUPPORTED |  |
| C70 | UNSUPPORTED | #1936 places the defect in the workflow-level concurrency placement and keeps per-issue cancel as intended, so the spec criterion is not shown to be the bug; "all 69" exceeds #1936's 53 traced jarvis cancellations (jarvis-oss's 15 untraced). Removed |
| C71 | SUPPORTED |  |
| C72 | SUPPORTED |  |
| C73 | SUPPORTED |  |
| C74 | SUPPORTED |  |
| C75 | PARTIAL | rests on C68, now single-instance; claim notes that |
| C76 | SUPPORTED |  |

Label verdict: open — the Summary's account of design 5 (ship gate not cleared) and design 1 (never proven unattended) rests on gapped Q1 evidence: if the reactive-core gate cleared on the 16 merged task PRs, or a task_queue dump shows design-1 unattended runs, the Summary and pattern 1 change; and Q4 has not ruled out a later spec revision.
Quote check: Quote check afk-orchestration-retrospective-2026-10-06.md: 47 quoted claim(s): 28 found, 9 NOT FOUND, 1 unfetchable, 9 no source
