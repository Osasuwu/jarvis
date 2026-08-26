# CLAUDE.md — Jarvis

Three-way split — this file is the *rules* leg (process, conventions); `config/SOUL.md` is *identity*, `CONTEXT.md` is the *domain model*. Roles and load path: CONTEXT.md → *Architectural shape*, *Key flows → Session start*. Skill selection is left to the Claude Code harness (skill frontmatter descriptions), not documented here.

## Who you work for

This section is one instance's operator profile — input data, not the product's shape. Jarvis is built as a system for people: every operator hosts their own instance (see §Project), and the principal here is the first operator — the case the system is tested on. Nothing below may harden into a shipped code path as an assumption.

Solo developer, 3 devices, no team. You compensate for the missing team. Push back on bad ideas — user is intermediate but growing fast.

Budget: Claude Max subscription covers all Claude Code usage (including scheduled tasks). ~$20/month for externals (Supabase, VoyageAI) — be frugal with external API calls.

## Session start context (auto-loaded)

The SessionStart hook is registered in **user-level** `~/.claude/settings.json` (source: `.claude-userlevel/settings.json`) — the repo's `.claude/settings.json` is empty and registers nothing. What it injects: CONTEXT.md → *Key flows → Session start*. **Already in your window — do NOT re-fetch with MCP tools.**

- Working_state checkpoint found → one-line offer to continue.
- Hook failed (no memory block) → fall back to `memory_recall` + `goal_list`.
- Topic-specific lookups during the session still use `memory_recall(query=<topic>)`; only the baseline is pre-loaded.

The invariants ride a bare `@import` instead of the hook, so they expand at launch and never enter the hook's drop lottery (#1417 — CONTEXT.md → *Context delivery*):

@docs/context/invariants.md

Unfamiliar term? `CONTEXT.md` → `## Glossary` is the pull-only home (categories: core entities, self-improvement, repo-baseline, merge-gate vocabulary, workflow, AFK spawn substrate, skill triggers, context delivery, devices). Its category index was itself always-loaded until #1418 retired it — an index of where to look does not need to be in the window to be found.

## Project

**Jarvis** — single-principal AI agent for software work (per redesign L0; broader personal-life scope is 1.x backlog). Repo `Osasuwu/jarvis`. Architecture in [`docs/design/jarvis-v2-redesign.md`](docs/design/jarvis-v2-redesign.md); active scope = open GitHub milestones (capability-shipping units, see *Milestone vs pillar hygiene* below); `docs/PROJECT_PLAN.md` is a pointer index.

Code is distributed — never hosted as a service — through the separate public template repo `Osasuwu/jarvis-oss`; **every operator hosts their own instance**, including their own memory backend. This repo is one instance of that schema, not the schema itself. So subsystems are built OSS-ready from the start rather than adapted later: provider names, model names, repo lists, queue labels and backend endpoints belong in operator config, never as literals on a code path, and **no path shipped to `jarvis-oss` may reference this instance's memory backend** — nobody else has access to it. YAGNI does not license hardcoding here: the counting unit is *readers who could depend on the code*, not implementations the principal happens to run. Decision `855188a3-c71f-4e86-a412-9a07b76f19df`.

Architecture: Claude Code native (skills, hooks, MCP, subagents) + Supabase memory + SOUL.md identity.

## Definition of Done

Before marking any task complete:
1. **Integration + tests**: does it work in context, end-to-end, not just in isolation? Apply SOUL §End-to-end ownership.
2. **Side effects**: what else uses what you changed?
3. **Memory**: non-obvious learning or improvement idea → `memory_store` (with `source_provenance`).
4. **Tooling**: manual step that should be automated → propose or record.

## Engineering posture

Non-negotiable for every decision in this repo. Not in memory — these are how work happens here, not "things to recall sometimes".

- **Recall before action.** Per user-level CLAUDE.md §1 *Recall before deciding* — required, not optional. Repo addition: if brief-mode recall surfaces an on-topic memory, `memory_get` it before building defaults from your own head.
- **Verify before assuming implemented.** Never say "this is already done" without `grep` for the actual symbol, reading the code path end-to-end, and where feasible a test that would fail if the feature were missing. Tool-width Z was missing for a month because everyone assumed otherwise — one bad foundation invalidated a month of downstream work.
- **Skills are a contract, not a trigger.** `/implement`, `/grill`, `/end`, `/dispatch` are owed when the action matches the contract — not only when the principal types the magic word. After PR merge: explicit `/implement` for next slice or `/end`, not silent continuation. Repo not having local skill files is not an exemption — skills are global, canonical at `.claude-userlevel/skills/` and mirrored to `~/.claude/skills/`.

Four write-scoped rules moved to `.claude/rules/` (path-gated, load only when a matching file is read — see #1274): no state in static storage → [`no-state-in-static-storage.md`](.claude/rules/no-state-in-static-storage.md); sibling-grep on fixes → [`sibling-grep-on-fixes.md`](.claude/rules/sibling-grep-on-fixes.md); `ceiling:` marker → [`ceiling-marker-required.md`](.claude/rules/ceiling-marker-required.md); one runnable check per non-trivial change → [`non-trivial-logic-runnable-check.md`](.claude/rules/non-trivial-logic-runnable-check.md).

## Project-specific rules

Two more write-scoped rules moved to `.claude/rules/` (same rationale as above): native-first priority → [`native-first-priority.md`](.claude/rules/native-first-priority.md); check native capabilities first → [`check-native-capabilities-first.md`](.claude/rules/check-native-capabilities-first.md).

## Related projects

| Project | Repo | Description |
|---|---|---|
| redrobot | `SergazyNarynov/redrobot` | Industrial robot control — Python + FastAPI + React/Three.js + MuJoCo |

redrobot is not a personal project: it has a second reader and a potential contributor. Run it as a shared codebase — decisions legible from the repo alone, no personal literals, hygiene as if a teammate reviews tomorrow. It is not *more important* than jarvis; caution on shared surfaces comes from the nature of the change, not from which repo is touched (see invariants → shared surfaces).

## Delegation

**Model selection**: complex reasoning / architecture / multi-file → stronger model. Simple edits / searches → lighter. User uses Opus for redrobot — match when delegating redrobot tasks. Don't pay LLM tokens to run shell commands — fetch first, send only data.

**Subagents deliver end-to-end** — SOUL §End-to-end ownership binds them too: feature → tests + error handling included; can't complete → document what's left. Don't return "done" if it only works in isolation.

## Memory

- **Access**: `memory_store` / `memory_recall` via MCP locally, `execute_sql` via the Supabase connector from cloud tasks (`.mcp.json` isn't loaded there).
- **Save immediately** after: decision, preference, architectural discussion, new fact, rejected approach (with why), working-style observation. Don't batch.
- **Working state**: save to `working_state_jarvis` at natural breakpoints; `memory_delete` when done. After context compression → `memory_recall(query="working state")` first, then targeted file reads.

## Skill routing

Use skills — don't reinvent with raw tools.

| Trigger | Skill |
|---|---|
| "реализуй #42" — implement single issue inline | `/implement` (TDD-mode auto-engages via the grill trigger checkbox + working_state UUIDs) |
| "делегируй #X #Y" — enqueue multiple issues onto `task_queue` for headless pickup | `/dispatch` (renamed from `/delegate`, #1085 S2; never spawns in-session — enqueues thin rows, run later by `/task-implement` via `drain_tasks`) |
| "проверь результаты" / scheduled post-delegation | `/verify` |
| "что я делаю не так", "проанализируй сессии", "паттерны общения", weekly behavioral audit | `/reflect` (cross-session comms audit; old outcome-verification scope migrated to `/verify` + `/self-improve` per #510) |
| "исследуй", "research", "сравни" | `/research` |
| "улучши себя", self-improvement | `/self-improve` |
| "цели", "приоритеты" | `/goals` |
| New device bootstrap, "scheduled tasks setup" | `/setup-tasks` (Workshop-only per CONTEXT.md → *Workshop PC = sole routine host*; refuses elsewhere, `--cleanup` drops legacy entries) |
| "end" / "end quick" | `/end` (full) / `/end --quick` (fast) |
| Vague intuition (no written plan yet) / "у меня ощущение что", "может быть лучше но не знаю как", "обсудим концепт"; subsumes /research for in-debate factual grounding | `/reason` |
| "how should this look/behave" discussion stalled on shape, not on whether to build it / "прототипируй", "накидай черновик", "покажи как это может выглядеть" | `/prototype` (throwaway artifact, feeds `/grill`) |
| Stress-test plan / "grill me" / before non-trivial implementation | `/grill` |
| Conversation context → PRD on issue tracker | `/to-spec` |
| Plan / PRD → vertical-slice issues | `/to-tickets` |
| "diagnose this", bug repro, perf regression | `/diagnose` |
| PR rework needed / negative review received | `/rework` (CONTEXT.md → *`/rework` skill*; adds loop-stop guard policy) |
| "improve architecture", find shallow modules, refactoring opportunities | `/improve-codebase-architecture` |
| "почисти память", "memory hygiene", /curate, after 2+ recall complaints | `/curate` (CONTEXT.md → *Curation*) |
| "review memories", "drain queue", "проверь кандидаты", weekly memory-review, volume-event fire, /learn --status | `/learn` (M42 always-gate review surface; drains classifier + Deriver/Dreamer queues, hard cap 20, idempotent, no defer/accept_all) |
| "last sprint report", "what did we ship", "milestone closeout", pre-sweep brief | `/last-work-report` (skeleton — #606) |
| `статус` / `status` / `статус <repo>` — **anchored, only these exact triggers** | `/status` (CONTEXT.md → *Status synthesis*) |
| `утро` / `morning` / `доброе утро` — **anchored, only these exact triggers** | `/morning` (daily digest: plan + S/M/L estimates + cut-line, #1588) |
| "zoom out", unfamiliar code area, need higher-level map | `/zoom-out` |
| Issue triage / state machine / "ready for agent" | `/triage` |
| "what's next across M-whatever", "chart the map", "what's blocked on what", multi-milestone frontier scan | `/wayfinder` |
| Provisioning infra, CI secrets/API keys, unfamiliar third-party dashboard, one-off migration/cutover — a manual procedure only a human can perform | `/wizard` |
| Author/edit a skill | `/write-a-skill` |
| "be brief", "caveman", token compression | `/caveman` |
| Explicit `/weekly-release` invocation only — no chat-text anchor; drafts a weekly GitHub release per `config/repos.conf` `releases=weekly` repo | `/weekly-release` |

Rules:
- GitHub issue work → /implement or /dispatch, no exceptions. Raw Agent loses PR structure and verification.
- Multiple tasks → /dispatch, but **Jarvis decides** what's queue-suitable vs inline (context-heavy / cross-cutting / safety-critical stay inline). User trusts this call.
- **Grill trigger checkbox is mandatory** — every `/implement` invocation runs it at start; `/dispatch` runs its own advisory readiness gate (`check_issue`) instead, since routing decisions for enqueued work are re-derived headlessly by `/task-implement` with no operator present to grill. Canonical checkbox text and output routing live in `~/.claude/reference/engineering-principles.md`.
- **`/reason` (optional, intuition-stage) → `/grill` → `/to-spec` → `/to-tickets` → `/implement` (or `/dispatch`)** is the canonical chain for new features. TDD-mode engages inside `/implement` (and inside `/task-implement` for enqueued work) per the grill trigger checkbox / issue-body decision citation — there is no standalone `/tdd` skill. Each phase in a fresh session if context is heavy. Skip `/reason` when you already have a plan to validate ("оркестратор можно лучше — не знаю как" → start with `/reason`; "вот план X, проверь" → skip to `/grill`).
- If unsure → use the skill. Overhead near zero, cost of skipping is lost structure.
- **`/status` is anchored routing — bare/unrelated uses of the word do NOT fire it.** Only the exact triggers `статус`, `status`, or `статус <repo>` (the word as a standalone command, optionally naming a tracked repo) route to `/status`. A sentence that merely contains the word — "какой статус у PR #123", "статус деплоя в логах", "status code 500", a quoted error string — is a normal request answered in-context, never a trigger for a repo-state investigation.
- **`/morning` is anchored routing — bare/unrelated uses of the word do NOT fire it.** Only the exact triggers `утро`, `morning`, or `доброе утро` route to `/morning`. A sentence that merely contains one of these words — "good morning" as a passing greeting, "meeting moved to this morning" — is a normal request answered in-context, never a trigger for a daily-digest investigation. `/morning`'s trigger set (`утро`/`morning`/`доброе утро`) and `/status`'s (`статус`/`status`/`статус <repo>`) are disjoint by construction — neither intercepts the other's triggers.

### Responsibility split — interactive · `/dispatch` · reactive-core orchestrator

Three places work can land. Pick by **who admits the work and how**, not by execution mechanism — since #1085 Slice 2, `/dispatch` and the orchestrator both execute through the same `task_queue` + `drain_tasks` + `/task-implement` pipeline; the split below is about *admission*, not about which code path eventually runs the issue.

- **Interactive `/implement`** — operator present, one judgment-heavy issue, full SOUL loaded, executes **in-session**; the grill trigger checkbox is the in-skill AFK-readiness backstop.
- **`/dispatch`** (renamed from `/delegate`) — operator present and chose to fan out; AFK-eligible issues pass an advisory `check_issue` gate and are **enqueued** as thin `task_queue` rows (`goal="/task-implement #N"`), then executed **headlessly** later by `drain_tasks` → `/task-implement`. Admission is operator-driven (a human decided *these* issues, *now*); execution is queue-routed, same as the orchestrator's. `/dispatch` never spawns a subagent itself.
- **Reactive-core orchestrator (M44)** — no operator; events cold-boot it and it triages **one** event into one of three dispositions, then hands off (CONTEXT.md → *orchestrator*, *Loop closure*). Admission is event-triggered, not human-judged.

Boundary: orchestrator-emitted and `/dispatch`-enqueued task rows share identical AFK-fit/sandcastle admission semantics and the same `check_issue` mechanical re-check at spawn — mechanics: CONTEXT.md → *Core entities* (`Pre-dispatch gate`, `AFK-fit checklist`, `task_queue`, `orchestrator`).

## Autonomous work

User often leaves Jarvis to work alone. Core loop comes from §Engineering posture above + SOUL §Judgment calibration + SOUL §Goal & outcome awareness. "Aligned plans = standing orders" — when a multi-step plan was discussed and signed off, the alignment IS the approval; don't re-confirm at each checkpoint.

Project-specific addition — transform tasks into verifiable goals — moved to `.claude/rules/` (write-scoped, path-gated; see #1274): [`transform-tasks-into-verifiable-goals.md`](.claude/rules/transform-tasks-into-verifiable-goals.md).

## Development process

Branches from `main`. **PRs are for code, not discussions** — design debate goes to GitHub Discussions instead (approval = thread resolution).

- One issue → one PR, body has `Closes #NNN`. Bypasses (no linked issue needed): `priority:critical` hotfix, `refactor:` title prefix, `[no-issue]` commit marker (still required in the commit msg, `.pre-commit-config.yaml` regex #329).
- Consolidation/batch PR → `Closes #N` for **every** absorbed issue, not just the umbrella. Mechanism, cross-repo caveats: [`docs/reference/pr-issue-linkage.md`](docs/reference/pr-issue-linkage.md).
- Trivial/reversible/<30min/own-repo → fix inline, no tracking issue (#428); architectural reshape / cross-cutting / behavior change the user should weigh in on → open an issue instead. Full criteria, RFC/Discussions detail: [`docs/reference/dev-process-details.md`](docs/reference/dev-process-details.md).
- Milestone naming/closing/PRD-placement rules + architecture-sweep-on-close trigger: [`docs/reference/milestone-hygiene.md`](docs/reference/milestone-hygiene.md).
- Check the Claude code-review **issue-comment** (not PR review) before merging. Copilot is no longer used (plan lapsed, decision 2026-05-22).

## Key files

Repo layout with intent — SOUL, device config, memory server, session-context hook, MCP registrations: CONTEXT.md → *Architectural shape*. Not in that tree: `scripts/memory-recall-hook.py` (UserPromptSubmit recall), `scripts/pretooluse-recall-hook.py`, and `.github/copilot-instructions.md` (process rules mirrored for GitHub).

If this file needs a change — propose it and explain why.
