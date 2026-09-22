### F — Fact corrections
| # | IDs | Correction | Evidence |
|---|---|---|---|
| F1 | C63, G24 | `enforce_admins` on `main` is already enabled; point 6 lists it as a new step. `docs/publishing-discipline.md:287` ("administrators bypass protection on this repo") is stale and should be corrected in the AC9 rewrite. | `gh api repos/Osasuwu/jarvis-oss/branches/main/protection` → `enforce_admins.enabled: true` (re-checked 2026-09-19); `docs/publishing-discipline.md:287` |
| F2 | G6 | The hold works differently from the proposal's description. The label is auto-applied only on `opened` / `ready_for_review` at run attempt 1, and only when no reviewer is requested. The check fails while the label is present OR a review is requested. "Label applied automatically to every new PR" is inexact. | `.github/workflows/waiting-human-review.yml:42, 49-68, 70-79` |

### D — Decision clusters

#### D1. Corpus supply and gate specification — [HIGH] — members: S2, C16, C18, C21, C50, G7, G19 — sources: sampling, coverage, grounding
Root cause: The gate "lower bound ≥ X at n ≥ 30 blocking" is set over a corpus that cannot currently be built. Five things stand in the way:
- n is ambiguous: AC2 asks for ≥30 entries of any label, while the gate needs 30 blocking ones.
- X is unset and would be chosen after the results are seen.
- The held-out rule is applied after the fact, and the #75/#81 findings drove edit #87/#89.
- No #75 or #81 report carries blocking/follow-up labels, and none records changed-vs-unchanged per finding.
- Nothing is posted for #81 round 2.
Question: What are the gate's n, X, label procedure and held-out rule, and are they written down before any corpus result is read?
Options: (a) Keep as drafted: n=30 provisional, X set after the first run. (b) Pre-register X, the n on blocking only, the label rules and the held-out set before building the corpus, and accept that the hold stays until n is reached. (c) Drop the numeric gate for now and publish counts only (caught/missed, n), with no interval or threshold, until n supports one.
Notes:
- S2's first bullet (biased denominator) duplicates D7, and its numbers duplicate C21.
- Wilson lower bounds at n=30: 0.886 for 30/30, 0.833 for 29/30, 0.787 for 28/30. X = 0.8 therefore allows one miss.
- G19 still holds. PR #81 now has commits up to `86ad376` but only two comments, and no report for any fix commit (`gh pr view 81`).
- Evidence confirmed at `CALIBRATION.md:74,114,159,174-176,277`.

#### D2. `blocking` redefined narrower than today's must-fix set — [HIGH] — members: S3, C40, C3, C8, G13, G14 — sources: sampling, coverage, grounding
Root cause: Today every `mismatch`, every `missing` option and every pass-3 `blocking` finding is must-fix (`SKILL.md:182-185`). Redefining `blocking` as clauses (i)–(iii) changes this in four ways:
- Unquoted wrong facts, wrong numbers, wrong tool behaviour and wrong `tried` status drop to follow-up.
- `unverifiable` has no mapping to either label.
- Clause (iii) is met by a boilerplate fallback line.
- Severity exists only in pass 3, and it is defined over ad-hoc setups, not over the four reader types.
Question: What is the must-fix set under the new design, and how does each finding type (pass-1 `mismatch`/`unverifiable`, `missing`, pass-3 findings, `tried` status) map to blocking or follow-up?
Options: (a) Keep (i)–(iii) as the sole blocking definition; everything else becomes an issue. (b) Make blocking = (i)–(iii) plus every pass-1 `mismatch` and every wrong `tried`/`sourced` status, give `unverifiable` a rule, and state when the fallback line satisfies (iii). (c) Keep the current must-fix set unchanged and use the negative guarantee only as the README-facing promise, not as the severity rule.
Note: S3's incentive point is that a writer under a round cap is rewarded for quoting less. It sits here and interacts with D11.

#### D3. No leak backstop before irreversible publication — [HIGH] — members: C36, C26, C37, C57, C58, G10 — sources: coverage, grounding
Root cause: The design removes the only human read, while leak detection stays weak and late:
- Detection is an exact-string denylist over file contents plus gitleaks. It misses variants, history, commit messages and PR/issue text.
- It runs in CI after the push, when the branch is already public.
- `scripts/scrub_personal_literals.py` only detects and rewrites nothing, so the scrubbing itself is done by the agent.
- The "leak" exception that calls the human fires after exposure, and no detector routes to it.
Question: What stands between private material and a public push once no human reads the text?
Options: (a) Change nothing: accept the denylist plus gitleaks, and state the gap. (b) Keep a human read for the private-evidence class only: `examples/` traces and any PR that adds scrubbed material. (c) Add a pre-push/local gate and widen detection to variants, commit messages and the PR/issue text `/doc-loop` writes before anything leaves the machine. (d) Do not publish private-derived traces.
Note: Evidence confirmed at `docs/private-literal-scrub.md:24-25,140-146`. G10 adds that `last_seen` older than 180 days fails the gate for own-trace examples.

#### D4. The human certifies inputs they cannot check — [HIGH] — members: C29, A4, S6, C49, C56, C73 — sources: sampling, coverage
Root cause: The same model produces the corpus labels and the catch/miss adjudication, and label error is already on record (`CALIBRATION.md:204,270`). Three consequences follow:
- The argument that voided the per-doc signature applies equally to the calibration signature.
- The README names the human accountable for content they neither read nor evaluate.
- The signature has no expiry as the corpus grows.
Question: What, if anything, does a human act certify in this design, and who is the second reader of the corpus labels?
Options: (a) Keep as drafted: the human signs `CALIBRATION.md`. (b) Replace the signature with a clerical random-sample audit (S6): k click-through checks of blocking-class claims per doc or release, with misses logged to the corpus. (c) Drop the human signature entirely and have the README state that no human certifies the number. (d) Keep the signature, but require a non-writer second pass on labels and re-signing whenever the corpus changes.
Note: A4's "Enforced by" is "nothing". S7's third bullet makes the same point; S7 is filed in D8.

#### D5. The PR under review defines its own required check, and the review job holds a secret next to untrusted text — [HIGH] — members: S1, C5, S4, C41 — sources: sampling, coverage
Root cause: On `pull_request`, the workflow file, `SKILL.md`, `CALIBRATION.md`, the skill hash and `structure_gate.py` are all read from the PR's merge ref. A same-repo agent PR can therefore change the reviewer, or turn the job into a no-op under the same check name, with no admin action needed. AC12's hash comparison is then void. Separately, the reviewer fetches writer-chosen URLs and reads PR content while the OAuth token is in its environment and Bash/web tools are enabled.
Question: From which ref does the gate take its definition, how are PRs that touch the reviewer handled, and what may the review job do (tools, network) while it holds the token?
Options: (a) Keep `pull_request` as drafted and add the self-definition gap to the stated residual gaps. (b) Keep `pull_request`, but add a review-blind rule: any PR touching the workflow, skill, calibration or gate files fails the check and needs the human. (c) Run the gate from the base branch (S4): `pull_request_target` guarded to same-repo heads, PR docs read as data only and never executed, with a tool allowlist. This reverses AC4's outright ban.
Note: The repo's own docs name `pull_request_target` as what is left for one developer on a personal account (`docs/doc-structure-gate.md:278-294`, confirmed). A3 (filed in D6) covers this path too.

#### D6. One account and one token, so nothing separates human acts from agent acts — [HIGH] — members: C52, C53, C27, A3 — sources: coverage
Root cause: The agent runs on the human's admin token. It can merge with `gh pr merge` once checks are green, and standing agent instructions allow low-risk merges autonomously. It can also remove labels without attribution and toggle branch protection. "The human always performs the merge" has no mechanism behind it. By the repo's own criterion (`publishing-discipline.md:160-162`) the new required check is advisory.
Question: Is "the human merges" enforced by a mechanism, or is it stated as a convention with a disclosed gap?
Options: (a) Change nothing beyond AC9's disclosure, extended to cover the merge path and unattributable label removal. (b) Give the agent a separate non-admin identity or token that cannot merge or administer, such as a machine user or hosted agent (option 3 in `publishing-discipline.md`). (c) Add a human-only merge precondition the agent's token cannot produce, such as a hardware-signed tag (option 5 there).
Note: A3's "Enforced by" is "nothing". Counter-evidence is on record: "gamed twice" (`publishing-discipline.md:188`), and #55 merged 57 s after the hold label (`SIGNOFF.md:30`). Both confirmed.

#### D7. The recall denominator contains only defects the same model later found — [HIGH] — members: C20, A1, C17, P1 — sources: coverage (S2 bullet 1 from sampling makes the same point)
Root cause: "Escaped = found in round N+1" leaves out defects no run ever finds, so the figure is biased upward. The entries come from 2 PRs and about 4 docs and are not independent draws, which makes the 95% interval narrower than the evidence supports. The premortem names this choice, together with D2, as the earliest preventive decision point.
Question: What population is the published figure estimated over, and how is the never-found remainder represented?
Options: (a) Keep the escaped-defect definition and publish the figure explicitly as a floor on same-model agreement, not as recall. (b) Add an estimator for unfound defects: the union of k runs with capture–recapture (S5, filed in D24). (c) Add a defect source the model did not select, such as the human sample audit (S6, D4) or reader reports (D21), and compute the figure on that. (d) Publish no recall figure.
Note: A1's "Enforced by" is "nothing". P1 also covers D1, D2, D6, D9, D11, D20 and D3.

#### D8. The independence claim does not cover the blocking classes — [HIGH] — members: C12, A2, S7, C14 — sources: sampling, coverage
Root cause: The proposal claims independence from the deterministic checks, but they cover little of the guarantee:
- `check_quotes.py` verifies wording only (`scripts/check_quotes.py:22-23`, confirmed). It skips quotes under 3 words and does not touch paraphrased plan-tier facts.
- The structure gate checks shape, and gitleaks checks secrets.
- Clause (i), clause (iii) and the claim-versus-quote half of clause (ii) therefore have no verifier other than the writer's own model.
Question: On what does the design claim independence for clauses (i)–(iii)?
Options: (a) Withdraw the independence claim and state that the blocking classes are guarded by same-model review only. (b) Build deterministic or non-model verification for specific clauses, such as a plan-tier fact check against pricing pages or a human click-through sample (S6). (c) Add a second, non-same-model reviewer for the blocking classes. This reverses "no second model vendor".
Note: A2's "Enforced by" is "nothing" for clauses (i) and (iii).

#### D9. The public trust claim is worded more strongly than what is measured — [HIGH] — members: C33, C34, C32, C65 — sources: coverage
Root cause: The README wording overstates the measurement in four ways:
- "Measured recall … the information can be trusted" will be read as the share of errors caught. It is recall on the narrow blocking class, over same-model-found defects.
- The guarantee says "never", yet it is published beside a lower bound below 1.
- Plan-tier facts change after publication, and nothing re-checks them.
- The figure ships at a provisional n=30.
Question: What exactly do the README and the guarantee claim, and in what words?
Options: (a) Keep "never leads to…" plus the recall figure as drafted. (b) Reword the guarantee as a dated, as-of-review aim. Publish the figure with its definition: class, denominator, n and provisional status. Add a plain statement that wrong non-blocking facts may ship. (c) Publish no number until the n≥60 target is met, and describe the process only.
Note: C33's example is #81's "a launch failure fails open everywhere", a safety-relevant claim that would be a follow-up under D2's drafted definition.

#### D10. The review record (`reviewed:` frontmatter + ledger + two-commit rule) is self-referential and unverifiable — [MEDIUM] — members: C24, G16, G2, G3, C23, C51, C61, C72, G17 — sources: coverage, grounding
Root cause: The record is a poor fit for the gate that has to enforce it:
- `reviewed.commit` and `reviewed.report` can only be written in a new head commit. That commit re-triggers the required review, so the record never describes the head, and with reviewer variance it can loop.
- The gate's two-commit check is keyed to a non-empty `signed_off` and the hardcoded ledger path. It treats any frontmatter edit as the doc's last commit, and it misses re-review edits to an existing ledger line.
- `_parse_frontmatter` is a flat `dict[str,str]` and cannot hold a mapping.
- `report` is validated by URL shape only, and the report is editable by the same account.
- The two-commit rule's named compensating control is the hold this proposal removes.
- The per-doc `recall` goes stale on recalibration.
- Body-change expiry (D26) was never implemented.
Question: Where does the per-doc review record live, who writes it, and what must the gate be able to prove from it?
Options: (a) Keep frontmatter `reviewed: {commit, report, recall}` plus ledger plus the two-commit rule. Exempt or special-case record-only commits, and extend the parser. (b) Have CI write the record outside the doc body (ledger only, a check-run or a commit status), with flat keys or none in frontmatter, and drop the two-commit rule. (c) Drop the per-doc record and let the required check's status on the merge commit be the record.

#### D11. The 3-round cap and stop semantics conflict with observed convergence — [MEDIUM] — members: C9, C11, C44, C46, C28, C43 — sources: coverage
Root cause: The round cap does not match what the repo has seen:
- "Round" is undefined: it could mean a full review or each fix plus delta.
- The writer agent counts its own rounds.
- Observed history is six rounds on #61/#62, and "neither converged" for #75 and #81 (`CALIBRATION.md:174-176`, confirmed).
- The false-blocking rate has no threshold, yet false blocking findings consume rounds.
- The stop message asserts "doc too broad", while the recorded cause was fix-induced defects.
- The human is the single server for every stop, and stops would be the usual case.
Question: What is a round, who counts it, what is the cap, and what does a stop say and cost?
Options: (a) Keep max 3 as drafted and define "round" in the skill. (b) Define a round as one full review plus its fix/delta cycle, count rounds in the workflow rather than in the agent, set a false-blocking threshold, and make the stop message report the observed cause. (c) Replace the fixed cap with a convergence rule (open blocking count not decreasing) plus a hard ceiling.

#### D12. The drift key and AC12 semantics are under-specified — [MEDIUM] — members: C19, C48, C70, C68, G12 — sources: coverage, grounding
Root cause: Several things about the drift check are left open:
- AC12 has two readings: fail the check, or only flag recalibration.
- The key is model id plus skill hash only. It leaves out the action/CLI version, workflow prompt, tool allowlist, chunking parameters and the action's default model.
- `CALIBRATION.md` sits inside the hashed skill directory.
- With `strict: false`, a green status outlives a skill change on `main`.
- The skill is tracked only at `.agents/skills/`. The local `.claude/skills/review-doc` is an untracked copy that differs from the tracked one, so "the reviewer" is not one artifact.
Question: What constitutes "the calibrated reviewer", and what happens on a mismatch?
Options: (a) Keep the key as model id + `SKILL.md` hash, pick one AC12 reading, and move `CALIBRATION.md` out of the hashed path. (b) Widen the key to cover the workflow file, pinned action version and explicit `--model`. A mismatch fails the check until recalibration. (c) A mismatch only flags: the README figure is marked stale while reviews continue.
Note: G12 confirmed. `.claude/` is untracked, and only `jarvis-setup` is a symlink.

#### D13. AC1's supersession list is incomplete and the decision file is unsettled — [MEDIUM] — members: C31, G21, G5, G22, G30 — sources: coverage, grounding
Root cause: The proposal conflicts with entries that AC1 does not name:
- D11 says "Trust is not measured", against the published recall figure.
- D1 says "Audience is one class", against the four reader types.
- D18 requires a `signed_off` date field, and AC items 3 and 5 say "every shipped doc has `signed_off`".
- The v0.9.0 entry binds AC item 5 to the first release.
- AC item 1's bucket list is affected.
The amended file is checked out on the unmerged branch `claude/journal-1895`, and the v0.9.0 entry exists only on that branch.
Question: Which entries does the new decision supersede or amend, and against which branch state of `2026-Q3.md`?
Options: (a) Supersede only D15/D20/D26 as drafted. (b) Extend AC1 to D1, D11, D18, AC items 1/3/5 and the v0.9.0 binding, written after `claude/journal-1895` lands. (c) Same list as (b), written onto that branch now.
Note: Confirmed in `jarvis/docs/decisions/2026-Q3.md` (D1 :27, D11 :155, D18 :220-225, AC item 5 :488-489, v0.9.0 :566-569 on the checked-out branch). D17/D19 are handled in D21.

#### D14. The required check's behaviour per PR and per push is unspecified — [MEDIUM] — members: C4, C25, C42, C64 — sources: coverage
Root cause: Several cases have no defined behaviour:
- A job-level `if` for same-repo PRs yields "skipped", which reports as success. That inverts AC4's "a PR the workflow cannot review does not pass".
- A path filter leaves the check pending on non-doc PRs, and no filter means every PR costs a model review.
- Fork PRs can never pass.
- Nobody is named to decide delta pass versus full review in Actions, and a wrong delta choice skips passes 2 and 4.
Question: For each PR type (doc, non-doc, fork, record-only, fix commit), what does the required check do and what status does it report?
Options: (a) Use an always-running job that classifies the PR inside a step, passes non-doc PRs explicitly and fails unreviewable ones explicitly. Delta versus full is decided by a deterministic diff rule. (b) Do full review on every push to doc PRs and never delta; non-doc PRs get an explicit pass. (c) As drafted, with a job-level filter. AC4's last sentence would need rewording.

#### D15. `check_quotes.py` is not a merge-time gate, and it fails open — [MEDIUM] — members: C1, C47, C15, G11 — sources: coverage, grounding
Root cause: The one deterministic content check is not wired into the merge gate:
- It runs only when the writer chooses to run it and self-reports.
- It is in no PR workflow and is not a required check.
- It exits 0 on `unfetchable`, `no source` and `found elsewhere` (`scripts/check_quotes.py:290-304`, confirmed).
- CI runs only two test files (`structure-gate.yml:19`, confirmed). An AC10 test, or the skill contract tests, would not run as things stand.
Question: Is `check_quotes.py` (and the wider test suite) a required PR check, and what is its exit policy when sources cannot be fetched?
Options: (a) Change nothing: it stays a writer-run step plus the weekly cron. (b) Run it in PR CI as a required check, failing on `NOT FOUND` only, and run the full `tests/` suite in CI. (c) Same as (b), and also fail or neutral-flag when more than some share of quotes is `unfetchable`.

#### D16. The weekly cron's liveness, baseline and ownership are unaddressed — [MEDIUM] — members: C13, C60, C69, G28 — sources: coverage, grounding
Root cause: The cron has no liveness guarantee, no baseline and no owner:
- Scheduled workflows in public repos are disabled after 60 days without activity, which is exactly when docs age.
- The cron false-fails when a source page rewords.
- The issue it opens has no owner and no closure condition, while the README promises no update schedule.
- It is unknown whether a run on current `main` is clean. The script has no doc discovery, and a doc's own quoted phrases show up as non-`found`.
Question: What keeps the cron alive, what is its clean baseline, and who acts on its issue?
Options: (a) As drafted in AC8. (b) Add a baseline run before enabling, an explicit file enumeration, one rolling issue with a closure rule, and a named owner. (c) Same as (b), plus a keep-alive or liveness signal for idle periods.
Note: C13 cites a code.claude.com URL. The 60-day rule is GitHub's behaviour, and the cited page is not the natural source for it. This was not re-verified here.

#### D17. Subscription quota and the personal token become a merge dependency — [MEDIUM] — members: C6, C62, C59, A5 — sources: coverage
Root cause: Every push triggers a multi-pass review that draws on the human's interactive subscription limits. If the limits are exhausted, the token expires or is revoked, or the billing terms change, every PR's required check goes red or pending. Nothing pins the action's model to the calibrated one either, which overlaps D12.
Question: What happens to merges when the reviewer cannot run, and how is review cost bounded?
Options: (a) Accept this: a red check means wait, and nothing is added. (b) Bound the cost: trigger the review on a label or `ready_for_review` rather than on every push, with a concurrency cancel. (c) Define an explicit degraded mode in which an unavailable reviewer routes the PR to the human hold.
Note: A5's "Enforced by" is partial. AC12 covers the model id only, and nothing covers quota or billing.

#### D18. Existing docs do not conform to the new scope and stance, and no AC covers rewriting them — [MEDIUM] — members: G8, G9, G23, G25 — sources: grounding
Root cause: Current docs differ from the proposal in several places:
- "Fits only if" is a table column, not a per-option line, and "Our own choice" is a paragraph, not a section.
- No doc encodes the four reader types, and the attended/unattended axis appears in one doc only.
- GitLab/Gitea/Bitbucket appear on 18 lines across three docs.
- `publishing-discipline.md` option 7 presumes a person reading. The option that matches model-review-as-check is `doc-structure-gate.md` option 9, which currently reads "Not ours… a person reviews substance here".
- `docs/SIGNOFF.md:35-49`, `resources/review-hold-and-signoff-ledger.md` and two examples pair with the ledger model.
Question: Which existing docs, resources and examples are rewritten as part of this lock, and which option does "Our own choice" point at?
Options: (a) AC9 as drafted: rewrite `publishing-discipline.md` only, around option 7. (b) Extend the ACs to `doc-structure-gate.md` option 9 and its own choice, `SIGNOFF.md`, and the paired resource and examples, and decide whether option 7 is rewritten or a new option is added. (c) Same as (b), plus migrating all docs to the four reader types and GitHub-only scope in this lock. (d) Same as (b), with the scope migration deferred doc by doc as each passes `/doc-loop`.

#### D19. Existing docs were never signed or calibrated-reviewed, so what does migration write? — [MEDIUM] — members: C22, G1, G4 — sources: coverage, grounding
Root cause: The gate requires the `signed_off` key but accepts an empty value, and it requires a ledger entry only when the value is non-empty (`tests/structure_gate.py:177-179`, confirmed). All six docs have an empty `signed_off`, and the ledger reads "Entries: None" because agent-written signatures were purged. AC5's "existing docs are migrated" means one of two things. Either `reviewed` stays blank, or it is back-filled with reviews nobody ran.
Question: May an unreviewed doc stay in the tree with an empty `reviewed`, and how do the six existing docs get their first record?
Options: (a) Empty `reviewed` is allowed, and existing docs stay blank until each goes through `/doc-loop`. (b) Every existing doc must pass a calibrated review before AC5 lands, with no blanks. (c) Empty is allowed, but the README or the doc visibly marks unreviewed docs.

#### D20. Follow-ups filed as issues have no capacity, owner or schema — [MEDIUM] — members: C10, C55, C66 — sources: coverage
Root cause: Each review round produces 10–15 findings, and every non-blocking one becomes an issue. They land in a tracker the README reserves for broken resources, with nobody assigned to work them. Delta passes re-report unfixed follow-ups. Raw `gh issue create` bypasses the operator's `/file-issue` rule.
Question: Where do follow-ups go, and who works them?
Options: (a) As drafted: one issue per follow-up. (b) One rolling follow-up issue or file per doc, de-duplicated across rounds, filed through `/file-issue`. (c) Follow-ups are fixed in the same PR up to a budget, and only the remainder is filed.
Note: The critic counted 23 open issues. `gh issue list` showed 22 on 2026-09-19. The point is unchanged.

#### D21. The reader error channel contradicts the support contract — [MEDIUM] — members: C30, G20, C74 — sources: coverage, grounding
Root cause: "Found an error → file an issue" and "reader issues feed the corpus" conflict with `README.md:22` and D17/D19: questions go to Discussions, and Issues are for a broken resource only. There are no issue templates, and nobody is assigned to triage whether a reader report is an escaped blocking defect. This is the only corpus input the model does not select.
Question: Which channel takes reader error reports, and who classifies them into the corpus?
Options: (a) Reopen D17/D19: Issues accept doc errors via a template, and the human or a named pass triages them. (b) Keep D19, route errors to Discussions, and have the agent harvest them into the corpus. (c) Keep D19 unchanged and drop "reader issues feed the corpus" from the trust basis.

#### D22. `tried` evidence cannot be checked by anyone but the writer — [MEDIUM] — members: C35, C38, G26 — sources: coverage, grounding
Root cause: The Actions reviewer cannot read the private originals. It confirms `tried` against the writer's own scrubbed trace, and nobody can check that trace against its original. Current docs mark `tried` "in our private source project" with no public trace (`agent-safety-hooks.md:42,74,172`), and one uses the combined status "tried and sourced".
Question: What makes a `tried` marker admissible?
Options: (a) As drafted: a scrubbed trace in `examples/` is sufficient, and the README states that `tried` is self-reported. (b) `tried` requires a public, reproducible trace from this repo or another public one; anything else is downgraded to `sourced` or to an unmarked anecdote. (c) The human attests `tried` claims only. This is a narrow clerical signature, since the human did the trying.

#### D23. Fix commits are a recorded defect source, and no AC addresses it — [MEDIUM] — members: C2, C39, C67 — sources: coverage
Root cause: Fixes are written "from a review summary, not from the source", and paired files are not grepped after a fix. PR #75 spent most of its rounds on fix-introduced defects. These defects consume the round budget (D11) and are excluded from the "escaped" corpus (D1).
Question: Does the design constrain how fixes are made, or only how they are reviewed?
Options: (a) Change nothing: the delta pass catches fix-induced defects. (b) Add a fix protocol to `write-doc` or `/doc-loop`: re-open the source for each fixed claim and grep paired files, as an AC. (c) Same as (b), plus tracking fix-induced defects as a separate reported line.

#### D24. A required-check verdict is a single draw from a high-variance reviewer — [MEDIUM] — members: C7, S5 — sources: sampling, coverage
Root cause: `CALIBRATION.md:74,157-159` (confirmed) records that a single run misses things another run catches. The same account can re-run the check until it is green. The design measures a single reviewer and does not reduce its variance.
Question: Is the gate one run, or an aggregate of runs?
Options: (a) One run as drafted, with re-runs allowed. (b) The union of k fresh runs per pass. Calibrate the union, and use run overlap (capture–recapture) to estimate unfound defects. This costs k times the quota (see D17), and same-model runs are correlated. (c) One run, but re-runs on the same commit are logged or disallowed so the verdict cannot be re-drawn silently.

#### D25. The staged hold-removal trigger and the post-removal stop — [MEDIUM] — members: C45, C54 — sources: coverage
Root cause: The AC11 trigger, "two consecutive docs pass with ≤1 fix round", is satisfied equally by an under-detecting reviewer, and the agent chooses which docs are attempted. After removal, `waiting-human-review` is no longer a required check. Yet `/doc-loop`'s round-3 stop relies on applying that label, which "holds nothing until it is a required status check" (`SIGNOFF.md:29`, confirmed).
Question: What evidence removes the hold, and what holds a stopped PR afterwards?
Options: (a) AC11 as drafted. (b) Keep `waiting-human-review` required permanently and remove only its auto-application, so the label still blocks when `/doc-loop` applies it. (c) Same as (b), and change the trigger to something an under-detecting reviewer cannot satisfy, such as human-chosen docs or an audit sample with zero misses.

### L — Low-impact follow-ups
| # | IDs | Item |
|---|---|---|
| L1 | G29 | No `/doc-loop` skill, corpus file, review workflow or cron workflow exists in any form. Everything in AC2/4/7/8 is a new build. This is a sizing note only. |
| L2 | G27 | The repo default is `default_workflow_permissions: read`. New workflows need an explicit `permissions:` block to comment or open issues, as `waiting-human-review.yml:17-20` has. |
| L3 | C71, G15 | Order-of-work step 4 lands before step 5, so the gate still requires `signed_off` in between. Contract tests pin literal strings that AC6 edits will break: `tests/test_review_doc_skill.py:36-39,53-57,60-66` and `tests/test_write_doc_skill.py`. They need updating in the same PRs. |
| L4 | G18 | This item is stale. PR #81's head is now `86ad376`, `docs/agent-safety-hooks.md` is 26,943 bytes at that head, and `structure-gate` passes (`gh pr checks 81`, 2026-09-19). The 30,000-byte cap no longer blocks finishing #81. |

### Coverage map
| ID | Bucket |
|---|---|
| S1 | D5 |
| S2 | D1 |
| S3 | D2 |
| S4 | D5 |
| S5 | D24 |
| S6 | D4 |
| S7 | D8 |
| C1 | D15 |
| C2 | D23 |
| C3 | D2 |
| C4 | D14 |
| C5 | D5 |
| C6 | D17 |
| C7 | D24 |
| C8 | D2 |
| C9 | D11 |
| C10 | D20 |
| C11 | D11 |
| C12 | D8 |
| C13 | D16 |
| C14 | D8 |
| C15 | D15 |
| C16 | D1 |
| C17 | D7 |
| C18 | D1 |
| C19 | D12 |
| C20 | D7 |
| C21 | D1 |
| C22 | D19 |
| C23 | D10 |
| C24 | D10 |
| C25 | D14 |
| C26 | D3 |
| C27 | D6 |
| C28 | D11 |
| C29 | D4 |
| C30 | D21 |
| C31 | D13 |
| C32 | D9 |
| C33 | D9 |
| C34 | D9 |
| C35 | D22 |
| C36 | D3 |
| C37 | D3 |
| C38 | D22 |
| C39 | D23 |
| C40 | D2 |
| C41 | D5 |
| C42 | D14 |
| C43 | D11 |
| C44 | D11 |
| C45 | D25 |
| C46 | D11 |
| C47 | D15 |
| C48 | D12 |
| C49 | D4 |
| C50 | D1 |
| C51 | D10 |
| C52 | D6 |
| C53 | D6 |
| C54 | D25 |
| C55 | D20 |
| C56 | D4 |
| C57 | D3 |
| C58 | D3 |
| C59 | D17 |
| C60 | D16 |
| C61 | D10 |
| C62 | D17 |
| C63 | F1 |
| C64 | D14 |
| C65 | D9 |
| C66 | D20 |
| C67 | D23 |
| C68 | D12 |
| C69 | D16 |
| C70 | D12 |
| C71 | L3 |
| C72 | D10 |
| C73 | D4 |
| C74 | D21 |
| A1 | D7 |
| A2 | D8 |
| A3 | D6 |
| A4 | D4 |
| A5 | D17 |
| P1 | D7 |
| G1 | D19 |
| G2 | D10 |
| G3 | D10 |
| G4 | D19 |
| G5 | D13 |
| G6 | F2 |
| G7 | D1 |
| G8 | D18 |
| G9 | D18 |
| G10 | D3 |
| G11 | D15 |
| G12 | D12 |
| G13 | D2 |
| G14 | D2 |
| G15 | L3 |
| G16 | D10 |
| G17 | D10 |
| G18 | L4 |
| G19 | D1 |
| G20 | D21 |
| G21 | D13 |
| G22 | D13 |
| G23 | D18 |
| G24 | F1 |
| G25 | D18 |
| G26 | D22 |
| G27 | L2 |
| G28 | D16 |
| G29 | L1 |
| G30 | D13 |

Mechanical check: a script compared the map against the expected set S1–S7, C1–C74, A1–A5, P1, G1–G30. It found 117 expected, 117 listed, 117 unique, 0 missing, 0 duplicates and 0 extras.

### Branch grouping
D has 25 clusters, which is more than 12. They are grouped here by the design branch each one touches; a cluster that also touches a second branch is marked.
- Point 1 — sign-off / human role: D4, and D13 (the AC1 decision entry).
- Point 2 — negative guarantee / `blocking` definition: D2.
- Point 3 — scope (reader types, GitHub-only, plan-tier facts, `tried`): D18, D22 (also point 4).
- Point 4 — private evidence: D3.
- Point 5 — trust basis / calibration: D1, D7, D8, D12, D24.
- Point 6 — enforcement (workflow, branch protection, record): D5, D6, D10, D14, D15, D17, D19.
- Point 7 — process (`/doc-loop`, cron, hold removal): D11, D16, D20, D23, D25.
- Point 8 — README / reader surface: D9 (also point 2), D21.