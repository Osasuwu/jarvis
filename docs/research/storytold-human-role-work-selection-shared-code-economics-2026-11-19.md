---
topic: storytold-human-role-work-selection-shared-code-economics
tags: area:process, research
source_provenance: /research invocation in session b065a837 — sixth run on the storytold ecosystem, after docs/research/artcraft-ecosystem-autocraft-2026-11-18.md and PRs #2235–#2239
status: open
audit: 2026-11-19 — 211 claims: 170 SUPPORTED, 41 PARTIAL, 0 UNSUPPORTED, 0 UNCHECKABLE
---

## Question

The user, verbatim:

"отойдём от CI немного, следующий прогон в другую сторону, грилл ещё держим"

Asked which direction, the user chose all four offered:
- "Human role, escalation" — what storytold maintainers actually do each day, how decisions reach a person (RFCs, owner statements, "not a maintainer decision"), and how much of the work is the human's;
- "What to build" — how agents pick work: parity scorecards against a reference app, roadmaps, menu catalogs as the spec; how "done" is defined for a feature, and how UI is checked visually;
- "Shared code, 20 apps" — craft-libs and craft-common, RFC-0040 "shared libraries first": how common code is factored out and versioned across repos, compared with our jarvis-private, skills and three repos;
- "Fleet economics" — which models run which stages, what an agent PR costs, limits and budgets, and how spend is held down at their volume, compared with our code-gate, /implement and the shadow review in #2233.

Four directions fit one run. The /grill on redrobot's CI rules stays deferred and is not part of this run. Earlier runs this report builds on, as leads only: `docs/research/artcraft-ecosystem-autocraft-2026-11-18.md`, and PRs #2235 (project side), #2236 (reliability, roadmaps), #2237–#2239 (CI baseline, contribution at scale, oracles and supply chain). #2236's roadmap question overlaps Q2; this run takes how a feature is chosen and judged done, not roadmap form.

Sub-questions:
- Q1 — the human role at storytold: what maintainers do, how decisions and escalations reach a person, and what share of the work is human; compared with our orchestrator and owner-escalation model;
- Q2 — how work is selected and judged done: parity scorecards, catalogs and reference apps as the spec, feature "done" criteria, visual UI checks;
- Q3 — how shared code is factored and versioned across ~20 apps, compared with our jarvis-private, skills and repos;
- Q4 — the economics of the agent fleet: models per stage, cost per PR, budgets and limits, compared with ours.



## Summary

**Recommendations, first.** Four candidates come out of this run, and none is a new gate.
1. If #2233's experiment moves code-gate toward an Opus review, take AutoCraft's spend controls with it: an explicit model and effort on the review call, a cap on review calls per PR with a minimum interval, and the CLI's cost recorded per run. Today code-gate sets no model and no turn cap, and nothing limits how often one PR is reviewed [C440], [C451], [C452].
2. Our HIGH-risk hold in jarvis is a label convention, not the role gate. risk-tier passes a HIGH PR on authorship when the author is a non-Bot admin, and every interactive agent commit lands under the one admin login [C155], [C162], [C163]. That is the documented design (#2088), but it should be said plainly where the hold is described, since the deferred /grill on advisory CI leans on what actually holds a merge.
3. Our copies drift with no source stamp. music-intel-mcp's ported `code_gate_verdict.py` has missed at least six jarvis fixes, and the two `test-quality.md` texts are unrelated [C345], [C350]. storytold's answer, a generated block stamped with source commit and hash plus a CI check, fits our copies [C332], [C334], [C364]. Under our "proposing a check" rule this is a candidate: first find out whether the missed fixes matter for music-intel-mcp.
4. The jarvis task form still offers a stale phase list [C246]. It is a small fix.

Nothing on visual UI checks or on work selection is recommended: neither has an incident in our repos, and storytold's own visual practice failed at scale (below).

**Human role and escalation (Q1).** storytold puts people in two places.
- **Decisions on direction.** RFCs merge on a maintainer's approval other than the author's, and owners can overrule [C101], [C103], [C104]. In practice one login merged 17 of 30 craft-contrib PRs and gave 21 of the 30 approvals [C107], [C108].
- **A decision inbox.** Where AutoCraft runs, models read, review, fix up and merge in-rule PRs. A person answers six kinds of question: scope, merge outside the rule, close, duplicate, reference behaviour, and label disagreements [C109], [C111]. Operators' answers count, and so do write-access maintainers' where an operator has switched that on; other maintainers and contributors' own agents (through an MCP server) give display-only feedback [C112], [C114], [C115]. An unanswered question blocks only its own item [C113].

AutoCraft's no-ask merge class is narrow and set by content: a take verdict, size S or M, bugfix or infra, a whitelisted author, green CI, and no README, CI or agent-instruction files [C117], [C118]. Ours is set by risk tier [C144], [C149], [C159].

AutoCraft runs on few apps. Its note appears on 347 of 460 designcraft PRs but 3 of 1,973 photocraft PRs [C136], [C138]. photocraft's and wordcraft's merges are all by personal logins, with CodeRabbit writing about half the reviews [C133], [C135]. Login share overstates human work, though: a human-login comment reads like agent output, and batch PRs go out under personal logins, not a bot [C139], [C140], [C141], [C161].

storytold spreads judgement across several maintainers and roles, while ours puts every owed decision on one person through `/orchestrate`'s packet [C143], [C145], [C146], [C158]. Whether the "UP axis" has freed altitude on jarvis is not shown. Of 41 PRs merged from 2026-10-20 to 11-18, 22 declared HIGH and 18 carried a `waiting-human-review` hold, placed and released under one login, by the user or an agent [C155], [C156], [C160]. The Tier 0/1/2 action gates in our memory are a Q2 design with no code behind them [C151], [C152]. No written account of a storytold maintainer's day was found [C130].

**What to build and when it is done (Q2).** PhotoCraft picks work by measuring its distance from the reference app.
- **Selection.** The order is fixed: infrastructure, then low-hanging parity, then the long tail [C201], [C202]. Agents read a ranked `docs/gaps.md` and a generated scorecard whose measured numbers outrank estimates [C203], [C204].
- **The menu catalog.** A command whose id matches the catalog goes live in the menu, but the catalog's floor has saturated: FLOOR is 663 with 664 of 664 items live [C205], [C228], [C229]. PhotoCraft's own doc says counting surface misled it: about 1,230 issues were filed against features already counted present. It now reports breadth (~76%) and ready-for-real-work (~45%) separately [C207], [C208].
- **"Verified" is manual.** Scorecard statuses are hand-set in TOML with a dated "verified against" note, and the generator checks only format and currency [C225], [C226], [C227].
- **Issues are the spec.** In November one maintainer account opened 1,935 of 3,083 PhotoCraft issues, and 1,905 of the 1,941 with a "Done when" section. No template defines that form, so it likely comes from the maintainer's own tooling [C214], [C215], [C216], [C217]. Claiming was introduced after 172 issues drew fixes from two or more authors [C220], [C221].
- **"Done" in the rules.** For a PhotoCraft tool, done means a command, a UI and tests [C224]. Craft Anything's PR template splits Verified from Not verified [C232], and FilmCraft's done includes a reviewed screenshot [C233].
- **Visual checks.** These are self-review of a rendered PNG plus screenshots in the PR body; 5 of 70 merged PRs carried one [C234], [C235], [C236]. PhotoCraft commits no golden images, though craft-libs has golden screen tests [C237], [C238]. A UI framework port produced an epic of 60 regression issues, at least one found afterwards by side-by-side comparison with the previous release [C239], [C240], [C241], [C242].

Ours: in jarvis, work comes from people and session findings through `/file-issue` and `/to-tickets` with outcome-only acceptance criteria. `/triage` shows what needs attention and leaves the pick to the maintainer, and nothing external generates work [C243], [C244], [C247], [C249]. Our PR template ties each criterion to a red test, command output or reading [C250]. No visual-check rule exists for product UI; redrobot's frontend has no screenshot tests and 3 of 98 merged PRs carried an image [C251], [C252].

**Shared code across ~20 apps (Q3).** storytold shares three things three ways [C360].
- **Code.** It is one Rust workspace of about 115 crates in craft-libs, taken as git dependencies pinned to a commit. There are no tags, releases or crates.io publishing, and every crate is version 0.1.0 [C301], [C302], [C303], [C304], [C305]. All 401 dependency entries across 20 repos pin by `rev` [C310].
  - **What pinning costs.** Pins fragment: up to 18 revisions in one repo, with two or three copies of a crate in a lockfile [C311], [C312]. Bump PRs list the craft-libs changes that alter that app and absorb breaking changes; 49 PRs have craft-libs and pin in the title [C315], [C316], [C318].
  - **RFC-0040, merged 2026-11-17.** It only adds "check craft-libs first" and moves no code [C321], [C323], [C325]. The existing app copies, which have drifted from their crates, wait on RFC-0036, still an open PR, which makes porting the copy's tests the condition for deleting it [C326], [C327], [C329], [C362].
- **Rules.** These are a generated block in each AGENTS.md, stamped with source commit and hash. A shared check fails an edited copy and warns on an older one [C331], [C332], [C334]. Two days after RFC-0040, none of 18 copies had the new rule yet, which is expected lag [C335].
- **CI.** It is called at `@main` [C336].

Ours: skills, agents and hooks ship as the auto-bumped `jarvis` plugin, rules load live through the import stub, and jarvis calls its own lane workflows at one pinned SHA with an advisory drift check [C340], [C341], [C343], [C346], [C347]. Between repos we share only by copy, with no source stamp and no shared package [C348], [C349], [C351], [C352], [C363].

**Fleet economics (Q4).** AutoCraft gives every stage an explicit model and effort.
- **Jev and Haiku** do bulk per-item work without tools.
- **Sonnet** writes patches.
- **Opus**, at effort high, makes every judgement that decides a merge or checks a Sonnet patch. An unsure Sonnet answer goes to Opus, and an unsure Opus answer goes to a person [C403], [C405], [C406], [C408].

AutoCraft says it optimises maintainer attention, not token cost [C402]. It holds spend down by capping throughput:
- per-stage daily limits;
- at most 3 Opus reviews per PR per day, at least 120 minutes apart;
- an outside-author budget of 5 PRs and 5 issues a day;
- a surge breaker;
- a per-repo switch;
- a stable cached prompt prefix.

Cost is recorded per run by stage and model, and dollars are capped only on security scans [C411], [C412], [C413], [C414], [C415], [C417], [C418], [C419], [C420], [C421], [C427]. Calls run on several claude.ai subscription logins chosen by remaining headroom, and contributors' PRs are written on contributors' own agents [C423], [C424], [C426], [C430], [C433]. No public dollar figure was found [C434].

Ours: code-gate runs on a subscription token with no `--model` or `--max-turns`. One sampled run used Sonnet, 5 turns and $0.074 [C440], [C441]. Our only spend controls are skipping cosmetic, draft and untrusted PRs and cancelling superseded runs [C443], [C444]. On both sides the binding budget is plan rate-limit headroom, not dollars [C437], [C438], [C450]. Opus 5.5 costs twice Sonnet 5.5 per token, so most of #2233's ~6x gap is more tokens rather than the model's price — on two PRs [C435], [C436], [C439], [C447].

## Findings

### Q1 — The human role at storytold: what maintainers do, how decisions reach a person, and the human share, against our orchestrator and owner-escalation model — answered with a gap

- **C101** [quoted] Maintainers are the craft-app-team GitHub team; owners are the org admins and also maintainers — "Maintainers are the `craft-app-team` GitHub team. Owners are the storytold org's admins, and are also maintainers." — [S1], bullet 1
- **C102** [quoted] A maintainer starts an RFC's comment period (7 days for adding or removing an app or changing the process, 3 days otherwise) — "A maintainer starts the comment period by commenting its end date" — [S1], bullet 3
- **C103** [quoted] An RFC merges after the period with approval from a maintainer other than the author and no unresolved maintainer objection — "After the period, the RFC merges with approval from a maintainer other than the author, if no maintainer's objection is unresolved." — [S1], bullet 4
- **C104** [quoted] An owner can decide objections or merge/close an RFC early, giving the reason on the PR — "An owner can decide an objection, or merge or close an RFC early, and says why on the PR." — [S1], last bullet
- **C107** [measured] All 30 merged craft-contrib PRs (23 RFC-titled) were merged by 5 logins; one login merged 17 and gave 21 of 30 approvals; the login echelon merged 2 — Own measurements, L1-M8
- **C108** [inference] In practice RFC closure sits with ~3 logins, one doing most approving and merging — from [C101], [C103], [C104], [C107]
- **C109** [quoted] AutoCraft's division of labour: models read, people answer judgement questions — "Models do the reading. People answer the questions that need judgement." — [S2], intro
- **C110** [quoted] AutoCraft covers ~21,000 open items; people answer judgement decisions on a dashboard — "The pipeline sorts the craft apps' open issues and PRs (about 21,000)" / "People answer the decisions that need judgement, on this dashboard." — [S3], intro
- **C111** [quoted] Six question kinds wait for a person: scope, Merge?, Close this PR?, Duplicate?, reference behaviour, classifier label disagreement — "Most work runs without anyone. These questions wait on the Needs you page" — [S2], What needs a person
- **C112** [quoted] Operators settle every question; write-access maintainers only when an operator enables it per repo — "Operators settle every question. Maintainers who have write access to the repo can settle them too, when an operator has switched that on for the repo." — [S2], What needs a person
- **C113** [quoted] An unanswered question blocks only its item — "When nobody answers, the question stays open and only that item waits. Everything else keeps moving." — [S2], What needs a person
- **C114** [quoted] Dashboard roles: operator answers and manages whitelist/repos/access; maintainer gives opinions; viewer reads — "Roles are `operator` (answers decisions, manages the whitelist, repos and access), `maintainer`" — [S4], Dashboard server
- **C115** [quoted] An Inbox MCP server lets contributors work the decision inbox from their own agent; their feedback is display-only until an operator answers — "It lists what the pipeline could not settle on its own and takes feedback back, so a contributor can work the Inbox from the agent they already use" — [S4], Inbox MCP server
- **C117** [quoted] No-ask merge needs a take verdict, size S or M, bugfix or infra type, a whitelisted author, green CI and no conflict with an owner statement — "final review verdict is take (not take-fix)" / "size S or M" / "type is bugfix or infra (tests, CI, docs, build)" / "author is on the whitelist (see Contributors)" / "names a conflict with an owner statement" — [S3], Merge without asking
- **C118** [quoted] Content a person looks at (README, CI/build config, agent instruction files and others) keeps a PR off the auto rule whatever reviews say — "These keep a PR off the rule whatever the reviews say, CI and build PRs included" — [S3], Content a person looks at
- **C119** [quoted] Owner memory: operators' past statements are fed into reviews of related work — "What the operators said once is kept and shown to the reviews of related work." — [S3], Owner memory
- **C120** [quoted] Model-written posts are labelled not a maintainer decision — "`AI-generated review (Opus 5.5). Not a maintainer decision.`" — [S3], Review, Body
- **C121** [quoted] An unsure Opus take never merges without an operator's Merge? answer — "It never merges without an operator's Merge? answer, and the Merge? summary says Opus was unsure." — [S3], Review, Unsure
- **C123** [quoted] Security fixes: an operator starts the scan and every later step — "An operator starts every later step: Land, Advisory and Publish." — [S2], Security deep scan
- **C124** [quoted] Operator pre-approval of a merge exists, so even the non-rule path is an operator act, not an automatic answer — "**Pre-approved** (a pre-approval with a fix-up), **Merge answer** (an operator answered Merge?" — [S3], Merge queue rows
- **C125** [quoted] The human running an agent is accountable and answers its review comments — "The person running the agent reads review comments and answers them, and is accountable for what the agent opens." — [S5], point 9
- **C126** [quoted] Agents stop and ask only about a short list of hard-to-undo actions — "**Stop and ask only about:** licensing outside the allowlist, publishing, releases, pushing to a new remote, secrets, spending money, destructive git" — [S5], Core, 9
- **C127** [quoted] Maintainers resolve disputes and decide PR closure; closure is never automatic — "Maintainers resolve disputed cases and decide closure; closure is never automatic." — [S5], Keep pull requests moving
- **C129** [quoted] In Craft Anything, for maintainer-owned roadmap items, agents may take unclaimed pending changes, but design decisions marked decision wait for a maintainer — "design decisions marked **decision** wait for a maintainer" — [S6], line 18
- **C130** [quoted] The founder's stated split: humans do backend, schema migrations and API design; agents get desktop apps and games — "If you're doing backend work or things that require schema migrations [or] API design, let your humans do that." — [S7], body
- **C133** [measured] photocraft merged 520 PRs in the week; in a 100-PR sample none of the 20 authors is a Bot-typed account and the mergers are personal logins (plus one ghost); 66 merges by one login, 19 and 13 by two more; CodeRabbit wrote 66 of 133 reviews; 131 of 176 comments are by Bot accounts; 30 of 100 PRs had a review from a human-type login — Own measurements, L1-M1
- **C134** [measured] photocraft merges by the main merger are batched: 52 of 66 share a minute with another merge; photocraft "Integration batch" PRs (created Nov 1–18) are authored by that same human login, 11 of 12 hits — Own measurements, L1-M2, L1-M3
- **C135** [measured] wordcraft merged 90 PRs in the week, all by four logins (46, 27, 16, 1); CodeRabbit wrote 192 of 393 reviews; 68 of 90 PRs had a human-type review — Own measurements, L1-M4
- **C136** [measured] AutoCraft is active on few apps: PRs created Nov 1–18 carrying its "Not a maintainer decision" note: photocraft 3 of 1973, wordcraft 2 of 1014, designcraft 347 of 460, deckcraft 244 of 376 — Own measurements, L1-M5
- **C137** [measured] designcraft week: 140 merged; in 100 sampled, autocraft-bot merged 28 and aiongg 4, humans 34 and 30 (two logins); autocraft-bot wrote 71 of 370 reviews, CodeRabbit 147 — Own measurements, L1-M6
- **C138** [measured] autocraft-bot commented on 314 designcraft items since Oct 1 and 0 photocraft items — Own measurements, L1-M9
- **C139** [measured] A designcraft integration-batch PR (#2291) was opened and merged by the login aiongg, not autocraft-bot, and carries AutoCraft's automated-message note — Own measurements, L1-M7
- **C140** [measured] A human-login comment in photocraft (FredApps on #15093, "Post-merge review of `eb758cc2c`... before I posted") reads like agent output, so a human login does not by itself show human-written text — Own measurements, L1-M10
- **C141** [inference] By login, photocraft and wordcraft merges are by personal accounts and about half of reviews are CodeRabbit's; in designcraft autocraft-bot merged 28 of 100 sampled. A login does not show human-written work — from [C133], [C135], [C137], [C139], [C140], [C125]
- **C142** [inference] storytold leaves to humans: RFC acceptance and objections, scope/duplicate/merge-outside-rule/close questions, security publishing, PR closure, design items; everything else (triage, review, fix-up, in-rule merges, batching) runs on models where AutoCraft is on — from [C103], [C111], [C112], [C118], [C123], [C127], [C129]
- **C143** [inference] The human role is distributed: several maintainers merge in each app and roles (operator/maintainer/viewer, contributors' agents via MCP) spread judgement; operators' answers count, and write-access maintainers' where an operator has enabled it — from [C112], [C114], [C115], [C133], [C135], [C137]
- **C144** [quoted] Our merge-gate goal: no human in the merge step unless a gate fires — "No human in the merge step *unless* a gate fires." — [S8], Goal
- **C145** [quoted] /orchestrate: the user keeps only their decisions — "The user keeps only the decisions that are theirs." — [S9], intro
- **C146** [quoted] /orchestrate batches questions into one packet and asks only for the Owed list — "Questions are only for the items *Owed to the user* lists, and they go in the packet." — [S9], invariant 8
- **C147** [quoted] Owed to the user includes HIGH/CRITICAL holds, design forks, irreversible actions, admin-merges — "**HIGH or CRITICAL holds:** approving the head SHA, or releasing `waiting-human-review`." — [S9], Owed to the user
- **C148** [quoted] jarvis risk-tier holds a HIGH+ PR only when its author lacks the releasing role (admin, not a bot) — "a HIGH+ PR whose author lacks the releasing role (admin, not a `Bot` account, not the lane's bot login) stays red until a holder of that role approves the head SHA" — [S10], Merge rules
- **C149** [quoted] redrobot: agent merges LOW/MEDIUM with green verdict and checks; a person merges HIGH/CRITICAL, held, or denylisted paths — "An agent merges a PR itself when its `Risk:` line says LOW or MEDIUM, `code-review/verdict` is green for the head SHA and every check is green. A person merges when risk is HIGH or CRITICAL" — [S11], Merge denylist
- **C150** [quoted] Our stated direction: UP axis, orchestrator layers free the owner's altitude — "UP (orchestrator layers free the owner's altitude)" — [S12], line 12
- **C151** [quoted] The Tier 0/1/2 action-gate model was a Q2 design: Tier 0 executes, Tier 1 queues — "gate() that executes Tier 0, queues Tier 1" — [S13], line 274
- **C152** [measured] No code implements the Tier 0/1/2 gate in jarvis today; matches are only in test fixtures — Own measurements, L1-M12
- **C153** [quoted] needs-human was the AFK lane's escalation label — "applied by an `always()` post-step on any no-PR ending or by the red-check watcher" — [S14], line 152
- **C154** [measured] jarvis 2026-11-10..16: 7 merged PRs, one login merged all, 0 formal reviews — Own measurements, L1-M13
- **C155** [measured] All 41 first-parent commits on jarvis main since 2026-10-20 carry a Claude co-author trailer, all under the one human login — Own measurements, L1-M14
- **C156** [measured] Of 41 jarvis PRs merged 10-20..11-18, 22 declare Risk HIGH, 7 MEDIUM, 12 LOW; 18 carried waiting-human-review, labelled and released by the same login — Own measurements, L1-M15
- **C157** [quoted] The user wants reliability, not strictness, and is weighing advisory CI with autonomous merge and a breaker — "я не хочу строгость, от строгости я как раз хочу уйти. Я хочу reliability." — [S15], body
- **C158** [inference] Ours concentrates every human decision on one principal via a packet; storytold spreads it across several maintainers and a role-gated inbox — from [C143], [C145], [C146], [C154]
- **C159** [inference] Our auto-merge class is by risk tier (LOW/MEDIUM); AutoCraft's is content-based (take, S/M, bugfix/infra, whitelisted author, no README/CI/agent files, no owner-statement conflict) — from [C117], [C118], [C149], [C144]
- **C160** [inference] On jarvis, 22 of 41 recent PRs declared HIGH and 18 carried a waiting-human-review hold, placed and released under the user's login (by the user or an agent is not shown); in AutoCraft's design an unanswered question stalls only its item — from [C150], [C156], [C113]
- **C161** [inference] Login-based human share cannot be measured in either org: agents act under human tokens in both — from [C140], [C139], [C155], [C156]
- **C162** [inference] Under our admin login, risk-tier's role check is passed by authorship, so HIGH holds in jarvis rest on the label convention, not on the role gate — from [C148], [C155], [C156], [C163]
- **C163** [quoted] risk-tier lets a HIGH or CRITICAL PR pass on authorship alone when the author is a non-Bot admin — "HIGH and CRITICAL → green when **the PR's author holds the releasing role (admin)** (#2088)" — [S16], step 4
### Q2 — How work is selected and judged done: parity scorecards, catalogs and reference apps as the spec, done criteria, visual UI checks — answered with a gap

- **C201** [quoted] PhotoCraft fixes its target as 1:1 parity with the reference app (menus, shortcuts, behaviour, file fidelity) — "The goal is 1:1 Photoshop parity (same menus, shortcuts, behaviour and file fidelity) with better performance, and every feature drivable by agents." — [S17], intro paragraph
- **C202** [quoted] PhotoCraft's work-picking order is fixed: infrastructure, then low-hanging parity, then the long tail — "Priorities: important infrastructure first, then low-hanging parity, then the long tail." — [S17], §4 Picking work
- **C203** [quoted] The generated scorecard is read before picking work and its measured numbers outrank estimates — "Its numbers are measured; prefer them to estimates." — [S17], §4 step 1
- **C204** [quoted] gaps.md is the ranked work list; agents take the highest-ranked unclaimed entry and update its evidence when closing part of it — "This is the work list agents pick from: take the highest-ranked entry that nobody is working on" — [S18], intro
- **C205** [quoted] Using the exact id from the menu catalog makes a command's menu item go live automatically — "Use the **exact id from `crates/ui-egui/src/menu_catalog.rs`** and the menu item goes live automatically." — [S17], §3 rule 1
- **C206** [quoted] The menu-wiring checklist is explicitly not a measure of behaviour — "`docs/parity-checklist.md` (menu wiring) is not a measure of behaviour." — [S17], §4 step 0
- **C207** [quoted] Counting feature surface badly overstated done-ness: ~1,230 issues were filed mostly against features already counted present — "about 1,230 issues have been filed since the first release (579 open on 2026-10-10), most of them against features already counted as present." — [S19], Headline, para after table
- **C208** [quoted] PhotoCraft's headline table reports feature breadth (~76%) separately from ready-for-real-work (~45%), alongside other estimates and agent-hour estimates to beta — "**Ready for real work** (could a professional replace Photoshop with it?) | **~45%** (range 40–50%)" — [S19], Headline table
- **C209** [quoted] FilmCraft makes the two-number split a reporting rule: an approximation or stub never counts as done, and no percentage rises without rerunnable evidence — "count an approximation, a stub or a partly wired setting as such, never as done" — [S20], §7 Reporting progress honestly
- **C210** [measured] Parity docs are an org-wide pattern: 109 Markdown files with "parity" in the path across 14 storytold repos; a generated scorecard.md exists only in photocraft; a `pub const FLOOR` parity floor only in photocraft and texturecraft — Own measurements, L2-M9
- **C211** [quoted] Craft Anything's work comes only from its roadmap, in dependency order, and items marked decision wait for a maintainer — "Pick work from `docs/ROADMAP.md` only. Don't start an item that is claimed, `blocked`, or waiting on a **decision**" — [S21], Before you write code
- **C213** [quoted] Craft Anything's product judges a rebuild against the observed original and lists mismatches (Study, Build, Check, Ready) — "**Check:** compare the build with the original and list what doesn't match yet." — [S22], How it works, step 3
- **C214** [measured] PhotoCraft issue volume is extreme and concentrated: 3,083 issues created 2026-11-01..18; 1,935 (63%) by one maintainer account, davidmann4; 1,332 carry the `parity` label — Own measurements, L2-M6
- **C215** [measured] The issue body is a de facto spec form: 1,941 of 3,083 November issues contain "Done when" in the body, 1,905 of them by davidmann4; only 36 by anyone else — Own measurements, L2-M6
- **C216** [measured] No issue template defines that form: photocraft has no .github/ISSUE_TEMPLATE or PR template, and an org code search for "Done when" + "Reference application" finds only a test file — Own measurements, L2-M1, L2-M14
- **C217** [inference] The "Done when" issues are likely produced by the maintainer's own tooling (≈107/day from one account), not by a published template; house rule 15 forbids agent attribution, so authorship by agent cannot be confirmed from the issues — from [C214], [C215], [C216], [C222]
- **C218** [quoted] A maintainer issue states reference-app behaviour as the spec and a "Done when" list that includes a test — "## Reference application\nThe dialog shows the current gradient (its name, or the strip) so the user can see which map is applied" — [S23], body
- **C219** [quoted] The same issue's done criteria name the observable result and require a test that exercises it — "A test opens the dialog and checks the preset row's label and text, and adds a stop." — [S23], ## Done when
- **C220** [quoted] Epics carry a pick-up protocol: check free, claim on the item issue, draft PR within a day, release if stopping — "Comment `Claiming this` with your GitHub name and where the fix goes" — [S24], How to pick up an item, step 2
- **C221** [quoted] RFC-0003 was motivated by measured duplicate work: 172 issues with fixing PRs from two or more authors, 148 of those PRs closed unmerged — "storytold/photocraft#3561 counted **172 issues** with fixing PRs from two or more authors, and **148** of those PRs closed unmerged" — [S25], Motivation
- **C222** [quoted] House rules forbid saying an agent wrote a PR — "**No agent attribution.** A pull request does not say an agent wrote it." — [S17], house rule 15
- **C224** [quoted] PhotoCraft scorecard checklist definition of done for tools: a command, a UI and tests — "# An item is done when it has a command, a UI and tests." — [S26], header line 2
- **C225** [quoted] Scorecard statuses are hand-set in TOML and were verified against a named commit on a date — "# Statuses must be true on main. Verified against 4b53f62 on 2026-10-05." — [S26], header line 3
- **C226** [measured] The scorecard generator validates only format (id, target, no pipe, no duplicate ids) and that the committed file is current; it does not check a done row's evidence against the code — Own measurements, L2-M3
- **C227** [quoted] Yet the generated scorecard claims its checklist statuses are verified against the code — "Checklist statuses are verified against the code; numbers here supersede estimates elsewhere." — [S27], intro
- **C228** [quoted] The parity floor is a test: live catalog items must not fall below FLOOR — "assert!(p.live >= FLOOR, \"menu parity regressed: {} live < floor {FLOOR}\", p.live);" — [S28], tests::parity_does_not_regress
- **C229** [measured] The floor is saturated: FLOOR = 663 while the scorecard reports 664 of 664 menu items live, so the floor now only guards against a drop below 663 wiring entries — Own measurements, L2-M2
- **C230** [measured] AGENTS.md points at a parity file that does not exist (`crates/ui-egui/src/parity.rs`); the file lives at `crates/ui-egui/src/menus/parity.rs` — Own measurements, L2-M1
- **C231** [quoted] Craft Anything's "Done means" puts docs, roadmap tick and an honest verified/not-verified report in the same PR — "Report what you verified and what you didn't. Never claim a live run you didn't do." — [S21], Done means
- **C232** [quoted] Craft Anything's PR template has separate Verified and Not verified fields — "**Not verified:** <!-- what you couldn't try, so the docs and STATUS say so -->" — [S29], body
- **C233** [quoted] FilmCraft's definition of done includes driving the feature through the control channel and reviewing a screenshot — "you have driven it through the control channel and reviewed a screenshot;" — [S20], §7 Definition of Done
- **C234** [quoted] PhotoCraft's rule for UI changes is agent self-review of a rendered PNG, offscreen or via the control channel — "Render offscreen with `cargo run -p photocraft-ui-egui --example snapshot` (no window, no focus stealing), or launch with `--control` and take `ui.screenshot`. Look at the PNG." — [S17], §3 rule 6
- **C235** [quoted] Before/after screenshots belong in the PR description, not the repo — "Screenshots that show a PR's change (before/after evidence) go in the PR description, never in the repo" — [S17], §3 rule 6
- **C236** [measured] Few PhotoCraft PRs carry screenshots: of 70 recently merged PhotoCraft PRs, 5 have an image in the body; in 1,052 PRs merged 2026-11-01..18, 141 mention "screenshot" anywhere — Own measurements, L2-M4, L2-M5
- **C237** [measured] PhotoCraft has egui_kittest with the snapshot feature as a dev-dependency but commits no golden snapshot PNGs and has no `.snapshot(` call; craft-libs commits 6 golden PNGs for its multilingual screen tests; texturecraft's UI snapshots are `--ignored` and write to a directory — Own measurements, L2-M10
- **C238** [quoted] craft-libs screen tests compare each language's render with a committed PNG and need a human review when regenerated — "Run with `UPDATE_SNAPSHOTS=1` to\n    /// write new snapshots; review them before committing." — [S30], Screens::snapshots doc
- **C239** [quoted] A UI framework port (#15449) produced an epic collecting what behaves worse since the port — "This epic collects what behaves worse since then." — [S24], intro
- **C240** [quoted] At least one issue in that epic (#15559) was found by comparing with the previous release under fixed conditions — "Compared side by side with the 0.23.1 release (before #15449) under the same conditions." — [S23], What happens today
- **C241** [measured] Epic #15476 lists 60 issue rows — Own measurements, L2-M8
- **C242** [inference] Rendered-PNG self-review plus optional PR screenshots did not catch layout regressions at port scale; no golden-image gate exists in PhotoCraft CI to catch them — from [C234], [C236], [C237], [C239], [C241]
- **C243** [quoted] Our /triage presents issues needing attention as counts and one-line summaries and leaves the pick to the maintainer — "Show counts and a one-line summary per issue. Let the maintainer pick." — [S31], line 79 (jarvis-private 970774e)
- **C244** [quoted] Our /file-issue demands literally verifiable acceptance criteria that state outcomes and do not prescribe tests — "Each states an observable outcome; none prescribes\n   tests" — [S32], step 4
- **C245** [quoted] /to-tickets makes an exploratory slice's AFK eligibility depend on a machine-checkable oracle, golden run among them — "a slice is **AFK-eligible if and only if its criterion has an objective, machine-checkable oracle**" — [S33], §3a, line 73
- **C246** [quoted] Our jarvis task form still offers a stale phase list and generic default acceptance criteria — "- \"P1 OpenClaw Migration + PM Skills\"" — [S34], phase dropdown (d5c93cd7)
- **C247** [measured] jarvis issue rate and form: 21 issues created 2026-11-01..18 (vs 3,083 in PhotoCraft); all 43 most recent by Osasuwu; 41 of them have an "Acceptance criteria" heading — Own measurements, L2-M11
- **C248** [quoted] Our /implement starts with an already-done audit of each acceptance criterion — "**Already-done audit first.** Grep each acceptance criterion's symbols and read the hits." — [S35], line 94
- **C249** [inference] jarvis has no measured external spec (reference app, catalog, scorecard) that generates work; its work comes from humans and session findings via /file-issue and /to-tickets, each with its own AC; redrobot's work source was not measured — from [C243], [C244], [C247], [C251]
- **C250** [quoted] Our PR template ties each acceptance criterion to a test that goes red, a command output, or reading — "Each acceptance criterion: the test that goes red for it, a command's output, or\n    (one-off static facts only) reading." — [S36], ## Testing comment
- **C251** [measured] redrobot has a frontend (77 files under frontend/src) but no UI snapshot or screenshot test in the tree; its golden tests are for leveling and a sandbox replay; its PR template asks for before/after screenshots in a comment; 3 of 98 recent merged PRs carry an image-like token — Own measurements, L2-M12
- **C252** [measured] jarvis-private skills and references contain no visual-check rule for UI work; the only visual rule is the user-level CLAUDE.md line on subagent-rendered widgets; 0 of 90 recent jarvis merged PRs carry an image — Own measurements, L2-M11, L2-M13
- **C253** [quoted] The user-level rule for visual work is self-check of the rendered result by a subagent — "Visual work (widgets, Figma, Mermaid) runs in a subagent that keeps its source in a file and checks the rendered result, dark mode included" — [S37], Session habits
### Q3 — How shared code is factored and versioned across ~20 apps, against our plugin, rules and copied files — answered with a gap

- **C301** [quoted] craft-libs is one Rust monorepo workspace of libraries that any Craft app may include — "It's a Rust monorepo workspace, and the libraries can be included by any Craft Apps that need them." — [S38], intro
- **C302** [quoted] A craft-libs README (on the repo's `HEAD` branch, not `main`) documents a git dependency pinned to a commit, not a registry version — "craft-<name> = { git = "https://github.com/storytold/craft-libs", rev = "<commit>" }" — [S38], Layout
- **C303** [quoted] Every crate inherits one workspace version, 0.1.0, so the version field carries no compatibility signal — "version = "0.1.0"" — [S39], workspace.package
- **C304** [measured] craft-libs has no GitHub releases and no tags; 115 crate directories, 108 crates listed in the README, 8 vendored crates — Own measurements, L3-M1
- **C305** [measured] storytold does not publish craft-libs crates to crates.io: craft-pdf and craft-xml do not exist there; a craft-atomic 1.4.7 exists but names a different GitHub owner's craft-libs as its repository — Own measurements, L3-M2
- **C306** [quoted] A crate in craft-libs must serve more than one app and must not depend on any app — "**No app code.** A crate here must be useful to more than one app and must not depend on any app." — [S40], AGENTS.md body
- **C307** [quoted] A crate that outgrows the suite may be split out into its own library later — "If any libraries grow beyond Craft App usage, eg. RAW format support, they may be promoted out and into their own libraries" — [S38], intro
- **C308** [measured] Much of craft-libs was carved out of apps: the README credits a source app 43 times (PhotoCraft 9, MailCraft 6, LightCraft 6, FilmCraft 6, EffectCraft 4, others) — Own measurements, L3-M6
- **C309** [quoted] For craft-aep, mapping onto an app's document stays in the app — "Clean room, from EffectCraft. Mapping onto an app's document stays in the app." — [S38], craft-aep entry
- **C310** [measured] Across 20 consumer repos, all 401 non-comment craft-libs dependency entries are pinned by `rev`; none by branch, tag or bare git — Own measurements, L3-M3
- **C311** [measured] Pins are fragmented within repos: the most fragmented repo holds 18 distinct craft-libs revs, the next 17 and 11; six repos hold one — Own measurements, L3-M3
- **C312** [quoted] Fragmented pins put two or three copies of the same shared crate into an app's lockfile — "They were pinned at fifteen different commits, so `Cargo.lock` held two or three copies of `craft-audio`, `craft-media`" — [S41], PR body
- **C313** [quoted] AniCraft's pins sat at nine commits; consolidating forced a code change because Cargo rejects one package named twice — "On `main` they are pinned at nine different commits" — [S42], PR body
- **C314** [quoted] A pin bump can be held back for a crate whose new revision changes a file format released builds cannot read — "At `453b0da7` it writes project schema 18, and released builds do not open schema 18 projects." — [S41], PR body
- **C315** [quoted] A pin-bump PR (filmcraft#4917, open) lists the merged craft-libs PRs that change what FilmCraft does — "Merged craft-libs pull requests this brings in that change what FilmCraft does:" — [S41], PR body
- **C316** [quoted] A shared-crate behaviour change reaches an app as a required local fix in the bump PR — "storytold/craft-libs#1729 makes the shared DOCX reader keep a `relativeHeight` of 0 as the lowest stacking order." — [S43], Change needed in this repository
- **C317** [quoted] A single bump moves the whole set of shared packages at once — "All 42 craft-libs packages in `Cargo.lock` move." — [S43], PR body
- **C318** [measured] 49 PRs in the org have craft-libs and pin in the title — Own measurements, L3-M5
- **C319** [measured] Dependabot runs on apps with a grouped cargo config, but the sampled Dependabot cargo PR (deckcraft#2077) does not mention craft-libs: git-rev pins are outside its updates in that sample — Own measurements, L3-M5
- **C320** [quoted] Code moving into craft-libs strands open app PRs, which must be redone against the shared crate — "`crates/cms/src/lutfile.rs` was deleted from this repo when colour management moved to craft-cms in https://github.com/storytold/craft-libs, so this change belongs in a craft-libs PR now." — [S44], comment
- **C321** [quoted] RFC-0040 adds one house rule: check craft-libs first, reuse or extend it, keep app policy local — "before implementing reusable formats, codecs, protocols or UI, check craft-libs and relevant open work, then reuse or extend the shared API instead of keeping another app-local implementation." — [S45], Summary
- **C322** [quoted] Its stated motive is drift between per-app guidance paragraphs — "Separate guidance paragraphs in app AGENTS.md files can drift or contradict existing rules." — [S45], Motivation
- **C323** [quoted] RFC-0040 changes guidance only; it moves no code and no pins — "This changes contributor guidance, not application code or dependency pins." — [S45], Decision
- **C324** [quoted] Rule 16 bars depending on sibling app crates and keeps platform/licence rules — "This does not authorize dependencies on sibling application crates or override existing platform, licensing or dependency-source requirements." — [S46], rule 16
- **C325** [measured] RFC-0040 merged 2026-11-17 (craft-contrib 937c37449f) — Own measurements, L3-M4
- **C326** [quoted] RFC-0036, an open (unmerged, not GitHub-draft) PR, records that apps still keep runtime copies of code craft-libs already holds — "The Craft apps keep their own copies of runtime code that a craft-libs crate already holds" — [S47], rfcs/0036, intro
- **C327** [quoted] The copies have diverged from their crates in behaviour — "the copies differ from their crates in permissions, retries, folder lists and dialog behavior." — [S47], rfcs/0036, intro
- **C328** [quoted] Concretely, atomic-write copies differ in safety-relevant details — "The copies of a temporary-file, flush and rename write differ in Windows retries, symlink handling, permissions and folder sync." — [S47], rfcs/0036, craft-atomic note
- **C329** [quoted] The proposed move requires porting the copy's tests into the crate before deleting the copy — "Before a copy is deleted, every test case the crate lacks is ported to the crate." — [S47], rfcs/0036, Summary
- **C331** [quoted] The house rules exist once, in craft-contrib; copies must not be edited — "The source is `standards/house-rules-core.md` in `storytold/craft-contrib`. Propose changes there, not in a copy." — [S46], header
- **C332** [quoted] Each repo's AGENTS.md holds the rules as a generated block stamped with the source commit and a hash — "<!-- craft-house-rules:start core source=dde09ea31e2e457f5b4653a6e76f7cdf55944bdf sha256=540e6cea" — [S40], line 1
- **C333** [quoted] RFC-0040's rollout regenerates each app's block with a tool and forbids hand edits — "regenerate each app's applicable shared blocks from the merged source revision using the existing house-rules tool. Do not hand-edit generated blocks" — [S45], Rollout
- **C334** [quoted] A shared CI check fails an edited copy but only warns on an intact older one — "An intact older copy warns only when its normalized standards file changed on main, and does not fail." — [S48], header comment
- **C335** [measured] Two days after RFC-0040 merged, none of 18 repos with a house-rules block carries rule 16; 17 stamp source dde09ea31e, pdfcraft 1315c63e17 — Own measurements, L3-M4
- **C336** [quoted] Shared CI is called at @main, not pinned (contrast with libs pinned by rev) — "uses: storytold/craft-common-actions/.github/workflows/house-rules.yml@main" — [S49], jobs
- **C337** [measured] 32 PRs with "house rules" in the title were opened in the org since 2026-11-01 — Own measurements, L3-M5
- **C340** [quoted] Our skills, agents and hooks ship as a versioned plugin; only a version bump reaches devices — "the plugin pins `version`, so only a bump is an update" — [S50], line 22 (private; local checkout)
- **C341** [quoted] The bump is automatic: CI commits the next patch to master after a merge touching plugin files — "PRs do not bump it: after a merge that changes `skills/`, `agents/`, `hooks/` or `plugin.json`, CI (`plugin-version`) commits the next patch to `master`" — [S50], line 22 (private; local checkout)
- **C342** [measured] The plugin is at 1.6.42; the cache keeps 14 versions; plugin.json changed in 41 commits between 2026-10-17 and 2026-11-10 — Own measurements, L3-M7
- **C343** [quoted] Rules (CLAUDE.md, SOUL.md, reference/) are not in the plugin; they load live from the marketplace checkout via an import stub — "Rules (CLAUDE.md, SOUL.md, reference/) load via the ~/.claude/CLAUDE.md import stub, not the plugin." — [S51], description (private)
- **C344** [quoted] The test-quality rule is deliberately copied per repo because headless workers lack the user-level layer — "each repo with a headless lane carries its own short copy" — [S52], header (private)
- **C345** [measured] jarvis's copy of test-quality.md and the jarvis-private original are separate texts (line similarity 0.18; 161 vs 199 lines) with no source stamp — Own measurements, L3-M9
- **C346** [measured] jarvis exposes three reusable workflows and calls them, plus the risk-tier action, at one pinned SHA (2d4b5aeb) from four of its own workflows — Own measurements, L3-M8
- **C347** [quoted] A fix to pinned lane code does not run until the pin is bumped by hand; an advisory drift check reports it — "A fix to that code merges green but does not run until the pin is bumped by hand." — [S53], header
- **C348** [measured] music-intel-mcp calls no jarvis workflow; it carries ported copies: 6 workflows share names with jarvis (1 identical) and 3 scripts (2 identical) — Own measurements, L3-M9
- **C349** [quoted] The ports say where they came from, by issue, not by commit — "Design: Osasuwu/jarvis#1964, ported in #226." — [S54], header
- **C350** [measured] The ported code_gate_verdict.py has drifted: last changed in music-intel-mcp 2026-10-16, while jarvis's copy took at least six later commits (e.g. #2085 red-check fix, the daily sweep: 8 mentions of sweep vs 0) — Own measurements, L3-M10
- **C351** [quoted] One shared Python helper is kept byte-identical, with lint exemptions to preserve that — "Kept byte-identical to Osasuwu/jarvis's copy (jarvis#1981 AC4), whose lint does not select SIM." — [S55], tool.ruff per-file-ignores
- **C352** [measured] No Python package is shared: music-intel-mcp's pyproject has no jarvis dependency; sharing is by copy — Own measurements, L3-M12
- **C353** [measured] redrobot's 17 workflows neither call nor cite jarvis workflows on its default branch — Own measurements, L3-M11
- **C360** [inference] storytold shares three things three ways: format/codec code as a library pinned by commit, rules as generated stamped copies with a CI integrity check, CI as reusable workflows at @main — from [C302], [C310], [C332], [C334], [C336]
- **C361** [inference] The rev-pin model costs storytold fragmentation (up to 18 revs per repo, duplicate crates in lockfiles) and bump PRs that list behaviour changes per consumer and absorb breaking changes; no semver or release signals compatibility — from [C303], [C304], [C311], [C312], [C315], [C316], [C318]
- **C362** [inference] RFC-0040 is a rule against new duplication; the existing duplication is a separate, still-open migration (RFC-0036) with test-porting as the gate — from [C321], [C323], [C326], [C329]
- **C363** [inference] Our closest analogue to craft-libs is the plugin (versioned, auto-bumped, one consumer: the devices); our cross-repo code sharing is by copy without a source stamp, which is where drift already shows — from [C341], [C345], [C348], [C350], [C352]
- **C364** [inference] The transferable piece is storytold's stamped generated block plus integrity check (source commit + hash), which ties a copy to its source; it fits our copies (test-quality.md, ported gate scripts) — from [C332], [C334], [C350], [C351]
### Q4 — The economics of the agent fleet: models per stage, cost controls and who pays, against our code-gate and model routing — answered with a gap

- **C401** [quoted] AutoCraft runs a pipeline of model steps using Jev (a TypeSafe classifier) plus Claude Haiku, Sonnet and Opus — "Jev classifiers and Claude Haiku, Sonnet and Opus classify, prioritise, find duplicates, ask maintainers for decisions, review, write fixes, verify and merge." — [S56], intro, line 3
- **C402** [quoted] AutoCraft says its design optimises maintainer attention, not token cost — "The pipeline is built around maintainers' judgement, which is the limited resource, not around token cost." — [S56], intro, line 5
- **C403** [quoted] Every Claude prompt carries an explicit effort level passed as --effort, independent of the account's settings — "Passed as --effort so the level never depends on the account's own settings." — [S57], type ClaudePrompt, line 78
- **C404** [quoted] A prompt lists the models it may be sent to, the first being the default — "Models the prompt may be sent to; the first is the default." — [S57], type Common, line 57
- **C405** [measured] Per prompt: Opus effort high on review (20 turns), pre-merge (40), post-merge, fix-up check, fix check, PR-dupe compare, conversation (20 each) and security (30-60); Sonnet writes code: fixup.patch (medium, 20), cifix.patch, fixissue.patch (high, 20-30), conflicts (high, 20), verify plan (medium, 20); Haiku (medium/low, no tools) and Jev do classify, priority, dupes, areas, lint; referee Sonnet then Opus; decide.prepare Opus by default — Own measurements, L4-M1
- **C406** [inference] storytold's split is: cheap models (Jev, Haiku) on per-item bulk work, Sonnet for writing patches, and Opus for every judgement that decides a merge or checks a patch Sonnet wrote — from [C405], [C412]
- **C408** [quoted] Referee escalation: an unsure Sonnet answer goes to Opus, and an unsure Opus answer goes to a person — "an unsure Sonnet answer goes to Opus with the same prompt, and an unsure Opus answer keeps its label and goes to a person as a scope question." — [S57], referee.sonnet purpose, line 122
- **C409** [quoted] When Jev is off or out of credit, Haiku does Jev's work through the Claude accounts — "when its account is out of credit or its key is rejected, Haiku does Jev's work through the Claude accounts" — [S56], Requirements table, line 58
- **C411** [quoted] Daily limits count items per stage per UTC day, failed jobs included; empty is unlimited and 0 pauses the stage — "Limits count items handled per stage per day (from 00:00 UTC), including by failed or stopped jobs." / "Empty means no limit; 0 pauses the stage." — [S58], ### Daily limits
- **C412** [quoted] Default daily limits on a new database include Review (Opus) 40, Fix 10, Merge 10, Decide 100 — "| Review (Opus) | 40 | Act | 20 |" / "| Embed | none | Fix | 10 |" / "| Decide | 100 | Merge | 10 |" — [S58], Daily limits table (generated)
- **C413** [quoted] Per-PR Opus cap: at most 3 Opus review calls per PR per UTC day, counting re-runs and failures — "Cap: at most 3 Opus calls per PR per UTC day, counting new heads, re-runs, and failed calls" — [S58], ## Review, line 193
- **C414** [quoted] Minimum interval between Opus reviews of one PR, default 120 minutes — "Interval: setting `review_min_interval_minutes` (default 120, 0 turns it off" — [S58], ## Review, line 193
- **C415** [quoted] Outside authors get a daily budget: only their first 5 PRs and 5 issues per 24 h get model work — "only the first `outside_prs_per_day` PRs (default 5) and the first `outside_issues_per_day` issues (default 5) get model work" — [S58], ### Outside authors
- **C416** [quoted] The stated purpose of the outside-author limits is protecting model spend from PR floods — "Two protections keep an author outside the team from using up model spend, for example by opening hundreds of PRs." — [S58], ### Outside authors
- **C417** [quoted] A surge breaker trips at more than 30 new outside items per hour and holds them until an operator resumes, no timer — "More than `outside_surge_per_hour` (default 30) new outside-author items in the last hour trips the breaker `outside-surge`." — [S58], ### Outside authors
- **C418** [quoted] A per-repo Pipeline switch: a new repo starts off, and off means sync only — "A newly tracked repo starts off. Off means sync only" — [S58], Pipeline switch per repo, line 677
- **C419** [quoted] Security deep scans carry a dollar spend cap checked before every call, with an expected $2 for the threat model — "Before every call (and again before the repeat of an unreadable one) the scan stops as `capped` when the cost so far plus the call's expected cost would pass the cap. The expected cost is $2 for the threat model" — [S58], Spend cap, line 453
- **C420** [quoted] Prompts keep a stable prefix so the model reads it from cache at a fraction of the cost; a prompt is cached once per account — "The model reads a repeated start of a prompt from its cache at a fraction of the cost, so every call keeps its start identical." — [S58], Stable prompt prefix, line 507
- **C421** [quoted] Token use and CLI-reported dollar cost are recorded per agent run, by stage, model and repo — "cost_usd REAL,                      -- as reported by the CLI; Jev: input tokens at TypeSafe's price" — [S59], table token_usage, line 126
- **C422** [quoted] The dashboard's Cost page shows what each stage costs — "Classifiers and Cost show how often the models agree and what each stage costs." — [S58], line 511
- **C423** [quoted] Calls are spread over several logged-in Claude accounts; before each call the runner picks one under the 5-hour and weekly pause levels (default 80%), preferring the lowest weekly use, else the call waits — "Before each call, the runner picks an enabled account with a free slot and headroom (5-hour and weekly use under the pause levels, which operators set; default 80 % for both" — [S58], ## Claude accounts and agent runs
- **C424** [quoted] Accounts sign in with the claude.ai subscription flow — "*Sign in* runs `claude auth login --claudeai` for that account's config directory" — [S58], ## Claude accounts and agent runs
- **C425** [quoted] When accounts lack headroom, the waiting queue gives freed slots first to security, then to path-to-merge work, then the rest — "A freed slot goes to the waiter with the highest priority class (2 security, 1 path to merge" — [S58], ## Claude accounts and agent runs
- **C426** [measured] AutoCraft's README, operations.md and pipeline.md never mention ANTHROPIC_API_KEY: the pipeline is wired for subscription logins, not metered API keys — Own measurements, L4-M2
- **C427** [inference] AutoCraft holds spend down by capping throughput (per-stage daily limits, per-PR review cap and interval, outside-author budget, surge breaker, per-repo switch, account headroom), not by cheaper judgement models; dollars are recorded but capped only on security scans — from [C402], [C411], [C413], [C414], [C415], [C417], [C418], [C419], [C421], [C423]
- **C428** [quoted] storytold's coding-agent RFC: the person running an agent is accountable for what it opens — "The person running the agent reads review comments and answers them, and is accountable for what the agent opens." — [S60], rule 9
- **C429** [quoted] photocraft's agent rules list spending money among the few things an agent must stop and ask about — "**Stop and ask only about** licensing outside the allowlist, publishing, releases, a new remote, secrets, spending money, destructive git, and anything else hard to undo." — [S61], rule 9
- **C430** [quoted] HN user echelon, in a thread on PhotoCraft, wrote of letting the "community token spend" diffuse into the products — "Let the community token spend have time to diffuse into the products. This effort needs a community to climb the quality and parity gradients." — [S62], comment 2026-10-06 (via HN Algolia API)
- **C432** [quoted] Same maintainer moves work to open-weight models when Anthropic limits usage: planning with Claude, implementation with Kimi — "Every time Anthropic limits what we can do, I start switching more of my process to open weights. Planning with Claude, implementation with Kimi." — [S63], comment 2026-11-01 (via HN Algolia API)
- **C433** [inference] Contributor PRs are written on the contributors' own agents; the outside-author budget exists to keep such authors from using up AutoCraft's model spend — from [C415], [C416], [C428], [C430]
- **C434** [measured] No public dollar figure for storytold's fleet was found in web search, HN (photocraft, autocraft, maintainer comments on Claude/tokens) or the AutoCraft docs — Own measurements, L4-M3
- **C435** [quoted] List API price of Opus 5.5: $4 input, $20 output per MTok — "| Claude Opus 5.5 | $4 / MTok | $5 / MTok | $8 / MTok | $0.20 / MTok<sup>2</sup> | $20 / MTok |" — [S64], model pricing table
- **C436** [quoted] Sonnet 5.5 row: $2 input, $10 output per MTok — "| Claude Sonnet 5.5 | $2 / MTok | $2.50 / MTok | $4 / MTok | $0.10 / MTok<sup>2</sup> | $10 / MTok |" — [S64], model pricing table
- **C437** [quoted] claude -p and Agent SDK usage still draw from subscription limits — "For now, nothing has changed: Claude Agent SDK, claude -p, and third-party app usage still draw from your subscription limits." — [S65], banner
- **C438** [quoted] Max/Ultra/Team monthly API credits do not cover Claude Code — "| **Doesn’t cover** | Claude Code, extra usage in the Claude apps                               |" — [S66], summary table
- **C439** [inference] Opus 5.5 costs 2x Sonnet 5.5 per token at list price, so the ~6x gap in #2233 ($0.80 vs $0.13) implies roughly 3x the tokens; which of turns, effort or format drives it is not shown, and it rests on two PRs — from [C435], [C436], [C447]
- **C440** [measured] code-gate (Code Review workflow) in jarvis, redrobot and music-intel-mcp authenticates with a subscription OAuth token and sets neither --model nor --max-turns — Own measurements, L4-M4
- **C441** [measured] One reviewed jarvis code-gate run (PR #2234) ran claude-sonnet-5-5, 5 turns, CLI-reported $0.074 — Own measurements, L4-M5
- **C442** [measured] 7-day Code Review run counts from 2026-11-12: jarvis 76 runs (53 success, 19 skipped, 4 cancelled) over 28 head branches; music-intel-mcp 21 over 8; redrobot at least 300 (list limit hit) over 54 branches — Own measurements, L4-M6
- **C443** [measured] code-gate skips the model for drafts, cosmetic-only diffs, incomplete file lists and untrusted authors; 5 of the 6 newest successful jarvis runs were cosmetic skips — Own measurements, L4-M7
- **C444** [quoted] code-gate cancels an in-progress review when a new push arrives for the same PR — "cancel-in-progress: true" — [S67], concurrency, line 50
- **C445** [measured] Our model routing: plan-review planner floor claude-opus-5, critics claude-sonnet-5; /orchestrate gives workers a Sonnet id only for mechanical work and otherwise inherits the PM's model; HIGH diffs get a fresh opus review; the AFK lane caller pins claude-sonnet-5-5; the coding agent frontmatter pins claude-haiku-4-5 — Own measurements, L4-M8
- **C446** [quoted] AGENTS.md's only delegation rule is qualitative — "Complex reasoning / architecture / multi-file → stronger model. Simple edits/searches → lighter." — [S68], ## Delegation
- **C447** [quoted] Our only side-by-side: code-gate Sonnet 4-6 turns 14 s $0.13 vs AutoCraft review.opus ~2 min ~$0.80 API-equivalent; it rests on 2 PRs — "| code-gate | Sonnet (default model), 4–6 turns | 14 s, $0.13 | 0 findings |" — [S69], body, Why table
- **C448** [quoted] A May 2026 draft research doc (jarvis) says Claude Code under Max costs ~$0 at the margin and only rate limits bind — "For a Claude Max subscriber, **the token cost of Claude Code itself is effectively $0 at the margin**" — [S70], TL;DR (status: draft)
- **C449** [quoted] Our AFK-lane retrospective recorded CLI costs up to $10.88 for a run that hit the 100-turn cap — "run 35710992984 (oss):     \"num_turns\": 101  \"total_cost_usd\": 10.8767  \"Reached maximum number of turns (100)\"" — [S71], line 359
- **C450** [inference] Both sides run on subscription logins, so the binding budget is plan rate-limit headroom, not dollars; storytold manages it with several accounts, usage polling and a priority queue, we only skip cosmetic PRs and cancel superseded runs — from [C423], [C424], [C437], [C440], [C443], [C444], [C448]
- **C451** [inference] Our review volume is jarvis ~11 Code Review runs a day and redrobot at least ~43, of unknown reviewed share; nothing caps review calls per PR, so on #2233's two-PR comparison an AutoCraft-style Opus review would cost ~6x per reviewed run — from [C442], [C443], [C444], [C447]
- **C452** [inference] storytold controls that fit us: per-PR review cap and interval, explicit model and effort per stage (code-gate inherits the default), per-run cost recorded by stage, usage-headroom pausing; outside-author budget and surge breaker matter little with one or two authors — from [C405], [C413], [C414], [C415], [C421], [C423], [C440], [C441]

## Disconfirming evidence

- [C111]/[C112] operators settle every question — grep pipeline.md for "auto-answer|without (an )?operator|pre-approved|standing answer": only operator pre-approval [C124] and the in-rule merge path; no automatic answering found.
- [C136]/[C137] AutoCraft on few apps — `commenter:app/autocraft-bot`: photocraft 0, designcraft 314 [C138]. It could act under a human token (as in [C139]); 3 marked photocraft PRs say rarely.
- [C133] merges by humans — one login's merges come in bursts and it authors the batch PRs [C134]; whether an agent drives them is not visible.
- [C141] human share by login — counter-claim [C140]: human-login text reads as agent output, and RFC-0006 makes the person running an agent accountable [C125]. It is a share of accountable logins, not of human-typed work.
- [C108] RFC decisions concentrated — team membership unreadable (L1-M11); based on 30 merged PRs only.
- [C130] founder's split — search `Brandon Thomas ArtCraft PhotoCraft agents human review maintainers blog interview`: no first-hand piece on maintainers' review; quote only via Latent Space.
- [C160] altitude not freed — holds placed and released under one login, maybe by an agent; latency not measured.
- [C162] role gate passed by authorship — read the check itself, risk_tier.md step 4 and `admin_author` in risk_tier.py (C163): an admin, non-Bot author passes; not tested by a run.
- [C203]/[C227] scorecard statuses verified — query: xtask/src/scorecard.rs for a code check of done rows → none (C226); verification is manual and dated (C225).
- [C205]/[C228] catalog + FLOOR as spec — query: FLOOR vs live count → 663 vs 664/664 (C229); surface counting misled (C207). Menu parity is saturated and no longer selects work.
- [C215]/[C217] "Done when" is a template — query: org code search for its headings (L2-M14), photocraft .github (L2-M1) → no template; agent authorship via "claude in:body author:davidmann4" → 1 hit; stays inference.
- [C234]/[C242] visual checks catch UI regressions — query: golden PNGs and `.snapshot(` in photocraft (L2-M10) → none; epic #15476 is the failure case (C239, C241). Counter: craft-libs has golden screen tests (C238), unused by PhotoCraft.
- [C236] PR screenshots as evidence — query: L2-M4, L2-M5 → 5/70 and 141/1,052; a ceiling, not a rate among UI PRs (gap).
- [C221] claiming solves duplicates — no post-RFC duplicate count found (gap).
- [C249] ours has no external spec generating work — query: skills grep → frontier is label-driven (C243); nothing found against.
- [C252] ours has no visual check rule — query: L2-M13, L2-M12 → only the golden-run oracle; nothing found against.
- Claim C302/C310 (rev pins only): searched every fetched manifest for craft-libs lines without `rev =` and for `branch = "main"` → 27 hits, all comments; 0 branch pins. Searched crates.io for published crates → storytold publishes none (L3-M2).
- Claim C311/C361 (fragmentation is a cost): looked for the opposite, repos on one rev → photocraft, wordcraft, lightcraft, materialcraft hold one; consolidation PRs (filmcraft#4917, anicraft#390) are recent, so fragmentation is fixed in places but recurring.
- Claim C318 (bumps by hand, not bot): query `org:storytold is:pr author:app/dependabot craft-libs` → 10 hits; the one read (deckcraft#2077) does not touch craft-libs. Gap: the other 9 were not read.
- Claim C326/C362 (duplication still present): RFC-0036 is an open PR dated 2026-11-15 with a table "as of 2026-11-14"; no merged migration found. Not checked: whether any listed copy was removed since.
- Claim C335 (rule 16 not in copies): expected lag, RFC merged 2 days ago; the check only warns on an older copy (C334). Not evidence of breakage.
- Claim C350 (our port drift): checked remote history, not only the 6-behind local clone → still no commit after 2026-10-16. Not checked: whether any drifted fix matters for music-intel-mcp's traffic.
- Claim C352 (no shared package): grep of music-intel-mcp pyproject for jarvis/git+ → none. redrobot pyproject not read.
- [C405]/[C406] model map — read the prompt definitions directly rather than the README; the README stage table agrees (Duplicates "Jev, Haiku, Opus, Sonnet"); defaults could be overridden on the Pipeline page for decide.prepare only (C404 "first is the default"). Nothing against.
- [C427] limits not dollars — grep for "cap_usd|spend cap|cost" in pipeline.md and schema.sql: a dollar cap exists only on security scans (C419); token_usage records cost without a cap. Nothing found against.
- [C423]/[C426] subscription accounts — query "Claude Max subscription automated pipeline claude -p headless allowed usage policy" found reports of a June 2026 move of claude -p to a separate credit pool; the official support page says that change is paused (C437). Supports, with the caveat that the rule changed once and may change again.
- [C433] contributors pay for their own agents — no storytold page states who pays; HN maintainer comments (L4-M3) say "community token spend" (C430); nothing found against.
- [C434] no public figure — WebSearch x2 and HN x4 (L4-M3); nothing found.
- [C439] 2x price, 6x cost — counter: #2233's $0.13 vs my measured $0.074 (C441) shows per-PR Sonnet cost varies ~2x on its own; n=2 behind $0.80, so the decomposition is weak.
- [C450] subscription is the real budget — counter: the May 2026 research doc is a draft and older than the paused June change (C437, C448); the credits page says Claude Code is not covered by API credits (C438), consistent.


## Coverage

| Channel | Read | Gap |
|---|---|---|
| Users | storytold issue and PR threads: epic #15476 and #15559, pin-bump PRs, photocraft#8506; HN comments by the maintainer ([C430], [C432]) | no forum discussion of how storytold's maintainers work; Reddit not used |
| Specialists | storytold's own docs and RFCs (craft-contrib RFC-0000, 0003, 0006, 0036 draft, 0040), AutoCraft docs, prompts and schema, AGENTS.md files, craft-libs README; the Latent Space interview ([C130]); Anthropic pricing and plan pages; our rules, skills, workflows and risk-tier code | the ArtCraft talk's human-review section was not read; RFC-0035 read by title only |
| Data | own measurements over the GitHub API: merge and review logins per week, AutoCraft note counts, issue authorship and "Done when" counts, pin census over 20 repos, house-rules stamps, code-gate run counts and one run log, jarvis PR risk and hold counts (L1-M1..L4-M8) | samples are in GitHub's best-match order, not random; storytold's production limits and Cost page are behind a login |
| Adversarial | disconfirming searches per load-bearing claim; the port regression epic ([C239]); the saturated parity floor and surface-counting misread ([C207], [C229]); fragmented pins ([C311]) | no public post-mortem of storytold's fleet cost or of a wrong AutoCraft merge |

Declared overruns:
- Q1: ledger at 20,323 characters against the 20,000 cap, after one claim ([C163]) was added at synthesis from the risk-tier code; page reads past three.
- Q2: five full page reads against a ceiling of three, because selection and done criteria live in different files.
- Q3: about 70 GitHub API calls against about 60 (40 tree reads for the pin census), and more than three full reads.
- Q4: page reads past three, because AutoCraft's facts span five files; read by section.

No fetched page addressed instructions to the agents. redrobot content was read through `gh api` and kept local; only counts, template headings and one denylist sentence enter this report. No search-and-scrape connector was used.

## Own measurements

<!-- ledger Q1 -->
### L1-M1

`sample_prs.py storytold/photocraft 2026-11-10 2026-11-16` + `analyze.py` (GraphQL, best-match order, 100 of 520): "PR authors distinct 20 bot-typed authors 0"; "mergedBy [('davidmann4', 66), ('dylanmtaylor', 19), ('FredApps', 13), ('ghost', 1), ('skylartaylor', 1)]"; "reviews total 133"; coderabbitai 66; "comments total 176 AI-marked 0 Bot-typed 131"; "PRs with >=1 non-AI-marked non-bot review 30"

### L1-M2

`inspect.py pc.json`: "davidmann4 merges 66 distinct minutes 32 merges sharing a minute 52 max in one minute 5"

### L1-M3

search `repo:storytold/photocraft is:pr in:title "Integration batch" created:2026-11-01..2026-11-18`: "photocraft issueCount 12"; 11 by davidmann4 (e.g. "11643 MERGED ... davidmann4 davidmann4 | Integration batch 19")

### L1-M4

same for wordcraft: "total 90 | sampled 90"; "mergedBy [('FredApps', 46), ('benandez', 27), ('dylanmtaylor', 16), ('skylartaylor', 1)]"; "reviews total 393", coderabbitai 192; "PRs with >=1 non-AI-marked non-bot review 68"

### L1-M5

`marker_repo.py` (`"Not a maintainer decision"`, PRs created Nov 1–18): "photocraft ... 1973 with AutoCraft note: 3"; "wordcraft ... 1014 ... 2"; "designcraft ... 460 ... 347"; "deckcraft ... 376 ... 244"

### L1-M6

same for designcraft: "total 140 | sampled 100"; "mergedBy [('dylanmtaylor', 34), ('FredApps', 30), ('autocraft-bot', 28), ('aiongg', 4), ('skylartaylor', 3), ('ghost', 1)]"; "reviews total 370 AI-marked 76"; coderabbitai 147, autocraft-bot 71

### L1-M7

org search `"integration batch" is:pr`: "designcraft 2291 MERGED ... {'login': 'aiongg'} {'login': 'aiongg'}"; body "_Automated message. Not a maintainer decision._"

### L1-M8

craft-contrib merged PRs: "craft-contrib merged total 30 sampled 30 RFC-titled 23"; "mergedBy [('FredApps', 17), ('skylartaylor', 6), ('dylanmtaylor', 4), ('echelon', 2), ('bflatastic', 1)]"; "approvers [('FredApps', 21), ('skylartaylor', 7), ('bflatastic', 1), ('echelon', 1)]"

### L1-M9

`commenter:app/autocraft-bot created:2026-10-01..2026-11-18`: "pc":{"issueCount":0}, "dc":{"issueCount":314}

### L1-M10

`inspect.py pc.json` openings: "review FredApps #15093 | Post-merge review of `eb758cc2c`. It was merged at 15:18 Stockholm time, before I posted."

### L1-M11

`orgs/storytold/teams/craft-app-team/members` → "Not Found (HTTP 404)" (needs admin:org); 8 public org members

### L1-M12

Grep `(?i)tier ?0|owner.escalation|tier_classif` over jarvis `*.{py,yml,yaml,ps1,sh}`: "tests\infrastructure\test_live_supabase_guard.py", "tests\conftest.py" only

### L1-M13

`sample_prs.py Osasuwu/jarvis 2026-11-10 2026-11-16`: "total 7 | sampled 7"; "mergedBy [('Osasuwu', 7)]"; "reviews total 0"

### L1-M14

`git log origin/main --first-parent --since=2026-10-20`, per-commit grep "Co-Authored-By: Claude": "commits 41 with-Claude-trailer 41"; "41 Osasuwu"

### L1-M15

`jv_risk.py` (merged 10-20..11-18): "Risk line [('HIGH', 22), ('LOW', 12), ('MEDIUM', 7)]"; "PRs that carried waiting-human-review 18", labelled and unlabelled by 'Osasuwu'; "reviews []"

<!-- ledger Q2 -->
### L2-M1

`gh api repos/storytold/photocraft/git/trees/HEAD?recursive=1`: "storytold/photocraft files: 2953 truncated: False"; grep `^crates/ui-egui/src/parity.rs$` → 0; present: "crates/ui-egui/src/menus/parity.rs"; `^\.github/` → actionlint.yaml, dependabot.yml, 11 workflows only; `snapshots/.*\.png$` → 0.

### L2-M2

`curl .../crates/ui-egui/src/menus/parity.rs | grep FLOOR`: "pub const FLOOR: usize = 663;"; docs/scorecard.md Summary: "| [Automation](#automation) | 6 | 4 | 2 | 664 of 664 menu items live (100.0%) |".

### L2-M3

`curl .../xtask/src/scorecard.rs`: parse_checklist errs only on "every item needs an id and a target", "`|` breaks the Markdown table"; load_checklists on "duplicate item id"; `--check` on "is stale". Item fields: id, target, status, issue, note; no test or path lookup.

### L2-M4

measure_prs_issues.py storytold/photocraft (100 closed PRs): "merged=70 merged_with_image_in_body=5"; "merged date range: 2026-11-14T19:33:10Z .. 2026-11-18T17:01:55Z"; "top PR body headings: summary by coderabbit=61; verification=16". Image regex also counts .png tokens (upper bound).

### L2-M5

search_counts.py (issue search; free text matches body and comments): "1052  repo:storytold/photocraft is:pr is:merged merged:2026-11-01..2026-11-18"; "141 ... screenshot"; "177 ... snapshot".

### L2-M6

search_counts.py, created:2026-11-01..2026-11-18: "3083 ... is:issue"; "1935 ... author:davidmann4"; "1941 ... \"Done when\" in:body"; "1905 ... \"Done when\" in:body author:davidmann4"; "36 ... -author:davidmann4 \"Done when\" in:body"; "1890 ... \"Reference application\""; "1332 ... label:parity"; "1 ... author:davidmann4 claude in:body".

### L2-M8

`gh api repos/storytold/photocraft/issues/15476`; body `grep -c "^| #"` → 60.

### L2-M9

code search: `org:storytold "pub const FLOOR"` total_count 3 (photocraft, texturecraft parity.rs; filmcraft ducking.rs unrelated); `filename:scorecard.md` total_count 1 (photocraft); `parity in:path extension:md` total_count 109 across 14 repos (figcraft 12, photocraft 9, wordcraft 8, ...).

### L2-M10

photocraft ui-egui dev-deps: "egui_kittest = { workspace = true, features = [\"wgpu\", \"snapshot\", \"eframe\"] }"; code search `repo:storytold/photocraft ".snapshot("` total_count 0; `org:storytold "try_snapshot"` total_count 2 (craft-libs testing/mod.rs, texturecraft ui_snapshots.rs); craft-libs tree `snapshots/.*\.png$` → 6; texturecraft header: "Run with TC_UI_SNAPSHOTS=<dir> cargo test ... -- --ignored".

### L2-M11

measure_prs_issues.py Osasuwu/jarvis: "merged=90 merged_with_image_in_body=0"; "issue authors (login,type): Osasuwu/User=43"; "top issue body headings: acceptance criteria=41; parent=35; ..."; search_counts: "21  repo:Osasuwu/jarvis is:issue created:2026-11-01..2026-11-18".

### L2-M12

redrobot (private, read locally): tree grep `\.(tsx|jsx|vue|html|qml|ui)$` → 78 (77 under frontend/src); golden/snapshot test paths are leveling and sandbox replays only, none for UI; PR template: "<!-- SCREENSHOTS: If UI changed, add before/after screenshots below -->"; measure_prs_issues.py: "merged=98 merged_with_image_in_body=3".

### L2-M13

Grep -i `screenshot|visual check|visually|golden|snapshot test` over jarvis-private skills/ and reference/ *.md → only to-tickets/SKILL.md:79,81 (golden run oracle); jarvis AGENTS.md → 0.

### L2-M14

code search `org:storytold "Done when" "Reference application"` total_count 1 (a photocraft test file); `org:storytold "Done when" language:Markdown` total_count 8 (gaps/roadmap/agents docs, none an issue template).

<!-- ledger Q3 -->
### L3-M1

`gh api repos/storytold/craft-libs/releases` and `/tags` → `[]` and `[]`; tree (not truncated) 3854 entries, 129 Cargo.toml, `crates/<dir>` 115, vendor 8; README `- [\`craft-` entries: 108. 2026-11-19.

### L3-M2

`curl -s -A research-client https://crates.io/api/v1/crates/{craft-pdf,craft-xml,craft-atomic}` → `crate \`craft-pdf\` does not exist`; `crate \`craft-xml\` does not exist`; craft-atomic `"default_version":"1.4.7"`, `"repository":"https://github.com/aphrody-labs/craft-libs"`.

### L3-M3

gh2.py: org has 82 public repos, 40 Rust; for each, tree + raw Cargo.toml/AGENTS.md (designcraft root refetched after an SSL error). an2.py: `TOTAL dependency entries naming craft-libs by kind: {'rev': 401}`; 27 other matching lines are comments. Distinct revs per repo (20 repos): 18, 17, 11, 9, 9, 8, 7, 6, 6, 6, 5, 4, 3, 2, and 1 in six (names in an2.txt in the scratch dir). Inline-table regex; multi-line `[dependencies.craft-*]` tables: none found.

### L3-M4

an2.py AGENTS.md: core block source `dde09ea31e` in 17 repos, `1315c63e17` in pdfcraft; `16. **Shared libraries first` present in 0. `gh api repos/storytold/craft-contrib/commits?path=rfcs/0040-...` → `937c37449f 2026-11-17 RFC-0040: Shared-library-first guidance for Craft apps (#62)`.

### L3-M5

gh4.py search/issues: `org:storytold is:pr in:title "craft-libs" pin` total 49; `... in:title craft-libs bump` 1; `org:storytold is:pr in:title "house rules" created:>=2026-11-01` 32. `gh api repos/storytold/deckcraft/pulls/2077 --jq .body` → 0 lines matching craft-libs; deckcraft dependabot.yml: cargo, daily, group `"*"`.

### L3-M6

`grep -oE "(From|from|Carved from|carved from) [A-Z][a-zA-Z]+Craft" README.md` → PhotoCraft 9, MailCraft 6, LightCraft 6, FilmCraft 6, EffectCraft 4, FigCraft 3, DeckCraft 3, PdfCraft 2, CADCraft 2, SoundCraft 1, LoopCraft 1.

### L3-M7

`ls ~/.claude/plugins/cache/jarvis-private/jarvis/` → 14 dirs, 1.6.16 … 1.6.42; `git log -- .claude-plugin/plugin.json` in ~/jarvis-private (HEAD 161e5ad, 2026-11-10) → 41 commits, first 2026-10-17 `feat(#56): deliver the harness as the jarvis plugin`.

### L3-M8

`grep workflow_call .github/workflows/*.yml` (jarvis d5c93cd7) → lane.yml, lane-watch.yml, lane-close.yml; `grep "uses: Osasuwu/"` → agent-dispatch, lane-ledger-close, lane-red-check-watcher, pr-body-check all `@2d4b5aeb9b3ff8a0a6c204ccadbec81aea04ad0d`; same grep in music-intel-mcp workflows → no `uses:`, 3 port/design comments.

### L3-M9

cmp_ours.py (music-intel-mcp local 9a51df8, 6 behind origin): workflows code-gate-verdict 0.68, code-review 0.85, gitleaks 0.75, pr-body-check 0.55, unblock-ready identical, waiting-human-review 0.42; scripts code_gate_verdict.py 0.74 (1350 vs 1198 lines), github_client.py identical, unblock_ready.py identical; test-quality.md jarvis vs jarvis-private 0.18 (161 vs 199 lines).

### L3-M10

`gh api repos/Osasuwu/music-intel-mcp/commits?path=.github/scripts/code_gate_verdict.py` → `72d215e 2026-10-16`, `55edd84 2026-10-08`. jarvis `git log` same path → 0a2bb7c3 11-04, 4d79e197 11-04, b7d63baa 10-27, a30b6a20 10-17 (#2085), plus 10-16 commits; `grep -c sweep` jarvis 8, music-intel 0.

### L3-M11

gh3.py: `repos/SergazyNarynov/redrobot/contents/.github/workflows` → 17 files; `uses: Osasuwu/` matches 0; jarvis-port mentions 0. Content not recorded.

### L3-M12

`grep -i "jarvis\|git+" music-intel-mcp/pyproject.toml` → only the description line and the byte-identical comment.

<!-- ledger Q4 -->
### L4-M1

`python -I q4/stages.py <autocraft src/prompts/index.ts @d8e45b5>` → e.g. "193 review.opus ["opus"] high 20" / "336 premerge.opus ["opus"] high 40" / "386 fixup.patch ["sonnet"] medium 20" / "658 fixissue.patch ["sonnet"] high 30" / "94 classify.haiku ["haiku"] medium -"; security.* sandbox `maxTurns: 60`.

### L4-M2

`grep -noE ".{0,200}ANTHROPIC_API_KEY.{0,200}" docs/pipeline.md docs/operations.md README.md` (autocraft) → no output.

### L4-M3

HN Algolia `photocraft` (top 50 of 665), `autocraft storytold` (38), author_echelon `claude`/`tokens` (top 30 each): no fleet dollar figure. WebSearch "storytold autocraft Claude cost per PR" → "The search didn't turn up anything about "Storytold" or "Autocraft"".

### L4-M4

grep of code-review.yml: jarvis line 156 "claude_code_oauth_token: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}", no `--model`/`--max-turns`; redrobot (gh api contents) lines 127, 236 same token, no model; music-intel-mcp lines 146, 269 same, no model.

### L4-M5

`gh run view 44352353390 --repo Osasuwu/jarvis --log` (PR_NUMBER 2234) → "\"model\": \"claude-sonnet-5-5\"" / "\"num_turns\": 5," / "\"total_cost_usd\": 0.07431750000000001,".

### L4-M6

`gh run list --workflow code-review.yml --created ">=2026-11-12" --limit 300` → "Osasuwu/jarvis runs>= 2026-11-12 76 {'success': 53, 'skipped': 19, 'cancelled': 4} distinct head branches 28" / "Osasuwu/music-intel-mcp ... 21 {'success': 15, 'skipped': 3, 'cancelled': 3} ... 8" / "SergazyNarynov/redrobot ... 300 {'success': 249, 'cancelled': 4, 'skipped': 47} ... 54".

### L4-M7

code_gate_verdict.py `review_skip_reason`: returns "draft", "files-incomplete", "cosmetic", "untrusted"; logs of the 6 newest successful jarvis runs: 44380452740, 44380019583, 44373382611, 44364491922, 44344268837 "skip_reason=cosmetic"; 44352353390 "skip_reason=" (reviewed).

### L4-M8

jarvis `config/plan_review.yaml` → "planner: \"claude-opus-5\"" / "critic: \"claude-sonnet-5\""; `.claude/agents/coding.md:4:model: claude-haiku-4-5-20251001`; agent-dispatch.yml:30 "model: claude-sonnet-5-5"; orchestrate SKILL.md:226 "a Sonnet id for mechanical work"; :268 "a background `Agent`, `opus`".


## Open questions

- Q1 — what a storytold maintainer's day looks like; nothing first-hand was found. The ArtCraft talk's human-review section would partly settle it.
- Q1 — AutoCraft's decision-queue size and answer latency, and `craft-app-team` membership; both need access storytold does not give publicly.
- Q1 — whether the HIGH holds on jarvis are placed and released by the user or by an agent under the user's login; the PR timeline events would settle it.
- Q2 — what share of PRs touch UI in either org, so the screenshot counts can be read as a rate; per-PR file lists would settle it.
- Q2 — whether davidmann4's "Done when" issues are written by an agent, and whether duplicate work fell after RFC-0003.
- Q3 — whether the fixes music-intel-mcp's `code_gate_verdict.py` missed matter for its traffic; a diff of the two copies against its recent runs would settle it.
- Q3 — the other 9 Dependabot hits and the merged/open split of the 49 pin PRs.
- Q4 — storytold's production limit values; our subscription tier and seat count; what share of redrobot's 300+ weekly Code Review runs actually ran the model.
- Q4 — whether #2233's ~6x cost gap holds beyond two PRs, and how much of it is turns, effort and format rather than model.
- Q2 — whether an org-level template (storytold/.github) defines the "Done when" issue form; reading that repo's ISSUE_TEMPLATE would settle it.
- Q3 — craft-libs `main` README announces a coordinated v0.1.0 release taken by `tag`, yet the repo has no tags or releases; whether tag pins are replacing rev pins would change the versioning answer. Re-reading tags, releases and app manifests after that release would settle it.
- Q3 — whether the pin-consolidation PRs (filmcraft#4917, anicraft#390), both open on 2026-11-19, merge and the repos stay on one rev.
- Q1 — whether the login aiongg, which merges designcraft batch PRs carrying AutoCraft's note, is a person or an automation account; its profile and commit history would settle it.


## Sources

- [S1] https://raw.githubusercontent.com/storytold/craft-contrib/HEAD/rfcs/0000-decision-process.md — passage
- [S2] https://raw.githubusercontent.com/storytold/autocraft/HEAD/docs/how-it-works.md — passage
- [S3] https://raw.githubusercontent.com/storytold/autocraft/HEAD/docs/pipeline.md — passage
- [S4] https://raw.githubusercontent.com/storytold/autocraft/HEAD/docs/operations.md — passage
- [S5] https://raw.githubusercontent.com/storytold/craft-contrib/HEAD/rfcs/0006-coding-agents.md — passage
- [S6] https://raw.githubusercontent.com/storytold/craft-anything/HEAD/docs/ROADMAP.md — passage
- [S7] https://latent.space/p/artcraft — passage
- [S8] https://github.com/Osasuwu/jarvis-private/blob/main/reference/merge-gates.md — passage
- [S9] https://github.com/Osasuwu/jarvis-private/blob/main/skills/orchestrate/SKILL.md — passage
- [S10] https://github.com/Osasuwu/jarvis/blob/main/AGENTS.md — passage
- [S11] https://github.com/SergazyNarynov/redrobot/blob/main/AGENTS.md — passage
- [S12] https://github.com/Osasuwu/jarvis-private/blob/main/memory/osasuwu/jarvis/MEMORY.md — passage
- [S13] https://github.com/Osasuwu/jarvis/blob/main/docs/decisions/2026-Q2.md — passage
- [S14] https://github.com/Osasuwu/jarvis/blob/main/CONTEXT.md — passage
- [S15] https://github.com/Osasuwu/jarvis-private/blob/main/memory/osasuwu/jarvis/feedback_reliability_not_strictness.md — passage
- [S16] https://github.com/Osasuwu/jarvis/blob/d5c93cd7/.github/scripts/risk_tier.md — passage
- [S17] https://github.com/storytold/photocraft/blob/main/AGENTS.md — passage
- [S18] https://github.com/storytold/photocraft/blob/main/docs/gaps.md — passage
- [S19] https://github.com/storytold/photocraft/blob/main/docs/target-app-parity.md — passage
- [S20] https://github.com/storytold/filmcraft/blob/main/docs/agents.md — passage
- [S21] https://github.com/storytold/craft-anything/blob/main/AGENTS.md — passage
- [S22] https://github.com/storytold/craft-anything/blob/main/README.md — passage
- [S23] https://github.com/storytold/photocraft/issues/15559 — passage
- [S24] https://github.com/storytold/photocraft/issues/15476 — passage
- [S25] https://github.com/storytold/craft-contrib/blob/main/rfcs/0003-claiming-issues.md — passage
- [S26] https://github.com/storytold/photocraft/blob/main/scorecard/tools.toml — passage
- [S27] https://github.com/storytold/photocraft/blob/main/docs/scorecard.md — passage
- [S28] https://github.com/storytold/photocraft/blob/main/crates/ui-egui/src/menus/parity.rs — passage
- [S29] https://github.com/storytold/craft-anything/blob/main/.github/pull_request_template.md — passage
- [S30] https://github.com/storytold/craft-libs/blob/main/crates/ui/src/testing/mod.rs — passage
- [S31] https://github.com/Osasuwu/jarvis-private/blob/970774e/skills/triage/SKILL.md — passage
- [S32] https://github.com/Osasuwu/jarvis-private/blob/970774e/skills/file-issue/SKILL.md — passage
- [S33] https://github.com/Osasuwu/jarvis-private/blob/970774e/skills/to-tickets/SKILL.md — passage
- [S34] https://github.com/Osasuwu/jarvis/blob/main/.github/ISSUE_TEMPLATE/task.yml — passage
- [S35] https://github.com/Osasuwu/jarvis-private/blob/970774e/skills/implement/SKILL.md — passage
- [S36] https://github.com/Osasuwu/jarvis/blob/main/.github/PULL_REQUEST_TEMPLATE.md — passage
- [S37] https://github.com/Osasuwu/jarvis-private/blob/970774e/CLAUDE.md — passage
- [S38] https://raw.githubusercontent.com/storytold/craft-libs/HEAD/README.md — passage
- [S39] https://raw.githubusercontent.com/storytold/craft-libs/HEAD/Cargo.toml — passage
- [S40] https://raw.githubusercontent.com/storytold/craft-libs/HEAD/AGENTS.md — passage
- [S41] https://github.com/storytold/filmcraft/pull/4917 — passage
- [S42] https://github.com/storytold/anicraft/pull/390 — passage
- [S43] https://github.com/storytold/wordcraft/pull/6954 — passage
- [S44] https://github.com/storytold/photocraft/pull/8506#issuecomment-6883981012 — passage
- [S45] https://raw.githubusercontent.com/storytold/craft-contrib/HEAD/rfcs/0040-shared-library-first-guidance.md — passage
- [S46] https://raw.githubusercontent.com/storytold/craft-contrib/HEAD/standards/house-rules-core.md — passage
- [S47] https://github.com/storytold/craft-contrib/pull/56 — passage
- [S48] https://raw.githubusercontent.com/storytold/craft-common-actions/main/.github/workflows/house-rules.yml — passage
- [S49] https://raw.githubusercontent.com/storytold/craft-libs/HEAD/.github/workflows/house-rules.yml — passage
- [S50] https://github.com/Osasuwu/jarvis-private/blob/master/README.md — passage
- [S51] https://github.com/Osasuwu/jarvis-private/blob/master/.claude-plugin/plugin.json — passage
- [S52] https://github.com/Osasuwu/jarvis-private/blob/master/reference/test-quality.md — passage
- [S53] https://github.com/Osasuwu/jarvis/blob/main/.github/workflows/lane-pin-drift.yml — passage
- [S54] https://github.com/Osasuwu/music-intel-mcp/blob/main/.github/workflows/code-review.yml — passage
- [S55] https://github.com/Osasuwu/music-intel-mcp/blob/main/pyproject.toml — passage
- [S56] https://github.com/storytold/autocraft/blob/d8e45b5/README.md — passage
- [S57] https://github.com/storytold/autocraft/blob/d8e45b5/src/prompts/index.ts — passage
- [S58] https://github.com/storytold/autocraft/blob/d8e45b5/docs/pipeline.md — passage
- [S59] https://github.com/storytold/autocraft/blob/d8e45b5/src/schema.sql — passage
- [S60] https://github.com/storytold/craft-contrib/blob/HEAD/rfcs/0006-coding-agents.md — passage
- [S61] https://github.com/storytold/photocraft/blob/HEAD/AGENTS.md — passage
- [S62] https://news.ycombinator.com/item?id=49976861 — passage
- [S63] https://news.ycombinator.com/item?id=50325139 — passage
- [S64] https://platform.claude.com/docs/en/about-claude/pricing — passage
- [S65] https://support.claude.com/en/articles/15036540-use-the-claude-agent-sdk-with-your-claude-plan — passage
- [S66] https://platform.claude.com/docs/en/about-claude/api-credits-for-subscribers — passage
- [S67] https://github.com/Osasuwu/jarvis/blob/d5c93cd7/.github/workflows/code-review.yml — passage
- [S68] https://github.com/Osasuwu/jarvis/blob/d5c93cd7/AGENTS.md — passage
- [S69] https://github.com/Osasuwu/jarvis/issues/2233 — passage
- [S70] https://github.com/Osasuwu/jarvis/blob/d5c93cd7/docs/research/cheap-models-cost-reduction-2026-05-18.md — passage
- [S71] https://github.com/Osasuwu/jarvis/blob/d5c93cd7/docs/research/afk-orchestration-retrospective-2026-10-06.md — passage

## Audit

| Claim | Verdict | Note |
|---|---|---|
| C101 | SUPPORTED | quote found in the cited source |
| C102 | PARTIAL | rewritten: S1 gives 7 days for adding/removing an app or changing the process, not 'big changes' |
| C103 | SUPPORTED | quote found in the cited source |
| C104 | SUPPORTED | quote found in the cited source |
| C107 | PARTIAL | rewritten: L1-M8 shows logins, not account types or who is founder |
| C108 | PARTIAL | rewritten: 'owners rarely override' not shown by any cited claim |
| C109 | SUPPORTED | quote found in the cited source |
| C110 | SUPPORTED | two quotes joined by ' / '; each found in S3 intro |
| C111 | SUPPORTED | quote found in the cited source |
| C112 | SUPPORTED | quote found in the cited source |
| C113 | SUPPORTED | quote found in the cited source |
| C114 | SUPPORTED | quote found in the cited source |
| C115 | SUPPORTED | quote found in the cited source |
| C117 | SUPPORTED | five quotes joined by ' / '; each found in S3 Merge without asking |
| C118 | SUPPORTED | quote found in the cited source |
| C119 | SUPPORTED | quote found in the cited source |
| C120 | SUPPORTED | quote found in the cited source |
| C121 | SUPPORTED | quote found in the cited source |
| C123 | SUPPORTED | quote found in the cited source |
| C124 | SUPPORTED | pre-approval is an operator act, S3 merge-queue rows |
| C125 | SUPPORTED | quote found in the cited source |
| C126 | SUPPORTED | quote found in the cited source |
| C127 | SUPPORTED | quote found in the cited source |
| C129 | PARTIAL | rewritten: S6 says agents may take unclaimed pending changes of maintainer items, not 'the rest' |
| C130 | SUPPORTED | Brandon Thomas, founder/CEO, quoted in Latent Space |
| C133 | PARTIAL | rewritten: L1-M1 shows 0 Bot-typed authors; merger types are not shown (one ghost) |
| C134 | PARTIAL | rewritten: the search window is Nov 1-18, not Nov 2-12 |
| C135 | PARTIAL | rewritten: L1-M4 lists four logins (46, 27, 16, 1) |
| C136 | SUPPORTED | matches the ledger output |
| C137 | SUPPORTED | matches the ledger output |
| C138 | SUPPORTED | matches the ledger output |
| C139 | PARTIAL | rewritten: L1-M7 shows one PR, by aiongg; that login being human is not shown |
| C140 | PARTIAL | rewritten: L1-M10 shows one FredApps comment; 'exact-head SHAs' not in the output |
| C141 | PARTIAL | rewritten: designcraft share is 28 of 100 sampled; 'human' per login not shown |
| C142 | SUPPORTED | follows from the cited claims |
| C143 | PARTIAL | rewritten: S2 says write-access maintainers can settle when an operator enables it |
| C144 | SUPPORTED | private repo, read via gh api on the default branch (master), not the cited blob/main URL |
| C145 | SUPPORTED | private repo, read via gh api on the default branch (master), not the cited blob/main URL |
| C146 | SUPPORTED | private repo, read via gh api on the default branch (master), not the cited blob/main URL |
| C147 | SUPPORTED | private repo, read via gh api on the default branch (master), not the cited blob/main URL |
| C148 | SUPPORTED | quote found in the cited source |
| C149 | SUPPORTED | private redrobot AGENTS.md, read via gh api on master |
| C150 | SUPPORTED | private repo, read via gh api on the default branch (master), not the cited blob/main URL |
| C151 | SUPPORTED | quote found in the cited source |
| C152 | SUPPORTED | matches the ledger output |
| C153 | PARTIAL | rewritten: lane freeze date not in S14 |
| C154 | PARTIAL | rewritten: L1-M13 shows mergers and reviews, not authors |
| C155 | SUPPORTED | matches the ledger output |
| C156 | SUPPORTED | matches the ledger output |
| C157 | SUPPORTED | private repo, read via gh api on the default branch (master), not the cited blob/main URL |
| C158 | PARTIAL | rewritten: 'crowd' overstates the several maintainers measured |
| C159 | PARTIAL | rewritten: 'narrower' is not comparable from the cited claims; 'declared' dropped |
| C160 | PARTIAL | rewritten: who placed and released the holds is unknown, so 'not freed much altitude' is not shown |
| C161 | SUPPORTED | follows from the cited claims |
| C162 | SUPPORTED | follows from the cited claims |
| C163 | SUPPORTED | quote found in the cited source |
| C201 | SUPPORTED | quote found in the cited source |
| C202 | SUPPORTED | quote found in the cited source |
| C203 | SUPPORTED | quote found in the cited source |
| C204 | SUPPORTED | quote found in the cited source |
| C205 | PARTIAL | rewritten: S17 rule 1 says a catalog id makes the item live; 'the spec for commands' is not in it |
| C206 | SUPPORTED | quote found in the cited source |
| C207 | SUPPORTED | quote found in the cited source |
| C208 | PARTIAL | rewritten: the table also carries other estimates; agent-hours are to beta and full parity |
| C209 | SUPPORTED | quote found in the cited source |
| C210 | SUPPORTED | matches the ledger output |
| C211 | PARTIAL | rewritten: 'no reference app' not in the quoted passage |
| C213 | SUPPORTED | quote found in the cited source |
| C214 | SUPPORTED | matches the ledger output |
| C215 | SUPPORTED | matches the ledger output |
| C216 | SUPPORTED | matches the ledger output |
| C217 | PARTIAL | rewritten: generation by tooling is inferred, not shown; hedged to 'likely' |
| C218 | SUPPORTED | quote has a literal \n; both lines found in S23 |
| C219 | SUPPORTED | quote found in the cited source |
| C220 | SUPPORTED | quote found in the cited source |
| C221 | SUPPORTED | quote found in the cited source |
| C222 | SUPPORTED | quote found in the cited source |
| C224 | SUPPORTED | quote found in the cited source |
| C225 | SUPPORTED | quote found in the cited source |
| C226 | SUPPORTED | matches the ledger output |
| C227 | SUPPORTED | quote found in the cited source |
| C228 | SUPPORTED | quote found in the cited source |
| C229 | SUPPORTED | matches the ledger output |
| C230 | SUPPORTED | matches the ledger output |
| C231 | SUPPORTED | quote found in the cited source |
| C232 | SUPPORTED | quote found in the cited source |
| C233 | SUPPORTED | quote found in the cited source |
| C234 | SUPPORTED | quote found in the cited source |
| C235 | SUPPORTED | quote found in the cited source |
| C236 | PARTIAL | rewritten: no rule requiring screenshots was cited, so 'compliance' overstates |
| C237 | SUPPORTED | matches the ledger output |
| C238 | SUPPORTED | quote has a literal \n; found in S30 |
| C239 | PARTIAL | rewritten: S24 intro says the epic collects what behaves worse; how found is per issue |
| C240 | PARTIAL | rewritten: S23 is one issue (#15559); extended to 'at least one' |
| C241 | SUPPORTED | matches the ledger output |
| C242 | SUPPORTED | follows from the cited claims |
| C243 | PARTIAL | rewritten: S31 line 79 is in the attention view, not frontier mode; private repo, read via gh api on the default branch (master), not the cited blob/main URL |
| C244 | SUPPORTED | private repo, read via gh api on the default branch (master), not the cited blob/main URL; quote has a literal \n; found in S32 |
| C245 | PARTIAL | rewritten: S33 3a applies the oracle rule to exploratory slices; private repo, read via gh api on the default branch (master), not the cited blob/main URL |
| C246 | SUPPORTED | S34 also has default AC 'Implementation complete / Tests pass / Documentation updated' |
| C247 | SUPPORTED | matches the ledger output |
| C248 | SUPPORTED | private repo, read via gh api on the default branch (master), not the cited blob/main URL |
| C249 | PARTIAL | rewritten: redrobot's work source was not measured |
| C250 | SUPPORTED | quote has a literal \n; found in S36 |
| C251 | SUPPORTED | matches the ledger output |
| C252 | SUPPORTED | matches the ledger output |
| C253 | SUPPORTED | private repo, read via gh api on the default branch (master), not the cited blob/main URL |
| C301 | SUPPORTED | quote found in the cited source |
| C302 | PARTIAL | rewritten: quote is only in the stale `HEAD`-branch README; main README documents tag = v0.1.0 with rev as alternative |
| C303 | SUPPORTED | quote found in the cited source |
| C304 | SUPPORTED | still no tags or releases on 2026-11-19, but main README announces v0.1.0 |
| C305 | SUPPORTED | matches the ledger output |
| C306 | SUPPORTED | quote found in the cited source |
| C307 | SUPPORTED | quote found in the cited source |
| C308 | SUPPORTED | matches the ledger output |
| C309 | PARTIAL | rewritten: S38 says this for craft-aep only |
| C310 | SUPPORTED | matches the ledger output |
| C311 | PARTIAL | rewritten: L3-M3 output gives counts, not repo names (names in an2.txt only) |
| C312 | SUPPORTED | quote found in the cited source |
| C313 | SUPPORTED | PR #390 is open |
| C314 | SUPPORTED | quote found in the cited source |
| C315 | PARTIAL | rewritten: one PR (filmcraft#4917, open) shown, not a general rule |
| C316 | SUPPORTED | quote found in the cited source |
| C317 | SUPPORTED | quote found in the cited source |
| C318 | PARTIAL | rewritten: L3-M5 shows the title count; hand-written/not-a-bot not shown |
| C319 | SUPPORTED | matches the ledger output |
| C320 | SUPPORTED | quote found in the cited source |
| C321 | SUPPORTED | quote found in the cited source |
| C322 | SUPPORTED | quote found in the cited source |
| C323 | SUPPORTED | quote found in the cited source |
| C324 | SUPPORTED | quote found in the cited source |
| C325 | SUPPORTED | matches the ledger output |
| C326 | PARTIAL | rewritten: PR #56 is open but not a GitHub draft; quote found in the PR's file patch via gh api |
| C327 | SUPPORTED | found in S47 PR file patch, line-wrapped with leading + |
| C328 | SUPPORTED | found in S47 PR file patch, line-wrapped with leading + |
| C329 | SUPPORTED | found in S47 PR file patch, line-wrapped with leading + |
| C331 | SUPPORTED | quote found in the cited source |
| C332 | SUPPORTED | quote found in the cited source |
| C333 | SUPPORTED | quote found in the cited source |
| C334 | SUPPORTED | quote found in the cited source |
| C335 | SUPPORTED | matches the ledger output |
| C336 | SUPPORTED | quote found in the cited source |
| C337 | SUPPORTED | matches the ledger output |
| C340 | SUPPORTED | private repo, read via gh api on the default branch (master), not the cited blob/main URL |
| C341 | SUPPORTED | private repo, read via gh api on the default branch (master), not the cited blob/main URL |
| C342 | SUPPORTED | matches the ledger output |
| C343 | SUPPORTED | private repo, read via gh api on the default branch (master), not the cited blob/main URL |
| C344 | SUPPORTED | private repo, read via gh api on the default branch (master), not the cited blob/main URL |
| C345 | SUPPORTED | jarvis docs/reference/test-quality.md re-read: no source stamp |
| C346 | SUPPORTED | matches the ledger output |
| C347 | SUPPORTED | quote found in the cited source |
| C348 | SUPPORTED | matches the ledger output |
| C349 | SUPPORTED | quote found in the cited source |
| C350 | SUPPORTED | re-run: 9 jarvis commits after 2026-10-16T04:22Z, at least 6 non-docs |
| C351 | PARTIAL | rewritten: 'by hand' not in S55 |
| C352 | SUPPORTED | matches the ledger output |
| C353 | SUPPORTED | matches the ledger output |
| C360 | SUPPORTED | follows from the cited claims |
| C361 | PARTIAL | rewritten: 'hand-written' bumps rest on the repaired C318 |
| C362 | SUPPORTED | follows from the cited claims |
| C363 | SUPPORTED | follows from the cited claims |
| C364 | PARTIAL | rewritten: '3+ repos' clause not supported by cited claims |
| C401 | SUPPORTED | quote found in the cited source |
| C402 | SUPPORTED | quote found in the cited source |
| C403 | SUPPORTED | quote found in the cited source |
| C404 | SUPPORTED | quote found in the cited source |
| C405 | SUPPORTED | checked directly against the S57 prompt definitions |
| C406 | PARTIAL | rewritten: 'thousands of times a day' not in C405/C412 (S58 limits are 2000-3000 for some stages) |
| C408 | SUPPORTED | quote found in the cited source |
| C409 | SUPPORTED | quote found in the cited source |
| C411 | SUPPORTED | two quotes joined by ' / '; each found in S58 Daily limits |
| C412 | SUPPORTED | table rows joined by ' / '; each found in S58 (padding differs) |
| C413 | SUPPORTED | quote found in the cited source |
| C414 | SUPPORTED | quote found in the cited source |
| C415 | SUPPORTED | quote found in the cited source |
| C416 | SUPPORTED | quote found in the cited source |
| C417 | SUPPORTED | quote found in the cited source |
| C418 | SUPPORTED | quote found in the cited source |
| C419 | SUPPORTED | quote found in the cited source |
| C420 | SUPPORTED | quote found in the cited source |
| C421 | SUPPORTED | quote found in the cited source |
| C422 | SUPPORTED | quote found in the cited source |
| C423 | SUPPORTED | quote found in the cited source |
| C424 | SUPPORTED | quote found in the cited source |
| C425 | SUPPORTED | quote found in the cited source |
| C426 | SUPPORTED | matches the ledger output |
| C427 | SUPPORTED | follows from the cited claims |
| C428 | SUPPORTED | quote found in the cited source |
| C429 | SUPPORTED | quote found in the cited source |
| C430 | PARTIAL | rewritten: S62 does not contain 'We built ... storytold/artcraft'; quote found in HN Algolia JSON |
| C432 | SUPPORTED | found in HN Algolia JSON, split by <p> |
| C433 | PARTIAL | rewritten: 'storytold pays only for AutoCraft' not shown; maintainers run their own agents too |
| C434 | SUPPORTED | matches the ledger output |
| C435 | SUPPORTED | found in pricing.md table; cell padding differs |
| C436 | SUPPORTED | found in pricing.md table; cell padding differs |
| C437 | SUPPORTED | found in S65 banner |
| C438 | SUPPORTED | found in S66 table; cell padding differs |
| C439 | PARTIAL | rewritten: 2x price into 6x cost implies ~3x tokens; which factor drives it is not shown; n=2 |
| C440 | SUPPORTED | matches the ledger output |
| C441 | SUPPORTED | matches the ledger output |
| C442 | SUPPORTED | matches the ledger output |
| C443 | PARTIAL | rewritten: L4-M7 lists the 6 newest runs; the date is not in the output |
| C444 | SUPPORTED | quote found in the cited source |
| C445 | SUPPORTED | S9 lines 226 and 268 confirm the orchestrate routing |
| C446 | SUPPORTED | quote found in the cited source |
| C447 | SUPPORTED | quote found in the cited source |
| C448 | SUPPORTED | quote found in the cited source |
| C449 | SUPPORTED | quote found in the cited source |
| C450 | SUPPORTED | priority queue is C425, not in the from-list; content holds |
| C451 | PARTIAL | rewritten: the 6x rests on #2233's two PRs and applies to reviewed runs, not every push |
| C452 | SUPPORTED | follows from the cited claims |

Label verdict: open — every claim survives, but 41 needed rewriting, and two gaps could change the recommendations: #2233's ~6x cost rests on two PRs (Q4, recommendation 1), and who places and releases jarvis HIGH holds is not known (Q1, recommendation 2); craft-libs' announced v0.1.0 release could also change the Q3 versioning answer.

Quote check: storytold-human-role-work-selection-shared-code-economics-2026-11-19.md: 136 quoted claim(s): 107 found, 13 NOT FOUND, 16 unfetchable, 0 no source

## Disposition

| Recommendation | State | Where |
|---|---|---|
| If #2233's experiment moves code-gate toward an Opus review, take AutoCraft's spend controls with it: explicit model and effort, a per-PR review cap with a minimum interval, cost recorded per run | deferred | Osasuwu/jarvis#2233 — the shadow-review experiment owns the switch, so the controls ride with it |
| Say plainly where the hold is described that jarvis's HIGH hold is a label convention, not the role gate | deferred | unfiled: input to the user's deferred /grill on advisory CI and the merge hold, which decides what actually holds a merge |
| Stamp our copied files (test-quality.md, ported gate scripts) with source commit and hash, after checking whether music-intel-mcp's missed fixes matter | deferred | unfiled: no incident yet under the "proposing a check" rule; the music-intel-mcp check comes first (Open questions, Q3) |
| Fix the stale phase list in the jarvis task form | deferred | unfiled: a small fix, offered as a follow-up in this session |
| Visual UI checks and an external spec for work selection | dropped | no incident in our repos, and storytold's own visual practice failed at port scale |
