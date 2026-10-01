# AFK orchestration — leftovers inventory (2026-10-01)

Read-only subagent inventory, verbatim except three redactions for publication (a local path, a private repo's details, a local key file). Spot-verified: agent-dispatch run counts (1 success, 1 failure, 54 cancelled, 222 skipped).

AFK/orchestration leftovers inventory, read-only, compiled 2026-10-01. No files, labels, comments or GitHub state were changed.

**Big gaps in the brief:**
- **Osasuwu/jarvis-oss** was not in the repo list, but it is an active public repo with its own forked lane: `agent-dispatch.yml`, `afk:*` labels and a live `status:owner-queue`.
- **~/.claude/scheduled-tasks** still holds orphaned AFK tick prompts.
- The **grill-rethink-0904 spec** (`spec_locked.md`), which issues #1808, #1809 and #1810 cite as their source, is not in any repo or under `~/.claude`.

---

## 1. Issue table

Status uses the brief's values. Most items are `live`; `stale` means the premise refers to a demolished mechanism, and `half-built` means code exists but is not wired in.

### Osasuwu/jarvis (all open)

| # | Title (short) | Labels | Milestone | Plan in one line | Status | Cluster |
|---|---|---|---|---|---|---|
| 1951 | Dispatch worker has no test toolchain | status:ready, afk:3-human | Agent-integrity | Install a pytest env in the agent-dispatch worker with no package-install grant; until then worker PRs get `waiting-human-review` | live | A Executor |
| 1941 | Research AFK lane: needs-research blocks /dispatch, executor can't research | needs-grill | Rebuild | 3 options: relax the /dispatch gate, route to claude-code-action, or a separate research issue + blocked_by edge | live | B Label contract |
| 1932 | Re-dispatch stops at preflight because the escalation owner-assignee is read as a claim | status:ready | Rebuild | Exempt the owner assignee in both preflights, or unassign it; one rule, plus a meta-test | live | A Executor |
| 1918 | Restore plan-review-diff-gate as a required check for afk:2-plan | status:ready | Plan-review stage | Re-add the workflow around the orphan `scripts/plan_review_diff_gate.py`. The AFK path either gets a planner or `/dispatch` refuses `afk:2-plan` | half-built | C Plan lane |
| 1573 | Plan-review stage in /implement and /task-implement | — | Plan-review stage | Class-2 planner + 2 critics + `## Plan` sha256 lock, drain plans in-tick, sandcastle admission | half-built (drain and sandcastle parts dead) | C Plan lane |
| 1681 | PreToolUse backstop for the interactive class-2 plan gate | status:ready | Agent-integrity | Hook that denies edits before the plan lock | half-built | C Plan lane |
| 1913 | Fate of the orphaned global-task advancer (#1802) | status:ready | Rebuild | Triage comment of 2026-09-24 says F1 implies drop: delete `scripts/advance-global-tasks.py` plus all Supabase residue | stale | E Dead-stack residue |
| 1810 | Worker token rotation: PAT until 2027-09-07, setup-token until 2027-09-08 | afk:3-human | Rebuild | Rotate both 7 days before expiry; covers jarvis and music-intel-mcp secrets | live (dormant until 2027) | A Executor |
| 1809 | Quota measurement after 10 unattended claude-code-action runs | afk:3-human | Rebuild | Quota before/after 10 runs, then decide `--max-turns` and run frequency | live; blocked in practice (see section 5) | A Executor |
| 1808 | 2026-10-06 checkpoint on native auto memory | afk:3-human | Rebuild | Record MEMORY.md size per device and give a verdict | live (due in 5 days) | F Rebuild follow-ups |
| 1894 | Audit: devs-agnostic form for single-developer mechanisms | status:ready, afk:2-plan | Methodology | Audit owner-assignee holds and similar mechanisms | live; `afk:2-plan` has no working plan lane | C / D |
| 1761 | weekly-release Step 5 notify no-ops outside wake_driver | — | Weekly releases | Notify depends on `wake_driver`, which #1802 deleted | stale | E |
| 1935 | code-review.yml: one shape across repos | needs-grill | Agent-integrity | Unify review workflows across jarvis, music-intel-mcp and like-current-song | live | D Merge gates |
| 1901 | code-review workflow_dispatch has no has_code gating | — | Agent-integrity | Gate manual review runs | live | D |
| 1880 | code-gate verdict regex needs a heading the prompt never asks for | — | Agent-integrity | Fix the parser | live | D |
| 1872 | code-gate fails closed when the reviewer legitimately skips | — | Agent-integrity | Handle the skip case | live | D |
| 1782 | Review gate deadlocks docs-only PRs (high) | — | Agent-integrity | Fix the has_code / docs deadlock | live | D |
| 1550 | Review gate: stale-content freshness check uses timestamp only | — | — | Check content freshness | live | D |
| 1178 | PR Body Check misses bundled slices | — | Agent-integrity | Orphaned open issues result | live | D |
| 1168 | Extract code-review verdict logic into a script | — | — | Refactor | live | D |
| 1075 | Verdict parser should fail closed on title-case headings | — | Agent-integrity | Parser fix | live | D |
| 1073 | Substantive-diff extension gap lets non-allowlisted files merge unreviewed | — | Agent-integrity | Possible fail-open gate | live | D |
| 1023 | Guard superseded-sibling Closes refs | — | — | CI guard | live | D |
| 1076 | Protected-paths enforcement bypassable via Bash; hooks absent on some devices | needs-grill | Agent-integrity | Enforcement design | live | D |
| 1926 | PreToolUse deny `gh pr merge --delete-branch` on a stack root | status:ready | Agent-integrity | Hook | live | D |
| 1911 | ruff CI gate | status:ready | Framework substrate | Add the gate | live | D |
| 1948 | Test-quality gates for defect classes no rule can hold | needs-grill | Agent-integrity | Gate design | live | G Test quality |
| 1945 | Test-suite follow-ups; diff-mutation-probe unwired | status:ready | Agent-integrity | Wire the probe, fix weak oracles | half-built | G |
| 1944 | Mirror tests (~240 items test a Python copy) | needs-grill | Agent-integrity | Rewrite approach | live | G |
| 1693 | Weak-assert lint | — | Methodology | Report-only AST check | live | G |
| 1317 | Gate the test diff separately from the code diff in /implement and /rework | status:ready | Methodology | `/rework` no longer exists | partly stale | G |
| 1672 | research: defect class the agent-authored verification stack cannot catch | needs-research | Methodology | One of the 4 `needs-research` issues #1941 cites | live | B |
| 1938 | Compare /research backends | — | Methodology | Firecrawl vs built-in search/fetch | live | H Research |
| 1939 | Research-pass gates must check audit/status, not file existence | — | Agent-integrity | Consumer gate | live | H |
| 1940 | Deterministic quote-in-source check | — | Agent-integrity | Experiment; jarvis-oss already ships `check_quotes.py` and `quote-cron` | live / overlap | H |
| 1925 | Post-compaction premise reminder hook | status:ready | Agent-integrity | Hook | live | I Interactive harness |
| 1478, 1374, 1336, 1320, 1319, 1318, 1264, 1161 | grill/methodology/harness items | various | Methodology / — | Not orchestration | live | I |

### Osasuwu/music-intel-mcp (open)

| # | Title | Labels | Milestone | Status | Cluster |
|---|---|---|---|---|---|
| 226 | verify-verdict passes green with no review when claude-code-action skips (high) | status:owner-queue | Agent-config & secret hygiene | live **fail-open gate**; same class as jarvis#1236 (closed) | D |
| 233 | Pin workflow actions to commit SHAs | status:ready | same | live | D |
| 232 | Weak tests left by #227 | status:ready | same | live | G |
| 221 | Pin ruff | status:ready | same | live | D |
| 192, 146 | code-review bot re-surface / silent skip | — | — | live | D |
| 119, 116, 107 | needs-research (119 and 107 also needs-grill) | — | — | live; no executor in this repo | B |
| 197, 193, 120, 110 | needs-grill product questions | — | — | live | product |
| 198, 112, 92 | product | — | — | live | product |

**Osasuwu/like-current-song (open):** #158, #144, #75, #74, #73, #72. All product work, no orchestration items.

### Osasuwu/jarvis-oss (open, orchestration-relevant)

| # | Title | Labels | Status | Cluster |
|---|---|---|---|---|
| 107 | Make review, machinery-guard, check_quotes and tests required checks | afk:3-human | live | D |
| 123, 124 | Decide: pre-push leak gate bypass / scrub literals | status:owner-queue | live (label used as an issue-level hold) | D |
| 118 | Authority log (rolling bot issue) | — | live mechanism | D |
| 169 | Weekly job: one issue for expired check dates, with keepalive | afk:2-plan | live | J Scheduled |
| 155 | Weekly quote check: NOT FOUND (rolling) | — | live | J |
| 173, 170, 164, 161, 159, 146, 203 | carry `afk:2-plan` | afk:2-plan | live; no planner exists in jarvis-oss either | C |
| ~15 docs/skill items | carry afk:3-human | afk:3-human | live | — |

**jarvis-private:** no issues. PRs 1–5 are all merged.

**redrobot:** private fork with issues disabled, last pushed 2026-06-24.

### Closed in the last ~6 months: not-planned, superseded or half-done (jarvis unless noted)

- **Autonomous loop v1 (Apr):** #113–#116, #133 executable orchestrator, #138, #55 cron triage. Superseded.
- **Pillar 7 LangGraph/APScheduler (Apr–Jun):** #296, #298, #368, #372, #385, #388–#390, #426. #387 Telegram ingest was NOT_PLANNED on 06-15. Superseded.
- **Sandcastle (May–Sep):** #534 epic NOT_PLANNED 05-08, slices #537–#546, #607–#611. Demolished by #1802.
- **AFK rework (May):**
  - #633, #637, #639 (watcher daemon), #711, #642.
  - #642 is the /delegate pre-dispatch gate. It survives as `/dispatch` condition 1.
  - #648 and #644 (scheduled-tasks MCP blocked in bypass mode) were NOT_PLANNED.
- **Reactive-core (May–Aug):**
  - #739–#746, #752, #906, #909, #921, #922, #931, #953, #1384–#1399, #1479–#1502.
  - #679 global task channel; its advancer survives as #1913.
  - All demolished.
- **Auto-merge (Jun–Aug):**
  - #891 auto-enable job, culled in #1796. Its function was re-added as a post-step in agent-dispatch (#1843).
  - #976, #1005 (jarvis-ci App token), #1012, #1234, #1512, #1655.
  - #1109: self-modifying PRs skip the gate.
  - #1236: gate green with zero comments. Same class as music-intel-mcp#226, still open there.
- **Convergence, milestone 58 (Jul–Sep):**
  - #959 umbrella NOT_PLANNED 09-24.
  - #1119 S3 and #1121 S4a completed, then demolished.
  - #1651 (task_queue has no repo column; cross-repo dispatch unsafe) NOT_PLANNED 08-19. `/dispatch` condition 0 still cites it.
  - #1617, #1759, #1788 NOT_PLANNED.
- **Plan-review, milestone 68 (Aug):**
  - #1686, #1689, #1691 (sandcastle admission), #1707 (`afk:2-plan` / `afk:3-human` vocabulary) and #1708 (three-class admission funnel) all completed.
  - #1702 and #1705 NOT_PLANNED.
  - The vocabulary survives. Its consumers (drain, sandcastle) are gone.
- **/delegate → task_queue:** #1085 NOT_PLANNED 09-24. `docs/reference/dispatch-ship-gate.md` still describes its SQL gate.
- **Rebuild, milestone 70 (Sep):**
  - #1793, #1796, #1802, #1804, #1805, #1806, #1815 completed.
  - Agent-dispatch hardening #1844, #1846, #1848, #1927, #1936, #1949, #1953 completed.
  - #1893 completed: waiting-human-review made required, owner-queue retired.
  - Supabase migration slices #1856–#1862 NOT_PLANNED 09-09. F1 is "Supabase stopped and removed everywhere".
- **Mass triage sweep 2026-09-24:** about 30 issues closed NOT_PLANNED as "obsolete, retired in milestone #70, file fresh against the current substrate". These include #959, #1412, #1702, #1564, #1085, #1002, #1003, #1010, #1036, #1116, #1164, #1202, #1462, #1541, #1546, #1551, #1574 (async inbox), #1575, #1577, #1682, #1762, #1764, #872, #910, #651, #652, #974, #1095, #1188, #1190, #1524. Notable comments:
  - #1412: "label-triggered pickup now exists as agent-dispatch.yml".
  - #1564: "no unattended path pushes to an existing PR today", so rework is a gap.
- **Other repos:**
  - like-current-song #81/#82: throwaway unblock-ready live checks.
  - music-intel-mcp#235 and like-current-song#224: owner-queue-guard replaced by waiting-human-review, 2026-10-01.
  - jarvis-oss #150 NOT_PLANNED: doc-review dispatch runs check out only the head commit.

---

## 2. Clusters

**A. Executor: claude-code-action via `agent:dispatch`.** This is the only live unattended lane, and it exists only in jarvis and jarvis-oss.
- Open defects: #1932 (re-dispatch blocked) and #1951 (no pytest).
- Ops: #1810 (tokens) and #1809 (quota).
- Prompt and skill text above the lane assume a planner, a research capability and cross-repo pickup. None of them exist.

**B. Label contract (`needs-*`, `afk:*`).**
- `needs-research` has a remover (`/research`) but no unattended runner (#1941).
- 3 of the 4 `needs-research` issues are in a repo with no executor (music-intel-mcp #119, #116, #107).
- The vocabulary differs per repo (section 5).
- The 2026-10-01 journal entry hands the `afk:*`/`needs-*` contract to the new "AFK orchestration" milestone.

**C. Plan lane (class 2).** Built in August for the drain/sandcastle runtime:
- `agents/plan_*.py`, `.claude/agents/planner.md` plus 3 critics, `config/plan_review.yaml`, `scripts/plan_review_diff_gate.py`.
- The runtime was demolished in September; the CI gate was deleted in #1835.
- `afk:2-plan` is still applied (jarvis #1894; jarvis-oss ×7), but no automation consumes it. #1918 and #1681 are open; #1573 is the open parent.

**D. Merge gates and holds.**
- Required checks in jarvis: code-gate, require-linked-issue, pytest, gitleaks, waiting-human-review.
- Auto-merge is queued by the agent-dispatch post-step.
- Open: code-gate correctness issues (#1782, #1872, #1880, #1073, #1075, #1550), plus a fail-open gate in music-intel-mcp (#226).
- jarvis-oss uses a different model: no auto-merge, a machinery-guard and an authority detector.

**E. Dead-stack residue.** Supabase migrations, the global-task advancer (#1913) and the wake_driver dependency (#1761). Docs and skills still describe sandcastle, task_queue, drain and the events substrate.

**F. Rebuild follow-ups (milestone 70).** #1808, #1809, #1810, #1913, #1932, #1941 are open. All cite a spec file that cannot be found.

**G. Test quality / H. Research / I. Interactive harness.** Adjacent, not orchestration. G matters because the worker cannot run tests (#1951), so every test-touching worker PR is held.

**J. Scheduled jobs.** The only live cron is jarvis-oss `quote-cron.yml` (Mondays 06:17 UTC). Workshop Routines (#1804) are the claimed routine host, but nothing in the repos verifies them.

---

## 3. Existing mechanisms, per repo, with triggers

### jarvis
- **agent-dispatch.yml**
  - Trigger: `issues.labeled`, with the job gated on `agent:dispatch`. Concurrency is keyed per issue (#1936). Timeout 45 min, `--max-turns 100`.
  - Auth: `AGENT_DISPATCH_PAT` on the owner's account, plus an OAuth setup-token.
  - Worker: allowlist only, and no Python setup step. Workflows, hooks and settings are denied.
  - Post-step "Queue auto-merge" (`if: always()`): `gh pr merge --squash --auto`. If there is no PR, the run fails red (#1927).
  - The prompt says there is no `~/.claude` layer; only the repo's AGENTS.md is available.
- **unblock-ready.yml** (logic in `.github/scripts/unblock_ready.py`)
  - Triggers: issues closed/reopened/unlabeled; pull_request opened/reopened/ready_for_review/edited/closed; workflow_dispatch sweep.
  - Closing an issue strips its status labels and promotes dependents whose last blocker it was to `status:ready`.
  - Removing a `needs-*` label re-evaluates the issue.
  - PR open sets `status:review`; PR closed unmerged sets back to `status:ready`.
  - Uses GITHUB_TOKEN, so it triggers no other workflows.
- **waiting-human-review.yml**: pull_request (opened/sync/ready/review_requested/removed/labeled/unlabeled) and pull_request_review. It fails while the label is present or a review request is pending. Required since #1893. Unlike jarvis-oss, it does not auto-add the label.
- **Gates:** code-review (code-gate), pr-body-check, pytest, gitleaks.

### music-intel-mcp
- Workflows: ci, code-review (PR + workflow_dispatch `pr_number`), gitleaks, pr-body-check, unblock-ready, waiting-human-review.
- **No agent-dispatch.**

### like-current-song
- Workflows: ci, code-review, pr-body-check, unblock-ready, waiting-human-review.
- No gitleaks, no agent-dispatch. `allow_auto_merge` is false but required checks are set (journal, 2026-10-01).

### jarvis-oss
- **agent-dispatch.yml** (ported from jarvis at 7b20ed9)
  - Installs Python 3.12 and pytest, so #1951 is already solved here.
  - No auto-merge; the worker cannot edit labels.
  - Its post-step applies **`status:owner-queue`** when no PR is produced.
  - Concurrency is keyed per issue.
- **machinery-guard.yml** (`pull_request_target`): re-applies `waiting-human-review` whenever a PR touches `.github/`, `.agents/`, `.claude/`, `scripts/` or `tests/`.
- **authority-detector.yml** (`branch_protection_rule`, plus `pull_request_target` unlabeled): logs hold releases to rolling issue #118.
- **waiting-human-review.yml**: auto-labels every fresh PR.
- **quote-cron.yml**: weekly cron.
- Also: doc-review, quote-check, structure-gate, tests, gitleaks.

### jarvis-private
- `skills-tests.yml` only. No review bot; merges are manual.

### redrobot (private fork, dormant since 2026-06-24)
- *[Redacted for publication: the workflow list of a private repo.]* It still carries `owner-queue-guard.yml` and a Supabase event-dispatch workflow.

### User-level skills (jarvis-private `skills/`)
- **/dispatch v4.0.0** (applies `agent:dispatch`). Five-condition gate at `dispatch/SKILL.md:41-62`:
  - condition 0: repo match, citing #1651 and M58;
  - condition 1: no `needs-*` label;
  - condition 2: an AC heading;
  - condition 3: a decision reference;
  - condition 4: not `afk:3-human`.
- **/to-tickets §3a** writes the class label, via `scripts/to_tickets_afk_fit.py` and `config/protected-paths.json`.
- **/triage 1a** classifies on demand.
- **/wayfinder** is a read-only frontier scan.
- **/research** removes `needs-research`; **/grill** removes `needs-grill`.
- **/implement §3b** runs the plan gate through `agents.plan_classifier` and the planner subagent.

### Local (`~/.claude/scheduled-tasks`)
- Registered tasks: only 3 disabled one-shots.
- Directories with no registered task:
  - `jarvis-autonomous-watchdog` (May AFK tick; calls the retired `mcp__memory__*` tools);
  - `weekly-self-improve` (Saturday self-improvement → PR).

---

## 4. Design history, in order

| # | When | Design | Outcome |
|---|---|---|---|
| 1 | Apr 2026 | **Autonomous Work Loop v1** (`docs/design/autonomous-loop.md`): perception skills, daily orchestrator, GH Actions → Supabase events. Milestone #14, #113–#138 | Superseded; the doc is frozen at 2026-05-17 |
| 2 | Apr–Jun | **Pillar 7**: LangGraph dispatcher, Ollama, APScheduler/NSSM service, task_queue, Telegram ingest. Milestones #18, #20, #21, #29, #31, #32 | Superseded by sandcastle and reactive-core |
| 3 | May | **Sandcastle**: Docker AFK loop on Workshop PC, PowerShell watchdog, Ollama → DeepSeek tier ladder. Milestone #38; #534 epic NOT_PLANNED; AFK rework milestone #41 with watcher daemon #639 | Folded into #4 and #5, then demolished (#1802) |
| 3a | Jun–Aug | **Ralph-loop** script | Retired 2026-08-08 in favour of reactive-core (`docs/reference/ralph-loop.md`) |
| 4 | May–Aug | **Reactive-core** (milestone #44): events/task_queue, wake_driver LISTEN/NOTIFY, local-model orchestrator, executor spawning `claude -p` in sandcastle; loop-closure paths A and B | Closed 08-08; demolished in Sep (#1802) |
| 5 | Jul–Sep | **Executor → sandcastle convergence** (milestone #58, #959): single spawn substrate, slot-chain ladder, sweeper. Research declared out of scope | Partly built (#1119, #1121); #959 NOT_PLANNED 09-24; demolished |
| 6 | Aug | **Plan-review stage** (milestone #68, grill #1573, PRD locked 08-24): class vocabulary, planner + critics, hash lock, drain, CI diff-gate | Python modules and agents remain; runtime and CI gate gone; milestone still open (2 issues) |
| 7 | 2026-09-04/06 | **Rebuild: native Claude Code** (milestone #70, spec grill-rethink-0904): claude-code-action by label with a PAT; Supabase paused (F1); sandcastle, memory and reactive-core demolished; 14 workflows culled; Workshop Routines | Live. agent-dispatch shipped #1839, auto-merge #1843, hardening through #1954 |
| 7a | Sep 12–21 | **jarvis-oss**: its own agent-dispatch fork, human-merge model, machinery-guard and authority detector, agent review replacing human sign-off (2026-Q3.md, 2026-09-21) | Live and diverging from jarvis |
| 8 | 2026-10-01 | **"AFK orchestration" milestone** (journal, decisions.md:414-434): `implement` / `implement-afk` split; automation triggers skills by conditions **without `/dispatch`**; owns merge-by-risk, the risk line plus `waiting-human-review`, the `## Plan` format and the `afk:*`/`needs-*` contract. Separate grill for the plan lane (decisions.md:362) | Not started. This inventory is its input |

---

## 5. Contradictions and stale references

1. **The executor has barely run.**
   - jarvis agent-dispatch has 278 runs in total. Only **2 completed**: success and failure, both on 2026-09-08. 55 were cancelled and the rest skipped.
   - The cancellations cluster on 09-08 (the Supabase slices), 09-16/17 and 09-24, which matches the #1936 concurrency bug. It cannot be told cheaply whether real workers were among them.
   - jarvis-oss: the last 50 runs are 0 completed, 7 cancelled, 43 skipped.
   - So #1809's "10 unattended runs" has effectively not started, and the lane is unproven at volume.
2. **`status:owner-queue` has 3 meanings.**
   - In jarvis it is retired (waiting-human-review.yml comment, AGENTS.md:40), and the label is deleted from jarvis.
   - CLAUDE.md says it is still live on issues.
   - The label still exists in music-intel-mcp (#226 carries it) and like-current-song.
   - jarvis-oss's agent-dispatch post-step actively writes it, and #123/#124 use it.
3. **The two dispatch lanes are forked.**
   - jarvis: auto-merge, label edits allowed, no pytest.
   - jarvis-oss: no auto-merge, no label edits, pytest installed, owner-queue on no-PR, auto-hold on every PR.
   - `/dispatch` SKILL.md:11 describes both, but there is no single canon.
4. **`/dispatch` text conflicts with the 2026-10-01 decision and the current state.**
   - The decision says AFK starts by conditions without `/dispatch`.
   - Condition 0 (`dispatch/SKILL.md:41-47`) points at milestone 58 / #1119 / #1121 as the "real fix"; #959 is NOT_PLANNED.
   - Condition 3 accepts decision UUIDs from the retired memory MCP, which cannot be resolved.
   - The `/to-tickets` §5 decision citation (lines 157, 199) mandates a decision UUID per #1099.
5. **Plan lane text is false.**
   - `implement/SKILL.md:188,191` say "the CI diff-gate … blocks" and "fail-closed backstop". The gate was deleted in #1835 (journal decisions.md:363; #1918).
   - `triage/SKILL.md:77` and `to-tickets/SKILL.md:137` name "the drain (#1691 AC5)" as the sole writer of `plan:locked`/`needs-plan`. The drain is demolished, though both labels still exist in jarvis.
   - `to-tickets:51,132` say "the plan-gate in /implement handles the lock". Interactive only.
6. **Reactive-core is still described as live.**
   - `to-tickets/SKILL.md:69` names "the reactive-core orchestrator's `emit_task` route" and the `task_queue` glossary.
   - `triage/SKILL.md:44` names "reactive-core event substrate (jarvis: events)".
   - jarvis `CONTEXT.md:27,103` say the AFK-fit checklist decides "the `sandcastle` label". Lines 31 and 107-109 describe `events` and `strategic_proposal_queue` tables.
   - `CONTEXT.md:191` says "Workshop PC = sole routine host"; this is not verified.
7. **Stale reference docs still on origin/main:**
   - `docs/reference/afk-delegation.md` (supervisor, queue, `/delegate`);
   - `docs/reference/dispatch-ship-gate.md` (SQL gate for #1085, which is NOT_PLANNED);
   - `docs/design/sandcastle-integration.md` (memory_get UUIDs);
   - `docs/design/autonomous-loop.md` (May status);
   - `docs/reference/native-first-substrate.md` (routes scheduling to `/loop` or scheduled tasks, background to desktop agents; never reconciled with claude-code-action).
8. **Unresolvable decision references.**
   - The agent-dispatch prompt cites decision `a2d10d70-…` (lines 69-74).
   - `wayfinder/SKILL.md:10` cites `9e3584e4…` and `7085a34a`.
   - The plan-review PRD's D1–D14/П1–П7 lived in the retired memory MCP.
   - The jarvis-private journal itself has only one old UUID: `6fd2df1d-…` at decisions.md:49. It is flagged as revisited, not resolvable.
   - The grill-rethink-0904 `spec_locked.md`, cited by #1808, #1809, #1810 and the milestone 70 description, was not found anywhere.
9. **Label vocabulary drift.**
   - jarvis: `afk:2-plan`, `afk:3-human`, `agent:dispatch`, `plan:locked`, `needs-plan`, `status:rework-in-progress`, `automerge-withheld:review-blind`. The last three have no live writer.
   - music-intel-mcp: `afk:2-plan` but **no `afk:3-human`**; legacy `tier:3-human` and `unsafe-for-afk`; no `agent:dispatch`.
   - like-current-song: no `afk:*`; legacy `tier:3-human` and `unsafe-for-afk`.
   - `needs-prototype`, used by `/wayfinder` (line 37), exists in **no** repo.
   - `ready-for-agent` / `ready-for-human` (`/triage`) exist in no repo.
10. **Owner-account identity.** The dispatch PAT, review bot and owner share one account, so notifications are invisible (#1927, closed by failing red), and the agent can release its own holds. jarvis-oss documents this ("a hold, not proof") and added an authority detector; jarvis has no equivalent. #1894 is the open audit.
11. **Ungated auto-merge path.** Worker PRs auto-merge with only the code-gate. The gate has known fail-closed and fail-open bugs (#1782, #1872, #1073; music-intel-mcp#226 is fail-open). Under CLAUDE.md's "fail-OPEN gate freezes merges" rule, #226 and #1073 should freeze those check-classes, but nothing records a freeze.
12. **redrobot.** The owner-queue-guard and the Supabase event-dispatch workflows still exist, contradicting "deleted in every owned repo". It is a dormant fork, so it is unclear whether it counts as owned.
13. **#1761** (wake_driver notify) and **#1913** (advancer) are open against deleted infrastructure. Local `~/.claude/scheduled-tasks/jarvis-autonomous-watchdog` still contains a prompt that calls `mcp__memory__*`, which no longer exists.
14. **#1941's injection chain is live as described.** unblock-ready runs on any issue close, and the worker auto-merges, so an auto-merged report can promote a dependent. jarvis-oss's machinery-guard pattern is the existing counter-design.

---

## 6. Open questions for the design

1. **Repo scope.** Is the orchestrator jarvis-only, or jarvis + music-intel-mcp + jarvis-oss? Three repos with different merge models (auto / manual / hold-every-PR) are the first fork.
2. **Canon.** Which `agent-dispatch.yml` is the canon to converge on: jarvis (auto-merge) or jarvis-oss (human merge, pytest, owner-queue on escalate)?
3. **`/dispatch`.** Does it survive as a manual trigger now that "AFK by conditions" exists? What replaces its 5-condition gate when the trigger is automatic, and who applies `agent:dispatch`?
4. **Plan-review code.** Revive or delete the remnants (`agents/plan_*.py`, planner and critic agents, `plan_review_diff_gate.py`, `config/plan_review.yaml`)? This decides #1918, #1681 and #1573, and the meaning of `afk:2-plan` (issues in jarvis and jarvis-oss carry it today).
5. **Escalation marker.** It is currently owner-assignee in jarvis and `status:owner-queue` in jarvis-oss. #1932 and #1894 both turn on this choice.
6. **Research lane (#1941).** The milestone-58 PRD put non-code AFK out of scope, and the 2026-09-30 journal keeps `needs-research` binding on a dead end. Which holds?
7. **Spec location.** Where is grill-rethink-0904 `spec_locked.md`? Without it, the AC-6.x acceptance on #1808, #1809 and #1810 cannot be checked.
8. **Worker workload.** Is a quota/volume baseline (#1809) a precondition for designing the scheduler, given only 2 completed jarvis worker runs exist?
9. **Cleanup.** Bulk-delete the dead-stack residue (Supabase migrations, #1913 scope, stale docs in section 5 items 6-7, redrobot workflows, local scheduled-task directories) before or inside the new milestone?
10. **Workshop PC.** Is it still the routine host (#1804, CONTEXT.md:191)? Nothing on GitHub shows which routines are registered there.
