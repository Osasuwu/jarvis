---
topic: artcraft-ecosystem-autocraft
tags: area:process, research
source_provenance: /research invocation in an interactive session, 2026-11-18, after the talk https://www.youtube.com/watch?v=UCL4K36SHp0
status: open
audit: 2026-11-18 — 91 claims: 81 SUPPORTED, 9 PARTIAL, 1 UNSUPPORTED, 0 UNCHECKABLE
---

## Question

Storytold / Brandon Thomas "Crafting Apps" ecosystem (photocraft, artcraft, autocraft, craftrules, их open-source agentic workflow) после видео https://www.youtube.com/watch?v=UCL4K36SHp0 (вышло ~2026-11-16). Нужно: таблица всех их продуктов/репо с кратким описанием и статусом OSS; autocraft — что это, выпущен ли OSS; как устроен их агентный workflow; сравнение с моим (jarvis + jarvis-private skills, построенные по советам Matt Pocock: grill, to-spec, to-tickets, implement, TDD, vertical slices); что стоит перенять/совместить; во что вступить как контрибьютор. Плюс интересные находки, о которых не спросили.

Asked for the talk's content, answering from the talk's published description, the repositories and public discussion because the YouTube transcript could not be fetched (HTTP 429 on every subtitle request, see M6).

Sub-questions: Q1 — what products and repositories ArtCraft/storytold has and their OSS status; Q2 — what AutoCraft is and whether it is open source; Q3 — how their agentic workflow is set up (rules, CI, coordination); Q4 — how it compares with Matt Pocock's current approach and where the two meet.

## Summary

AutoCraft is already public: `storytold/autocraft`, MIT or Apache-2.0, created 2026-11-05, a TypeScript harness that mirrors a repo's issues and PRs into a local database and runs Jev, Haiku, Sonnet and Opus over them to classify, dedupe, review, fix, verify and merge, asking maintainers for decisions [C201], [C202], [C204], [C218]. The talk's description calls it a "forthcoming" factory that also covers evaluations and post-training [C219]; the public pipeline doc has no evaluation or post-training stage yet [C220].

The ecosystem is seventeen open-source Rust apps, Craft Anything among them (study any software and have Claude Code build your own version), all Apache-2.0 per GitHub and all "Early alpha" or "In development"; ArtCraft itself (an AI image and video IDE); and a set of public tooling repos: `craft-contrib` (rules and RFCs), `craft-common-actions` (shared CI), Craft PR Review and Craft Status [C105], [C108], [C109], [C113], [C114], [C127]. Public testers on Hacker News called the apps very broken in October [C121], [C122]; quality is the open question, not openness.

Their published agent workflow is in `craft-contrib`: short house rules copied into every repo's root `AGENTS.md` and checked unchanged by a shared CI workflow [C304]–[C313]. The rules came from running agents on hundreds of issues across eleven repos [C303]. Inside PhotoCraft, rules are about the product (never panic, everything is a command, a parity floor that only rises), with a fuzz test over every command [C315]–[C323]. Whether the talk describes a different internal workflow is unknown: the talk could not be read.

Pocock moved the same way: his skills repo gained an in-progress `software-factory` skill (tickets → runs → merged code, with automated checks, automated review and human review as brakes) and a `chief-of-staff` skill with a session-outliving wiki [C401]–[C410]. The two describe the same shape [C413]; they differ in emphasis — ArtCraft's rules coordinate many contributors, Pocock's README centres alignment on a grilling session with the user [C414].

Recommendation (its jarvis side rests on no sourced claim, see Open questions): take specific pieces rather than switch modes. (1) Read AutoCraft's design as a concrete open reference for brakes on a merge pipeline — per-repo write approvals and an independent pre-merge Opus review [C207], [C212], [C415] — plus one audited write module and a post-merge review that files follow-ups [C206], [C213]. (2) Weigh AutoCraft as the project to contribute to: it already tracks repos of other owners without source edits [C205], and its contributor base is small [C218]. (3) Watch Pocock's `software-factory` skill, which is still in `in-progress` [C410]. A lightly supervised factory is a documented failure case [C418]; Horthy's answer is verifiers [C419].

## Findings

### Q1 — Products and repositories, OSS status — answered

- **C101** [quoted] The talk is "How I cloned Adobe with AI" by Brandon Thomas of ArtCraft, published by AI Engineer — "How I cloned Adobe with AI — Brandon Thomas, ArtCraft" — [S1], oEmbed title
- **C102** [quoted] The talk says the first Photoshop clone took about 24 hours — "ArtCraft’s first Photoshop clone took about 24 hours to build, Brandon Thomas says." — [S2], description
- **C103** [quoted] The talk covers MCP and CLI automation, Linux, reusable UI components and CI bottlenecks — "MCP and CLI automation, Linux support, reusable UI components and CI bottlenecks lead into Autocraft" — [S2], description
- **C104** [quoted] The talk has a section on human review and the AutoCraft factory — "17:35 - Human review and the Autocraft software factory" — [S2], description timestamps
- **C105** [quoted] The apps page lists seventeen open-source Rust apps — "Seventeen apps · Open source · Pure Rust" — [S3], header
- **C106** [quoted] Every app is drivable from a CLI, a JSON control channel or an MCP server — "Drive every app from a CLI, a JSON control channel or an MCP server, built for automation and AI agents." — [S3], Principles 05
- **C107** [quoted] PhotoCraft is pitched as an open-source image editor with a familiar interface — "The open-source image editor you already know how to use." — [S3], lineup
- **C127** [measured] PhotoCraft, PdfCraft, AniCraft, FigCraft and Craft Anything carry "Early alpha"; the other twelve "In development" — Own measurements, M3
- **C108** [quoted] ArtCraft is an IDE for interactive AI image and video creation — "ArtCraft is the IDE for interactive AI image and video creation." — [S4], intro
- **C109** [quoted] Craft Anything studies a website, app or game and has AI build your own version — "See how any website, app or game works, then have AI build your own version; an open-source, clean-room engine in pure Rust." — [S5], header
- **C110** [quoted] Craft Anything exposes 320 tools as CLI commands and MCP tools — "320 tools, each one a CLI command and an MCP tool, so any agent can drive the same engine the app uses." — [S5], Agent-ready
- **C111** [quoted] Craft Anything runs the user's own unmodified `claude` as the builder — "Craft Anything runs your own, unmodified `claude` program, which uses your own sign-in" — [S5], AI
- **C112** [quoted] Craft Anything is early alpha — "**Status:** Craft Anything is in early alpha." — [S5], Status
- **C113** [measured] storytold has 82 public repos; the apps, craft-libs, craft-anything and autocraft are Apache-2.0 per GitHub; stars: photocraft 80219, artcraft 41466, craft-anything 36487, pdfcraft 21085, filmcraft 18532, wordcraft 18224, lightcraft 16143, vectorcraft 11867 — Own measurements, M3
- **C114** [measured] Tooling repos: craft-contrib, craft-common-actions, craft-pr-review-tool, craft-repo-status-app, craft-skills, craft-wiki, craft-launcher, craft-libs, craft-i18n, craft-ai-integrations — Own measurements, M3
- **C115** [quoted] craft-skills calls itself a corpus of shared skills for agentic development — "Corpus of shared skills used in agentic development of craft apps" — [S6], README
- **C116** [measured] craft-skills contains only an 81-byte README — Own measurements, M3
- **C117** [quoted] Craft PR Review grades how close each open PR is to landing and has Claude summarise and group related PRs — "It polls GitHub, grades how close each PR is to landing, reads CodeRabbit's findings, and has Claude summarize PRs and group the ones possibly related." — [S7], intro
- **C118** [quoted] Its grading is deterministic and shows its working — "All of it is deterministic, and the PR view shows the working" — [S7], How PRs are graded
- **C119** [measured] photocraft: 1790 open PRs, 4534 merged, 473 merged since 2026-11-11; `main` has deletion, non_fast_forward and pull_request rules — Own measurements, M4
- **C120** [quoted] The HN user echelon, writing as the apps' maker, asked for help and offered stipends and bug bounties — "I'll need lots of help. (Anyone want to join me? I'll pay stipends and bug bounties.)" — [S8], comment 49959605
- **C121** [quoted] A HN tester called it very broken AI-produced software — "Tested it: very broken software produced by AI." — [S8], comment 49961301
- **C122** [quoted] Another tester said essentially nothing worked in the Photoshop equivalent — "I tried their photoshop \"equivalent\" and it's a piece of garbage. Essentially nothing works." — [S8], comment 49961271
- **C123** [quoted] A commenter argued such suites take oxygen from credible open-source tools — "They suck the oxygen out of the open-source ecosystem for other more credible software, such as Photopea or Gimp or FreeCAD." — [S9], comment 50011123
- **C124** [quoted] On 2026-10-05 (UTC) a commenter quoted the main ArtCraft repo as "fair source" — "ArtCraft is a form of \"fair source\" software. ... As seen on the main Artcraft repo." — [S8], comment 49960110
- **C125** [measured] On 2026-11-18 GitHub reports storytold/artcraft as Apache-2.0, with LICENSE-APACHE and LICENSE-MIT files — Own measurements, M3
- **C126** [inference] ArtCraft's main repo appears to have moved from fair-source to Apache/MIT between 2026-10-05 and 2026-11-18 — from [C124], [C125]

Product table (descriptions from [S3], [S5], [S4] and repo descriptions in M3):

| Product | What it is | Status | Repo |
|---|---|---|---|
| ArtCraft | IDE for AI image and video creation: 2D/3D compositing, posing, model choice | released app, Apache-2.0 now | storytold/artcraft |
| PhotoCraft | image editor, layers, masks, PSD | early alpha | storytold/photocraft |
| VectorCraft | vector illustration | in development | storytold/vectorcraft |
| FilmCraft | non-linear video editor | in development | storytold/filmcraft |
| LightCraft | photo library and raw developer | in development | storytold/lightcraft |
| PdfCraft | PDF reader and editor | early alpha | storytold/pdfcraft |
| EffectCraft | motion graphics and compositing | in development | storytold/effectcraft |
| AniCraft | 2D vector animation | early alpha | storytold/anicraft |
| DesignCraft | page layout and publishing | in development | storytold/designcraft |
| FigCraft | interface design and prototyping | early alpha | storytold/figcraft |
| TextureCraft | 3D texture painting | in development | storytold/texturecraft |
| MaterialCraft | node-based procedural materials | in development | storytold/materialcraft |
| SoundCraft | audio workstation | in development | storytold/soundcraft |
| WordCraft | word processor | in development | storytold/wordcraft |
| DeckCraft | presentations | in development | storytold/deckcraft |
| CADCraft | CAD and drafting | in development | storytold/cadcraft |
| GridCraft | spreadsheet | in development | storytold/gridcraft |
| Craft Anything | study any site/app/game, Claude Code builds your own version; 320 CLI/MCP tools | early alpha, installers released | storytold/craft-anything |
| AutoCraft | model harness for maintaining repos with a large backlog | public, active, no release | storytold/autocraft |
| ArtCraft Launcher | installs and updates every app | repo public | storytold/craft-launcher |
| craft-contrib | house rules for agents and people, RFCs | public | storytold/craft-contrib |
| craft-common-actions | shared CI: gate, house-rules check, release, signing | public | storytold/craft-common-actions |
| Craft PR Review / Craft Status | tray apps grading PRs and showing repo status | public | storytold/craft-pr-review-tool, craft-repo-status-app |
| craft-libs, craft-i18n, craft-fonts, craft-extensions, craft-ai-integrations | shared libraries and assets | public | storytold/* |
| craft-skills | "corpus of shared skills" | README only | storytold/craft-skills |

### Q2 — AutoCraft: what it is, is it open source — answered

- **C201** [quoted] AutoCraft mirrors issues and PRs into a local database and runs a pipeline of model steps — "AutoCraft is a model harness for maintaining GitHub repositories with a large backlog. It mirrors every issue and PR into a local database and runs a pipeline of model steps over them." — [S10], intro
- **C202** [quoted] Jev plus Claude Haiku, Sonnet and Opus classify, prioritise, dedupe, ask maintainers, review, fix, verify and merge — "Jev classifiers and Claude Haiku, Sonnet and Opus classify, prioritise, find duplicates, ask maintainers for decisions, review, write fixes, verify and merge." — [S10], intro
- **C203** [quoted] It optimises for maintainer judgement, not token cost — "The pipeline is built around maintainers' judgement, which is the limited resource, not around token cost." — [S10], intro
- **C204** [quoted] Dual-licensed MIT or Apache-2.0 — "AutoCraft is dual-licensed under [MIT](LICENSE-MIT) or [Apache-2.0](LICENSE-APACHE), at your option." — [S10], License
- **C205** [quoted] It tracks repos of other owners without source edits — "AutoCraft can also track repositories owned by other GitHub organizations or users via `autocraft repos track owner/name` without requiring source edits." — [S10], intro
- **C206** [quoted] One module writes to GitHub, every write is audited, a test fails if another file writes — "Only `src/github/write.ts` writes to GitHub. Every write is recorded in an audit table, and a test fails if another file writes." — [S10], Trust boundaries
- **C207** [quoted] Every write needs a per-repo operator approval, given only on the dashboard — "Every GitHub write needs an operator's approval for that repo. Approvals are given on the dashboard and cannot be set from the CLI." — [S10], Trust boundaries
- **C208** [quoted] Untrusted code runs only in a separate build environment — "Untrusted code runs only in a separate build environment (a worker as another OS user, with rootless Podman), never where GitHub or Claude credentials are." — [S10], Trust boundaries
- **C209** [quoted] All Claude calls go through the Claude Code CLI — "| `claude` (Claude Code CLI) | All Claude calls |" — [S10], Requirements
- **C210** [quoted] Contributors' own agents reach the Inbox through an MCP server — "Contributors' own agents reach the Inbox through an MCP server on the dashboard (`POST /mcp`) with a personal token." — [S10], Trust boundaries
- **C211** [quoted] Merging without asking needs every condition of a list to hold at the PR's current head, among them a take review verdict and green CI — "**Merge without asking** only when all of these hold at the PR's current head: ... final review verdict is take (not take-fix) ... CI is green" — [S11], Merge queue
- **C212** [quoted] Before merging, Opus reviews the head again, independently — "Opus reviews its head commit once more, adversarially and independently of the first review" — [S10], stage table
- **C213** [quoted] Merged PRs get a post-merge review; uncovered defects become issues — "Opus reviews each merged pull request a second time and reads what actually landed. Each defect that no open item covers becomes a follow-up issue." — [S12], Post-merge review
- **C214** [quoted] Merges go in batches of up to 50 PRs checked by CI on a batch PR — "Merges PRs that pass the rules in integration batches (up to 50 PRs, checked by upstream CI on the batch PR) through safe-merge" — [S10], stage table
- **C215** [quoted] Jev at ≥90% self-reported confidence matched maintainers' labels 98% of the time — "Reports how sure it is; at 90 % or more it matched maintainers' labels 98 % of the time" — [S11], Which model does what
- **C216** [quoted] An unanswered question blocks only its own item — "When nobody answers, the question stays open and only that item waits. Everything else keeps moving." — [S12], What needs a person
- **C217** [quoted] All `claude` calls run in one fixed empty directory to keep the prompt prefix cacheable — "All `claude` calls run in one fixed empty directory (`~/.cache/autocraft/claude-cwd`, `AUTOCRAFT_CLAUDE_CWD`), because the CLI puts its working directory into its system prompt" — [S11], Which model does what
- **C218** [measured] storytold/autocraft is public, created 2026-11-05, 99 stars, 31 forks, TypeScript, ~1534 commits on main between 2026-11-02 and 11-17; committers aiongg 1046, davidmann4 30, claude 25, dylanmtaylor 12, magnus919 5 — Own measurements, M1
- **C219** [quoted] The talk's description calls AutoCraft a forthcoming factory for triage, agentic development, evaluations and post-training — "lead into Autocraft, a forthcoming software factory for issue triage, agentic development, evaluations and post training." — [S2], description
- **C220** [measured] The public pipeline doc has no evaluation or post-training stage; a grep found none — Own measurements, M2
- **C221** [quoted] A security deep scan looks for outsider-reachable vulnerabilities and fixes them privately — "An operator starts a scan of one repo's default branch. Opus looks for vulnerabilities an outsider can reach, checks each one and fixes it privately." — [S12], Security deep scan

### Q3 — Their agentic workflow — answered

- **C301** [quoted] craft-contrib holds the shared guidelines for contributors and coding agents — "Shared contributor and coding-agent guidelines for the storytold craft apps." — [S13], README
- **C302** [quoted] Gaps in instructions become the same agent mistake repeated many times — "An agent follows its instructions literally, so gaps in the instructions turn into the same mistake repeated many times: duplicate PRs, fixes for bugs already fixed on `main`, PRs left as drafts, or code that uses functions that don't exist." — [S14], Motivation
- **C303** [quoted] The rules came from running agents on hundreds of issues across eleven repos — "Running agents on hundreds of issues across eleven repositories taught us which instructions prevent those mistakes." — [S14], Motivation
- **C304** [quoted] Check, then claim — "**Check, then claim.** Before writing code, read the issue comments, search pull requests for `#N` and the keywords, and check recent commits on `main`. Comment on the issue first." — [S15], rule 2
- **C305** [quoted] Look for a better PR and close yours if the other is better or equal — "**Look for a better pull request.** If another fixes the same thing, close yours when it is better or equal, and say why." — [S15], rule 6
- **C306** [quoted] `main` only through PRs, enforced, no exception — "**`main` changes through a pull request.** Do not push to it. Branch protection enforces this. There is no exception." — [S15], rule 8
- **C307** [quoted] Stop and ask only about a short list of hard-to-undo things — "**Stop and ask only about** licensing outside the allowlist, publishing, releases, a new remote, secrets, spending money, destructive git, and anything else hard to undo. Otherwise keep working." — [S15], rule 9
- **C308** [quoted] CI is shared and not changed in feature or fix PRs — "**CI stays shared.** Workflows call `storytold/craft-common-actions`. Do not change CI in a feature or fix pull request." — [S15], rule 11
- **C309** [quoted] Guards say why — "**Guards say why.** A check that looks removable says what it prevents. Read that before changing it." — [S15], rule 12
- **C310** [quoted] No agent attribution in PRs — "**No agent attribution.** A pull request does not say an agent wrote it. A repository rule may not require that." — [S15], rule 15
- **C311** [quoted] `craftrules` is retired and must not be linked — "`craftrules` is retired. Do not link to it." — [S15], rule 13
- **C312** [quoted] Rules are copied into each `AGENTS.md`, because agents may not follow links — "Copy the applicable text into a generated block in each root `AGENTS.md`; linking alone is not enough because agents may not follow links." — [S14], Source and validation
- **C313** [quoted] A shared CI workflow fails unless `AGENTS.md` carries the house rules unchanged — "Fails unless `AGENTS.md` carries the shared house rules from [storytold/craft-contrib](https://github.com/storytold/craft-contrib) unchanged." — [S16], 10. house-rules.yml
- **C314** [quoted] 3 KB for the core block, 10 KB soft limit for the root file; measure rather than assume longer context helps — "Budget 3 KB for the core block and a 10 KB soft limit for the root file, measured in bytes. Measure the pilot rather than assuming that longer context improves results." — [S14], Source and validation
- **C315** [quoted] Non-test code never panics — "**Non-test code never panics.** No `unwrap()`, `expect()`, `panic!`, `unreachable!`, `todo!` or `unimplemented!`." — [S17], 3. Golden rules
- **C316** [quoted] Everything is a command dispatched by id from UI, CLI, control channel and MCP — "The UI, CLI, control channel and MCP all dispatch commands by id." — [S17], rule 1
- **C317** [quoted] A parity FLOOR only rises — "When parity rises, raise `FLOOR` in `crates/ui-egui/src/parity.rs` (never lower it)." — [S17], 4. Picking work
- **C318** [quoted] The menu-wiring checklist is not a measure of behaviour — "`docs/parity-checklist.md` (menu wiring) is not a measure of behaviour." — [S17], 4. Picking work
- **C319** [quoted] Measured scorecard numbers beat estimates when picking work — "Its numbers are measured; prefer them to estimates." — [S17], 4. Picking work
- **C320** [quoted] Parallel agents use their own `CARGO_TARGET_DIR` and edit only files they own — "Use your own target dir (`CARGO_TARGET_DIR=target/agent-<name>`) to avoid the Cargo build lock, and edit only the files you own." — [S17], 6. Parallel agents
- **C321** [quoted] New commands go in a new module rather than a shared file — "Put new commands in a **new module** (`engine/src/<area>_cmds.rs` with a `specs()` function) rather than growing a shared file." — [S17], 6. Parallel agents
- **C322** [quoted] A devlog entry plus a green tree is the handoff between agent sessions — "Sessions can end abruptly (crashes, context limits), so the dev log plus a green tree is how the next agent picks up." — [S17], 5. Before you finish a task
- **C323** [quoted] `panic_hunt` fuzzes every command with adversarial params — "The `panic_hunt` integration test fuzzes every command with adversarial params and must stay green." — [S17], rule 9
- **C324** [quoted] The craft-anything README carries a CodeRabbit review badge — "Reviewed by CodeRabbit" — [S5], badges

### Q4 — Pocock's current approach vs ArtCraft's — answered with a gap

- **C401** [quoted] Pocock's repo added a `software-factory` skill — "A **software factory** is a system of agents that turns tickets, PRs and schedules into merged code, deployed on remote infrastructure the user chooses." — [S18], intro
- **C402** [quoted] Start slow: every trigger needs brakes — "Every trigger is an accelerator. Accelerators without brakes make a slop cannon." — [S18], Start slow
- **C403** [quoted] Human review's catches become new checks — "**Human review**: a human reads the PR before it merges; what it catches becomes new automated checks and sharper automated review." — [S18], Start slow
- **C404** [quoted] One automated trigger at a time, throttled, with human review on every PR — "Add one automated trigger at a time, throttled at first (one bug report in ten, a clock once a day), with human review on every PR." — [S18], Start slow
- **C405** [quoted] A run never waits for a human — "A run never waits for a human: it ends, and the human's later change to the ticket tracker or git host triggers a new run." — [S18], Tasks and runs
- **C406** [quoted] Buy the services, build the tasks — "Buy the services and build the tasks: the tasks carry the user's design, the services are generic." — [S18], Fill every slot
- **C407** [quoted] `chief-of-staff` pursues a long-running goal in one session through subagents — "Pursue a long-running goal in a single session by co-ordinating subagents." — [S19], description
- **C408** [quoted] It keeps memory in a wiki of interlinked markdown pages — "Keep your memory in a **wiki**: a folder of interlinked markdown pages that outlives this session." — [S19], Wiki
- **C409** [quoted] `implement-spec` works tickets as a task graph with implementer subagents — "Works the tickets as a task graph, running implementer subagents across the ready frontier for maximum concurrency, then closes out with `/code-review`." — [S20], skill list
- **C410** [measured] mattpocock/skills ~327k stars, pushed 2026-11-18; `software-factory` added 2026-10-31; both it and `chief-of-staff` sit under `skills/in-progress` — Own measurements, M5
- **C411** [quoted] Pocock still centres alignment on a grilling session — "The fix for this is a **grilling session** - getting the agent to ask you detailed questions about what you're building." — [S20], grilling section
- **C412** [quoted] Pocock's sandcastle orchestrates sandboxed coding agents — "Orchestrate sandboxed coding agents in TypeScript with sandcastle.run()" — [S21], repo description
- **C413** [inference] Both converge on tickets in, model runs with deterministic checks plus model review plus human decisions at defined points, merged code out — from [C201], [C211], [C401], [C403]
- **C414** [inference] ArtCraft's house rules address coordination among many contributors (check for existing work first, close the weaker of two duplicate PRs); Pocock's README centres alignment on a grilling session between the agent and its user — from [C304], [C305], [C411]
- **C415** [inference] AutoCraft's per-repo operator approval of writes and its independent pre-merge review are concrete brakes in Pocock's sense; the pre-merge review matches his automated-review brake — from [C207], [C212], [C402], [C403]
- **C416** [quoted] A HN commenter doubts babysitting agents gets software past 80% — "If all you can add is baby sitting agents, then you will never reach beyond 80%." — [S9], comment 50011260
- **C418** [quoted] HumanLayer ran a lightly supervised software factory for three or four months and eventually archived the codebase — "HumanLayer eventually archived the entire codebase" — [S22], body
- **C419** [quoted] Dex Horthy argues for verifiers rather than nested loops — "verifiers all the way down" — [S22], body

Gap: the comparison with jarvis rests on jarvis's own rules files, which were read as context, not as sources; the talk itself could not be read (M6).

## Disconfirming evidence

- [C201]/[C204] — query: `storytold autocraft ArtCraft software factory open source PR triage` — search found nothing about AutoCraft at all (no coverage yet); nothing against the repo's own statements. The repo itself (M1) settles that it is public.
- [C105]/[C113] (open, active suite) — HN search `photocraft`, `artcraft` — testers report the apps as very broken [C121], [C122]; critics argue it harms other open-source tools [C123]; licence history: the main ArtCraft repo was described as fair-source in October [C124], [C126].
- [C303]/[C304] (rules learned from agents work) — nothing found against; the open-PR count (1790 on photocraft, M4) shows the volume problem is not solved by rules alone, which is the stated reason for AutoCraft [C201], [C203].
- [C413] (factories converge as the way forward) — query: `AI software factory autonomous merge failures slop problems 2026` — HumanLayer's lightly supervised factory was archived [C418]; Horthy argues for verifiers [C419]; a HN commenter doubts babysitting agents gets past 80% [C416].

## Coverage

| Channel | Read | Gap |
|---|---|---|
| Users | [S8], [S9] | HN only; no user reports on AutoCraft exist yet |
| Specialists | [S10]–[S21] | the talk transcript could not be fetched (M6) |
| Data | M1–M5 | no benchmark of the apps' quality; Jev's 98% figure is the project's own claim [C215] |
| Adversarial | [S8], [S9], [S22] | |

Overruns: Q1 and Q3 used more than three full page reads each (READMEs, rules files and AGENTS.md read via `gh api`), because the product table needed every repo listed. The `curl` floor and `gh` were used; no connector.

## Own measurements

### M1 — AutoCraft repository state

Command: `gh api repos/storytold/autocraft --jq '{stars:.stargazers_count,forks:.forks_count,lang:.language}'`; `gh api repos/storytold/autocraft/stats/contributors`; commit list paginated, counted per day; link header `rel="last"` page 1534 at per_page=1.
Output: `{"forks":31,"lang":"TypeScript","stars":99}`; `magnus919 5 / dylanmtaylor 12 / claude 25 / davidmann4 30 / aiongg 1046`; commits per day from 2026-11-02 (139) to 2026-11-17 (15); created_at 2026-11-05 in the org listing.

### M2 — Evaluations or post-training in AutoCraft docs

Command: `grep -n -i -E "post.?train|fine.?tun|eval(uation)?s?\b|training data|dataset" docs/pipeline.md` (230,084 bytes, fetched via `gh api`)
Output: no lines.

### M3 — storytold repositories and apps page

Command: `gh api "users/storytold/repos?per_page=100" --paginate --jq '...name, stars, license...'`; `curl -sL https://getartcraft.com/apps` stripped to text; `gh api repos/storytold/artcraft --jq .license.spdx_id`; `gh api repos/storytold/craft-skills/git/trees/main?recursive=1`
Output: 82 repos (trimmed): `photocraft 80219 Apache-2.0`, `artcraft 41466 Apache-2.0`, `craft-anything 36487 Apache-2.0`, `autocraft 99 Apache-2.0`, `craft-contrib 43 -`, `craft-skills 18 -`; apps page: "Early alpha" on PhotoCraft, PdfCraft, AniCraft, FigCraft, Craft Anything, "In development" on the rest; artcraft: `Apache-2.0`, files `LICENSE-APACHE`, `LICENSE-MIT`; craft-skills tree: `README.md 81`.

### M4 — photocraft PR volume and branch rules

Command: `gh api "search/issues?q=repo:storytold/photocraft+is:pr+is:open" --jq .total_count` (and `is:merged`, `merged:>=2026-11-11`); `gh api repos/storytold/photocraft/rules/branches/main --jq '.[].type'`
Output: `1790`, `4534`, `473`; `deletion`, `non_fast_forward`, `pull_request`.

### M5 — Pocock's skills repo

Command: `gh api repos/mattpocock/skills --jq '{stars,pushed}'`; `gh api "repos/mattpocock/skills/commits?per_page=12"`; tree listing filtered on `software-factory|chief-of-staff`
Output: `{"stars":327194,"pushed":"2026-11-18T09:51:01Z"}`; `2026-10-31 software-factory: glossary skill for designing a factory (#1316)`, `2026-10-19 chief-of-staff: keep memory in a dated, commit-cited wiki (#1304)`, `2026-10-29 implement-spec: a fresh implementer subagent per ticket (#1342)`; paths `skills/in-progress/software-factory/SKILL.md`, `skills/in-progress/chief-of-staff/SKILL.md`.

### M6 — Talk transcript

Command: YouTube `timedtext` with `fmt=json3`; `yt-dlp --write-auto-subs --sub-langs en` (json3, vtt, then `--impersonate chrome`)
Output: empty body; `ERROR: Unable to download video subtitles for 'en': HTTP Error 429: Too Many Requests` (three attempts).

## Open questions

- Talk content — blocked: YouTube 429 on subtitles — reading the transcript from another network or after the rate limit clears would settle what the talk says about human review and AutoCraft's evaluation and post-training plans.
- Whether AutoCraft is in use on the craft repos today — not found — the craft repos' PR timelines (comments or labels by the AutoCraft account) would settle it.
- What Jev is (who makes "TypeSafe's Jev model") — not searched — one search on the vendor would settle it.
- Whether the apps' quality improved since the October HN reports — not measured — a hands-on test of current PhotoCraft releases would settle it.
- Q4 gap, comparison with jarvis — no claim in the report sources jarvis's current gates, so which AutoCraft pieces jarvis lacks is unestablished — citing jarvis's `AGENTS.md` merge rules and the merge-gates reference as sources and mapping them against [C206], [C207], [C212], [C213] would settle what to adopt.

## Sources

- [S1] YouTube oEmbed for the talk — https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v=UCL4K36SHp0&format=json — read in full
- [S2] Talk page description — https://www.youtube.com/watch?v=UCL4K36SHp0 — passage (description and timestamps)
- [S3] Crafting Apps page — https://getartcraft.com/apps — read in full
- [S4] storytold/artcraft README — https://github.com/storytold/artcraft/blob/main/README.md — passage
- [S5] storytold/craft-anything README — https://github.com/storytold/craft-anything/blob/main/README.md — read in full
- [S6] storytold/craft-skills README — https://github.com/storytold/craft-skills/blob/main/README.md — read in full
- [S7] storytold/craft-pr-review-tool README — https://github.com/storytold/craft-pr-review-tool/blob/main/README.md — passage
- [S8] HN: ArtCraft Apps launch thread — https://news.ycombinator.com/item?id=49958850 — top comments
- [S9] HN: What ArtCraft's Vibe-Coded Apps Say About Adobe — https://news.ycombinator.com/item?id=50010170 — top comments
- [S10] storytold/autocraft README — https://github.com/storytold/autocraft/blob/main/README.md — read in full
- [S11] storytold/autocraft docs/pipeline.md — https://github.com/storytold/autocraft/blob/main/docs/pipeline.md — passages
- [S12] storytold/autocraft docs/how-it-works.md — https://github.com/storytold/autocraft/blob/main/docs/how-it-works.md — read in full
- [S13] storytold/craft-contrib README — https://github.com/storytold/craft-contrib/blob/main/README.md — read in full
- [S14] craft-contrib RFC-0006 — https://github.com/storytold/craft-contrib/blob/main/rfcs/0006-coding-agents.md — read in full
- [S15] craft-contrib house-rules-core — https://github.com/storytold/craft-contrib/blob/main/standards/house-rules-core.md — read in full
- [S16] storytold/craft-common-actions README — https://github.com/storytold/craft-common-actions/blob/main/README.md — passages (gate.yml, house-rules.yml)
- [S17] storytold/photocraft AGENTS.md — https://github.com/storytold/photocraft/blob/main/AGENTS.md — passages (sections 3–7)
- [S18] Pocock software-factory skill — https://github.com/mattpocock/skills/blob/main/skills/in-progress/software-factory/SKILL.md — read in full
- [S19] Pocock chief-of-staff skill — https://github.com/mattpocock/skills/blob/main/skills/in-progress/chief-of-staff/SKILL.md — passage
- [S20] mattpocock/skills README — https://github.com/mattpocock/skills/blob/main/README.md — passages
- [S21] mattpocock/sandcastle — https://github.com/mattpocock/sandcastle — repo description only
- [S22] AAIF: Dex still thinks long-running coding agents stink — https://aaif.io/blog/dex-still-thinks-long-running-coding-agents-stink — passages

## Audit

| Claim | Verdict | Note |
|---|---|---|
| C101 | SUPPORTED | title is in the oEmbed JSON with its dash stored as a `\u2014` escape, so the quote check reports NOT FOUND; decoded, the string matches |
| C102 | SUPPORTED |  |
| C103 | SUPPORTED |  |
| C104 | SUPPORTED |  |
| C105 | SUPPORTED |  |
| C106 | SUPPORTED |  |
| C107 | SUPPORTED |  |
| C108 | SUPPORTED |  |
| C109 | SUPPORTED |  |
| C110 | SUPPORTED |  |
| C111 | SUPPORTED |  |
| C112 | SUPPORTED |  |
| C113 | SUPPORTED | recorded M3 output was trimmed; re-run of the repo listing on 2026-11-18 shows every app, craft-libs, craft-anything and autocraft as Apache-2.0 and the stars within +10 |
| C114 | SUPPORTED | recorded M3 output did not list these; re-run of the repo listing shows all ten |
| C115 | SUPPORTED |  |
| C116 | SUPPORTED |  |
| C117 | SUPPORTED |  |
| C118 | SUPPORTED |  |
| C119 | SUPPORTED |  |
| C120 | PARTIAL | comment author is HN user echelon; nothing in it names Brandon Thomas; claim rewritten to the handle and what the quote says |
| C121 | SUPPORTED |  |
| C122 | SUPPORTED |  |
| C123 | SUPPORTED |  |
| C124 | PARTIAL | comment is dated 2026-10-05T02:35Z, not 10-04; 'main repo' attribution was outside the quote; date corrected and quote extended within the same comment |
| C125 | SUPPORTED |  |
| C126 | PARTIAL | follows from C125 and repaired C124; start date corrected to 2026-10-05; current README has no 'fair source' text |
| C127 | SUPPORTED | apps page re-read: 5 Early alpha, 12 In development |
| C201 | SUPPORTED |  |
| C202 | SUPPORTED |  |
| C203 | SUPPORTED |  |
| C204 | SUPPORTED |  |
| C205 | SUPPORTED |  |
| C206 | SUPPORTED |  |
| C207 | SUPPORTED |  |
| C208 | SUPPORTED |  |
| C209 | SUPPORTED |  |
| C210 | SUPPORTED |  |
| C211 | PARTIAL | quote was only the list header; the claim's list omitted two of nine conditions; claim narrowed and quote extended within the same list |
| C212 | SUPPORTED |  |
| C213 | SUPPORTED |  |
| C214 | SUPPORTED |  |
| C215 | SUPPORTED |  |
| C216 | SUPPORTED |  |
| C217 | SUPPORTED |  |
| C218 | SUPPORTED | re-run: public, created 2026-11-05, now 101 stars, 31 forks |
| C219 | SUPPORTED |  |
| C220 | SUPPORTED | grep re-run on docs/pipeline.md (230,084 bytes): no lines |
| C221 | SUPPORTED |  |
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
| C311 | PARTIAL | quote does not say craftrules was private; 'private' dropped |
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
| C323 | SUPPORTED |  |
| C324 | PARTIAL | badge alt text found in S5 (craft-anything) only; claim generalised to all repos; narrowed |
| C401 | SUPPORTED |  |
| C402 | SUPPORTED |  |
| C403 | SUPPORTED |  |
| C404 | SUPPORTED |  |
| C405 | SUPPORTED |  |
| C406 | SUPPORTED |  |
| C407 | SUPPORTED |  |
| C408 | SUPPORTED |  |
| C409 | SUPPORTED |  |
| C410 | SUPPORTED | re-run: first commit on skills/in-progress/software-factory is 2026-10-31; stars 327,201 |
| C411 | SUPPORTED |  |
| C412 | SUPPORTED |  |
| C413 | SUPPORTED | follows from C201, repaired C211, C401, C403 |
| C414 | PARTIAL | 'high-volume' and 'one engineer' were premises no named claim states; C310 did not bear on it; narrowed to what C304, C305, C411 say |
| C415 | PARTIAL | the audited write module (C206) is a trust boundary, not one of Pocock's three named brakes; narrowed to approvals and pre-merge review |
| C416 | SUPPORTED |  |
| C417 | UNSUPPORTED | comment says 60/40 *unless* detailed specs exist; claim said 'even with detailed specs', the reverse; removed |
| C418 | PARTIAL | S22 says 'lightly supervised' for three or four months, not 'unreviewed'; rewritten |
| C419 | SUPPORTED | S22 renders it 'its verifiers all the way down', framed as Dex's position |

Label verdict: open — the talk itself was not read and Q4's comparison with jarvis has no sourced claim; either could change the recommendation (what to adopt, whether the published craft-contrib rules are the whole workflow).
Quote check: artcraft-ecosystem-autocraft-2026-11-18.md: 77 quoted claim(s): 71 found, 1 NOT FOUND, 5 unfetchable, 0 no source

## Disposition

| Recommendation | State | Where |
|---|---|---|
| Read AutoCraft's design as a concrete open reference for brakes on a merge pipeline | deferred | unfiled: the user picks which products and pieces to study from this report's table first; an issue follows that choice |
| Weigh AutoCraft as the project to contribute to | deferred | unfiled: a personal choice of the user's, not repo work; nothing to track in Osasuwu/jarvis until it is made |
| Watch Pocock's `software-factory` skill, which is still in `in-progress` | deferred | unfiled: a watch item with no work until the skill leaves `in-progress`; the next /research run on this topic re-checks it |
