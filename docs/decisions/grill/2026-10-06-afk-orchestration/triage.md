### F — Fact corrections
| # | IDs | Correction | Evidence |
|---|---|---|---|
| F1 | G22 | The problem statement's run count is wrong: there are 276 skipped runs, not 222. 1 success, 1 failure and 54 cancelled are correct. All 54 cancelled runs are older than the concurrency fix 7872858. | `gh api repos/Osasuwu/jarvis/actions/workflows/agent-dispatch.yml/runs --paginate`. Re-run during triage: 54 cancelled / 1 failure / 276 skipped / 1 success. |
| F2 | C16, G6 | [HIGH] The `needs-human` escalation label does not exist in jarvis or in like-current-song. It has to be created in both before §6 can run, because `gh issue edit --add-label needs-human` errors today. | `gh label list -R Osasuwu/jarvis` (re-checked during triage: the `needs-*` labels are research/grill/prd/rebase/triage/plan only); `gh label list -R Osasuwu/like-current-song` |
| F3 | C12 | The model is not pinned, so the §11 parameter "Fixed: model" does not hold yet. `claude_args` needs an explicit `--model`. | `.github/workflows/agent-dispatch.yml:142-143` (grep for `--model` finds nothing) |
| F4 | G4 | The proposal says nothing else depends on the `/dispatch` skill, but deleting it breaks `jarvis-private/tests/test_keep_set_skills_native_memory.py:33` (`SKILL_NAMES` includes `"dispatch"`) and leaves stale prose references. The cleanup slice has to update the test and those references: to-tickets:131, implement:3,18,197, wayfinder:73, research:296, grill:257, engineering-principles:43, SOUL.md:54, settings.json:95, agent-dispatch.yml:12. | `jarvis-private/tests/test_keep_set_skills_native_memory.py:33` (verified); raw-grounding G4 row |
| F5 | G7 | `threat-model.md` does not call prompt injection via issues "not a threat". It lists it as an accepted risk: Medium with mitigation "None (trusted input assumed)" at :27, and Low, "Accepted (trusted repo)" at :91. The document is dated 2026-04-15. | `docs/security/threat-model.md:3,27,91,117` (verified :27, :91) |
| F6 | G2 | `scripts/to_tickets_afk_fit.py` does not call `classify()` and applies no labels. It matches `config/protected-paths.json` buckets (hitl→3, guarded→2) for Q1 only. `/to-tickets` Q2–Q4 are LLM judgement, and the skill applies the labels. | `scripts/to_tickets_afk_fit.py:28` (imports only `label_for`, verified), `:58-90`; `to-tickets/SKILL.md:34-65,129-135` |

### D — Decision clusters
#### D1. One GitHub account behind every "human" boundary — [HIGH] — members: S1, S4, S7, C41, C43, C50, C51, C62, A3, P1, G9 — sources: sampling, coverage, grounding
Root cause: Osasuwu is the only collaborator. The operator, interactive skills and local scheduled runs all act as Osasuwu. So "a human with write access approves" (§7), "author has write access" (§4) and "never applied by an unattended run" (§3) cannot tell the human apart from agents. The platform also forbids authors approving their own PRs, and the worker App can approve with `pull_requests:write` alone (G9). P1, the premortem, names §7's approver definition as the earliest point where this failure could be prevented. A3 is enforced by "nothing". Verified during triage: `gh api repos/Osasuwu/jarvis/collaborators` returns `Osasuwu` only.
Question: What identity model backs the §7 HIGH/CRITICAL release and the §3/§4 trust checks, given that agents act under the operator's account?
Options: (a) Keep the single account and rewrite every boundary that names a human as "not the worker App". Accept that agents under the operator token count as human, and that the "merged without a human editing code" record (C62) can't be verified. (b) Add a second identity: interactive skills and scheduled runs act as a bot App that authors PRs and issues. The operator is then a non-author approver, and issues and labels from agents can be told apart from the operator's own. (c) Release HIGH/CRITICAL without a review: don't queue auto-merge for HIGH/CRITICAL, and the operator merges by hand (S4). This is not server-enforced, and it leaves C41/C43 unaddressed.

#### D2. Host repos differ from jarvis, so the reusable lane doesn't fit like-current-song — [HIGH] — members: S6, C27, C28, C29, C36, C57, C65, C74, A5, G14, G15 — sources: sampling, coverage, grounding
Root cause: The proposal assumes like-current-song is set up like jarvis. It isn't. `allow_auto_merge` is false there. It has no `agents/`, no `config/plan_review.yaml` and no protected-paths entry. Its checks are `test`/`verify-verdict`, with no `code-gate` or `gitleaks`. It has no `agent:dispatch`, `afk:*` or `needs-human` labels, and its tests are Flutter. Its backlog is mostly machinery, device-bound or desktop work, so ≥3 real runs there may be impossible (C36). How secrets and the workflow ref get passed to a reusable workflow in a public repo is also unspecified (C57, C74). A5 is enforced by "nothing".
Question: How does the lane reach like-current-song, and does it stay the second host for the N-run gate?
Options: (a) Keep the reusable workflow plus an explicit per-host prerequisites list: enable auto-merge, create the labels, map check names, cross-checkout or vendor the classifier, pass named secrets instead of `secrets: inherit`, and pin the ref. (b) Per-repo lane workflows adapted from a jarvis reference (S6). (c) Make jarvis the only gate host and defer like-current-song until its prerequisites and backlog support it.

#### D3. The terminal artifact depends on the LLM worker reaching its last step — [HIGH] — members: C5, C13, C14, C40, C45, C47, C49, C69, C81 — sources: coverage
Root cause: Escalation (§6) and refusal comments only happen if the LLM worker or the intake job gets to them. These cases all end with no artifact: a crash, a timeout, exhausting `--max-turns`, cancel-in-progress on a re-label, a `MalformedPlanError` or GraphQL exception at intake, a red check after the PR opens, or a partial label swap. Nothing notifies the operator (App comments don't ping, and §6 drops the assignee). C40's model-pin half is covered by F3.
Question: Which mechanism guarantees "every run ends in an artifact" when the worker or intake doesn't finish normally?
Options: (a) A deterministic `if: always()` post-step that writes the escalation itself (a label swap in one call, a `run_id` comment, an operator @-mention) on any end without a PR. Intake catches its own exceptions as refusals, something watches for red checks after the PR opens, and cancel-in-progress is reconsidered. (b) Keep worker-performed escalation. Redefine the §11 artifact rule so crash, cancel and max-turns endings are recorded as "no-artifact" outcomes. (c) (a) without the watcher for red checks after the PR opens.

#### D4. The tool allowlist can't confine the worker's GitHub writes — [HIGH] — members: S3, C10, C11, C46, A1, G11, G21 — sources: sampling, coverage, grounding
Root cause: `--allowed-tools` entries are literal prefix matches. `gh issue edit` accepts several issue numbers, `gh issue view` can read comments and the live body, and `git push` reaches any branch. Code run under `pytest` is not bound by the allowlist at all. The App's `issues:write` and `contents:write` cover the whole repo, and labels it applies do trigger workflows, so the worker can start new unattended runs. Intake checks the issue author but not the label `sender`. The worker can also remove `waiting-human-review` from its own PR.
Question: What enforces §5 ("label edits only on its own issue/PR", "never reads comments", snapshot-only body) and limits pushes to the worker's own branch?
Options: (a) Move all GitHub writes out of the worker into deterministic steps scoped by issue or PR number. The worker gets no writable GitHub token, and a step pushes its own branch. (b) Keep the allowlist but tighten it: issue-number-templated prefixes, drop `gh issue view`, intake checks the label `sender`. Record the remaining pytest/subprocess gap in `threat-model.md`. (c) Narrow the App's permissions instead (e.g. no `issues:write`), and make label and comment writes with `GITHUB_TOKEN`, which triggers no workflows.

#### D5. A plan lock proves the plan is well-formed, not who wrote or reviewed it — [HIGH] — members: C8, C31, C58, C75, C76, G5, G17 — sources: coverage, grounding
Root cause: `verify_lock` is an unkeyed sha256 over the `- ` step lines only. Anyone who can edit the body can recompute it. Prose added between steps, or steps after a sub-heading, is neither hashed nor parsed. `lock_max_age_days` isn't checked at intake. Nothing records whether the planner and critic panel ran. The planner only returns the plan and can't write or hash it, so the "planner writes it into the issue body" step in §8 has no actor (G5: `/implement` writes it today).
Question: What must a `## Plan` that passes intake prove, and which component writes and locks it for an AFK-bound issue?
Options: (a) Accept "lock = well-formed plan from a write-access account". Name the writer (e.g. `/implement`, or a new skill step) and document the limit. (b) Make the lock carry provenance and scope: hash the whole plan section, add a panel-run record or keyed signature, and refuse stale locks. (c) Keep `afk:2-plan` out of AFK until planner-in-AFK (#1573).

#### D6. A missing `afk:*` label is treated as an AFK-eligible verdict — [HIGH] — members: C1, C2, C4, C30, A4, G3 — sources: coverage, grounding
Root cause: "No `afk:*` = class 1" fails open. `/file-issue` doesn't classify AFK fitness, yet §3 lets it apply `agent:dispatch`. `/to-tickets` Q4-"yes" issues get no class label. like-current-song has no `afk:*` labels, so all 7 of its open issues read as class 1. The class has two writers (`/to-tickets` and `/triage` §1a), not the one §9 names. And the three trigger skills currently encode the opposite rule, that only `/dispatch` applies `agent:dispatch`. A4 is enforced by "nothing".
Question: Does an issue with no `afk:*` label enter the lane as class 1, and who is the single writer of the class?
Options: (a) Keep the implicit default. Make `/file-issue` route through `/triage` §1a before it may apply the trigger, and name `/triage` as a second class writer. (b) Require a positive class label (e.g. `afk:1-auto`) from the classifying path, and have intake refuse unclassified issues. (c) Have intake classify unlabelled issues itself, using static path buckets, before it admits them.

#### D7. The computed risk tier under-counts and the PR can lower it — [HIGH] — members: S2, S5, C18, C21, G1, G16 — sources: sampling, coverage, grounding
Root cause: Working from a diff, `classify` never returns 3: only `docs-only` is derived, so the 3→HIGH mapping is dead. `docs-only` short-circuits to 1, and that includes the contract documents. `config/plan_review.yaml` and `agents/**` are not on the machinery list. Test weakening (conftest, skip/xfail, looser asserts) isn't machinery either; only deletions are. A `pull_request` check runs the PR head's classifier and config. `pr-body-check.yml` has no checkout, no Python and no pyyaml to import the classifier. Verified during triage: `agents/plan_classifier.py:125-131`.
Question: How is the computed tier made complete and out of the PR's own reach?
Options: (a) Extend the machinery list (contract docs, classifier config and code, test-modification patterns) and evaluate it from base-branch code in a job that has Python. (b) GitHub CODEOWNERS on the machinery paths plus a ruleset requiring code-owner review, read from base (S5). This also needs a non-author approver (see D1). (c) Drop the classifier ordinal and compute the tier from the machinery path list alone.

#### D8. The intake refusal set is narrower than the gates it replaces — [HIGH] — members: C3, C6, C15, C42, G18, G19 — sources: coverage, grounding
Root cause: §4 drops conditions that the current preflight and `/dispatch` enforce: a closed issue; an existing open PR or branch (the #1932 claim class, which re-dispatch hits); `status:in-progress`/`status:review`; an open blocker after labelling; a decision reference or `[no-decision]`; a repo match; and the dispatchable-vs-inline judgement. The spec also may live in a comment the worker never reads (the `/triage` agent brief, G19).
Question: Which pre-dispatch conditions does the deterministic intake carry over?
Options: (a) Port all of them: closed, claim (open PR or branch), in-progress/review status, open blocker checked live, decision reference, repo match, and a rule that the spec is complete in the body (or `/triage` writes the brief into the body). (b) The drafted §4 list plus the claim and closed-issue checks only. (c) The §4 list as drafted.

#### D9. Unclear when the issue body and labels are checked, and whether they're up to date — [HIGH] — members: G8, C7, C32, C44, C66, C67 — sources: coverage, grounding
Root cause: The snapshot-and-`lastEditedAt` design leaves several things open. Body edits (`## Plan`, links, AC) have no required order relative to labelling, so legitimately prepared issues are refused. It's not said whether label checks read the event snapshot or live state. A `needs-*` label added after intake is never re-checked. `lastEditedAt` edge cases are unspecified (null, title edits, ties, latest LabeledEvent on re-label). The grounding pass could not confirm that the `labeled` payload carries `body` (G8, UNVERIFIABLE). Without it, the snapshot-only rule breaks.
Question: What binds the body and labels the worker acts on to the state intake approved?
Options: (a) Snapshot-only for both body and labels, with a mandated order (all body edits, including plan and lock, before labelling) and specified `lastEditedAt` semantics. Verify that the payload carries `body` first. (b) Replace `lastEditedAt` with a body hash recorded at intake and re-compared when the worker starts. (c) Live reads at both intake and worker start, re-running the refusal checks.

#### D10. Approving a HIGH PR doesn't release the hold — [HIGH] — members: C17, C19, C20, C53, G13 — sources: coverage, grounding
Root cause: `risk-tier` would sit in `pr-body-check.yml`, which has no `pull_request_review` trigger. An approval isn't bound to a head SHA (`required_pull_request_reviews: null`, so stale reviews are never dismissed). And the `waiting-human-review` label, described as "for visibility", is itself a required failing check that nothing removes after approval.
Question: How does the §7 hold track an approval?
Options: (a) A custom `risk-tier` that also triggers on `pull_request_review`, binds the approval to the head SHA, and clears `waiting-human-review` when it releases. (b) Native `required_pull_request_reviews` with dismiss-stale-reviews in place of the custom approval logic. This needs a non-author approver (see D1). (c) No approval-tracking check at all, following D1(c).

#### D11. Required checks don't stop a worker or outsider from shaping the result — [HIGH] — members: C23, C25, C55, A2, G12 — sources: coverage, grounding
Root cause: `code-gate` takes its verdict from the newest matching comment by any author. The worker, through the allowlisted `gh issue comment`, or any GitHub user on a public repo can post "No issues found." and get a LOW/MEDIUM PR auto-merged. Verified during triage: `.github/workflows/code-review.yml:436-447`, "selection can't be author-based", and no selected comment at all also counts as a pass. The "different App" claim in §2 is false: every check is app 15368, and `code-gate` and `gitleaks` are pinned to `null`. `pytest` runs the PR head's tests and conftest. Pinning `app_id` shows which runner reported a check, not what code ran. A2 is enforced by "nothing".
Question: What makes required checks trustworthy merge evidence when the worker writes the code and can comment?
Options: (a) Take the `code-gate` verdict from an author-restricted source (a specific bot author, or the check-run output itself), drop the "different App" claim, and tier test changes HIGH so check-weakening needs a human. (b) Run the trust-relevant checks from base-branch code (`pull_request_target` or `workflow_run`), and give code review its own App so the `app_id` pin means something. (c) Keep `app_id` pinning only and record the remaining risk in `threat-model.md`.

#### D12. Admin bypass of the HIGH hold stays open, and AC2a doesn't exist — [HIGH] — members: C56, G10, G23 — sources: coverage, grounding
Root cause: `enforce_admins: false` lets the admin, the only account, merge past red required checks. The AC line "AC2a (`--admin` deny hook) stays" is based on a false premise. `/implement` contains no AC2, AC2a or AC3a, and no `--admin` hook exists anywhere. Those ACs exist only as unshipped locked ACs in `docs/research/implement-skill-redesign-2026-09-30/05-locked-acs.md:27-45`. The problem statement's "interactive skills carry interim rules for four coupling points" is therefore also inaccurate.
Question: Is the admin path around the HIGH hold closed, and by which mechanism?
Options: (a) Set `enforce_admins: true` on both hosts. (b) Build the `--admin` deny hook as a new deliverable, rewriting the AC from "stays" to "added", and keep `enforce_admins` false. (c) Leave it open, treat admin merges under the merge-gates carve-outs, and fix only the AC and problem-statement wording.

#### D13. The N-run gate's pass/fail rule is ambiguous — [MEDIUM] — members: C37, C38, C39, C61, C63, C72, C79, C84, C92 — sources: coverage
Root cause: §11 leaves a lot open. It's unclear whether the denominator is runs or PRs, and whether a HIGH PR merged after approval counts. There's no rule for choosing which issues to run, so easy issues can be picked. Nothing says what happens at ≤5/10, and there's no time bound. The window resets on a lane change. A held PR can wait forever. "Lane-defect fix" and "trust boundary in" have no done-criterion. New skipped runs keep accruing because every label event fires the workflow, the worker's own `needs-human` included. 6/10 has a Wilson 95% interval of about 31–83%.
Question: What exactly counts, how are runs picked, and what happens on a fail or a stall?
Options: (a) Specify all of it: the denominator, a sampling rule, a fail branch at ≤5/10 or no 10 runs by date X, a reset on lane change, a timeout for held PRs, done-criteria for the trust boundary and for "lane-defect fix", and filtering of skipped runs. (b) Keep §11 as drafted and resolve ambiguities when they come up. (c) Replace the ratio with a smaller smoke criterion that makes no statistical claim, plus a qualitative review of each run.

#### D14. The lane doesn't write issue status transitions — [MEDIUM] — members: C34, C35, C59, C60, C77, C78, C82, C91 — sources: coverage
Root cause: Nothing sets `status:in-progress` when a run starts, so it can race an interactive `/implement`. Escalation, no-PR endings and unmerged PR closes leave or restore `status:ready` while `needs-human` or `agent:dispatch` is still on the issue. `agent:dispatch` stays on after success. A worker PR using `[no-issue]` or a `refactor:` title prefix never links back. And `unblock_ready.py` promotes an issue back to ready after `needs-human` is removed only on its "once blocked" path.
Question: Does the lane own `status:*` and `agent:dispatch` transitions at start and end?
Options: (a) Deterministic lane steps: set in-progress at start, write a terminal status on escalation or no-PR, remove `agent:dispatch` on PR or close, require `Closes #N` (no bypass markers) for worker PRs, and extend `unblock_ready` to handle `needs-human` removal. (b) Leave status to `unblock_ready.py` as it is and document the gaps. (c) Only require `Closes #N` for worker PRs and remove `agent:dispatch` at intake.

#### D15. Who arms auto-merge and keeps branches current under strict protection — [MEDIUM] — members: C22, C26, C54, C68, C83, C86 — sources: coverage
Root cause: `strict: true` plus the removed merge-train means concurrent AFK PRs stall on out-of-date branches. An App without `workflows` permission can't update a branch when `main` changed workflow files. The post-step that arms auto-merge runs under the operator PAT that AC line 74 removes, and no replacement identity is named. There's no cap on concurrent workers across issues, so N labels start N runs.
Question: Which identity arms auto-merge after the PAT is gone, and how is the strict-mode stall handled?
Options: (a) A deterministic post-step under the App arms auto-merge, plus a branch-update step or job (with a human fallback for workflow-file drift), plus a global concurrency cap. (b) Turn off `strict: true` on the host branches. (c) A serial lane (cap of 1) with manual update-branch when a stall happens.

#### D16. Rollout order for required checks, labels and callers per host is unspecified — [MEDIUM] — members: C24, C52, C73, C87, C88 — sources: coverage
Root cause: Auto-merge is armed before `risk-tier` exists in a host's protection. Making `risk-tier` required leaves already-open PRs pending until they're re-synced. Callers can be wired before the host has its labels and checks. like-current-song is onboarded "immediately", before the jarvis smoke results are evaluated. And nothing enforces "other repos only after the gate".
Question: What is the enablement order per host, and is "other repos after the gate" enforced?
Options: (a) Prerequisites first: labels and required `risk-tier` in protection before the caller or auto-merge goes live, re-sync open PRs, onboard the next host only after the smoke runs are evaluated, and an allowlist of host repos inside the reusable workflow. (b) As drafted, with ordering left to the slices.

#### D17. The worker grades its own work, with no deterministic check before the PR — [MEDIUM] — members: C9, C33, C48, G20 — sources: coverage, grounding
Root cause: The worker can't run pytest (#1951 is open). It alone decides whether it deviated from the plan and whether the AC is met, so a partial PR can ride LOW/MEDIUM auto-merge. The only deterministic plan-conformance check (`plan_review_diff_gate.py`) is being deleted. It is already wired to no workflow, yet `/implement` §3b (`:188,191`) still cites it as the fail-closed backstop for the `priority:critical` carve-out.
Question: Is there deterministic verification inside the run before a PR opens, and what replaces the diff-gate backstop that `/implement` cites?
Options: (a) Add the Python toolchain (#1951) and keep or wire a deterministic plan/diff conformance step instead of deleting it. (b) Add the toolchain only, delete the gate, and rewrite `/implement` §3b so it no longer claims the backstop. (c) Change nothing in the lane, so CI is the only verifier, and fix the `/implement` §3b wording only.

### L — Low-impact follow-ups
| # | IDs | Item |
|---|---|---|
| L1 | C64 | No staleness check at label time: an old issue can run against a `main` that has moved past its AC. |
| L2 | C70 | Escalation comments are free LLM text on a public issue, and gitleaks doesn't scan comments. Consider a secret-shape filter on the comment. |
| L3 | C71 | Specify the grammar for parsing the `Risk:` line (dash variants, case, duplicates, code fences), and reconcile the classifier's `dependency-bump` exemption with dependency manifests being machinery. |
| L4 | C80 | Blocked issues need a manual trigger once unblocked (chaining is deferred). Document it in the contract. |
| L5 | C85 | `needs-human` escalations have no expiry, sweep or review cadence. |
| L6 | C89 | `afk:2-plan` issues waiting for an interactive planner session have no queue signal (planner-in-AFK deferred to #1573). |
| L7 | C90 | The `plan:locked` label exists in jarvis but isn't in the §9 contract. Delete it or define it. |

### Coverage map
| ID | Bucket |
|---|---|
| S1 | D1 |
| S2 | D7 |
| S3 | D4 |
| S4 | D1 |
| S5 | D7 |
| S6 | D2 |
| S7 | D1 |
| C1 | D6 |
| C2 | D6 |
| C3 | D8 |
| C4 | D6 |
| C5 | D3 |
| C6 | D8 |
| C7 | D9 |
| C8 | D5 |
| C9 | D17 |
| C10 | D4 |
| C11 | D4 |
| C12 | F3 |
| C13 | D3 |
| C14 | D3 |
| C15 | D8 |
| C16 | F2 |
| C17 | D10 |
| C18 | D7 |
| C19 | D10 |
| C20 | D10 |
| C21 | D7 |
| C22 | D15 |
| C23 | D11 |
| C24 | D16 |
| C25 | D11 |
| C26 | D15 |
| C27 | D2 |
| C28 | D2 |
| C29 | D2 |
| C30 | D6 |
| C31 | D5 |
| C32 | D9 |
| C33 | D17 |
| C34 | D14 |
| C35 | D14 |
| C36 | D2 |
| C37 | D13 |
| C38 | D13 |
| C39 | D13 |
| C40 | D3 |
| C41 | D1 |
| C42 | D8 |
| C43 | D1 |
| C44 | D9 |
| C45 | D3 |
| C46 | D4 |
| C47 | D3 |
| C48 | D17 |
| C49 | D3 |
| C50 | D1 |
| C51 | D1 |
| C52 | D16 |
| C53 | D10 |
| C54 | D15 |
| C55 | D11 |
| C56 | D12 |
| C57 | D2 |
| C58 | D5 |
| C59 | D14 |
| C60 | D14 |
| C61 | D13 |
| C62 | D1 |
| C63 | D13 |
| C64 | L1 |
| C65 | D2 |
| C66 | D9 |
| C67 | D9 |
| C68 | D15 |
| C69 | D3 |
| C70 | L2 |
| C71 | L3 |
| C72 | D13 |
| C73 | D16 |
| C74 | D2 |
| C75 | D5 |
| C76 | D5 |
| C77 | D14 |
| C78 | D14 |
| C79 | D13 |
| C80 | L4 |
| C81 | D3 |
| C82 | D14 |
| C83 | D15 |
| C84 | D13 |
| C85 | L5 |
| C86 | D15 |
| C87 | D16 |
| C88 | D16 |
| C89 | L6 |
| C90 | L7 |
| C91 | D14 |
| C92 | D13 |
| A1 | D4 |
| A2 | D11 |
| A3 | D1 |
| A4 | D6 |
| A5 | D2 |
| P1 | D1 |
| G1 | D7 |
| G2 | F6 |
| G3 | D6 |
| G4 | F4 |
| G5 | D5 |
| G6 | F2 |
| G7 | F5 |
| G8 | D9 |
| G9 | D1 |
| G10 | D12 |
| G11 | D4 |
| G12 | D11 |
| G13 | D10 |
| G14 | D2 |
| G15 | D2 |
| G16 | D7 |
| G17 | D5 |
| G18 | D8 |
| G19 | D8 |
| G20 | D17 |
| G21 | D4 |
| G22 | F1 |
| G23 | D12 |

Totals: 128 IDs. F covers 7 IDs in 6 entries, D covers 114 IDs in 17 clusters, and L covers 7 IDs in 7 entries.

### Branch grouping
- Identity, approval and merge gating (§2, §7): D1, D7, D10, D11, D12, D15
- Trigger, intake and plan contract (§3, §4, §8, §9): D5, D6, D8, D9
- Worker run, escalation and issue lifecycle (§5, §6): D3, D4, D14, D17
- Distribution, rollout and N-run gate (§1, §10, §11): D2, D13, D16
