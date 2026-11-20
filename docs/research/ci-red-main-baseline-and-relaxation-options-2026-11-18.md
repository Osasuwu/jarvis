---
topic: ci-red-main-baseline-and-relaxation-options
tags: area:process, research
source_provenance: /research invocation in session b065a837 — third run, following docs/research/reliability-autonomous-merge-stack-roadmap-2026-11-18.md (PR #2236)
status: open
audit: 2026-11-18 — 174 claims: 143 SUPPORTED, 27 PARTIAL, 3 UNSUPPORTED, 1 UNCHECKABLE
---

## Question

The user, answering which rollback to manual merging they meant, verbatim: "redrobot 14.10 rule. Но давай твои предложенные вопросы тоже посмотрим, меня он заинтересовали. И возможно сейчас у тебя появились ещё варианты?"

"Your proposed questions" are the ones the previous report left open or proposed as next runs: the baseline of how often redrobot and jarvis main turn red after a green PR; the GitHub plan / merge-queue question for redrobot if checks stay required; test-impact selection for pytest measured on redrobot's CI. "More options" is read as ways to relax pre-merge gates safely that the previous report did not weigh.

The rollback the user meant is redrobot's decision of 2026-10-14, "С красными чеками не мержим, а чиним: main всегда зелёный", which reversed an earlier unwritten rule «мержить с красным, чинить потом» (redrobot `docs/decisions/2026-10-14-red-is-not-merged.md`, read in this run). It rejected a split of required checks because the main line could not be separated ("по ощущению это «всё кроме UI»"), and its critic counted 20 of 35 master failures as runner infrastructure and 3 as integration after a green PR.

Sub-questions: Q1 — the current baseline in redrobot and jarvis: how often the default branch is red and why, how long, how much time required CI adds per PR, and which checks are required; Q2 — merge-queue options for a private and a public repo on a personal account, native and third-party, and their cost; Q3 — making the pytest CI substantially faster without dropping what it catches; Q4 — other ways to relax pre-merge gates safely (risk-tier gating, shadow transition, automatic post-merge remedies) and teams that moved between blocking and non-blocking checks.

## Summary

**Recommendation.** In redrobot, the red master in this 12-day window came mostly from timing-flaky tests in the master lane: 16 of 23 red commits [C118]. The 7 of them in tests/driver sit in tests pr-fast skips [C120]; whether PR CI runs the rest was not established. Only one red was shown to come from what PR gating lets through, a PR merged red [C124]. So the main lever for "main always green" is the master lane itself: fix or quarantine its timing-flaky tests, and make every master commit get a result. A merge queue or stricter PR gates would not have prevented most of these reds. jarvis has neither problem: its main was green on every sampled commit, and its required CI adds under a minute. Its gap is that an admin merge can pass a red required check. Each step below is a proposal for the user to weigh, not a change made.

**Baseline (Q1).**
- redrobot master was red for 12% of the time over 12.4 days: 23 of 153 commits with a result [C115].
  - Red streaks: median about 0.8 h, one of 20.2 h [C116].
- Causes of the 23 red commits [C118]:
  - 16 were timing, load or nondeterministic test failures [C119]. The 7 in tests/driver are in tests pr-fast skips [C120]; whether PR CI runs the sandbox/replay e2e and f3_p1 tests that failed was not established.
    - Two of these were test defects that later commits fixed [C121].
  - 3 were real defects with 2 distinct causes.
  - 4 were infrastructure: gitleaks hung in a git fetch until its 15-min timeout, and one artifact-upload error [C122].
  - None was self-hosted runner loss [C117]. The 2026-10-14 decision's critic counted 20 of 35 failures as runner infrastructure. That count does not describe this window, and this run did not establish why it changed [C128].
- Of the two real defects:
  - One came from merging a PR whose own pr-fast was red [C123], [C124]. That is the case the 14.10 rule "red is not merged" addresses.
  - The other most likely entered through a master commit that got no CI result, and first showed on a later docs-only commit [C125], [C126].
- 46 of 200 master commits got no checks at all [C112]. The two inspected had cancelled runs [C113], so a red commit does not identify the commit that broke master [C114].
- Throughput: redrobot merged 151 PRs in the 7 days to 2026-11-18 [C111]. Required-by-convention CI adds about 15 min per PR, mostly pr-fast and the review [C129], [C130], [C132].
- jarvis: 100 of 100 sampled main commits were green [C127]. Its 7 strict required checks finish a median 0.6 min after the first one starts [C101], [C131], [C132].
  - enforce_admins is off, and 2 of 15 sampled PRs were merged by the admin account about a minute after code-gate posted failure [C133], [C134]. In both cases that red was a code-gate timing race, not a defect.
  - Whether a human or an agent ran those merges was not established.

**Merge queue (Q2).** Neither repo can turn on GitHub's native queue as it stands:
- It needs an organization: public for free, or private on Enterprise Cloud [C201], [C211], [C212].
- redrobot has no branch protection or rulesets on its plan [C103], [C207], [C208]. Any queue there is convention only: Mergify's free hybrid mode, or a DIY serializer [C213], [C215], [C217], [C221], [C243].
- Trunk and Kodiak lean on branch protection [C223], [C232], [C237].
- On jarvis, strict required checks already work as a poor man's queue [C246], [C247].
- Two vendors say small teams with cheap-to-repair breaks may not need a queue [C244], [C245].
- Inference from [C118], [C124], [C126]: in this window no red was shown to come from two green PRs that conflict, which is the failure a queue exists for. A queue is not justified by this baseline.

**CI speed (Q3).**
- redrobot's PR lane already uses uv, 4 xdist workers, path-scoped lanes and no coverage. It defers slow and heavy_sim tests off the PR path [C302], [C303], [C305], [C316].
- What is left is the ~6 min test step and runner pickup of 0.5–7.1 min [C312], [C313]. The same suite took 6:45 to 45:00 depending on runner load [C310].
- Levers that keep every test:
  - shards or more workers per runner, bounded by that contention [C352];
  - xdist worksteal [C348];
  - a numba cache keyed per commit. Today none of the 8 kernels caches [C315], and the time saved is unmeasured [C347].
- Coverage-based test selection (testmon, Datadog TIA) is a poor fit for redrobot:
  - testmon is blind to config files and, by one project's report, inside numba kernels, and needs `--testmon-forceselect` under `-m` [C330];
  - testmon has an open false-negative bug [C325];
  - Datadog TIA is incompatible with pytest-cov and races with xdist [C332], [C333].
- jarvis CI is not a time bottleneck [C314].

**Other safe relaxations (Q4).**
- A path filter at workflow level leaves a required check Pending, so it cannot make that check conditional [C410].
- redrobot already selects checks by path: docs, frontend and hardware lanes, with heavy_sim post-merge only. So the option the 14.10 decision rejected, "block only mainline checks", is partly in place [C406], [C407], [C408].
  - Counter: ChromiumOS names path-skipped builders as one way bad changes land, and makes a check informational only as a last resort [C433], [C434].
- A shadow phase before making a check required has to be built: run it non-required and log what it would have blocked. Rulesets' Evaluate mode is Enterprise-only [C413], [C415], [C416].
  - Give the phase a fixed end date, such as Semgrep's two weeks [C419]. A vendor reports that most audit-mode policies never get enforced [C420].
- Automatic revert:
  - Google's naive culprit finder would wrongly revert 20–130 changes a day [C422]. Chromium caps auto-reverts of compile-failure culprits per day and by culprit age [C426].
  - ChromiumOS and LLVM rely on revert-first norms [C427], [C428].
  - In redrobot an auto-revert keyed on a red master would mostly hit innocent commits: most reds here are flaky tests [C118], and commits without a CI result hide the culprit [C114]. Inference from [C114], [C118], [C422]: rerun first, and revert only a commit that has its own red result.
- Quarantining a known-flaky test is GitLab's and Trunk's answer to flakes that block master. Trunk refuses to quarantine a broken (non-flaky) test [C339], [C340], [C431].
- The one team found that switched tests to advisory, D-Robotics/moss, made core tests blocking again within ~18 h. It kept platform and e2e jobs advisory, and gave no reason [C435], [C436], [C437].

## Findings

### Q1 — baseline: how often redrobot and jarvis main are red and why, for how long, CI time per PR, required checks — answered with a gap

- **C101** [measured] jarvis main has classic branch protection requiring 7 contexts (require-linked-issue, pytest, code-gate, gitleaks, waiting-human-review, risk-tier, ruff), strict (branch must be up to date), with enforce_admins disabled — Own measurements, L1-M1
- **C102** [measured] jarvis's only ruleset on main covers deletion and non-fast-forward, no status checks — Own measurements, L1-M1
- **C103** [measured] redrobot master has no readable branch protection (API 404) and rulesets are unavailable on its plan (403 "Upgrade to GitHub Pro or make this repository public"); repo is private, user-owned, allow_auto_merge=false — Own measurements, L1-M1
- **C104** [quoted] redrobot's own rules say no check is enforced: PR workflows report but do not block, and merging is a manual discipline step — "Private repo on GitHub Free — no branch protection, no auto-merge. PR workflows report but do not block; merging is a manual, disciplined step, not a gated one." — [S1], § CI/CD & Merging
- **C105** [quoted] redrobot's by-convention merge set is five PR-event workflows: CI (pr-fast), Code Review (+ Code Gate Verdict status), PR Checks, Owner Queue Guard, Gitleaks — "wait for the five PR-event workflows to go green — `CI` (job `pr-fast`: lint +" — [S1], § CI/CD & Merging
- **C106** [measured] redrobot pr-fast runs `pytest tests --ignore=tests/driver --ignore=tests/experiments -m "not slow and not heavy_sim"`; tests/driver runs on PRs only when hardware paths change (pr-fast-hardware) — Own measurements, L1-M2
- **C107** [measured] redrobot's full `not slow` suite including heavy_sim and coverage (job "Backend (pytest + coverage)") runs only on non-PR events (master push, schedule, dispatch); `-m slow` runs only on schedule/dispatch — Own measurements, L1-M2
- **C108** [measured] redrobot CI on master pushes shares one concurrency group with cancel-in-progress off, so a newer master push supersedes a pending one; gitleaks push has timeout-minutes 15 — Own measurements, L1-M2
- **C109** [measured] jarvis pytest runs the same full suite (`uv run pytest tests/`) on PRs and on main pushes, on GitHub-hosted ubuntu-latest; there is no main-only test tier like redrobot's — Own measurements, L1-M3
- **C110** [quoted] redrobot AGENTS.md asks for a manual heavy_sim run before merging PRs in heavy_sim areas instead of relying on pr-fast — "gets a manual `pytest -m heavy_sim` run before merge rather than relying on green `pr-fast` alone" — [S1], § CI/CD & Merging
- **C111** [measured] redrobot master throughput is far above 43 PRs/week now: 151 squash merges in the 7 days to 2026-11-18, 90 the week before, 84 and 56 in the two weeks before that — Own measurements, L1-M4
- **C112** [measured] Of 200 redrobot master commits (2026-11-06 to 2026-11-18, 12.4 days), 130 were green, 23 red, 1 pending and 46 had no check runs at all — Own measurements, L1-M5
- **C113** [measured] Two of the 46 commits with no checks (9a7a7ccc, bb0642dc) were inspected: their GitHub Actions suites are 'completed / cancelled' with 0 check runs, consistent with superseded master pushes — Own measurements, L1-M6
- **C114** [inference] redrobot master CI tests only about three quarters of merge commits; under bursty merging (24 merges in under 5 minutes on 2026-11-18, L1-M5) the untested share is larger, so a red commit does not identify the commit that broke master — from [C108], [C112], [C113]
- **C115** [measured] redrobot master red rate: 23 of 153 commits with a final result (15%); head-of-master red for 35.0 h of 297.7 h (12%, time-weighted) — Own measurements, L1-M5
- **C116** [measured] redrobot had 16 red streaks in 12.4 days; red-to-next-green-commit times 0.0-4.8 h except one of 20.2 h, median about 0.8 h. The figure is measured to the green commit's timestamp, so it leaves out the 10-90 min that commit's Backend run takes — Own measurements, L1-M5
- **C117** [measured] All 20 red Backend jobs ended with a test-step exit code 1 or an artifact error; none showed runner loss (no shutdown-signal or lost-communication lines in any of the 20 logs) — Own measurements, L1-M7
- **C118** [measured] Cause of the 23 redrobot red commits: 16 timing/load/nondeterministic test failures, 3 real defects (2 distinct), 4 infrastructure (3 gitleaks jobs cancelled at the 15-min timeout, 1 GitHub artifact-upload error), 0 self-hosted-runner loss — Own measurements, L1-M7, L1-M8
- **C119** [measured] Flaky detail: 6 red commits failed only on tests/driver/test_stale_reply.py; 3 (2026-11-06) on an xdist worker crash in tests/api/test_sandbox_speed_cap_e2e.py; 1 only on test_f3_p1 IK; 1 on a mock pause/resume timing bound; 5 on several timing tests at once (sandbox/replay 'did not finish in time'); two of those jobs took 52 and 89 min, against 13.1 min for one green Backend run — Own measurements, L1-M7, L3-M3
- **C120** [measured] The tests/driver flaky failures (test_stale_reply ×6, pause/resume mock ×1) are in tests pr-fast ignores; tests/driver still runs on PRs via pr-fast-hardware when hardware paths change — Own measurements, L1-M2, L1-M7
- **C121** [measured] Two of the 'flaky' tests were test defects that later commits fixed: test_stale_reply made clock-independent (8b37db3b, #3347, 2026-11-18) and the pause/resume bound made to survive CPU load (97df3199, #3429, 2026-11-18) — Own measurements, L1-M9
- **C122** [measured] One gitleaks cancellation log shows the job hanging in a git fetch (orphan git-remote-https processes terminated) before 'The operation was canceled.' at the 15-min limit — Own measurements, L1-M8
- **C123** [measured] Real defect 1: master commit 03f2b1ae (PR #3297) failed tests/ci/test_code_review_guideline_path_meta.py; master stayed red 20.2 h until 77fae165 'fixes red master (03f2b1ae)' — Own measurements, L1-M7, L1-M9
- **C124** [measured] PR #3297's own pr-fast was FAILURE and its code-review/verdict status was failure before the merge, so this red came from merging a red PR, not from integration after a green PR — Own measurements, L1-M10
- **C125** [measured] Real defect 2: tests/scripts/test_r8_volume_offset.py raised a pytest.approx TypeError on 7873a220 (docs-only) and cdf964be; 1f735fb0 (#3337), 1.3 h after the first red, fixed it but was itself red (pause/resume); master went green 1.8 h after the first red (fd0e9d9e). The last green commit before it was 17b712ea, followed by 5067b2e3 (code change, no checks run) — Own measurements, L1-M5, L1-M7
- **C126** [inference] The r8 defect most likely came in via a commit (5067b2e3) that got no master CI result and first showed on a later docs-only commit; this is the blame cost of C114 — from [C113], [C125]
- **C127** [measured] jarvis main: 100 of 100 sampled commits (2026-10-07 to 2026-11-18, 42 days) have a green check rollup; zero red streaks — Own measurements, L1-M11
- **C128** [inference] The redrobot critic's '20 of 35 failures were runner infrastructure' does not describe the current 12-day window, where runner loss is 0 of 23 and the main cause is flaky tests in the master lane — from [C118], [C117]
- **C129** [measured] redrobot: across 15 recently merged PRs, the five conventional checks finished a median 14.2 min after the first check started (p75 348.9 min, max 3254.3 min). First check to merge: median 19.8 min — Own measurements, L1-M12
- **C130** [measured] redrobot per-check medians on PR heads: pr-fast 5.8 min (max 10.8), review 5.1 min (max 8.5), gitleaks 3.8 min (max 10.5) — Own measurements, L1-M12
- **C131** [measured] jarvis: across 15 recently merged PRs, the 7 required checks finished a median 0.6 min after the first check (p75 1.5 min); first check to merge: median 5.7 min; slowest checks are review 0.7 min and pytest 0.5 min — Own measurements, L1-M12
- **C132** [inference] For jarvis, required CI adds well under a minute of machine wait per PR; what remains is gate logic (code-gate, risk-tier, waiting-human-review), not compute. For redrobot, about 15 min per PR, dominated by pr-fast and the review — from [C129], [C130], [C131]
- **C133** [measured] jarvis PRs #2230 and #2228 were merged by Osasuwu about 1 min after the required code-gate check posted failure ('code-gate: evidence-none'); no later code-gate run exists, while the review run finished green after the code-gate post — Own measurements, L1-M10, L1-M13
- **C134** [inference] Required checks on jarvis bind only non-admin merges: with enforce_admins off, the admin token merged 2 of 15 sampled PRs past a red required check. Here the red was a code-gate race (verdict posted before the review finished), not a defect — from [C101], [C133]
- **C135** [measured] Two other jarvis PRs that looked red (#2232 waiting-human-review, #2207 risk-tier) had a later successful run of the same check before the merge; the earlier red was superseded — Own measurements, L1-M13
- **C136** [measured] redrobot PRs #3421 and #3439 show code-review/verdict 'failure / evidence-none' only after the merge (posted 12-16 min after it), with 'success / evidence-clean' before; a check-rollup read alone misreads these as red merges — Own measurements, L1-M14
- **C137** [inference] Nightly results are not in this baseline: the slow suite runs only on schedule or dispatch, so its results are not part of this per-commit push baseline — from [C107], [C112]
### Q2 — merge-queue options for private and public personal-account repos, native and third-party, and cost — answered with a gap

- **C201** [quoted] GitHub's native merge queue is available only in public repos owned by an organization, or private repos owned by organizations on Enterprise Cloud — not personal-account repos, and not Team-plan private repos — "Pull request merge queues are available in any public repository owned by an organization, or in private repositories owned by organizations using GitHub Enterprise Cloud." — [S2], "Who can use this feature?" box
- **C202** [quoted] The merge queue tests each PR against the latest target branch plus PRs already queued — "The merge queue will ensure the pull request's changes pass all required status checks when applied to the latest version of the target branch and any pull requests already in the queue." — [S2], About merge queues
- **C203** [quoted] GitHub frames the merge queue as the same guarantee as strict status checks, minus the manual update-and-wait loop — "The merge queue provides the same benefits as the **Require branches to be up to date before merging** branch protection, but does not require a pull request author to update their pull request branch and wait for status checks to finish before trying to merge." — [S2], About merge queues
- **C204** [quoted] Adopting the native queue requires CI workflows to also trigger on the merge_group event — "You **must** use the `merge_group` event to trigger your GitHub Actions workflow when a pull request is added to a merge queue." — [S2], Configuring CI workflows for merge queues
- **C205** [quoted] Strict required status checks force the head branch to be up to date with base before merge; it is the default for required checks and costs extra builds — "The branch **must** be up to date with the base branch before merging. ... This is the default behavior for required status checks. More builds may be required, as you'll need to bring the head branch up to date after other collaborators update the target branch." — [S3], Require status checks before merging (Strict row)
- **C206** [quoted] Loose required checks allow status checks to fail after merge when the branch is incompatible with base — "Status checks may fail after you merge your branch if there are incompatible changes with the base branch." — [S3], Loose row
- **C207** [quoted] Protected branches (hence strict checks) are available on Free only for public repos; private repos need Pro, Team or Enterprise — "Protected branches are available in public repositories with GitHub Free and GitHub Free for organizations. Protected branches are also available in public and private repositories with GitHub Pro, GitHub Team, GitHub Enterprise Cloud, and GitHub Enterprise Server." — [S3], "Who can use this feature?" box
- **C208** [quoted] Rulesets have the same plan split: Free public only; private needs Pro/Team/Enterprise Cloud — "Rulesets are available in public repositories with GitHub Free and GitHub Free for organizations, and in public and private repositories with GitHub Pro, GitHub Team, and GitHub Enterprise Cloud." — [S4], "Who can use this feature?" box
- **C209** [quoted] GitHub Pro (personal account) adds protected branches for private repos — "Advanced tools and insights in private repositories: ... Protected branches" — [S5], GitHub Pro section
- **C210** [quoted] GitHub Team costs $4 per user/month; Enterprise $21 per user/month — "Team $4 per user/month Enterprise $21 per user/month" — [S6], plan table
- **C211** [inference] For redrobot (private, personal, Free): no native merge queue on any personal plan; Pro (or moving to a Team org) unlocks branch protection and strict checks but still no native queue — that needs an org on Enterprise Cloud, or making the repo public in an org — from [C201], [C207], [C209], [C210]
- **C212** [inference] For jarvis (public, personal): strict checks are available now on Free; a native queue requires transferring the repo to an organization (a free org suffices for a public repo) — from [C201], [C207]
- **C213** [quoted] Mergify's Free plan costs $0 for private teams of up to 5 active contributors, and there is a separate free Open Source plan — "Zero cost for open source projects and private teams of up to 5 active contributors." — [S7], JSON-LD offer "Free / Open Source"
- **C214** [quoted] Mergify's paid Max tier is $21 per seat per month — "Max $21 per seat / month" — [S7], plan cards
- **C215** [quoted] Mergify Free (private, up to 5 users) includes Merge Queue parallel checks and batching; the Open Source plan includes parallel checks but not batching — "Merge Queue Parallel Checks Open Source [YES] Free [YES] Max [YES] Enterprise [YES] Batch Open Source [NO] Free [YES] Max [YES] Enterprise [YES]" — [S7], feature comparison table (icons rendered as [YES]/[NO] by own HTML strip)
- **C216** [quoted] Mergify's default serial mode tests every PR on top of the previous one, i.e. against the exact state it merges into — "Every pull request is tested on top of the one before it, forming a single ordered pipeline. This guarantees correctness: each pull request is validated against the exact state it will merge into." — [S8], Serial mode
- **C217** [quoted] Mergify's default hybrid mode lets developers use the queue or merge manually at the same time, with no setup — "In hybrid mode, developers can use the merge queue or merge manually. Both work simultaneously. This is the default behavior and requires no setup." — [S9], Approach 1: Hybrid mode
- **C218** [quoted] Making Mergify the only merge path needs GitHub rulesets, or classic protection's push restriction — "In exclusive mode, only Mergify can merge pull requests. This is enforced using GitHub rulesets" — [S9], Approach 2: Exclusive mode
- **C219** [quoted] GitHub offers "Restrict who can push" only on organization-owned repos — "You can enable branch restrictions in public repositories owned by a GitHub Free organization and in all repositories owned by an organization using GitHub Team or GitHub Enterprise Cloud." — [S3], Restrict who can push to matching branches
- **C221** [inference] On redrobot (private, personal, Free), Mergify's queue would run in hybrid mode only: no rulesets or protection exist to force merges through it, so the merging agents must route every merge through the queue by convention — from [C207], [C208], [C217], [C218], [C219]
- **C222** [quoted] Trunk's Free plan is $0 for teams up to 5 committers, and its plan table lists the Merge Queue GitHub integration as included — "Free $ 0 / committer/month For teams up to 5 committers." — [S11], plan cards; Merge Queue rows read "Merge Queue GitHub integration &amp; support Included" in the comparison table
- **C223** [quoted] Trunk's setup assumes branch protection: push restrictions for its bot are marked required — "**Configure push restrictions (required)** Trunk Merge Queue needs permission to push to your protected branch." — [S12], Classic branch protection
- **C224** [quoted] Trunk admits a PR into the queue only once GitHub's branch protection marks it ready to merge — "Trunk doesn't admit a submitted PR for testing until GitHub considers it ready to merge. Branch protection (required reviews, required status checks, conversation resolution, etc.) is what determines when GitHub marks a PR as ready to merge" — [S12], How branch protection affects the queue
- **C225** [quoted] Trunk's install guide is written for a GitHub organization — "Admin access to your GitHub organization" — [S13], Prerequisites
- **C226** [quoted] Trunk offers predictive testing, batching, optimistic merging and parallel queues — "Test PRs against the projected future state of your main branch to catch conflicts before they reach production." — [S14], Predictive testing entry
- **C227** [inference] Trunk does not fit redrobot as-is: its admission and push model leans on branch protection that a private personal Free repo cannot have; on jarvis (public) protection exists, but personal-account support is not stated either way — from [C207], [C223], [C224], [C225]
- **C228** [quoted] Graphite's merge queue starts at the Team tier, $40 per user/month billed annually — "$ 40 $ 40 Per user/month, billed annually Start free trial Everything in Starter tier ... Merge Queue" — [S15], Team plan card
- **C229** [quoted] Graphite's free Hobby tier supports personal-account repos but has no merge queue — "Hobby Code review essentials for personal projects. Free Free Sign up Personal account repos support" — [S15], Hobby card; comparison row "Merge queue hobby : [NO] starter : [NO] team : Basic enterprise : Advanced"
- **C230** [quoted] Aviator's MergeQueue (parallel queues, batching, flaky handling) starts at Team, $20 per dev per month, up to 10 repos; the Free tier has no queue — "Team Full review and ship workflows. For teams ready to automate merging and deployment. $20 /dev/mo 14-day free trial. Everything in Free, plus: ... MergeQueue — parallel queues, batching, flaky test handling" — [S16], Team card; table row "MergeQueue — single-lane queue" shows lucide-minus for Free, lucide-check for Team (raw HTML)
- **C231** [quoted] Kodiak is free for personal use and public repos; a subscription is needed only for private org repos, $4.99 per active user per month — "Kodiak is free for personal use and public repositories, but requires a subscription for use with private GitHub Organization repositories. A Kodiak subscription is billed at $4.99 per active user per month." — [S17], Billing
- **C232** [quoted] Kodiak needs GitHub branch protection on the target branch — "GitHub branch protection must exist on the target branch." — [S18], configuration requirements
- **C233** [quoted] Kodiak updates a PR only when it is ready to merge — "Kodiak efficiently updates pull requests by only updating a PR when it's ready to merge." — [S19], Minimal updates
- **C234** [quoted] Kodiak's stated purpose is removing the manual update churn that "require branches be up to date" creates — "Enabling the &quot;require branches be up to date&quot; feature on GitHub repositories is great because, when coupled with CI, master will always be green ." — [S19], Why?
- **C235** [measured] Kodiak is maintained (last commit 2026-11-07); bors-ng is archived — Own measurements, L2-M1
- **C236** [quoted] bors-ng is deprecated and points users to GitHub's built-in merge queue — "If you want to implement a workflow like this, use [GitHub's built-in merge queue][ghmq]." — [S20], line 2
- **C237** [inference] Kodiak is usable on jarvis now (public, protection available, free) but not on redrobot while it has no branch protection — from [C207], [C231], [C232]
- **C238** [quoted] Since May 2026 an Actions concurrency group can hold up to 100 pending runs processed in order (queue: max); before, a new run cancelled and replaced the single pending one — "Previously, a concurrency group could have one run in progress and one pending run. If another run entered the group, the pending run was canceled and replaced. Now, you can configure concurrency groups to queue multiple pending runs and process them sequentially, with support for up to 100 queued jobs or workflow runs per concurrency group." — [S21], changelog body
- **C239** [quoted] An existing DIY action (yamachu/merge-queue-action) builds a temp branch of base+PR, tests it, then merges, serialized by an Actions concurrency group, with no ordering guarantee; it also refuses to merge if HEAD moved outside it — "ただし、GitHub Actions の Concurrency 機能を利用しているため、順序の保証はできません。" — [S22], 提供する機能
- **C240** [quoted] yamachu's action warns that its merges fire no push event on main, so CD needs a GitHub App token — "merge では、main などへの push イベントが発火しません。" — [S22], IMPORTANT note
- **C241** [measured] yamachu/merge-queue-action is a 3-star repo, last pushed 2024-05-28 — a pattern reference, not a maintained dependency — Own measurements, L2-M1
- **C242** [inference] A serial DIY queue (update-branch, wait for checks, merge, one PR at a time) lands at most one PR per full CI duration; batching or speculative testing is what the vendor queues add on top — from [C202], [C215], [C216], [C238]
- **C243** [inference] On redrobot the DIY serializer is advisory: with no protection, nothing stops a direct merge that skips it, the same as Mergify hybrid mode — from [C207], [C217]
- **C244** [quoted] Counter: a vendor's own guide says individuals or small single-project teams probably do not need a merge queue — "You probably don’t need a merge queue if you’re an individual developer in a simple codebase or a small team working on a single project." — [S23], Why Do You Need a Merge Queue?
- **C245** [quoted] Counter: Harness lists conditions to leave a queue off, including few merges and cheap-to-repair breaks — "The repository takes few merges. A small team already coordinates merges directly. Changes are mostly independent of each other. A broken branch is cheap to repair." — [S24], When to leave the queue disabled
- **C246** [measured] jarvis main already has strict required checks (7 contexts) and enforce_admins is off — Own measurements, L2-M2
- **C247** [inference] On jarvis the strict poor-man's queue is already on, so any break between green PRs would have to enter by a path it does not cover (admin-identity merges with enforce_admins off is one candidate, unverified); the cheap step there is closing that path before adding a queue, and any real queue needs an org (native) or a third-party app — from [C201], [C205], [C246]
### Q3 — making the pytest CI substantially faster without dropping what it catches — answered with a gap

- **C301** [quoted] redrobot PR fast lane is the only PR-blocking pytest job besides the conditional hardware lane — "fast lane — the ONLY checks a PR merge waits on (this job + the conditional `pr-fast-hardware` below)" — [S25], lines 153-154 (fetched 2026-11-18)
- **C302** [quoted] The fast lane runs `-n ${PYTEST_WORKERS:-4}` xdist workers (4 by default) and excludes slow and heavy_sim — "uv run pytest tests --ignore=tests/driver --ignore=tests/experiments -n \"${PYTEST_WORKERS:-4}\" -m \"not slow and not heavy_sim\"" — [S25], line 337
- **C303** [quoted] Coverage was deliberately removed from the PR path as overhead — "No coverage instrumentation either — coverage is a nightly concern (AC), not a per-PR one, and skipping it removes real overhead from the hot path." — [S25], lines 160-161
- **C304** [quoted] Locally measured fast-lane size and time after #2114 — "measured locally post-#2114: 4243 tests in ~5.5min at 4 xdist workers" — [S25], lines 175-176
- **C305** [quoted] Hardware-protocol tests run on PR only when the diff touches that surface; everything still runs nightly — "Every test still runs somewhere: this job (common + MVP fast surface), `pr-fast-hardware` (hardware surface, conditionally on PR), or nightly `backend`/`backend-slow` (unconditionally, always)" — [S25], lines 167-169
- **C306** [quoted] The master Backend job runs on every push to master, so its signal fires on the merge rather than on a schedule — "Running `backend` on every push to master makes that signal fire by the FACT of the merge, not on a schedule" — [S25], lines 11-13
- **C307** [quoted] The slow suite runs only on schedule or dispatch — "if: github.event_name == 'schedule' \|\| github.event_name == 'workflow_dispatch'" — [S25], line 861
- **C308** [quoted] heavy_sim is an explicit per-file list in conftest, and the list is a known regression risk — "This list is a time budget for the blocking `pr-fast` lane: revisit it whenever slow sandbox tests are added." — [S26], lines 55-58
- **C309** [quoted] Default addopts exclude slow everywhere — "addopts = \"-m 'not slow'\"" — [S27], [tool.pytest.ini_options]
- **C310** [quoted] Runner fleet is heterogeneous and the same suite runtime varied 6:45 to 45:00 by runner load — "measured variance on the SAME commit was 6:45 -> 45:00 depending on runner load" — [S25], lines 541-543
- **C311** [quoted] Install creates a cleared venv with uv in each job — "uv venv --clear" — [S25], lines 243-244
- **C312** [measured] PR fast-lane test step takes 5.9-6.9 min; install, checkout and lint together stay under ~0.5 min, so pytest execution is ~95% of the job — Own measurements, L3-M1
- **C313** [measured] Runner pickup adds 0.5-7.1 min before the fast lane starts on a PR — Own measurements, L3-M2
- **C314** [measured] jarvis pytest finishes in 0.5 min with no parallelism, so jarvis is not a CI-time bottleneck — Own measurements, L3-M4, L3-M6
- **C315** [measured] redrobot numba kernels are JIT-compiled without cache=True and no NUMBA_CACHE_DIR is set, so each fresh process recompiles them — Own measurements, L3-M5
- **C316** [inference] Remaining PR-path headroom in redrobot is in the ~6 min test step and runner queueing, not install or coverage; uv, xdist, slow/heavy_sim deferral and path-scoped lanes are already in place — from [C302], [C303], [C305], [C311], [C312], [C313]
- **C317** [quoted] testmon selects tests from per-test coverage, no heuristics — "There is no heuristics involved. testmon works with these pretty solid assumptions: coverage.py library can reliably determine executed and unexecuted lines of code" — [S28], body
- **C318** [quoted] testmon's reliability limits equal coverage.py's — "The limits and reliability of this method are pretty much the same as limits of coverage.py" — [S28], end of Implementation details
- **C319** [quoted] testmon does not track static files or external services — "Testmon doesn’t know and doesn’t track changes of these categories: static files (txt, xml, other project assets) external services (reachable through network)" — [S29], Test dependencies
- **C320** [quoted] Passing -m forces testmon into no-deselect mode unless --testmon-forceselect is used — "--testmon-noselect Reorder and prioritize the tests most likely to fail first, but don’t deselect anything. Forced if you use -m, -k, -l, -lf" — [S29], All command line options
- **C321** [quoted] testmon collection is disabled under coverage — "--testmon-nocollect Run testmon but deactivate the collection and writing of testmon data. Forced if you run under debugger or coverage." — [S29], All command line options
- **C322** [quoted] testmon supports xdist since 1.4 — "With pytest-testmon=>1.4.0 the support has recently been added." — [S30], body
- **C323** [quoted] testmon's maintainer has no official CI guide and says testmon.net, a hosted service in development, is far more effective than sharing or caching .testmondata across CI runners — "That’s far more effective than sharing or caching .testmondata files across CI runners." — [S31], Testmon in CI
- **C324** [quoted] A testmon CI bug made it run all tests, fixed in 2.1.4 — "particularly if it’s running all tests when it shouldn’t, please test again with release v2.1.4 or later" — [S31], If you still want GHA
- **C325** [quoted] Open testmon bug: changes to module/class-level variables do not trigger reruns (false negative) — "does not rerun `test_module()` when the value of `MyClass.FOO` or `foo_bar` is changed" — [S32], issue body, open since 2022-08-17
- **C326** [quoted] Older testmon false negative: parametrize data from another module not tracked — "appending an item to `listdata` will not result in `test_list` being selected in the next test run" — [S33], issue body (closed)
- **C327** [quoted] testmon is maintained: v2.3.0 released 2026-11-02 — "v2.3.0" — [S34], gh api releases/latest, published_at 2026-11-02
- **C328** [quoted] One project's issue (estimagic #447) reports numba-jitted functions are ignored by codecov — "Currently numba-jitted functions are ignored by codecov." — [S35], issue body
- **C329** [quoted] NUMBA_DISABLE_JIT runs the plain Python function instead — "The jit() decorator acts as if it performs no operation, and the invocation of decorated functions calls the original Python function instead of a compiled version." — [S36], NUMBA_DISABLE_JIT
- **C330** [inference] For redrobot, testmon is blind to config/passport data files, likely blind to edits inside numba kernels (one project's report), and needs --testmon-forceselect because every lane passes -m — from [C319], [C320], [C325], [C328], [C315]
- **C331** [quoted] Datadog TIA skips a test only if it passed before with identical covered and tracked files — "If Datadog has a record of the test passing in a commit where the covered and tracked files are identical to the current commit, the test is skipped." — [S37], Overview
- **C332** [quoted] Datadog TIA (Python) is incompatible with pytest-cov — "Incompatible with pytest-cov (see known limitations )" — [S38], Compatibility
- **C333** [quoted] Datadog TIA has race conditions with pytest-xdist — "Some race conditions may cause exceptions when using pytest plugins such as pytest-xdist that change test execution order or introduce parallelization." — [S38], Known limitations
- **C334** [quoted] CloudBees Smart Tests (ex-Launchable) subsets by a target percentage, confidence or time budget — "--confidence [PERCENTAGE]" — [S39], Optimization target
- **C335** [quoted] CloudBees Smart Tests returns an untrained (isBrainless) answer until it learns from recorded runs — "When the CloudBees Smart Tests model is untrained and the service returns isBrainless: true, this means it is still learning from your recorded test data and cannot yet produce an optimized subset." — [S39], page text
- **C336** [quoted] Facebook predictive test selection halved test cost while still reporting >99.9% of faulty changes, but under 100% of test failures — "reduces the total infrastructure cost of testing code changes by a factor of two, while guaranteeing that over 95% of individual test failures and over 99.9% of faulty changes are still reported back to developers" — [S40], abstract
- **C337** [quoted] pytest-picked selects only modified test files from git status or branch diff — "Run the tests related to the unstaged files or the current branch" — [S41], README
- **C338** [quoted] pytest-incremental is deprecated — "DEPRECATED: This project is no longer maintained." — [S42], README
- **C339** [quoted] Trunk quarantine overrides the exit code for known-flaky failures; the test still runs — "A quarantined test continues running in CI and uploading results to Trunk Flaky Tests, but its failures won't block your pipeline." — [S43], Overview
- **C340** [quoted] Trunk refuses to quarantine broken (non-flaky) tests — "Broken tests are not quarantine candidates." — [S43], callout
- **C341** [quoted] Trunk fails safe when its service is down — "Your original test exit code is preserved — if tests fail, your CI fails" — [S44], behaviour list
- **C342** [quoted] numba writes compiled functions to a file cache only when cache=True — "you can instruct Numba to write the result of function compilation into a file-based cache. This is done by passing cache=True" — [S45], Cache
- **C343** [quoted] NUMBA_CACHE_DIR only relocates the cache — "Override the location of the cache directory." — [S36], NUMBA_CACHE_DIR
- **C344** [quoted] numba cache invalidation misses changes in other files and freezes globals — "Cache invalidation fails to recognize changes in symbols defined in a different file." — [S46], Caching Limitations
- **C345** [quoted] numba cache is safe to share across machines but only reused on an exact CPU match — "If the CPU model and the CPU features do not match exactly, the cache contents will not be considered." — [S46], Cache Sharing
- **C346** [quoted] When the cache directory is shared on a network filesystem, concurrent cache access is safe only with atomic file replacement — "concurrent read/write of the cache is safe only if file replacement operation is atomic" — [S46], line ~1064
- **C347** [inference] A numba cache could save JIT time per xdist worker, but it can serve stale kernels after edits to a helper in another file, so it fits PR CI only with a per-commit cache key; the time it saves is unmeasured — from [C315], [C342], [C344], [C345]
- **C348** [quoted] xdist worksteal handles very uneven test durations better than load — "worksteal should handle tests with significantly differing duration better" — [S47], --dist worksteal
- **C349** [quoted] pytest-split shards a suite across CI jobs from a committed .test_durations file — "Pytest plugin which splits the test suite to equally sized \"sub suites\" based on test execution time." — [S48], project description
- **C350** [quoted] coverage.py sysmon core (default from Python 3.14) does not support dynamic contexts — "The sysmon core does not yet support plugins, dynamic contexts, or some concurrency libraries." — [S49], [run] core
- **C351** [quoted] Practitioner report: a coverage-based selector had a median skip rate of 73% over 15 replayed Flask commits (483-test suite); sysmon recorded only one context per line — "sysmon, at the time, recorded only the FIRST context to hit each line and dropped the rest." — [S50], post, 2026
- **C352** [inference] Shards (pytest-split across runners) or more workers per runner are the levers that keep every test while cutting wall time, bounded by redrobot's measured runner contention and queue latency — from [C310], [C312], [C313], [C348], [C349]
### Q4 — other ways to relax pre-merge gates safely, and teams that moved between blocking and non-blocking — answered with a gap

- **C401** [measured] jarvis risk-tier computes a tier as the max of a path tier (protected-paths buckets → HIGH), test weakening (→ HIGH) and a diff classifier ordinal; final = max(computed, declared); LOW/MEDIUM green, HIGH/CRITICAL red until an admin approves the head SHA unless the author is admin — Own measurements, L4-M1
- **C402** [measured] jarvis risk-tier treats anything it cannot read as HIGH and has a comment-only exemption for protected .py files whose AST is unchanged — Own measurements, L4-M1
- **C403** [measured] jarvis risk tier today decides only the human hold; the test checks (pytest.yml) run the full suite on every PR with no path filter, so risk tier does not select which checks are required — Own measurements, L4-M2
- **C404** [measured] redrobot defines three tiers in AGENTS.md: tier 1 safety core (driver/, planning/ CI-enforced, plus experiments.py, tests/safety/), tier 2 measurement tool (simulation, MuJoCo assets, golden baselines), tier 3 lab (sandbox, vision, ui, cli, scripts, docs) whose "Only requirement is a green master"; source of truth scripts/ci/pr_tier.py — Own measurements, L4-M3
- **C405** [measured] redrobot agent merge rule: agent merges LOW/MEDIUM with verdict and every check green; a person merges HIGH/CRITICAL, a review-requested PR, or a diff touching tier-1 / .github / scripts/ci / AGENTS.md paths — Own measurements, L4-M3
- **C406** [measured] redrobot already selects checks by path: pr_tier.py classifies changed paths as hardware / frontend / docs-only; a docs-only diff runs a docs lane instead of the full suite (#3254), with the classifier taken from the base commit so a PR cannot call itself docs-only — Own measurements, L4-M4
- **C407** [measured] redrobot already has a pre/post split: the PR fast lane (#2024/#2114) is "the ONLY checks a PR merge waits on" and runs `-m "not slow and not heavy_sim"`; the full not-slow suite incl. heavy_sim and coverage runs off the PR path (master push / nightly) — Own measurements, L4-M4
- **C408** [inference] so the 2026-10-14 redrobot decision's rejected option "block only mainline checks" is partly already in place at the test-selection level: what is required per PR already varies by path (docs/frontend/hardware) and heavy_sim is post-merge only — from [C406], [C407], [C409]
- **C409** [measured] redrobot decision 2026-10-14 "red-is-not-merged" rejected blocking only mainline checks because the line could not be separated ("всё кроме UI"); its critic noted 3 of 35 master failures were integration after a green PR because heavy_sim runs only on master, and that "всё кроме UI" is wider than the AGENTS.md tiers — Own measurements, L4-M3
- **C410** [quoted] A required check whose workflow is skipped by a path filter stays Pending and blocks merge, so path filters at workflow level cannot make a required check conditional — "If a workflow is skipped due to branch filtering, path filtering, or a commit message, then checks associated with that workflow will remain in a "Pending" state. A pull request that requires those checks to be successful will be blocked from merging." — [S51], section on skipped workflows (link markup removed from quote)
- **C413** [quoted] GitHub rulesets have an "Evaluate" status that does not enforce but records would-be violations on Rule Insights — documented in the Enterprise Cloud docs — "Evaluate:** your ruleset will not be enforced, but you will be able to monitor which actions would or would not violate rules on the "Rule Insights" page." — [S53], Using ruleset enforcement statuses
- **C414** [quoted] In Evaluate, insights show which actions would have passed or failed had the ruleset been active — "If the enforcement status is set to "Evaluate", you can see which actions would have passed or failed if the ruleset was active." — [S54], Finalizing your ruleset
- **C415** [measured] The Free/Pro/Team docs version of "Using ruleset enforcement statuses" lists only Active and Disabled — Evaluate is absent there and present only in the Enterprise Cloud version, so it is not available to a personal account repo — Own measurements, L4-M5
- **C416** [inference] For these repos the shadow transition has to be built, not toggled: run the candidate check non-required (or continue-on-error) and log what it would have blocked, then decide; rulesets Evaluate does not apply — from [C413], [C415]
- **C417** [quoted] Gatekeeper's documented rollout path for new constraints is dryrun: violations are surfaced in the constraint status without enforcement; deny is the default if unset — "When rolling out new constraints to running clusters, the dry run functionality can be helpful as it enables constraints to be deployed in the cluster without making actual changes." — [S55], Dry Run enforcement action
- **C418** [quoted] Gatekeeper's warn action adds immediate feedback on why a constraint would have denied, between dryrun and deny — "Warn enforcement action offers the same benefits as dry run, such as testing constraints without enforcing them. In addition to this, it will also provide immediate feedback on why that constraint would have been denied." — [S55], Warn enforcement action
- **C419** [quoted] Semgrep recommends a fixed shadow window for CI blocking rules: comment-only for two weeks, review true positives and engagement, then flip to blocking — "Run them in comment mode for two weeks. Review the findings with your team: are these true positives? Are developers engaging with the comments? Then flip those five to blocking." — [S56], Start with five rules
- **C420** [quoted] Counter: a vendor reports that across hundreds of Kyverno-using organizations most policies stay in audit and never get enforced — a shadow phase without an exit date tends to become permanent — "Across hundreds of organizations using open source Kyverno, the pattern is consistent: most policies never graduate from audit to enforce." — [S57], The Audit Mode Illusion (vendor, no method given)
- **C421** [quoted] Counter on Evaluate: a third-party test on a Free plan got an explicit refusal from both UI and REST API — "Enforcement evaluate option is not supported on this plan. Please upgrade to Enterprise to enable it." — [S58], test of Evaluate on Free plan, 2026-10-21
- **C422** [quoted] Google-scale auto-revert is not safe naively: the flake-aware culprit finder is 99.54% accurate per test but only 77.37% per blamed change, which would wrongly revert ~20–130 of ~300–500 reverted changes per day — "even though Google’s FACF has a measured per-test accuracy of 99.54%, when aggregated (grouped) by blamed change, the accuracy per-change is only 77.37% in the last 28 day window" — [S59], Introduction (SafeRevert, ICST Industry 2024)
- **C423** [quoted] Google's target for auto-revert is under one wrong revert per day, because a wrong revert costs a lot of developer toil — "At Google, we find the cost of incorrectly reverting a change is extremely high in terms of developer toil and frustration. Therefore, we need to reduce the rate of bad reversions as much as possible. In this work, we aim to incorrectly revert fewer than one change per day on average." — [S59], Introduction
- **C424** [quoted] SafeRevert, gated by an ML confidence model, reverts about half of real culprits (recall 55.7%, ~2.1x baseline) on ~25,137 culprits over ~3 months while meeting that safety bar — "yields a recall of 55.7%, \(\sim2.1 \times\) higher than the baseline method" — [S59], Our Contributions and Findings
- **C425** [quoted] Chromium's Findit auto-reverted compile-failure culprits itself and posted to Sheriff-o-Matic — "When a culprit is identified, Findit now automatically creates and commits a revert. Notifications are also posted to Sheriff-o-Matic." — [S60], AutoRevert for compile failures
- **C426** [quoted] Chromium's LUCI Bisection (Findit's successor) config at one commit caps auto-revert actions for compile-failure culprits per day (create 10, submit 4) and a max culprit age of 6 h; for test failures, submitting reverts is disabled (daily_limit 0) and max age is 1 — "create_revert_settings: { enabled: true daily_limit: 10 } submit_revert_settings: { enabled: true daily_limit: 4 } max_revertible_culprit_age: 21600" — [S61], compile_analysis_config gerrit_config
- **C427** [quoted] ChromiumOS is "revert-first": reverting a recent known-bad CL is the preferred fix over fixing forward — "ChromiumOS is a revert-first project. This means, whenever it's possible to solve a breakage simply by reverting a CL or two, this is the preferred way to solve the breakage." — [S62], Reverting Bad CLs
- **C428** [quoted] LLVM (pre-merge checks plus post-commit buildbots) relies on revert-to-green norms for tip-of-tree health — "We strongly encourage “revert to green” as opposed to “fixing forward”. We encourage reverting first, investigating offline, and then reapplying the fixed patch" — [S63], Patch reversion policy
- **C429** [quoted] One GitHub Action reverts a given commit; its example runs it when a needed test job fails — "This action reverts the given commit in the Github Action Workflow" — [S64], README
- **C430** [quoted] Consume-from-last-green: Bazelisk lets users pin to the binary built at the most recent commit that passed CI rather than tip — "`last_green` refers to the Bazel binary that was built at the most recent commit that passed [Bazel CI]" — [S65], line 70
- **C431** [quoted] GitLab quarantines a flaky test that blocks master so it stops impacting other developers — "When a flaky test is blocking development on master, it should be quarantined to prevent impacting other developers." — [S66], Quarantined tests
- **C432** [inference] Where most master reds are flaky tests or runner infrastructure (redrobot's critic: 20 of 35 master failures were runner infra), an auto-revert keyed on red master would revert innocent PRs unless it reruns first — from [C422], [C409]
- **C433** [quoted] ChromiumOS names path-based builder skipping (informational or post-submit-only builders, deemed low risk for some files) as one way bad CLs reach the tree — "Due to a CI configuration, a builder was marked as either informational or post-submit only, and was skipped during the commit queue run of the bad CL." — [S62], How can bad CLs land in the tree?
- **C434** [quoted] ChromiumOS treats making a builder or test informational as a last resort because it lets new breakages in; a revert is much preferred — "Generally, this is done as a last-resort step, as it allows new breakages to slip in. A reverted CL would be preferred much more to this." — [S62], Making Builders/Tests Informational
- **C435** [quoted] D-Robotics/moss (2026-10-11) made test jobs non-blocking by team decision, keeping only Check required and the workflow visible — "Per team decision: CI no longer gates merges except Check. Adds `continue-on-error: true` to test, real-terminals, install-e2e, windows-shell jobs. Workflow kept so red runs remain visible" — [S67], PR body, merged 2026-10-11T14:28Z
- **C436** [quoted] Within ~18 hours (2026-10-12) moss made Test blocking again with a single Test summary gate job, keeping the other three jobs advisory; PR #119 had to merge first (existing Windows reds, git-spawn debounce, a full run under CI), and making Test summary required was left to a repo admin, since main had no branch protection — "去掉 test matrix 上 #87（e11336ff）加的 continue-on-error，Test 重新会挡合并。" — [S68], PR body, merged 2026-10-12T08:48Z
- **C437** [inference] moss's reversal kept a split rather than full blocking (core tests blocking, platform/e2e advisory); its PRs state no explicit reason for the reversal — from [C435], [C436]
- **C438** [measured] redrobot's own reversal (2026-10-14) from an unwritten "merge on red, fix later" rule to "red is not merged" was decided by two maintainers for ease of checking, status `proposed`, with three critic findings still open — Own measurements, L4-M3

## Disconfirming evidence

- Against C124, the class 'integration after a green PR': the 20.2 h red streak looked like master-only integration, but the PR was red before merge (L1-M10).
- Against C121, 'flaky = noise': two 'flaky' tests were test defects fixed by commits; the product code was not shown to be at fault, but the redness was not random noise either.
- Against C128, the critic's runner-infra share: 0 of 20 Backend logs show runner loss (L1-M7). Its window (before 2026-10-14) was not re-measured here.
- Against C133, 'jarvis main is protected by required checks': admin merges passed a red required check (L1-M13).
- Searched for a red-at-merge redrobot PR in the 15-PR sample: none found once post-merge statuses are separated out (L1-M12, L1-M14); #3297 came from the master-red trace, not from the sample.
- [C201] — query: `GitHub merge queue now available Team plan private repositories changelog 2026` — no change found; the current docs page (C201) stands.
- [C244], [C245] — query: `merge queue not worth it small team` — only vendor-authored pages came back; no benchmark either way.
- testmon reliability C317/C318 — query "pytest-testmon missed failing test bug false negative issue" + gh issue search on tarpas/pytest-testmon → counter-claims C325 (open false negative), C326; open issue #89 asks for a "validation tool (running all tests but big warning in case testmon would miss changes)".
- Selection safety C331/C336 — query "test impact analysis false negatives missed regressions coverage-based test selection unsafe study" → Legunsen et al. 2016 (snippet only: dynamic RTS "at the risk of being unsafe sometimes"), C351. C336 itself states <100% of failures reported.
- numba cache C342/C347 — query "numba cache=True pytest-xdist parallel workers cache corruption race condition issue" → nothing numba-specific; C346 sets the condition.
- Quarantine claim C339 — C340, C341 are limits from the vendor's own docs; no independent failure report searched.
- Workers/shards claim C352 — counter is in-repo: C310 (contention 6:45→45:00). No external search run.
- C413/C415 (Evaluate unavailable outside Enterprise): query "GitHub ruleset evaluate mode only Enterprise not available Team plan community discussion" → C421 confirms on Free; Team plan unconfirmed either way.
- C422–C425 (auto-revert works): query "auto-revert bot reverted wrong commit false positive disabled automatic revert complaints" → no disabled-bot case found; SafeRevert itself is the counter (C422, C423); WebKit bot issues are tooling bugs, not wrong reverts.
- C416/C419 (shadow then enforce): query "policy stuck in audit mode never enforced warn mode ignored warnings developers ignore non-blocking checks" → C420 (most audit policies never promoted).
- Path-gated checks (C406, C410): counters C433, C434 and redrobot's own C409 (heavy_sim master-only gave 3 post-green integration failures).
- C435–C437 (blocking/advisory moves): query "non-blocking CI checks made blocking again engineering blog why we made tests required after main broke" → only moss found; no long-form write-up.

## Coverage

| Channel | Read | Gap |
|---|---|---|
| Users | testmon issue threads (#191, #115), a practitioner post on a coverage-based selector that skipped 73% of a suite, D-Robotics/moss PRs #87 and #120 | no Hacker News thread read; no first-hand account of Mergify or Kodiak on a personal-account repo |
| Specialists | GitHub docs (merge queue, protected branches, rulesets, workflow syntax, plans, pricing), Mergify / Trunk / Graphite / Aviator / Kodiak docs and pricing, testmon / Datadog TIA / CloudBees / numba / xdist / coverage.py docs, ChromiumOS, LLVM and GitLab policies, Gatekeeper, Semgrep, redrobot and jarvis workflows and rules files | LUCI Bisection current docs not reached; Microsoft's flaky-quarantine post returned 404 |
| Data | SafeRevert (Google), Facebook predictive test selection (arXiv); own measurements of redrobot and jarvis main (L1-M5, L1-M11), PR check times (L1-M12, L3-M1, L3-M2) and failing-job logs (L1-M7) | no nightly or slow-suite results; numba compile time unmeasured; PR time measured from the first check start, on 15 PRs per repo |
| Adversarial | testmon false negatives [C325], [C326]; audit policies never enforced [C420]; ChromiumOS on path-skipped builders [C433], [C434]; vendors saying small teams need no queue [C244], [C245]; moss reversing advisory tests [C436] | no long-form "why we made CI blocking again" write-up found; no report of an auto-revert bot disabled for wrong reverts |

Declared overruns:
- Q1 made 54 gh API calls against a budget of ~50. It read the logs of 20 failing Backend jobs and 3 gitleaks jobs by job id, not by scraping run history.
- Q2 ran about four searches but read many primary pages (GitHub docs and five vendors' pricing and docs), because each vendor needed its own page.
- Q3 ran 9 web searches and about 18 page reads against a ceiling of 4 and 3.
- Q4 ran 11 web searches and about 14 page reads. Each reached a separate part of the sub-question, and 4 of them were disconfirming.

Measurement ids carry their ledger as a prefix: L<n> for the ledger of Q<n>.

## Own measurements

<!-- ledger Q1 -->
### L1-M1

`python protect.py` (gh api repos/<r>/branches/<b>/protection, /rules/branches/<b>, repos/<r>): jarvis contexts=[require-linked-issue,pytest,code-gate,gitleaks,waiting-human-review,risk-tier,ruff] strict=true enforce_admins=false, rules=[deletion,non_fast_forward]; redrobot protection 404 'Not Found', rules 403 'Upgrade to GitHub Pro or make this repository public', private=true owner=User allow_auto_merge=false.

### L1-M2

`git show origin/master:.github/workflows/{ci,gitleaks}.yml` (redrobot): ci.yml:173 pr-fast if event==pull_request; :337 `pytest tests --ignore=tests/driver --ignore=tests/experiments ... -m "not slow and not heavy_sim"`; :349 pr-fast-hardware if hardware paths; :494 backend if event != pull_request; :861 backend-slow if schedule|workflow_dispatch; :41/:47 group ci-<ref>-<event>, cancel-in-progress != push; gitleaks.yml:33 timeout-minutes 15.

### L1-M3

jarvis .github/workflows/pytest.yml: on pull_request + push main; runs-on ubuntu-latest; `uv run pytest tests/ -v`.

### L1-M4

`git log origin/master --first-parent --since=<date> | wc -l` (redrobot): since 11-11T18:00 151 (151 end in '(#N)'); since 11-04 241; since 10-28 325; since 10-21 381. jarvis since 11-11: 15.

### L1-M5

`python sample.py 4 redrobot` (GraphQL history 4x50 with statusCheckRollup) + `analyze.py sample_rr.json`: 200 commits 2026-11-06T08:30Z..11-18T18:12Z; STATES SUCCESS 130 FAILURE 23 NONE 46 PENDING 1; failing check 'Backend (pytest + coverage)'[push] x20, 3 others = gitleaks CANCELLED; TIME-WEIGHTED head red 35.0h of 297.7h = 12%; 16 streaks (h): 0.9,0.0,0.4,2.5,2.2,0.1,1.2,0.4,0.2,0.1,0.4,20.2,1.8,1.7,4.8,0.7.

### L1-M6

`gh api repos/SergazyNarynov/redrobot/commits/{9a7a7ccc,bb0642dc}/check-suites`: github-actions suites 'completed cancelled' latest_check_runs_count 0 (plus claude/cursor suites queued 0).

### L1-M7

`python logs.py` (gh api .../actions/jobs/<id>/logs for all 20 failing Backend jobs, grep FAILED/##[error]): stale_reply-only: 131722056476,131710129897,131318778435,129830119667,129796330754,131990176113; f3-only: 131761847120; worker 'gw1' crashed test_sandbox_speed_cap_e2e: 128043433125,127941178331,127931735336; multi-timing: 131796295516,129901611881,129876568625,131932471520(52 min),133164703423(89 min); pause/resume mock: 132621758644; r8 'pytest.approx() does not support nested dictionaries': 132604857270,132615311851; guideline meta test: 132196048287; 'Failed to CreateArtifact ... Unexpected token <': 130775763366. Annotations for 7 jobs: only 'Process completed with exit code 1.' + Node 20 warning.

### L1-M8

gitleaks job 133269418184 log tail: 'Terminate orphan process ... (git-remote-https)', '##[error]The operation was canceled.'; started 12:04:48 cancelled 12:20:00; the other two cancelled jobs also ran ~15 min (12:56:02-13:11:09, 14:19:30-14:34:36).

### L1-M9

`git log origin/master` (redrobot): 77fae165 'fix(ci): fixes red master (03f2b1ae): guideline meta test reads REVIEW.md' (#3306); 8b37db3b 'make test_stale_reply.py independent of the clock (#3253) (#3347)'; 97df3199 'pause/resume no-jump bound survives CPU load (#3428) (#3429)'; 1f735fb0 'per-lever approx in r8 volume-offset windows check (#3337)'; 03f2b1ae is PR #3297.

### L1-M10

`gh pr view 3297 -R SergazyNarynov/redrobot --json statusCheckRollup`: 'PR fast lane (lint + unit tests) FAILURE 20:38:22-20:43:41', 'code-review/verdict FAILURE 20:52:12'; merged 21:59:01 by Osasuwu.

### L1-M11

`python sample.py 2` (jarvis 2x50) + analyze.py: 100 commits 2026-10-07T17:45Z..11-18T17:16Z, STATES SUCCESS 100, TIME-WEIGHTED red 0.0h of 1007.5h.

### L1-M12

`python prwall.py` (15 merged PRs per repo, last-commit rollup, only checks completed <= mergedAt): redrobot WALL median 14.2m p75 348.9m max 3254.3m, firstcheck->merge median 19.8m, pr-fast 5.8m/10.8m, review 5.1m/8.5m, gitleaks 3.8m/10.5m; jarvis WALL median 0.6m p75 1.5m, firstcheck->merge 5.7m, review 0.7m, pytest 0.5m.

### L1-M13

`python mergedby.py` (GraphQL mergedBy + checkSuites): #2230 merged 13:41:19 by Osasuwu, code-gate (osasuwu-ci app 3969106) FAILURE 13:40:06 'evidence-none', no later code-gate; #2228 same pattern (12:21:58 fail, merged 12:23:09); #2232 waiting-human-review FAILURE 14:44:56 then SUCCESS 15:02:34, merged 15:03:15; #2207 risk-tier FAILURE 14:38:33 then SUCCESS 14:44:18, merged 14:45:52. `gh api .../commits/<sha>/check-runs?filter=all` for #2230: review success 13:39:53-13:40:33 (after code-gate post).

### L1-M14

`gh api repos/SergazyNarynov/redrobot/commits/<sha>/statuses`: #3439 verdict success 11-16T13:51:40, failure 11-18T12:10:07 (merged 11:57:01); #3421 verdict success 12:34:51, failure 12:53:24 (merged 12:37:24).

<!-- ledger Q2 -->
### L2-M1

`gh api repos/{bors-ng/bors-ng,chdsbd/kodiak,yamachu/merge-queue-action}` (2026-11-18): bors-ng archived=true pushed 2024-04-04; kodiak archived=false last commit 2026-11-07; yamachu/merge-queue-action archived=false pushed 2024-05-28 stars=3.

### L2-M2

`gh api repos/Osasuwu/jarvis/branches/main/protection` (2026-11-18): required_status_checks strict=true, 7 contexts; enforce_admins=false; rulesets: default-branch-history (branch, active), release-tags (tag, active).

<!-- ledger Q3 -->
### L3-M1

`q3_jobs.py` (gh run view --json jobs) on redrobot CI PR runs 44364454514, 44357480735, 44334345152, 44330461579 (2026-11-18): "Run fast-lane tests" step 5.9 / 6.8 / 6.0 / 6.9 min; whole `PR fast lane` job 6.3 / 7.0 / 6.3 / 7.2 min; no other step of that job (checkout, uv install, ruff) exceeded 30 s. Output: rs4/q3/rr_jobs.txt.

### L3-M2

same runs: `PR fast lane` job started 4.4 / 0.5 / 1.4 / 7.1 min after the run was created (runner pickup); in run 44330461579 `Detect changed paths` spent 1.9 min in actions/checkout. `PR fast lane (hardware protocol)` ran in 2 of 4 runs, 2.4 / 2.8 min test step, in parallel with the fast lane.

### L3-M3

redrobot master push run 44362489760: `Backend (pytest + coverage)` 13.1 min job, 12.7 min test step, started 2.8 min after creation; not PR-blocking.

### L3-M4

jarvis `Tests` workflow, PR runs 44352353303, 44344268868, 44339871589: `pytest` job 0.5 min each, `lockfile-check` 0.1 min, start latency 0.1 min. Output: rs4/q3/jv_jobs.txt.

### L3-M5

grep of all 17 redrobot workflow files (rs4/rrwf) and tests/conftest.py: no NUMBA_CACHE_DIR; redrobot/sandbox/sand_fast.py has 8 `@numba.njit(error_model="numpy")` decorators, none with cache=True; GitHub code search `repo:SergazyNarynov/redrobot "cache=True"` → 0 hits (code-search index may lag).

### L3-M6

jarvis pytest.yml (local checkout): one ubuntu-latest job, `uv sync --all-extras` then `uv run pytest tests/ -v`; no xdist, no markers in pyproject (`addopts = "--import-mode=prepend"`); 98 test_*.py files.

<!-- ledger Q4 -->
### L4-M1

read C:\Users\petrk\GitHub\jarvis\.github\scripts\risk_tier.md (verdict section, lines 1–80) at main d5c93cd7.

### L4-M2

read jarvis .github/workflows/pytest.yml header: triggers on every pull_request and push to main, no paths filter; full suite job `pytest`.

### L4-M3

read redrobot AGENTS.md (Three Research Tiers, Merge denylist) and docs/decisions/2026-10-14-red-is-not-merged.md from files saved in rs4 (rr_AGENTS.md, rr_decision.md), fetched earlier this run via gh api.

### L4-M4

read redrobot .github/workflows/ci.yml saved in rs4/rrwf: lines 140–151 (pr_tier.py hardware/frontend/docs-only outputs), 153–159 (fast lane "the ONLY checks a PR merge waits on", `-m "not slow and not heavy_sim"`), 204–236 (docs-only via base classifier), 483+ (full suite off the PR path).

### L4-M5

curl of docs.github.com article API for about-rulesets and creating-rulesets-for-a-repository, dotcom vs enterprise-cloud@latest: dotcom lists only "Active" and "Disabled"; enterprise-cloud also lists "Evaluate".

## Open questions

- Q1 — no data — Nightly and slow-suite results are not in the baseline, because the schedule results attach to whichever commit is head [C137]. Reading the last few weeks of `schedule` runs of redrobot CI would settle it.
- Q1 — not established — Why runner loss went from 20 of 35 failures (critic, before 2026-10-14) to 0 of 23 here [C128]. Measuring a window before 2026-10-14 with the L1-M5/L1-M7 scripts would settle it.
- Q1 — not established — Whether the admin-account merges past a red code-gate on jarvis (#2228, #2230) were run by the user or by an agent [C133]. The session transcripts for those merges would settle it.
- Q1 — sample — 12.4 days and 15 PRs per repo is a short window. Rerunning L1-M5 and L1-M12 in a month gives a trend.
- Q2 — gap — Whether Mergify and Trunk install on a personal-account repo was not confirmed by either vendor [C225]. Installing Mergify's GitHub App on a scratch personal repo would settle it.
- Q3 — unmeasured — How much of the ~6 min test step is numba JIT compilation [C347]. One pr-fast run with `--durations` and a warm numba cache, against a cold one, would settle it.
- Q3 — unmeasured — How far shards or more workers cut wall time under the measured runner contention [C352]. One run with 8 workers, or two shards via pytest-split, would settle it.
- Q4 — not found — Why moss made its core tests blocking again [C437]. Asking in the moss repo would settle it; it is not our repo.
- Q1 — not established — Whether PR CI (pr-fast) runs the other flaky tests that turned master red (tests/api sandbox/replay e2e, tests/executor f3_p1). Reading their markers and the heavy_sim list in tests/conftest.py at the commits where they failed would settle it, and it decides whether stricter PR gates could have caught them.
- Q4 — unsupported — Whether a required check whose job is skipped by `if:` reports Success and lets the PR merge. The cited workflow-syntax page does not contain that sentence; GitHub's "Using conditions to control job execution" page appears to, and re-citing it would settle whether required checks can be made conditional per job.

## Sources

- [S1] https://github.com/SergazyNarynov/redrobot/blob/c42bf002c89e1b98a55cba45b687fef07f4707dc/AGENTS.md — passage
- [S2] https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue — passage
- [S3] https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches — passage
- [S4] https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets — passage
- [S5] https://docs.github.com/en/get-started/learning-about-github/githubs-plans — passage
- [S6] https://github.com/pricing — passage
- [S7] https://mergify.com/pricing — passage
- [S8] https://docs.mergify.com/merge-queue/queue-modes.md — passage
- [S9] https://docs.mergify.com/merge-queue/deploy.md — passage
- [S10] https://docs.mergify.com/integrations/github.md — snippet only
- [S11] https://trunk.io/pricing — passage
- [S12] https://docs.trunk.io/merge-queue/getting-started/configure-branch-protection.md — passage
- [S13] https://docs.trunk.io/merge-queue/getting-started/install-and-create-your-queue.md — passage
- [S14] https://docs.trunk.io/llms.txt — passage
- [S15] https://graphite.com/pricing — passage
- [S16] https://www.aviator.co/pricing — passage
- [S17] https://kodiakhq.com/docs/billing — passage
- [S18] https://kodiakhq.com/docs/config-reference — passage
- [S19] https://kodiakhq.com/docs/why-and-how — passage
- [S20] https://raw.githubusercontent.com/bors-ng/bors-ng/master/README.md — passage
- [S21] https://github.blog/changelog/2026-05-07-github-actions-concurrency-groups-now-allow-larger-queues — passage
- [S22] https://raw.githubusercontent.com/yamachu/merge-queue-action/main/README.md — passage
- [S23] https://trunk.io/learn/what-is-a-merge-queue-and-do-you-need-one — passage
- [S24] https://developer.harness.io/code-repository/use-harness-code/pull-requests/merge-queue — passage
- [S25] https://github.com/SergazyNarynov/redrobot/blob/master/.github/workflows/ci.yml — passage
- [S26] https://github.com/SergazyNarynov/redrobot/blob/master/tests/conftest.py — passage
- [S27] https://github.com/SergazyNarynov/redrobot/blob/master/pyproject.toml — passage
- [S28] https://testmon.org/blog/determining-affected-tests/ — passage
- [S29] https://testmon.org/ — passage
- [S30] https://testmon.org/blog/v14-with-xdist-support-is-out/ — passage
- [S31] https://testmon.org/blog/testmon-in-ci/ — passage
- [S32] https://github.com/tarpas/pytest-testmon/issues/191 — passage
- [S33] https://github.com/tarpas/pytest-testmon/issues/115 — passage
- [S34] https://github.com/tarpas/pytest-testmon/releases — passage
- [S35] https://github.com/OpenSourceEconomics/estimagic/issues/447 — passage
- [S36] https://numba.readthedocs.io/en/stable/reference/envvars.html — passage
- [S37] https://docs.datadoghq.com/tests/test_impact_analysis/how_it_works/ — passage
- [S38] https://docs.datadoghq.com/tests/test_impact_analysis/setup/python/ — passage
- [S39] https://docs.cloudbees.com/docs/cloudbees-smart-tests/latest/concepts/subset — passage
- [S40] https://arxiv.org/abs/1810.05286v2 — passage
- [S41] https://github.com/anapaulagomes/pytest-picked — passage
- [S42] https://github.com/pytest-dev/pytest-incremental — passage
- [S43] https://docs.trunk.io/flaky-tests/quarantining — passage
- [S44] https://docs.trunk.io/flaky-tests/quarantining/quarantine-service-availability — passage
- [S45] https://numba.readthedocs.io/en/stable/user/jit.html — passage
- [S46] https://numba.readthedocs.io/en/stable/developer/caching.html — passage
- [S47] https://pytest-xdist.readthedocs.io/en/stable/distribution.html — passage
- [S48] https://pypi.org/project/pytest-split — passage
- [S49] https://coverage.readthedocs.io/en/latest/config.html — passage
- [S50] https://dev.to/breadmsa/my-test-selection-tool-skipped-73-of-the-suite-that-number-was-the-bug-49m2 — passage
- [S51] https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/troubleshooting-required-status-checks — passage
- [S52] https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax — passage
- [S53] https://docs.github.com/en/enterprise-cloud@latest/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets — passage
- [S54] https://docs.github.com/en/enterprise-cloud@latest/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/creating-rulesets-for-a-repository — passage
- [S55] https://open-policy-agent.github.io/gatekeeper/website/docs/violations/ — passage
- [S56] https://semgrep.dev/blog/2026/preventing-vulnerable-code-from-merging-without-blocking-developers — passage
- [S57] https://nirmata.com/2026/04/08/your-clusters-are-unlocked/ — passage
- [S58] https://dev.classmethod.jp/en/articles/github-branch-protection-convert-to-ruleset/ — passage
- [S59] https://hackthology.com/saferevert-when-can-breaking-changes-be-automatically-reverted.html — passage
- [S60] https://sites.google.com/chromium.org/cat/findit/reliable-failure/waterfall-failures — passage
- [S61] https://chromium.googlesource.com/chromium/src/+/bbad3a62162765c67780c4337a2bdcdb5ab8e760/infra/config/generated/luci/luci-bisection.cfg — passage
- [S62] https://chromium.org/chromium-os/developer-library/guides/testing/breakages-and-flakes — passage
- [S63] https://llvm.org/docs/DeveloperPolicy.html — passage
- [S64] https://www.github.com/tofu-apis/revert-commit-action — passage
- [S65] https://raw.githubusercontent.com/bazelbuild/bazelisk/master/README.md — passage
- [S66] https://docs.gitlab.com/development/testing_guide/unhealthy_tests/ — passage
- [S67] https://github.com/D-Robotics/moss/pull/87 — passage
- [S68] https://github.com/D-Robotics/moss/pull/120 — passage

## Audit

| Claim | Verdict | Note |
|---|---|---|
| C101 | SUPPORTED |  |
| C102 | SUPPORTED |  |
| C103 | SUPPORTED |  |
| C104 | SUPPORTED | quote verbatim in S1 (spans a line break) |
| C105 | SUPPORTED |  |
| C106 | SUPPORTED |  |
| C107 | SUPPORTED |  |
| C108 | SUPPORTED |  |
| C109 | SUPPORTED |  |
| C110 | SUPPORTED |  |
| C111 | SUPPORTED |  |
| C112 | SUPPORTED | matches its ledger entry (L1-M5) |
| C113 | PARTIAL | only 2 of the 46 no-check commits were inspected (L1-M6); narrowed to those two |
| C114 | SUPPORTED | 24-merge burst 11:25:19-11:29:46 on 11-18 is in the L1-M5 output; rests on C108, C112, C113 |
| C115 | SUPPORTED | matches its ledger entry (L1-M5) |
| C116 | SUPPORTED | matches its ledger entry (L1-M5 streak list) |
| C117 | SUPPORTED | re-grepped the 20 logs: 0 shutdown / lost-communication lines |
| C118 | SUPPORTED | counts match L1-M7/L1-M8; the flaky classification is the author's judgement from the logs |
| C119 | PARTIAL | L1-M7 records 52 and 89 min for two multi-timing jobs; '32-89 min' and '11-12 min for two green runs' not recorded; green figure is L3-M3's 13.1 min |
| C120 | PARTIAL | only the tests/driver failures are shown to be in tests pr-fast ignores; 'sandbox/replay e2e run only on master' not established by the recorded output |
| C121 | SUPPORTED |  |
| C122 | SUPPORTED |  |
| C123 | SUPPORTED |  |
| C124 | SUPPORTED |  |
| C125 | PARTIAL | 1f735fb0 came 1.3 h after the first red and was itself red; master went green 1.8 h after the first red (fd0e9d9e) |
| C126 | PARTIAL | 5067b2e3 got no master CI result; 'superseded' not shown for that commit |
| C127 | SUPPORTED |  |
| C128 | PARTIAL | self-heal sentence (0079d32c, 9abeed37, 2026-10-23) dropped: no claim or measurement records it |
| C129 | PARTIAL | narrowed to the recorded figures (median 14.2, p75 348.9, max 3254.3; first check to merge 19.8); '10 of 15 within 7.5-18.2' and the re-run explanation not in L1-M12 |
| C130 | PARTIAL | pr-fast-hardware 3.0 min and 'everything else under 1 min' not in L1-M12; dropped |
| C131 | SUPPORTED |  |
| C132 | SUPPORTED |  |
| C133 | SUPPORTED |  |
| C134 | SUPPORTED |  |
| C135 | SUPPORTED |  |
| C136 | SUPPORTED |  |
| C137 | PARTIAL | 'attaches to whichever commit is head' and 'no schedule-event result appeared' not recorded; narrowed to schedule/dispatch-only (C107) |
| C201 | SUPPORTED |  |
| C202 | SUPPORTED |  |
| C203 | SUPPORTED |  |
| C204 | SUPPORTED |  |
| C205 | SUPPORTED |  |
| C206 | PARTIAL | 'exactly the post-merge break seen here' dropped: the report found no such break after a green PR |
| C207 | SUPPORTED |  |
| C208 | SUPPORTED |  |
| C209 | SUPPORTED |  |
| C210 | SUPPORTED |  |
| C211 | SUPPORTED |  |
| C212 | SUPPORTED |  |
| C213 | SUPPORTED | quote is in the page's JSON-LD; checker strips scripts, so NOT FOUND expected |
| C214 | SUPPORTED |  |
| C215 | SUPPORTED | verified from the raw HTML icons (Parallel Checks all circle-check; Batch x for Open Source, check otherwise); NOT FOUND expected |
| C216 | SUPPORTED |  |
| C217 | PARTIAL | 'needs no branch protection' and 'can disrupt it' not in the quote |
| C218 | SUPPORTED |  |
| C219 | PARTIAL | 'classic-protection route to Mergify exclusive mode' is a Mergify framing, not in S3; narrowed to the S3 sentence |
| C220 | UNSUPPORTED | negative snippet from a WebSearch model summary; S10's page has no supporting passage (only an organization selector and per-repo app install). Deleted; references removed |
| C221 | SUPPORTED |  |
| C222 | SUPPORTED | Free column reads 'Included' for Merge Queue rows |
| C223 | SUPPORTED |  |
| C224 | SUPPORTED |  |
| C225 | SUPPORTED |  |
| C226 | SUPPORTED | the other features are in the same llms.txt list |
| C227 | SUPPORTED |  |
| C228 | SUPPORTED |  |
| C229 | SUPPORTED |  |
| C230 | SUPPORTED | verified from raw HTML lucide-minus/lucide-check |
| C231 | SUPPORTED |  |
| C232 | SUPPORTED |  |
| C233 | PARTIAL | 'first-come-first-served, rather than speculative merge' not in the quote |
| C234 | SUPPORTED |  |
| C235 | SUPPORTED |  |
| C236 | SUPPORTED |  |
| C237 | SUPPORTED |  |
| C238 | SUPPORTED |  |
| C239 | SUPPORTED | extra details are in the same README section |
| C240 | SUPPORTED | extra details are in the same README section |
| C241 | SUPPORTED |  |
| C242 | SUPPORTED |  |
| C243 | SUPPORTED |  |
| C244 | SUPPORTED |  |
| C245 | SUPPORTED |  |
| C246 | SUPPORTED |  |
| C247 | PARTIAL | made conditional: no break between green PRs was shown on jarvis |
| C301 | SUPPORTED |  |
| C302 | PARTIAL | 'skips coverage' not in the quote (C303 covers it); worker count is ${PYTEST_WORKERS:-4}, default 4 |
| C303 | SUPPORTED |  |
| C304 | SUPPORTED |  |
| C305 | SUPPORTED |  |
| C306 | PARTIAL | quote says the signal fires on the merge; 'nightly, not on PR' not in it |
| C307 | SUPPORTED |  |
| C308 | SUPPORTED |  |
| C309 | SUPPORTED |  |
| C310 | SUPPORTED |  |
| C311 | PARTIAL | 'self-hosted image with python+uv baked in' is elsewhere in the file (line ~695), not in the quote |
| C312 | SUPPORTED |  |
| C313 | SUPPORTED |  |
| C314 | SUPPORTED |  |
| C315 | SUPPORTED |  |
| C316 | SUPPORTED |  |
| C317 | SUPPORTED |  |
| C318 | SUPPORTED |  |
| C319 | SUPPORTED |  |
| C320 | SUPPORTED |  |
| C321 | SUPPORTED |  |
| C322 | SUPPORTED |  |
| C323 | PARTIAL | 'paid' not in source: testmon.net is described as a hosted service in development |
| C324 | SUPPORTED |  |
| C325 | SUPPORTED | issue open, created 2022-08-17 |
| C326 | SUPPORTED |  |
| C327 | SUPPORTED | v2.3.0 published 2026-11-02 |
| C328 | PARTIAL | one project's issue (estimagic #447) about codecov, not a general coverage property |
| C329 | SUPPORTED |  |
| C330 | PARTIAL | narrowed to testmon; Datadog TIA tracks files (C331), so the Datadog generalisation dropped; numba blindness rests on one project's report (C328) |
| C331 | SUPPORTED | Datadog page needs curl --compressed; quote present |
| C332 | SUPPORTED | Datadog page needs curl --compressed; quote present |
| C333 | SUPPORTED | Datadog page needs curl --compressed; quote present |
| C334 | SUPPORTED | the other targets are in the same code block |
| C335 | SUPPORTED | snippet -> quoted: passage read on the page |
| C336 | SUPPORTED |  |
| C337 | SUPPORTED |  |
| C338 | SUPPORTED |  |
| C339 | SUPPORTED |  |
| C340 | SUPPORTED |  |
| C341 | SUPPORTED |  |
| C342 | SUPPORTED |  |
| C343 | SUPPORTED |  |
| C344 | SUPPORTED | the 'freezes globals' part is in the adjacent sentence |
| C345 | SUPPORTED | 'safe to share' is in the adjacent sentence |
| C346 | PARTIAL | the atomic-replacement condition is stated for a cache directory shared on a network filesystem |
| C347 | PARTIAL | 'or per-lockfile' dropped: a lockfile key does not catch helper edits in another file (C344) |
| C348 | SUPPORTED |  |
| C349 | SUPPORTED | snippet -> quoted: project description read via the PyPI JSON API; README mentions the stored .test_durations file |
| C350 | SUPPORTED |  |
| C351 | PARTIAL | post reports a median skip rate of 73% over 15 replayed Flask commits (483 tests); 'false negative' framing narrowed |
| C352 | SUPPORTED |  |
| C401 | SUPPORTED |  |
| C402 | SUPPORTED |  |
| C403 | SUPPORTED | re-read risk_tier.md and pytest.yml at d5c93cd7 |
| C404 | SUPPORTED |  |
| C405 | SUPPORTED |  |
| C406 | SUPPORTED |  |
| C407 | SUPPORTED |  |
| C408 | SUPPORTED |  |
| C409 | SUPPORTED |  |
| C410 | UNCHECKABLE | S51 returns 404 (also via docs API); the author's saved copy is a 404 page. The identical sentence is in S52 under on.push paths, but S52 is not the cited source |
| C411 | UNSUPPORTED | quote not in S52 (workflow-syntax page); it appears verbatim on GitHub's 'Using conditions to control job execution' page, which is not cited. Deleted; Q4 summary bullet removed |
| C412 | UNSUPPORTED | inference rests on removed C411. Deleted |
| C413 | SUPPORTED |  |
| C414 | SUPPORTED |  |
| C415 | SUPPORTED | re-curled both doc versions: Evaluate only in Enterprise Cloud |
| C416 | SUPPORTED |  |
| C417 | SUPPORTED |  |
| C418 | SUPPORTED |  |
| C419 | SUPPORTED |  |
| C420 | SUPPORTED |  |
| C421 | SUPPORTED |  |
| C422 | SUPPORTED | numbers verified on the same page |
| C423 | SUPPORTED |  |
| C424 | SUPPORTED | numbers verified; safety bar stated in the abstract |
| C425 | SUPPORTED |  |
| C426 | PARTIAL | snippet -> quoted after reading the cfg at that commit; limits apply to compile_analysis_config; for tests submit is disabled (daily_limit 0) and max age is 1. |
| C427 | SUPPORTED |  |
| C428 | SUPPORTED | 'premerge checks' is on the same page |
| C429 | PARTIAL | snippet -> quoted after reading the README; 'not as a culprit-finding bot' not in source |
| C430 | SUPPORTED | quote present with link markup |
| C431 | SUPPORTED |  |
| C432 | PARTIAL | 'solo dev, culprit is the single last merge' premise dropped: C114 shows bursty, partly untested merges |
| C433 | SUPPORTED |  |
| C434 | SUPPORTED |  |
| C435 | SUPPORTED |  |
| C436 | PARTIAL | 'Windows reds that fail-fast had hidden' not in source; PR body says #119 had to merge first and that making Test summary required was left to a repo admin (no branch protection) |
| C437 | SUPPORTED |  |
| C438 | SUPPORTED |  |

Label verdict: open — Q1 did not establish whether PR CI runs most of the flaky tests behind the red master, and Q4's conditional-required-check mechanism lost its only source (C411 removed, C410 uncheckable); either could change the Recommendation.
Quote check: Quote check ci-red-main-baseline-and-relaxation-options-2026-11-18.md: 104 quoted claim(s): 80 found, 7 NOT FOUND, 17 unfetchable, 0 no source

## Disposition

| Recommendation | State | Where |
|---|---|---|
| redrobot: fix or quarantine the master lane's timing-flaky tests | deferred | unfiled: redrobot is shared with its maintainers, and this changes how the 14.10 "red is not merged" rule is met, so it goes to the user's /grill on that rule first |
| redrobot: make every master commit get a CI result instead of cancelling superseded runs | deferred | unfiled: same /grill as above; the burst share of the 46 unchecked commits is still open |
| No merge queue for either repo on this baseline | landed | no change to make; the decision stays as it is, and this report is its record |
| redrobot CI speed: shards or more workers, xdist worksteal, numba cache keyed per commit | deferred | unfiled: the saving is unmeasured; one measurement run (Open questions, Q3) comes before an issue |
| Do not adopt coverage-based test selection (testmon, Datadog TIA) for redrobot | landed | no change to make; nothing in either repo uses it |
| A shadow phase with a fixed end date before making any new check required | deferred | unfiled: it belongs to the advisory-CI / breaker /grill deferred on 2026-11-11 |
| Auto-revert only after a rerun, and only a commit with its own red result | deferred | unfiled: same breaker /grill; no auto-revert exists to change |
| jarvis: close the path for an admin merge past a red required check (code-gate timing race, enforce_admins off) | deferred | unfiled: who ran the two merges is not established; the final message proposes a /file-issue for the code-gate race |
