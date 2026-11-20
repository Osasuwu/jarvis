---
topic: storytold-contribution-scale-rules-sync-autocraft
tags: area:process, research
source_provenance: /research invocation in session b065a837 — fourth run, the first of two covering the next runs proposed in docs/research/storytold-project-side-2026-11-18.md (PR #2235)
status: open
audit: 2026-11-19 — 192 claims: 154 SUPPORTED, 37 PARTIAL, 1 UNSUPPORTED, 0 UNCHECKABLE
---

## Question

The user, verbatim, quoting the earlier report's list of questions not yet asked, which ended with "Как 543 внешних автора узнают правила, и что это значит, если у redrobot появятся новые участники.":

"вот эти ещё не посмотрели. И теперь по новой инфе можно ещё попробовать вопросы задать, которые с их проектов получится узнать

Грилл чуть позже, пока инфу собираем, откладываем как вход на грилл"

The list has seven questions, and the user asks for new ones on top. A run takes at most four sub-questions, so they are split into two runs, done in parallel. This run takes the four about contribution, rules and process at scale. The companion run `storytold-oracles-cleanroom-supply-chain-main-health-2026-11-18` takes test oracles, clean-room and licensing, supply chain, and one new question: how healthy photocraft's main is under advisory CI. The /grill the user deferred is not part of either run; both feed it.

Sub-questions:
- Q1 — how storytold integrates hundreds of outside PRs in batches;
- Q2 — how ~543 outside authors learn the rules, and what that implies if redrobot gains collaborators;
- Q3 — how house rules are kept identical across ~20 repos, and whether our three repos need the same;
- Q4 — how AutoCraft is applied to its own repository, including whether its circuit breaker has run in practice.

## Summary

**Batch integration (Q1).** storytold's "integration batches" were a hand-run phase, not a standing process. An integrator builds one PR from a fork branch that carries many accepted contributor PRs unchanged, resolves conflicts and review findings in their own commits, tests the combined tree on fork CI with two agent reviews per PR and a revert check on each PR's tests, and lands it as a merge commit [C101], [C102], [C109], [C112], [C114], [C115], [C116]. PRs are taken out of a batch for regressions, unused code, divergence from the reference app or architecture [C118], [C119], [C120], [C121]; the five "reverts on main" the earlier report counted are such take-outs [C125]. On photocraft batching ran roughly Oct 19 to Nov 6 and then gave way to single merges [C127], [C129], [C131]; one maintainer closed a wordcraft batch because main moved too fast [C130]. Main was not kept green either way: lightcraft's main failed its own gates during its batching [C133], and under photocraft's later single merges a maintainer accepted known unrelated red CI [C136]; no RFC or house rule defines the process [C155]. AutoCraft's documented version adds bisection of a red batch, a hold while main is red, and single merges for small queues [C141], [C143], [C145]. redrobot, at about 100–143 merged PRs a week, sits where storytold also merges singly; what it gives up is the combined-tree test that catches cross-PR conflicts git does not flag, a gap its own 2026-11-18 decision records [C161], [C164], [C165], [C166].

**Onboarding (Q2).** storytold onboards by text and after-the-fact review, not by a door: one AGENTS.md for agents and people, house rules copied in from craft-contrib, claims by comment, CodeRabbit as the first responder, maintainer- or AutoCraft-approved CI for first-timers, human closes with reasons; no CLA, no welcome bot, no photocraft PR template [C201], [C203], [C207], [C215], [C224], [C233], [C234], [C243], [C246]. The rules that carry it: the human running an agent is accountable for what it opens, claim before coding, a response clock with closure only by a maintainer [C214], [C215], [C216]. The cost shows in 2,500 workflow runs waiting for approval [C236]. redrobot already has most of the text side, with machine-checked claims and a byte budget storytold only states [C249], [C251], [C252], [C253]; it lacks a response clock, an explicit accountability rule and per-author limits, and its onboarding doc trails AGENTS.md (four PR gates named where AGENTS.md has five) [C257], [C258]. The door mechanisms answer anonymous public volume; for invited collaborators the transferable part is rules in one file, claims and a response clock [C259].

**House-rules sync (Q3).** storytold copies shared rules into each AGENTS.md between markers carrying a source commit and sha256; a shared check fails a hand-edited copy and only warns about a stale one, and photocraft's caller runs it only when AGENTS.md, CLAUDE.md or the caller workflow changes [C301], [C302], [C306], [C307], [C321]. On 2026-11-18 all 20 copies passed integrity and all were stale, by 2–12 days and up to three rule changes [C324], [C325], [C338]; propagation is a human opening PRs [C327], and the tool itself deleted local text once [C330], [C331]. Their own open RFC says the drift that matters is in local paraphrases the check does not cover [C333]. Our three repos share rules through one user-level import, not copies [C339]. The drift we have is in restatements: issue-linkage bypass lanes worded differently in each repo, a dead path in music-intel-mcp, redrobot's CI section missing two checks [C340], [C341], [C344]. None of the incidents found would have been caught by a digest check [C351], and the check's cost at storytold was real [C352]. **Recommendation:** no sync check; fix the three drift items by hand.

**AutoCraft on its own repo (Q4).** The circuit breaker is real code — a push stage trips when 2 of its last 10 pushes turned a required check red, operator-only reset, state in a local SQLite table [C401], [C402], [C403], [C406] — added on 2026-11-04 [C409]. It counts only AutoCraft's own PR-branch pushes and merges [C405], and AutoCraft does not run on its own repository: main is pushed directly by one author, its 13 PRs are human and hand-merged, no AutoCraft review appears on those read [C422], [C423], [C424], [C425]. Its CI runs no tests; the repo's rules put verification on the author before pushing [C417], [C418]. Of 82 main commits with checks, 4 failed for real, all infrastructure (image build, registry login), none a test [C426], [C427], [C429]. No public evidence shows the breaker ever tripped, and none could: trips are recorded only in the operator's local table [C432], [C433]. So AutoCraft's own repo is no evidence for or against advisory CI with a breaker; that evidence would have to come from the craft repos it pushes to.

## Findings

### Q1 — How storytold integrates hundreds of outside PRs in batches — answered with a gap

- **C101** [quoted] A photocraft integration batch is one PR from an integrator's fork that carries many open contributor PRs on top of main; merging it merges all of them — "TL;DR: 37 reviewed community PRs on top of main, tested together in the app; merging this one PR merges all 37." — [S1], body, first line
- **C102** [quoted] The batch keeps contributor commits unchanged, so it must land as a merge commit or fast-forward; squash or rebase would leave the member PRs open — "Squash or rebase would rewrite the commits, and the 37 PRs would stay open." — [S1], body, second paragraph
- **C103** [measured] Batch 8 came from davidmann4's fork branch integration-batch-8 (372 commits, 217 files) and was merged by aiongg at 2026-10-26T00:04:41Z; its member PRs show merged at 00:04:43-44, merged_by aiongg — Own measurements, L1-M1
- **C104** [measured] PRs taken out of batch 8 by a revert on the batch branch (#4573, #1199, #9454) still show as merged at the batch's merge time, because their head commits stayed in the branch — Own measurements, L1-M1
- **C105** [quoted] One integrator assembled batch 8 and tested each of its PRs in the app — "@davidmann4 put this batch together and tested each PR in the app." — [S1], body
- **C106** [quoted] Selection in another batch: PRs a reviewer had approved, with green CI, taken at their current head — "85 open PRs approved by @FredApps on their current head, with green CI, each merged at its current head." — [S2], ## Contents › PRs approved by FredApps
- **C107** [quoted] On #1199, acceptance was a separate, earlier maintainer step on the contributor PR (2026-10-09, before batch 8) — "Maintainer decision: **accepted** as an off-by-default `local-ml` feature." — [S3], tanish2k09, 2026-10-09
- **C108** [measured] echelon, bflatastic, tanish2k09, benandez are public storytold members; davidmann4, aiongg, FredApps, Higgs32584 are not public members — Own measurements, L1-M2
- **C109** [quoted] On #1199 the integrator, not the contributor, resolved the conflict with main and the review findings, in a fix-up on the integrator's fork — "since the branch also conflicts with main again, we've put them in a fix-up on top of your commits" — [S4], davidmann4, 2026-10-25
- **C110** [quoted] Contributor commits and authorship stay; the fix-up co-credits the author and goes up with the next batch — "Your commits stay exactly as they are, with you as the author, and the fix-up credits you as co-author. It goes to the maintainers with our next reviewed batch" — [S4], same comment
- **C111** [quoted] The stated reason for fixing instead of requesting changes is turnaround — "a fix that's already clear is quicker to apply than to describe, and it saves everyone days of back and forth." — [S4], same comment
- **C112** [quoted] Conflicts are resolved in merge commits, documented per PR, including semantic conflicts git did not flag — "#3567: not flagged by git: the merge renamed the History panel's `doc` to `doc_id`" — [S1], ## Conflicts resolved in merge commits
- **C114** [quoted] The combined tree is tested on fork CI, plus a local gate — "Fork CI at the head `ccff1361b`: https://github.com/davidmann4/photocraft/actions/runs/40241330338, all green." — [S1], ## Testing
- **C115** [quoted] Each PR gets two independent agent reviews — "Review: two independent agents per PR (a reviewer and an attacker), every claim checked against code, spec or a run, and each included diff read in full." — [S1], ## Testing
- **C116** [quoted] Tests are mutation-checked on the stack: each PR's code is reverted and its tests must fail — "each PR's code reverted on the branch, its named tests fail" — [S1], ## Testing
- **C118** [quoted] A PR was taken out of batch 8 for a measured performance regression — "same pixels, but the default AHD demosaic gets slower on a multi-core machine." — [S1], table row #9455
- **C119** [quoted] A PR was taken out because nothing used its code yet; it should land with its caller — "nothing calls `develop_half` yet" — [S1], table row #9454
- **C120** [quoted] PRs were taken out for diverging from the reference application — "the reference application doesn't support .cube files with a 1D shaper and a 3D table." — [S1], table row #9183
- **C121** [quoted] A PR was taken out for architecture: a shared AI layer created after its acceptance — "we've taken this PR out of integration batch 8, because local models in PhotoCraft should most likely go through the shared" — [S5], davidmann4, 2026-10-25 14:25
- **C122** [quoted] In batch #8355, two PRs were left out because they conflicted with a refactor landing next; they were to follow rebased onto it — "#8035 and #6492: they conflict with the CLI refactor #8300, which lands next; they follow rebased onto it." — [S2], ## Not included
- **C123** [quoted] designcraft's integrator published, per skipped PR, why it was not batched; security risk is one reason — "A hostile .xlsx can make formula evaluation take exponential time, and URLs in data cells are fetched from the network" — [S6], table, row #109/#125
- **C124** [quoted] Skipped PRs are either rejected or left for maintainers to decide — "These 21 PRs were skipped, or left for the maintainers to decide, when the batches were built." — [S6], ## Still open from the original list
- **C125** [inference] The 2026-10-25 burst of five reverts on photocraft main (#1199, #9454, #4573, #9455, #9183) are batch-8 take-outs: reverted on the batch branch, landed on main by the batch merge — from [C104], [C118], [C119], [C120], [C121]
- **C126** [measured] "integration batch" appears in 847 storytold issues/PRs; batch PRs exist in at least 10 repos (photocraft, lightcraft, designcraft, pdfcraft, effectcraft, deckcraft, soundcraft, wordcraft, figcraft, artcraft-services), one of them a 218-PR batch (pdfcraft#3983) — Own measurements, L1-M3
- **C127** [measured] photocraft same-second merges by week from 2026-09-28: 0%, 0%, 3%, 64%, 76%, 25%, 1%; the counts sum to 900, matching the earlier run's 900; top merger moved from echelon (Oct 5-18) to aiongg (Oct 19-Nov 1) to davidmann4 (Nov 2-15) — Own measurements, L1-M4
- **C128** [inference] The same-second merges fit integration-batch landings, and same-second counting undercounts a batch, since batch 8 and its members landed over about 3 seconds; that all 900 are batch landings is not shown — from [C103], [C127]
- **C129** [measured] photocraft week of Nov 9-15: 547 merged, only 5 sharing a second; davidmann4 merged 334, FredApps 71, tanish2k09 71 — Own measurements, L1-M4, L1-M5
- **C130** [quoted] A storytold member closed a wordcraft batch because main moved too fast and each PR needed its own review and CI anyway — "Main moves too fast for a batch to stay mergeable, and each PR in it needs its own review and CI at its current head anyway, so batching only adds a step." — [S7], benandez, 2026-11-03
- **C131** [inference] photocraft hand-run batching ran about Oct 19 to Nov 6, then gave way to single merges; the one written reason found is for wordcraft — from [C127], [C129], [C130]
- **C133** [quoted] During lightcraft's batching (batch 33, 2026-10-13), lightcraft's main failed its own gates, and the batch was used to fix it — "`main` did not pass its own gates: clippy 1.99 failed in `spots.rs` and `lock.rs`, and tests failed on Windows and macOS (#989)." — [S8], body, batch 33
- **C136** [quoted] Under single merges, a maintainer accepted known unrelated red CI — "with the maintainer accepting the known unrelated CI failures" — [S9], skylartaylor, 2026-11-12 20:57
- **C137** [quoted] AutoCraft starts a batch as soon as PRs may merge, up to the repo's batch size (1-50, start 20) and ~10,000 changed lines; an L-size PR goes alone — "A batch starts whenever a repo has PRs that may merge and no batch in flight there; nothing waits for more PRs." — [S10], ## Merge queue › Integration batches
- **C138** [quoted] A PR that conflicts with the batch waits for the next one — "A PR that conflicts with the batch so far waits for the next batch." — [S10], Integration batches
- **C139** [quoted] The batch branch is built with merge commits in a bare clone; contributor commits stay — "Contributor commits stay, so GitHub marks each PR merged when the batch lands." — [S10], Integration batches, step 1
- **C140** [quoted] Upstream CI on the batch PR is the only test of the combined tree — "Upstream CI runs on it and is the only check of the combined tree." — [S10], Integration batches, step 2
- **C141** [quoted] A red batch is bisected and the batch size halves; a green one grows it by one — "If upstream CI fails, the batch is split in half and each half is retried, and the repo's batch size halves (minimum 1)." — [S10], Integration batches
- **C143** [quoted] While main is red, no merge or new batch starts — "no single merge runs and no new batch starts, because their CI would fail against the broken main." — [S10], Main CI red
- **C145** [quoted] With at most N mergeable PRs (the single-merge limit, default 3) and no shared file, AutoCraft merges one at a time without a batch — "the merge step merges them one at a time, and starts no batch." — [S10], Single merges
- **C146** [quoted] Merge without a human needs: verdict take, size S/M, bugfix or infra, whitelisted author, green CI, Verify passed, mergeable, no owner-statement conflict — "author is on the whitelist (see Contributors)" — [S10], Merge without asking
- **C149** [quoted] An operator can pull a PR from a batch — "**Remove from batch** (`autocraft batch-remove <repo#n>`): holds the PR and ends its batch." — [S10], Queue controls
- **C150** [quoted] A maintainer's changes-requested review drops a member and rebuilds the batch — "A blocked member is dropped and the batch is rebuilt without it." — [S10], Changes requested › Batches
- **C152** [quoted] safe-merge refuses unless every check is green and pins the merge to the head — "it refuses unless the PR is open, not a draft, mergeable and every check and Actions run for the head finished green, and it merges pinned to that head." — [S10], Merge step
- **C153** [quoted] AutoCraft-style batches ran on designcraft from aiongg's fork with the documented branch naming — "_Automated message. Not a maintainer decision._" — [S11], body; head aiongg/designcraft:integration-designcraft-20261104-1
- **C154** [inference] aiongg's account runs AutoCraft's merge stage on designcraft; photocraft's November merges are not AutoCraft batches. Confidence low: based on branch naming and the measured drop only — from [C127], [C129], [C139], [C153]
- **C155** [measured] No storytold RFC, house rule or AGENTS.md defines the batch process: code search for "integration batch" hits only AutoCraft and per-app parity docs — Own measurements, L1-M6
- **C156** [quoted] redrobot agents merge LOW/MEDIUM PRs themselves when review verdict and every check are green — "An agent merges a PR itself when its `Risk:` line says LOW or MEDIUM, `code-review/verdict` is green for the head SHA and every check is green." — [S12], ## Merge denylist (via GitHub API)
- **C157** [quoted] Nothing enforces it in redrobot — "PR workflows report but do not block; merging is a manual, disciplined step, not a gated one." — [S12], ## CI/CD & Merging
- **C158** [quoted] redrobot squash-merges each PR alone — "gh pr merge <N> --squash --delete-branch" — [S12], ## CI/CD & Merging
- **C159** [quoted] Since 2026-11-18 a PR behind master rebases only on file overlap with master — "a PR behind master rebases, and CI finishes on the rebased branch before merging, only if master changed a file the PR touches since its base." — [S12], ## Rebase Before Merge
- **C160** [quoted] The rule was adopted for queue throughput; GitHub merge queue was rejected as unavailable on Free — "Merge queue GitHub — отказ: недоступна в приватном репо на плане Free." — [S13], ## Альтернативы
- **C161** [quoted] The decision records that file overlap misses semantic conflicts between different files — "пересечение по файлам не ловит конфликт по смыслу между разными файлами" — [S13], ## Возражения
- **C162** [quoted] "Red is not merged, main always green" is status proposed — "С красными чеками не мержим, а чиним: main всегда зелёный, одинаково во всех репозиториях." — [S14], ## Ответ; front matter status: proposed
- **C163** [quoted] A critic finding left open: most master failures were runner infrastructure, 3 integration after a green PR — "из 35 падений на master 20 — инфраструктура раннера, 3 — интеграция после зелёного PR" — [S14], Критики, row 1
- **C164** [measured] redrobot merged 105, 22, 115, 134 PRs in the weeks from Oct 19 to Nov 9, and 143 for Nov 12-18, none sharing a second, by two logins; the ~151/week figure was not reproduced in these windows — Own measurements, L1-M7
- **C165** [inference] storytold's batch tests the combined tree once and catches cross-PR breakage git does not flag; redrobot tests each PR alone and accepts the semantic-conflict gap outside strict paths — from [C112], [C140], [C159], [C161]
- **C166** [inference] Batching did not keep lightcraft's main green. Hand batches were dropped where main moved fast. AutoCraft's engineered version adds bisection and a red-main hold, and still merges small queues one by one. At ~100-143 PRs a week, redrobot is where storytold also merges singly — from [C127], [C129], [C130], [C133], [C141], [C143], [C145], [C164]
### Q2 — How ~543 outside authors learn the rules, and what it implies for redrobot collaborators — answered with a gap

- **C201** [measured] photocraft has no root CONTRIBUTING.md, no PR template, no issue templates and no CODEOWNERS; its contribution rules sit in AGENTS.md, docs/contributing.md and book/src/getting-started/contributing.md; storytold has no org `.github` repo, so no org-wide default community files — Own measurements, L2-M1
- **C202** [measured] craft-anything (newer, created 2026-10-31) has the classic set: root CONTRIBUTING.md, CLAUDE.md, a PR template and issue templates; autocraft has a CONTRIBUTING.md that is only a dev-setup guide — Own measurements, L2-M1
- **C203** [quoted] photocraft's AGENTS.md is addressed to agents and human contributors alike and is the first thing to read — "# AGENTS.md: guide for AI agents and contributors" — [S15], heading line 54
- **C204** [quoted] The book's contributing page sends people to AGENTS.md and docs/contributing.md before any edit — "before editing source" — [S16], top
- **C205** [quoted] craft-anything's CONTRIBUTING.md is a short pointer: one rule set for people and agents, kept in AGENTS.md — "The rules every change follows (people and AI agents alike) are in [AGENTS.md](AGENTS.md)" — [S17], intro
- **C206** [quoted] craft-anything's CLAUDE.md only imports AGENTS.md and the pitfalls doc, so the agent's session loads the same rules — "@AGENTS.md" — [S18], body
- **C207** [quoted] The shared house rules are copied into photocraft's AGENTS.md as a generated block stamped with the source commit and a digest — "<!-- craft-house-rules:start core source=dde09ea3" — [S15], line 1
- **C208** [quoted] RFC-0006 copies the rules instead of linking because agents may not follow links — "linking alone is not enough because agents may not follow links" — [S19], Source and validation
- **C209** [quoted] A CI check in craft-common-actions validates each copied block against the canonical text; an edited block fails — "An edited block or invalid source reference fails the integrity check. An intact older version only warns about freshness." — [S19], Source and validation
- **C210** [quoted] photocraft's house-rules workflow is a thin caller of the shared check, triggered by pushes to main and PRs that touch AGENTS.md, CLAUDE.md or the workflow, or by hand (paths: Own measurements, M1) — "uses: storytold/craft-common-actions/.github/workflows/house-rules.yml@main" — [S20], on.pull_request.paths
- **C211** [quoted] RFC-0006 was motivated by agent PR volume repeating the same mistakes — "much of the current PR volume comes from coding agents" — [S19], Motivation
- **C212** [quoted] RFC-0006 sets a byte budget for the shared block and the root file — "Budget 3 KB for the core block and a 10 KB soft limit for the root file, measured in bytes." — [S19], Updates
- **C213** [measured] photocraft's root AGENTS.md is 27,199 bytes, well past RFC-0006's 10 KB soft limit; craft-anything's is 12,275 — Own measurements, L2-M2
- **C214** [quoted] House rule 1: the human running an agent is accountable for what it opens — "**A person is accountable.** Whoever runs an agent answers for what it opens and for its review comments." — [S15], House rules 1
- **C215** [quoted] House rule 2: check for existing work and claim on the issue before coding — "**Check, then claim.** Before writing code, read the issue comments" — [S15], House rules 2
- **C216** [quoted] House rule 14: response clock on PRs, closure only by a maintainer, never automatic — "Respond in 7 days, a reminder at 14, closure eligible at 30" — [S15], House rules 14
- **C217** [quoted] House rule 15 forbids saying an agent wrote the PR — "**No agent attribution.** A pull request does not say an agent wrote it." — [S15], House rules 15
- **C218** [quoted] RFC-0003 (claiming) quantifies the duplicate-work problem that drove the rules — "counted **172 issues** with fixing PRs from two or more authors, and **148** of those PRs closed unmerged" — [S21], Motivation
- **C219** [quoted] Claims expire: a comment-only claim lasts 24 hours without visible progress — "**A comment-only, unstarted claim lasts 24 hours** without a visible sign of progress" — [S21], Proposal 5
- **C220** [quoted] RFC-0003 lists a /take assignment bot as an alternative, useful later and to be proposed separately once the rule is agreed — "**A bot that assigns on `/take` and drops stale assignments.** Useful later" — [S21], Alternatives
- **C221** [quoted] craft-anything replaces issue claims with a claim written into the roadmap line plus a draft PR — "Claim it first: add `— claimed: <your name>, branch <branch>` to its line and open a draft PR" — [S17], bullet 1
- **C222** [quoted] craft-anything's PR template makes the author state what was and was not verified — "**Not verified:** <!-- what you couldn't try, so the docs and STATUS say so -->" — [S22], body
- **C223** [quoted] In craft-anything, inbound licence is by a statement in CONTRIBUTING — "by contributing you agree your work is licensed the same way" — [S17], last paragraph
- **C224** [measured] No CLA or DCO path appears in the trees of photocraft, craft-anything or autocraft — Own measurements, L2-M1
- **C225** [quoted] craft-contrib invites anyone to take part, no role needed — "**Anyone can take part.** You do not need a special role, an invitation, or a merged pull request." — [S23], intro
- **C226** [quoted] Contributors credit themselves in a people.toml entry, in their own PR — "**Each contributor adds only their own entry**, in their own PR." — [S24], Decision
- **C229** [measured] craft-anything's AGENTS.md carries no generated house-rules block (0 markers vs 2 in photocraft), so the RFC-0006 copy is not in every app — Own measurements, L2-M2
- **C230** [measured] The shared workflow library craft-common-actions has no welcome, first-interaction, labeler or stale workflow among its 21, which include gate, house-rules, refresh-contributors, release, sonarcloud and supply-chain — Own measurements, L2-M9
- **C231** [measured] GitHub's author_association does not mark newcomers usefully here: in 400 recent photocraft PRs no PR carries FIRST_TIME_CONTRIBUTOR, and NONE (46 PRs) includes an author with 6 merged PRs — Own measurements, L2-M3
- **C232** [measured] In the 400-PR sample (11–18 Nov) 56 distinct authors appear; 20 have one PR; the top author has 45; 35 of 100 open PRs are by NONE-association authors — Own measurements, L2-M3
- **C233** [measured] On all 7 sampled outside-author PR threads the first comment is the CodeRabbit bot's (on #13509 within the minute the PR opened) — Own measurements, L2-M4, L2-M6
- **C234** [quoted] GitHub holds a first-time contributor's workflow runs until a maintainer approves them; contributors ask for it in the thread — "because this is my first PR here, so nothing has run on it yet. Could a maintainer approve them" — [S25], comment 2026-11-13T05:45:56Z
- **C235** [quoted] A newcomer counted 24 held runs on one PR with no maintainer reply a day later — "24 workflow runs across CI, Documentation, Packaging lint and SonarCloud, every one of them `action_required`, on all six commits" — [S26], comment 2026-11-18T01:35:05Z
- **C236** [measured] The photocraft Actions API reports a total_count of 2,500 runs in status action_required on 2026-11-18 — Own measurements, L2-M5
- **C237** [quoted] AutoCraft documents that held runs block merging and that it approves them itself once its review says take, when the operator enabled CI approval for the repo — "the check rollup does not list them, and `safe-merge` refuses such a head." — [S10], Runs waiting for approval
- **C238** [quoted] AutoCraft caps model work per outside author per day (5 PRs, 5 issues by default) — "only the first `outside_prs_per_day` PRs (default 5) and the first `outside_issues_per_day` issues (default 5) get model work" — [S10], Outside authors, Daily budget
- **C239** [quoted] AutoCraft's fixed-template posts are labelled as not a maintainer decision; model-written replies carry an "AI-generated reply" note instead — "`_Automated message. Not a maintainer decision._`" — [S10], GitHub writes, note line
- **C240** [quoted] AutoCraft close comments are fixed templates whose text an operator approves; a model never closes a PR alone — "the operator's answer approves that text" — [S10], Act, Comment rules
- **C241** [measured] GitHub search finds the AutoCraft note "Not a maintainer decision" on 89 photocraft PRs, 13 of them closed unmerged — Own measurements, L2-M5
- **C242** [quoted] A merged first PR: a team-side reviewer merged main into the newcomer's branch, pushed a fix and told the author nothing was left to do; open 12 Nov, merged 15 Nov — "TL;DR: this is ready on our side; nothing is left for you to do." — [S25], comment 2026-11-14T01:41:49Z
- **C243** [quoted] A human close of a newcomer PR: superseded by a merged PR, with thanks, the reason and an invitation to a fresh PR — "The same change has since landed on main (#5837), so I'm closing this as superseded." — [S27], comment 2026-11-05T04:14:45Z
- **C244** [quoted] An outside author closed their own PR because the code had moved to craft-libs — "Closing: #15449 moved this code to craft-libs, so this change no longer applies here." — [S28], comment 2026-11-17T18:08:05Z
- **C245** [measured] An out-of-scope PR from an author with one PR in the repo (Python/React AI panel in a Rust-only repo) sat open with only a CodeRabbit review: rules are not enforced at the door — Own measurements, L2-M4
- **C246** [inference] storytold onboards by text plus after-the-fact review: AGENTS.md rules from craft-contrib, comment claims, CodeRabbit first, held CI approved by a maintainer or AutoCraft, human-approved closes; no CLA, welcome bot, photocraft PR template or entry gate — from [C201], [C207], [C215], [C224], [C230], [C233], [C234], [C237], [C240], [C243]
- **C249** [measured] redrobot root has AGENTS.md, README, REVIEW.md, GLOSSARY.md but no CONTRIBUTING, CODEOWNERS, SECURITY.md or LICENSE; .github has issue templates (bug-report, task, hardware-test) and a PR template — Own measurements, L2-M8
- **C250** [quoted] redrobot's onboarding doc exists, for an invited collaborator; the invite and role are agreed verbally — "Приглашение в репо и роль обсуждаются на словах; этот документ" — [S30], intro
- **C251** [quoted] redrobot, like storytold, makes AGENTS.md the single rules carrier for agents and people — "`AGENTS.md` (корень) — единственный носитель правил и инструкций агенту" — [S30], intro
- **C252** [quoted] redrobot enforces a byte budget on AGENTS.md by script, which storytold only states (10 KB soft) — "**Budget: ≤ 15 000 bytes** for this file plus its `@`-imports" — [S12], top
- **C253** [quoted] redrobot claims are machine-checked: assignee only, via a script, with a guard workflow dropping later assignees — "**Agents claim (шаги 1–2) only via `python scripts/claim_issue.py <N>`**: exit 0 = yours" — [S12], AFK Agent Coordination
- **C254** [quoted] Agents act under their human's login; there are no bot accounts — "Агенты работают под GitHub-логином своего человека; отдельных bot-аккаунтов нет." — [S31], §1
- **C255** [quoted] redrobot's team-workflow plan releases no stale claim automatically; it reports them in a weekly metric — "Авто-снятия нет." — [S31], §5.4
- **C256** [quoted] redrobot's PR template has Closes, an optional Key Decisions section, a Retirement question that must be answered, and a Safety Review hint for driver/ and planning/ — "\"Nothing replaced\" is a legal, common answer — the question must be answered, not skipped." — [S32], Retirement
- **C257** [quoted] The onboarding doc lists four PR gates (CI, Code Review, PR Checks, Owner Queue Guard) where AGENTS.md names five (it adds Gitleaks), so it trails AGENTS.md — "`PR Checks` (связанный issue + safety), `Owner Queue Guard`." — [S30], §5 step 6
- **C258** [inference] redrobot has one rules file, an onboarding doc, templates, guarded assignee claims and a budget check; it lacks a PR response clock, an explicit accountability rule, per-author limits and separate agent identities — from [C214], [C216], [C238], [C249], [C250], [C252], [C253], [C254], [C255], [C256]
- **C259** [inference] Most storytold door mechanisms (held CI for forks, per-outsider budgets, surge breaker, no CLA) answer anonymous public volume; a private repo with invited collaborators needs few of them, but rules-in-one-file, claims and a response clock transfer — from [C234], [C238], [C246], [C250], [C254]
### Q3 — How house rules stay identical across ~20 repos, and whether our three repos need the same — answered with a gap

- **C301** [quoted] The shared house-rules workflow fails a caller unless its AGENTS.md holds the shared rules from craft-contrib unchanged, at a commit on craft-contrib main — "Fails unless AGENTS.md copies the shared rules from craft-contrib unchanged, at a commit that is" — [S33], header comment, line 3
- **C302** [quoted] Drift to an older but intact copy only warns, and only when the standards file changed on main since; it does not fail — "An intact older copy warns only when its normalized standards file changed on main, and does not fail." — [S33], header comment, line 4
- **C306** [quoted] Each shared block sits between HTML-comment markers recording the craft-contrib commit and the block's sha256 — "<!-- craft-house-rules:start ([a-z]+) source=([0-9a-f]{40}) sha256=([0-9a-f]{64}) -->" — [S34], START regex, line 26
- **C307** [quoted] The check compares three things: block bytes vs recorded sha256, and block bytes vs the standards file at the recorded commit on main; rewriting the digest to fit an edit does not pass — "A digest rewritten to suit an edit does not pass." — [S34], module docstring, lines 4-6
- **C309** [quoted] Failure classes: unknown block, sha256 mismatch, source commit not on main, block text differs from the standards file at that commit, required block missing, repeated block — "block does not match {path} at {block['source']}" — [S34], judge_block() and check_file(), lines 177-225
- **C310** [quoted] An intact copy behind main produces a GitHub Actions ::warning, not a failure — "is intact at {block['source']}, which is behind main" — [S34], judge_block(), line 198
- **C311** [quoted] The same script has a write mode that renders the blocks from craft-contrib main and replaces only the generated spans, keeping local AGENTS.md text verbatim — "Replace only generated spans; keep all surrounding local text verbatim." — [S34], apply_blocks() docstring, line 246
- **C313** [measured] The mechanism is 433 lines: workflow 57, composite action 35, Python checker 341 — Own measurements, L3-M1
- **C314** [quoted] The rule behind it: canonical text lives in craft-contrib standards files and is copied into each root AGENTS.md, because agents may not follow a link — "linking alone is not enough because agents may not follow links" — [S19], ### Source and validation, line ~78
- **C315** [quoted] RFC-0006 sets the failure semantics: edited block or invalid source fails integrity; an intact older version only warns about freshness — "An intact older version only warns about freshness." — [S19], ### Source and validation, lines ~89-92
- **C316** [quoted] Rule changes are proposed in craft-contrib, never by editing the copies — "propose changes here for maintainer review, rather than editing the copies" — [S19], ### Source and validation, lines 72-74
- **C317** [quoted] Propagation is meant to be bot-opened update PRs reviewed by maintainers, but a maintainer-run command is accepted and automation is not required — "A maintainer-run command is an acceptable starting point; automation is not a prerequisite for adopting this RFC." — [S19], ### Updates, lines 97-99
- **C318** [quoted] RFC-0006's rollout plan moves the remaining repos in small PRs that each list every removed rule and where it went — "Each PR lists every removed rule and where it went, so no guard disappears quietly." — [S19], ## Rollout, point 3
- **C320** [quoted] The craft-common-actions README restates the semantics: edited block or off-main commit fails; unchanged file gives no warning; unreadable source fails as "could not check" — "An edited block, or a commit that is not on `main`, fails." — [S35], ### 10. house-rules.yml, line ~777
- **C321** [quoted] photocraft's caller triggers the check only when AGENTS.md, CLAUDE.md or the caller workflow itself changes (push to main, PR) or by hand; a change in craft-contrib does not trigger it — "      - AGENTS.md" — [S36], on.push.paths and on.pull_request.paths
- **C322** [quoted] photocraft calls the shared workflow at @main with rust true, no pinning — "uses: storytold/craft-common-actions/.github/workflows/house-rules.yml@main" — [S36], jobs.house-rules
- **C323** [measured] 20 storytold repos outside craft-common-actions have a house-rules.yml caller and the same 20 carry the craft-house-rules marker in AGENTS.md; craft-anything and autocraft have neither; the org has 77 non-archived repos — Own measurements, L3-M2
- **C324** [measured] All 20 marker-carrying repos pass integrity (digest and source match) but none matches craft-contrib main on 2026-11-18: 19 carry blocks from dde09ea31 (2026-11-06), pdfcraft from 1315c63e1 (2026-11-09) — Own measurements, L3-M3
- **C325** [measured] Since dde09ea31 the canon changed three times: core gained rule 16 (shared libraries first, RFC-0040, 2026-11-16) and the Rust file gained licence-allowlist changes (RFC-0026 2026-11-08, RFC-0027 2026-11-15); none of the 20 copies carries rule 16 — Own measurements, L3-M4
- **C326** [quoted] vectorcraft's rollout copy, commit aabefa3 on 2026-11-06, pinned dde09ea31, made CLAUDE.md import AGENTS.md and added the caller workflow — "The blocks come from craft-contrib at dde09ea31e2e457f5b4653a6e76f7cdf55944bdf. CLAUDE.md imports AGENTS.md. The house-rules workflow checks the copy." — [S37], commit message
- **C327** [quoted] Propagation is done by hand: five "sync house rules to craft-contrib 937c374" PRs were opened on 2026-11-17 by one non-bot human login and are still open; the PR names a local script check — "`scripts/craft-rules.sh check pdfcraft` equivalent run against canon `main`" — [S38], PR body, ## Checks
- **C328** [quoted] A sync PR also removes local restatements made redundant by the new shared rule — local text had duplicated the rule before it reached the block — "This repository carried its own restatement of that guidance in a `## Shared-library reuse` section below the blocks; it is now redundant, and this PR removes it" — [S38], PR body, ## What is new in the blocks
- **C329** [quoted] One earlier propagation was a single hand-copied line in pdfcraft for Unicode-3.0, merged 22 minutes after opening; the other 19 repos never got it — "Copies the shared Rust rules block from storytold/craft-contrib `main`, which now lists `Unicode-3.0`" — [S39], PR body
- **C330** [quoted] Incident in the tool itself: the first writer deleted local instructions between the core and Rust blocks, fixed by craft-common-actions#155 a week later — "The writer replaced the whole range from the first generated block to the last, deleting any local instructions between the core and Rust blocks." — [S40], PR body, ## Summary
- **C331** [quoted] Incident from the rollout copy: vectorcraft's local session-start steps were shortened by the copy commit and a contributor is restoring them — "Puts back the old steps 2 and 3 under \"Start every session here\", plus the \"`plan/` is gitignored (local only)\" line. Commit aabefa3 replaced them with a shorter step 2." — [S41], PR body, ## What and why
- **C332** [measured] The checker had six commits in eight days (2026-11-06 to 2026-11-13) — Own measurements, L3-M5
- **C333** [quoted] RFC-0048 (open, comment period to 2026-11-21) says the local text left outside RFC-0006's block grew and drifted: up to 20 wordings of one rule across 28 repos, some repos relaxing what others enforce — "across 28 public repositories, the same rule appears in up to 20 wordings, some repositories relax rules others enforce" — [S60], rfcs/0048-shared-agents-md.md, ## Motivation
- **C334** [quoted] RFC-0048 keeps the same check design (copy between markers, digest plus recorded revision, stale copy only warns) for one whole shared AGENTS.md — "An edited copy or an invalid revision fails; an intact older copy warns that it is stale." — [S60], rfcs/0048-shared-agents-md.md, Proposal point 5
- **C335** [quoted] RFC-0048 still plans propagation as a maintainer-run command first, automation later, one update PR per repo — "A maintainer-run command, later an automated job, opens one update pull request per repository" — [S60], rfcs/0048-shared-agents-md.md, Proposal point 6
- **C336** [quoted] RFC-0048 rejects linking the shared file instead of copying it, for the same reason as RFC-0006 — "Agents do not reliably open links, so a rule an agent needs on every task has to be in the file it reads." — [S60], rfcs/0048-shared-agents-md.md, ## Alternatives
- **C337** [measured] The core standards file is 3,565 bytes, over the 3 KB budget RFC-0006 sets beside a 10 KB soft limit for the root file; 16 of 20 root AGENTS.md files exceed the 10 KB soft limit (5.0 to 27.2 KB) — Own measurements, L3-M3, L3-M4
- **C338** [inference] storytold's check enforces integrity (no hand edits to the copy) but not freshness: photocraft's caller runs only when AGENTS.md, CLAUDE.md or the workflow changes, staleness only warns, and propagation is a human opening PRs; on 2026-11-18 every copy was stale by 2 to 12 days and one to three rule changes — from [C302], [C310], [C317], [C321], [C324], [C325], [C327]
- **C339** [measured] The three AGENTS.md files are written independently (6,041 / 14,990 / 8,125 bytes) with no marked shared block; shared rules reach sessions through the user-level CLAUDE.md import, one source, no copies — Own measurements, L3-M6
- **C340** [measured] Drift: the issue-linkage bypass lanes differ. jarvis requires priority:critical applied by a non-author human; music-intel-mcp has no such condition and puts [no-issue] at the title's last token; redrobot lists only [no-issue], at title start or end — Own measurements, L3-M7
- **C341** [measured] Drift: music-intel-mcp AGENTS.md sends agents to ~/.claude/reference/engineering-principles.md, which does not exist; the file now lives under the jarvis-private plugin checkout — Own measurements, L3-M8
- **C342** [quoted] Drift by design: jarvis keeps its own copy of the test rule for runs with no user-level layer; it is 11,590 bytes against 14,415 for the user-level copy, with different sections — "It is the repo's own copy of the rule, so a run with no user-level layer (the unattended worker) has the whole of it." — [S43], intro, lines 3-5; sizes Own measurements, M6
- **C343** [quoted] The user-level test rule settles conflicts with a repo copy in prose instead of forbidding them — "Where the repo's rule asks for more than this file (a higher bar on the same test), it wins." — [S44], ## When the repo's own rule disagrees
- **C344** [measured] Drift inside redrobot: its CI/CD section names five PR workflows including Owner Queue Guard but not risk-tier or waiting-human-review, which its Merge denylist relies on and which exist; the user-level file calls the owner-queue label advisory everywhere — Own measurements, L3-M9
- **C345** [quoted] Incident with a stale rules copy: a redrobot session 70 commits behind master stated a removed process as current, and it reached an issue and a grill close-out — "stated `REDROBOT_PROTECTED_EDIT` as the current process, nine days after it was removed. It went into redrobot#2882 and a grill close-out" — [S45], PR body, ## Why
- **C346** [quoted] The fix was an inform-only SessionStart hook costing one fetch per start — "**Cost:** one fetch per session start and per compaction, 6 s at worst." — [S45], PR body, ## What
- **C347** [quoted] Earlier incident: the installed user-level mirror lagged the repo and five skills ran stale bodies silently — "The live skill loaded the stale body without §3a, so `/to-issues` silently stopped proposing the `sandcastle` label." — [S46], ## Problem
- **C348** [quoted] A drift check for shared rule text (jarvis vs jarvis-oss) was proposed in August and closed as obsolete when the copy was retired — "Syncing jarvis and jarvis-oss is retired." — [S47], triage comment, 2026-09-24
- **C349** [quoted] Cross-repo copy drift did cost us, in workflows not rules: redrobot's review workflow kept a permission the jarvis reference had dropped — "The redrobot copy of the review workflow drifted from the jarvis reference: it still grants `id-token: write`" — [S48], ## What to build
- **C350** [measured] 5 queries over 4 repos returned 90 issues and PRs; none records a problem caused by AGENTS.md shared-rule text differing between repos — Own measurements, L3-M10
- **C351** [inference] A storytold-style digest check would have caught none of the incidents found: two were stale copies in time (worktree, mirror), and one was workflow drift. The measured AGENTS.md drift is in paraphrased restatements, which a hash does not cover, the same gap RFC-0048 names for storytold — from [C333], [C339], [C340], [C341], [C345], [C347], [C349], [C350]
- **C352** [inference] The cost side: storytold's check took 433 lines, six commits in eight days and a writer bug that deleted local text, yet left every copy stale; for us a check would also need a copy to check, which today exists only for the test rule — from [C313], [C324], [C330], [C332], [C342]
### Q4 — How AutoCraft is applied to its own repository, and whether its circuit breaker has run — answered with a gap

- **C401** [quoted] The circuit breaker covers three push stages and the merge path; a push stage trips when 2 of its last 10 pushes turned a required check red, the merge path on a red main caused by an AutoCraft merge or a post-merge defect — "A push stage (fix-up, CI fix, fix issue) stops when 2 of its last 10 pushes turned a required check red; the merge path stops when main CI turns red because of a merge of ours or a post-merge review finds a defect in it" — [S49], Waits table, row "Circuit breaker" (line 775)
- **C402** [quoted] A trip has no timer; only an operator resumes the stage, by CLI or dashboard button — "Until an operator resumes the stage (`autocraft pipeline resume <stage>` or the Resume button on the Pipeline page); no timer" — [S49], Waits table, row "Circuit breaker"
- **C403** [quoted] The thresholds are code constants: a window of 10 pushes and 2 breakages — "export const BREAKER_WINDOW = 10;" — [S50], lines 12-13 (BREAKER_BROKE = 2)
- **C404** [quoted] "Required" is AutoCraft's own notion: every check except per-repo optional ones and skipped ones, not GitHub branch-protection required checks — "Optional checks and skipped ones do not count." — [S50], line 3, doc comment of requiredResult
- **C405** [quoted] Only pushes to PR branches are counted; batch pushes and main-fix pushes are not recorded for the breaker — "Pushes of other kinds (batches, main fixes) are not recorded." — [S51], doc comment, line 45
- **C406** [quoted] Trip state lives in a local SQLite table, one row per stage, cleared only by an operator, with evidence as JSON refs — "Circuit breaker: a stage that stopped itself. One row per stage; active = 1 while tripped, and only an operator clears it" — [S52], table stage_trips comment (line 1553)
- **C407** [quoted] On a repo marked as a test repo a post-merge defect or red main trips only that repo's merge breaker — "On a test repo, a post-merge defect or a red default branch trips the breaker `merge:<repo>` only, which holds merges on that repo and not the whole pipeline." — [S49], CLI section, paragraph after the command table (line 848)
- **C408** [quoted] Separate from the breaker, a red main makes ready PRs and batches wait until main is green, except AutoCraft's own main-fix PRs — "ready PRs and open batches wait, AutoCraft's main-fix PRs (branches `autocraft/main-ci-*`) do not" — [S49], Waits table, row "Main CI red"
- **C409** [quoted] The breaker was added on 2026-11-04 in one commit by the main human author, with tests — "Record the required-check outcome of every push of ours and trip a stage after repeated breakage" — [S53], commit headline, 2026-11-04T12:44Z, author aiongg; files include test/push-outcome.test.ts
- **C410** [quoted] The test-repo variant came a day later — "A post-merge defect or red main on a test repo trips that repo's own merge breaker, not the pipeline's" — [S54], commit headline, 2026-11-05T21:36Z
- **C411** [quoted] A second breaker trips on a surge of outside-author items — "More than `outside_surge_per_hour` (default 30) new outside-author items in the last hour trips the breaker `outside-surge`." — [S49], Outside authors, "Surge breaker" (line 688)
- **C412** [quoted] The global switch: Off cancels queued jobs and refuses writes of running ones — "Turning it Off cancels queued automatic jobs; running ones finish, but their GitHub writes are refused." — [S55], Commands list, `autocraft runner serve` (line 10)
- **C413** [quoted] A deploy drains the pipeline, waits for running jobs, deploys, then switches it back on — "A deploy runs `pipeline drain`, waits for the running jobs, deploys, then runs `pipeline on --if-draining`" — [S55], Commands list, line 10
- **C414** [quoted] Production deploys by git push to a bare repo whose post-receive hook builds and switches the release — "A production install runs the dashboard, the runner, the sync timer and a daily database backup as system services of one unprivileged user, and deploys by `git push`." — [S55], Production install (line 375)
- **C415** [quoted] Each tracked repo also has a per-repo pipeline switch that starts off — "A newly tracked repo starts off." — [S49], "Pipeline switch per repo" (line 677)
- **C416** [quoted] The container deploy checklist builds and pushes images from a checkout, without CI — "Build and push from a checkout, on any machine with Docker or Podman. No CI is involved." — [S56], intro (line 7)
- **C417** [quoted] The repo's own agent rules put verification on the author before pushing, not on CI — "Before pushing: `pnpm check` and the tests for what you changed." — [S57], last bullet of "Working on AutoCraft"
- **C418** [measured] The repo has three workflow files: Docker publish (push to main, tags), Lockfile check (push to main and PRs) and the actions.lock file itself; no workflow runs pnpm test or pnpm check — Own measurements, L4-M2
- **C419** [quoted] The Docker publish workflow exists to publish the image the cluster runs, via the shared reusable workflow — "Publishes the image the cluster's `autocraft` Deployment runs." — [S58], header comment
- **C420** [measured] Neither the Dockerfile nor the deploy hook runs the test suite; the hook runs web tsc --noEmit, a vite build and a CLI-load check — Own measurements, L4-M8
- **C421** [measured] No CI check ran on main before 2026-11-07 20:08 UTC: of the newest 1,500 of 1,534 main commits, 1,418 carry no check rollup at all and only 82 do, all from 2026-11-07 on — Own measurements, L4-M1
- **C422** [measured] Main is developed by direct pushes: 1,452 of the 1,500 sampled commits are by one login (aiongg), 449 are merge-headline commits of local branches, and only 44 are associated with a PR — Own measurements, L4-M1
- **C423** [measured] The repo has 13 PRs, all merged, all by humans (dylanmtaylor, davidmann4, magnus919), all merged by aiongg; none from an AutoCraft branch — Own measurements, L4-M4
- **C424** [measured] No AutoCraft review or comment appears on the four of its own PRs read (#6, #9, #12, #13), and its one issue has no comments or labels; the only bot reviewer is CodeRabbit, which skipped several PRs (fewer than 10 stars, free OSS limit) — Own measurements, L4-M7
- **C425** [inference] AutoCraft's pipeline stages (review, fix-up, CI fix, merge queue, post-merge review) leave no visible trace on storytold/autocraft (no AutoCraft branch among its 13 PRs, no AutoCraft review on those read), and the breaker counts only AutoCraft's own pushes to PR branches and its own merges, so on its own repo the breaker had nothing to count: the human-pushed main is outside its scope by design — from [C401], [C405], [C422], [C423], [C424]
- **C426** [measured] Of 82 main commits with a check rollup, 11 read FAILURE; 7 of those are only CANCELLED jobs (the publish workflow cancels in-progress runs on a new push) and 4 have a real failed job — Own measurements, L4-M1, L4-M3
- **C427** [measured] Three real failures sit in a 44-minute burst on 2026-11-07 while the container build was being written (20:08 to 20:49), green at 20:52; the fourth (2026-11-08 23:01) was a DigitalOcean registry authorization failure — Own measurements, L4-M3, L4-M6
- **C428** [measured] No revert commit exists in the sampled main history or in commit search, and no commit headline names a broken main or a rollback; the only CI-repair headlines are "Fix test typing", "Fix test expectation", "Fix ci-approval test" — Own measurements, L4-M1, L4-M5
- **C429** [inference] Every red main in the repo's own history was red infrastructure (image build, registry credentials), not a failing test, because no test runs in its CI at all; its history says nothing about how often its code breaks — from [C418], [C420], [C426], [C427]
- **C430** [measured] Commit search for breaker, circuit and tripped in storytold/autocraft finds only the commits that built the breakers; org-wide issue and commit search for "circuit breaker" and "breaker tripped" finds only unrelated product text (line breakers, hinting) — Own measurements, L4-M5
- **C431** [measured] Web search for AutoCraft or storytold with circuit breaker, tripped, broke main or revert returned no page about AutoCraft — Own measurements, L4-M9
- **C432** [inference] No public evidence shows the breaker ever tripped; the trip record lives only in the operator's local stage_trips table and the dashboard, which are not public, so absence on GitHub is not evidence it never tripped — from [C406], [C430], [C431]
- **C433** [inference] The breaker is 14 days old (2026-11-04) and is built for repos AutoCraft pushes to and merges in, i.e. the craft apps it tracks, not its own repo; evidence of it in real operation would have to come from those repos or the operator — from [C409], [C425], [C432]
- **C434** [quoted] An outside user opened the repo's only open issue proposing reversibility-based approval and a dead-man alarm, which AutoCraft has not answered — "Approval by reversibility, not by write type." — [S59], issue body, item 4 (opened 2026-11-18, no comments)

## Disconfirming evidence

- [C101]/[C128] (batching is how photocraft merges): weekly same-second share (L1-M4) shows batching only from Oct 19 to early Nov, 1% in Nov 9-15. Recorded as C127, C129, C131.
- [C114]-[C116] (batches keep main working): query `org:storytold "integration batch"` and a read of lightcraft batch 33. Main was red before that batch (C133). Under single merges a maintainer accepted known red CI (C136).
- [C137]-[C152] (AutoCraft batching is in use): a check of whether AutoCraft batches photocraft. The only batch PRs in AutoCraft format are on designcraft (C153). photocraft's November merges are singles (C129). Use is unconfirmed beyond designcraft, see C154.
- [C130] (batching adds a step): searched the other batch threads for a defence of batching; only the integrators' own rationale turned up (C111). Nothing contradicts C130.
- Process documented as policy: code search `org:storytold "integration batch"` found no RFC or house rule (C155).
- External: WebSearch `storytold photocraft "integration batch" pull requests merge main broken`: nothing relevant.
- [C164] (~151/week for redrobot): not reproduced. The maximum was 143 for Nov 12-18 (L1-M7).
- [C246] no welcome bot or entry gate — searched workflow list (L2-M9) and trees (L2-M1) for welcome/first-interaction/labeler/stale/CLA: none; counters: AutoCraft gates outsiders' model work and approves held CI [C237], [C238]; craft-anything has a PR template [C202].
- [C207] rules copied into every repo — grep of craft-anything AGENTS.md for the block marker: 0, so the copy is not universal [C229].
- [C233] CodeRabbit first — 7 of 7 sampled threads; a sample, not a rate; no human-welcome-first thread found.
- [C234], [C236] held CI is a newcomer bottleneck — counter-reading: 2,500 may include stale and superseded heads and is API-reported, not per PR; #13509 still merged in 3 days [C242].
- [C243] closes are human and polite — read closed-unmerged PRs carrying the AutoCraft note (L2-M5, L2-M7): both samples human-closed; the other 11 AutoCraft-noted closes not read.
- Industry pattern vs storytold (claim removed in audit) — query `storytold photocraft pull request contributors AI agents maintainers flood`: no coverage of storytold by name; results describe tldraw auto-closing and Godot complaints, the opposite stance (disclosure, closing) to rule 15.
- [C258] what redrobot lacks — searched AGENTS.md, team-workflow.md, onboarding.md and the tree for a response clock, accountability and stale-PR rules: none found; stale claims only reported weekly [C255].
- On C327/C338 (propagation is manual): searched craft-contrib's own workflows (clone) for a sync job: only lockfile.yml and sonarcloud.yml, no house-rules or AGENTS job; `gh search code "house_rules.py write" --owner storytold` → 0. Nothing found against.
- On C324/C338 (every copy stale): `gh search issues "\"behind main\" house" --owner storytold` → 0; `house rules` issues/PRs (41+100) show no failed-check incident, only the five open sync PRs and pdfcraft#6635. Not contradicted.
- On C333 (local text is where drift is): RFC-0048 is open and contested (credit and accessibility objections), not accepted; its 20-wordings count is the author's, not re-measured here.
- On C350/C351 (no rule-text drift incident for us): 5 queries ×4 repos, 90 hits read by title; jarvis-private#107 is the nearest case and it is staleness in time, not cross-repo. Session transcripts and decision journals were not searched.
- On C342 (copy needed for unattended runs): not tested whether CI review in redrobot or music-intel-mcp loads the user-level layer; jarvis says its unattended worker does not.
- On C401/C403 (breaker as specified): looked for code contradicting the docs; push-outcome.ts constants BREAKER_WINDOW = 10, BREAKER_BROKE = 2 match the docs. Nothing against.
- On C421/C418 (no test CI on its own main): searched for any workflow running tests (workflows dir, Dockerfile, deploy hook, CodeQL dynamic runs); found only build, lockfile, CodeQL actions scan and CodeRabbit. The newest 1,500 commits were sampled; the oldest 34 of 1,534 (before 2026-11-02 18:32) were not read, but no rollup exists on any commit before 2026-11-07, so they would not change the count of checked pushes.
- On C425 (pipeline does not run on its own repo): searched PRs for autocraft/* branches, AutoCraft-authored comments or reviews, labels on issue #14; none. Could not read the operator's tracked-repo list (local DB), so "not tracked" is not proven, only "no visible action".
- On C428 (no reverts): `search/commits repo:storytold/autocraft revert` → 0; headline regex over 1,500 commits → no revert, rollback or hotfix. A force-push that rewrote main would leave no trace here; not checkable via API.
- On C432 (no evidence of a trip): queries `repo:storytold/autocraft breaker|circuit|tripped` (commits), `org:storytold "circuit breaker"`, `org:storytold breaker tripped`, `org:storytold "autocraft" paused` (issues), web search "storytold autocraft "circuit breaker" agent merge tripped" and "AutoCraft storytold software factory problems broke main revert"; nothing about a trip came back. A trip writes no GitHub artifact by design (C406), so this search cannot find one; it is a stated gap, not a negative.
- On C429 (red main was infra only): read one failed job log (c1882e31, registry auth); the 11-07 failures were inferred from commit headlines about the Dockerfile, their logs were not read.


## Coverage

| Channel | Read | Gap |
|---|---|---|
| Users | storytold PR and issue threads: batch PRs, take-out comments, newcomer PRs, sync PRs ([C109], [C130], [C234], [C235], [C242], [C327]); one outside issue on autocraft ([C434]) | no discussion forum or blog by storytold contributors found; Reddit not used |
| Specialists | storytold's own docs and RFCs: AutoCraft pipeline.md and operations.md, craft-contrib RFC-0003/0006/0048, craft-common-actions check source, AGENTS.md files; our repos' AGENTS.md, decisions and references | no outside practitioner writing about storytold's process found |
| Data | own measurements over the GitHub API: merge timing by week, PR author associations, held runs, house-rules copy freshness, commit check rollups (L1-M1..L4-M9) | sampled, not full history; integrator roles and AutoCraft's own trip log not observable |
| Adversarial | disconfirming searches per load-bearing claim; storytold's own incidents (lightcraft red main, craft-common-actions#155, vectorcraft#8407, RFC-0048's drift finding); our incidents (jarvis-private#107, jarvis#753, redrobot#3164) | no post-mortem by storytold on batching or the breaker |

Declared overruns:
- Q1: about 85 GitHub API calls against a budget of about 60 (per-week merge windows, membership checks); 1 web search.
- Q2: about 64 GitHub API calls; page reads past the ceiling of three, because the answer spans two organizations' file sets.
- Q3: page reads past the ceiling: the check spans three files, and measuring drift needed all 20 copies.
- Q4: page reads past the ceiling, because the sub-question turns on source code and docs together; about 45 API calls, within budget.

No fetched page addressed instructions to the agents. No search-and-scrape connector was used; all reads went through `gh`, `curl` on raw files and the built-in web tools.

## Own measurements

<!-- ledger Q1 -->
### L1-M1

`fetch_prs.py` (gh api repos/storytold/<r>/pulls/<n>) and `check_members.py`:
`#9386 head davidmann4/photocraft:integration-batch-8 merged_at 2026-10-26T00:04:41Z merged_by aiongg commits 372 changed_files 217`; members `6923 00:04:44 aiongg`, `4573 00:04:44 aiongg`, `1199 00:04:44 aiongg`, `9454 00:04:43 aiongg`, `8846 00:04:43 aiongg`.

### L1-M2

`gh api -i orgs/storytold/members/<l>`: echelon 204, bflatastic 204, tanish2k09 204, benandez 204; davidmann4 404, aiongg 404, FredApps 404, Higgs32584 404

### L1-M3

`gh api search/issues q='org:storytold "integration batch"'` total 847; batch PRs in photocraft, lightcraft, designcraft, pdfcraft, effectcraft, deckcraft, soundcraft, wordcraft, figcraft, artcraft-services; e.g. pdfcraft#3983 "Integration batch: 218 PRs on main".

### L1-M4

`weekly_batching.py storytold/photocraft 2026-09-28 7` (gh pr list --state merged, two half-week windows each):
```
09-28 merged=47 same_second=0 top=echelon 47
10-05 merged=1360 same_second=0 top=echelon 1115, bflatastic 199
10-12 merged=976 same_second=26 (3%) top=echelon 807, skylartaylor 80
10-19 merged=805 same_second=519 (64%) top=aiongg 564, echelon 159
10-26 merged=312 same_second=238 (76%) top=aiongg 184, dylanmtaylor 120
11-02 merged=442 same_second=112 (25%) top=davidmann4 240, FredApps 109
11-09 merged=547 same_second=5 (1%) top=davidmann4 334, FredApps 71, tanish2k09 71
```

### L1-M5

`sample_single.py storytold/photocraft 2026-11-12 davidmann4`: "47 merged on 2026-11-12; 36 by davidmann4".

### L1-M6

`gh api search/code q='org:storytold "integration batch"'` total 42: 35 autocraft files, the rest photocraft/lightcraft parity, gaps and roadmap docs; none in craft-contrib or any AGENTS.md.

### L1-M7

`weekly_batching.py SergazyNarynov/redrobot 2026-10-19 4` and `measure_week.py ... 2026-11-12 2026-11-18`:
`10-19 105 (same_second 0)`, `10-26 22 (0)`, `11-02 115 (0)`, `11-09 134 (0)`, `11-12..18 143 (0)`; two merging logins.

<!-- ledger Q2 -->
### L2-M1

`q2_fetch_tree.py` (git/trees/HEAD?recursive=1 + path regex): photocraft hits AGENTS.md, SECURITY.md, docs/contributing.md, book/.../contributing.md, contributors/people.toml, workflows/house-rules.yml; no root CONTRIBUTING, ISSUE_TEMPLATE, pull_request_template. craft-anything: ISSUE_TEMPLATE/{bug_report,config,idea}, pull_request_template.md, AGENTS.md, CLAUDE.md, CONTRIBUTING.md. autocraft: AGENTS.md, CONTRIBUTING.md. storytold/.github: "Not Found (HTTP 404)". No cla/dco path. house-rules.yml paths: AGENTS.md, CLAUDE.md, the workflow.

### L2-M2

`wc -c` AGENTS.md: photocraft 27199, craft-anything 12275. `grep -c "craft-house-rules:start"`: craft-anything 0, photocraft 2.

### L2-M3

`q2_prs.py` (pulls closed 3 pages, open 1): closed 300 (created 11-11..11-18): CONTRIBUTOR merged 203/unmerged 40; MEMBER 40/6; NONE 6/5. Open 100: CONTRIBUTOR 63, MEMBER 2, NONE 35. `q2_once.py`: 56 authors, 20 with 1 PR, top 45. NONE author Bobderto: 6 merged.

### L2-M4

`q2_threads.py photocraft 13274 15453 15432 15589 15437`: first comment coderabbitai[bot] on each; #15432 (1 PR in repo) "Actionable comments posted: 11", ai-agent/bridge.py + React/Vite, open, no other commenter; #15437 24 action_required runs, no maintainer reply; #13274, #12945 closed by their author (events).

### L2-M5

`actions/runs -f status=action_required --jq .total_count` → 2500. search total_count: `is:pr "Not a maintainer decision"` 89; with `is:closed is:unmerged` 13; `"AI-generated review"` 3775 (discarded, loose matching).

### L2-M6

`q2_threads.py photocraft 13509 13419`: #13509 PRs=3 merged=1 first_pr=#13509, merged 11-15T14:44, first comment coderabbitai 11-12T16:48. #13419 first_pr=#9926.

### L2-M7

`q2_close.py`: #6579 closed by tanish2k09 (MEMBER) as superseded; #5767 closed by its author.

### L2-M8

`q2_rr.py`, `q2_rr2.py` (read-only, local): CONTRIBUTING.md "Not Found (HTTP 404)"; root: .claude/ AGENTS.md GLOSSARY.md README.md REVIEW.md … (no LICENSE, SECURITY, CODEOWNERS); .github: ISSUE_TEMPLATE/ PULL_REQUEST_TEMPLATE.md workflows/; tree has workflows/claim-guard.yml, scripts/claim_issue.py, docs/onboarding.md.

### L2-M9

`contents/.github/workflows` of craft-common-actions: 21 names, e.g. gate, house-rules, refresh-contributors, release, sonarcloud, supply-chain; none welcome/first-interaction/labeler/stale.

<!-- ledger Q3 -->
### L3-M1

`curl -sL raw.githubusercontent.com/storytold/craft-common-actions/main/{.github/workflows/house-rules.yml,actions/house-rules/action.yml,actions/house-rules/house_rules.py} | wc -l` → 57, 35, 341.

### L3-M2

`gh search code house-rules.yml --owner storytold` → 28 hits, house-rules.yml in 20 repos besides craft-common-actions; `gh search code craft-house-rules:start --owner storytold` → AGENTS.md in the same 20; `gh repo list storytold --limit 200` → 82 total, 77 not archived.

### L3-M3

q3/drift.py (own re-implementation, storytold's script not run) against `git clone craft-contrib` (main f845d663f, 2026-11-18): 20 of 20 `digest=ok match_src=ok on_main=True same_as_main=False`; core@dde09ea31 ×19, core@1315c63e1 ×1 (pdfcraft); AGENTS.md 5,046–27,199 bytes, 16 over 10,240.

### L3-M4

`git diff --stat dde09ea31 origin/main -- standards/house-rules-core.md` → 1 insertion (937c374 RFC-0040); same for rust → 11 insertions (0f6cc48 RFC-0026, f750223 RFC-0027); `wc -c` core 3,565, rust 2,969.

### L3-M5

`gh api repos/storytold/craft-common-actions/commits?path=actions/house-rules/house_rules.py` → 6 commits, 70fc5d496 2026-11-06T10:34 … 13ad478f3 2026-11-13T20:18.

### L3-M6

`gh api repos/<r>/contents/AGENTS.md`: jarvis 6,041 B, redrobot 14,990 B, music-intel-mcp 8,125 B; CLAUDE.md 404 ×3. `wc -c` test-quality.md: jarvis docs/reference 11,590, jarvis-private reference 14,415; `diff -q` → differ; only upstream: "When you change production code", "When the repo's own rule disagrees"; only jarvis: "What the PR's ## Testing section holds", "Open exception: tests/ci/ mirrors".

### L3-M7

`grep -o` over the three AGENTS.md: jarvis:23 "`priority:critical` hotfix applied by a non-author human (#2082), `refactor:` title prefix, `[no-issue]` marker"; mim:35 "`priority:critical` label (hotfix), or contain a `[no-issue]` line of its own in the body, or as the title's last token"; redrobot:86 "at the start or end of the **PR title**, or alone on a line of the body"; redrobot has no refactor:/priority:critical lane.

### L3-M8

mim AGENTS.md:20 cites `~/.claude/reference/engineering-principles.md`; `ls` → "No such file or directory"; `~/.claude/plugins/marketplaces/jarvis-private/reference/engineering-principles.md` → 5,678 B.

### L3-M9

`gh api repos/SergazyNarynov/redrobot/contents/.github/workflows` → includes owner-queue-guard.yml, risk-tier.yml, waiting-human-review.yml; redrobot AGENTS.md:107-110 names CI, Code Review, PR Checks, Owner Queue Guard, Gitleaks; :146 relies on `waiting-human-review`.

### L3-M10

q3/ours3.py: `gh search issues <q> --include-prs`, 5 queries ("drift in:title", "out of sync", "stale copy", "AGENTS.md copy", "mirror drift") × 4 repos → 90 hits; rule-copy staleness: jarvis#753, #1730, jarvis-private#107; workflow-copy drift: jarvis#1300, redrobot#3164.

<!-- ledger Q4 -->
### L4-M1

`python -I fetch.py 15` (GraphQL `repository.defaultBranchRef.target.history(first:100)` with statusCheckRollup, 15 pages) then `python -I analyze.py`. Output trimmed: "totalCount 1534 sampled 1500" / "newest 2026-11-17T17:03:32Z d8e45b5d | oldest sampled 2026-11-02T18:32:11Z 06ca8cfc" / "rollup states {'SUCCESS': 71, 'NONE': 1418, 'FAILURE': 11}" / "oldest commit with any rollup ('2026-11-07T20:08:58Z', '626e6346')" / "authors [('aiongg', 1452), ('davidmann4', 30), ('dylanmtaylor', 12), ('magnus919', 6)]" / "commits with an associated PR 44 merge-headline commits 449". Keyword headlines (revert|undo|roll back|breaker|trip|hotfix|broke|broken|red main|fix build/ci/test): "Fix test typing", "Fix test expectation", "Merge test-repo-trip", the breaker commits, "Fix ci-approval test", "Pin pnpm 11.28.10: 11.12.0 is marked broken"; no revert.

### L4-M2

`gh api repos/storytold/autocraft/contents/.github/workflows` and each file raw. Output: files actions.lock, docker-publish.yml ("on: push: branches: [main] tags: ["v*"]", "uses: storytold/craft-common-actions/.github/workflows/docker-build.yml@main"), lockfile.yml ("on: pull_request: push: branches: [main]", step "gh actions-lock --verify"). Checks seen on main (M1 analysis): "Docker publish / publish / Build linux/amd64", "... linux/arm64", "Publish multi-arch manifests", "CodeRabbit", "CodeQL / Analyze (actions)", "Lockfile / Lockfile is in sync", ".github/dependabot.yml".

### L4-M3

`python -I timeline.py`. Output trimmed: "2026-11-07T20:08:58Z | 626e6346 | FAILURE | REAL-FAIL | Publish the container image from CI" / "20:37:35Z | 777ee888 | FAILURE | cancel-only" / "20:46:30Z | e37245fc | FAILURE | REAL-FAIL | Install curl for the GitHub CLI fetch..." / "20:49:22Z | 73211a27 | FAILURE | REAL-FAIL | Provide gzip for the GitHub CLI archive..." / "20:52:09Z | c7912fe4 | SUCCESS" / "2026-11-08T23:01:20Z | c1882e31 | FAILURE | REAL-FAIL | Unassign tests answer the pipeline account lookup with a fake gh" / "pushes with rollup 82 real failures 4". Conclusion counts: "6 Build linux/amd64 CANCELLED, 3 FAILURE, 45 SUCCESS"; "8 Build linux/arm64 CANCELLED, 1 FAILURE".

### L4-M4

`gh pr list --repo storytold/autocraft --state all --limit 100 --json ...` then `python -I prs.py`. Output: 13 rows, all MERGED; authors dylanmtaylor (#1-#5), davidmann4 (#6-#10, #13), magnus919 (#11, #12); branches e.g. "feat/dockerhub-push", "merge-queue-board", "search-github-url"; none prefixed autocraft/. `gh issue list --state all` → one issue, #14, OPEN, no labels.

### L4-M5

`gh api -X GET search/commits -f q="repo:storytold/autocraft <term>"`: breaker 3 (d68f4e14, 66291305, ef745511), circuit 0, tripped 3 (736af0d7, 66291305, b69e9fe2), revert 0. `search.py`: issues `org:storytold "circuit breaker"` 6 hits (cadcraft, pdfcraft, effectcraft, craft-anything feature text), `org:storytold breaker tripped` 1 (wordcraft hinting), commits `org:storytold breaker` 35 (line breakers in designcraft/vectorcraft, wordcraft hinting, plus the 3 autocraft commits).

### L4-M6

`gh run view --repo storytold/autocraft --job 128891607425 --log-failed` (commit c1882e31). Output trimmed: "ERROR: failed to push registry.digitalocean.com/artcraft/autocraft: failed to authorize: failed to fetch oauth token" / "##[error]Process completed with exit code 1."

### L4-M7

`gh pr view <n> --json comments,reviews,mergedBy` for #6, #9, #12, #13 then `python -I prconv.py`. Output: "6 mergedBy aiongg / C coderabbitai"; "9 mergedBy aiongg / R coderabbitai COMMENTED Actionable comments posted: 2 / R davidmann4"; "12 mergedBy aiongg / R coderabbitai Actionable comments posted: 1"; "13 mergedBy aiongg / C coderabbitai". PR #6 CodeRabbit: "This repository does not receive automatic reviews because it has fewer than 10 stars."; PR #13: "You've used all free OSS reviews for now."

### L4-M8

`curl -sL .../deploy/container/Dockerfile` and `.../deploy/hook.sh`, grep -i "test|check|pnpm". Dockerfile: only "pnpm install", "pnpm exec vite build" RUN steps, no test. hook.sh: "pnpm install --frozen-lockfile --prod --ignore-scripts", "pnpm -C web exec tsc --noEmit", "pnpm -C web exec vite build", "-> Checking that the CLI loads..."; no pnpm test.

### L4-M9

WebSearch (standard) "storytold autocraft "circuit breaker" agent merge tripped" and "AutoCraft storytold software factory problems broke main revert", 2026-11-18. Tool summaries, verbatim: "The search didn't turn up anything about "storytold" or "autocraft," so I can't confirm those terms." and "The search didn't turn up anything about AutoCraft or Storytold". Results were generic agent circuit-breaker articles (hackernoon, dev.to, oneuptime docs) and software-factory pieces.


## Open questions

- Q1 — who the integrators are (public org membership cannot separate private members from outside collaborators), why photocraft stopped batching (no written reason found outside wordcraft), and whether AutoCraft merges photocraft at all. Settled by the maintainers' own statement, or by matching AutoCraft branch names across photocraft's merged PRs.
- Q1 — what main's CI state was in the batch weeks. Settled by sampling check rollups of photocraft main commits from Oct 19 to Nov 6, as the companion run does for main health.
- Q2 — a first-PR merge rate for newcomers. GitHub's author_association does not mark newcomers here [C231]; settled by computing each author's first PR and its outcome from the PR list.
- Q3 — whether storytold's stale-copy warning ever fired in a run (Actions logs not read), and whether CI review in redrobot or music-intel-mcp loads the user-level rules at all; if it does not, the shared rules reach local sessions but not the review bot.
- Q4 — whether the breaker has tripped in the craft repos AutoCraft pushes to. The trip record is local to the operator [C406], [C432]; an indirect trace would be a sudden stop of AutoCraft pushes on one repo. A next run.

## Sources

- [S1] https://github.com/storytold/photocraft/pull/9386 — passage
- [S2] https://github.com/storytold/photocraft/pull/8355 — passage
- [S3] https://github.com/storytold/photocraft/pull/1199 — passage
- [S4] https://github.com/storytold/photocraft/pull/1199#issuecomment-6397823413 — passage
- [S5] https://github.com/storytold/photocraft/pull/1199#issuecomment-6398842098 — passage
- [S6] https://github.com/storytold/designcraft/issues/259 — passage
- [S7] https://github.com/storytold/wordcraft/pull/4997#issuecomment-6617703450 — passage
- [S8] https://github.com/storytold/lightcraft/pull/1431 — passage
- [S9] https://github.com/storytold/photocraft/pull/13546 — passage
- [S10] https://raw.githubusercontent.com/storytold/autocraft/HEAD/docs/pipeline.md — passage
- [S11] https://github.com/storytold/designcraft/pull/2291 — passage
- [S12] https://github.com/SergazyNarynov/redrobot/blob/master/AGENTS.md — passage
- [S13] https://github.com/SergazyNarynov/redrobot/blob/master/docs/decisions/2026-11-18-rebase-only-on-file-overlap.md — passage
- [S14] https://github.com/SergazyNarynov/redrobot/blob/master/docs/decisions/2026-10-14-red-is-not-merged.md — passage
- [S15] https://raw.githubusercontent.com/storytold/photocraft/HEAD/AGENTS.md — passage
- [S16] https://raw.githubusercontent.com/storytold/photocraft/HEAD/book/src/getting-started/contributing.md — passage
- [S17] https://raw.githubusercontent.com/storytold/craft-anything/HEAD/CONTRIBUTING.md — passage
- [S18] https://raw.githubusercontent.com/storytold/craft-anything/HEAD/CLAUDE.md — passage
- [S19] https://raw.githubusercontent.com/storytold/craft-contrib/HEAD/rfcs/0006-coding-agents.md — passage
- [S20] https://raw.githubusercontent.com/storytold/photocraft/HEAD/.github/workflows/house-rules.yml — passage
- [S21] https://raw.githubusercontent.com/storytold/craft-contrib/HEAD/rfcs/0003-claiming-issues.md — passage
- [S22] https://raw.githubusercontent.com/storytold/craft-anything/HEAD/.github/pull_request_template.md — passage
- [S23] https://raw.githubusercontent.com/storytold/craft-contrib/HEAD/README.md — passage
- [S24] https://raw.githubusercontent.com/storytold/photocraft/HEAD/docs/contributors.md — passage
- [S25] https://github.com/storytold/photocraft/pull/13509 — passage
- [S26] https://github.com/storytold/photocraft/pull/15437 — passage
- [S27] https://github.com/storytold/photocraft/pull/6579 — passage
- [S28] https://github.com/storytold/photocraft/pull/15453 — passage
- [S29] https://news.lavx.hu/article/tldraw-halts-external-pull-requests-as-ai-generated-submissions-overwhelm-maintainers — snippet only
- [S30] https://github.com/SergazyNarynov/redrobot/blob/master/docs/onboarding.md — passage
- [S31] https://github.com/SergazyNarynov/redrobot/blob/master/docs/plans/team-workflow.md — passage
- [S32] https://github.com/SergazyNarynov/redrobot/blob/master/.github/PULL_REQUEST_TEMPLATE.md — passage
- [S33] https://raw.githubusercontent.com/storytold/craft-common-actions/main/.github/workflows/house-rules.yml — passage
- [S34] https://raw.githubusercontent.com/storytold/craft-common-actions/main/actions/house-rules/house_rules.py — passage
- [S35] https://raw.githubusercontent.com/storytold/craft-common-actions/main/README.md — passage
- [S36] https://raw.githubusercontent.com/storytold/photocraft/main/.github/workflows/house-rules.yml — passage
- [S37] https://github.com/storytold/vectorcraft/commit/aabefa3a2 — passage
- [S38] https://github.com/storytold/pdfcraft/pull/7657 — passage
- [S39] https://github.com/storytold/pdfcraft/pull/6635 — passage
- [S40] https://github.com/storytold/craft-common-actions/pull/155 — passage
- [S41] https://github.com/storytold/vectorcraft/pull/8407 — passage
- [S42] https://github.com/storytold/craft-contrib/pull/72 — passage
- [S43] https://github.com/Osasuwu/jarvis/blob/main/docs/reference/test-quality.md — passage
- [S44] https://github.com/Osasuwu/jarvis-private/blob/master/reference/test-quality.md — passage
- [S45] https://github.com/Osasuwu/jarvis-private/pull/107 — passage
- [S46] https://github.com/Osasuwu/jarvis/issues/753 — passage
- [S47] https://github.com/Osasuwu/jarvis/issues/1730 — passage
- [S48] https://github.com/SergazyNarynov/redrobot/issues/3164 — passage
- [S49] https://raw.githubusercontent.com/storytold/autocraft/main/docs/pipeline.md — passage
- [S50] https://raw.githubusercontent.com/storytold/autocraft/main/src/core/push-outcome.ts — passage
- [S51] https://raw.githubusercontent.com/storytold/autocraft/main/src/push-outcomes.ts — passage
- [S52] https://raw.githubusercontent.com/storytold/autocraft/main/src/schema.sql — passage
- [S53] https://github.com/storytold/autocraft/commit/b69e9fe2 — passage
- [S54] https://github.com/storytold/autocraft/commit/66291305 — passage
- [S55] https://raw.githubusercontent.com/storytold/autocraft/main/docs/operations.md — passage
- [S56] https://raw.githubusercontent.com/storytold/autocraft/main/docs/deploy-checklist.md — passage
- [S57] https://raw.githubusercontent.com/storytold/autocraft/main/AGENTS.md — passage
- [S58] https://raw.githubusercontent.com/storytold/autocraft/main/.github/workflows/docker-publish.yml — passage
- [S59] https://github.com/storytold/autocraft/issues/14 — passage
- [S60] https://github.com/aiongg/craft-contrib/blob/ff4cefb2ecd5b5161c54a8efef266ffe186b3559/rfcs/0048-shared-agents-md.md — passage (RFC-0048 file at the head of craft-contrib#72)

## Audit

| Claim | Verdict | Note |
|---|---|---|
| C101 | SUPPORTED |  |
| C102 | SUPPORTED |  |
| C103 | SUPPORTED | matches L1-M1; head and merge time re-read from the PR |
| C104 | SUPPORTED | matches L1-M1; #4573 take-out confirmed in S1 table |
| C105 | PARTIAL | quote says he tested each PR in the app, not the batch; narrowed |
| C106 | SUPPORTED |  |
| C107 | PARTIAL | one PR's acceptance stated as the general process; narrowed to #1199 |
| C108 | SUPPORTED |  |
| C109 | PARTIAL | one PR's fix-up stated as the general practice; narrowed to #1199 |
| C110 | SUPPORTED |  |
| C111 | SUPPORTED |  |
| C112 | SUPPORTED | quote trimmed before '#5940': GitHub's page inlines that PR's title there, so the full quote failed the page check; full text verbatim in the PR body via API |
| C114 | SUPPORTED | local gate is in the next bullet of the same section |
| C115 | SUPPORTED |  |
| C116 | SUPPORTED |  |
| C118 | SUPPORTED |  |
| C119 | SUPPORTED | 'land with its caller' is in the same table cell |
| C120 | SUPPORTED | S1 has two reference-application take-outs (#9183, #4573); quote shows one |
| C121 | SUPPORTED | acceptance-before-creation dates are in the same comment |
| C122 | PARTIAL | one batch's two PRs stated as a general rule; narrowed to #8355 |
| C123 | SUPPORTED |  |
| C124 | SUPPORTED |  |
| C125 | SUPPORTED | #4573 take-out found in S1 (reverted in c01dc04b5) |
| C126 | PARTIAL | date range not in recorded output, and 218 is one example, not a measured maximum; narrowed |
| C127 | SUPPORTED | weekly shares and the 900 sum match L1-M4 |
| C128 | PARTIAL | that all 900 are batch landings needs an unstated premise; narrowed to 'fit' |
| C129 | PARTIAL | 'one batch PR' is not in the recorded output; removed |
| C130 | SUPPORTED |  |
| C131 | PARTIAL | 'reason written only for wordcraft' is an absence not established; narrowed to 'the one found' |
| C133 | PARTIAL | quote shows lightcraft main red during batching, not batches in general failing to keep main green; narrowed |
| C136 | SUPPORTED |  |
| C137 | SUPPORTED |  |
| C138 | SUPPORTED |  |
| C139 | SUPPORTED |  |
| C140 | SUPPORTED |  |
| C141 | SUPPORTED | 'grows by one' is the sentence before the quote |
| C143 | SUPPORTED |  |
| C145 | PARTIAL | 3 is the default of a configurable N; narrowed |
| C146 | SUPPORTED |  |
| C149 | SUPPORTED |  |
| C150 | SUPPORTED |  |
| C152 | SUPPORTED |  |
| C153 | SUPPORTED |  |
| C154 | SUPPORTED | kept as stated, with its own low-confidence flag |
| C155 | SUPPORTED |  |
| C156 | SUPPORTED |  |
| C157 | SUPPORTED |  |
| C158 | SUPPORTED |  |
| C159 | SUPPORTED |  |
| C160 | SUPPORTED | throughput reason is in the decision's Почему section |
| C161 | SUPPORTED |  |
| C162 | SUPPORTED |  |
| C163 | SUPPORTED |  |
| C164 | SUPPORTED | matches L1-M7 |
| C165 | SUPPORTED |  |
| C166 | PARTIAL | rests on C133, narrowed to lightcraft; rewritten |
| C201 | SUPPORTED | no CODEOWNERS re-checked: photocraft tree has 0 CODEOWNERS paths |
| C202 | SUPPORTED | autocraft CONTRIBUTING.md re-read: project structure and local dev only |
| C203 | SUPPORTED | 'Read this file first' is two lines below the heading |
| C204 | SUPPORTED |  |
| C205 | SUPPORTED |  |
| C206 | SUPPORTED |  |
| C207 | PARTIAL | quote is photocraft's marker; 'each repo' is contradicted by C229; narrowed to photocraft |
| C208 | SUPPORTED |  |
| C209 | SUPPORTED |  |
| C210 | PARTIAL | workflow also runs on push to main and workflow_dispatch, not only PRs; corrected |
| C211 | SUPPORTED |  |
| C212 | SUPPORTED |  |
| C213 | SUPPORTED |  |
| C214 | SUPPORTED |  |
| C215 | SUPPORTED |  |
| C216 | SUPPORTED |  |
| C217 | SUPPORTED |  |
| C218 | SUPPORTED |  |
| C219 | SUPPORTED |  |
| C220 | PARTIAL | RFC lists the bot as an alternative 'useful later'; 'social, no tooling' is beyond the quote; narrowed |
| C221 | SUPPORTED |  |
| C222 | SUPPORTED |  |
| C223 | PARTIAL | 'No CLA or DCO' is not in the quote (it is C224's); narrowed to craft-anything's statement |
| C224 | PARTIAL | recorded output covers file paths in three trees; CLA bot, sign-off check and craft-contrib not shown; narrowed |
| C225 | SUPPORTED |  |
| C226 | SUPPORTED |  |
| C229 | SUPPORTED |  |
| C230 | PARTIAL | listed workflow kinds were incomplete (sonarcloud, supply-chain in output); rewritten |
| C231 | SUPPORTED |  |
| C232 | SUPPORTED |  |
| C233 | PARTIAL | 'within minutes' shown for #13509 only; 'no welcome message' not in recorded output; narrowed |
| C234 | SUPPORTED |  |
| C235 | SUPPORTED | no later maintainer comment in the thread as fetched 2026-11-19 |
| C236 | SUPPORTED |  |
| C237 | SUPPORTED | approval step (take or take-fix review plus operator's CI approval) is in the same paragraph |
| C238 | SUPPORTED |  |
| C239 | PARTIAL | model-written posts carry 'AI-generated reply', not the maintainer-decision note; narrowed |
| C240 | SUPPORTED |  |
| C241 | SUPPORTED |  |
| C242 | SUPPORTED | open 2026-11-12, merged 2026-11-15 by davidmann4 per PR metadata |
| C243 | SUPPORTED |  |
| C244 | PARTIAL | one PR generalised to newcomers; author's newcomer status not shown; narrowed |
| C245 | PARTIAL | 'a day' not in recorded output; 'first PR' recorded as '1 PR in repo'; narrowed |
| C246 | SUPPORTED |  |
| C248 | UNSUPPORTED | S29 page read: it reports only tldraw auto-closing external PRs; no 'common responses' passage, no Godot; removed |
| C249 | SUPPORTED | issue template names re-checked: bug-report, config, hardware-test, task |
| C250 | SUPPORTED |  |
| C251 | SUPPORTED |  |
| C252 | SUPPORTED |  |
| C253 | SUPPORTED |  |
| C254 | SUPPORTED | S31 is a plan doc; this line is in its who-is-who section |
| C255 | PARTIAL | S31 is a plan (docs/plans/team-workflow.md), not current practice; narrowed to the plan |
| C256 | PARTIAL | Key Decisions is optional ('Skip this section'); Safety Review hint is for driver/ and planning/; corrected |
| C257 | PARTIAL | AGENTS.md also lists Owner Queue Guard and also says Free plan/manual merge; the real gap is four gates vs five (Gitleaks); rewritten |
| C258 | PARTIAL | 'better PR' rule, AI review, draft-first and shared rules source not in named claims; removed |
| C259 | SUPPORTED |  |
| C301 | SUPPORTED |  |
| C302 | SUPPORTED |  |
| C306 | SUPPORTED |  |
| C307 | SUPPORTED |  |
| C309 | SUPPORTED |  |
| C310 | SUPPORTED |  |
| C311 | SUPPORTED |  |
| C313 | SUPPORTED |  |
| C314 | SUPPORTED |  |
| C315 | SUPPORTED |  |
| C316 | SUPPORTED |  |
| C317 | SUPPORTED |  |
| C318 | PARTIAL | quote is the RFC's rollout plan, not a record of what happened; narrowed |
| C320 | SUPPORTED |  |
| C321 | PARTIAL | only photocraft's caller was read; 'app callers' narrowed to photocraft |
| C322 | SUPPORTED |  |
| C323 | SUPPORTED |  |
| C324 | SUPPORTED |  |
| C325 | SUPPORTED |  |
| C326 | PARTIAL | one vectorcraft commit generalised to one PR per repo; narrowed |
| C327 | SUPPORTED | five open copoka sync PRs of 2026-11-17 confirmed by gh search |
| C328 | SUPPORTED |  |
| C329 | SUPPORTED | 16:53:50 to 17:15:21 = 22 min; 'other 19 never got it' rests on C324/C325 |
| C330 | SUPPORTED | #155 opened 2026-11-06, merged 2026-11-13 |
| C331 | SUPPORTED |  |
| C332 | PARTIAL | 'five on day one, hardening paths, ancestry and markers' not in recorded output; removed |
| C333 | PARTIAL | 'the drift that matters... the check does not cover' is the author's framing; narrowed to what the RFC says; re-cited from the PR page [S42] to the RFC file at the PR head [S60] |
| C334 | SUPPORTED | re-cited from the PR page [S42] to the RFC file at the PR head [S60], where the quote is |
| C335 | SUPPORTED | re-cited from the PR page [S42] to the RFC file at the PR head [S60], where the quote is |
| C336 | SUPPORTED | re-cited from the PR page [S42] to the RFC file at the PR head [S60], where the quote is |
| C337 | SUPPORTED |  |
| C338 | PARTIAL | rests on C321, narrowed to photocraft's caller |
| C339 | SUPPORTED |  |
| C340 | SUPPORTED |  |
| C341 | SUPPORTED |  |
| C342 | SUPPORTED | sizes match L3-M6 |
| C343 | SUPPORTED | S44 URL named branch main (404); repo branch is master; read there, URL corrected |
| C344 | SUPPORTED |  |
| C345 | SUPPORTED |  |
| C346 | SUPPORTED |  |
| C347 | SUPPORTED |  |
| C348 | SUPPORTED |  |
| C349 | SUPPORTED |  |
| C350 | SUPPORTED |  |
| C351 | PARTIAL | 'already covered by hooks' not supported by named claims; removed |
| C352 | PARTIAL | C332 shows six commits, not six fixes; narrowed |
| C401 | PARTIAL | trip is 2 of the last 10 pushes turning a check red, not '2 broken checks'; corrected |
| C402 | SUPPORTED |  |
| C403 | SUPPORTED |  |
| C404 | SUPPORTED | 'not GitHub branch-protection' follows from requiredResult filtering only the repo's optional list |
| C405 | SUPPORTED |  |
| C406 | SUPPORTED |  |
| C407 | SUPPORTED |  |
| C408 | SUPPORTED |  |
| C409 | SUPPORTED | commit files include test/push-outcome.test.ts |
| C410 | SUPPORTED |  |
| C411 | SUPPORTED |  |
| C412 | SUPPORTED |  |
| C413 | SUPPORTED |  |
| C414 | SUPPORTED | bare repo and hook are in the Files table of the same section |
| C415 | SUPPORTED |  |
| C416 | SUPPORTED |  |
| C417 | SUPPORTED |  |
| C418 | SUPPORTED |  |
| C419 | SUPPORTED |  |
| C420 | SUPPORTED |  |
| C421 | SUPPORTED |  |
| C422 | SUPPORTED |  |
| C423 | SUPPORTED |  |
| C424 | PARTIAL | recorded output covers four PRs (#6, #9, #12, #13); narrowed |
| C425 | PARTIAL | rests on C424, narrowed to 'no visible trace' |
| C426 | SUPPORTED |  |
| C427 | PARTIAL | PRs #1 and #2 adding Docker Hub and dropping DigitalOcean not in recorded output; removed |
| C428 | SUPPORTED |  |
| C429 | SUPPORTED |  |
| C430 | SUPPORTED |  |
| C431 | SUPPORTED |  |
| C432 | SUPPORTED |  |
| C433 | SUPPORTED |  |
| C434 | SUPPORTED | 'Dead-man alarm' is item 5 of the issue; no comments as of 2026-11-19 |

Label verdict: open — Q4 cannot say whether the breaker ever ran (trip records are operator-local), and Q1's integrator roles and batch-week main health are unresolved; each would change part of the Summary.
Quote check: 132 quoted claim(s): 112 found, 0 NOT FOUND, 20 unfetchable, 0 no source — the 20 unfetchable cite private repos (SergazyNarynov/redrobot, Osasuwu/jarvis-private); all 20 were read through the authenticated GitHub API and found verbatim.

## Disposition

| Recommendation | State | Where |
|---|---|---|
| no sync check | landed | nothing to build: our three repos keep sharing rules through the one user-level import, and no digest check is added |
| fix the three drift items by hand | deferred | unfiled: three small edits (bypass-lane wording across jarvis, music-intel-mcp and redrobot; music-intel-mcp's dead engineering-principles path; redrobot's CI/CD section missing risk-tier and waiting-human-review), offered to the user as one follow-up at the end of this run |
