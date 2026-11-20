---
topic: reliability-autonomous-merge-stack-roadmap
tags: area:process, research
source_provenance: /research invocation in session b065a837 — follow-up run to docs/research/storytold-project-side-2026-11-18.md (PR #2235), on the user's replies to it
status: open
audit: 2026-11-18 — 181 claims: 136 SUPPORTED, 39 PARTIAL, 4 UNSUPPORTED, 2 UNCHECKABLE
---

## Question

The user's replies to points of the previous report's answer, verbatim, each after the point it answers:

- On "strictness … they do not use it": "я не хочу строгость, от строгости я как раз хочу уйти. Я хочу reliability."
- On the circuit breaker being dropped: "его нет именно потому что я ещё не решил как раз circuit breaker. В прошлый раз, когда делал автономный мердж не дожал и откатил до ручного. Если сейчас ввести circuit breaker вместе в автономным мерджем, было бы очень хорошо."
- On the experiments lane: "Это возможный сигнал, что и нам стоит отказаться, но в какую сторону. Всё делать рекомендательно как в дорожке экспериментов или эксперименты вести по общим правилам. Я думаю первое, но не факт"
- On the Rust stack: "А у нас python выбран чисто, потому что лёгкий для написания язык. Возможно стоит перейти на rust тоже. Чем раньше перейти, тем меньше переписывать. Или лучше дописать на питоне, а потом отдельно весь проект переписать на rust? И стоит ли вообще переписывать, у нас же не софт в обычном понимании. Хотя возможно и к этому придём, так что тут надо смотреть на перспективу."
- On advisory CI: "И даже так продукт успешный и не сломанный. Я тоже думал сделать CI рекомендательным, но пока не рискую. Но как сейчас увидел, жёсткие правила с медленным CI сильно замедляют слитие множества PR'ов. До недавнего момента поток был меньше и нынешний CI справлялся, сейчас уже на грани, уже тормозить начинает, так что либо поправить правила, то есть ослабить требования, что я уже по чуть чуть делаю, либо полностью рекомендательным сделать, как у них. рекомендательный как будто сильно развязывает руки и делает работу гибче. Тут хз, возможно стоит рискнуть"
- On the organization's admin role: "это получается осталась единственная причина, зачем нужна организация, чтобы получить админа. Но действия, нуждающиеся в Сергазы очень редкие, легче как будто уже просто попросить его что-то сделать, чем заморачиваться с организацией. Он всё равно агентом всё делает тоже"
- On roadmaps: "У нас раньше тоже были roadmap, но изменения были настолько частые в начале проекта, что я устал править их и перешёл на что-то другое. На что не помню. Возможно стоит возродить roadmaps или аналог, чтобы было видно чем занимаемся мы в долгосроке."
- "давай следующий прогон, взяв во внимание мои ответы"

Asked seven points, answering four sub-questions because the skill takes at most four per run: the experiments-lane point is folded into Q1 (advisory everywhere vs common rules is the same trade-off as advisory vs required CI), and the organization point is not researched here — it turns on Q1's outcome (whether checks stay required) and on the merge-queue availability found in Q1 [C140].

Sub-questions: Q1 — advisory vs required pre-merge CI for main-branch reliability at high PR throughput, including a path-scoped split and the experiments lane; Q2 — designing an autonomous agent merge path with a circuit breaker, and why our previous autonomous merge was rolled back; Q3 — Rust vs Python for agent-written code and the migration strategy for jarvis and redrobot; Q4 — what replaced our roadmaps, and low-maintenance roadmap forms for plans that change often.

## Summary

**Reliability without full advisory CI: a split, with the breaker as the second half.** Google TAP and Chromium both pair a pre-merge gate with a staffed or automated revert loop [C124], [C125]. storytold, which does run advisory, has a main that is often red: its primary gate concluded red on 3 of 4 and 3 of 8 sampled main commits, it is repaired by forward-fix PRs, and it carries at least 29 PRs titled "Fix main" [C102], [C103], [C104], [C106]. Pre-submit tests cannot catch real conflicts between concurrent changes, and photocraft's repair PRs name concurrent landings [C105], [C108]. The counter is Google's own: blanket "nothing lands unless CI is green" rules are called "probably misguided" and a 100% green rate very expensive [C126]. Google's recipe is a split [C139]:
- **Required:** only a fast, reliable subset [C116], [C138]; Google cut one team's presubmit runtime 14x by making it hermetic [C137]. In redrobot add the safety paths, built as an always-run workflow with a conditional job, since a required workflow skipped by `paths` stays Pending and blocks merge while a job skipped by `if:` reports Success [C129], [C130].
- **Post-merge:** the slow, flaky or exhaustive suites, with culprit detection and revert or stop [C117], [C119].
- **Metric:** Uber reports mainline health as the share of time it is green [C110]; Google cuts releases at green head [C120].
- **Speed:** test selection and hermetic presubmits cut CI time without loosening it [C136], [C137].
- **Not available:** GitHub's merge queue requires an organization-owned repo, Enterprise Cloud for private ones [C140].

The case for advisory checks is argued for low-risk, low-concurrency work [C133], [C134]. That supports keeping the experiments lane advisory, not extending the lane's rules to the main path (inference from those claims).

**A circuit breaker belongs on the agent merge path, and it is the half that makes relaxed pre-merge CI safe.**
- **Trip rules:** AutoCraft's breaker trips a stage when 2 of its last 10 pushes turned a previously green head red, and trips the merge path on a single merge that reddens main [C201], [C203], [C205], [C206].
- **Scope and resume:** it is scoped per stage and resumed only by an operator, with no timer [C202], [C207]. It only stops; it does not revert [C216].
- **Other designs differ on two choices:**
  - **Reopen:** an operator or human (AutoCraft, bors), closing the blocker issue (Tide), automatic on green (Chromium), or back within an SLO budget (SRE) [C207], [C239], [C240], [C241], [C235].
  - **Remedy:** revert (Chromium, Mozilla, Google TAP) or stop [C119], [C242], [C243], [C250].
- **Flake guards:** repeated or concurrent failures, plus a grace period after a human reopen [C244], [C245]. AutoCraft's single-event merge trip lacks them [C217].
- **Blind spot:** a CI-red breaker cannot see defects that pass checks. It needs a post-merge reading signal, which redrobot's nightly breaker agents supply by filing defects as issues [C249].
- **Premise check:** the documents read record no rollback of agent merge to manual merging, and no missing breaker as a reason for one [C233]. Agent merge of LOW/MEDIUM PRs is still the written rule in redrobot, and jarvis allows auto-merge [C234]. What was frozen on 2026-10-17 was the unattended AFK lane, for its record (1 success in its lifetime) and wedged runs [C218], [C219]. The breaker question was explicitly deferred to a separate grill on 2026-11-11 [C223], [C224].

**Stay in Python; do not rewrite now.**
- **Benchmarks:** they do not show agents write Rust better or worse than Python. SWE-bench Multilingual puts Rust highest and Multi-SWE-bench puts it far below Python, and neither separates language from task difficulty [C305], [C311], [C312].
- **What the compiler does:** type errors do help an agent repair code [C313], [C331]. But a green Rust build still ships wrong logic [C319].
- **Later port:** porting later is cheaper than it was, because agents port existing code quickly and the old code serves as spec and oracle. What makes it feasible is a behaviour harness that runs against both versions [C320], [C321], [C322], [C340].
- **redrobot:** its robot driver is stdlib TCP/JSON and would port easily. Its simulation and geometry core rests on numpy/scipy/shapely/trimesh/numba/Warp, and Rust's numerics ecosystem is fragmented [C303], [C304], [C336], [C338].
- **jarvis:** its correctness risk sits in prompts and workflow logic, which no compiler checks [C339].
- **Migration guidance:** piecewise, with tests kept throughout and PyO3 for introducing Rust gradually behind a Python interface; tests must be external-facing to survive a port [C323], [C328], [C330].

**Roadmaps: revive one only as a by-product of the work.**
- **What replaced ours:** milestones as themed, undated buckets plus a vision doc, in both repos [C402], [C408], [C409], [C414], [C417], [C420]. The goals system that sat beside them was deleted as unused [C405], and the weekly-release goal section still reads its retired source [C413].
- **Why both roadmaps died:** they were separate hand-kept files. redrobot's living roadmap needed a "sync 8 stale checkboxes" commit while still active [C401], [C415], [C416].
- **What survives frequent change:**
  - roadmaps edited in the same PR as the work under an AGENTS.md rule, as at storytold [C425], [C431];
  - roadmaps generated from issue state [C446];
  - roadmaps with no dated promises: Now-Next-Later, Shape Up bets, an explicit "Not doing" section [C433], [C435], [C439], [C447].
- **Not useful as-is:** a GitHub Projects roadmap view would be near-empty, since almost no milestones carry dates [C443].
- **Cost:** an agent-maintained roadmap grows and needs compacting [C444], [C448].

## Findings

### Q1 — advisory vs required pre-merge CI for main-branch reliability at high PR throughput (incl. path-scoped split and the experiments lane) — answered with a gap

- **C101** [measured] photocraft main has no required status checks: its only rules are deletion, non-fast-forward and a PR rule with 0 required approvals — Own measurements, L1-M1
- **C102** [measured] In a 6-hour sample (2026-11-18) the primary Linux gate on photocraft main SHAs concluded red on 3 of 4 concluded SHAs; 7 of 16 SHAs with check-runs had at least one failed check — Own measurements, L1-M2
- **C103** [measured] In a second sample (2026-11-11) the primary gate concluded red on 3 of 8 SHAs — Own measurements, L1-M3
- **C104** [measured] photocraft has at least 29 PRs titled "Fix main", 5 items titled "main is red" and 8 titled "fixes main" (title searches with no date filter); ~4150 PRs were merged since 2026-10-08 — Own measurements, L1-M4
- **C105** [measured] photocraft main-repair PRs name breakage from concurrent landings (semantic merge conflicts), e.g. "two ui-egui tests broken by concurrent landings" and "clippy after the 11-11 merges", and one main-repair PR (#4304, open) is titled as blocking the release — Own measurements, L1-M4
- **C106** [inference] photocraft's advisory CI does not keep main green: in both per-SHA samples the primary gate concluded red on 3 of 4 and 3 of 8 concluded SHAs, and main is repaired by forward-fix PRs — from [C101], [C102], [C103], [C104]
- **C107** [quoted] Uber: a red mainline delays rollouts because the faulty commit must be detected and rolled back, and it hampers productivity of everyone building on it — "A broken master (red) leads to delayed feature rollouts because a faulty code commit needs to be detected and rolled backed. Additionally, a red master has a cascading effect that hampers developer productivity" — [S1], Abstract
- **C108** [quoted] Uber: pre-submit tests on individual changes cannot catch real conflicts between concurrent changes; among concurrent, potentially conflicting changes the chance of a real conflict rises from 5% (2 changes) to 40% (16 changes) — "pre-submit tests cannot detect these real conflicts, and they can only be captured post-submit. Observe that with even two concurrent and potentially conflicting changes, there is a 5% chance of a real conflict. This number grows to 40% with only 16 concurrent" — [S1], §2.1
- **C109** [quoted] Uber: under commit-on-presubmit plus post-submit rollback, finding and reverting the faulty patch is tedious and needs build sheriffs — "since several patches could have been committed in the meantime, detecting and reverting the faulty patch is tedious and error-prone. In many cases, build sheriffs and engineers need to get involved" — [S1], §2.1 Intermittently Green Mainline
- **C110** [quoted] Uber measured its iOS mainline green only 52% of a week before SubmitQueue, and green at all times after — "Over a span of one week, the mainline was green only 52% of the time affecting both development and rollouts. [...] Since its launch, our mainlines have remained green at all times." — [S1], §8.5, Figure 14
- **C111** [quoted] Uber: with a single serial queue at 500 changes per hour, P50, P95 and P99 turnaround grew 80x, 129x and 132x against the Oracle — "With 500 changes per hour, P50, P95, P99 turnaround times grow 80x, 129x and 132x respectively compared to the turnaround times of the Oracle." — [S1], §8 Single-Queue
- **C112** [quoted] Uber survey: 93% of 40 respondents said an always-green mainline helps their productivity, none said it hurts — "93% of survey takers believed that enforcing an always green mainline positively impacts their personal productivity while 7% saw no impact." — [S1], §8.6
- **C113** [quoted] The Not Rocket Science Rule: automatically keep a repository that always passes all tests — "The Not Rocket Science Rule Of Software Engineering:  automatically maintain a repository of code that always passes all the tests" — [S2], post body
- **C114** [quoted] Graydon: CI as commonly practised only learns quickly that the tree broke, instead of preventing the break — "Continuous integration seemed everywhere to be used only to learn (rapidly) when the tree was broken, not prevent it breaking in the first place." — [S2], post body
- **C115** [quoted] Graydon names the cost: integration cycle time is bounded by test cycle time; long suites need an integration-test subset — "It does mean that your integration cycle time is bounded by your test cycle time" — [S2], post body, closing paragraphs
- **C116** [quoted] Google: run only fast, reliable tests on presubmit and accept post-submit catches plus some rollbacks — "Our general rule of thumb is: only fast, reliable ones. You can accept some loss of coverage on presubmit, but that means you need to catch any issues that slip by on post-submit, and accept some number of rollbacks." — [S3], Software Engineering at Google ch.23, Presubmit versus post-submit
- **C117** [quoted] Google TAP lets changes land after a fast presubmit subset; such changes pass the rest of the tests 95%+ of the time — "Empirically, a change that passes the presubmit has a very high likelihood (95%+) of passing the rest of the tests, and we optimistically allow it to be integrated" — [S3], Presubmit optimization
- **C118** [quoted] Google pairs optimistic landing with a per-team Build Cop who drops everything to fix breakage, preferring rollback — "When a Build Cop is notified of a failing test in their project, they drop whatever they are doing and fix the build. This is usually by identifying the offending change and determining whether it needs to be rolled back (the preferred solution)" — [S3], Presubmit optimization
- **C119** [quoted] Google TAP auto-reverts when it is confident of the culprit; rollback is the fastest return to known-good — "Rolling a change back is often the fastest and safest route to fix a build [...] TAP has recently been upgraded to automatically roll back changes when it has high confidence that they are the culprit." — [S3], Culprit finding
- **C120** [quoted] Google tracks "green head" separately from "true head"; most teams cut release candidates at green head — "At Google, most teams cut these at green, as opposed to true, head." — [S3], Continuous Build
- **C121** [quoted] Google: mid-air collisions happen daily at its scale; small repos can avoid them by serializing submits — "CI systems for smaller repositories or projects can avoid this problem by serializing submits so that there is no difference between what is about to enter and what just did." — [S3], Why presubmit isn't enough
- **C122** [quoted] Chromium gardeners' first priority is an open tree, and they may revert suspected culprits — "1. **The tree is open**, because when the tree is closed nobody can make progress" ... "Revert changes that you know or suspect are causing breakages" — [S4], top, Tree Status
- **C123** [quoted] Chromium: while the tree is closed the CQ will not submit changes; only reverts or fixes for the breakage can still land — "**Closed**: The CQ will not submit changes while critical build or test failures are being fixed. Reverts or fixes for the tree breakage can still land" — [S4], Tree Status
- **C124** [inference] Google TAP and Chromium pair a pre-merge gate (TAP presubmit, Chromium CQ) with a staffed or automated revert loop (Build Cop, gardeners, TAP auto-rollback) — from [C116], [C117], [C118], [C119], [C122], [C123]
- **C125** [quoted] Chromium CQ full-run submits a CL only if it introduces no new regressions, so Chromium gates pre-land — "If there are no new regressions introduced, the CL will be submitted into the repo." — [S5], Modes, Full-Run
- **C126** [quoted] Google warns that a 100% green CI rate is very expensive, and that blanket "no commits unless CI is green" policies are probably misguided; the same passage still expects CI failures to be investigated — "Policies that say, “Nobody can commit if our latest CI results aren’t green” are probably misguided." — [S3], CI challenges list
- **C127** [quoted] GitHub: without required status checks a branch can be merged at any time, which raises the odds of incompatible changes; loose (not up-to-date) required checks can still fail after merge — "Status checks may fail after you merge your branch if there are incompatible changes with the base branch." — [S6], Require status checks to pass before merging
- **C128** [quoted] GitHub's "Restrict file paths" ruleset rule blocks pushes that include changes in specified paths — "Prevent commits that include changes in specified file paths from being pushed to the repository." — [S6], Restrict file paths
- **C129** [quoted] A required workflow skipped by `paths` filtering stays Pending and blocks merge; GitHub advises not requiring skippable workflows, while a job skipped by an `if:` conditional reports Success — "Associated checks stay in a \"Pending\" state and block merging" ... "Avoid requiring workflows that can be skipped." — [S7], Handling skipped but required checks
- **C130** [inference] A path-scoped required gate on GitHub can be built as an always-triggered workflow whose job-level `if:` (on a changed-files result) runs safety tests only when safety paths change, since a path-skipped required workflow stays Pending while an `if:`-skipped job reports Success — from [C128], [C129]
- **C131** [quoted] GitHub merge queue tests each PR against the latest base plus the PRs ahead of it and is meant to keep a busy branch from breaking on incompatible changes — "ensuring the branch is never broken by incompatible changes" — [S8], About merge queues
- **C132** [quoted] Merge queue groups can absorb flaky failures: with "only merge non-failing" off, a group merges if its last PR passes, since that tests the combined changes — "If the last pull request in the group has passed required checks, this means that the checks have passed for the combined set of changes in the merge group." — [S8], Only merge non-failing pull requests
- **C133** [quoted] Optimistic merging (merge first, fix after) is argued for small or medium projects doing nothing too security-sensitive, to cut contributor friction; the author still re-runs linters and tests before pushing — "But for a small or medium-sized project, that does nothing too security-sensitive, and for which maintainers and collaborators are hard to find - is it such a bad deal?" — [S9], Issues with Pessimistic Merging
- **C134** [quoted] Mergify (vendor, 153k merges / 160 teams / 90 days): a green PR breaks main ~1 in 130 merges at 2-5 engineers and ~1 in 8 at 40+ engineers — "At two to five engineers sharing a repo, a green PR breaks main about once in 130 merges, rare enough to fix by hand when it happens. At forty-plus engineers, it is one in eight." — [S10], broken-main rate section
- **C135** [inference] The odds of semantic breakage rise with the number of concurrent changes; where redrobot sits on that scale is not measured — from [C108], [C134], [C105]
- **C136** [quoted] Meta predictive test selection halves test infra cost while still reporting over 95% of test failures and 99.9% of faulty changes — "reduces the total infrastructure cost of testing code changes by a factor of two, while guaranteeing that over 95% of individual test failures and over 99.9% of faulty changes are still reported back to developers" — [S11], Abstract
- **C137** [quoted] Google cut a team's presubmit runtime 14x by making it hermetic, after, on some days, more than 50 changes bypassed and ignored the non-hermetic presubmit results — "In some days, the team would see more than 50 code changes bypass and ignore the test results. In moving presubmit to hermetic, the team cut the runtime by a factor of 14, with virtually no flakiness." — [S3], Case study: Google Assistant
- **C138** [quoted] Google: flaky presubmits are excluded because they block engineers on failures unrelated to their change — "it’s expensive for engineers to be blocked on presubmit by failures arising from instability or flakiness that has nothing to do with their code change." — [S3], Why presubmit isn't enough
- **C139** [inference] Google's recipe is a split: a fast, reliable presubmit subset is required; what slips by is caught post-submit with culprit rollback (automated in TAP); small repositories can avoid mid-air collisions by serializing submits, as a merge queue does — from [C116], [C117], [C119], [C121], [C131], [C136], [C138]
- **C140** [quoted] GitHub merge queue is available only in org-owned public repos or org-owned private repos on Enterprise Cloud — "Pull request merge queues are available in any public repository owned by an organization, or in private repositories owned by organizations using GitHub Enterprise Cloud." — [S12], Who can use this feature?

### Q2 — autonomous agent merge with a circuit breaker; why our previous autonomous merge was rolled back — answered with a gap

- **C201** [quoted] AutoCraft's push-stage breaker window and threshold are code constants: 10 pushes, 2 broken. — "export const BREAKER_WINDOW = 10;" / "export const BREAKER_BROKE = 2;" — [S13], lines 12-13
- **C202** [quoted] Breaker scope is per stage: four stages that push or merge (fixup, cifix, fixissue, merge). — "export const TRIP_STAGES = [\"fixup\", \"cifix\", \"fixissue\", \"merge\"] as const;" — [S13], line 8
- **C203** [quoted] "Red" means a required check failed; optional and skipped checks do not count; a push counts as "broke" only when the head before it was green (red-to-red is "still-red", an unknown baseline is "unknown"). — "if (after === \"red\") return before === \"green\" ? \"broke\" : before === \"red\" ? \"still-red\" : \"unknown\";" — [S13], lines 3-4, 25
- **C204** [quoted] The window counts only pushes since the last operator resume; a resume wipes prior history from the count. — "An operator clears a trip. Pushes and merges before this moment no longer count." — [S14], line 172 (resumeStage)
- **C205** [quoted] The merge-path breaker trips on the first red main head whose culprit is a PR AutoCraft merged after the last resume — one event is enough, no window. — "The default branch of `repo` is red and its culprit is PR `number` (main CI): trips the merge path when we merged that PR after the last resume." — [S14], line 153 (mainRedAfterMerge)
- **C206** [quoted] The culprit is computed as the first red head after the last green head, with the PR number parsed from that commit's headline. — "the first red head after the last green one" — [S15], lines 41-52
- **C207** [quoted] Doc summary of trip conditions and reset: operator-only resume, no timer. — "the merge path stops when main CI turns red because of a merge of ours or a post-merge review finds a defect in it \| Until an operator resumes the stage (`autocraft pipeline resume <stage>` or the Resume button on the Pipeline page); no timer" — [S16], waits table, row "Circuit breaker" (line 775)
- **C208** [quoted] A tripped stage writes nothing to GitHub until resumed, regardless of who asks (operator presses included). — "A stage that stopped itself (circuit breaker) writes nothing until an operator resumes it, whoever asks." — [S17], line 58
- **C209** [quoted] Repo scoping exists only for test repos: there a defect trips merge:<repo> instead of the global merge stage. — "a post-merge defect or a red default branch trips the breaker `merge:<repo>` only, which holds merges on that repo and not the whole pipeline." — [S16], line 848
- **C210** [quoted] The test-repo carve-out was added because deliberate test defects would otherwise halt the whole pipeline (a scoping false positive designed out). — "so a test repo's deliberate defects never stop the whole pipeline." — [S14], lines 123-125; commit 66291305 (2026-11-05)
- **C211** [quoted] Surge breaker: >30 new outside-author items per hour trips outside-surge; operator-only resume, no timer. — "More than `outside_surge_per_hour` (default 30) new outside-author items in the last hour trips the breaker `outside-surge`." — [S16], line 688
- **C212** [quoted] Daily limits are a separate cost-control wait that resets at 00:00 UTC (not operator-gated). — "Until 00:00 UTC, or until an operator raises the limit" — [S16], waits table, row "Daily limit" (line 773)
- **C213** [quoted] Separate from the breaker, a red main makes ready PRs and batches wait (stop-the-line) until main is green, except AutoCraft's own main-fix PRs. — "ready PRs and open batches wait, AutoCraft's main-fix PRs (branches `autocraft/main-ci-*`) do not \| Until main is green" — [S16], waits table, row "Main CI red" (line 767)
- **C214** [quoted] Autonomous merge in AutoCraft is narrow: take verdict, size S/M, bugfix or infra type, whitelisted author, green CI, no human-looked-at content (README, CI/build config, agent instruction files). — "**Merge without asking** only when all of these hold at the PR's current head:" — [S16], lines 327-345
- **C215** [measured] The breaker landed 2026-11-04 (commit b69e9fe2) and the repo became public 2026-11-05: it is two weeks old; a search of its issues for "breaker" returns 0. — Own measurements, L2-M2
- **C216** [measured] AutoCraft's docs mention no revert on a trip: the breaker only stops; grep for "revert" in docs/pipeline.md returns nothing. — Own measurements, L2-M3
- **C217** [inference] Because the culprit is the first red head after the last green one and a single such event trips the merge path, a flaky main failure right after an AutoCraft merge could trip it (false-positive exposure, unverified in operation). — from [C205], [C206]
- **C218** [quoted] The AFK lane was frozen 2026-10-17 by disabling agent-dispatch.yml; the record names no breaker; its why is the lane's record (1 success in its lifetime) and its last three runs wedged in `queued` for 10 days. — "the lane has 1 success in its lifetime (2026-09-08), and its last three runs had been wedged in `queued` for 10 days unnoticed." — [S18], § 2026-10-17 AFK lane frozen, Why (agent)
- **C219** [quoted] The same 2026-10-17 decision widened agent merging rather than removing it: the agent merges its own PRs, with a prompt guarding redrobot tier-1 or protected-file merges; gates and review still apply. — "**Merge (D1):** the agent merges its own PRs." — [S18], § 2026-10-17, Answer D1
- **C220** [quoted] The user's stated reason for agent merge was absence of a reason to ban it. — "есть ли вообще смысл запрещать агенту мерджить самому? Пусть мерджит." — [S18], § 2026-10-17, Why
- **C221** [quoted] The lane's auto-merge was armed by a bot post-step with a concurrency cap of 1 during an N-run gate — a throughput limit, not a breaker. — "a deterministic post-step arms auto-merge as `osasuwu-bot`. Concurrency cap 1 across the lane during the N-run gate" — [S18], § D15
- **C222** [quoted] Merge-by-risk was decided: LOW/MEDIUM auto-merge on green, HIGH held for a human, tier computed by CI. — "LOW/MEDIUM auto-merge on green required checks; HIGH/CRITICAL get `waiting-human-review` and never merge unattended." — [S18], § Merge policy by risk
- **C223** [quoted] The 2026-11-11 cross-repo grill explicitly deferred breakers to a separate grill. — "Breakers go to a separate grill." — [S18], § 2026-11-11 preamble
- **C224** [quoted] A "MEDIUM breaker" was left undecided pending the first weekly-read reading. — "A MEDIUM breaker is decided after the first reading." — [S18], § 2026-11-11, weekly-read
- **C225** [quoted] The retrospective found no AFK design stopped on a measured failure; supersession ended them. — "**No design was stopped by a measured failure verdict.**" — [S19], Summary
- **C226** [quoted] One repeating failure pattern was gates failing open. — "**Gates that failed open** (designs 3/6 admission, 7 plan gate)." — [S19], Q2, C67
- **C227** [measured] The 2026-10-06 external research contains no mention of circuit breaker, breaker, kill switch, stop the line, error budget, Tide, bors, SubmitQueue or tree closing. — Own measurements, L2-M4
- **C228** [quoted] The external research found no study comparing hold-for-human vs merge-fast-and-revert for agent PRs. — "No study compares holding agent PRs for a human against merging fast and reverting" — [S20], Summary, Merge policy (topic 4)
- **C229** [quoted] redrobot: jarvis skills refused redrobot merges while AGENTS.md had no `## Merge denylist` heading, so Petr's 17.10 permission ("Пусть мерджит") had not been carried out as of 2026-11-04. — "так что разрешение Петра от 17.10 («Пусть мерджит») до сих пор не исполнялось." — [S21], Почему
- **C230** [quoted] redrobot: "red is not merged, main always green" (2026-10-14); a critic noted it alone does not give green main: 20 of 35 master failures were runner infra and 3 were integration after a green PR. — "из 35 падений на master 20 — инфраструктура раннера, 3 — интеграция после зелёного PR" — [S22], Критики, row 1
- **C231** [quoted] redrobot interim rule (until 2026-11-07, status proposed): during a runner outage nothing merges, urgent work included. — "во время простоя ничего не мержится, срочное тоже" — [S23], Ответ
- **C232** [quoted] redrobot "breaker" (ломатель) means adversarial test-running agents, not a merge circuit breaker; a post-merge nightly defect becomes an issue, with no revert. — "Ломатели — агенты, которые ищут дефекты, запуская код" / "Revert не делается." — [S24], Ответ; B9
- **C233** [measured] No document read records a rollback of agent merge to manual merging or names a missing circuit breaker as its reason; the only source is a memory note dated 2026-11-18 written from the user's words. — Own measurements, L2-M5
- **C234** [measured] Agent self-merge is still the written rule today: redrobot AGENTS.md § Merge denylist (lines 144-146) lets an agent merge LOW/MEDIUM; jarvis has allow_auto_merge true. — Own measurements, L2-M5
- **C235** [quoted] Google SRE error-budget policy: exceeding the 4-week budget halts all changes except P0/security fixes until back within SLO — a freeze driven by a measured budget, not a count of bad merges. — "we will halt all changes and releases other than P01 issues or security fixes until the service is back within its SLO." — [S25], Policy
- **C236** [quoted] The same policy frames halting as permission to focus on reliability, not punishment. — "This policy is not intended to serve as a punishment for missing SLOs." — [S25], Goals
- **C237** [quoted] SRE workbook cites changes as roughly 70% of outages, the rationale for gating change on reliability. — "Changes are a major source of instability, representing roughly 70% of our outages" — [S25], Background
- **C238** [quoted] Prow Tide merges only PRs with up-to-date passing tests (retest at current base before merge), batching where possible. — "automatically merge them when they have up-to-date passing test results" — [S26], intro
- **C239** [quoted] Tide's stop mechanism is a blocker issue: an open issue with the blocker label blocks merges to all branches of the repo unless `branch:` tokens scope it. — "if an open issue is found with the label it will block merges to all branches for the repo." — [S27], § Merge Blocker Issues
- **C240** [quoted] rust-lang bors: tree closing is a human command with a priority threshold, so high-priority fixes still merge. — "`treeclosed=<priority> [reason]`: Close the tree for PRs with priority less than `<priority>`." — [S28], line 71
- **C241** [quoted] Chromium: a tree auto-closed by a builder auto-reopens when that builder goes green (no human resume needed). — "if the tree is automatically closed by a builder, it will automatically reopen if that builder goes green." — [S29], § tree status
- **C242** [quoted] Chromium sheriffs hold authority to revert suspected culprits; the remedy for red is revert, not only stop. — "Revert changes that you know or suspect are causing breakages" — [S29], sheriff authority
- **C243** [quoted] Mozilla: sheriffs close the tree on test failures while they find and back out the offending patch. — "Sheriffs close the tree while they identify and back out the offending patch." — [S30], § Test Failures
- **C244** [quoted] Fuchsia's tree closer closes on N consecutive failures of a builder or concurrent failures across builders (flake tolerance by repetition). — "The tree was closed because {self.builder} failed {len(self.builds)} times in a row." — [S31], line 241
- **C245** [quoted] Fuchsia's closer has false-positive guards: an ignore regexp for build summaries and a grace period after a human reopen. — "If the tree was manually reopened recently it shouldn't be closed again, to avoid stepping on build gardeners' toes." — [S31], lines 128-129, 144
- **C246** [quoted] Uber pre-SubmitQueue: iOS mainline green only 52% of a sample week (secondary summary of the EuroSys'19 paper). — "The mainline was green only 52% of the time." — [S32], body
- **C247** [quoted] SubmitQueue's approach is prevention: merge only when all build steps pass on the would-be mainline. — "responsible for continuous integration of changes into the mainline at scale while always keeping the mainline green." — [S32], intro
- **C248** [quoted] AI review gave all-clear on a merged workflow change that removed an injection guard (Snowflake connector, June 2026): the defect was security, not a red check. — "Copilot Autofix checked the merged PR and code change and identified it as all-clear without noticing the critical vulnerabilities." — [S33], § actual role (vendor blog)
- **C249** [inference] A CI-red breaker (AutoCraft-style) cannot see defects that pass checks (security, behavior outside tests); it needs a post-merge reading signal, which AutoCraft has (post-merge review) and redrobot has as nightly breaker agents that file defects as issues. — from [C205], [C207], [C232], [C248]
- **C250** [inference] Designs split on reset: AutoCraft and bors need an operator or human to reopen, Tide holds while the blocker issue is open; Chromium auto-reopens on green; SRE reopens when back within SLO. They split on remedy: Chromium and Mozilla revert, AutoCraft only stops, redrobot B9 files an issue. — from [C207], [C216], [C239], [C240], [C241], [C242], [C243], [C232], [C235]
- **C251** [snippet] Unverified single-developer report: an agent approved and merged its own PR under a service account, leaking keys; team removed autonomous merge rights. — "approved its own pull request under its service account" — [S34], search summary only

### Q3 — Rust vs Python for agent-written code; migration strategy for jarvis and redrobot — answered with a gap

- **C301** [measured] jarvis is ~1.45 MB of Python with small PLpgSQL/PowerShell/JS shares; 63% of its Python bytes are tests, and its core is scripts, CI glue and agent prompts (206 .md files) — Own measurements, L3-M1, L3-M2
- **C302** [measured] redrobot is ~15.4 MB of Python plus a ~0.7 MB TypeScript frontend; 45% of Python bytes are tests and 22% scripts; the sandbox simulation package is 2.15 MB — Own measurements, L3-M1, L3-M2
- **C303** [measured] redrobot's robot driver talks to the BORUNTE controller over raw TCP/JSON with stdlib only, so no vendor SDK binds it to Python — Own measurements, L3-M3, L3-M4
- **C304** [measured] redrobot's scientific stack is numpy, scipy, shapely, scikit-image, trimesh, matplotlib, numba, with NVIDIA Warp and CuPy for GPU simulation — Own measurements, L3-M3, L3-M4
- **C305** [quoted] On SWE-bench Multilingual, SWE-agent + Claude 3.7 Sonnet resolved Rust tasks at the highest rate of nine languages (58.14% vs 42.67% overall) — "Resolution rate varies by language (figure 2), with Rust having the highest resolution rate and C/C++ the lowest." / table: "Rust 25 18 43 58.14% Total 128 172 300 42.67%" — [S35], Results; Appendix B table
- **C306** [quoted] The SWE-bench Multilingual author found Rust tasks were not easier by patch size, yet resolved most often — "solutions to Rust tasks modify more lines of code on average, yet SWE-agent had the highest resolution rate in Rust" — [S35], Results, Figure 3
- **C307** [quoted] The Multilingual sample is small: 300 tasks across 9 languages, 43 of them Rust — "the Multilingual dataset provides 300 tasks across 42 repositories and 9 popular programming languages" — [S35], Benchmark construction; Appendix B
- **C308** [quoted] Multi-SWE-bench (1,632 tasks) found agents strong on Python but weaker on other languages, partly because the agent scaffolds were tuned for Python — "existing LLMs and methods demonstrate strong performance in resolving Python issues but struggle to generalize effectively across other languages" / "(2) Method optimization bias : The three methods are initially optimized for Python" — [S36], Sec. 4, "Limited generalization beyond Python"
- **C309** [quoted] In Multi-SWE-bench, Rust sat mid-pack: behind Python and Java, ahead of TS/JS — "Java ranks second after Python, though with a noticeable gap. Go and Rust exhibit inconsistent performance across models, generally outperforming TS and JS but falling behind Java." — [S36], Sec. 4 analysis
- **C310** [quoted] Multi-SWE-bench: Rust and C++ projects frequently require large-scale edits, some over 200 lines and 7 files per patch — "Rust and C++ projects frequently require large-scale edits, with some instances modifying over 200 lines and 7 files per patch" — [S36], Sec. 3 features
- **C311** [quoted] Multi-SWE-bench Table 4, MagentLess rows (columns Python, Java, TS, JS, Go, Rust, C, C++): Python 36.2–48.2% vs Rust 5.0–7.1% for GPT-4o, o1, Claude 3.5/3.7 Sonnet — "Claude-3.7-Sonnet 44.60 14.06 3.57 1.97 5.84 5.44" — [S37], Table 4 (PDF)
- **C312** [inference] The two benchmarks disagree on Rust (highest on SWE-bench Multilingual, near-lowest on Multi-SWE-bench); neither isolates language from task difficulty and scaffold bias, so benchmark data does not show agents write Rust worse or better than Python — from [C305], [C306], [C308], [C309], [C310], [C311]
- **C313** [quoted] Type-constrained decoding cut LLM compilation errors by more than half and raised functional correctness (TypeScript, HumanEval/MBPP) — "our approach reduces compilation errors by more than half and significantly increases functional correctness in code synthesis, translation, and repair tasks" — [S38], Abstract
- **C314** [quoted] GitHub's blog cites a 2025 study that 94% of LLM compilation errors were type-check failures — "a 2025 academic study found that a whopping 94% of LLM-generated compilation errors were type-check failures" — [S39], body, 2026-01-08
- **C315** [inference] The 94% figure measures the composition of compilation errors, not that typed code has fewer bugs than Python; it shows the type checker is where errors surface, which is the guardrail argument, not proof of lower defect rates — from [C313], [C314]
- **C316** [quoted] A study of 86,726 erroneous LLM samples in four compiled languages found even top models make simple mistakes and often omit input validation and memory-safety checks — "even the largest models frequently make simple mistakes. We also observe that generated code often omits basic input validation or memory-safety checks" — [S40], Abstract (ISSRE 2026)
- **C317** [quoted] In a C-to-Rust LLM translation system, compile-and-equivalence feedback loops mattered more than model choice (up to 50% gain with loops plus multiple runs vs up to 9 points between models) — "LLM selection has an influence on performance (up to 9% points difference), but feedback loops have an even bigger effect" ... "Using both feedback loops and multiple runs can boost performance by up to 50%" — [S41], Introduction (HTML v2)
- **C318** [quoted] A practitioner who built a 700-line Rust tool with an AI found the borrow checker did turn a class of concurrency mistakes into build failures — "it converts a class of concurrency mistakes into build failures, and the model can lean on that to attempt refactors it would otherwise have to be timid about" — [S42], body (Zyte, 2026-05-31)
- **C319** [quoted] The same practitioner found a green Rust build still shipped wrong code; compiling, green tests and the model's claim of done were independent false comforts — "the build was green and the code was still wrong" / "\"It compiles, the tests are green, and the model says it's done\" turned out to be three independent false comforts stacked on top of each other" — [S42], intro; lesson section
- **C320** [quoted] Anthropic reports agent-driven language migrations went from multi-year to weeks: Bun Zig-to-Rust (~1M lines, under two weeks, full test suite green before merge, 19 regressions after) and a Python-to-TypeScript port of 165K lines over a weekend — "A million lines of code were produced in less than two weeks, with 100% of Bun's existing test suite passing in CI before merge. Nineteen regressions surfaced after merge" — [S43], intro (2026-07-16)
- **C321** [quoted] Anthropic's migration method puts a behaviour judge first: tests that run against both old and new code, validated against deliberately broken code — "A prerequisite before starting on your migration project is to have a strong judge in place, otherwise you won't have an exit condition or measure of success. The judge must be able to evaluate both the original code and the target code on equal terms." — [S43], Six steps, judge
- **C322** [quoted] In agent migrations the existing code is itself the spec, which is why porting later is cheaper than it was — "Context is clear and comprehensive. The old code serves as a great spec for the model." — [S43], Why AI changes the code migration math
- **C323** [quoted] Tests written in the source language often hit internals that will not exist in the port, so they must be rewritten as external-facing assertions — "Test suites written in the original language will often depend on internal functions that won't exist in the target code." — [S43], Six steps, judge
- **C324** [quoted] Mergify ported its Python CLI to Rust command by command (40+ stacked PRs) with old and new run side by side; generation took days, review took 3–4 weeks — "The port has run to more than forty merged PRs so far, one command at a time." / "It took us three weeks to a month. Not because the writing was slow, but because reviewing is the bottleneck now ." — [S44], body (2026-06-09)
- **C325** [quoted] Mergify's reasons for Rust were distribution (single binary, startup, Windows install) and reuse as a native core, not agent correctness — "We were fighting interpreter assumptions, a clumsy Windows install story, and a startup cost you feel on every invocation" / "But the binary wasn't the real reason. The real reason is reuse." — [S44], Why we touched it at all
- **C326** [quoted] Danjou argues a one-shot port that nobody can review is a gamble, while the old code defines correctness in an incremental port — "A million lines in one PR is not something a human reviews, green checks or not." / "The model gets to write the Rust and the tests. It doesn't get to decide what correct means. The old code already did" — [S44], But you should never rewrite; How we did it
- **C328** [quoted] Rust migration specialist (corrode) recommends piecewise migration with tests kept throughout, not a full rewrite — "Add functionality piece by piece rather than attempting a complete rewrite. Maintain comprehensive tests throughout the migration process." — [S46], Baby Steps
- **C329** [quoted] The same guide lists data analysis, visualization and ML as areas where Python remains the better tool, recommending a hybrid — "Not everything needs to be migrated! Python excels at:" / "Data analysis and visualization are great in Python (e.g., Pandas, Matplotlib) Machine learning workflows" / "Consider a hybrid approach where each language handles what it does best." — [S46], Keeping Python's Strengths
- **C330** [quoted] PyO3 is positioned for gradual introduction of Rust behind a Python interface — "PyO3 is ideal for: Optimizing performance-critical components Gradually introducing Rust while maintaining Python interfaces Creating Python packages with Rust internals" — [S46], PyO3
- **C331** [quoted] A controlled experiment (Krishnamurthi, Flatt) found an agent repaired errors better with a type system's error than with only a failing test suite — "We also find that the presence of a type system appears to help more than only test suite failure reports." — [S47], Abstract (v2, 2026-06-25; ML-style language Shplait, single-error programs)
- **C332** [quoted] PROBE (five languages) reports Python with the highest pass rates and Rust as the hardest language; fewer Rust training resources are offered as a plausible explanation for a gap that grows in smaller models — "Python consistently yields the highest pass rates, followed by C++ and Java at similar levels, then C, with Rust emerging as the most challenging language." — [S48], results discussion (HTML v1)
- **C333** [quoted] RustRepoTrans found compilation errors were 92.3% of LLM failures when translating repositories into Rust — "In RustRepoTrans, compilation errors account for 92.3%" — [S49], RQ1 results (PDF)
- **C334** [quoted] A small Claude Code comparison across four languages found no sign the borrow checker either helped or hindered the agent — "Neither hypothesis - that the borrow checker helps with repairs or that the borrow checker challenges AI - was supported. Rust had 0 compilation errors" — [S50], Findings, Hypotheses 1, 2
- **C335** [quoted] Cursor's large Rust crates took minutes to compile and serialized parallel agents until split into small crates — "Their Rust codebase had large crates that took several minutes to compile. When 10 agents were all modifying files in those large crates simultaneously, they each triggered full recompilation of the crate, and the compilation jobs serialized on shared resources." — [S51], What It Is
- **C336** [quoted] numr's author says fragmentation is a real pain point in Rust numerics; numr with its solvr layer (experimental beta) and SciRS2 are announced as SciPy equivalents — "We all love ndarray and the existing Rust ecosystem, but fragmentation is a real pain point." — [S52], announcement post
- **C337** [prior] NVIDIA Warp is a Python-embedded GPU kernel DSL and numba a Python JIT; neither has a Rust port, so redrobot's GPU/fast sand simulation would need a rewrite onto Rust CUDA bindings (cudarc, rust-gpu) rather than a crate swap — not fetched in this run
- **C338** [inference] redrobot's robot I/O layer (stdlib TCP/JSON driver) is portable to Rust at low risk; its larger simulation and geometry core rests on numpy/scipy/shapely/trimesh/numba/Warp, and Rust numerics are fragmented (that numba and Warp have no Rust port is prior knowledge, unchecked) — from [C303], [C304], [C302], [C329], [C336], [C337]
- **C339** [inference] jarvis is mostly tests, scripts and markdown prompts; no compiler checks prompt or workflow logic, and a green build can still ship wrong logic — from [C301], [C319]
- **C340** [inference] The "migrate now, less to rewrite" argument weakens when agents port existing code cheaply and the old code serves as spec and oracle; what makes a later port feasible is a behaviour harness that runs against both versions, not a small codebase — from [C320], [C321], [C322], [C323], [C324]

### Q4 — what replaced our roadmaps; low-maintenance roadmap forms under frequent change — answered with a gap

- **C401** [measured] jarvis had a file roadmap docs/roadmap.md from 2026-01-16 (phase-by-phase, "Current: P1 ... Next: P2" with task checkboxes), rewritten on the 2026-03-21 OpenClaw pivot and deleted 2026-03-23 in the Claude Agent SDK/MCP migration — about 9 weeks of life across two platform pivots — Own measurements, L4-M1
- **C402** [measured] jarvis docs/PROJECT_PLAN.md was turned into a pointer on 2026-04-28; it states active development follows GitHub milestones (sprints), not a static plan — Own measurements, L4-M2
- **C403** [measured] jarvis docs/PROJECT_PLAN.md records that it used to hold pillar-by-pillar status and full scope (v7.0, 2026-04-13) and was replaced because the redesign consolidated scope and live work moved to GitHub milestones — Own measurements, L4-M2
- **C404** [measured] On 2026-04-15 jarvis replaced percentage progress tracking of pillars with qualitative labels and an accomplishment log appended by /end, because percentages were false precision — Own measurements, L4-M3
- **C405** [measured] A goals system (Supabase goals table + /goals skill, "Pillar 1 of Jarvis 2.0") existed from 2026-04-08; the /goals skill was deleted 2026-09-07 as one of 13 zero-call skills, and the Supabase memory tables (incl. goal_list tool) were demolished 2026-09-08 — Own measurements, L4-M3
- **C406** [measured] The memory migration (#1790) deliberately did not carry goals over: MEMORY.md says outcomes and goals were intentionally not migrated — Own measurements, L4-M4
- **C407** [measured] The jarvis GitHub wiki has three pages (Home, Vision, Project-Plan), all last edited 2026-04-08; Project-Plan is bannered as needing an update for Vision 2.0 — stale for 7 months — Own measurements, L4-M5
- **C408** [measured] jarvis has 67 milestones (63 closed, 4 open), none with a due date; milestone creation fell from 24 in 2026-04 to 1 each in 2026-09 and 2026-10 — Own measurements, L4-M6
- **C409** [measured] jarvis milestones are themed work buckets, not dated releases: open ones are "Agent-integrity enforcement gates" (since 2026-06-15), "Methodology adoption & loop-closure" (since 2026-07-26), "Weekly releases" (0 open issues, still open), "AFK orchestration" — Own measurements, L4-M6
- **C410** [measured] Of 51 open jarvis issues, 5 have no milestone — milestones still carry the backlog — Own measurements, L4-M7
- **C411** [measured] On 2026-09-24 jarvis retired three milestone-level directions (eval v2 m51, deslop m60, competence measurement m62), rationale in .out-of-scope/ files; eval v2 because its own kill criterion's go/no-go date passed with no progress, deslop because its tooling was deleted, competence measurement because its series never started — Own measurements, L4-M8
- **C412** [measured] jarvis VISION.md still exists and calls pillars "roadmap tracks" that are narrative only and "don't gate implementation" — the vision is the only long-horizon document left — Own measurements, L4-M2
- **C413** [measured] The weekly-release engine still has a goal-movement section that parsed the retired goal_list() output; its source tool was retired in #1801, so the goal section has no live input — Own measurements, L4-M3
- **C414** [measured] redrobot had docs/PROJECT_PLAN.md (v1.0, 2026-03-18) superseded by docs/MASTER_PLAN.md (v2.0, 2026-04-07, hard deadline 2026-04-13); on 2026-04-09 MASTER_PLAN was archived "replaced by backlog" in a "migrate to agile" commit: epics replaced by milestones, 1-week sprints — Own measurements, L4-M9
- **C415** [measured] redrobot docs/ROADMAP_UC1.md (created 2026-07-10, rewritten 2026-07-30) declared itself a living document to update on track-node closure; it got 19 commits in July and 40 in August, then none of substance after 2026-08-21 (only two cleanup commits in Oct/Nov) — Own measurements, L4-M10
- **C416** [measured] Staleness was already visible during its active life: an 2026-08-19 commit had to "sync 8 stale checkboxes" in ROADMAP_UC1 — Own measurements, L4-M10
- **C417** [measured] From 2026-09-08 redrobot moved to per-round plan docs (docs/plans/core-convergence-round-N.md + journal + wrapup, rounds 3-6) paired with one milestone per round (e.g. #42 round 6, #44 round 7, #45 round 8) — short-horizon plan files instead of a long roadmap — Own measurements, L4-M10
- **C418** [measured] redrobot dropped its GitHub Project board on 2026-09-17; the principal's reason: the board had long been unused, the agent does not read it, tried and it did not take — Own measurements, L4-M11
- **C419** [measured] redrobot has 45 milestones (33 closed, 12 open), only 2 with a due date; open ones include long-lived buckets like "Бэклог вне кругов" (40 open) and "CI/CD Reliability" (42 open) and two marked "(заморожено)" — Own measurements, L4-M12
- **C420** [inference] Both repos converged on the same replacement: GitHub milestones as themed buckets plus a vision/brief doc, with no dated horizon view; the gap is that nothing shows where milestones lead or in what order — from [C402], [C408], [C409], [C414], [C417], [C419]
- **C421** [quoted] photocraft docs/roadmap.md carries a stamp line with last-reviewed date, last-updated date, change class and target — "**Last reviewed:** 2026-10-11 · **Last updated:** 2026-11-12 · **Change:** minor" — [S53], line 3
- **C422** [quoted] photocraft roadmap ends with a revision-history table of date, change class (minor/major) and summary; recent minor rows note milestones and estimates unchanged — "M11: Edit › Preferences › AI Integrations connects MCP clients to the running app without a terminal or restart; milestones, alpha gate and estimates unchanged" — [S53], ## Revision history
- **C423** [quoted] photocraft roadmap is a forward plan (milestones, current focus, estimates) and pushes current-state numbers out to separate measured docs — "Forward-looking plan: milestones, the **Current focus** list, and what's next with estimates." — [S53], intro
- **C424** [quoted] photocraft estimates are in agent wall-clock hours — "Hours are Opus 5.5 agent wall-clock hours for one agent working sequentially" — [S53], intro
- **C425** [quoted] photocraft AGENTS.md makes the agent update the parity doc and gap entry plus status line and revision history when work moves a number — maintenance is part of each PR — "update the parity doc and gap entry it belongs to, with the date, and bump their status line and revision history" — [S54], §4 Picking work
- **C426** [measured] photocraft docs/roadmap.md: 68 commits (1 Sep, 61 Oct, 6 Nov 2026) by ~29 distinct authors; 33 of 68 carry an AI co-author trailer — roughly half agent-written — Own measurements, L4-M13
- **C427** [quoted] craft-anything ROADMAP.md is a shared plan for people and agents, rebuilt from a specific commit of main, with finished work kept in roadmap-history.md — "Rebuilt on 2026-11-02 from `main` at `2e4afc5`, with v0.3.0 the latest release." — [S55], header
- **C428** [quoted] craft-anything items carry ids, owner, status and pending changes; finished lines are moved to history at release — "Maintainers move ticked lines to `roadmap-history.md` when a release ships." — [S55], How to use this file
- **C429** [quoted] craft-anything AGENTS.md makes the roadmap the agents' only work queue — "Pick work from `docs/ROADMAP.md` only." — [S56], line 97
- **C430** [measured] craft-anything docs/ROADMAP.md is 306,908 bytes / 3,422 lines and got at least 100 commits in Nov 2026 alone (API page cap) — a roadmap that doubles as the claim/task board, not a low-maintenance summary — Own measurements, L4-M14
- **C431** [inference] storytold roadmaps stay alive because agents edit them in the same PR as the work (tick, bump stamp/history) under a mandatory AGENTS.md rule, at many-contributor volume; this differs from the single-author case where the roadmap was a separate chore — from [C425], [C426], [C428], [C429], [C415]
- **C432** [quoted] Now-Next-Later's originator (ProdPad, a roadmap-tool vendor) argues dated roadmaps fail faster under AI-era shipping velocity — "With AI in the mix and shipping velocity climbing, dated roadmaps fail even harder than they used to, because the timeline is obsolete within weeks." — [S57], body
- **C433** [quoted] The same source frames Now-Next-Later as a confidence view, not a schedule — "The faster things move, the more a confidence-based view earns its place." — [S57], body
- **C434** [quoted] One ProdPad customer (Rosslyn Analytics) says in a testimonial on ProdPad's blog that the out-of-date-roadmap problem is gone (vendor-published, no method) — "the roadmap “black hole” and “out of date roadmaps in circulation” problem is no more." — [S57], body
- **C435** [quoted] Shape Up (Basecamp) rejects a central backlog; pitches not bet on are not kept — "Now that we’ve written a pitch, where does it go? It doesn’t go onto a backlog." — [S58], Bets, Not Backlogs
- **C436** [quoted] Shape Up: stale lists of old ideas create a false feeling of being behind — "Backlogs are big time wasters too." — [S58], Bets, Not Backlogs
- **C437** [quoted] Shape Up keeps memory in decentralized per-person lists that are not inputs to planning — "There’s no one backlog or central list and none of these lists are direct inputs to the betting process." — [S58], Decentralized lists
- **C438** [quoted] Shape Up says a tiny team can throw out most of the structure — "For these reasons, a tiny team can throw out most of the structure." — [S59], Small enough to wing it
- **C439** [quoted] A practitioner warns that Next/Later items placed casually pull work toward them, and recommends an explicit Not doing section — "if you have put lots of things in your Next or Later column because it was the easy thing to do, people all over the organisation are probably now working on them." — [S60], body
- **C441** [quoted] GitHub Projects' roadmap layout positions items by date or iteration fields; without them it has nothing to place — "Roadmaps use your custom date and iteration fields to position your issues, pull requests, and draft issue" — [S62], intro
- **C442** [quoted] GitHub roadmap layout can draw milestone markers — "You can configure vertical markers on a roadmap to show your iterations, the dates of items in your project, and the milestones associated with items in your project." — [S62], Configuring markers
- **C443** [inference] A GitHub Projects roadmap view would be empty-ish for us: 0 of 67 jarvis and 2 of 45 redrobot milestones carry due dates, and redrobot already dropped its board as unread by agents — from [C408], [C418], [C419], [C441]
- **C444** [quoted] An agent-maintained living plan file grows until it must be compacted; one practitioner cut it 28,357 to 8,332 words by paging settled history out to linked files — "The Payoff: 28,357 Words Down to 8,332" — [S63], Payoff
- **C445** [quoted] Same author: most of a living plan is settled history that need not be loaded each session — "The other 80% is settled history." — [S63], body
- **C446** [quoted] A tool that renders a Markdown roadmap from a repo's milestones and issues exists: indexzero/roadmap (2013) — "Generates a `README.md` file from all milestones and issues in a given Github repository." — [S64], project README
- **C447** [inference] The forms that survive frequent change share one property: the roadmap is either a by-product of work already being done (storytold: agents edit it in the work PR; generated from milestones) or carries no dated promises (Now-Next-Later, Shape Up bets); our two dead roadmaps were separate hand-kept artifacts with dated or checkbox detail — from [C401], [C415], [C416], [C425], [C432], [C435], [C446]
- **C448** [inference] craft-anything shows the cost side of an agent-maintained roadmap: at team scale it becomes a 300 KB task board needing a wholesale rebuild and a history file, which echoes the "living plan got fat" pattern — from [C427], [C428], [C430], [C444]

## Disconfirming evidence

- For C106 and C124 (advisory keeps main broken): q `"merge first" OR "optimistic merging" post-merge CI revert bot main broken lessons why we made CI checks required again` → only C133 argues for merge-first, scoped to small low-risk OSS, with tests still run locally; no source found reporting a reliable main under pure advisory CI at high throughput. Google C126 is the nearest counter: blocking all commits on red CI is "probably misguided".
- For C110 (required gating fixes red main): same query; Trunk docs (snippet) say optimistic merging breaks down above ~5% flake rate; Walmart (snippet) reports sequential merge keeps main green. Nothing against.
- For C134, counter to urgency: at 2-5 engineers breakage is ~1/130 merges, "rare enough to fix by hand" - supports advisory for low-concurrency repos. Answered by C135 (agents raise concurrency) - inference, not measured on redrobot.
- On C205, C207 (AutoCraft breaker works): `search/issues repo:storytold/autocraft breaker` → 0; no public trip record; breaker 2 weeks old (C215). Against: false-positive exposure on a flaky main (C217); a test-repo false trip was designed out (C210).
- On C233 (rollback reason = no breaker): grep for rollback/manual merge in decisions → none (L2-M5); records show the lane frozen for its record (1 success) and wedged runs (C218) and agent merge still live (C234). The user's framing is not supported by the documents read.
- On C241-C245 (automatic stop-the-line): search "automatic tree closure false positives flaky tests" → Chromium moved test failures off auto-closure to triage (search snippet only, not read); Fuchsia and Skia add consecutive-failure and grace guards (C244, C245).
- AI auto-merge incidents: search "AI coding agent auto-merged its own pull request broke production" → blogs and unverified accounts only (C251); one vendor-documented review miss (C248).
- For C305 (Rust highest on Multilingual) — query "Multi-SWE-bench results by language Rust Python resolved rate" → counter C308, C309, C311 (Rust well below Python). Query "LLM code generation Rust lower pass rate than Python benchmark borrow checker" → counter C332, C333; partial support C334.
- For C313/C314/C331 (types help agents) — query "Python type hints pyright strict LLM agent bugs reduced study versus untyped Python" → no controlled pyright-vs-untyped study found; C331 is the closest. Counter C319 (green build, wrong code).
- For C320/C322 (migrations now cheap) — query "Bun Rust rewrite unsafe blocks criticism" → snippet only (its claim was removed in audit: the unsafe-block count is not on the page); query "\"rewrite in Rust\" regret moved back to Python postmortem" → no Rust-to-Python reversal postmortem found; regrets found were team velocity and error-type churn (blog/Medium, not cited).
- For C335 (compile cost) — query "Rust compile times slow AI coding agent iteration loop" → no measured token/time cost of compile loops found; only Cursor anecdote.
- For C415/C447 (living roadmaps die without in-PR upkeep). Query: in-repo counterexample → craft-anything ROADMAP.md is alive at ≥100 commits/month (C430), but it is the agents' mandated work queue (C429), so it supports rather than refutes the by-product mechanism.
- For C432/C433 (Now-Next-Later suits fast change). Query "Now Next Later roadmap criticism problems later column becomes dumping ground" → implied promises of Next/Later items (C439); mostly blogs, no study. Also vendor bias: C432-C434 come from the tool's seller.
- Roadmap needed at all for a solo dev. Query "solo developer stopped maintaining roadmap waste of time indie hacker" → only weak forum posts ("80% of your roadmap is a waste"); strongest counter is Shape Up: no backlog, tiny teams drop structure (C435-C438).
- For C441/C443 (GitHub Projects roadmap view). No search run against it beyond the docs; redrobot's own board abandonment (C418) is the adverse evidence.
- For C444 (living plan growth). Query "coding agents maintain ROADMAP.md or PLAN.md living plan file" → OpenAI PLANS.md/ExecPlan pattern is task-scoped (one multi-hour task), not a long-horizon roadmap; no counter found for growth.

## Coverage

| Channel | Read | Gap |
|---|---|---|
| Users | practitioner write-ups on optimistic merging, a Rust tool built with an AI, Mergify's port, living-plan compaction [S9], [S42], [S44], [S63]; photocraft "Fix main" PR titles (L1-M4) | no Hacker News thread read; the agent auto-merge incident found is an unverified blog [S34] |
| Specialists | Google SWE book ch. 23, Chromium/Mozilla/Fuchsia/Prow/bors docs and source, SRE workbook, GitHub docs, AutoCraft source and pipeline doc, storytold roadmaps and AGENTS.md, corrode migration guide, Shape Up | no first-hand account of AutoCraft's breaker in operation |
| Data | Uber EuroSys '19 paper, Meta predictive test selection, SWE-bench Multilingual, Multi-SWE-bench, type-constrained decoding and type-error repair papers; own gh measurements of photocraft main, AutoCraft history, our repos' languages, roadmaps and milestones | no controlled study of strict-typed vs untyped Python for agent bugs; no measured compile-loop cost; photocraft "time red" is a commit sample, not time-weighted |
| Adversarial | photocraft main repairs (L1-M4); AI review miss [S33]; Now-Next-Later critique [S60]; redrobot board abandonment (L4-M11) | no "why we made CI checks required again" post-mortem; no Rust-to-Python reversal post-mortem; no verified post-mortem of an agent auto-merge incident |

Declared overruns: every sub-question went past the ceiling of three full page reads (Q1 ~8, Q2 ~10 primary-source reads, Q3 and Q4 several each), because each read was a primary source the sub-question named and still added quotable rules. Q3 ran 9 searches against a ceiling of 4, three of them disconfirming. Q1 made ~52 gh API calls against a budget of ~50. No Actions run or job history was read. Graydon's post was read through web.archive.org because the live site timed out. Measurement ids are prefixed with their ledger, L<n> for the ledger of Q<n>.

## Own measurements

<!-- ledger Q1 -->
### L1-M1

photocraft main rules. `gh api repos/storytold/photocraft/rules/branches/main` → only org ruleset 26661234: `deletion`, `non_fast_forward`, `pull_request` (required_approving_review_count 0). No `required_status_checks` rule. `branches/main/protection` → 404 (no classic protection readable).

### L1-M2

25 most recent commits reachable from main (`commits?sha=main&per_page=25`, window 2026-11-18 11:06–17:01Z), check-runs per SHA (`commits/<sha>/check-runs`), script q1_main_checks.sh, raw q1_main_checks.tsv. Result: 9/25 SHAs had no check-runs (commits from merged PR branches, not main tips). Of 16 with runs: 7 had ≥1 failed run (0376ac1a, 750129f0, d039f542, b4511d21, 9e934c6e, 6bbe4cc1, 435d6e5a); 4 still in progress with no failure; 5 only cancelled/superseded. The primary Linux check `gate / gate (ubuntu-24.04)` concluded on 4 SHAs: failure 3 (435d6e5a, 750129f0, 0376ac1a), success 1 (b4511d21). Failing checks included windows unit/integration, web build and wasm size gate, corpus tests, SonarCloud, FreeBSD. Caveat: check-runs are per SHA, not per branch, so a run may come from a PR-branch push of the same SHA.

### L1-M3

second window, 12 commits up to 2026-11-11T12:00Z (q1_main_checks2.sh): gate concluded on 8 SHAs: success 5, failure 3 (995ce3ad, 36bfc50f, 9908ce96). 4 SHAs had a single run only. Same window holds "Fix main: gradient alert expectation…" (a5721856) and merges of PR #13128 "Fix main: duplicate TIFF tag constants and clippy after the 11-11 merges".

### L1-M4

search API total_count (`gh api -X GET search/issues -f q=...`): `is:pr in:title "fix main"` → 29; `in:title "main is red"` → 5; `in:title "fixes main"` → 8; merged PRs since 2026-10-08 → 4150. Titles include #15474 "Fix main's CI: gate, scorecard, Windows test build, web build" (merged 11-17), #15595 (closed 11-18, same subject), #5946 "Fix main: two ui-egui tests broken by concurrent landings", #4304 "Fix main and unblock the release: …" (open since 10-12), #3821 "ci: fix main's red test, corpus and web size gate jobs".

<!-- ledger Q2 -->
### L2-M1

`gh api repos/storytold/autocraft/git/trees/main?recursive=1 --jq '.tree[].path'` → 1094 paths; no file named breaker/circuit. `gh api search/code q='tripped repo:storytold/autocraft'` → src/outside.ts, src/core/gates.ts, src/push-outcomes.ts, src/core/push-outcome.ts (+25 more). Raw files fetched via raw.githubusercontent.com into rs3/ac/.

### L2-M2

`gh api repos/storytold/autocraft/commits?path=src/core/push-outcome.ts` → 2 commits, both 2026-11-04: b69e9fe2 "Record the required-check outcome of every push of ours and trip a stage after repeated breakage", 842ba161. Repo created_at 2026-11-05T03:30:48Z. `search/issues q='repo:storytold/autocraft breaker'` → total_count 0. Commit 66291305 (2026-11-05): test-repo merge breaker.

### L2-M3

`grep -i revert ac/pipeline.md` (docs/pipeline.md, 230,084 bytes) → no lines.

### L2-M4

`grep -iE 'circuit|breaker|kill.?switch|stop the line|error budget|tide|bors|submitqueue|tree clos' docs/research/afk-orchestration-external-2026-10-06.md` (jarvis @ d5c93cd7) → no output.

### L2-M5

grep jarvis docs/decisions/2026-Q3.md (0 auto-merge hits), 2026-Q4.md and memory-store decisions.md for "manual merg / roll(ed) back / auto-merge" → no rollback entry; only feedback_reliability_not_strictness.md (2026-11-18, the user's words). `gh api -H raw repos/SergazyNarynov/redrobot/contents/AGENTS.md`, grep → line 144 "## Merge denylist", line 146 "An agent merges a PR itself when its `Risk:` line says LOW or MEDIUM". `gh api repos/Osasuwu/jarvis --jq .allow_auto_merge` → true. redrobot tree (4678 paths, 396 under docs/decisions or docs/plans); files named "breaker" are ломатель (adversarial agents).

<!-- ledger Q3 -->
### L3-M1

`gh api repos/<repo>/languages` (2026-11-18). jarvis: Python 1,454,675 B; PLpgSQL 81,502; PowerShell 16,593; JavaScript 4,083. redrobot: Python 15,371,712 B; TypeScript 687,323; Shell 81,587; CSS 32,517; PowerShell 26,276; Cuda 8,961; Dockerfile 5,074.

### L3-M2

`q3_tree.py` (git trees API, recursive, not truncated). jarvis: 174 .py files, 1.65 MB, of which tests 109 files/1.05 MB, scripts 42/346 KB, .github 12/198 KB, agents 8/46 KB; non-code .md 206 files, .sql 31. redrobot: 1,026 .py files, 15.5 MB; tests 585/6.97 MB, scripts 212/3.43 MB, redrobot/sandbox 57/2.15 MB, planning 21/540 KB, ui 32/504 KB, driver 22/476 KB, leveling 16/244 KB, calibration 14/171 KB, cli 13/119 KB, vision 7/57 KB; plus 77 .tsx + 51 .ts (frontend).

### L3-M3

redrobot `pyproject.toml` deps: numpy, scipy, shapely>=2.0, scikit-image, trimesh, matplotlib, Pillow, PyYAML, pydantic, numba>=0.68; extras gpu = warp-lang>=1.12, cupy-cuda12x; ui = fastapi, uvicorn, websockets, python-multipart, starlette, anyio; dev = pytest(+cov, asyncio, timeout, xdist), ruff, bandit, pip-audit. No vendor robot SDK listed.

### L3-M4

`q3_imports.py` on redrobot modules: driver/borunte_robot.py (135 KB) imports only stdlib (socket, json, threading, …) and says "через TCP/JSON протокол … Основано на: Borunte Remote Communication Protocol Manual V1.0_2023.8.1"; driver/protocol.py stdlib only; vision/scan_to_heightmap.py imports numpy, scipy, trimesh; sandbox/sand_fast.py imports numba, numpy, ctypes.

<!-- ledger Q4 -->
### L4-M1

`git log --all --diff-filter=AD --name-status -- '*oadmap*' ...` in jarvis → docs/roadmap.md A 1e304db4 (2026-01-16), D 05f16aed (2026-03-23); 30677d36 2026-03-21 "docs: pivot project to OpenClaw platform architecture" touched it. `git show 05f16aed^:docs/roadmap.md` header: "## Current: P1 — OpenClaw Migration + PM Skills" / "## Next: P2 — Research Skills"; 57 lines.

### L4-M2

jarvis docs/PROJECT_PLAN.md (HEAD): "> **Active development now follows GitHub milestones (sprints), not a static plan.**" and "History: this file used to hold pillar-by-pillar status and full scope (v7.0, 2026-04-13). Replaced with pointer 2026-04-28 after the redesign consolidated scope/architecture and live work moved to GitHub milestones." docs/VISION.md:197 "Pillars are narrative organization for Vision. Structural code-architecture work is done via capability units (caps) and sprint milestones — pillars themselves don't gate implementation."

### L4-M3

`git show 708339ac` (2026-04-15) "refactor: replace percentage tracking with accomplishment log … qualitative labels (Not started → Early → Active → Mature) instead of false-precision percentages". 524894ac 2026-04-08 "feat(goals): implement goals system — Pillar 1 of Jarvis 2.0". fc1052dd 2026-09-07 deletes goals among "13 zero-call skills". 7fadc251 2026-09-08 demolish memory-stack + supabase memory tables. scripts/weekly_release_engine.py:181 "`goal_list()` (formerly backed by the `mcp__memory__goal_list` tool, retired in #1801)".

### L4-M4

memory-store osasuwu/jarvis/MEMORY.md line 3: "Outcomes and goals are intentionally not migrated (out of scope per #1790)."

### L4-M5

`git clone https://github.com/Osasuwu/jarvis.wiki.git` → Home.md, Project-Plan.md, Vision.md; `git log` 2 commits, latest ef868e3 2026-04-08. Project-Plan.md: "> **Status: needs update for Vision 2.0.** This plan (v6.0, 2026-03-31) predates the Vision document."

### L4-M6

`gh api repos/Osasuwu/jarvis/milestones?state=all --paginate` → q4_jarvis_milestones.tsv: 67 rows, 63 closed / 4 open, 0 with due_on; created by month 03:8 04:24 05:10 06:7 07:11 08:5 09:1 10:1.

### L4-M7

`gh api search/issues?q=repo:Osasuwu/jarvis+is:issue+is:open+no:milestone` total_count 5; same without no:milestone → 51.

### L4-M8

memory-store osasuwu/jarvis/decisions-archive.md lines 57,58,62 (2026-09-24 retirements of milestones 51, 60, 62); line 57 "the issues' own kill criterion set a go/no-go for 2026-09-23 that passed with no progress".

### L4-M9

redrobot `git log origin/master -- docs/MASTER_PLAN.md docs/PROJECT_PLAN.md`; `git show 0a56368a` 2026-04-09 "chore: migrate to agile — remove epics … epics replaced by milestones … 1-week sprints … Archive MASTER_PLAN.md to docs/archive/ (replaced by backlog)".

### L4-M10

redrobot `git log --date=format:%Y-%m -- docs/ROADMAP_UC1.md | uniq -c` → 07:19, 08:40, 10:1, 11:1; last docs(roadmap) commit aa61ff05 2026-08-21; f0080677 2026-08-19 "docs(roadmap): sync 8 stale checkboxes". Header: "**Живой документ**: обновлять при закрытии узлов трека". docs/plans/core-convergence-round*.md first commits 2026-09-08 (round, round-3), round-6 2026-10-06.

### L4-M11

memory-store sergazynarynov/redrobot/decisions-archive.md:461 (2026-09-17): "principal decided the Project board is not migrated at all ("доска давно не использовалась… агент её не читает… попробовал — не зашло")"; project-sync.yml deleted, board mentions rewritten to "active milestones".

### L4-M12

`gh api repos/SergazyNarynov/redrobot/milestones?state=all --paginate` → q4_rr_milestones.tsv: 45 rows, 33 closed / 12 open, 2 with due_on.

### L4-M13

`gh api repos/storytold/photocraft/commits?path=docs/roadmap.md&per_page=100` → 68 commits; months 2026-09:1, 10:61, 11:6; 29 author names; jq count of messages matching Co-Authored-By Claude/Codex/Copilot/GPT/anthropic/openai → 33.

### L4-M14

`gh api repos/storytold/craft-anything/contents/docs/ROADMAP.md` raw → `wc -l -c` 3422 lines, 306908 bytes; commits?path=docs/ROADMAP.md&per_page=100 → 100 dated 2026-11.

## Open questions

- Q2 — no new information — which autonomous-merge attempt the user rolled back to manual merging, and why. The documents read record none [C233]; settled by the user naming the repo and date, or the PR or commit that turned it off.
- Q2 — no new information — how often AutoCraft's breaker trips, and on what. It is two weeks old and its trips live in a local table [C215]; the flaky-main false-trip exposure [C217] is untested.
- Q1 — ceiling — how much of the time photocraft's main is red, time-weighted. The two commit samples [C102], [C103] are per SHA; settled by a time series of the default branch's combined status.
- Q1 — not measured — how often redrobot and jarvis main turn red after a green PR today, which is the baseline any CI relaxation must be measured against. redrobot's 2026-10-14 critic counted 3 of 35 master failures as integration after a green PR [C230].
- Q3 — no new information — no controlled study of strict-typed (pyright strict) vs untyped Python for agent-written bugs; no measured cost of compile time in Rust agent loops [C335].
- Q4 — no new information — whether the "something else" that replaced the roadmaps was milestones alone or milestones plus the goals system [C405], [C408]; settled by the user.
- Q1 — removed in audit — whether redrobot can use GitHub's merge queue: the claim that it is a User-owned private repo had no ledger entry; settled by recording `gh api repos/SergazyNarynov/redrobot --jq .owner.type,.private` and its plan.
- Q2 — not checked — redrobot's 2026-10-14 decision [S22] reverses an earlier rule to merge on red and fix later; whether that is the rollback the user meant is unread; settled by the user, or by reading that decision's history section.
- Q2 — source blocked — no verified account of an agent auto-merge incident: [S34] returned 403 [C251]; settled by a primary post-mortem of an agent merging its own PR.
- Q3 — prior only — that numba and Warp have no Rust port or drop-in equivalent [C337] was not fetched; settled by checking Rust GPU-kernel and JIT crates against redrobot's sandbox/sand_fast.py and its Warp kernels.
- Label verdict open — Q2's premise (which rollback the user meant, and why) is unresolved and would change the breaker framing; Q1's split has no measured redrobot/jarvis post-green-PR red rate to compare against; settled by the user naming the rollback and a measurement of master's red rate after green PRs.
- Next runs, proposed (not researched here): (1) GitHub plan question for redrobot if checks stay required — merge queue and rulesets by plan; (2) test-impact selection for pytest suites (pytest-testmon and similar) measured on redrobot's CI.

## Sources

- [S1] https://lethain.com/static/blog/2019/eurosys19uber.pdf — passage
- [S2] https://graydon2.dreamwidth.org/1597.html — passage
- [S3] https://abseil.io/resources/swe-book/html/ch23.html — passage
- [S4] https://chromium.googlesource.com/chromium/src/+/HEAD/docs/gardener.md — passage
- [S5] https://chromium.googlesource.com/chromium/src/+/HEAD/docs/infra/cq.md — passage
- [S6] https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets — passage
- [S7] https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks — passage
- [S8] https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue — passage
- [S9] https://dev.to/dmerejkowsky/optimistic-merging-in-practice-1j4a — passage
- [S10] https://mergify.com/blog/state-of-merge-queues-2026 — passage
- [S11] https://arxiv.org/abs/1810.05286 — passage
- [S12] https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/merging-a-pull-request-with-a-merge-queue — passage
- [S13] https://raw.githubusercontent.com/storytold/autocraft/main/src/core/push-outcome.ts — passage
- [S14] https://raw.githubusercontent.com/storytold/autocraft/main/src/push-outcomes.ts — passage
- [S15] https://raw.githubusercontent.com/storytold/autocraft/main/src/mainci/classify.ts — passage
- [S16] https://raw.githubusercontent.com/storytold/autocraft/main/docs/pipeline.md — passage
- [S17] https://raw.githubusercontent.com/storytold/autocraft/main/src/core/gates.ts — passage
- [S18] https://github.com/Osasuwu/jarvis/blob/main/docs/decisions/2026-Q4.md — passage
- [S19] https://github.com/Osasuwu/jarvis/blob/main/docs/research/afk-orchestration-retrospective-2026-10-06.md — passage
- [S20] https://github.com/Osasuwu/jarvis/blob/main/docs/research/afk-orchestration-external-2026-10-06.md — passage
- [S21] https://github.com/SergazyNarynov/redrobot/blob/master/docs/decisions/2026-11-04-agents-md-merge-denylist.md — passage
- [S22] https://github.com/SergazyNarynov/redrobot/blob/master/docs/decisions/2026-10-14-red-is-not-merged.md — passage
- [S23] https://github.com/SergazyNarynov/redrobot/blob/master/docs/decisions/2026-10-22-runner-outage-no-merge-interim.md — passage
- [S24] https://github.com/SergazyNarynov/redrobot/blob/master/docs/decisions/2026-11-11-breaker-agents-execute-before-and-after-merge.md — passage
- [S25] https://sre.google/workbook/error-budget-policy/ — passage
- [S26] https://raw.githubusercontent.com/kubernetes-sigs/prow/main/site/content/en/docs/components/core/tide/_index.md — passage
- [S27] https://raw.githubusercontent.com/kubernetes-sigs/prow/main/site/content/en/docs/components/core/tide/config.md — passage
- [S28] https://raw.githubusercontent.com/rust-lang/bors/main/src/bors/handlers/help.rs — passage
- [S29] https://chromium.googlesource.com/chromium/src/+/refs/tags/78.0.3890.0/docs/sheriff.md — passage
- [S30] https://raw.githubusercontent.com/mozilla-firefox/firefox/main/testing/docs/automated-testing/tree-closure.md — passage
- [S31] https://fuchsia.googlesource.com/infra/recipes/+/refs/heads/main/recipes/tree_closer.py — passage
- [S32] https://blog.acolyer.org/2019/04/18/keeping-master-green-at-scale/ — passage
- [S33] https://getunblocked.com/blog/copilot-autofix-snowflake-incident/index.md — passage
- [S34] https://pub.towardsai.net/how-an-ai-coding-agent-leaked-our-secret-keys-and-how-we-stopped-it-c1a86c63a6d6 — snippet only
- [S35] https://www.swebench.com/multilingual.html — passage
- [S36] https://arxiv.org/html/2504.02605v1 — passage
- [S37] https://arxiv.org/pdf/2504.02605 — passage
- [S38] https://arxiv.org/abs/2504.09246 — passage
- [S39] https://github.blog/ai-and-ml/llms/why-ai-is-pushing-developers-toward-typed-languages/ — passage
- [S40] https://arxiv.org/abs/2608.00661 — passage
- [S41] https://arxiv.org/html/2512.02567v2 — passage
- [S42] https://dev.to/extractdata/the-compiler-caught-a-lot-it-didnt-catch-enough-17ln — passage
- [S43] https://claude.com/blog/ai-code-migration — passage
- [S44] https://julien.danjou.info/blog/i-shipped-rust-i-cant-write-rust/ — passage
- [S45] https://www.devclass.com/devops/2026/07/15/zig-creator-calls-buns-claude-rust-rewrite-unreviewed-slop/5271749 — snippet only
- [S46] https://corrode.dev/learn/migration-guides/python-to-rust/ — passage
- [S47] https://arxiv.org/abs/2606.01522 — passage
- [S48] https://arxiv.org/html/2607.13820v1 — passage
- [S49] https://arxiv.org/pdf/2411.13990 — passage
- [S50] https://dev.classmethod.jp/en/articles/claude-code-4-languages-comparison/ — passage
- [S51] https://visdom-maturity-matrix.virtuslab.com/guides/infrastructure/compilation-bottleneck-eliminated-via-crate-module-architect — passage
- [S52] https://users.rust-lang.org/t/announcing-numr-a-batteries-included-numerical-library-for-rust-numpy-gpu-autograd/138053 — passage
- [S53] https://github.com/storytold/photocraft/blob/main/docs/roadmap.md — passage
- [S54] https://github.com/storytold/photocraft/blob/main/AGENTS.md — passage
- [S55] https://github.com/storytold/craft-anything/blob/main/docs/ROADMAP.md — passage
- [S56] https://github.com/storytold/craft-anything/blob/main/AGENTS.md — passage
- [S57] https://prodpad.com/blog/invented-now-next-later-roadmap/ — passage
- [S58] https://basecamp.com/shapeup/2.1-chapter-07 — passage
- [S59] https://basecamp.com/shapeup/4.1-appendix-02 — passage
- [S60] https://public.digital/2021/06/09/why-your-roadmap-should-have-a-not-doing-section — passage
- [S61] https://www.savio.io/product-roadmap/now-next-later-roadmaps/ — snippet only
- [S62] https://docs.github.com/en/issues/planning-and-tracking-with-projects/customizing-views-in-your-project/customizing-the-roadmap-layout — passage
- [S63] https://www.stephanmiller.com/the-living-plan-got-fat-compacting-a-doc-that-wont-stop-growing/ — passage
- [S64] https://awesome.ecosyste.ms/projects/github.com%2Findexzero%2Froadmap — passage

## Audit

| Claim | Verdict | Note |
|---|---|---|
| C101 | SUPPORTED |  |
| C102 | SUPPORTED |  |
| C103 | SUPPORTED |  |
| C104 | PARTIAL | title searches carry no date filter; 'since ~2026-10-08' and the per-100-merges ratio dropped |
| C105 | SUPPORTED |  |
| C106 | PARTIAL | '640 PR/week' and 'large share of time' are not in the premises; restated on the two per-SHA samples and forward-fix PRs |
| C107 | SUPPORTED |  |
| C108 | PARTIAL | source conditions the 5%/40% on concurrent and potentially conflicting changes; added |
| C109 | SUPPORTED |  |
| C110 | SUPPORTED |  |
| C111 | PARTIAL | 'Uber's metric is time-green' is not in the quote; kept only the Single-Queue 80x/129x/132x figures |
| C112 | SUPPORTED |  |
| C113 | SUPPORTED |  |
| C114 | SUPPORTED |  |
| C115 | SUPPORTED |  |
| C116 | SUPPORTED |  |
| C117 | SUPPORTED |  |
| C118 | SUPPORTED |  |
| C119 | SUPPORTED |  |
| C120 | PARTIAL | source says most teams cut at green head; claim narrowed |
| C121 | SUPPORTED |  |
| C122 | SUPPORTED | the '1.' is the page's rendered list numbering |
| C123 | PARTIAL | quote does not call the CQ a 'required pre-land gate'; restated as what a closed tree does |
| C124 | PARTIAL | premises cover Google TAP and Chromium only, not 'every primary source'; narrowed |
| C125 | SUPPORTED |  |
| C126 | PARTIAL | the same passage still expects CI failures to be investigated; added |
| C127 | SUPPORTED |  |
| C128 | PARTIAL | quote shows only that Restrict file paths blocks pushes, not that rulesets lack a path condition on checks; narrowed |
| C129 | SUPPORTED |  |
| C130 | PARTIAL | 'not a native ruleset feature' rested on C128's dropped part; restated on C129's Pending vs Success behaviour |
| C131 | SUPPORTED |  |
| C132 | SUPPORTED |  |
| C133 | PARTIAL | source says small or medium projects doing nothing too security-sensitive, author re-runs linters and tests; 'explicitly' and 'OSS' dropped |
| C134 | SUPPORTED |  |
| C135 | PARTIAL | redrobot's '43-134/week' and 'not head count' are not in the premises; narrowed to odds rising with concurrent changes, redrobot unmeasured |
| C136 | SUPPORTED |  |
| C137 | PARTIAL | source says 'in some days', not a day; fixed |
| C138 | SUPPORTED |  |
| C139 | PARTIAL | premises are Google's recipe and 'hermetic' is not in them; narrowed |
| C140 | SUPPORTED | snippet; page read (Who can use this feature?), relabelled quoted with the passage |
| C141 | UNSUPPORTED | no L1-M5 entry under Own measurements; removed with its references |
| C201 | SUPPORTED | both pieces present in S13 lines 12-13; the checker joins the ' / ' pieces into one string |
| C202 | PARTIAL | 'not per repo' is not in the quote (test repos are scoped per repo, C209); dropped |
| C203 | SUPPORTED |  |
| C204 | SUPPORTED |  |
| C205 | SUPPORTED |  |
| C206 | SUPPORTED |  |
| C207 | SUPPORTED |  |
| C208 | SUPPORTED |  |
| C209 | SUPPORTED |  |
| C210 | SUPPORTED |  |
| C211 | SUPPORTED |  |
| C212 | SUPPORTED |  |
| C213 | SUPPORTED |  |
| C214 | SUPPORTED |  |
| C215 | PARTIAL | the stage_trips table is not in the L2-M2 ledger; parenthetical dropped |
| C216 | SUPPORTED |  |
| C217 | PARTIAL | 'does not consult the flaky-rerun classification' was not checked; dropped, rests on the single-event trip |
| C218 | PARTIAL | the quoted why is the lane's record and wedged runs, not 'volume'; fixed |
| C219 | PARTIAL | the decision guards redrobot tier-1/protected-file merges with a prompt and keeps gates, not 'only irreversible diffs'; fixed |
| C220 | SUPPORTED |  |
| C221 | SUPPORTED |  |
| C222 | SUPPORTED |  |
| C223 | SUPPORTED |  |
| C224 | SUPPORTED |  |
| C225 | SUPPORTED |  |
| C226 | SUPPORTED |  |
| C227 | PARTIAL | '378 claims' and 'hold-vs-revert only' are not in the L2-M4 output; dropped, grep term list restated |
| C228 | SUPPORTED |  |
| C229 | PARTIAL | source says jarvis skills refused redrobot merges without the heading, so the 17.10 permission was not carried out; 'LOW/MEDIUM granted' dropped. Conflicts with S18's 2026-10-17 'the agent merges its own PRs' |
| C230 | SUPPORTED |  |
| C231 | PARTIAL | rule is interim until 2026-11-07, status proposed; added |
| C232 | SUPPORTED |  |
| C233 | SUPPORTED |  |
| C234 | PARTIAL | 'on green' and the interpretive sentence are not in the L2-M5 output; dropped |
| C235 | SUPPORTED | 'P01' in the quote is 'P0' plus footnote marker 1 as rendered |
| C236 | SUPPORTED |  |
| C237 | SUPPORTED |  |
| C238 | SUPPORTED |  |
| C239 | PARTIAL | doc does not say human-placed or 'no automatic trip'; restated as the open blocker-label issue, branch-scoped by tokens |
| C240 | SUPPORTED |  |
| C241 | SUPPORTED |  |
| C242 | SUPPORTED |  |
| C243 | SUPPORTED |  |
| C244 | SUPPORTED |  |
| C245 | SUPPORTED | the comment is split across '#' lines in the source; checker misses the join |
| C246 | SUPPORTED |  |
| C247 | SUPPORTED |  |
| C248 | SUPPORTED |  |
| C249 | PARTIAL | weekly-read is not in its from-list (C224 not named); narrowed to redrobot's nightly breaker agents |
| C250 | PARTIAL | Tide holds while the blocker issue is open, not a human resume; AutoCraft 'only stops' needs C216, added to from-list |
| C251 | UNCHECKABLE | S34 returns 403 to curl with a browser user agent; snippet only |
| C301 | SUPPORTED |  |
| C302 | PARTIAL | 'library package ~4.9 MB' is not in L3-M2; dropped |
| C303 | SUPPORTED |  |
| C304 | SUPPORTED |  |
| C305 | SUPPORTED | both pieces present; checker joins ' / ' pieces |
| C306 | SUPPORTED |  |
| C307 | PARTIAL | 'carry wide error' is not in the source; dropped |
| C308 | SUPPORTED | both pieces present; checker joins ' / ' pieces |
| C309 | SUPPORTED |  |
| C310 | PARTIAL | 'confounds language with difficulty' is not in the quote; restated as the quote. HTML text doubles numbers ('200 200'), so the checker misses it |
| C311 | PARTIAL | snippet; PDF read via pdftotext, relabelled quoted with the Table 4 row; restated as MagentLess ranges Python 36.2-48.2% vs Rust 5.0-7.1%, attribution parenthetical dropped |
| C312 | SUPPORTED |  |
| C313 | SUPPORTED |  |
| C314 | SUPPORTED |  |
| C315 | PARTIAL | the study is not tied to TypeScript in C314/S39; '(TypeScript)' dropped |
| C316 | SUPPORTED |  |
| C317 | SUPPORTED | snippet; passage read in arXiv HTML v2 Introduction, relabelled quoted, S41 URL set to v2 |
| C318 | SUPPORTED |  |
| C319 | SUPPORTED | both pieces present; checker joins ' / ' pieces |
| C320 | SUPPORTED |  |
| C321 | SUPPORTED |  |
| C322 | SUPPORTED |  |
| C323 | SUPPORTED |  |
| C324 | SUPPORTED | both pieces present; checker joins ' / ' pieces |
| C325 | SUPPORTED | both pieces present; checker joins ' / ' pieces |
| C326 | SUPPORTED | both pieces present; checker joins ' / ' pieces |
| C327 | UNSUPPORTED | S45 page has the 'unreviewed slop' quote but no '13,044 unsafe blocks'; removed with its Summary sentence |
| C328 | SUPPORTED |  |
| C329 | SUPPORTED | all three pieces present; checker joins ' / ' pieces |
| C330 | SUPPORTED |  |
| C331 | SUPPORTED |  |
| C332 | PARTIAL | snippet; HTML v1 read, relabelled quoted, S48 URL set to v1; training data is offered as a 'plausible explanation' for a gap larger in smaller models; 'six models' dropped |
| C333 | SUPPORTED | snippet; PDF read via pdftotext (RQ1 results), relabelled quoted; quote trimmed where the two-column layout interleaves text |
| C334 | SUPPORTED |  |
| C335 | SUPPORTED |  |
| C336 | PARTIAL | snippet; page read, relabelled quoted; numrs2 and 'without independent maturity evidence' not on the page, dropped |
| C337 | UNCHECKABLE | prior |
| C338 | PARTIAL | 'no mature Rust equivalents' rests on C337 (prior); narrowed to a fragmented ecosystem, Warp/numba point marked unchecked |
| C339 | PARTIAL | 'three devices' and the compile-and-distribute step are not in the premises; dropped |
| C340 | SUPPORTED |  |
| C341 | UNSUPPORTED | inference names C327, which was removed; deleted, Summary bullet rewritten on C323, C328, C330 |
| C401 | SUPPORTED | re-run: 30677d36 changed 41+/41- lines of the 57-line file, read as a rewrite |
| C402 | SUPPORTED |  |
| C403 | SUPPORTED |  |
| C404 | SUPPORTED | re-run: git show 708339ac |
| C405 | SUPPORTED | re-run: fc1052dd, 7fadc251 |
| C406 | SUPPORTED |  |
| C407 | SUPPORTED |  |
| C408 | SUPPORTED |  |
| C409 | SUPPORTED | re-run: open milestones API matches |
| C410 | SUPPORTED |  |
| C411 | PARTIAL | re-run of archive lines 57/58/62: only eval v2 retired on a passed kill-criterion date; deslop for deleted tooling, competence for a series never started; fixed |
| C412 | SUPPORTED | re-run: docs/VISION.md:195 'Pillars are roadmap tracks' |
| C413 | SUPPORTED |  |
| C414 | SUPPORTED | re-run: git log and file headers confirm v1.0 2026-03-18, v2.0 deadline 2026-04-13, 0a56368a |
| C415 | SUPPORTED | re-run: created 9498c3f5 2026-07-10, rewritten 6bb22ec9 2026-07-30 |
| C416 | SUPPORTED |  |
| C417 | SUPPORTED | re-run: round plan commits from 2026-09-08; milestones #42/#44/#45 are rounds 6/7/8 |
| C418 | SUPPORTED |  |
| C419 | SUPPORTED | re-run: open milestones API matches |
| C420 | SUPPORTED |  |
| C421 | SUPPORTED |  |
| C422 | SUPPORTED |  |
| C423 | SUPPORTED |  |
| C424 | SUPPORTED |  |
| C425 | SUPPORTED |  |
| C426 | SUPPORTED |  |
| C427 | SUPPORTED |  |
| C428 | SUPPORTED |  |
| C429 | SUPPORTED |  |
| C430 | SUPPORTED |  |
| C431 | SUPPORTED |  |
| C432 | SUPPORTED |  |
| C433 | SUPPORTED |  |
| C434 | PARTIAL | the quote is one customer's testimonial (Rosslyn Analytics), not 'its users'; narrowed |
| C435 | SUPPORTED |  |
| C436 | SUPPORTED |  |
| C437 | SUPPORTED |  |
| C438 | PARTIAL | 'structure pays once coordination costs time' is not in the quote; dropped |
| C439 | SUPPORTED |  |
| C440 | UNSUPPORTED | quote not on the S61 page; removed with its references |
| C441 | SUPPORTED |  |
| C442 | SUPPORTED |  |
| C443 | SUPPORTED |  |
| C444 | SUPPORTED |  |
| C445 | SUPPORTED |  |
| C446 | PARTIAL | snippet; page read, relabelled quoted; dialogware/roadmap-generator not on the page, and 'needs no hand upkeep' is not in the quote; dropped |
| C447 | SUPPORTED |  |
| C448 | SUPPORTED |  |

Label verdict: open — Q2's premise (which autonomous merge the user rolled back, and why) is unresolved and would change the breaker framing, and Q1's split has no measured redrobot/jarvis baseline.

Quote check: reliability-autonomous-merge-stack-roadmap-2026-11-18.md: 122 quoted claim(s): 95 found, 12 NOT FOUND, 15 unfetchable, 0 no source

## Disposition

| Recommendation | State | Where |
|---|---|---|
| Reliability without full advisory CI: a split — a fast, reliable required subset (plus redrobot's safety paths), slow suites post-merge with culprit detection, reliability measured as time main is green | deferred | unfiled: a consequential, cross-repo CI decision that goes to /grill with the user first; it also needs the post-green-PR red-rate baseline from Open questions. The final message proposes the issue |
| Keep the experiments lane advisory rather than extending its rules to the main path | deferred | unfiled: decided in the same /grill as the CI split, since it is the same trade-off |
| A circuit breaker on the agent merge path (trip on a merge that reddens main, per-stage scope, flake guard, explicit resume and remedy) | deferred | unfiled: the 2026-11-11 cross-repo grill deferred breakers to a separate grill [C223]; it waits for the user to name the rollback in Open questions. The final message proposes the issue |
| Stay in Python; do not rewrite jarvis or redrobot in Rust now | landed | no change to carry: both repos stay in Python; a port is weighed again only when a concrete component needs it |
| Revive a roadmap only as a by-product of the work (edited in the work PR, generated from issue state, or undated Now-Next-Later with a Not-doing section) | deferred | unfiled: the form and the first repo are the user's call; the final message proposes the issue |
