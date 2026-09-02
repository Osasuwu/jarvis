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

Unfamiliar term? `CONTEXT.md` → `## Glossary` is the pull-only home (categories: core entities, self-improvement, merge-gate vocabulary, workflow, AFK spawn substrate, skill triggers, context delivery, devices). Its category index was itself always-loaded until #1418 retired it — an index of where to look does not need to be in the window to be found.

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
