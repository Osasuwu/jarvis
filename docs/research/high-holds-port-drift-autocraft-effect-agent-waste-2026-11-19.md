---
topic: high-holds-port-drift-autocraft-effect-agent-waste
tags: area:process, research
source_provenance: /research invocation in session b065a837 — seventh run, after PRs #2235–#2240; input to the /grill on advisory CI planned for 2026-11-20
status: open
audit: 2026-11-19 — 150 claims: 120 SUPPORTED, 29 PARTIAL, 0 UNSUPPORTED, 1 UNCHECKABLE
---

## Question

The user, verbatim:

"давай все 4 сейчас, грилл я думаю провести завтра вместе с Даней, ему возможно будет интересно про всё это почитать тоже, решать будем вместе, или он хотя бы будет знать что решится."

"All 4" are the four questions proposed after the sixth run (#2240):
1. who places and releases the HIGH holds on jarvis — the user or an agent under the user's login;
2. whether the fixes music-intel-mcp's ported `code_gate_verdict.py` missed matter for it;
3. apps with AutoCraft against apps without it, at storytold: main health, reverts and fix-forwards, PRs closed unmerged, what post-merge review finds;
4. how much agent work storytold throws away: the share of PRs closed unmerged, and why.

Sub-questions:
- Q1 — who places and releases jarvis's `waiting-human-review` holds on HIGH PRs, and what actually holds a HIGH merge in jarvis today;
- Q2 — whether music-intel-mcp's copy of the code-gate verdict script misses fixes that matter for its traffic;
- Q3 — whether storytold's apps with AutoCraft differ in outcomes from its apps without it;
- Q4 — what share of storytold's agent PRs is closed unmerged, and why.

Earlier reports used as leads only: PRs #2235–#2240, chiefly #2237 (the redrobot red-main baseline method), #2238 (photocraft main health) and #2240 (human role, fleet economics).

## Summary

This is the seventh run in a series on the storytold organization, an open-source set of apps written mostly by AI agents, compared with our repos (jarvis, music-intel-mcp, redrobot). It feeds a /grill on advisory CI and merge holds. Terms used below:
- **HIGH hold**: on jarvis, a PR whose risk is declared HIGH should not merge until a person releases it. The hold is the `waiting-human-review` label, which keeps a required check red while present.
- **code-gate**: our CI review step; a model reviews the PR and a script turns its findings into a pass/fail check.
- **AutoCraft**: storytold's pipeline that reviews PRs with Opus, fixes them up and merges in-rule ones; it runs on some storytold apps and not others.

**Recommendations, first.**
1. **Say plainly that jarvis's HIGH hold is a convention, and decide at the /grill whether to make it enforced.** For an admin-authored HIGH PR the label is the only CI hold, and nothing but skill text stops a session holding the user's token from removing it; the check counts that removal as human [C134]. In practice no release on this device was agent-issued, but 4 of 22 HIGH PRs got no hold at all [C135]. Fix the contradiction in CONTEXT.md, which says the label only notifies [C112]. Candidate controls for the /grill, not filed here: a hook that denies an agent's label removal or `gh pr ready` on a HIGH PR, judged under our "proposing a check" rule.
2. **Re-port the missed code-gate fixes to music-intel-mcp once; drop the source-stamp check.** The drift has cost nothing observable [C238]. One fix applies and is unpatched, #2179 (a reviewer write grant relative to the working directory), then the two fail-closed write paths, #2081 and #2085 [C239]. A stamp check has no incident to cite, and would miss fixes that reach music-intel-mcp through like-current-song [C239], [C240].
3. **Judge #2233's Opus review experiment finding by finding, not by main-health outcomes.** Apps with and without AutoCraft show no outcome difference that can be credited to it [C335], [C336]. The narrower evidence is that its post-merge Opus review found real defects its own pre-merge pass had cleared [C332].
4. **If we run parallel agent sessions for throughput, claim the issue and check open PRs before writing code.** The largest share of storytold's thrown-away work is duplicate work by many authors on the same issue, not loose CI [C435], [C436].
5. **Correct the earlier "~6% closed unmerged" figure for photocraft** (from the first run, #2235). It came from a search filter that misses most closed PRs; the real share is about 19–24% [C403], [C404], [C407].

**Q1 — who places and releases the HIGH holds.** In the 30 days to 2026-11-18, jarvis merged 42 PRs, 22 of them declared HIGH, all authored and merged under the user's login `Osasuwu` [C114]. 18 of the 22 carried the hold label; every label event, placing and releasing, is recorded as `Osasuwu` with no app marker [C115]. So GitHub's record cannot tell the user from an agent using the user's token [C118]. 16 of the 18 releases were followed by a merge within 10 minutes [C117].
- **What the code does.** risk-tier, the check meant to require a releasing role on HIGH PRs, passes them when the author is an admin who is not a bot [C108], [C113]. That was a recorded, accepted residual risk on 2026-10-16 [C109], [C110], [C111]. Branch protection requires no reviews and does not bind admins [C105], [C106]. `waiting-human-review` treats any login other than the bot login, a `[bot]` login or a missing one as human [C102], [C104].
- **What agents did.** On this device (one of three), an orchestrator placed the hold on three PRs [C122] and agents merged two held PRs after a release [C121]; no release came from an agent command [C119]. A worker opened HIGH PR #2218 as a draft with no label and later marked it ready; it merged with no hold [C125]. In September an agent command did remove the label on #1924, which GitHub recorded as an ordinary unlabel by `Osasuwu` [C126].
- **What forbids removal.** /orchestrate and its worker rules forbid it; /implement has no such rule; no hook covers labels, and the user's permissions allow `gh pr edit` [C128]–[C133].

**Q2 — music-intel-mcp's code-gate copy.** music-intel-mcp's verdict script matches jarvis as of 2026-10-16; jarvis made 6 behavioural fixes since [C201], [C204], [C205]. Two are latent at music-intel-mcp's volume (a page cap and a daily sweep) [C206]–[C210]; two need a GitHub API error during the write, and none occurred in 104 runs [C212]–[C214], [C226]; one is a jarvis-only refactor [C218]; one adds retries where music-intel-mcp already fails closed [C215], [C216]. Of the workflow fixes, #2179 applies and is unpatched but did not show in 13 of 13 sampled review runs [C221]–[C224]. Of 22 merges since the port, 19 passed on a green verdict, and the 2 red ones were gate-machinery PRs [C230], [C232]. The planned shared action (#283, #2205) does not name the verdict script [C234]–[C237].

**Q3 — AutoCraft on vs off.** AutoCraft has run on designcraft and deckcraft since about Oct 7–10, at 66–80% of new PRs from Nov 3, and not on photocraft, wordcraft or filmcraft [C305]. filmcraft is the closest match to designcraft in age, size and merge volume [C309].
- **Main health.** The share of time main's gate was red is 0–2% for the AutoCraft apps and 0–5% for wordcraft and filmcraft; only photocraft is red often (16–42%), and it is 3.7–15x larger on disk [C309], [C310], [C311], [C314]. Fix-main PRs per 100 merges do not separate the groups, and no app had a real revert [C316], [C317].
- **Speed and closes.** AutoCraft apps close fewer PRs unmerged (by a search count that misses most closes) and merge faster at the median, but inside those apps the PRs that skip AutoCraft merge fastest [C320], [C322], [C323], [C324].
- **Post-merge review.** Only 6 public follow-up issues exist, all designcraft, filed in one burst on Nov 3–4; all 6 originals had a pre-merge "No blocking problems found", and maintainers treated all 6 as real (3 fixed, 3 with open fix PRs) [C328], [C330], [C331], [C333]. The pre-merge review passed about 79% of sampled PRs [C325]. How many post-merge reviews found nothing is not public [C332].

**Q4 — how much agent work storytold throws away.** Counted by creation week over six weeks, 18.7% of photocraft's closed PRs, 23.3% of wordcraft's and 11.6% of designcraft's were closed unmerged; the oldest, mostly resolved week sits at ~24% in all three [C404]–[C407]. wordcraft also carries 1,441 open PRs, 519 untouched for two weeks [C408].
- **Why.** In 94 sampled closes, duplicate or already fixed elsewhere is 43%, no reason 23%; 69 of 94 were closed by their own author, none by AutoCraft [C413], [C415]. Some "closed" PRs landed another way [C411], [C412]. Duplicates are small [C416]. wordcraft dropped batching because main moved too fast [C422].
- **Claiming.** Duplicates in photocraft fell from late October, before the claim-first house rule (Nov 6) and RFC-0003 (Nov 12), so the data cannot credit claiming with the drop [C427], [C431]. designcraft's first AutoCraft week was as high as the others [C410].
- **Ours.** jarvis 13.3% and music-intel-mcp 14.3% look similar, but they are canaries and Dependabot; real thrown-away work is about 1 PR in 6 weeks; redrobot is 2.0% [C433], [C434]. storytold's merge rate of closed PRs (~76–81%) lies between one outside study's mid-range agents and its human baseline [C437], [C439].

## Findings

### Q1 — Who places and releases jarvis's `waiting-human-review` holds on HIGH PRs, and what actually holds a HIGH merge — answered with a gap

- **C101** [quoted] The `waiting-human-review` check is red while any review request is pending or while the label is present, with no role read. — "A hold is any pending review request (to a user or a team, whatever the reviewer's role), or the `waiting-human-review` label, which holds whenever it is present; no role or team size is read." — [S1], module docstring, lines 4-7
- **C102** [quoted] A release counts as non-human only when the actor is the lane bot login, a `*[bot]` login, or missing. Any other login, the admin's included, is a human release. — "\"Not a human\" is the bot login, any `*[bot]` login, and a login the event did not name." — [S1], docstring line 12; `is_non_human`, lines 52-55
- **C103** [quoted] The bot-release guard was built against the AFK worker's machine user `osasuwu-bot`. — "Since the AFK worker writes as machine user `osasuwu-bot` (D1) with `write` access, it can remove the label or a review request. A hold the bot released is therefore not a release" — [S1], docstring lines 9-11
- **C104** [measured] Run locally, `decide()` returns clear for a label removal by `Osasuwu` and red with re-apply for `osasuwu-bot`, `github-actions[bot]` and an empty login. An agent removing the label under the user's gh login therefore releases the hold. — Own measurements, L1-M9
- **C105** [quoted] GitHub branch protection does not bind admins unless "Do not allow bypassing" is on. — "By default, the restrictions of a branch protection rule do not apply to people with admin permissions to the repository" — [S2], Do not allow bypassing the above settings
- **C106** [measured] jarvis `main` requires 7 checks, `waiting-human-review` and `risk-tier` among them, with `enforce_admins` false and no required approving reviews. — Own measurements, L1-M1
- **C107** [quoted] jarvis's rules file names `waiting-human-review` as the merge hold, red while a review request is pending, while the label is present, or after a non-human release. — "`waiting-human-review` is the merge hold: red while any review request is pending (whatever the reviewer's role), while the label is present (no role is read; it is how a hold is placed when no review can be requested), or after the hold was last released by a non-human actor" — [S3], Merge rules
- **C108** [quoted] risk-tier passes a HIGH or CRITICAL PR when its author is a non-Bot admin. — "HIGH and CRITICAL → green when **the PR's author holds the releasing role (admin)** (#2088)" — [S4], The verdict, step 4
- **C109** [quoted] risk_tier.md names, as an accepted residual risk, an agent session opening a HIGH PR under the admin's account. — "That includes a PR an agent session opens under the admin's own account: the check sees an admin author and skips the hold" — [S4], Residual risks, item 2
- **C110** [quoted] The 2026-10-16 decision accepted that residual. It rejected an admin-applied release label partly because an agent acting as the admin could apply it too. — "Rejected: a click on about 90% of PRs, and an agent acting as the admin can apply it too." — [S5], 2026-10-16 risk-tier hold scoped to non-admin authors, Alternatives
- **C111** [quoted] The same decision records the counter that the admin-author pass drops the trace an agent acting as the admin would leave, and accepts it. — "critic S1 (HIGH): a green check drops the `--admin` + marker trace that an agent session acting as the admin would otherwise leave" — [S5], same entry, Counter
- **C112** [quoted] CONTEXT.md says the label only notifies, which contradicts AGENTS.md (C107) and the code (C101). — "a releasing-role holder's own PR (same condition) is green; `waiting-human-review` only notifies." — [S6], glossary, Risk tier (line 151)
- **C113** [measured] All 12 declared-HIGH PRs sampled (the first 12 by number) have risk-tier conclusion success, and the two job logs read (#2121, #2187) print "HIGH hold skipped: author Osasuwu has admin permission". — Own measurements, L1-M4
- **C114** [measured] 42 jarvis PRs merged 2026-10-20..2026-11-18: 22 declare HIGH, 7 MEDIUM, 13 LOW. All 42 were authored and merged by `Osasuwu`, and 40 bodies carry the Claude Code attribution line. — Own measurements, L1-M2
- **C115** [measured] 18 PRs carried a `waiting-human-review` label event, all of them declared HIGH. Every label event (19 labeled, 18 unlabeled) has actor `Osasuwu` and no `performed_via_github_app`. No PR in the window has a review_requested or reviewed event. — Own measurements, L1-M2
- **C116** [measured] 4 declared-HIGH PRs (#2164, #2215, #2218, #2234) were merged with no hold label ever applied. #2215 and #2218 went up as drafts, and #2215 had auto-merge enabled by `Osasuwu`. — Own measurements, L1-M2, L1-M3
- **C117** [measured] Merges follow releases closely: 10 of 18 held PRs merged within 120 s of the label's removal (18 s minimum) and 16 of 18 within 10 min. — Own measurements, L1-M3
- **C118** [inference] From GitHub's record alone, a release by the user and one by an agent under the user's token look the same: same actor login, no app marker. — from [C102], [C115], [C126]
- **C119** [measured] This device's transcripts (2,444 files modified since 2026-10-15) contain no agent command that removes `waiting-human-review` from any of the 18 held PRs within 10 min of the GitHub unlabel. 0 of 18 releases have an agent match here. — Own measurements, L1-M5
- **C120** [measured] Agent sessions on this device ran `gh pr merge <N> --disable-auto` on #2137 and #2138, about 1 h 45 min before the release. — Own measurements, L1-M6
- **C121** [measured] Agent sessions on this device merged 2 held HIGH PRs after someone under the `Osasuwu` login released them: #2158, 40 s after the release, and #2159, 100 s after, the second with `--match-head-commit`, chained after a `gh pr view` that reads the PR's labels. — Own measurements, L1-M6
- **C122** [measured] An orchestrator ledger on this device (local file, 2026-11-04 run) records that the orchestrator placed the hold on #2186/#2187/#2189 because risk-tier passes admin authors. — Own measurements, L1-M11
- **C123** [measured] The same ledger shows the orchestrator leaving the red hold alone and treating its release as the user's act. — Own measurements, L1-M11
- **C124** [measured] That ledger attributes the #2186/#2187/#2189/#2193/#2194/#2196 merges to the user, #2189 and #2194 as review-blind admin-merges. It is an agent's self-report. — Own measurements, L1-M11
- **C125** [measured] Not every HIGH PR got a label. Worker subagent work on #2218 (HIGH) ran `gh pr create --draft` with no `--label` and later a command containing `gh pr ready 2218`. GitHub records `ready_for_review` by `Osasuwu` about 3 min later, and the PR merged with no hold label. — Own measurements, L1-M7
- **C126** [measured] Before the window, an agent command on this device did remove the label on a jarvis PR. #1924 (2026-09-24): `gh pr edit <N> --remove-label "waiting-human-review"` at 11:58:36Z, then GitHub `unlabeled` by `Osasuwu`, no app, at 11:58:38Z, and a merge 7 min later. — Own measurements, L1-M8
- **C127** [measured] Two agent `--remove-label waiting-human-review` attempts on music-intel-mcp ended in an error or no result. — Own measurements, L1-M5
- **C128** [quoted] /implement places the label at creation on a HIGH PR and never merges it, but has no rule against removing the label. — "HIGH or CRITICAL → place the hold the repo enforces (below), turn Auto-fix off (the paragraph after the hold), tell the user in chat that the PR waits for them and that Auto-fix is off on it, then go to step 8; the run never merges it." — [S7], §5, line 210
- **C129** [quoted] /orchestrate forbids the orchestrator to act as the user's approval: approving reviews, removing `waiting-human-review`. — "**Never act as the user's approval.**" … "Labels: remove `waiting-human-review`, `needs-*` or `status:owner-queue`; apply `priority:critical`." — [S8], §1 rule 7, lines 43-45
- **C130** [quoted] /orchestrate's worker rules forbid workers to remove the label. — "Never remove `waiting-human-review`, `needs-*` or `status:owner-queue`, and never apply `priority:critical`." — [S9], Gate labels, line 72
- **C131** [quoted] merge-push-guard enforces exactly three rules: deny `--admin`, ask on redrobot HIGH/CRITICAL merges, deny pushes to master/main. Other repos' merges pass, and labels and approvals are not mentioned. — "Merges of other repos pass." — [S10], docstring, rules 1-3, lines 4-14
- **C132** [measured] No jarvis-private hook mentions the label or `--approve`. The 3 "label" hits in merge-push-guard.py are a message variable and a gh subcommand list. The user's auto-mode rules allow `gh pr edit:*` and merges of own-repo PRs "whichever session opened the PR", with no clause on hold labels or approvals. — Own measurements, L1-M10
- **C133** [measured] The user's auto-mode allow rule lets any session merge own-repo PRs with `gh pr merge`, `--auto` included. Only `--admin` and API/GraphQL merges are soft-denied. — Own measurements, L1-M10
- **C134** [inference] For an admin-authored jarvis HIGH PR, the only CI hold is the label, and it binds any session holding the user's token only by convention. Placing it is a skill instruction, and 4 of 22 HIGH PRs went without it. Not removing it is a skill rule (orchestrate, worker rules) with no hook behind it. The check accepts an agent's release as human. — from [C101], [C102], [C104], [C108], [C116], [C128], [C129], [C130], [C131], [C132], [C133]
- **C135** [inference] On this device, no release of the 18 holds was agent-issued, and agents merged 2 of the 18 PRs after a release. "A HIGH merge needs a human" holds in practice as a habit that GitHub's record cannot verify: 4 of 22 HIGH PRs had no hold at all, and two other devices are unexamined. — from [C115], [C116], [C118], [C119], [C121], [C124]
### Q2 — Whether music-intel-mcp's copy of the code-gate verdict script misses fixes that matter for its traffic — answered with a gap

- **C201** [measured] music carries 9 gate files that also exist in jarvis (6 workflows, 3 scripts). Three are identical to jarvis main (github_client.py, unblock_ready.py, unblock-ready.yml); music's code_gate_verdict.py is closest to jarvis commit bee8706e of 2026-10-16 (similarity 0.896) and further from jarvis main (0.750) — Own measurements, L2-M1
- **C202** [quoted] music's last change to code_gate_verdict.py (2026-10-16, PR #255) is a port of like-current-song#250 — "Port of Osasuwu/like-current-song#250." — [S11], commit message
- **C203** [quoted] music's original gate port pulled fixes from like-current-song too, not only from jarvis — "fix(code-gate): port like-current-song#227 review fixes (#226)" — [S12], squash-commit body, third bullet
- **C204** [measured] After the port point, jarvis made 9 commits to code_gate_verdict.py. 6 change behaviour (#2067 path policy, #2076 page cap, #2068 shared client, #2079 daily sweep, #2081 unreadable listing, #2085 failed PATCH) and 3 change only docstrings (#2140, #2124, #2190) — Own measurements, L2-M2
- **C205** [measured] Fix markers from those 6 commits are absent from music's copy: ListingTruncated 4 vs 0, github_client 15 vs 0, sweep 9 vs 0, _post_red 3 vs 0, path_policy 9 vs 0 (jarvis vs music); music's code-gate-verdict.yml has no schedule — Own measurements, L2-M3
- **C206** [quoted] #2076 (page cap) fixes a silent truncation that jarvis itself called latent — "Latent today (31 dispatch runs on main vs a 300-run cap)." — [S13], Description
- **C207** [quoted] music's copy still truncates silently at the cap — "All items of a paginated list endpoint (up to `max_pages`)." — [S14], def paged
- **C208** [measured] music is far from the cap: 6 Code Review dispatch runs in total against a 300-run cap (MAX_RUN_PAGES = 3), and every merged head since the port has exactly 1 verify-verdict check run (the check-run listing reads one page of 100) — Own measurements, L2-M4, L2-M6
- **C209** [quoted] #2079 (daily sweep) fixes a green verdict outliving its expired evidence, also called latent in jarvis — "Latent today (no long-lived open PRs), but it makes a green verdict outlive its evidence." — [S15], What
- **C210** [measured] music cannot reach that condition yet: artifacts are kept 90 days and its oldest open PR was opened 2026-11-01 (18 days ago) — Own measurements, L2-M4
- **C211** [quoted] Without the sweep, music still turns an expired artifact red on the next event for the SHA — "an expired artifact turns the gate red" — [S16], comment above Upload review evidence
- **C212** [quoted] #2081 (unreadable check-run listing leaves an old green) was found by a review, not by an incident — "(found by the fresh-context review of slice 1, PR #2080)" — [S17], Parent
- **C213** [quoted] #2085 (a failed PATCH on a red verdict leaves the old green) was also found by review, reproduced with a probe — "Reproduced by probe 2 in the review's `probes-2084/parse_crash.py` (production code unmodified)." — [S18], Steps to Reproduce
- **C214** [inference] Both #2081 and #2085 need a GitHub API error inside post_check after an earlier green check exists on the same head, and either one fails the verdict job. music had 0 failed verdict runs out of 104 since the port, so neither has happened there — from [C212], [C213], [C226]
- **C215** [quoted] Before #2068, code_gate_verdict was the only jarvis `.github/scripts` script that retried 502/503/504; #2068 set one retry policy for every caller — "Only `code_gate_verdict` retries 502/503/504." — [S19], What
- **C216** [quoted] music's client still retries only 502/503/504, so a 403/429 rate limit fails the verdict run (red verdict-error, fail-closed) instead of backing off — "if exc.code in (502, 503, 504) and attempt < attempts:" — [S14], class Api.__call__
- **C217** [quoted] #2068's empty-GET-body fix was motivated by waiting-human-review going green, not by code-gate — "On a GET that turned an unreadable PR into one with no hold, and waiting-human-review went green where the base went red." — [S20], second commit in squash body
- **C218** [quoted] #2067 is a jarvis-only refactor: code-gate's machinery list moves into jarvis's shared protected-paths file. music keeps its own literal list, so the fix does not carry over — "agents/path_policy.py is now the only reader of config/protected-paths.json." — [S21], second commit in squash body
- **C219** [quoted] jarvis #2044 (editing a PR body cancels the in-flight review, and code-gate goes falsely red) was a real incident in jarvis — "Seen on 2026-10-08 and 2026-10-13" — [S22], What
- **C220** [quoted] music already avoids #2044 another way: job-level concurrency, from the like-current-song port — "Job-level, so it is evaluated after the `if` below: a skipped" — [S16], jobs.review comment
- **C221** [quoted] jarvis #2179 (the reviewer's findings write is denied after a `cd`, so the gate goes falsely red) names music as affected — "The same workflow and allowed-tools string are in Osasuwu/jarvis, Osasuwu/like-current-song and Osasuwu/music-intel-mcp." — [S23], Bug Description
- **C222** [quoted] #2179's evidence comes from like-current-song, where the write was denied in 2 of the 4 runs listed — "denied twice" — [S23], Steps to Reproduce table
- **C223** [quoted] music still carries the cwd-relative grant that #2179 fixed (github.workspace count is 0 in music's code-review.yml) — "Edit(./.review/findings.json)" — [S16], --allowed-tools, both attempts
- **C224** [measured] #2179 has not hit music in the sample: in 13 of 13 reviewed Code Review runs (the 14 newest successful ones; 1 was a skip), findings passed validation on attempt 1 and the retry never ran. The 3 failed review runs since the port are all on PR #244 (the port itself); the two whose steps were read failed at "Prepare review inputs" — Own measurements, L2-M7, L2-M5
- **C225** [quoted] jarvis #1999 makes waiting-human-review re-apply the hold when a bot releases it. music's copy predates it and has 0 "bot" mentions — "re-applies the label when osasuwu-bot (or any *[bot] actor) released the hold" — [S24], AP5
- **C226** [measured] Since the port, music has run Code Gate Verdict 104 times: 102 success, 0 failure, 2 cancelled. Code Review: 43 success, 3 failure (all on #244), 4 cancelled — Own measurements, L2-M5
- **C227** [quoted] jarvis #2082 closes a bypass in which the lane bot labels its own PR `priority:critical`; the fix also refuses the label when the PR's author applies it — "The lane bot has write access and could label its own PR priority:critical" — [S25], first commit body
- **C228** [measured] music has no bot author: of its 60 newest PRs, 58 are by Osasuwu (User) and 2 by dependabot[bot]. It has no agent-dispatch or lane workflow (7 workflows in all) — Own measurements, L2-M4
- **C229** [quoted] jarvis #1178 fails the check when a commit names an open issue that the PR body does not link. It applies to music in principle; whether it happened there was not checked — "A `(#N)` commit headline naming an open same-repo issue that the body does not link now fails the check" — [S26], first commit body
- **C230** [measured] Of 22 music PRs merged since 2026-10-08: 19 merged on a green evidence-clean verify-verdict. 2 merged on a red gate-machinery verdict: #255, a code-gate fix, and #258, a dependabot actions bump. 1 (#244, the port itself) has no check. Each head carries exactly one verify-verdict check run, from osasuwu-ci — Own measurements, L2-M6
- **C231** [measured] Branch protection on music main requires verify-verdict, bound to App 3969106, with strict up-to-date and enforce_admins off. There are no rulesets — Own measurements, L2-M4
- **C232** [inference] No music merge went through on a missing, stale or wrongly green verdict that the drift could explain. The 2 red merges are gate-machinery PRs, the review-blind class the admin carve-out covers, and none of the post-port jarvis fixes touches that path — from [C230], [C231], [C204]
- **C233** [measured] No music issue filed after 2026-10-08 names a gate failure. Issues naming verify-verdict stop at #251 (2026-10-08); a "stale/stuck/flaky" search since 10-17 finds only product PRs — Own measurements, L2-M8
- **C234** [quoted] An open music issue plans to replace the review-workflow copy with jarvis composite actions pinned by SHA — "Replace this repo's copy of the review workflow with thin callers of the jarvis composite actions (code review and risk tier), pinned by full SHA." — [S27], What to build
- **C235** [quoted] Its jarvis parent #2205 (open) already asks for drift to be detectable — "The action exposes a stable reference a team repo's own copy can be diffed against, so the weekly retro can report drift." — [S28], Acceptance criteria
- **C236** [measured] jarvis main has only one shared action so far (.github/actions/risk-tier). #2205 and #2200 are open — Own measurements, L2-M9
- **C237** [inference] #2205 and #283 name the review steps and risk-tier, not code_gate_verdict.py or code-gate-verdict.yml. Whether the verdict script joins the shared action is not stated — from [C234], [C235]
- **C238** [inference] The drift has cost nothing observable in music so far. Of the 6 behaviour fixes it lacks in the verdict script, 2 are latent at music's volume (#2076, #2079), 2 need a GitHub API error during the write and none appeared in 104 runs (#2081, #2085), 1 is a jarvis-only refactor (#2067), and 1 only adds retries where music already fails closed (#2068). Of the workflow fixes: #2044 is covered another way, #1999 and the bot half of #2082 need a bot author that music lacks, and #2179 applies and is unpatched but was not seen in 13 runs — from [C204], [C208], [C210], [C214], [C216], [C218], [C220], [C223], [C224], [C228], [C232], [C233]
- **C239** [inference] Under the user's rule for proposing a check (a linked incident, or a miss that costs more than the check), a source-stamp CI check has no incident to cite. A one-time re-port fits the evidence: #2179's grant first (one line, live in a sibling repo), then the fail-closed write paths (#2081, #2085). #283/#2205's pinned action plus its drift reference would replace the copy for the review workflow anyway — from [C221], [C222], [C234], [C235], [C238]
- **C240** [inference] A stamp naming the jarvis source commit would miss fixes that arrive via like-current-song, which is music's second upstream (lcs#227, lcs#242, lcs#250). The stamp would have to name lcs as well, or the copies would have to be pulled from one canonical source — from [C202], [C203]
### Q3 — Whether storytold's apps with AutoCraft differ in outcomes from its apps without it — answered with a gap

- **C301** [measured] PRs created Nov 1–18 carrying AutoCraft's "Not a maintainer decision" note: designcraft 347 of 461, deckcraft 244 of 376; photocraft 3 of 1979, wordcraft 2 of 1014, filmcraft 1 of 700, lightcraft 3 of 549 — Own measurements, L3-M1
- **C302** [measured] The autocraft-bot app reviewed 296 designcraft PRs and 209 deckcraft PRs, and 0 in photocraft, wordcraft, lightcraft, filmcraft and craft-anything — Own measurements, L3-M2
- **C303** [measured] The note first appears on items created Oct 7 (designcraft #65) and Oct 10 (deckcraft #66); weekly note share of new PRs rose from 19/437 and 14/191 (Oct 1–12) to 166/213 and 90/137 (Nov 10–18), with the step up in the week of Nov 3 — Own measurements, L3-M3
- **C304** [measured] photocraft has 80 PRs created Oct 13–19 that match the note text, but in 8 sampled the note was in neither the body nor the first 40 comments; outside that week photocraft never exceeds 3 a week — Own measurements, L3-M3, L3-M12
- **C305** [inference] AutoCraft has been on in designcraft and deckcraft since about Oct 7–10, at 4–33% of new PRs per week in October and 66–80% from Nov 3; it has not run on photocraft, wordcraft or filmcraft in November. So Nov 3–18 is the cleanest on-vs-off window — from [C301], [C302], [C303], [C304]
- **C306** [measured] The shared gate job `gate / gate (ubuntu-24.04)` runs on main pushes in all five apps; photocraft's failing checks also include a Windows test job and a wasm-size gate — Own measurements, L3-M11
- **C307** [measured] Created: photocraft Sep 30, filmcraft Sep 30, designcraft Oct 1, deckcraft Oct 7, wordcraft Oct 7. Disk (KB): photocraft 203,124, wordcraft 54,248, filmcraft 42,492, designcraft 42,017, deckcraft 13,910. Stars: 80,276 / 18,237 / 18,548 / 5,322 / 4,868 — Own measurements, L3-M1
- **C308** [measured] PRs merged Nov 1–18: photocraft 1058, wordcraft 426, filmcraft 297, designcraft 286, deckcraft 198 — Own measurements, L3-M1
- **C309** [inference] filmcraft is designcraft's closest off-group match (same week of birth, same disk size, 297 vs 286 merges); photocraft differs from every other app by 3.7–15x in disk size and 2.5–5.3x in merge volume, so photocraft-vs-designcraft compares mostly size and volume, not AutoCraft — from [C307], [C308]
- **C310** [measured] Window A (Nov 15 16:00–Nov 18 17:00 UTC), gate-red share of main time: photocraft 42% (29 of 54 commits red), filmcraft 5% (8/58), designcraft 2% (3/25), wordcraft 0% (0/113), deckcraft 0% (0/32) — Own measurements, L3-M4
- **C311** [measured] Window B (Nov 4–8), gate-red time: designcraft 0% (0/43), deckcraft 0% (0/46), wordcraft 0% (0/103), filmcraft 0% (0/50); photocraft 16% (24/94) over the 28 h the sample reached (Nov 6 20:00–Nov 7 23:42, 500 of 1423 commits) — Own measurements, L3-M5
- **C312** [measured] Whole-rollup red time is driven by SonarCloud outside photocraft: wordcraft 43% (A) and 99% (B) with the gate green throughout; designcraft 2% and 12%; filmcraft 25% and 1%; deckcraft 0% and 1%; photocraft 48% and 84% — Own measurements, L3-M4, L3-M5
- **C313** [measured] Photocraft window A reproduces #2238's w1 (gate 42% red, longest streak 24.94 h) — Own measurements, L3-M4
- **C314** [inference] On the gate, the two AutoCraft apps (0–2%) and two of the three off apps (wordcraft 0%, filmcraft 0–5%) are in the same band; only photocraft is red often. The on/off split does not separate main health; photocraft does — from [C310], [C311], [C312]
- **C315** [measured] Merged PRs (merged Nov 10–18, newest-created first, 100 or 60 per app) whose head commit's rollup reads FAILURE at query time: photocraft 44/100, filmcraft 14/60, wordcraft 11/100, deckcraft 3/60, designcraft 2/60 — Own measurements, L3-M6
- **C316** [measured] Merged PRs with main-fix titles ("main red", "main green", "main CI", "fix main", "unbreak") Nov 1–18: photocraft at least 11 distinct, e.g. #15474 "Fix main's CI: gate, scorecard, Windows test build, web build"; wordcraft 4; designcraft 1 (#2797, a FreeBSD nightly); deckcraft 0; filmcraft 0. Real reverts: 0 in every app — Own measurements, L3-M10
- **C317** [inference] Per 100 merged PRs, main-fix PRs run ~1.0 in photocraft, ~0.9 in wordcraft, ~0.3 in designcraft, 0 in deckcraft and filmcraft. Off-group filmcraft matches the on-group, so the measure does not separate on from off — from [C308], [C316]
- **C318** [quoted] AutoCraft holds its own merges while main is red, except its main-fix PRs — "ready PRs and open batches wait, AutoCraft's main-fix PRs (branches `autocraft/main-ci-*`) do not" — [S29], Waits table, row "Main CI red" (line 767)
- **C319** [measured] autocraft-bot merged 25 of 60 sampled designcraft merges and 17 of 60 deckcraft merges; the rest were human logins (dylanmtaylor, FredApps, aiongg, skylartaylor) — Own measurements, L3-M6
- **C320** [measured] Closed unmerged as a share of PRs closed Nov 1–18, counted with search's `closed:` qualifier, which misses most closed-unmerged PRs in these repos (C401): designcraft 1.4% (4/290), deckcraft 3.4% (7/205), photocraft 5.1% (57/1115), filmcraft 6.3% (20/317), wordcraft 7.0% (32/458) — Own measurements, L3-M1
- **C321** [measured] Share of PRs created Nov 1–18 still open: designcraft 49%, deckcraft 48%, photocraft 54%, wordcraft 59%, filmcraft 59% — Own measurements, L3-M1
- **C322** [measured] Open-to-merge median (merged Nov 10–18): designcraft 2.1 h (n=60), deckcraft 3.1 h (n=60, p75 115.9 h), photocraft 9.4 h (n=100), filmcraft 12.7 h (n=60), wordcraft 35.6 h (n=100). Median lines changed 72.5 / 69.5 / 121.5 / 187.5 / 38.5 — Own measurements, L3-M6
- **C323** [measured] Within the AutoCraft apps, PRs with an AutoCraft review merged more slowly than those without: designcraft median 3.0 h (39) vs 1.4 h (21); deckcraft 12.5 h (42) vs 0.7 h (18) — Own measurements, L3-M6
- **C324** [inference] By the undercounting `closed:` counts, the on-group closes fewer PRs unmerged (1.4–3.4% vs 5.1–7.0%) and merges faster at the median (2–3 h vs 9–36 h), but the within-app split points the other way: the PRs that skip AutoCraft (likely maintainers' own) merge fastest. Faster merges are not shown to come from the review step — from [C320], [C322], [C323]
- **C325** [measured] On the sampled merged PRs, AutoCraft's pre-merge Opus review said "No blocking problems found" (incl. "not certain") on 31 of 39 in designcraft and 30 of 38 in deckcraft; the rest said "Small fixes needed" (5 and 4, two in each made by AutoCraft) or "Changes needed" (3 and 4). Each PR had one AutoCraft review — Own measurements, L3-M7
- **C326** [quoted] The post-merge review is a second Opus review of PRs the pipeline merged, only for PRs in the pilot — "A second Opus review of every PR the pipeline merged, to catch what the first review and the merge let through" — [S29], ## Post-merge review, para 1 (line 435)
- **C327** [quoted] Only defects become public issues; the full findings are on the dashboard item page — "A merged PR shows its findings with severity, text, file and line, and the issue filed for each defect" — [S29], ## Post-merge review, "Item page" bullet (line 442)
- **C328** [measured] Org-wide, exactly 6 issues carry the post-merge note ("AI-generated review (Opus)" + "Follow-up to #N"): all designcraft, all filed by aiongg Nov 3 23:35–Nov 4 02:18, none in deckcraft, none after Nov 4 — Own measurements, L3-M8, L3-M9
- **C329** [quoted] Example follow-up body — "_AI-generated review (Opus). Not a maintainer decision._ … Follow-up to #1294." — [S30], issue body, lines 1–3
- **C330** [measured] All six originals (#1222, #1294, #1302, #1424, #1968, #2168) had one AutoCraft pre-merge review reading "No blocking problems found" and were merged by aiongg Nov 3–4; three issues were filed 1–7 minutes after the merge (#1302 01:55 → #2288 01:57; #1294 02:17 → #2290 02:18; #2168 23:33 → #2283 23:40) — Own measurements, L3-M8
- **C331** [measured] Outcome of the 6: three closed as completed by merged fix PRs (#2290 by #2521 on Nov 9, #2283 by #2701 on Nov 12, #2281 by #2285 21 minutes after filing); three open, each cross-referenced by an open fix PR (#2337, #2297, #2295). None closed as not planned — Own measurements, L3-M8
- **C332** [inference] Where it could be seen, the post-merge Opus review caught defects the pre-merge Opus review passed (6 of 6 with "no blocking problems"), and maintainers treated them as real: half fixed within 0–9 days, half with fix PRs open, none rejected. The denominator (how many post-merge reviews ran and found nothing) is dashboard-only, so the hit rate is not measurable from GitHub — from [C326], [C327], [C328], [C330], [C331]
- **C333** [inference] The six were filed in one ~3-hour burst on one app and none since; whether the stage was stopped, scoped to a pilot, or found nothing filable later cannot be told from public data — from [C326], [C328]
- **C334** [quoted] jarvis #2233 (open) plans a non-blocking second Opus review next to code-gate on ~10 PRs, changing code-gate only if it keeps catching real defects code-gate misses — "code-gate changes only if the second review keeps catching real defects that code-gate misses" — [S31], body, line 15
- **C335** [inference] storytold's natural comparison gives no outcome-level evidence that AutoCraft's Opus review makes main greener or reduces fix-forwards: off-group filmcraft and wordcraft match the on-group, and photocraft, the one app red often, differs in size and volume and merges through red heads (44/100). The evidence for #2233 is narrower and per-finding: Opus findings judged real by maintainers (C331), including defects its own first pass missed (C330). That fits #2233's design of judging findings one by one, not main-health outcomes — from [C314], [C315], [C317], [C330], [C331], [C334]
- **C336** [inference] Confidence is low for any on/off causal effect: n = 2 vs 3 apps, AutoCraft rollout was gradual (4–33% of new PRs per week in October, 66–80% from Nov 3), windows are 3–4 days, the apps differ in owners, size and code, and AutoCraft's merges also follow a red-main hold (C318) that is a policy, not a review — from [C303], [C309], [C318], [C319]
### Q4 — What share of storytold's agent PRs is closed unmerged, and why — answered with a gap

- **C401** [measured] GitHub search's `closed:<range>` qualifier misses most closed-unmerged PRs in storytold repos: photocraft PRs created 2026-10-13 that are closed unmerged number 55 (all with closedAt in Oct–Nov), but adding `closed:2026-10-01..2026-11-19` returns 25 — Own measurements, L4-M3
- **C402** [measured] Same gap repo-wide: closed-unmerged photocraft 1,020 total vs 295 with `closed:>=2026-10-06` and 0 with `closed:<2026-10-06`; wordcraft 559 vs 121; designcraft 152 vs 26; jarvis 77 vs 75 (no real gap). `merged:` sums agree with totals (photocraft 4,352 in W1–W6 + 154 before ≈ 4,548) — Own measurements, L4-M2, L4-M3
- **C403** [inference] Window counts built on `closed:` (the earlier run's photocraft "~6% closed unmerged", C406 in prev_2235) understate storytold waste by roughly 3–5x; cohorts by `created:` are complete (they sum to the totals) and are used below — from [C401], [C402], [C404]
- **C404** [measured] photocraft PRs created in six weeks: 4,372 merged, 1,007 closed unmerged, 1,658 still open; 18.7% of closed PRs closed unmerged; dependabot is 31 of the 1,007 — Own measurements, L4-M4
- **C405** [measured] wordcraft (no AutoCraft: 4 PRs carry its note): 1,843 merged, 559 closed unmerged, 1,389 open; 23.3% of closed unmerged; dependabot 19 — Own measurements, L4-M4, L4-M1
- **C406** [measured] designcraft (AutoCraft: 559 PRs carry its note, first on #65 created 2026-10-07): 1,153 merged, 152 closed unmerged, 412 open; 11.6% of closed unmerged; dependabot 3 — Own measurements, L4-M4, L4-M1, L4-M2
- **C407** [measured] The oldest cohort (created 2026-10-06..12, ~95% resolved) ends up not merged in 24% of PRs in all three apps: photocraft 449+118 of 2,365; designcraft 71+29 of 414; wordcraft 116+41 of 650 — Own measurements, L4-M4
- **C408** [measured] Open backlog is the larger latent waste in wordcraft: 1,441 open PRs, 519 not updated since before 2026-11-04; 30% of the W2 cohort (362 of 1,209) still open after four-plus weeks. photocraft: 1,789 open, 130 stale; designcraft: 433 open, 61 stale — Own measurements, L4-M1, L4-M2, L4-M4
- **C409** [measured] Unmerged share falls in designcraft after its first two weeks (18.4%, 12.5%, then 5.3–9.2%) but not in photocraft (17.9–21.8% in W1–W4, then 12.4% and 16.6%) or wordcraft (19.0–34.0%); later cohorts are right-censored by open PRs — Own measurements, L4-M4
- **C410** [inference] Correlation only: designcraft had AutoCraft from its first week, when its unmerged share was as high as the others (18.4%), so its later drop does not line up with AutoCraft adoption; lower volume and contributor mix are equally plausible — from [C406], [C409]
- **C411** [quoted] A closed-unmerged PR may still have landed: wordcraft#4059 was landed in #5753 on current main, with the maintainers resolving the conflicts and the author credited — "Landed in #5753 on current main (docs conflicts resolved by us), with you credited as co-author." — [S32], last comment
- **C412** [quoted] Same pattern in designcraft: a closed PR merged from its branch by hand — "Landed on main in 26137acb — thank you for the contribution!" — [S33], last comment
- **C413** [measured] Across 94 non-dependabot closed-unmerged PRs: duplicate or already fixed elsewhere 40 (43%), no reason given 22 (23%), housekeeping (wrong repo, reopen, split, self-replaced) 9 (10%), folded into a broader or integration PR 6, landed by another route 6, closed after review asked for changes 5, not needed (no repro) 3, obsolete after main moved 2, integration batch abandoned 1 — Own measurements, L4-M5, L4-M6
- **C414** [measured] Per sample, duplicate share of non-dependabot closes: photocraft Oct 6–12 12/20 (60%), photocraft Nov 10–18 4/16 (25%), wordcraft Oct 6–12 12/15 (80%), wordcraft Nov 3–18 4/20 (20%), designcraft Oct 6–Nov 18 8/23 (35%) — Own measurements, L4-M6
- **C415** [measured] Most closes are by the PR's own author, not a maintainer or bot: 69 of 94 non-dependabot sample PRs self-closed; no sampled PR was closed by autocraft-bot — Own measurements, L4-M6
- **C416** [measured] Duplicates are cheap per item: photocraft early duplicates total 2,179 changed lines over 12 PRs; the early wordcraft sample's median non-dependabot close is 12 lines, 4 of 15 have zero diff (claim-drafts); merged-PR medians for comparison: photocraft 132, wordcraft 32, designcraft 57 lines — Own measurements, L4-M6, L4-M7
- **C417** [measured] dependabot group PRs are 9 of 25 in the late photocraft sample and 7 of 27 in the late wordcraft sample, all closed by dependabot itself as superseded; they are not agent work — Own measurements, L4-M6
- **C418** [quoted] A maintainer duplicate close, first-opened wins — "#3501 fixed #3486 the same way and was opened earlier ... so we landed that one. Closing this as a duplicate." — [S34], last comment
- **C419** [quoted] A collision between two of the maintainer's own agent sessions — "Closing as a duplicate of #49: another session was already rolling out Windows ARM64 from the same PrintCraft #66 template, and its PR came first." — [S35], last comment
- **C420** [quoted] In photocraft#12870 the review found the fix right but asked for unrelated work to be stripped from the branch before taking it — "The fix itself is right ... Before we can take it, the branch needs some cleanup: - **Keep only this item's change.**" — [S36], davidmann4 comment 2026-11-10
- **C421** [quoted] The maintainer finished the fix in a replacement PR instead of iterating on the stacked one — "the Pen Shift-click fix from this PR is finished in #13161, which replaces it." — [S37], davidmann4 comment 2026-11-12
- **C422** [quoted] Batching was abandoned in wordcraft because main moved too fast for a batch to stay mergeable — "Main moves too fast for a batch to stay mergeable, and each PR in it needs its own review and CI at its current head anyway, so batching only adds a step." — [S38], last comment
- **C423** [prior] Opposite batching outcome in photocraft: fixes were folded into #15474 because each alone left main red (photocraft#15473, from prev_2235 L3-M4) — not fetched in this run
- **C424** [quoted] The RFC's 172/148 figure is a contributor's count of PRs naming an issue, updated 2026-10-15 from 108 issues on Oct 11 — "**172 issues** have fixing PRs from two or more authors (108 on Oct 11), with **148** of those PRs closed unmerged." — [S39], comment 2026-10-15 (kayrockscreenprinting)
- **C425** [quoted] The same commenter shows claims did not protect a claimant under the old rules — "I claimed #4107 with a comment and a draft PR (#4108). A second PR (#4138) opened 35 minutes later and merged that night, so mine was dropped." — [S39], comment 2026-10-15
- **C426** [quoted] RFC-0003 makes claim-before-code the rule for people and agents — "**Coding agents follow the same rules.** An agent working on a backlog does steps 1 and 2 right before starting each issue, claims before writing code" — [S40], Proposal 9
- **C427** [measured] RFC-0003 merged 2026-11-12 (craft-contrib a915429a "RFC-0003: Claiming issues (#4)"); house rule 2 "Check, then claim" and rule 6 "Look for a better pull request" were already in the shared house rules from 2026-11-06 (48ae9e42); photocraft's contributing-doc claim PR #3576 is still open and #2847 closed unmerged 2026-11-08 — Own measurements, L4-M8
- **C428** [quoted] Shared house rule 6 tells the losing author to close — "If another fixes the same thing, close yours when it is better or equal, and say why." — [S41], rule 6
- **C429** [quoted] A post-rule collision: a claimant missed linked PRs while checking and produced a three-way duplicate — "we checked the issue's comments when claiming and missed the linked PRs - our miss, sorry for the three-way" — [S42], last comment 2026-11-14
- **C430** [measured] Closed-unmerged PRs whose comments say "duplicate", per created cohort, photocraft: 53, 43, 24, 9, 10, 10 (W1..W6) = 2.2%, 2.8%, 2.7%, 1.6%, 1.5%, 1.0% of PRs created; as share of closed-unmerged 12–20% with no trend; wordcraft 9, 29, 19, 17, 16, 3 — Own measurements, L4-M9
- **C431** [inference] Duplicates per PR created fell in photocraft from late October (W4 cohort, Oct 27), before house rules (Nov 6) and RFC-0003 (Nov 12); the sample's 60%→25% duplicate share is not matched by the keyword count, and W5–W6 are censored. The data cannot credit claiming with the drop; at most it is consistent with it — from [C414], [C427], [C430]
- **C432** [quoted] photocraft epic #15476 asks whoever picks up an item to open a draft PR naming it within a day — "**Open a draft PR soon** (within a day) that names the item" — [S43], How to pick up an item, step 3
- **C433** [measured] Same cohort (created 2026-10-06..11-16): jarvis 111 merged, 17 closed unmerged, 5 open (13.3%); music-intel-mcp 24/4/2 (14.3%); redrobot 496/10/11 (2.0%, counts only) — Own measurements, L4-M4
- **C434** [measured] Of jarvis's 17 closes, 7 are dependabot and 9 are deliberate canary or seeded-defect PRs; one (#2214) was superseded by #2218 with its tests folded in. All 4 music-intel-mcp closes are canaries. Real thrown-away work: about 1 PR in 6 weeks — Own measurements, L4-M10
- **C435** [inference] Our waste is near zero because one principal picks the work serially; the largest single reason in storytold's ~24% is duplicate or already-fixed work (43% of sampled closes), from many authors picking the same issue in parallel, which autonomous merge or advisory CI alone would not cause for us — from [C407], [C413], [C434]
- **C436** [inference] Pushing our throughput by running parallel agent sessions reintroduces storytold's main cause: designcraft#50 is two sessions of one maintainer colliding. The cheap counter is a claim before code, checked against open PRs and main, which redrobot partly has — from [C419], [C426], [C429]
- **C437** [quoted] In the AIDev study, human PRs merge at 82.6% and agent PRs at 55–86% by agent — "OpenAI Codex 20,993 85.8% Devin 4,673 55.5% GitHub Copilot 3,891 55.0% Cursor 1,347 74.6% Claude Code 380 71.3% Human 6,149 82.6%" — [S44], Table 1
- **C438** [quoted] In that study's sample of rejected PRs (agent and human), 67.9% carry no clear reviewer feedback on why, more than the 23% with no reason in our storytold sample — "the majority of rejected PRs (67.9%) do not include clear reviewer feedback about why the change was rejected" — [S44], Finding #3
- **C439** [inference] storytold's ~76–81% merge rate of closed PRs (photocraft, wordcraft) lies between that study's mid-range agents (71–75%) and its human baseline (82.6%), above the weakest agents (55%) — from [C404], [C405], [C437]

## Disconfirming evidence

- [C102]/[C104] — I looked for any login-to-role check on release in waiting_human_review.py (searched for "admin", "permission", "collaborators"). There is none; the only test is `is_non_human`. The probe (L1-M9) confirms that an admin-login release clears the check.
- [C108]/[C113] — I looked for a HIGH declared PR whose risk-tier failed in the window: 12 of 12 sampled show success, and both logs read show "hold skipped". Nothing found against. The last 10 of the 22 HIGH PRs were not sampled.
- [C115] — Looked for app or bot label events (a workflow re-apply shows `github-actions`): none of 37.
- [C119] — The opposite would be an agent remove-label on a held PR. I widened the search to every repo, all dates since 2026-10-15, and MCP label-set tools. That found agent remove-label on jarvis#1924 (outside the window, C126) and two failed music-intel-mcp attempts (C127), and none on the 18. Gap: the other two devices and the GitHub web UI leave no record here.
- [C121] — Did the #2158 and #2159 merges race the release? No: both agent commands come after the GitHub unlabel, and #2159's reads the labels first.
- [C116]/[C125] — I checked whether the 4 unlabelled HIGH PRs had another hold. #2215 and #2218 were drafts until readied by `Osasuwu` (one by a worker command). #2164 and #2234 show no draft, label or review event.
- [C129]-[C133] — The opposite would be a hook or permission rule that blocks label removal or approval. I grepped all jarvis-private hooks, hooks.json and user settings (permissions and autoMode): none. merge-push-guard's docstring scopes it to merge/push.
- [C112] — I looked for a newer CONTEXT.md wording: 14a29594 still has "only notifies".
- Claim C238 (no cost yet): searched for harm instead of assuming none. Queried every failed Code Gate Verdict run since the port (0 of 104), every failed Code Review run (3, all on the port PR, at input prep), verify-verdict on every merged head (no green without evidence; 2 red merges, both gate-machinery), issues naming verify-verdict or stale/stuck/flaky (none since 10-08 about the gate). Nothing came back against.
- Claim C224 (#2179 not seen): looked for the silent form a single failure would take, a first-attempt validation failure that the retry hides. 0 of 13 sampled runs. Limit: the 29 older successful runs (10-08 to 11-15) were not inspected.
- Claim C208/C210 (page cap and expiry latent): checked the real inputs (6 dispatch runs, 1 check run per head, oldest open PR 18 days) instead of assuming low volume. Nothing against.
- Claim C220 (#2044 covered): read music's concurrency block directly. The job-level group is evaluated after the `edited` filter, which is the effect jarvis's fix gets. The 4 cancelled review runs sit on heads that then got a successful review and a green verdict (#285, #286, #291) or on the 10-08 canary #250, so no evidence-none red.
- Claim C239 (re-port over stamp): searched for an existing plan that would make either option moot and found music #283 and jarvis #2205 (open), which retire the review-workflow copy with a SHA pin and a drift reference. Neither names the verdict script (C237), so the question stays open for code_gate_verdict.py.
- Claim C228 (no bot author): checked the 60 newest PR authors and the workflow list. Not checked: whether an agent session on the user's token removes waiting-human-review labels in music (jarvis #1999 would not catch that either: it tests for bot actors).
- For [C314] (on/off does not separate main health): looked for an off app as green as the on apps — filmcraft and wordcraft are (gate 0–5%). Looked for the opposite in a second window (B): on apps 0%, off apps 0% except photocraft. Nothing found against.
- For [C315/C317] (photocraft merges through red): a red head at query time could be a later rerun; #2238 C410 already showed 16 gate-red merges in 23 minutes on Nov 18, so the merge-through-red reading stands for photocraft.
- For [C324] (faster merges not shown to come from review): the within-app split (C323) is the counter; it shows the review-free PRs merge fastest, so the cross-app gap more likely reflects who merges and how big the queue is.
- For [C330/C331] (post-merge findings real and fixed): searched org-wide for other AutoCraft follow-ups or ones closed as not planned (L3-M9): none; no issue was rejected. Counter: only 6 exist, one burst, one app.
- For [C335] (no outcome evidence for adopting): web search "storytold AutoCraft designcraft Opus review results main broken" returned nothing on AutoCraft outcomes; storytold publishes no own comparison that was found.
- [C404]–[C407] (~19–24% of storytold PRs not merged) — query: total vs `closed:` counts (L4-M3) and `created:` cohorts (L4-M4); the earlier run's ~6% came from the undercounting qualifier; nothing found that lowers the cohort numbers. Censoring of later cohorts can only raise them.
- [C413] (duplicates are the leading cause) — query: `duplicate in:comments` keyword counts per cohort (L4-M9): only 12–20% of closed-unmerged say "duplicate"; the sample's 43% includes "superseded"/"already fixed on main" wording. Duplicates lead in the sample, but by keyword they are a minority; the 23% with no reason could hide more.
- [C431] (claiming cannot be credited) — query: sample before/after vs keyword cohorts (L4-M6, L4-M9) plus #14873 collision after the rules; the sample suggests a drop, the keyword counts show the drop began before the rules. Kept as "consistent with, not shown".
- [C410] (AutoCraft not shown to cut waste) — query: designcraft first AutoCraft note date (L4-M2) vs weekly unmerged share (L4-M4): AutoCraft present in W1 at 18.4%. Nothing found for an AutoCraft effect.
- [C435]/[C434] (our waste is near zero) — query: read every closed-unmerged jarvis/music-intel-mcp PR in the cohort (L4-M10); 1 real superseded PR. redrobot reasons not read (private, counts only).
- [C439] (storytold near human baseline) — web search `agentic pull requests acceptance rate study ... merged closed unmerged reasons arXiv`: AIDev studies report 55–86% by agent; datasets and filters differ, so the comparison is rough.


## Coverage

| Channel | Read | Gap |
|---|---|---|
| Users | storytold PR and issue threads: closed duplicates and re-lands (wordcraft#4059, designcraft#50, #971, photocraft#3911, #12870, #13008, #14873), batching (wordcraft#5032), the claiming thread photocraft#3561, epic #15476, designcraft post-merge follow-ups (#2290 and five more) | no forum discussion of storytold's waste or AutoCraft's effect; Reddit not used |
| Specialists | our code and rules: `waiting_human_review.py`, `risk_tier.md`, the 2026-Q4 decision entry, AGENTS.md, CONTEXT.md, the /implement and /orchestrate skills, merge-push-guard; music-intel-mcp's gate files and the jarvis fixes #2067–#2085, #2179, #1999, #2044, #2055, #2082; AutoCraft `docs/pipeline.md`; craft-contrib RFC-0003 and house rules; GitHub's protected-branch docs | the AutoCraft dashboard (post-merge findings, decision answers) is behind a login |
| Data | own measurements over the GitHub API and local files: jarvis PR timelines and risk-tier logs (L1-M1..M11), music-intel-mcp run and check counts (L2-M1..M9), gate-red time and merge outcomes across five apps (L3-M1..M12), creation-week cohorts and close reasons (L4-M1..M10); arXiv 2602.04226 as an outside baseline | samples are in GitHub's search or newest-first order, not random; transcripts read on one device of three |
| Adversarial | disconfirming searches per load-bearing claim; the #1924 label removal by an agent ([C126]); the search-filter undercount that overturned an earlier figure ([C401]–[C403]); the within-app split that cuts against AutoCraft speeding merges ([C323]) | no public post-mortem of an AutoCraft merge gone wrong |

Declared overruns:
- Q1: page reads past three, because the question is about our own code and skills; read by section.
- Q2: about 81 GitHub API calls against about 80, for one check-runs read per merged head.
- Q3: about 57 GraphQL calls with batched aliases; windows of 3–4 days, photocraft's window B truncated to 28 hours.
- Q4: within budget.

Q1's transcript search covers this device only: the other two devices and any release made in the GitHub web UI leave no trace here. No fetched page addressed instructions to the agents. Session transcripts and an orchestrator ledger were read locally; only counts and command forms enter this report. No search-and-scrape connector was used.

## Own measurements

<!-- ledger Q1 -->
### L1-M1

`gh api repos/Osasuwu/jarvis/branches/main/protection` (q1/gh_holds.py, 2026-11-19): "protection contexts=['require-linked-issue', 'pytest', 'code-gate', 'gitleaks', 'waiting-human-review', 'risk-tier', 'ruff'] strict=True" / "enforce_admins=False" / "required_pull_request_reviews=absent"

### L1-M2

q1/gh_holds.py: `gh pr list -R Osasuwu/jarvis --state merged --search merged:2026-10-20..2026-11-18` (all 42, not sampled) + `issues/<n>/timeline?per_page=100` for each of the 42: "declared risk: [('HIGH', 22), ('LOW', 13), ('MEDIUM', 7)]"; "PRs with any waiting-human-review label event: 18 -> [2121, 2137, 2138, 2150, 2158, 2159, 2166, 2169, 2180, 2186, 2187, 2189, 2193, 2194, 2196, 2209, 2210, 2232]"; "of which declared: [('HIGH', 18)]"; "label event (kind, actor, app) counts: [(('labeled', 'Osasuwu', None), 19), (('unlabeled', 'Osasuwu', None), 18)]"; "declared HIGH/CRITICAL with no label event: [2164, 2215, 2218, 2234]"; "other event … (('auto_squash_enabled', 'Osasuwu', None, None), 4), (('merged', 'Osasuwu', None, None), 42), (('ready_for_review', 'Osasuwu', None, None), 9)"; "author counts: [('Osasuwu', 42)]"; "mergedBy counts: [('Osasuwu', 42)]". q1/extra.py: "PR bodies with 'Generated with [Claude Code]': 40 of 42". 42 against 41 in the 2240 run: #2241 merged 11-18 20:14Z.

### L1-M3

q1/extra.py over M2 data: "unlabel->merge seconds, sorted: [18, 20, 31, 39, 44, 56, 64, 82, 92, 105, 144, 171, 282, 286, 289, 568, 40154, 245711]"; "<=120s: 10 of 18"; "#2215 held=False … auto=[('auto_squash_enabled', 'Osasuwu', '2026-11-16T07:40:07Z')]"; "#2218 held=False" with ready_for_review Osasuwu 2026-11-15T21:23:45Z.

### L1-M4

risk-tier check run on the head SHA of the first 12 declared-HIGH PRs by number (`commits/<sha>/check-runs?check_name=risk-tier`): all "conclusion=success". Job logs (`actions/jobs/<id>/logs`) for #2121 and #2187: "declared HIGH, computed HIGH, final HIGH" / "HIGH hold skipped: author Osasuwu has admin permission" (both).

### L1-M5

q1/scan_transcripts.py: every `*.jsonl` under ~/.claude/projects with mtime ≥ 2026-10-15 ("files scanned (mtime >= 2026-10-15): 2444"), subagents included. It reads tool_use of shell tools, GitHub MCP merge/review/label tools and user bash-mode input, each with its tool_result. q1/match.py: "transcript match: 0 ok / 0 total" for each of the 18; "held PRs with an agent-issued release on this device: 0". All remove-label commands, any repo (q1/other_removes.py): `gh pr edit <N> --repo Osasuwu/jarvis --remove-label "waiting-human-review"` once (#1924); `gh pr edit <N> --repo Osasuwu/music-intel-mcp --remove-label waiting-human-review` twice (is_error True / no result). The other hits are greps or heredocs. Approve: only `gh pr review 999999 --approve --repo Osasuwu/no-such-repo-rr3160-smoke` (error), none on jarvis.

### L1-M6

q1/match.py and q1/detail.py, merge commands naming the PR within 48 h before merge: "#2158 … 2026-10-21T12:54:01Z … `gh pr merge <N> --repo Osasuwu/jarvis --auto --squash`" (GitHub unlabel 12:53:21Z, merged 12:54:05Z); "#2159 … 14:05:28Z … `gh pr view <N> … --json state,headRefOid,labels,mergeStateStatus … && gh pr merge <N> --repo Osasuwu/jarvis --auto --squash --match-head-commit <sha>`" (unlabel 14:03:48Z, merged 14:05:33Z); #2137/#2138: `gh pr merge <N> --repo Osasuwu/jarvis --disable-auto` about 1 h 45 min before release. The other HIGH matches are heredoc ledger writes (false positives).

### L1-M7

q1/scan_unheld.py + q1/ready2218.py: #2218 creation in a worker subagent transcript: `gh pr create --draft --repo Osasuwu/jarvis --base main --head feat/2146-irreversible-coverage --title …` (no `--label`); "use 2026-11-15T21:20:44.550Z" for a command containing `gh pr ready 2218 --repo Osasuwu/jarvis`, result is_error False. No creation command for #2164, #2215 or #2234 on this device; 0 `mcp__ccd_pr__set_auto_merge` calls on jarvis since 2026-10-20.

### L1-M8

q1/gh_1924.py (`issues/1924/events`): "labeled waiting-human-review Osasuwu None 2026-09-24T11:58:11Z" / "unlabeled waiting-human-review Osasuwu None 2026-09-24T11:58:38Z" / "merged None Osasuwu None 2026-09-24T12:05:27Z"; transcript tool_use at 2026-09-24T11:58:36.318Z (M5).

### L1-M9

q1/probe_decide.py imports `waiting_human_review.py` from origin/main 14a29594: "release by 'Osasuwu': decide -> (False, 'clear', False)"; "release by 'osasuwu-bot': decide -> (True, 'bot-released', True)"; "release by 'github-actions[bot]': decide -> (True, 'bot-released', True)"; "release by '': decide -> (True, 'bot-released', True)"; "label present: decide -> (True, 'label', False)".

### L1-M10

`grep -c -i label hooks/*.py` in the jarvis-private checkout: only merge-push-guard.py:3, decision-overdue.py:19 and weekly-read.py:2 match, and none of them is about the hold label. The guard's 3 lines: "label = f\"merge of {selector…" / "confirm {label}" / a gh subcommand list containing "label". `grep` for remove-label/approve/waiting-human-review in hooks/ and settings.json: no rule. ~/.claude/settings.json permissions.allow line 35: "Bash(gh pr edit:*)"; permissions.ask holds only New-BwsSecret; autoMode.allow line 148: "Merge a pull request in Osasuwu/jarvis, … with `gh pr merge` (`--squash`/`--merge`/`--rebase`, `--auto`, `--delete-branch`) … — whichever session opened the PR (decision 2026-11-10, jarvis-private#134)"; soft_deny covers `--admin` and `gh api`/GraphQL merges only.

### L1-M11

`grep -n -i "2186\|…\|2196" LEDGER.md` in local ~/pm-runs/2026-11-04-m71 (an /orchestrate run ledger): line 103 "PM: added the `waiting-human-review` label to #2186/#2187/#2189 as the HIGH hold, since risk-tier passes for an admin author."; line 79 "waiting-human-review red = the HIGH hold I applied; releasing it is the user's — no action"; line 113 "**Merged this run:** #2186, #2187, #2189, #2193, #2194, #2196 (user); #2192 (PM)."; line 45 "#2189 … merged (by user, admin-merge review-blind)". The ledgers of the 10-20 and 10-27 runs no longer exist on disk.

<!-- ledger Q2 -->
### L2-M1

`python q2/sim.py` (difflib SequenceMatcher ratio, music origin/main file vs each jarvis commit to the same path since 2026-09-10; all commits, newest first): `code_gate_verdict.py (music 1198 lines)`: `0a2bb7c3 2026-11-04 jarvis 1350 lines ratio=0.750` … `bee8706e 2026-10-16 jarvis 1217 lines ratio=0.896` · `886e31d5 2026-10-14 ratio=0.778`; `github_client.py 4817278e ratio=1.000`; `unblock_ready.py 4817278e ratio=1.000`; `unblock-ready.yml e02ef8c2 ratio=1.000`; `code-review.yml fe4bd219 ratio=0.846`; `waiting-human-review.yml a8f930d6 2026-10-01 ratio=0.919`, `102fa7f2 2026-10-08 ratio=0.422`; `pr-body-check.yml 27a190b6 ratio=0.769` (max).

### L2-M2

`git log origin/main --format="%h %ad %s" -- .github/scripts/code_gate_verdict.py` in jarvis (all commits): after bee8706e: `0a2bb7c3 2026-11-04 docs(ci)… (#2190)`, `4d79e197 2026-11-04 docs(ci)… (#2124)`, `b7d63baa 2026-10-27 fix(ci): point code_gate_verdict docstring… (#2140)`, `a30b6a20 2026-10-17 … (#2085)`, `ffbe6c53 2026-10-16 … (#2081)`, `9ea44873 2026-10-16 feat(code-gate): daily sweep… (#2079)`, `17df8ff1 2026-10-16 … (#2068)`, `898273fb 2026-10-16 … page cap (#2076)`, `5a4aceba 2026-10-16 feat(path-policy)… (#2067)`. music same path: `72d215e 2026-10-16 …(#251) (#255)`, `55edd84 2026-10-08 Port…(#226) (#244)`. Doc-only status of b7d63baa/4d79e197/0a2bb7c3 from `git show --stat` and their bodies ("Wording only.", "Docstrings only.").

### L2-M3

`python q2/markers.py` (string counts, origin/main of both): `ListingTruncated jarvis=4 music=0`, `github_client jarvis=15 music=0`, `sweep jarvis=9 music=0`, `_post_red jarvis=3 music=0`, `path_policy jarvis=9 music=0`; code-gate-verdict.yml `schedule jarvis=10 music=0`, `cron jarvis=1 music=0`; code-review.yml `github.workspace jarvis=4 music=0`; waiting-human-review.yml `bot jarvis=4 music=0`; pr-body-check.yml `LANE_BOT_LOGIN jarvis=3 music=0`, `absorbed jarvis=2 music=0`.

### L2-M4

`python q2/gh1.py` (gh api, 7 calls): protection `"contexts": ["require-linked-issue", "lint", "test", "verify-verdict", "waiting-human-review"]`, `{"context": "verify-verdict", "app_id": 3969106}`, `"strict": true`, `enforce_admins … "enabled": false`; rulesets `[]`; retention `{"days": 90, …}`; PRs (newest 60 by created, state=all): authors 58 `Osasuwu(User)`, 2 `dependabot[bot](Bot)`; open: #293 2026-11-18, #289 2026-11-15, #261 2026-11-01; `CODE REVIEW dispatch runs total=6`. Workflow list (`git ls-tree`): ci, code-gate-verdict, code-review, gitleaks, pr-body-check, unblock-ready, waiting-human-review.

### L2-M5

`python q2/gh4.py` (runs?status=X&created>=2026-10-08, total_count): code-review `failure 3` (all `Code review PR #244`, 2026-10-08), `success 43`, `cancelled 4`; code-gate-verdict `failure 0`, `success 102`, `cancelled 2`. Failed-step check, `gh5.py`: `37785075372 … review failure :: Prepare review inputs`, `37774612851 … :: Prepare review inputs`.

### L2-M6

`python q2/gh2.py` (commits/{merged head}/check-runs?check_name=verify-verdict, all 22 PRs merged since 2026-10-08): 19 lines `n=1 :: completed/success app=osasuwu-ci title=verify-verdict: evidence-clean`; `#258 … n=1 :: completed/failure … gate-machinery`; `#255 … n=1 :: completed/failure … gate-machinery`; `#244 … n=0`. merged_by sample (#292, #287, #274, #258): `Osasuwu User`. Run code-gate MAX_RUN_PAGES in music: `MAX_RUN_PAGES = 3` (line 134).

### L2-M7

`python q2/gh6.py` (14 newest successful Code Review runs since 2026-10-08, jobs API step conclusions): 13 runs `Validate findings (attempt 1)=success; Reseed findings file for the retry=skipped; Run code review (attempt 2)=skipped`; 1 run (43831846465) `Record skipped review=success`, review steps skipped.

### L2-M8

`python q2/gh3.py`, `gh7.py`, `gh8.py` (search/issues): `repo:Osasuwu/music-intel-mcp verify-verdict` → 24, newest gate issue #251 2026-10-08 (others: #226, #224, #133, #146, #192, older; #269 pilot findings); `… created:>=2026-10-17 stale OR stuck OR "false red" OR flaky` → 4: #290, #274, #272, #259; body lines matched in #290/#274 are `skipped_stale`/`stale_version` (embedding versions), #272 no line match.

### L2-M9

`git ls-tree -r --name-only origin/main .github/actions/` (jarvis): `.github/actions/risk-tier/action.yml` only. `gh issue view` → `2205 Share the code-review mechanism as a composite action pinned by SHA OPEN`, `2200 … OPEN`, `2198 … OPEN`.

<!-- ledger Q3 -->
### L3-M1

`python meta.py` (aliased GraphQL search). Output: "photocraft {'createdAt': '2026-09-30T13:37:48Z', 'diskUsage': 203124, 'stargazerCount': 80276 …} 7358 {'note': 3, 'created': 1979, 'merged': 1058, 'unmerged': 57, 'revert': 1}"; "wordcraft {'createdAt': '2026-10-07T08:34:24Z', 'diskUsage': 54248, 'stargazerCount': 18237 …} {'note': 2, 'created': 1014, 'merged': 426, 'unmerged': 32}"; "designcraft {'createdAt': '2026-10-01T13:13:14Z', 'diskUsage': 42017, 'stargazerCount': 5322 …} {'note': 347, 'created': 461, 'merged': 286, 'unmerged': 4}"; "deckcraft {'createdAt': '2026-10-07T05:27:21Z', 'diskUsage': 13910, 'stargazerCount': 4868 …} {'note': 244, 'created': 376, 'merged': 198, 'unmerged': 7}"; "filmcraft {'createdAt': '2026-09-30T13:41:20Z', 'diskUsage': 42492, 'stargazerCount': 18548 …} {'note': 1, 'created': 700, 'merged': 297, 'unmerged': 20}". meta2: open created Nov 1–18 "photocraft 1074", "wordcraft 600", "designcraft 225", "deckcraft 182", "filmcraft 413". (merged = merged date in range; unmerged = closed date in range.)

### L3-M2

`python meta2.py` with `reviewed-by:app/autocraft-bot`, `commenter:app/autocraft-bot`: "designcraft … 'botreviewed': 296, 'botcommented': 314"; "deckcraft … 'botreviewed': 209, 'botcommented': 214"; photocraft, wordcraft, lightcraft, filmcraft, craft-anything "'botreviewed': 0, 'botcommented': 0". First note: "designcraft … (585, 65, '2026-10-07T02:27:45Z'"; "deckcraft … (412, 66, '2026-10-10T10:40:45Z'".

### L3-M3

`python weekly.py` (note-carrying PRs / all PRs by creation week): "designcraft 10-01..10-12 pr 19/437 | 10-13..10-19 pr 66/414 | 10-20..10-26 pr 90/341 | 10-27..11-02 pr 46/143 | 11-03..11-09 pr 172/216 | 11-10..11-18 pr 166/213"; "deckcraft 14/191 | 56/505 | 51/238 | 56/172 | 135/205 | 90/137"; "photocraft 3/2528 | 80/1557 | 2/885 | 1/563 | 1/670 | 2/1154"; "wordcraft 1/650 | 1/1209 | 0/612 | 0/484 | 0/472 | 2/427"; "filmcraft 2/774 | 5/541 | 0/492 | 1/385 | 0/288 | 1/252".

### L3-M4

Window A: `python sample.py <app> 2026-11-15T16:00:00Z 2026-11-18T17:00:00Z wA_<app>.json` (complete: every app "commits N of totalCount N", e.g. photocraft 195 of 195), then `python analyze.py wA_<app>.json`. "photocraft [gate] counts {'RED': 29, 'GREEN': 25, 'CANC': 1}; … time red 30.4h of 72.3h = 42%"; "[rollup] … time red 34.7h of 72.3h = 48%; closed streaks 6 median 2.12h max 24.94h"; "wordcraft [rollup] … time red 29.3h of 67.9h = 43%"; "[gate] counts {'GREEN': 113}"; "designcraft [gate] counts {'GREEN': 22, 'RED': 3}; … time red 1.3h of 72.8h = 2%"; "deckcraft [gate] counts {'GREEN': 32} … 0%"; "filmcraft [rollup] … time red 17.9h of 70.4h = 25%"; "[gate] counts {'GREEN': 50, 'RED': 8}; … time red 3.5h of 70.4h = 5%".

### L3-M5

Window B: same with 2026-11-04T00:00:00Z..2026-11-08T00:00:00Z. "photocraft calls 10 commits 500 of totalCount 1423"; "first-parent main 94 commits 2026-11-06T19:59:25Z .. 2026-11-07T23:41:59Z"; "[gate] … 24/94; time red 4.6h of 28.0h = 16%"; "[rollup] … time red 23.4h of 28.0h = 84%"; "wordcraft [rollup] … 82/103; time red 94.3h of 95.2h = 99%" / "[gate] counts {'GREEN': 103}"; failing "('SonarCloud Code Analysis', None), 55"; "designcraft [rollup] … 11.6h of 95.6h = 12%" / "[gate] counts {'GREEN': 43}"; "deckcraft [rollup] … 0.9h of 95.4h = 1%" / "[gate] counts {'GREEN': 46}"; "filmcraft [rollup] … 1.2h of 92.5h = 1%" / "[gate] counts {'GREEN': 50}".

### L3-M6

`python prs.py` (search `is:pr is:merged merged:2026-11-10..2026-11-18 sort:created-desc`, first 100 for photocraft/wordcraft, first 60 for the others after HTTP 502s). "photocraft: total merged in window 562, sampled 100; open->merge median 9.4h"; "mergedBy [('davidmann4', 47), ('dylanmtaylor', 20), ('FredApps', 16), ('aiongg', 10)…]"; "head rollup … {'FAILURE': 44, 'PENDING': 3, 'SUCCESS': 53}; lines changed median 121.5"; "wordcraft: … 173, sampled 100; … median 35.6h"; "{'SUCCESS': 89, 'FAILURE': 11}; … 38.5"; "designcraft: … 151, sampled 60; … median 2.1h"; "with AutoCraft review 39: median 3.0h …; without 21: median 1.4h"; "mergedBy [('autocraft-bot', 25), ('dylanmtaylor', 16), ('FredApps', 13), ('aiongg', 4), ('skylartaylor', 2)]"; "{'SUCCESS': 58, 'FAILURE': 2}; … 72.5"; "deckcraft: … 98, sampled 60; … median 3.1h p25 0.3h p75 115.9h"; "with AutoCraft review 42: median 12.5h …; without 18: median 0.7h"; "mergedBy [('FredApps', 27), ('autocraft-bot', 17), ('dylanmtaylor', 16)]"; "{'SUCCESS': 57, 'FAILURE': 3}; … 69.5"; "filmcraft: … 132, sampled 60; … median 12.7h"; "{'SUCCESS': 46, 'FAILURE': 14}; … 187.5". Head rollup is read now, not at merge time.

### L3-M7

`python verdicts.py` (autocraft-bot reviews in M6's sample): "designcraft PRs with AutoCraft review 39 reviews per PR {1: 39}"; "[('No blocking problems found.', 30), ('Small fixes needed:', 2), ('Changes needed:', 2), ('Small fixes needed, made in 05f08db:', 1), ('No blocking problems found (not certain).', 1), ('Small fixes needed (not certain):', 1), ('Small fixes needed, made in b325589:', 1), ('Changes needed (not certain):', 1)]"; "deckcraft … 38 … [('No blocking problems found.', 25), ('No blocking problems found (not certain).', 5), ('Changes needed:', 3), ('Small fixes needed:', 2), ('Small fixes needed, made in 0490748:', 1), ('Small fixes needed, made in 6ae02d2:', 1), ('Changes needed (not certain):', 1)]".

### L3-M8

`python followups.py`, `python originals.py`: "## dc_fu: 6"; "Is #2290 2026-11-04T02:18 CLOSED COMPLETED by aiongg … fu=['1294']" / "closed 2026-11-09T13:29 autocraft-bot {'number': 2521, 'merged': True"; "Is #2283 … CLOSED COMPLETED … closed 2026-11-12T15:53 autocraft-bot {'number': 2701, 'merged': True"; "Is #2281 2026-11-03T23:36 CLOSED COMPLETED … closed 2026-11-03T23:57 aiongg {'number': 2285, 'merged': True"; "#2288 … OPEN … xref {'number': 2337, 'state': 'OPEN'"; "#2280 … xref {'number': 2297, 'state': 'OPEN'"; "#2284 … xref {'number': 2295, 'state': 'OPEN'". "## kc_bot: 3" (all Fix PRs). originals: "#1302 -> issue #2288: merged 2026-11-04T01:55:12Z by aiongg … ['_AI-generated review (Opus). Not a maintainer decision._ No blocking problems found.']", same for #1424 (21:15:00Z), #1968 (21:48:53Z), #1294 (02:17:16Z), #2168 (23:33:37Z), #1222 (19:07:38Z).

### L3-M9

`python fu2.py`: "## org_ai_review_issue: 6" (the six designcraft issues); "## org_ai_issue: 4" (all user-written, none AutoCraft); "## kc_fu_any: 14" (none carries the AutoCraft note).

### L3-M10

`python fixmain.py` (merged Nov 1–18, title terms): "photocraft mainred=1 maingreen=4 mainci=3 fixmain=6 revert=1 unbreak=0" (the revert hit is #11850 "Escape … reverts what was typed", not a revert); listed titles include "(13023, 'Pen Enter tests: … (main red since #12993)'", "(15474, \"Fix main's CI: gate, scorecard, Windows test build, web build\"" and 9 more; "wordcraft mainred=2 maingreen=0 mainci=2 fixmain=3" (4 distinct); "designcraft mainred=1 …" ("2797 … (main's FreeBSD nightly is red)"); "deckcraft … all 0"; "filmcraft … all 0". At most 5 titles per term are listed, so photocraft is a floor.

### L3-M11

`python names.py wA_*.json`: "('gate / gate (ubuntu-24.04)', 'push')" present in designcraft (25), deckcraft (32), wordcraft (113), filmcraft; photocraft's failing list adds "test (windows-latest, integration)", "web build and wasm size gate".

### L3-M12

`python pcoct.py` (8 photocraft PRs created Oct 13–19 matching the note): every row "OPEN False <author>  []" (note not in body, first 40 comments or 20 reviews).

<!-- ledger Q4 -->
### L4-M1

`s2_counts.py`: one GraphQL query, `search(type: ISSUE, query: ..., first: 0){issueCount}`. "Not a maintainer decision" in PRs: photocraft 89, designcraft 559, wordcraft 4; open PRs: photocraft 1789, designcraft 433, wordcraft 1441. (Its `closed:` weekly counts are superseded by M4, see C401.)

### L4-M2

`s6_more.py`: `is:open updated:<2026-11-04` photocraft 130, designcraft 61, wordcraft 519, jarvis 0; designcraft closed-unmerged with AutoCraft note 20; first designcraft note `sort:created-asc` → #65 2026-10-07T02:27:45Z; photocraft `closed:<2026-10-06` unmerged 0, `merged:<2026-10-06` 154. `"Close this PR"` search hits (photocraft 130, org 989) discarded: sampled hits did not contain the phrase as an AutoCraft post (loose word matching).

### L4-M3

`s7_check.py`, `s8_disc.py`: photocraft unmerged all 1020, `closed:2026-10-06..2026-11-18` 295, merged all 4548; `created:2026-10-13` unmerged 55 vs `+closed:2026-10-01..2026-11-19` 25; closedAt histogram of the 55: 10-13 22, 10-14 13, 11-05 7, ... all in Oct–Nov. wordcraft 559 vs 121; designcraft 152 vs 26; jarvis 77 vs 75.

### L4-M4

`s9_cohort.py`, `created:<week>` × `is:merged` / `is:closed is:unmerged` / `is:open`, weeks Mon–Sun 2026-10-06..11-16. Output `s9_out.txt`, e.g. "pc W1 created 2026-10-06..2026-10-12: merged=1798 closed_unmerged=449 open=118 total=2365", "pc ALL W1-W6: merged=4372 closed_unmerged=1007 open=1658 unmerged/closed=18.7% dependabot_unmerged=31", "dc ALL W1-W6: merged=1153 closed_unmerged=152 open=412 unmerged/closed=11.6%", "wc ALL W1-W6: merged=1843 closed_unmerged=559 open=1389 unmerged/closed=23.3%", "jv ALL ... merged=111 closed_unmerged=17 open=5", "mim ... merged=24 closed_unmerged=4 open=2", "rr ... merged=496 closed_unmerged=10 open=11".

### L4-M5

`s3_sample.py`: GraphQL search, best-match order, first N of closed-unmerged by `closed:` window (subset that search indexes, see C401): photocraft Oct 6–12 20 of 105, Nov 10–18 25 of 31; designcraft Oct 6–Nov 18 26 of 26; wordcraft Nov 3–18 27 of 27, Oct 6–12 15 of 28. Fields: closer, last 3 comments, linked issues' other PRs, size. Rendered `s4_view.txt`; full maintainer comments `s5_out.json`.

### L4-M6

`s10_tally.py` over manual classes from the closing comments: "ALL non-dependabot n=94: D=40 (43%, 7379 lines), X=22 (23%, 9591 lines), H=9 (10%), F=6 (6%), L=6 (6%), R=5 (5%), N=3 (3%), O=2 (2%), I=1 (1%)"; "pc_early ... D_share_of_non_dep=60% ... self_closed_by_author=15/20 D_lines=2179"; "pc_late ... B=9 D=4 F=2 H=1 O=2 R=4 X=3 ... 25% ... 16/16"; "dc_all ... 35% ... 16/23"; "wc_late ... B=7 D=4 F=1 I=1 L=5 X=9 ... 20% ... 15/20"; "wc_early ... 80% median 12 zero_diff=4 ... 7/15". One classifier, no second rater.

### L4-M7

`s6_more.py`: first 40 merged PRs by search order, additions+deletions median: photocraft (merged Nov 10–16) 132, wordcraft (Nov 3–16) 32, designcraft (Oct 6–Nov 16) 57.

### L4-M8

`s1_rfc.py`: commits on rfcs/0003-claiming-issues.md → `a915429a 2026-11-12T20:12:39Z "RFC-0003: Claiming issues (#4)"`; house-rules-core.md commits c6a8b147 / 48ae9e42 2026-11-06; `s13_house.py` (ref 48ae9e42) shows rule 2 "Check, then claim." and rule 6. `s6_more.py`: photocraft #3576 OPEN, #2847 CLOSED 2026-11-08 unmerged.

### L4-M9

`s11_dupkw.py`: `is:closed is:unmerged created:<week> duplicate in:comments`: pc 53/43/24/9/10/10, dc 7/2/6/1/1/3, wc 9/29/19/17/16/3. Keyword match is loose and misses "superseded", "in favour of".

### L4-M10

`s12_ours.py`: closed-unmerged created 2026-10-06..11-16, titles and last comment: jarvis 7 dependabot, #2147–#2149 "Seeded-defect PR for #2131", #1993–#1996, #2020, #2025 canaries, #2214 "superseded by #2218"; music-intel-mcp #247–#250 "Canary for #244, done."


## Open questions

- Q1 — who issued the 18 releases: transcripts on the other two devices, or the user's own account of each, would settle it; GitHub's record cannot ([C118]).
- Q1 — whether any HIGH PR was merged by an agent with no hold besides #2218; a per-PR check of the other three unheld PRs (#2164, #2215, #2234) against transcripts would settle it.
- Q2 — whether like-current-song's fixes after lcs#250 should also reach music-intel-mcp; a diff of the two copies would settle it.
- Q2 — whether #2179's write denial ever hit music-intel-mcp before 2026-11-15; a step check of older review runs would settle it.
- Q2 — whether jarvis #2055's fix matters for music-intel-mcp; its commit was not read in this run.
- Q3 — whether the on-group's lower closed-unmerged share survives a count by creation cohort; the Nov 1–18 shares use the `closed:` search qualifier, which misses most closes in these repos.
- Q3 — how lightcraft and craft-anything, two more apps without AutoCraft reviews, compare on main health and speed; they were left out of those tables.
- Q3 — how many post-merge Opus reviews ran and found nothing; the AutoCraft dashboard holds it, and it is not public.
- Q3 — whether designcraft and deckcraft were healthier before AutoCraft; it ran within a week of their creation, so no baseline exists.
- Q4 — what AutoCraft's "Close this PR?" answers were; search did not find them.
- Q4 — whether claiming reduced duplicates; the November cohorts are still open and need a re-count in a few weeks.

## Sources

- [S1] https://github.com/Osasuwu/jarvis/blob/14a29594/.github/scripts/waiting_human_review.py — passage
- [S2] https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches — passage
- [S3] https://github.com/Osasuwu/jarvis/blob/14a29594/AGENTS.md — passage
- [S4] https://github.com/Osasuwu/jarvis/blob/14a29594/.github/scripts/risk_tier.md — passage
- [S5] https://github.com/Osasuwu/jarvis/blob/14a29594/docs/decisions/2026-Q4.md — passage
- [S6] https://github.com/Osasuwu/jarvis/blob/14a29594/CONTEXT.md — passage
- [S7] https://github.com/Osasuwu/jarvis-private/blob/eaa990c/skills/implement/SKILL.md — passage
- [S8] https://github.com/Osasuwu/jarvis-private/blob/eaa990c/skills/orchestrate/SKILL.md — passage
- [S9] https://github.com/Osasuwu/jarvis-private/blob/eaa990c/skills/orchestrate/WORKER-RULES.md — passage
- [S10] https://github.com/Osasuwu/jarvis-private/blob/eaa990c/hooks/merge-push-guard.py — passage
- [S11] https://github.com/Osasuwu/music-intel-mcp/commit/72d215e — passage
- [S12] https://github.com/Osasuwu/music-intel-mcp/commit/55edd84 — passage
- [S13] https://github.com/Osasuwu/jarvis/issues/2076 — passage
- [S14] https://github.com/Osasuwu/music-intel-mcp/blob/0b85f02ab557be37232aaf8ba64591334a8db83c/.github/scripts/code_gate_verdict.py — passage
- [S15] https://github.com/Osasuwu/jarvis/issues/2079 — passage
- [S16] https://github.com/Osasuwu/music-intel-mcp/blob/0b85f02ab557be37232aaf8ba64591334a8db83c/.github/workflows/code-review.yml — passage
- [S17] https://github.com/Osasuwu/jarvis/issues/2081 — passage
- [S18] https://github.com/Osasuwu/jarvis/issues/2085 — passage
- [S19] https://github.com/Osasuwu/jarvis/issues/2068 — passage
- [S20] https://github.com/Osasuwu/jarvis/commit/17df8ff163daa8fd4da2838740e239e126d9907a — passage
- [S21] https://github.com/Osasuwu/jarvis/commit/5a4acebad41ccc3c1e2a9899a003cc4812db6376 — passage
- [S22] https://github.com/Osasuwu/jarvis/issues/2044 — passage
- [S23] https://github.com/Osasuwu/jarvis/issues/2179 — passage
- [S24] https://github.com/Osasuwu/jarvis/commit/102fa7f2cc99962db99205cecab12e00a64c1bd8 — passage
- [S25] https://github.com/Osasuwu/jarvis/commit/ead8c6bfef0bab9adcb0ace11f027e085bb176ea — passage
- [S26] https://github.com/Osasuwu/jarvis/commit/b6fb73984804de7e8a81660b602b441d0bb21300 — passage
- [S27] https://github.com/Osasuwu/music-intel-mcp/issues/283 — passage
- [S28] https://github.com/Osasuwu/jarvis/issues/2205 — passage
- [S29] https://raw.githubusercontent.com/storytold/autocraft/main/docs/pipeline.md — passage
- [S30] https://github.com/storytold/designcraft/issues/2290 — passage
- [S31] https://github.com/Osasuwu/jarvis/issues/2233 — passage
- [S32] https://github.com/storytold/wordcraft/pull/4059 — passage
- [S33] https://github.com/storytold/designcraft/pull/971 — passage
- [S34] https://github.com/storytold/photocraft/pull/3911 — passage
- [S35] https://github.com/storytold/designcraft/pull/50 — passage
- [S36] https://github.com/storytold/photocraft/pull/12870 — passage
- [S37] https://github.com/storytold/photocraft/pull/13008 — passage
- [S38] https://github.com/storytold/wordcraft/pull/5032 — passage
- [S39] https://github.com/storytold/photocraft/issues/3561 — passage
- [S40] https://raw.githubusercontent.com/storytold/craft-contrib/HEAD/rfcs/0003-claiming-issues.md — passage
- [S41] https://raw.githubusercontent.com/storytold/craft-contrib/HEAD/standards/house-rules-core.md — passage
- [S42] https://github.com/storytold/photocraft/pull/14873 — passage
- [S43] https://github.com/storytold/photocraft/issues/15476 — passage
- [S44] https://arxiv.org/html/2602.04226v1 — passage

## Audit

| Claim | Verdict | Note |
|---|---|---|
| C101 | SUPPORTED |  |
| C102 | SUPPORTED |  |
| C103 | PARTIAL | quote names the AFK worker's machine user; "not against an agent using the admin's token" is not in it, dropped |
| C104 | SUPPORTED |  |
| C105 | SUPPORTED |  |
| C106 | SUPPORTED |  |
| C107 | SUPPORTED |  |
| C108 | SUPPORTED |  |
| C109 | SUPPORTED |  |
| C110 | SUPPORTED |  |
| C111 | SUPPORTED |  |
| C112 | SUPPORTED |  |
| C113 | PARTIAL | the log line was read on #2121 and #2187 only; rewritten to say so |
| C114 | SUPPORTED |  |
| C115 | SUPPORTED |  |
| C116 | SUPPORTED | raw holds_rows.json: #2215 ready_for_review 11-15T19:08:31Z |
| C117 | SUPPORTED |  |
| C118 | SUPPORTED |  |
| C119 | SUPPORTED |  |
| C120 | PARTIAL | M5/M6 record only `--disable-auto` on #2137/#2138; hold-placing commands are not in the recorded output, dropped |
| C121 | PARTIAL | M6 shows a `gh pr view` reading labels, not that they were empty; rewritten |
| C122 | SUPPORTED |  |
| C123 | SUPPORTED |  |
| C124 | PARTIAL | "written after the user said in chat" is not in M11, dropped |
| C125 | SUPPORTED |  |
| C126 | PARTIAL | "looks like a live demo" is not measured, dropped |
| C127 | PARTIAL | dates 10-01/10-08 are not in M5, dropped |
| C128 | SUPPORTED |  |
| C129 | SUPPORTED |  |
| C130 | SUPPORTED |  |
| C131 | SUPPORTED |  |
| C132 | SUPPORTED |  |
| C133 | SUPPORTED |  |
| C134 | SUPPORTED |  |
| C135 | PARTIAL | "agents placed holds" rests on C120/C122, neither cited; dropped |
| C201 | SUPPORTED |  |
| C202 | PARTIAL | commit message says only "Port of like-current-song#250"; port-point reasoning dropped |
| C203 | SUPPORTED |  |
| C204 | SUPPORTED |  |
| C205 | SUPPORTED |  |
| C206 | SUPPORTED |  |
| C207 | SUPPORTED |  |
| C208 | SUPPORTED |  |
| C209 | SUPPORTED |  |
| C210 | SUPPORTED |  |
| C211 | SUPPORTED | quote check NOT FOUND: present in S16 code-review.yml, split across two YAML comment lines; kept |
| C212 | SUPPORTED |  |
| C213 | SUPPORTED |  |
| C214 | SUPPORTED |  |
| C215 | PARTIAL | S19 says code_gate_verdict was the only script retrying 502/503/504 and #2068 unified the policy; rewritten |
| C216 | SUPPORTED | fail-closed path in S14 lines 1143–1152 |
| C217 | SUPPORTED |  |
| C218 | SUPPORTED |  |
| C219 | SUPPORTED |  |
| C220 | SUPPORTED |  |
| C221 | SUPPORTED |  |
| C222 | SUPPORTED |  |
| C223 | SUPPORTED |  |
| C224 | PARTIAL | M5 read failed steps for 2 of the 3 failed runs; rewritten |
| C225 | SUPPORTED |  |
| C226 | SUPPORTED |  |
| C227 | PARTIAL | S25 is #2082 only and also refuses PR-author labelling; #2055 has no source; rewritten |
| C228 | PARTIAL | "conditions behind #1999, #2055, #2082 absent" overreaches (#2055 unsourced; #2082 also covers author labelling); dropped |
| C229 | SUPPORTED |  |
| C230 | SUPPORTED |  |
| C231 | SUPPORTED |  |
| C232 | SUPPORTED |  |
| C233 | SUPPORTED |  |
| C234 | SUPPORTED |  |
| C235 | SUPPORTED |  |
| C236 | SUPPORTED |  |
| C237 | SUPPORTED |  |
| C238 | PARTIAL | narrowed to #1999 and the bot half of #2082, per C227/C228 |
| C239 | SUPPORTED |  |
| C240 | SUPPORTED |  |
| C301 | SUPPORTED |  |
| C302 | SUPPORTED |  |
| C303 | SUPPORTED |  |
| C304 | SUPPORTED |  |
| C305 | PARTIAL | M3 weekly shares are 4–33% in October and 66–80% from Nov 3, not 20–30% / ~80% |
| C306 | PARTIAL | M11 shows the gate name and photocraft's failing list; SonarCloud on all five is not shown; rewritten |
| C307 | SUPPORTED |  |
| C308 | SUPPORTED |  |
| C309 | PARTIAL | M1 gives 3.7–15x disk and 2.5–5.3x merges, not 4–15x / 3.5–5x |
| C310 | SUPPORTED |  |
| C311 | SUPPORTED |  |
| C312 | SUPPORTED | re-ran analyze.py on wA_/wB_ files |
| C313 | SUPPORTED |  |
| C314 | SUPPORTED |  |
| C315 | SUPPORTED |  |
| C316 | SUPPORTED |  |
| C317 | SUPPORTED |  |
| C318 | SUPPORTED |  |
| C319 | SUPPORTED |  |
| C320 | PARTIAL | counts use the `closed:` qualifier that C401 shows undercounting; caveat added |
| C321 | SUPPORTED |  |
| C322 | SUPPORTED |  |
| C323 | SUPPORTED |  |
| C324 | PARTIAL | rests on C320's undercounting filter; caveat added |
| C325 | SUPPORTED |  |
| C326 | SUPPORTED |  |
| C327 | SUPPORTED |  |
| C328 | SUPPORTED |  |
| C329 | SUPPORTED |  |
| C330 | SUPPORTED |  |
| C331 | SUPPORTED |  |
| C332 | SUPPORTED |  |
| C333 | SUPPORTED |  |
| C334 | SUPPORTED |  |
| C335 | PARTIAL | "follows its size, volume" is causal; rewritten to "differs in" |
| C336 | PARTIAL | rollout figures corrected to M3's weekly shares |
| C401 | SUPPORTED |  |
| C402 | SUPPORTED | 4,352 = sum of weekly merged counts in s2_out.json |
| C403 | SUPPORTED |  |
| C404 | SUPPORTED |  |
| C405 | SUPPORTED |  |
| C406 | SUPPORTED |  |
| C407 | SUPPORTED |  |
| C408 | SUPPORTED |  |
| C409 | PARTIAL | photocraft W5 12.4%, W6 16.6%; rewritten |
| C410 | SUPPORTED |  |
| C411 | PARTIAL | S32 shows one re-land, not a general maintainer practice; narrowed to wordcraft#4059 |
| C412 | SUPPORTED | quote check NOT FOUND: present in the PR's last comment (2026-10-15), read via the issues API; the static page fetch lacks it; kept |
| C413 | SUPPORTED |  |
| C414 | SUPPORTED |  |
| C415 | SUPPORTED | no "autocraft" closer in s3/s4/s5 outputs |
| C416 | SUPPORTED |  |
| C417 | SUPPORTED | s3_out.json: all 16 dependabot PRs closed by dependabot ("no longer needed") |
| C418 | PARTIAL | "Typical" not shown by one thread; dropped |
| C419 | SUPPORTED |  |
| C420 | PARTIAL | S36 shows one PR asked to drop unrelated work; the generalisation and "branches carried each other's commits" dropped; quote check NOT FOUND: both pieces are in davidmann4's 2026-11-10 comment (read via the API, the check's page fetch lacks it); kept |
| C421 | SUPPORTED |  |
| C422 | SUPPORTED |  |
| C423 | UNCHECKABLE | [prior] from an earlier run; source not fetched in this run |
| C424 | SUPPORTED |  |
| C425 | SUPPORTED |  |
| C426 | SUPPORTED |  |
| C427 | SUPPORTED |  |
| C428 | SUPPORTED |  |
| C429 | SUPPORTED |  |
| C430 | SUPPORTED |  |
| C431 | SUPPORTED |  |
| C432 | PARTIAL | S43 is one epic; "epics now carry a stricter protocol" narrowed to #15476 |
| C433 | SUPPORTED |  |
| C434 | SUPPORTED |  |
| C435 | PARTIAL | duplicates are 43% of sampled closes (12–20% by keyword), the largest reason, not "mostly"; rewritten |
| C436 | SUPPORTED |  |
| C437 | SUPPORTED | quote is Table 1 cells; present |
| C438 | PARTIAL | 67.9% is over the study's rejected sample incl. human PRs and is larger than our 23%, not "as in" it; rewritten |
| C439 | PARTIAL | 76–81% lies between the mid-range agents (71–75%) and the human 82.6%, not at the baseline; rewritten |

Label verdict: open — Q1 cannot say who issued the 18 releases (two devices unexamined, GitHub's record cannot tell), which could change recommendation 1; Q2–Q4 each carry open sub-questions.

Quote check: Quote check high-holds-port-drift-autocraft-effect-agent-waste-2026-11-19.md: 56 quoted claim(s): 49 found, 3 NOT FOUND, 4 unfetchable, 0 no source

## Disposition

| Recommendation | State | Where |
|---|---|---|
| Say plainly that jarvis's HIGH hold is a convention, and decide at the /grill whether to make it enforced | deferred | unfiled: an input to the /grill planned for 2026-11-20, which decides between convention and an enforced control; the CONTEXT.md wording follows that decision |
| Re-port the missed code-gate fixes to music-intel-mcp once; drop the source-stamp check | deferred | unfiled: proposed in the final message as a music-intel-mcp issue (#2179 grant first, then #2081 and #2085); the stamp check is dropped for want of an incident |
| Judge #2233's Opus review experiment finding by finding, not by main-health outcomes | deferred | Osasuwu/jarvis#2233 |
| If we run parallel agent sessions for throughput, claim the issue and check open PRs before writing code | deferred | unfiled: applies only if the /grill adopts parallel sessions for throughput; an input to it |
| Correct the earlier "~6% closed unmerged" figure for photocraft | landed | a correction comment on Osasuwu/jarvis#2235, the PR carrying that figure; its report file stays as audited |
