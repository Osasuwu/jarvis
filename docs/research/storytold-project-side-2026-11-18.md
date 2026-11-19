---
topic: storytold-project-side
tags: area:process, research
source_provenance: /research invocation in an interactive session, 2026-11-18, follow-up to docs/research/artcraft-ecosystem-autocraft-2026-11-18.md (jarvis PR #2231)
status: open
audit: 2026-11-18 — 179 claims: 148 SUPPORTED, 27 PARTIAL, 1 UNSUPPORTED, 3 UNCHECKABLE
---

## Question

посмотри ещё на сами репозитории как они настроены. У меня для redrobot запланирован переход в организацию, потому что только там есть некоторые фишки, которые я хотел включить, но возможно они не нужны по типу branch protection. Зачем он нужен, если того же самого можно достичь другим механизмом? Я просто не помню что именно мне нужно было из организации, возможно она всё равно нужна будет но по другим причинам. И как CI у них настроен и всё такое. Агентную часть разобрали, теперь надо разобрать проектную часть. Архитектуру и стэк как выбирают, по обычному или в агентской разработке есть другие правила? lifecycle проектов как выглядит, сравнить с нашими. У нас decisions записываются прям в репозиторий, они так делают, если нет, то куда записывают или держат в голове? researches у нас тоже пишется прям в репозиторий. У нас в redrobot отдельная дорожка для экспериментов есть, где-то ещё такое есть, как выглядит у них, нужна ли. У них только софт с примером копирования, есть ли проект, который оригинальный, как по другому он ведётся или так же? Что они делают, когда встают в тупик возможностей? Как справляются с непредвиденностями, когда что-то не правильно встаёт. Решают ли они весь дизайн в начале проекта и идут по нему и в процессе ничего не меняют или в процессе тоже меняют решения. Если да, то как? Какая скорость разработки у них, сравнивая между их же проектами и нашими, стабильная везде или рывками? Сколько стоит их режим разработки, если получится найти числа. И ещё вот таких вопросов докинь, что я не покрыл, но что можно взять полезного.

Asked also for extra questions worth asking; answering those as a list of proposed next runs under Open questions, not researched in this run, because a run takes at most four sub-questions. The storytold side is the public `github.com/storytold` organization; "our projects" are Osasuwu/jarvis, SergazyNarynov/redrobot and Osasuwu/music-intel-mcp.

Sub-questions: Q1 — how the storytold repositories, protection and CI are configured, and which GitHub plan gives a private repo enforced checks and a second admin (the redrobot organization question); Q2 — project lifecycle: stack choice, where decisions and research live, design up front vs revised, experiments lane, original vs clone products; Q3 — what happens at dead ends and surprises; Q4 — velocity and cost, compared with our repos.

## Summary

**redrobot and the organization.** The organization is still needed, but for two reasons, not the original list. A private repo on a personal Free account cannot enforce anything: redrobot's branch-protection endpoint answers 404 and its rulesets endpoint answers 403 "Upgrade to GitHub Pro" [C152]. GitHub's docs put protected branches, rulesets, required reviewers and code owners for private repos on Pro, Team or Enterprise [C123], [C125], [C130], [C132], and auto-merge for private repos on the same plans [C135]. A personal repository has only owner and collaborators, so a second admin is impossible there [C137], [C138]; organizations have a real Admin repository role [C140]. So Pro on the owner's personal account would buy enforced checks and auto-merge but no second admin, a Free organization would buy the admin role but no enforcement on a private repo [C131], [C140] — that the Admin role needs no paid plan is unchecked [C141] — and by the docs a Team organization buys both [C151]. That is what the redrobot plan already says: admin is impossible on a personal private repo, and Pro covers everything except "every setting only through the owner" [C153]; the admin is needed for the self-hosted runners, and a second org owner also covers token approvals and billing [C156]. CODEOWNERS is no longer one of the reasons — it was cancelled on 14.10 (#2523) [C154]. Merge queue is out on every option short of Enterprise Cloud [C136]. One caution: community threads disagree on whether Pro really enforces rules on a private personal repo [C148], [C149]; the docs and redrobot's own 403 text say it does [C123], [C152].

**How storytold is configured.** It is a public organization [C101], [C103]. Its protection is a single org-level ruleset on the default branch: no deletion, no force-push, PR required with zero approvals — no required status checks, no CODEOWNERS [C107], [C108], [C111], [C113]. CI is advisory: 12 of the 40 most recent merged photocraft PRs show a failed, cancelled or unfinished check on their head when read after merge, the shared `gate` among the failures [C155]. CI itself is a library of reusable workflows in `craft-common-actions` that every app calls at `@main` on GitHub-hosted runners [C115]–[C119]; Dependabot is daily and grouped [C121]; releases go out by pushing a ruleset-locked `release` branch [C110], [C122]. The enforcement redrobot wants is something storytold does not use; their brakes are the shared gate run, the house-rules check and, for review and merge, AutoCraft [C117], [C301]–[C312].

**Lifecycle and decisions.** The stack is a suite-wide rule for the native Craft apps: Rust only, no webview, justified by native performance and by agents writing the Rust [C201], [C202], [C206], [C210]; no written comparison of alternatives turned up [C214]. The compiler is used as a guardrail for agents (forbidden unsafe, denied lints, a format crate that fails to compile when a struct grows) [C208], [C209]. Cross-app decisions are RFCs in `craft-contrib` with a 3- or 7-day comment period and an owner override [C215]–[C217], amended IETF-style — accepted RFCs are never edited, a new RFC updates or obsoletes them [C339], [C228]. That process arrived two weeks after the apps did [C218]. Per-app decisions are thin: photocraft's `docs/decisions.md` holds 2 entries beside 83 top-level docs, parity, gap, performance and plan docs among them [C219], [C220]; AutoCraft has no decision log at all [C223]. Research notes are local and gitignored; what is committed is measurement docs [C224]–[C226]. Ours is heavier on both: jarvis keeps quarterly decision shards, grill folders, 4 ADRs and 80 research files; redrobot one file per decision, 122 plans and 65 research files [C240], [C241], [C243]. Design is not frozen: roadmaps are living documents with revision history, one was rebuilt wholesale from the code, big changes get a standalone plan doc [C229]–[C231].

**Experiments lane and original products.** No experiments lane found in photocraft, Craft Anything or AutoCraft (checked by branch names, and in photocraft also by path); only the older original product ArtCraft has `experimental/*` branches and an Experimental settings pane [C233]. redrobot's experiments journal for its RL/sand research [C242] has no counterpart there. The clones are steered by parity against the reference app [C207], [C232]; the original products are run differently — AutoCraft with spec docs, no roadmap or decision log, built by direct pushes to main, mostly by one login [C223], [C238], [C410]; Craft Anything with an explicit roadmap carrying owners and maintainer-only decision items [C222], [C238].

**Dead ends and surprises.** No postmortem files [C344]. Lessons go into rules and gates instead [C345]: RFC-0006 was written from repeated agent failure modes [C322]; a silently shipped placeholder became proposed shared rule 15 (RFC-0048, still open) [C317]–[C319]; a review of 196 performance issues concluded that point fixes kept regressing and opened a tracking issue for one systemic fix per root cause [C346], [C347]. Capability limits are handled by rules — say when you cannot build or test, return "unsupported" instead of faking [C320], [C321] — and by a corpus of PSDs made in Photoshop by their own scripts as the test oracle [C324]. Reversals happen by revert: five merged photocraft PRs were reverted in one burst on 2026-10-25; for one, #1199, the stated reason was a shared AI layer created after its acceptance [C333], [C335], [C336]. AutoCraft encodes the surprises: hold/close verdicts, a `sure` flag, owner statements, a classifier escalation ladder, an off switch, daily limits, circuit breakers on red pushes and an outside-author surge breaker [C301]–[C315].

**Velocity and cost.** No repo is steady: weekly coefficient of variation is 0.54–0.80 everywhere with weekly activity, 1.38 for music-intel-mcp [C416]. Raw throughput favours storytold by an order of magnitude (photocraft ~641 merged PRs a week vs redrobot 43.5, jarvis 26.5), but photocraft has 543 PR authors; per author per repo the busiest photocraft author is near 55 a week vs ~40 for redrobot's lead and ~25 for jarvis [C401], [C403], [C404], [C411], [C413], [C417]. ArtCraft, their only repo with a 26-week history and a small team, merged 15.6 a week [C418]. No cost figure is published on either side: AutoCraft runs its Claude calls on several logged-in Claude Code accounts signed in through claude.ai and caps work by daily item counts per step [C420]–[C424], [C427]; ours is a now-superseded design doc citing Max subscription limits plus six CLI-reported AFK-lane run costs totalling $15.99, with no per-PR figure [C430]–[C432].

**What to take.** (1) Keep the redrobot organization plan, with the reasons narrowed to the admin role and enforced checks; Pro on the owner's account is the fallback only if a second admin can wait [C151], [C153]. (2) Add a circuit breaker to the agent merge path — stop after 2 of the last 10 pushes turned a required check red, resume only by a person [C312] — a mechanism that matters once agents merge unattended; it needs its own issue before any build. Nothing else in this report calls for a change: our decision and research records are already more complete than theirs [C240]–[C243], [C220], [C223].

## Findings

### Q1 — storytold repository, protection and CI configuration; GitHub plan gating for a private repo — answered with a gap

- **C101** [measured] storytold is a GitHub Organization (display name ArtCraft, blog getartcraft.com), created 2021-01-03, with 82 public repos — Own measurements, L1-M1
- **C102** [measured] The org's plan is not visible to a non-member: `orgs/storytold` returns plan null and is_verified false — Own measurements, L1-M1
- **C103** [measured] Every repo listed by the public org listing is public (private=false), including artcraft, photocraft, autocraft, craft-contrib, craft-common-actions; craft repos default to main — Own measurements, L1-M2
- **C104** [measured] has_discussions is false on artcraft, photocraft, autocraft, craft-contrib and craft-common-actions; has_wiki is true — Own measurements, L1-M3
- **C105** [measured] Merge settings (allow_squash/merge/rebase, allow_auto_merge, delete_branch_on_merge) come back null for a pull-only caller, so they are not observable from outside — Own measurements, L1-M3
- **C106** [measured] GET branches/main/protection returns 404 Not Found for all five repos (non-admin caller); the legacy endpoint cannot show whether classic protection exists — Own measurements, L1-M4
- **C107** [measured] An organization-level ruleset "Protect main" (id 26661234, source storytold, enforcement active) applies to artcraft, photocraft and craft-common-actions; it targets ~DEFAULT_BRANCH — Own measurements, L1-M4, L1-M5
- **C108** [measured] "Protect main" contains only three rules: deletion, non_fast_forward, and pull_request with required_approving_review_count 0, require_code_owner_review false, allowed_merge_methods merge/squash/rebase; no required_status_checks rule and no bypass actors visible — Own measurements, L1-M5
- **C109** [measured] autocraft and craft-contrib have no ruleset at all and branches/main reports protected=false; rules/branches/main returns an empty list for both — Own measurements, L1-M4, L1-M9
- **C110** [measured] Repo-level rulesets lock auxiliary branches: photocraft "release" (creation/update/deletion/non_fast_forward on refs/heads/release) and artcraft "main-historical" (same four rules) — Own measurements, L1-M5
- **C111** [measured] No required status checks are configured on any sampled default branch: branches/main shows required_status_checks contexts [] and enforcement_level off; active rules on photocraft main are deletion, non_fast_forward, pull_request only — Own measurements, L1-M4, L1-M9
- **C112** [inference] storytold's protection makes PRs mandatory on main for the protected repos but enforces no CI result and no approval; CI is advisory as far as GitHub-enforced gates go — from [C108], [C111]
- **C113** [measured] No CODEOWNERS file exists at CODEOWNERS, .github/CODEOWNERS or docs/CODEOWNERS in any of the five repos — Own measurements, L1-M6
- **C114** [measured] Merges into photocraft main are merge commits (2 parents, committer GitHub, "Merge pull request #15616 from aiongg/..."); sampled closed PRs had auto_merge null; most PRs come from forks — Own measurements, L1-M10
- **C115** [measured] craft-common-actions holds 21 workflows (gate, house-rules, release, sonarcloud, supply-chain, freebsd, nix, flatpak-oci, docker-build and others, plus test-* self-tests) — Own measurements, L1-M6
- **C116** [measured] Every sampled shared workflow (gate, house-rules, release, sonarcloud, supply-chain, changed-paths, freebsd, windows-arm64, nix) triggers only on workflow_call — they are reusable workflows — Own measurements, L1-M7
- **C117** [quoted] The shared gate is the suite's quality gate run on PRs and pushes to main, one job per OS running cargo xtask ci, and app workflows are meant to call only this repo's workflows — "an app's workflows only call this repository's workflows" — [S1], header comment, lines 3-7
- **C118** [measured] All sampled shared workflows use GitHub-hosted runners (ubuntu-24.04, ubuntu-latest, ubuntu-22.04-arm, windows-latest, windows-11-arm, macos-15-xlarge); no workflow in craft-common-actions contains "self-hosted" — Own measurements, L1-M7, L1-M8
- **C119** [measured] photocraft ci.yml triggers on push to main, pull_request (opened/synchronize/reopened/labeled) and workflow_dispatch, and calls storytold/craft-common-actions gate.yml@main and git-sources.yml@main plus shared composite actions, all pinned to @main — Own measurements, L1-M8
- **C120** [measured] photocraft release.yml runs on push to the release branch, a nightly cron dry run (28 2 * * *), and workflow_dispatch; contents and packages write permissions — Own measurements, L1-M8
- **C121** [measured] Dependabot (.github/dependabot.yml) is present in all five repos; photocraft's groups all cargo updates and all github-actions updates into one daily PR each; no renovate.json found — Own measurements, L1-M6, L1-M8
- **C122** [inference] Release process is branch-driven: pushing to a ruleset-locked release branch triggers photocraft's release workflow — from [C110], [C118], [C120]
- **C123** [quoted] Classic protected branches: public repos on Free/Free-org; public and private on Pro, Team, Enterprise — "Protected branches are also available in public and private repositories with GitHub Pro, GitHub Team, GitHub Enterprise Cloud, and GitHub Enterprise Server." — [S2], Who can use this feature
- **C124** [quoted] Same page, Free tier — "Protected branches are available in public repositories with GitHub Free and GitHub Free for organizations." — [S2], Who can use this feature
- **C125** [quoted] Rulesets: public repos on Free; public and private on Pro, Team, Enterprise Cloud — "Rulesets are available in public repositories with GitHub Free and GitHub Free for organizations, and in public and private repositories with GitHub Pro, GitHub Team, and GitHub Enterprise Cloud." — [S3], Who can use this feature
- **C126** [quoted] The rulesets page body ties rulesets to Team/Enterprise customers, which reads narrower than its own availability box — "applies to a repository or to multiple repositories in an organization for customers on GitHub Team and GitHub Enterprise plans" — [S4], intro
- **C127** [quoted] Organization-wide rulesets: Team or Enterprise — "For customers on GitHub Team or GitHub Enterprise plans you can create rulesets in your organization" — [S5], intro
- **C128** [inference] storytold runs an organization-level ruleset (C107), and docs place org rulesets on Team or Enterprise (C127), so storytold is likely on a paid org plan; not confirmed — Free orgs may get org rulesets for public repos without the docs saying so — from [C102], [C107], [C127]
- **C129** [quoted] Required status checks are part of protected branches; once enabled all must pass before merge — "After enabling required status checks, all required status checks must pass before collaborators can merge changes into the protected branch." — [S2], Require status checks before merging
- **C130** [quoted] Pro includes required reviewers, protected branches and code owners for private repos — "Advanced tools and insights in private repositories" (Pro list: Required pull request reviewers, Multiple pull request reviewers, Protected branches, Code owners) — [S6], GitHub Pro
- **C131** [quoted] Free for organizations gives private repos only a limited feature set; its additions are support, team access controls and Actions compute — no protected branches — "unlimited private repositories with a limited feature set" — [S6], GitHub Free for organizations
- **C132** [quoted] Team adds required reviewers, team reviewers, protected branches and code owners for private repos — "In addition to the features available with GitHub Free for organizations, GitHub Team includes:" (list incl. Required pull request reviewers, Team pull request reviewers, Protected branches, Code owners) — [S6], GitHub Team
- **C133** [quoted] CODEOWNERS: public on Free; public and private on Pro/Team/Enterprise — "You can define code owners in public repositories with GitHub Free and GitHub Free for organizations, and in public and private repositories with GitHub Pro, GitHub Team, GitHub Enterprise Cloud, and GitHub Enterprise Server." — [S7], Who can use this feature
- **C134** [quoted] Pricing page: repository rules and code owners are Free = public repositories only, Team = included — "Repository rules Enforce restrictions on how code branches are merged, including requiring reviews by selected collaborators, or allowing only specific contributors to work on a particular branch. Free Public repositories Team Included" — [S8], comparison table, Code workflow
- **C135** [quoted] Auto-merge: private repos need Pro, Team or Enterprise — "Auto-merge for pull requests is available in public repositories with GitHub Free and GitHub Free for organizations, and in public and private repositories with GitHub Pro, GitHub Team, GitHub Enterprise Cloud, and GitHub Enterprise Server." — [S9], Who can use this feature
- **C136** [quoted] Merge queue: any public org repo, private only on Enterprise Cloud; personal-account repos excluded — "Pull request merge queues are available in any public repository owned by an organization, or in private repositories owned by organizations using GitHub Enterprise Cloud." — [S10], Who can use this feature
- **C137** [quoted] A personal-account repo has only two permission levels, owner and collaborator — "A repository owned by a personal account has two permission levels: the repository owner and collaborators." — [S11], intro
- **C138** [quoted] The single owner holds full control; collaborators get read+write — "Repositories owned by personal accounts have a single owner who has full control of the repository." — [S11], Owner access
- **C139** [quoted] Docs point to an org transfer for finer access — "If you require more granular access to a repository owned by your personal account, consider transferring the repository to an organization." — [S11], note
- **C140** [quoted] Org repositories have an Admin repository role with full access incl. destructive actions — "**Admin:** Recommended for people who need full access to the project, including sensitive and destructive actions like managing security or deleting a repository" — [S12], roles list
- **C141** [prior] The org Admin repository role is available on GitHub Free for organizations (no plan gate); docs page fetched did not state a plan box — not fetched in this run
- **C142** [quoted] Repo-level self-hosted runners exist for personal repos; registering one needs the repo owner — "To add a self-hosted runner to a user repository, you must be the repository owner." — [S13], Adding to a repository
- **C143** [quoted] Org-level self-hosted runners serve many repos and need an org owner — "You can add self-hosted runners at the organization level, where they can be used to process jobs for multiple repositories in an organization." — [S13], Adding to an organization
- **C144** [quoted] Runner groups availability box names Team and Free orgs — "organizations using GitHub Team or GitHub Free plans can create and manage additional runner groups using self-hosted runners." — [S14], Who can use this feature
- **C145** [quoted] The same page's body says only Team org owners can create extra groups — contradicts C144 — "All organizations have a single default runner group. Organization owners using the GitHub Team plan can create additional organization-level runner groups." — [S15], About runner groups
- **C146** [quoted] Discussions: any repo or org admin enables them; the about page names no plan restriction — "an administrator must enable GitHub Discussions for the repository or organization first." — [S16], About discussions
- **C147** [prior] GitHub Discussions are available on private repositories on all plans including Free — not fetched in this run
- **C148** [quoted] A 2023 report: a Pro user's private repo showed rules would not be enforced until moving to a Team/Enterprise org — contradicts C123/C125 for Pro — "Your rules won't be enforced on this private repository until you move to a GitHub Team or Enterprise organization account" — [S17], opening post, 2023-07-11
- **C149** [quoted] A 2025 user moved private repos from an individual (education) account to an org and lost branch-protection enforcement — "before transferring there was little-to-no indication that transferring the repositories would result in dropping enforcement of branch protection rules, previously established." — [S18], opening post, 2025-09-23
- **C150** [quoted] Reply in the same thread (community, not staff-confirmed) — "Currently, branch protection for private repositories is included only with GitHub’s Team and Enterprise plans, which is why you’re seeing the limitation when using an organization." — [S18], reply
- **C151** [inference] By GitHub's docs, for a private repo: Free personal — no enforced checks; Free org — still no enforced checks, with an org Admin repository role whose docs page names no plan gate (that it needs no paid plan is the unchecked [C141]); Pro personal — enforced checks but no second admin (a 2023 report says otherwise for Pro [C148]); Team org — both. One 2025 user who moved private repos to an org lost protection — from [C123], [C124], [C131], [C132], [C137], [C140], [C149]

- **C152** [measured] redrobot is a private repo owned by a personal (User) account; its master branch-protection endpoint answers 404 and its rulesets endpoint answers 403 "Upgrade to GitHub Pro or make this repository public to enable this feature."; collaborators are one admin (the owner) and three with write — Own measurements, M1
- **C153** [quoted] redrobot's own plan records the reason for the organization: the admin role cannot be granted on a personal private repo, and Pro on the personal account covers everything except that every setting goes through the owner — "Admin-роль на личном приватном репо выдать нельзя (проверено), Pro на личном аккаунте закрывает всё, кроме «любая настройка только через Сергазы»." — [S56], §3.1
- **C154** [quoted] The CODEOWNERS part of the redrobot plan was cancelled on 14.10 by #2523 (the PR author merges) — "Отменено решением 14.10 (#2523): PR мержит автор" — [S56], §3.4
- **C155** [measured] Of the 40 most recently merged photocraft PRs, 12 show a failed, cancelled or unfinished check on their head commit when read on 2026-11-18, after merge; the shared `gate / gate (ubuntu-24.04)` is among the failed checks — Own measurements, M2
- **C156** [quoted] The redrobot plan also needs admin for the self-hosted runners, and a second organization owner would cover token approvals and billing — "раннерам нужен admin, второй владелец закрывает ещё и одобрение токенов и биллинг на случай недоступности" — [S56], §3.2

### Q2 — project lifecycle: stack, decisions, research, design changes, experiments, original products — answered with a gap

- **C201** [quoted] ArtCraft founder/CEO Brandon Thomas, at AI Engineer Code Summit, called Rust "probably essential" and said high-quality creative apps need something native, contrasting it with Electron — "for high-quality creative apps, you really need something that's native." — [S19], section "Rust is key, but there have been technical challenges"
- **C202** [quoted] Thomas said Rust expertise is not needed because agents write it — "Do you need to know Rust to start using Rust today as an engineer? Definitely not. [...] Your agents will drive it just fine." — [S20], same section
- **C203** [quoted] Thomas drew a human/agent split: humans do backend work, schema migrations and API design; agents get desktop apps, games and anything "basically immutable" — "If you're doing backend work or things that require schema migrations [or] API design, let your humans do that." — [S20], same section
- **C204** [quoted] PhotoCraft began from a detailed prompt outlining Photoshop's tools, data structures and importers, followed by a "large, large prompt" to build the application; a "pretty good approximation" came within 24 hours — "laid out a large, large prompt to say, let's build out the application." — [S20], section "PhotoCraft: The development process"
- **C205** [quoted] The clone-first strategy is a stated product decision to match Adobe's UI for artist muscle memory, with original "more agentic" apps planned only afterwards — "So we are going for Adobe, their interface and 'look and feel' directly." — [S20], section "PhotoCraft: The development process"
- **C206** [quoted] PhotoCraft's AGENTS.md fixes the stack as a rule: Rust only, no JS/TS, no Tauri/Electron/webview; native egui/eframe on wgpu, web = same Rust to WASM — "Never add Tauri (or any webview/JS UI framework) as a dependency, build step or packaging target." — [S21], line 56 (project overview)
- **C207** [quoted] PhotoCraft's goal is defined against the reference app: 1:1 Photoshop parity plus better performance and agent-drivability — "The goal is 1:1 Photoshop parity (same menus, shortcuts, behaviour and file fidelity) with better performance, and every feature drivable by agents." — [S21], line 56
- **C208** [quoted] The compiler is used as a guardrail: workspace forbids unsafe, one isolated exception crate, and crash-prone clippy lints are denied in production crates — "The workspace sets `unsafe_code = \"forbid\"`." — [S21], line 108; deny list at line 27
- **C209** [quoted] A further compile-time guard: the format crate deliberately fails to compile when a doc struct gains a field, so nothing is silently dropped from saves — "`photocraft-format` deliberately fails to compile when a `photocraft-doc` struct gains a field" — [S21], section 8 "Keeping the native format complete"
- **C210** [quoted] Rust-only is a suite-wide rule; RFC-0006 grants a documented Tauri/TypeScript exception only to the PR-review tool — "This exception does not relax the native Craft apps' Rust-only rule." — [S22], "Applicability"
- **C211** [quoted] Clean-room method: study the reference app for behaviour and look only; implement from public specs and observation — "We studied Photoshop and other proprietary editors for *behaviour and look only*." — [S21], line 118 (rule 3)
- **C212** [quoted] Tests are the gate, and the PSD corpus results and a never-lowered parity floor must not regress — "Keep the PSD corpus results and the parity floor (`crates/ui-egui/src/parity.rs`) from regressing." — [S21], line 119 (rule 4); "raise FLOOR ... (never lower it)" line 144
- **C213** [measured] AutoCraft, the internal tool, is TypeScript on Node 24, not Rust — the Rust-only rule binds the native Craft apps, not the infrastructure — Own measurements, L2-M5
- **C214** [inference] Stack choice in the clone apps is a suite-wide rule the founder stands behind (Rust native, no webview), justified by performance and agent-writability; no written comparison of alternatives turned up in the documents read or the searches run — from [C201], [C202], [C206], [C210]
- **C215** [quoted] Suite-wide decisions live as RFC files in craft-contrib, a repo with rules and decisions only, no application code — "The Craft apps — PhotoCraft, WordCraft, EffectCraft, VectorCraft and the rest — share one set of rules and one way to make decisions together. This repository holds both." — [S23], intro
- **C216** [quoted] RFC-0000 scope: changes to craft-contrib and decisions affecting several apps go through RFC PRs with a 3- or 7-day comment period — "decisions that affect several apps, are made through RFCs" — [S24], body
- **C217** [quoted] Owners (org admins) can override the RFC process: decide objections, merge or close early — "An owner can decide an objection, or merge or close an RFC early, and says why on the PR." — [S24], last bullet
- **C218** [measured] craft-contrib was created 2026-10-15, about two weeks after the first clone apps (2026-09-30); it holds 21 RFC files and saw 65 PRs (30 merged) in its first month, so the RFC process was added after the apps existed — Own measurements, L2-M1, L2-M3, L2-M10
- **C219** [quoted] Per-app implementation decisions in PhotoCraft go to a dated docs/decisions.md that names alternatives and reasons — "Carrying the security-relevant parts across needs platform calls that have no safe API in `std`, and the workspace forbids `unsafe`, so each platform took a dependency rather than an exception." — [S25], entry "2026-10-17"
- **C220** [measured] PhotoCraft's docs/decisions.md holds only 2 entries against 83 top-level docs files (parity, gap, performance and plan docs among them) and 421 branches — Own measurements, L2-M4, L2-M9
- **C221** [quoted] Shared house rules are copied verbatim into every repo's AGENTS.md because agents may not follow links — "linking alone is not enough because agents may not follow links." — [S22], "Source and validation"
- **C222** [quoted] In Craft Anything, design decisions are marked inline on roadmap items and wait for a maintainer — "anything marked **decision** waits for a maintainer" — [S26], "Parallel agents" (line ~87)
- **C223** [measured] AutoCraft has no decision log, ADR, RFC or roadmap file; its docs are specs and operations (pipeline, dashboard-spec, ui-design, operations, migration) — Own measurements, L2-M5
- **C224** [quoted] PhotoCraft keeps research notes in a gitignored local `plan/` notebook, explicitly optional — "`plan/` is an optional gitignored notebook (research, parity notes, estimates)." — [S21], section 7 "Where things are tracked"
- **C225** [quoted] Craft Anything's devlog is a local gitignored scratch record; shared knowledge must go to the PR, STATUS or ROADMAP — "the devlog is a local scratch record; anything others need goes in the PR, `docs/STATUS.md` or `docs/ROADMAP.md`." — [S26], line ~164
- **C226** [measured] Committed investigation results in PhotoCraft take the form of per-topic measurement docs (~25 `*-performance.md`, benchmark JSON), not a research folder — Own measurements, L2-M4
- **C227** [quoted] RFC-0013 (amending an accepted RFC) was motivated by the expectation that shared rules change on contact with code — "Rules that apps adopt one by one, such as shared conventions, will change as they meet real code, so this will come up soon." — [S27], Motivation
- **C228** [quoted] The amendment mechanism is in use: RFC-0006 already carries an Updated-by link — "Updated by: [RFC-0040](0040-shared-library-first-guidance.md)" — [S22], header
- **C229** [quoted] Craft Anything's plan was rebuilt wholesale from the code state, with finished items moved to a history file — "Rebuilt on 2026-11-02 from `main` at `2e4afc5`, with v0.3.0 the latest release." — [S28], intro
- **C230** [quoted] PhotoCraft's roadmap is a living document with review/update stamps and a revision-history table — "**Last reviewed:** 2026-10-11 · **Last updated:** 2026-11-12" — [S29], header; "Revision history"
- **C231** [quoted] Large technical changes get a standalone plan doc, marked historical once implemented — "The original planning record below is historical." — [S30], top status update 2026-10-25
- **C232** [quoted] In PhotoCraft the reference app fixes the target; agents pick work from measured gaps in a fixed priority order — "Priorities: important infrastructure first, then low-hanging parity, then the long tail." — [S21], section 4 "Picking work"
- **C233** [measured] No branch named for experiments, spikes or prototypes exists in photocraft, craft-anything, autocraft or craft-contrib, and no such path in photocraft's tree; only the older original product artcraft has experimental/* branches and a user-facing Experimental settings pane — Own measurements, L2-M4, L2-M7, L2-M9
- **C234** [snippet] ArtCraft (original product) prototyped its 3D layout in Bevy before switching to Three.js for early-stage productivity — "We'd previously prototyped and worked in Bevy (a Rust game engine), but Three.js is much more productive for our early stages." — [S31], search snippet (page not read)
- **C235** [quoted] AutoCraft is an original product, a model harness for backlog maintenance, first written for the craft apps — "AutoCraft is a model harness for maintaining GitHub repositories with a large backlog." — [S32], intro
- **C236** [quoted] Thomas described AutoCraft as an autonomous software factory to be open-sourced — "AutoCraft is a completely autonomous software factory that we're going to open source." — [S20], section "Rust is key, but there have been technical challenges"
- **C237** [quoted] Craft Anything is a second original product (study a target, have an agent rebuild it) — "See how any website, app or game works, then have AI build your own version; an open-source, clean-room engine in pure Rust." — [S33], tagline
- **C238** [inference] Original products are run differently from clones: AutoCraft (infrastructure, TypeScript) has spec docs and no roadmap or decision log; Craft Anything replaces the parity target with an explicit roadmap carrying owners, claims and maintainer-only decision items; clones steer by parity metrics against the reference app — from [C203], [C207], [C213], [C222], [C223], [C229], [C232]
- **C239** [measured] The older original product artcraft mixes Rust and TypeScript (3263 .rs / 1666 .ts(x)), so the Rust-only rule is specific to the 2026 clone suite — Own measurements, L2-M8
- **C240** [measured] jarvis records decisions in quarterly journal shards (docs/decisions/2026-Q2/Q3/Q4.md, Q4 = 52 entries) plus per-grill artefact folders, 4 ADRs and 80 research files; docs/decisions/README.md does not exist — Own measurements, L2-M12
- **C241** [quoted] redrobot keeps one file per decision in docs/decisions/, so decisions are visible to all collaborators rather than one person's machine-local memory — "Журнал живёт в репо, чтобы решения видели все collaborator'ы, а не только машинно-локальная память одного человека." — [S34], intro (private repo, read via gh)
- **C242** [quoted] redrobot keeps an experiments journal for its RL/sand research, whose rule is that research direction must rest on documented past experiments, failures included — "решения по направлению исследования **обязаны опираться на задокументированные результаты прошлых экспериментов** — включая неудачные." — [S35], "Регламент" (private, via gh)
- **C243** [measured] redrobot also keeps docs/plans (122) and docs/research (65); music-intel-mcp has no decisions folder and no experiments lane, only 1 research file and 27 docs/domain files incl. architectural-decisions.md and open-questions.md — Own measurements, L2-M12

### Q3 — dead ends and surprises — answered with a gap

- **C301** [quoted] AutoCraft's Opus review has four verdicts; hold means a person is needed and close means the PR is beyond a small fix — "hold | Needs a person: unclear reference behaviour, design or scope choice, too large" — [S36], ## Review, verdict table
- **C302** [quoted] A diff over the review call's length limit is held without any model call — "A diff over the call's length limit, or no diff from GitHub: held (\"too large for the final review\") without a model call." — [S36], ## Review, Too large
- **C303** [quoted] Opus returns a `sure` flag; an unsure take never merges without an operator's Merge? answer and the unsureness sticks across AutoCraft's own pushes — "It never merges without an operator's Merge? answer, and the Merge? summary says Opus was unsure. Unsure sticks" — [S36], ## Review, Unsure
- **C304** [quoted] Hand-off by verdict: close becomes a Close this PR? decision for a person, hold waits for a person — "close to a \"Close this PR?\" decision (answered yes, Act closes it), hold waits for a person." — [S36], end of ## Review
- **C305** [quoted] Owner memory: operators' past statements are embedded and shown to reviews of related PRs (up to five, cosine >= 0.7) — "What the operators said once is kept and shown to the reviews of related work." — [S36], ## Merge queue, Owner memory
- **C306** [quoted] A PR whose review names a conflict with an owner statement is kept off the automatic merge rule — "neither the review nor the pre-merge review at the head names a conflict with an owner statement" — [S36], ## Merge queue, merge-rule conditions (line 336)
- **C307** [quoted] The documented list of what needs a person: scope calls, reference behaviour public sources don't settle, merges outside the rule, closing a PR, label disagreements, duplicates — "**Reference behaviour** that public sources don't settle." — [S36], ## What needs a person
- **C308** [quoted] Classifier escalation ladder: Sonnet referee, then Opus when Sonnet is unsure; if Opus is unsure too the item becomes a scope question for a person — "When Opus is unsure too, the label stands and the item is asked as a scope question." — [S36], ## What needs a person
- **C309** [quoted] A Backlog (Later) answer parks a question undecided and holds the item out of every later stage — "Answering it holds the question undecided" — [S36], ## Decide, Backlog
- **C310** [quoted] Kill switch: the pipeline starts Off and an operator switch stops all automatic writes except the security deep scan — "The pipeline's on/off switch stops all of them except the security deep scan." — [S36], ### What AutoCraft does on its own
- **C311** [quoted] Daily limits per stage, 0 pauses a stage; defaults include Fix 10, Merge 10, Review (Opus) 40 — "Empty means no limit; 0 pauses the stage." — [S36], ### Daily limits
- **C312** [quoted] Circuit breaker: a push stage stops when 2 of its last 10 pushes turned a required check red, the merge path stops when its merge reddens main or a post-merge review finds a defect; only an operator resumes it — "A push stage (fix-up, CI fix, fix issue) stops when 2 of its last 10 pushes turned a required check red" — [S36], ### Waits, Circuit breaker row
- **C313** [quoted] Conflict handling gives up after two tries and holds the PR — "\"conflict: held\" after 2 tries" — [S36], ## Merge queue (line ~362)
- **C314** [quoted] Outside-author surge breaker: more than 30 new outside items an hour halts model work for them until an operator resumes, no timer — "Until an operator resumes it (the Resume button on the Pipeline page); no timer" — [S36], ### Waits, Outside surge breaker row
- **C315** [quoted] Per-PR cost cap on Opus review: at most 3 calls per PR per UTC day including failed calls — "Cap: at most 3 Opus calls per PR per UTC day, counting new heads, re-runs, and failed calls" — [S36], ## Review, Waits before a review
- **C316** [quoted] Operator releases exist for items that stopped waiting for a person, including retrying a failed issue fix — "*Try the fix again* (a skipped or failed issue fix; the attempt count starts over)" — [S36], ## What needs a person, Releases
- **C317** [quoted] A LightCraft Subject selection tool shipped as a centre-weighted contrast heuristic standing in for the intended model-backed segmentation, without telling the user — "uses a center-weighted local-contrast heuristic rather than the intended model-backed subject segmentation" — [S37], issue body, Concrete examples, LightCraft
- **C318** [quoted] The issue author framed silent placeholders as a risk specific to a suite built by autonomous agents — "visibly incomplete functionality can reinforce perceptions of superficial, AI-generated software" — [S37], issue body, Motivation
- **C319** [quoted] The standalone PR #45 was closed in favour of RFC-0048 (one shared AGENTS.md, PR #72, still open on 2026-11-18), whose proposed rule 15 covers it — "You SHOULD NOT present unsupported, partial or placeholder behaviour as success" — [S38], FredApps closing comment
- **C320** [quoted] PhotoCraft code rule: unfinished features return an unsupported error rather than panicking — "Unfinished features return an \"unsupported\" error." — [S39], Rust rules, Non-test code never panics (line 107)
- **C321** [quoted] Shared agent rule: an agent that cannot build or run tests locally must tell its human and rely on CI — "If you cannot build or run the tests locally, say so to the human running you" — [S40], ## Proposal, point 2
- **C322** [quoted] RFC-0006 was written from observed repeated agent failure modes across hundreds of issues: duplicates, already-fixed bugs, stale drafts, invented functions — "duplicate PRs, fixes for bugs already fixed on `main`, PRs left as drafts, or code that uses functions that don't exist" — [S40], ## Motivation
- **C323** [quoted] Accountability for agent output sits with the human running it — "The person running the agent reads review comments and answers them, and is accountable for what the agent opens." — [S40], ## Proposal, point 9
- **C324** [quoted] Reference behaviour is pinned by a corpus of PSDs made in Adobe Photoshop by the team's own scripts, each storing Photoshop's own rendering as the test oracle — "PSDs made in Adobe Photoshop by our own scripts. Each file stores Photoshop's rendering of" — [S41], header block
- **C326** [quoted] PhotoCraft's stop-and-ask list is narrow: agents keep working on everything except licensing, publishing, releases, remotes, secrets, money, destructive git and hard-to-undo acts — "Otherwise keep working." — [S39], shared rules, point 9 (line 14)
- **C327** [measured] Closed-unmerged PRs are a minority but not rare: photocraft 1011 vs 4539 merged (about 18 percent of closed PRs), artcraft 281 vs 1674, craft-libs 149 vs 1208; autocraft 0 of 13 — Own measurements, L3-M1
- **C328** [measured] Commit search finds 74 commits matching revert in photocraft (13901 commits on main), 10 in craft-libs, 0 in artcraft and autocraft; many hits are branch-level or use the word in feature text — Own measurements, L3-M2, L3-M3
- **C329** [measured] In a sample of six recent closed-unmerged photocraft PRs, four gave a reason — superseded by a better PR, already fixed on main, folded into a combined PR, and conflicts after code moved to craft-libs — and two gave none; none cited an agent unable to do the work — Own measurements, L3-M4
- **C330** [quoted] A PR was closed because main had already fixed the issue, with the closer stating what was and was not checked — "I did not check opening the dialog by double-clicking a layer row" — [S42], qvest-ssels closing comment
- **C331** [quoted] A large multi-part PR was closed as unlandable: part had moved to craft-libs, parts superseded, the needed part relanded alone as a new PR — "As a single PR this can't land against today's `main`, and part of it is already handled elsewhere." — [S43], FredApps comment
- **C332** [quoted] Rescoping by revert on a branch: a commit was reverted so one part lands standalone and the rest is rescoped to a separate issue — "so the GPU viewport streaming lands standalone. The import work is rescoped separately in #5331 (EXR streaming only)." — [S44], commit message
- **C333** [measured] On 2026-10-25 five merged PRs were reverted on photocraft main in one burst (#1199, #9454, #4573, #9455, #9183); a later commit restores code that the main revert dropped — Own measurements, L3-M3, L3-M5
- **C334** [quoted] A contributor commit records collateral damage from that revert and repairs it — "Main reverted the earlier #9455 merge, which also removed the AHD changes that came in with it" — [S45], commit message
- **C335** [quoted] PR #1199 (local ML models in a PhotoCraft-only crate) was pulled from integration batch 8 because a shared AI layer had been created after the PR was accepted — "we've taken this PR out of integration batch 8, because local models in PhotoCraft should most likely go through the shared [craft-ai-integrations]" — [S46], davidmann4, 2026-10-25 14:25 UTC
- **C336** [quoted] The reversal was explained against the timeline of the earlier acceptance — "you accepted this on Oct 9, two days before craft-ai-integrations was created (Oct 11)" — [S46], davidmann4, 2026-10-25
- **C337** [measured] GitHub reports #1199 as MERGED while main also carries the revert of its merge (both ancestors of main), so the reversal shows only in commits and comments, not the PR state — Own measurements, L3-M5
- **C338** [quoted] Cross-app decisions go through RFCs in craft-contrib; an owner can decide an objection or close an RFC early and must say why — "An owner can decide an objection, or merge or close an RFC early, and says why on the PR." — [S47], body
- **C339** [quoted] Reversals are recorded IETF-style: an accepted RFC is never edited, a new RFC Updates or Obsoletes it and a back-link is added — "An accepted RFC is not edited. A later RFC changes it and says so under its title, with `Updates:` or `Obsoletes:`" — [S48], ## Summary
- **C340** [quoted] RFC-0013 expected shared rules to change on contact with real code — "Rules that apps adopt one by one, such as shared conventions, will change as they meet real code, so this will come up soon." — [S48], ## Motivation
- **C341** [quoted] An earlier rules system, craftrules, was retired and replaced by the house rules — "**`craftrules` is retired.** Its old tree is not published here. The house" — [S40], rollout list (line ~215)
- **C342** [quoted] RFC-0006 carries an Updated-by back-link to RFC-0040, the mechanism in use — "Updated by: [RFC-0040](0040-shared-library-first-guidance.md)" — [S40], header
- **C343** [measured] 8 PRs in craft-contrib were closed unmerged, six of them RFCs (0002, 0004, 0005, 0011, 0018, 0028); RFC-0028 was closed as too small a part of what is needed — Own measurements, L3-M6
- **C344** [measured] No postmortem, incident, lessons or known-issues file found by path in photocraft, artcraft, craft-contrib or craft-libs; photocraft has docs/decisions.md of 2823 bytes holding two dated implementation decisions — Own measurements, L3-M7
- **C346** [quoted] Retrospective analysis lives in issues instead: a photocraft tracking issue reviewed 196 performance issues and found point fixes kept regressing — "Nearly every closed one was fixed one command or one code path at a time, so the same kinds of bug keep coming back" — [S49], issue body, brennanMKE, 2026-10-25
- **C347** [quoted] Its remedy is one systemic fix per root cause rather than further point fixes — "This issue tracks one systemic fix per root cause." — [S49], issue body
- **C348** [measured] Red main is handled as ordinary issues and PRs titled main is red (16 title hits org-wide), e.g. photocraft #15503 after a framework port — Own measurements, L3-M8
- **C345** [inference] Lessons are absorbed into rules and gates rather than written up as postmortems: RFC-0006 from repeated agent mistakes, issue #44 into a proposed rule 15 (RFC-0048, not yet accepted), AutoCraft breakers on red pushes — from [C322], [C319], [C312], [C344]

### Q4 — velocity and cost — answered with a gap

- **C401** [measured] storytold/photocraft (created 2026-09-30): 4,489 PRs merged in 7 weeks (28 Sep..15 Nov); per ISO week mean 641, median 547, max 1,360 (week of 5 Oct), CV 0.64, 0 zero weeks; series 47,1360,976,805,312,442,547: launch spike then a plateau of ~300-550/week — Own measurements, L4-M1, L4-M2
- **C402** [measured] photocraft default branch: 17,848 commits in 7 Sunday-weeks (mean 2,550, median 2,570, max 3,953, CV 0.47); about 4 commits per merged PR — Own measurements, L4-M1
- **C403** [measured] photocraft is a crowd, not a team: 543 distinct PR authors in the window; top 5 authors hold 24% of merged PRs, top 10 hold 36%; 260 authors merged exactly one PR; median 2 PRs per author; 3 bot-authored PRs — Own measurements, L4-M1
- **C404** [measured] photocraft's busiest single author merged 382 PRs in 7 weeks (~55 per week); the commit author with the most commits on main is the login "claude" (4,519 commits in the window); 496 distinct commit authors — Own measurements, L4-M1
- **C405** [measured] photocraft merges in batches: 900 of 4,489 merged PRs share their exact merge second with at least one other PR; no other measured repo has any — Own measurements, L4-M1
- **C406** [measured] photocraft selection and backlog: 291 PRs closed unmerged in the window vs 4,489 merged (~6% of closed); 1,783 PRs open on 2026-11-18 — Own measurements, L4-M3
- **C407** [measured] storytold/craft-anything (created 2026-10-31): 1,015 PRs merged in 3 weeks (26 Oct..15 Nov), series 82,427,506; mean 338, median 427, CV 0.54; 996 commits on main (series 12,467,517); 102 distinct PR authors, top 5 = 54% of PRs, 52 authors with one PR; 33 closed unmerged, 184 open now — Own measurements, L4-M1, L4-M3
- **C408** [measured] storytold/artcraft (created 2022): 406 PRs merged in 26 weeks, 401 into main; mean 15.6, median 11.5, max 46, CV 0.80, 1 zero week; series runs 19-46/week from mid-May to mid-July, 9-28/week from mid-July to mid-August, then 0-14/week from mid-August, with 22 in the last week; 9 distinct PR authors, top 5 = 97% — Own measurements, L4-M1, L4-M4
- **C409** [measured] artcraft commit_activity is not usable as velocity: main was reset on 2026-09-11 (root commit "ArtCraft Desktop (fresh start)", 0 parents), so only 62 commits on main since 18 May and 17 of 26 weeks read zero while PRs kept merging — Own measurements, L4-M4
- **C410** [measured] storytold/autocraft (created 2026-11-05) is developed by direct pushes, not PRs: 2 merged PRs vs 1,034 commits on main in its first two Sunday-weeks (871, 163); one human login authored 1,046 commits; 5 commit authors — Own measurements, L4-M1
- **C411** [measured] Osasuwu/jarvis: 688 PRs merged in 26 weeks; mean 26.5, median 22, max 79, CV 0.67, 0 zero weeks; series 44,55,18,13,23,9,37,19,12,24,36,79,48,46,27,21,32,17,12,9,33,41,14,5,8,6 (last 4 weeks 5-14); commits on main mean 28.8, median 27.5, max 73, CV 0.64, 1 zero week — Own measurements, L4-M1
- **C412** [measured] jarvis team size: one human PR author (656 PRs) plus 32 Dependabot PRs; commit authors are the human login, "claude" (524), a CI bot (151) and Dependabot; 58 PRs closed unmerged, 8 open now — Own measurements, L4-M1, L4-M3
- **C413** [measured] SergazyNarynov/redrobot: 1,130 PRs merged in 26 weeks; mean 43.5, median 32.5, max 134 (last week), CV 0.75, 0 zero weeks; last 4 weeks 105,22,115,134 (rising); commits on main mean 44.6, median 36.5, max 122, CV 0.71 — Own measurements, L4-M1
- **C414** [measured] redrobot team size: two human PR authors, one with 1,033 of 1,130 PRs (91%); four commit authors incl. "claude" (1,044 commits); 59 closed unmerged, 19 open now — Own measurements, L4-M1, L4-M3
- **C415** [measured] Osasuwu/music-intel-mcp: 108 PRs merged in 26 weeks; mean 4.2, median 1.5, max 23, CV 1.38, 12 zero weeks; commits mean 4.1, median 0.5, 13 zero weeks; one human author — Own measurements, L4-M1
- **C416** [inference] Steadiness: none of the measured repos is steady; CV is 0.54-0.80 for every repo with weekly activity and 1.38 for music-intel-mcp. jarvis and redrobot have no zero weeks; music-intel-mcp is bursty (half its weeks empty); photocraft shows a launch spike followed by a lower plateau, while craft-anything's three weeks rise (82, 427, 506) — from [C401], [C407], [C408], [C411], [C413], [C415]
- **C417** [inference] Raw repo throughput favours storytold by an order of magnitude (photocraft ~641 PRs/week vs redrobot 43.5 and jarvis 26.5), but per author per repo the gap narrows sharply: photocraft's busiest author ~55 PRs/week vs ~40/week for the redrobot lead and ~25/week for jarvis's single author; photocraft's volume comes from hundreds of outside contributors — from [C401], [C403], [C404], [C411], [C412], [C413], [C414]
- **C418** [inference] The storytold flagship with a 26-week history and a small team (artcraft, 9 authors) merged fewer PRs per week (15.6) than jarvis (26.5) or redrobot (43.5) in the same window; the high-velocity storytold repos are weeks old and crowd-sourced — from [C408], [C411], [C413], [C401], [C407]
- **C419** [quoted] AutoCraft states its pipeline is designed around maintainer attention, not token spend — "The pipeline is built around maintainers' judgement, which is the limited resource, not around token cost." — [S32], intro, paragraph 2
- **C420** [quoted] AutoCraft runs Claude calls under logged-in Claude Code accounts, each a config directory — "Each account is a Claude Code config directory that is logged in." — [S32], Claude accounts
- **C421** [quoted] AutoCraft's account scheduler tracks each account's 5-hour and weekly usage limits and prefers the least-used account, i.e. it spreads load across several subscription accounts — "Before each call, the runner picks an enabled account with a free slot and headroom (5-hour and weekly use under the pause levels, which operators set; default 80 % for both; a reading older than 30 minutes counts as unknown), preferring the lowest weekly use." — [S50], Claude accounts and agent runs
- **C422** [quoted] Sign-in is the claude.ai login flow, which ties accounts to Claude subscription plans — "*Sign in* runs `claude auth login --claudeai` for that account's config directory" — [S50], Claude accounts and agent runs
- **C423** [quoted] AutoCraft caps work with a daily limit per step — "each step has a daily limit." — [S32], safety list
- **C424** [quoted] Default daily limits on a new database include Review (Opus) 40, Fix 10, Fix-up 20, Merge 10, Verify 30, Classify 2000, Duplicates 2000 — "| Review (Opus) | 40 | Act | 20 |" — [S50], Daily limits table
- **C425** [quoted] Model per stage: Opus for review, pre-merge and post-merge review; Sonnet/Opus/Haiku for fix and fix-up; Jev and Haiku for classify and priority — "| Review | Opus reviews every wanted PR at its current head" — [S32], stages table
- **C426** [quoted] AutoCraft records token use and a dollar cost per agent run, but the dollar figure is what the CLI reports, not an invoice — "cost_usd REAL,                      -- as reported by the CLI; Jev: input tokens at TypeSafe's price" — [S51], table token_usage
- **C427** [inference] No published per-PR or per-month dollar figure for storytold's mode was found: AutoCraft records per-run cost locally but publishes none, and its Claude calls run on claude.ai logins, so their cost would be the number of accounts times the plan price, which is not stated anywhere read — from [C419], [C420], [C421], [C422], [C426]
- **C428** [quoted] A secondary write-up attributes the craft apps mostly to AI agents such as Claude Code, citing Phoronix — "reported on 7 October that the apps come mostly from AI agents such as Claude Code" — [S52], section on pace
- **C429** [quoted] An outside commentary on Craft Anything calls its release pace churn as well as momentum — "Six releases shipped in nine days, which is momentum and also churn." — [S53], body
- **C430** [quoted] Our side: a jarvis design doc, now marked superseded and historical, says scheduled tasks ran on Claude Max subscription limits with no added API cost — "All scheduled tasks use Claude Max subscription limits. No additional API costs." — [S54], Cost
- **C431** [quoted] Our side: a 2026-10-06 retrospective records CLI-reported costs for six AFK-lane runs (claude-code-action; a seventh failed without one), $0.51-$10.88 each, $15.99 total; not billed amounts — "sum of total_cost_usd: 15.99" — [S55], M8
- **C432** [inference] Neither side publishes a cost per merged PR; ours could be estimated only from subscription price over PR count, and the plan tier and number of seats are not recorded in the files read — from [C427], [C430], [C431]

## Disconfirming evidence

- [C151], [C123], [C125] (Pro enforces protection on a private personal repo) — query: `github private repository free plan branch protection "not enforced" upgrade required status checks` (gathering) and `GitHub Pro personal private repository branch protection rules not enforced required status checks` (main thread) — found against: a 2023 Pro user told rules would not be enforced until moving to a Team/Enterprise org [C148]; found for: a 2025 user whose individual (education) account enforced protection and lost it on moving to a Free org [C149]; redrobot's own 403 names Pro as the unlock [C152]. Unresolved between users; the docs side with Pro.
- [C144] vs [C145], [C125] vs [C126] — the docs contradict themselves on runner groups for Free orgs and on rulesets for Pro; both pairs reported, not averaged.
- [C112] (storytold's CI is advisory) — test: merged photocraft PRs whose head carried a failing check (M2) — 12 of 40, supports the claim [C155].
- [C214] (no written stack rationale) — queries: `Brandon Thomas ArtCraft PhotoCraft pure Rust agents why Rust`, `... software factory devlog OR blog how we decide architecture` — nothing against; only the conference write-up [C201]–[C203].
- [C215] (decisions live in craft-contrib RFCs) — query: `storytold craft-contrib RFC decisions ADR Brandon Thomas agents "decision"` — nothing about storytold returned; nothing against.
- [C233] (no experiments lane) — `git ls-remote` over all heads of five repos — ArtCraft is the counter-case and is reported as such [C233], [C234].
- [C344], [C345] (no postmortems) — search for postmortem/root-cause titles — one real retrospective, kept in an issue [C346]; the claim is narrowed to "no postmortem files".
- [C417], [C401] (storytold throughput is real, not spam) — query: `photocraft github pull requests slop low quality contributors bounty AI-generated PR flood` — nothing on photocraft; measured instead: 3 bot PRs, ~6% closed unmerged, 900 batch-merged [C403], [C405], [C406].
- [C427] (no published cost) — query: `Brandon Thomas ArtCraft Storyteller Claude Code accounts spend` — nothing about storytold.

## Coverage

| Channel | Read | Gap |
|---|---|---|
| Users | GitHub community threads [S17], [S18]; photocraft and craft-contrib PR/issue threads [S37], [S38], [S42], [S43], [S46], [S49] | no Hacker News thread on the storytold process found |
| Specialists | GitHub docs [S2]–[S16]; storytold AGENTS.md, RFCs, roadmaps, AutoCraft docs [S21]–[S36], [S39]–[S41], [S47]–[S51]; conference write-up [S19], [S20] | no first-hand blog or devlog by the founder found; the talk is known only through a write-up |
| Data | own gh measurements of rulesets, trees, PR and commit series (Own measurements) | no third-party data on agent-driven velocity or cost |
| Adversarial | Pro-enforcement complaints [S17]; outside commentary calling Craft Anything's pace churn [S53]; revert and closed-PR samples (L3-M1–M5) | no "why we moved off" write-up; Phoronix blocked by Cloudflare, cited through [S52] |

Declared overruns: Q1 read more than three full pages (one docs page per plan claim, as grep extracts) and made ~45 gh calls; Q3 ran 8 searches against a ceiling of 4 because each still returned new material; Q4 made ~75 gh calls (GitHub search caps at 1,000, photocraft needed 9 date windows) and 5 searches. No Actions run or job history was read. Measurement ids from the four gathering ledgers are prefixed with their ledger, L<n> for the ledger of Q<n> (L1-M1 …); M1 and M2 are the main thread's.

## Own measurements

### M1 — redrobot plan, protection and collaborators

Command: `gh api repos/SergazyNarynov/redrobot/branches/master/protection`; `gh api repos/SergazyNarynov/redrobot/rulesets`; `gh api repos/SergazyNarynov/redrobot --jq "{private, owner_type: .owner.type, visibility}"`; `gh api repos/SergazyNarynov/redrobot/collaborators --jq ".[] | [.login, .role_name] | @tsv"` (2026-11-18)
Output:
```
{"message":"Not Found",...,"status":"404"}
{"message":"Upgrade to GitHub Pro or make this repository public to enable this feature.",...,"status":"403"}
{"owner_type":"User","private":true,"visibility":"private"}
SergazyNarynov	admin
MikeZenko	write
Osasuwu	write
DaNi64j	write
```

### M2 — merged photocraft PRs with a failing check

Command: `python merged_red.py storytold/photocraft` — runs `gh pr list --repo storytold/photocraft --state merged --limit 40 --json number,mergedAt,statusCheckRollup` and counts PRs whose head rollup has a FAILURE/ERROR/CANCELLED/TIMED_OUT conclusion or an incomplete check (2026-11-18)
Output (trimmed to 4 of the 10 printed rows):
```
storytold/photocraft: 40 merged PRs sampled, 12 merged with a failed/cancelled/pending check
(15616, '2026-11-18T15:43:54Z', ['gate / gate (ubuntu-24.04)'], ['test (windows-latest, unit)', 'test (windows-latest, integration)'])
(15565, '2026-11-18T07:13:03Z', ['gate / gate (ubuntu-24.04)', 'sonarcloud / SonarCloud Scan', 'test (windows-latest, unit)', 'test (windows-latest, integration)'], ['CodeRabbit'])
(15510, '2026-11-18T15:04:49Z', ['gate / gate (ubuntu-24.04)', 'test (windows-latest, unit)', 'test (windows-latest, integration)', 'web build and wasm size gate'], [])
(15189, '2026-11-16T01:21:09Z', ['sonarcloud / SonarCloud Scan'], [])
```

<!-- ledger Q1 -->
### L1-M1

`gh api users/storytold` → type Organization, name ArtCraft, public_repos 82, created 2021-01-03. `gh api orgs/storytold` → plan null, is_verified false.

### L1-M2

`gh api "orgs/storytold/repos?per_page=100&type=public"` → 82 rows, all private=false; craft repos default branch main.

### L1-M3

`gh api repos/storytold/<r>` for artcraft, photocraft, autocraft, craft-contrib, craft-common-actions → allow_* and delete_branch_on_merge null; has_discussions false; has_wiki true; visibility public; permissions pull only.

### L1-M4

`gh api repos/storytold/<r>/rulesets` → artcraft: 26661234 "Protect main" (Organization), 22936628 "main-historical" (Repository); photocraft: 26661234, 24322531 "release"; craft-common-actions: 26661234; autocraft, craft-contrib: none. `.../branches/main/protection` → 404 Not Found ×5. `.../branches/main` → protected true (artcraft, photocraft, craft-common-actions), false (autocraft, craft-contrib); required_status_checks contexts [] enforcement_level off ×5.

### L1-M5

`gh api repos/storytold/photocraft/rulesets/26661234` → include ~DEFAULT_BRANCH; rules deletion, non_fast_forward, pull_request{required_approving_review_count 0, require_code_owner_review false, allowed_merge_methods [merge,squash,rebase]}; bypass_actors null. rulesets/24322531 → refs/heads/release: creation, update, deletion, non_fast_forward. artcraft rulesets/22936628 → refs/heads/main-historical: same four.

### L1-M6

`gh api repos/storytold/<r>/contents/<path>` for CODEOWNERS, .github/CODEOWNERS, docs/CODEOWNERS, .github/dependabot.yml, renovate.json, .github/renovate.json → only .github/dependabot.yml found, in all five. `.../contents/.github/workflows` → craft-common-actions 21 files, photocraft 11, autocraft 3, craft-contrib 3.

### L1-M7

`curl raw.githubusercontent.com/storytold/craft-common-actions/main/.github/workflows/<f>.yml | grep on:/runs-on` → gate, house-rules, release, sonarcloud, supply-chain, changed-paths, freebsd, windows-arm64, nix: `on: workflow_call` only; runners ubuntu-24.04/ubuntu-latest/macos-15-xlarge/windows-latest/windows-11-arm/ubuntu-22.04/ubuntu-22.04-arm.

### L1-M8

grep "self-hosted" over 16 craft-common-actions workflows → no hits. photocraft ci.yml: on push [main], pull_request types [opened,synchronize,reopened,labeled], workflow_dispatch; `uses: storytold/craft-common-actions/.github/workflows/gate.yml@main` and git-sources.yml@main. photocraft release.yml: schedule cron "28 2 * * *", push branches [release], workflow_dispatch. dependabot.yml: cargo + github-actions, daily 06:00 America/New_York, grouped "*".

### L1-M9

`gh api repos/storytold/<r>/rules/branches/main` → photocraft: deletion, non_fast_forward, pull_request (all Organization:storytold); autocraft, craft-contrib: empty.

### L1-M10

`gh api repos/storytold/photocraft/commits?per_page=8` → 0376ac1 and d039f54 have 2 parents, "Merge pull request #15616 from aiongg/ci-speed-windows", committer GitHub. `pulls?state=closed&per_page=8` → auto_merge null on all; heads mostly forks.

<!-- ledger Q2 -->
### L2-M1

`gh api "orgs/storytold/repos?per_page=100"` (2 pages): 82 repos. Craft-app repos (photocraft, pdfcraft, filmcraft, vectorcraft, lightcraft) all created 2026-09-30; designcraft/effectcraft 10-01; gridcraft/cadcraft/deckcraft/soundcraft/wordcraft 10-07; figcraft/craft-libs/craft-launcher 10-09; craft-contrib 10-15; craft-skills 10-30; craft-anything 10-31; autocraft 11-05; craft-wiki 11-06. artcraft (main product) created 2022-03-31. storyteller-bevy desc "Danny's Bevy exploration" (2023-09-28). Descriptions repeat "written from scratch in pure Rust" / "clean-room ... in pure Rust".

### L2-M2

`gh api repos/storytold/<r>/git/trees/main?recursive=1` saved locally (none truncated). Blob counts: autocraft 985, craft-anything 1182, photocraft 2953, craft-wiki 1116, artcraft 5848, craft-contrib 34, craft-skills 1 (README only).

### L2-M3

craft-contrib tree: `rfcs/` holds 21 files (0000,0003,0006,0013,0014,0015,0017,0020-0027,0029-0031,0034,0035,0040) — gaps in numbering; `standards/` 6 files (accessibility, house-rules-accessibility, house-rules-core, house-rules-rust, naming, time). No application code.

### L2-M4

photocraft tree: `docs/*.md` top level = 83 files, incl. docs/decisions.md (2 dated entries: 2026-10-10, 2026-10-17), docs/roadmap.md, docs/gaps.md, docs/target-app-parity.md, 6 `*-parity.md`, ~25 `*-performance.md`, `*-plan.md` (canvas-rotation-shortcuts-plan, egui-037-migration-plan), docs/benchmarks/. Also an mdBook `book/src/` (architecture/, security/, formats/). grep for experiment|spike|sandbox|prototype|adr|rfc in paths: 0 hits.

### L2-M5

autocraft tree: language TypeScript (Node 24, pnpm, `src/*.ts`, `web/` React-tsx); docs/ = dashboard-spec, deploy-checklist, how-it-works, migration, operations, pipeline, stage-summaries, ui-design. No ROADMAP, no decisions/ADR/RFC file; "decision" paths are product code (src/decisions.ts, web/src/modules/decisions/) — the product's own maintainer-decision inbox. AGENTS.md is 1127 bytes.

### L2-M6

craft-anything tree: Rust (Cargo workspace, apps/, crates/, xtask). docs/ROADMAP.md (305 KB), docs/STATUS.md, docs/roadmap-history.md, docs/pitfalls.md, docs/design-system.md; per-agent docs (claude-code.md, codex.md, copilot.md, grok.md, opencode.md). No ADR/RFC dir.

### L2-M7

artcraft tree: docs/ = desktop-session-regression, performance(+ dated before/after json), website-login; ROADMAP.md; nested AGENTS.md files; frontend `ExperimentalSettingsPane.tsx`, `experimental-store.ts`, `ExperimentalConfirmModal.tsx` (user-facing experimental toggles).

### L2-M8

file-extension counts from M2 trees: photocraft .rs 2478 / .ts 0; artcraft .rs 3263 / .ts(x) 1666; autocraft .rs 0 / .ts(x) 915.

### L2-M9

branch heads via `git ls-remote --heads` (no API): photocraft 421, craft-anything 262, artcraft 1326, autocraft 5, craft-contrib 16. Names matching experiment/spike/proto/sandbox/research/poc/explor: photocraft 0, craft-anything 0, autocraft 0, craft-contrib 0; artcraft 6 (bt-research-preview, experimental/experimental-menu, experimental/moodboard-bringup, experimental/scene-descriptor-enhancement, speedup-experiments, worktree-mcp-mvp-spike).

### L2-M10

`gh api repos/storytold/craft-contrib/pulls?state=all&per_page=100`: 65 PRs, 27 open, 30 merged (repo created 2026-10-15).

### L2-M11

craft-anything docs/ROADMAP.md: 15 occurrences of the `**decision**` marker. photocraft docs/roadmap.md has a "Revision history" table (2026-10-11, 2026-11-12, both "minor ... estimates unchanged"); docs/gaps.md header "Last updated 2026-11-10" with an inline change log.

### L2-M12

comparison trees (`gh api repos/<o>/<r>/git/trees/<default>?recursive=1`, none truncated). Osasuwu/jarvis (main, 482 blobs): docs/decisions 19 files = 2026-Q2/Q3/Q4.md shards + 16 under docs/decisions/grill/<date-topic>/; docs/research 80 files (69 distinct top-level entries); docs/adr 4 (0001-0004); no docs/plans; 3 "experiment" paths (2 research docs on hardware-experiment methodology, 1 test). `docs/decisions/README.md` → HTTP 404. 2026-Q4.md = 93 KB, 52 `###` entries. SergazyNarynov/redrobot (master, 4277 blobs): docs/decisions 266 files (one file per decision `YYYY-MM-DD-<slug>.md` + README.md); docs/plans 122; docs/research 65; docs/experiments 4 (README, TEMPLATE, 001-pure-rl-tqc-sand-leveling, reference/rl-architecture-debate) plus redrobot/experiments.py and ~16 tests/experiments files. Osasuwu/music-intel-mcp (main, 195 blobs): no docs/decisions; docs/research 1 file (replay-process-loopback-drm-2026-11-02.md); docs/domain 27 files incl. architectural-decisions.md and open-questions.md; 0 experiment paths.

<!-- ledger Q3 -->
### L3-M1

`gh api -X GET search/issues -f q="repo:storytold/<r> is:pr <state>" --jq .total_count` (2026-11-18). photocraft merged 4539, closed-unmerged 1011, open 1783; artcraft 1674/281/153; craft-libs 1208/149/506. `gh pr list --repo storytold/autocraft`: 13 merged, 0 closed-unmerged, 0 open; craft-contrib 30 merged, 8 closed-unmerged, 27 open.

### L3-M2

GraphQL defaultBranchRef history totalCount: photocraft 13901, craft-libs 3792, artcraft 62 (artcraft main has only 62 commits, so its commit search says little). `search/commits q="repo:storytold/<r> revert"` total_count: photocraft 74, craft-libs 10, artcraft 0, autocraft 0.

### L3-M3

first 40 photocraft revert hits include 2026-10-25 bb39b4a8d Revert "Merge PR #1199...", 92f592684 (#9454), c01dc04b5 (#4573), 0134d2dc7 (#9455), 02074c9a8 (#9183), 6ab5c0775 (#1199/#4097 integration); 2026-10-26 1e52abfb2 "raw: restore the LabF pair table that the main revert dropped"; branch-level: 25f21db89 (#5332 rescope), 2de7a9c04, 27e0735af, 23f1b8bce, 947d4fd1b, f3ce2e2b9, 459a25bd9, 70cb31610; roughly a third of the 40 are not reverts.

### L3-M4

`gh pr list --repo storytold/photocraft --state closed --search "is:unmerged sort:updated-desc" --limit 40`, then last comments of #15134, #13274, #15589, #15473, #15310, #8506. #15134 fixed on main by #15449; #15473 "Folded into #15474, since each fix alone leaves main red"; #15310 closed in favour of #15311 with "stronger evidence"; #8506 superseded/moved to craft-libs; #13274, #15589 (draft) no closing reason.

### L3-M5

`gh pr view 1199 --json state,mergedAt` -> MERGED 2026-10-26T00:04:44Z. `gh api repos/storytold/photocraft/compare/bb39b4a8d...main` -> ahead, behind=0; same for merge commit 5f2a7b99 -> both on main. Revert committed 2026-10-25T14:19:27Z, explaining comment 14:25.

### L3-M6

`gh pr list --repo storytold/craft-contrib --state closed --search is:unmerged`: #57, #45, #42 (RFC-0028), #29 (RFC-0018, reopened on current main), #14 (RFC-0011), #6 (RFC-0005), #5 (RFC-0004), #3 (RFC-0002). #42: "Closing this since it's too small a part of what we really need."

### L3-M7

`gh api repos/storytold/<r>/git/trees/HEAD?recursive=1` paths grepped for postmortem, lesson, known-issue, incident, retro, decision, adr: photocraft docs/decisions.md; craft-contrib rfcs/0000-decision-process.md; none in artcraft, craft-libs. `curl .../photocraft/HEAD/docs/decisions.md | wc -c` = 2823, entries dated 2026-10-10 and 2026-10-17.

### L3-M8

`search/issues q='org:storytold "main is red" OR "broke main" in:title'` total 16 (photocraft #10173, #15503 "16 failing tests after the #15449 framework port", gridcraft #4190, pdfcraft #6934). `q='org:storytold postmortem OR post-mortem OR "root cause" in:title'` total 3: photocraft #9327, photocraft #7700, pdfcraft #5287.

<!-- ledger Q4 -->
### L4-M1

velocity bucketing. Script: C:\Users\petrk\AppData\Local\Temp\rs2\q4_velocity.py; output m_velocity.txt.
Inputs: `gh pr list --repo <r> --state merged --search "merged:<from>..<to>" --limit 1000 --json mergedAt,author` in non-overlapping date windows (the search caps at 1,000, so photocraft was split into 9 windows, craft-anything 6, redrobot 5; the others fit one query); `gh api -i repos/<r>/stats/commit_activity` and `.../stats/contributors` (several 202s, each retried once and got 200).
Trimmed output:
```
photocraft  2026-09-28..11-15 PRs/wk {weeks 7, total 4489, mean 641.3, median 547, max 1360, cv 0.64, zero 0}
            authors 543, bot 3, top5 0.24, top10 0.36, single-PR authors 260; batch-merged 900/4489
            commits/wk {7, 17848, mean 2549.7, median 2570, max 3953, cv 0.47}; committers 496 (top: claude 4519)
craft-anything 10-26..11-15 PRs/wk {3, 1015, 338.3, 427, 506, cv 0.54}; authors 102, top5 0.54
            commits/wk {3, 996, 332.0, 467, 517, cv 0.68}
artcraft    05-18..11-15 PRs/wk {26, 406, 15.6, 11.5, 46, cv 0.80, zero 1}; authors 9, top5 0.97
            commits/wk {26, 59, 2.3, 0.0, 22, cv 1.99, zero 17}
autocraft   11-02..11-15 PRs/wk {2, 2}; commits/wk [871, 163]; committers 5
jarvis      05-18..11-15 PRs/wk {26, 688, 26.5, 22.0, 79, cv 0.67, zero 0}; authors 2 (human 656, dependabot 32)
            commits/wk {26, 749, 28.8, 27.5, 73, cv 0.64, zero 1}; committers 5 (claude 524)
redrobot    05-18..11-15 PRs/wk {26, 1130, 43.5, 32.5, 134, cv 0.75, zero 0}; authors 2 (lead 1033)
            commits/wk {26, 1159, 44.6, 36.5, 122, cv 0.71, zero 0}; committers 4 (claude 1044)
music-intel 05-18..11-15 PRs/wk {26, 108, 4.2, 1.5, 23, cv 1.38, zero 12}
            commits/wk {26, 107, 4.1, 0.5, 28, cv 1.55, zero 13}
```
A first run deduplicated on (mergedAt, author) and undercounted photocraft by 395 because batch merges share a second; dedup was removed (the windows do not overlap). Corrected totals match M3's search counts exactly.

### L4-M2

repo creation dates (`gh api repos/<r> --jq .created_at`): photocraft 2026-09-30, craft-anything 2026-10-31, autocraft 2026-11-05, artcraft 2022-03-31, jarvis 2026-01-16, redrobot 2026-02-28, music-intel-mcp 2025-02-03.

### L4-M3

`gh api -X GET search/issues -f q="repo:<r> is:pr is:merged merged:2026-05-18..2026-11-15"` / `is:closed is:unmerged closed:...` / `is:pr is:open`:
```
photocraft     merged=4489 closed_unmerged=291 open_now=1783
craft-anything merged=1015 closed_unmerged=33  open_now=184
jarvis         merged=688  closed_unmerged=58  open_now=8
redrobot       merged=1130 closed_unmerged=59  open_now=19
```

### L4-M4

artcraft: merged PRs by base branch in the window `{main: 401, design/premium-website: 5}`; `gh api "repos/storytold/artcraft/commits?sha=main&since=2026-05-18T00:00:00Z&per_page=100" --jq length` = 62; oldest of those: `2026-09-11T18:19:51Z parents=0 ArtCraft Desktop (fresh start)`.

## Open questions

- Q1 — no new information — whether GitHub Pro really enforces rulesets and required checks on a private personal repo [C148] vs [C123]; settled by enabling Pro on a throwaway private repo and trying a red-check merge, or by GitHub support.
- Q1 — not fetched — which plans carry the organization Admin repository role and Discussions on private repos [C141], [C147] are priors; settled by the GitHub plans comparison table.
- Q1 — not researched — whether any mechanism other than branch protection or rulesets can bind a human's merge on a private repo on a Free plan (the user's "can the same be achieved by another mechanism" question); no claim in this run answers it; settled by a dedicated run on GitHub merge controls available on Free.
- Q2 — not readable — the ArtCraft Bevy-prototype source (ProductHunt) sat behind a Cloudflare challenge, so [C234] is unchecked; settled by another copy of that page or the ArtCraft repo history.
- Q2 — gap — the experiments-lane check outside photocraft looked at branch names only, not at paths or docs; settled by a tree search for `experiment` in craft-anything, autocraft and artcraft.
- Q3 — pending — rule 15 is proposed in RFC-0048 (craft-contrib PR #72, open on 2026-11-18), not adopted; settled when #72 merges or closes.
- Q2 — ceiling — 17 of 21 RFCs and 27 open RFC PR threads unread; the deliberation lives in those threads.
- Q3 — ceiling — only 6 of 1,011 closed-unmerged photocraft PRs read for their reason; a larger sample would test "no closure cites agent incapacity".
- Q4 — no new information — no published cost on either side; settled for us by recording the subscription tier and seat count against PR counts.
- Next runs, proposed (not researched here): (1) how storytold integrates crowd PRs in batches — the "integration batch" process and who resolves conflicts [C335], [C405]; (2) test oracles in agent-built apps — reference corpora and parity floors [C212], [C324] — and whether redrobot can use recorded robot runs the same way; (3) how house rules are kept identical across ~20 repos (the SHA check) and whether our three repos need the same; (4) clean-room and licensing discipline when an agent studies a reference product; (5) how storytold handles security and supply chain (sonarcloud, supply-chain workflow, Dependabot grouping) vs our gitleaks plus minimum release age; (6) how AutoCraft is dogfooded on its own repo with direct pushes; (7) onboarding — how 543 outside authors learn the rules, and what that implies if redrobot gains collaborators.

## Sources
- [S1] https://raw.githubusercontent.com/storytold/craft-common-actions/main/.github/workflows/gate.yml — passage
- [S2] https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches — passage
- [S3] https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets — passage
- [S4] https://docs.github.com/api/article/body?pathname=/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets — passage
- [S5] https://docs.github.com/en/organizations/managing-organization-settings/creating-rulesets-for-repositories-in-your-organization — passage
- [S6] https://docs.github.com/en/get-started/learning-about-github/githubs-plans — passage
- [S7] https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners — passage
- [S8] https://github.com/pricing — passage
- [S9] https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/incorporating-changes-from-a-pull-request/automatically-merging-a-pull-request — passage
- [S10] https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue — passage
- [S11] https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/repository-access-and-collaboration/permission-levels-for-a-personal-account-repository — passage
- [S12] https://docs.github.com/en/organizations/managing-user-access-to-your-organizations-repositories/managing-repository-roles/repository-roles-for-an-organization — passage
- [S13] https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/add-runners — passage
- [S14] https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/manage-access — passage
- [S15] https://docs.github.com/api/article/body?pathname=/en/actions/how-tos/manage-runners/self-hosted-runners/manage-access — passage
- [S16] https://docs.github.com/api/article/body?pathname=/en/discussions/collaborating-with-your-community-using-discussions/about-discussions — passage
- [S17] https://github.com/orgs/community/discussions/60566 — passage
- [S18] https://github.com/orgs/community/discussions/174400 — passage
- [S19] https://latent.space/p/artcraft (Richard MacManus, 2026-11-12; same page as S20) — passage
- [S20] https://latent.space/p/artcraft — passage
- [S21] https://github.com/storytold/photocraft/blob/main/AGENTS.md — passage
- [S22] https://github.com/storytold/craft-contrib/blob/main/rfcs/0006-coding-agents.md — passage
- [S23] https://github.com/storytold/craft-contrib/blob/main/README.md — passage
- [S24] https://github.com/storytold/craft-contrib/blob/main/rfcs/0000-decision-process.md — passage
- [S25] https://github.com/storytold/photocraft/blob/main/docs/decisions.md — passage
- [S26] https://github.com/storytold/craft-anything/blob/main/AGENTS.md — passage
- [S27] https://github.com/storytold/craft-contrib/blob/main/rfcs/0013-amending-rfcs.md — passage
- [S28] https://github.com/storytold/craft-anything/blob/main/docs/ROADMAP.md — passage
- [S29] https://github.com/storytold/photocraft/blob/main/docs/roadmap.md — passage
- [S30] https://github.com/storytold/photocraft/blob/main/docs/egui-037-migration-plan.md — passage
- [S31] https://www.producthunt.com/@echelon/reviews — snippet only
- [S32] https://github.com/storytold/autocraft/blob/main/README.md — passage
- [S33] https://github.com/storytold/craft-anything/blob/main/README.md — passage
- [S34] https://github.com/SergazyNarynov/redrobot/blob/master/docs/decisions/README.md — passage
- [S35] https://github.com/SergazyNarynov/redrobot/blob/master/docs/experiments/README.md — passage
- [S36] https://raw.githubusercontent.com/storytold/autocraft/HEAD/docs/pipeline.md — passage
- [S37] https://github.com/storytold/craft-contrib/issues/44 — passage
- [S38] https://github.com/storytold/craft-contrib/pull/45 — passage
- [S39] https://raw.githubusercontent.com/storytold/photocraft/HEAD/AGENTS.md — passage
- [S40] https://raw.githubusercontent.com/storytold/craft-contrib/HEAD/rfcs/0006-coding-agents.md — passage
- [S41] https://raw.githubusercontent.com/storytold/photocraft-corpus/HEAD/README.md — passage
- [S42] https://github.com/storytold/photocraft/pull/15134 — passage
- [S43] https://github.com/storytold/photocraft/pull/8506 — passage
- [S44] https://github.com/storytold/photocraft/commit/25f21db89 — passage
- [S45] https://github.com/storytold/photocraft/commit/1e52abfb2 — passage
- [S46] https://github.com/storytold/photocraft/pull/1199#issuecomment-6398842098 — passage
- [S47] https://raw.githubusercontent.com/storytold/craft-contrib/HEAD/rfcs/0000-decision-process.md — passage
- [S48] https://raw.githubusercontent.com/storytold/craft-contrib/HEAD/rfcs/0013-amending-rfcs.md — passage
- [S49] https://github.com/storytold/photocraft/issues/9327 — passage
- [S50] https://github.com/storytold/autocraft/blob/main/docs/pipeline.md — passage
- [S51] https://github.com/storytold/autocraft/blob/main/src/schema.sql — passage
- [S52] https://jacar.es/en/artcraft-crafting-apps-open-source-rust/ — passage
- [S53] https://ibl.ai/blog/craft-anything-clean-room-rebuild-software-moat — passage
- [S54] https://github.com/Osasuwu/jarvis/blob/main/docs/design/autonomous-loop.md — passage
- [S55] https://github.com/Osasuwu/jarvis/blob/main/docs/research/afk-orchestration-retrospective-2026-10-06.md — passage
- [S56] https://github.com/SergazyNarynov/redrobot/blob/master/docs/plans/team-workflow.md — read in full (private repo, via the GitHub API)

## Audit

| Claim | Verdict | Note |
|---|---|---|
| C101 | SUPPORTED | re-run: type Organization, blog getartcraft.com |
| C102 | SUPPORTED |  |
| C103 | PARTIAL | re-run shows 3 of 5 repos Apache-2.0; "most Apache-2.0" dropped |
| C104 | SUPPORTED |  |
| C105 | SUPPORTED |  |
| C106 | SUPPORTED |  |
| C107 | SUPPORTED | re-run: ruleset enforcement active |
| C108 | SUPPORTED |  |
| C109 | SUPPORTED |  |
| C110 | SUPPORTED |  |
| C111 | SUPPORTED |  |
| C112 | SUPPORTED |  |
| C113 | SUPPORTED |  |
| C114 | SUPPORTED |  |
| C115 | SUPPORTED | re-run: 21 workflow files |
| C116 | SUPPORTED |  |
| C117 | SUPPORTED |  |
| C118 | SUPPORTED | re-run: no self-hosted runner in any of the 21 workflows |
| C119 | SUPPORTED |  |
| C120 | SUPPORTED |  |
| C121 | SUPPORTED |  |
| C122 | PARTIAL | release target list not in the named measurement; dropped |
| C123 | SUPPORTED |  |
| C124 | SUPPORTED |  |
| C125 | SUPPORTED |  |
| C126 | SUPPORTED |  |
| C127 | SUPPORTED |  |
| C128 | SUPPORTED |  |
| C129 | SUPPORTED |  |
| C130 | SUPPORTED |  |
| C131 | SUPPORTED |  |
| C132 | SUPPORTED |  |
| C133 | SUPPORTED |  |
| C134 | SUPPORTED |  |
| C135 | SUPPORTED |  |
| C136 | SUPPORTED |  |
| C137 | SUPPORTED |  |
| C138 | SUPPORTED |  |
| C139 | SUPPORTED |  |
| C140 | SUPPORTED |  |
| C141 | UNCHECKABLE | prior; plan box for the Admin role not stated on the fetched page |
| C142 | SUPPORTED |  |
| C143 | SUPPORTED |  |
| C144 | SUPPORTED |  |
| C145 | SUPPORTED |  |
| C146 | SUPPORTED |  |
| C147 | UNCHECKABLE | prior, not fetched in this run |
| C148 | SUPPORTED |  |
| C149 | SUPPORTED |  |
| C150 | SUPPORTED |  |
| C151 | PARTIAL | docs-based only; rewritten to say the Admin-on-Free part rests on unchecked C141 and that C148 contradicts Pro enforcement |
| C152 | SUPPORTED |  |
| C153 | SUPPORTED | read via gh api on private redrobot |
| C154 | SUPPORTED | read via gh api on private redrobot |
| C155 | PARTIAL | M2 reads the check rollup after merge, not at merge, and counts cancelled/unfinished checks; gate is among the failures, not in all; rewritten |
| C156 | SUPPORTED | read via gh api on private redrobot |
| C201 | PARTIAL | source says "probably essential"; hedge restored |
| C202 | SUPPORTED |  |
| C203 | PARTIAL | "by reversibility" not in source; source says "basically immutable"; rewritten |
| C204 | PARTIAL | source gives two prompts, not one; rewritten |
| C205 | SUPPORTED |  |
| C206 | SUPPORTED |  |
| C207 | SUPPORTED |  |
| C208 | SUPPORTED |  |
| C209 | SUPPORTED |  |
| C210 | SUPPORTED |  |
| C211 | SUPPORTED |  |
| C212 | PARTIAL | "not human design review" not in source; dropped |
| C213 | PARTIAL | SQLite not in L2-M5; dropped |
| C214 | PARTIAL | "pre-made" and "any repo" overstate the searches; dropped |
| C215 | SUPPORTED |  |
| C216 | SUPPORTED |  |
| C217 | SUPPORTED |  |
| C218 | SUPPORTED |  |
| C219 | SUPPORTED |  |
| C220 | PARTIAL | "most choices sit in ..." is interpretation; narrowed to the doc count |
| C221 | SUPPORTED |  |
| C222 | SUPPORTED |  |
| C223 | SUPPORTED |  |
| C224 | SUPPORTED |  |
| C225 | SUPPORTED |  |
| C226 | SUPPORTED |  |
| C227 | PARTIAL | source gives only the motivation; the never-edited rule is C339, summary now cites C339 |
| C228 | SUPPORTED |  |
| C229 | SUPPORTED |  |
| C230 | SUPPORTED |  |
| C231 | SUPPORTED |  |
| C232 | SUPPORTED |  |
| C233 | PARTIAL | branch names checked in 4 repos, paths only in photocraft; narrowed |
| C234 | UNCHECKABLE | ProductHunt page behind a Cloudflare challenge |
| C235 | SUPPORTED |  |
| C236 | SUPPORTED |  |
| C237 | SUPPORTED |  |
| C238 | PARTIAL | "kind of backend Thomas assigns to humans" not in source; dropped |
| C239 | SUPPORTED |  |
| C240 | SUPPORTED |  |
| C241 | SUPPORTED | read via gh api on private redrobot |
| C242 | PARTIAL | journal is for RL/sand research, not a general research-direction rule; rewritten; read via gh api |
| C243 | SUPPORTED |  |
| C301 | SUPPORTED |  |
| C302 | SUPPORTED |  |
| C303 | SUPPORTED |  |
| C304 | SUPPORTED |  |
| C305 | SUPPORTED |  |
| C306 | SUPPORTED |  |
| C307 | SUPPORTED |  |
| C308 | SUPPORTED |  |
| C309 | SUPPORTED |  |
| C310 | SUPPORTED |  |
| C311 | SUPPORTED |  |
| C312 | SUPPORTED |  |
| C313 | SUPPORTED |  |
| C314 | SUPPORTED |  |
| C315 | SUPPORTED |  |
| C316 | SUPPORTED |  |
| C317 | SUPPORTED |  |
| C318 | SUPPORTED |  |
| C319 | PARTIAL | PR #72 (RFC-0048) still open on 2026-11-18; rule 15 is proposed, not adopted |
| C320 | SUPPORTED |  |
| C321 | SUPPORTED |  |
| C322 | SUPPORTED |  |
| C323 | SUPPORTED |  |
| C324 | PARTIAL | corpus is made in Photoshop by the team's own scripts, not "human-built"; rewritten |
| C325 | UNSUPPORTED | inference does not follow from C324/C307 and admits the README does not say it; removed |
| C326 | SUPPORTED |  |
| C327 | SUPPORTED |  |
| C328 | SUPPORTED |  |
| C329 | PARTIAL | only four of six gave a reason (#13274, #15589 none); rewritten |
| C330 | SUPPORTED |  |
| C331 | SUPPORTED |  |
| C332 | SUPPORTED |  |
| C333 | SUPPORTED |  |
| C334 | SUPPORTED |  |
| C335 | SUPPORTED | quote is in S46 with the repo name as a markdown link; script misses it because of the link syntax |
| C336 | SUPPORTED |  |
| C337 | SUPPORTED |  |
| C338 | SUPPORTED |  |
| C339 | SUPPORTED |  |
| C340 | SUPPORTED |  |
| C341 | SUPPORTED |  |
| C342 | SUPPORTED |  |
| C343 | SUPPORTED |  |
| C344 | SUPPORTED |  |
| C345 | PARTIAL | rule 15 is proposed, not adopted; rewritten |
| C346 | SUPPORTED |  |
| C347 | SUPPORTED |  |
| C348 | SUPPORTED |  |
| C401 | SUPPORTED | value confirmed in m_velocity.txt (L4-M1) |
| C402 | SUPPORTED |  |
| C403 | SUPPORTED | value confirmed in m_velocity.txt (L4-M1) |
| C404 | SUPPORTED | value confirmed in m_velocity.txt (L4-M1) |
| C405 | SUPPORTED |  |
| C406 | SUPPORTED |  |
| C407 | SUPPORTED | value confirmed in m_velocity.txt (L4-M1) |
| C408 | PARTIAL | series has a middle phase (9-28/week mid-July to mid-August) the claim skipped; rewritten |
| C409 | SUPPORTED |  |
| C410 | SUPPORTED | value confirmed in m_velocity.txt (L4-M1) |
| C411 | SUPPORTED | value confirmed in m_velocity.txt (L4-M1) |
| C412 | SUPPORTED |  |
| C413 | SUPPORTED | value confirmed in m_velocity.txt (L4-M1) |
| C414 | SUPPORTED |  |
| C415 | SUPPORTED | value confirmed in m_velocity.txt (L4-M1) |
| C416 | PARTIAL | craft-anything rises (82, 427, 506), no spike then plateau; rewritten |
| C417 | PARTIAL | "per human" -> "per author per repo": the redrobot lead and jarvis's author are the same login (~65/week combined) |
| C418 | SUPPORTED |  |
| C419 | SUPPORTED |  |
| C420 | PARTIAL | "subscription logins, not an API key" not in source; rewritten to logged-in accounts as config directories |
| C421 | SUPPORTED |  |
| C422 | SUPPORTED |  |
| C423 | PARTIAL | pipeline.md also has a dollar cap (discord_search_daily_usd); "not by money" dropped |
| C424 | SUPPORTED |  |
| C425 | SUPPORTED |  |
| C426 | SUPPORTED |  |
| C427 | PARTIAL | C422 added to the from-list; cost-per-account reasoning kept as unstated inference |
| C428 | SUPPORTED |  |
| C429 | SUPPORTED |  |
| C430 | PARTIAL | S54 is marked "Superseded - historical reference only (#1959)"; rewritten |
| C431 | PARTIAL | six runs with a cost, a seventh failed; "only" dropped; rewritten |
| C432 | SUPPORTED |  |

Label verdict: open — Q1's unresolved Pro-enforcement conflict (C148 vs C123) would change the "Pro as fallback" recommendation, and the user's question whether another mechanism can replace branch protection is answered by no claim.

Quote check: Quote check storytold-project-side-2026-11-18.md: 110 quoted claim(s): 102 found, 1 NOT FOUND, 5 unfetchable, 2 no source

## Disposition

| Recommendation | State | Where |
|---|---|---|
| Keep the redrobot organization plan, with the reasons narrowed to the admin role and enforced checks; Pro on the owner's account is the fallback only if a second admin can wait | deferred | SergazyNarynov/redrobot#2256 — the existing tracking issue for the organization move; its steps are the repo owner's |
| Add a circuit breaker to the agent merge path — stop after 2 of the last 10 pushes turned a required check red, resume only by a person | dropped | No unattended agent merge lane runs today (the AFK lane is frozen since 2026-10-17, /orchestrate is interactive), so there is no incident to link, which a new gate needs under the user-level check-proposal rule; revisit if an unattended merge lane returns |
