# CLAUDE.md — Jarvis

Three-way split — this file is the *rules* leg (process, conventions, skill routing); `config/SOUL.md` is *identity*, `CONTEXT.md` is the *domain model*. Roles and load path: CONTEXT.md → *Architectural shape*, *Key flows → Session start*.

## Who you work for

Solo developer, 3 devices, no team. You compensate for the missing team. Push back on bad ideas — user is intermediate but growing fast.

Budget: Claude Max subscription covers all Claude Code usage (including scheduled tasks). ~$20/month for externals (Supabase, VoyageAI) — be frugal with external API calls.

## Session start context (auto-loaded)

The SessionStart hook is registered in **user-level** `~/.claude/settings.json` (source: `.claude-userlevel/settings.json`) — the repo's `.claude/settings.json` is empty and registers nothing. What it injects: CONTEXT.md → *Key flows → Session start*. **Already in your window — do NOT re-fetch with MCP tools.**

- Working_state checkpoint found → one-line offer to continue.
- Hook failed (no memory block) → fall back to `memory_recall` + `goal_list`.
- Topic-specific lookups during the session still use `memory_recall(query=<topic>)`; only the baseline is pre-loaded.

## Project

**Jarvis** — single-principal AI agent for software work (per redesign L0; broader personal-life scope is 1.x backlog). Repo `Osasuwu/jarvis`. Architecture in [`docs/design/jarvis-v2-redesign.md`](docs/design/jarvis-v2-redesign.md); active scope = open GitHub milestones (capability-shipping units, see `milestone_hierarchy_v3`); `docs/PROJECT_PLAN.md` is a pointer index.

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
- **No state in static storage.** State (% done, ✅/❌ markers, "shipped in PR #X", sprint dates, "last audit YYYY-MM-DD") belongs in GitHub Issues/Projects/PRs/commit history — NOT in markdown files, NOT in memory. Static storage may hold: evergreen lessons, decisions+rationale, reference info (API shapes, config locations), target architecture, pointers ("see #633 for current status"). If a field would be wrong in 2 weeks → GH, not here.
- **Sibling-grep on fixes.** When a reviewer flags a bug in one helper/pattern, grep for sibling patterns across the whole file AND related files before declaring the fix done. A second-round review with the same class of finding = the first fix was partial. 30 seconds of grep beats a full CI cycle of rework.
- **Skills are a contract, not a trigger.** `/implement`, `/grill`, `/end`, `/delegate` are owed when the action matches the contract — not only when the principal types the magic word. After PR merge: explicit `/implement` for next slice or `/end`, not silent continuation. Repo not having local skill files is not an exemption — skills are global, canonical at `.claude-userlevel/skills/` and mirrored to `~/.claude/skills/`.
- **Deliberate simplifications carry a `ceiling:` marker.** When you knowingly ship a shortcut with a known limit — global lock, O(n²) scan over a list assumed small, naive heuristic, hardcoded single-device path — leave an inline `ceiling:` comment naming *both* the limit and the upgrade path (`# ceiling: O(n²) over labels, fine <200; switch to a set-diff if a repo crosses that`). Not for ordinary "could be prettier" code — only for a corner cut against a limit you can name. This is the cheap end of «tech debt must be visible»: `grep -rn 'ceiling:'` is the debt list, so a shortcut no longer needs an issue to stay visible. Unnamed limit ⇒ you don't understand the shortcut well enough to ship it.
- **Non-trivial logic leaves one runnable check.** Any change with real logic in it ships with at least one thing that fails if the logic breaks — the smallest such thing, not a suite: one test in the existing file, or an assert-based self-check. Trivial one-liners, renames and doc edits need nothing. This is the floor under drive-by fixes where full TDD is overkill; it does **not** relax the TDD requirement inside `/implement` and `/rework`, which stays as-is. A fix you can't leave a check behind for is itself a finding — flag it.

## Project-specific rules

- **Native-first priority, not a ban.** Before writing a custom script/service (any language), check skills/MCP/hooks/subagents first; if native covers it cleanly, use native. Custom code is permitted on merit — when the native solution is awkward or incomplete. (Relaxed 2026-05-20 from the prior near-prohibition; decision `d9be0390`.) Existing justified custom code: `mcp-memory/server.py`, `src/risk_radar.py`.
- **Check native capabilities first**: Telegram → Channels; scheduling → `/loop` or scheduled tasks; background → desktop agents.
- **Cross-project impact + MCP portability**: `mcp-memory/server.py`, `.mcp.json` and the Supabase schema are shared with redrobot; `.mcp.json` must stay device-portable (env vars, never hardcoded usernames or absolute paths). Standing invariant — CONTEXT.md → *Invariants → Skills, infra & eval*.

## Related projects

| Project | Repo | Description |
|---|---|---|
| redrobot | `SergazyNarynov/redrobot` | Industrial robot control — Python + FastAPI + React/Three.js + MuJoCo |

## Delegation

**Model selection**: complex reasoning / architecture / multi-file → stronger model. Simple edits / searches → lighter. User uses Opus for redrobot — match when delegating redrobot tasks.

**Subagents deliver end-to-end** — SOUL §End-to-end ownership binds them too: feature → tests + error handling included; can't complete → document what's left. Don't return "done" if it only works in isolation.

**Verification (non-negotiable)**: after any agent completes, run `git diff` in its working directory — never the self-report (CONTEXT.md → *Invariants → AFK & delegation*). Reports N files edited, diff shows 0 ⇒ fabricated.

## Memory

- **Supabase** is the cross-device source of truth; file-based `~/.claude/projects/…/memory/` is device-local and does not sync (CONTEXT.md → *Invariants → Memory & persistence*). Access: `memory_store` / `memory_recall` via MCP locally, `execute_sql` via the Supabase connector from cloud tasks (`.mcp.json` isn't loaded there).
- **Save immediately** after: decision, preference, architectural discussion, new fact, rejected approach (with why), working-style observation. Don't batch.
- **`source_provenance` on every `memory_store`** — namespaced: `skill:<name>`, `session:<YYYY-MM-DD>`, `hook:<name>`, `user:explicit`, `episode:<id>`, or URL/`external:<system>`.
- **Working state**: save to `working_state_jarvis` at natural breakpoints; `memory_delete` when done. After context compression → `memory_recall(query="working state")` first, then targeted file reads.

## Skill routing

Use skills — don't reinvent with raw tools.

| Trigger | Skill |
|---|---|
| "реализуй #42" — implement single issue inline | `/implement` (TDD-mode auto-engages via SOUL.md grill-me checkbox + working_state UUIDs) |
| "делегируй #X #Y" — dispatch multiple issues to parallel subagents | `/delegate` (TDD-mode auto-engages via SOUL.md grill-me checkbox + working_state UUIDs) |
| "проверь результаты" / scheduled post-delegation | `/verify` |
| "что я делаю не так", "проанализируй сессии", "паттерны общения", weekly behavioral audit | `/reflect` (cross-session comms audit; old outcome-verification scope migrated to `/verify` + `/self-improve` per #510) |
| "исследуй", "research", "сравни" | `/research` |
| "улучши себя", self-improvement | `/self-improve` |
| "цели", "приоритеты" | `/goals` |
| New device bootstrap, "scheduled tasks setup" | `/setup-tasks` (Workshop-only per CONTEXT.md → *Workshop PC = sole routine host*; refuses elsewhere, `--cleanup` drops legacy entries) |
| ~~Daily scheduled tick~~ | ~~`/autonomous-loop`~~ — **SUPERSEDED**, pre-M44 catch-up baseline only. **Do not invoke for new flows.** No live cron registration since Medium-scope cleanup 2026-05-26 (legacy per-device cron jobs must be unregistered manually). Will be deleted when reactive-core M44 (`wake_driver` + `orchestrator`) ships. |
| "end" / "end quick" | `/end` (full) / `/end --quick` (fast) |
| Vague intuition (no written plan yet) / "у меня ощущение что", "может быть лучше но не знаю как", "обсудим концепт"; subsumes /research for in-debate factual grounding | `/reason` |
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
| "zoom out", unfamiliar code area, need higher-level map | `/zoom-out` |
| Issue triage / state machine / "ready for agent" | `/triage` |
| Author/edit a skill | `/write-a-skill` |
| "be brief", "caveman", token compression | `/caveman` |

Rules:
- GitHub issue work → /implement or /delegate, no exceptions. Raw Agent loses PR structure and verification.
- Multiple tasks → /delegate, but **Jarvis decides** what's subagent-suitable vs inline (context-heavy / cross-cutting / safety-critical stay inline). User trusts this call.
- **Grill trigger checkbox is mandatory** — every `/implement` and `/delegate` invocation runs it at start; rule and output routing live in SOUL §Grill trigger checkbox.
- **`/reason` (optional, intuition-stage) → `/grill` → `/to-spec` → `/to-tickets` → `/implement` (or `/delegate`)** is the canonical chain for new features. TDD-mode engages inside `/implement` and `/delegate` per the SOUL.md grill-me checkbox — there is no standalone `/tdd` skill. Each phase in a fresh session if context is heavy. Skip `/reason` when you already have a plan to validate ("оркестратор можно лучше — не знаю как" → start with `/reason`; "вот план X, проверь" → skip to `/grill`).
- If unsure → use the skill. Overhead near zero, cost of skipping is lost structure.
- **`/status` is anchored routing — bare/unrelated uses of the word do NOT fire it.** Only the exact triggers `статус`, `status`, or `статус <repo>` (the word as a standalone command, optionally naming a tracked repo) route to `/status`. A sentence that merely contains the word — "какой статус у PR #123", "статус деплоя в логах", "status code 500", a quoted error string — is a normal request answered in-context, never a trigger for a repo-state investigation.

### Responsibility split — interactive · `/delegate` · reactive-core orchestrator

Three places work can land. Pick by **who's present** and **how the work was triggered**, not by what the work is.

- **Interactive `/implement`** — operator present, one judgment-heavy issue, full SOUL loaded; SOUL §Grill trigger checkbox is the in-skill AFK-readiness backstop.
- **`/delegate`** — operator present and chose to fan out; AFK-eligible issues → parallel sandcastle subagents, admitted by CONTEXT.md → *Pre-dispatch gate*. Operator-driven dispatch, **not** the orchestrator.
- **Reactive-core orchestrator (M44)** — no operator; events cold-boot it and it triages **one** event into one of three dispositions, then hands off (CONTEXT.md → *orchestrator*, *Loop closure*).

Boundary: **orchestrator-emitted TASK rows carry the same AFK-fit/sandcastle semantics** as manually-triaged ones — `/to-tickets`'s checklist applies regardless of who emits the task, and an AFK-unsafe row goes to owner attention (no auto-spawn), same landing zone as a `/delegate` refusal. The orchestrator routes, it is not the principal (CONTEXT.md → *Invariants → Skills, infra & eval*).

## Autonomous work

User often leaves Jarvis to work alone. Core loop comes from §Engineering posture above + SOUL §Judgment calibration + SOUL §Goal & outcome awareness. "Aligned plans = standing orders" — when a multi-step plan was discussed and signed off, the alignment IS the approval; don't re-confirm at each checkpoint.

Project-specific addition — **transform tasks into verifiable goals**: "Fix bug" → write failing test → make it pass. "Add validation" → tests for invalid inputs → make them pass. "Refactor X" → tests pass before and after.

## Development process

- Branches from `main`. **PRs are for code, not for discussions.**
  - Code change → one issue, one PR; body includes `Closes #NNN`. Drive-by fixes without parent → create post-factum issue-bucket (see #183).
  - **Consolidation / batch PR** (bundles or supersedes the work of multiple issues — e.g. a stacked refactor that absorbs sibling branches, or a PR whose siblings get closed as "shipped via #X") → the body MUST carry a `Closes #N` line for **every** absorbed issue (here "absorbed" = its entire scope ships in this PR, not merely referenced), not just the umbrella or the one whose branch you happened to be on. Auto-close (native *and* `pr-merged.yml`) fires only from the PR's own `closingIssuesReferences`, built solely from this PR body's closing keywords (`Closes/Fixes/Resolves #N` and their `close/closed/fix/fixed/resolve/resolved` variants) — an absorbed issue you don't list gets neither close path and silently stays open with stale `sandcastle`/`in-progress` labels (this is #948 Mode 2: PR #900 shipped #845/#846/#847/#859/#860 but listed only `Closes #851`, leaving 5 open). Cross-repo: `Closes owner/other#N` is **not** auto-closed by `pr-merged.yml` (its `GITHUB_TOKEN` is repo-scoped — it skips+warns); close a foreign absorbed issue manually. When you close a sibling PR as "superseded by #X", carry over **that sibling's own** issue-closing keywords into #X's body — e.g. if the sibling listed `Closes #845, Closes #846`, add those exact lines (NOT `Closes #<siblingPR-number>`, which resolves to the wrong issue). Caveat: `closingIssuesReferences` is frozen at merge time — if **#X is already merged**, editing its body is documentation-only and fires no close; close the absorbed issues directly with `gh issue close #N --reason completed`. Never rely on a prose "shipped via #X" note — it is invisible to the linkage.
  - Hotfix (`priority:critical`) / refactor (`refactor:` title prefix) / `[no-issue]` marker → the three bypasses of the linked-issue requirement, enumerated in user-level CLAUDE.md gate 3 `require-linked-issue`. Commit-msg still needs `[no-issue]` when there's no parent issue (`.pre-commit-config.yaml` regex, #329).
  - Design RFC / proposal / debate → **GitHub Discussions, not an issue and not a PR.** Approval = thread resolution by the task initiator (user if user-started; orchestrator/PM if agent-started). Stable post-decision artifacts may land in `docs/design/` via direct commit; no PR ceremony.
  - Final decisions go to memory (`record_decision` / `memory_store`) — that is the queryable source of truth, not a markdown file.
- Check the Claude code-review comment before merging — it posts as an **issue-comment**, not a PR review, so check all reviewer surfaces. Copilot is no longer used (plan lapsed, decision 2026-05-22).

### Architecture sweep at milestone close

After a milestone closes (capability shipped), run `/improve-codebase-architecture` in a **fresh session**, never the one that closed the milestone (dumb zone). The skill:

1. Reads `CONTEXT.md` + ADRs + repo state.
2. Surfaces numbered list of *deepening opportunities* (shallow → deep modules, friction points, untested seams).
3. Grills you on selected candidates → architectural decisions → child issues attached to a follow-up milestone (or as standalone slices).

**Trigger (planned — #605):** the automatic ≥3-closed-slices SessionStart surface described in `milestone_hierarchy_v3` Rule 6 is not implemented. Until #605 lands the trigger is **manual**; small milestones (1–2 slices) skip the sweep.

**Cadence:** semantic, not temporal. The sweep follows capability shipping, never a date.

**Output discipline:** 1–2 actionable refactors → child issues attached to a follow-up milestone via grill chain. Rest goes to `.out-of-scope/<topic>.md` with reason. Don't try to action everything.

### Fix > track for trivial reversible (#428)

Trivial, reversible, scope-obvious change (<30 min, own repo): **fix inline**. Don't open a tracking issue you'll close in 5 minutes — that's paperwork. Issues are for things you can't finish now, want to discuss, or that will outlive this session.

- **Fix inline**: stale doc fragment (broken link, version mismatch); missing test for newly-touched code; typo/comment cleanup adjacent to other work; config drift between two files; lint warning on a file you just touched.
- **Open issue**: architectural reshape >1h; cross-cutting refactor needing coordination; behavior change user should weigh in on; anything touching another active area mid-flight; foreign-owner repo where Jarvis can't merge.

The `Fix > track` rule does **not** override the rest of the development process — fixes still go through PR review, with the `[no-issue]` commit-msg marker above.

### Path-filtered CI guards require a meta-test (#326)

Any workflow under `.github/workflows/` with a `paths:` filter that blocks PRs must ship with a co-located fixture test in `tests/ci/test_<name>_guard.py`. Convention: `.github/workflows/X-guard.yml` ⇒ `tests/ci/test_X_guard.py`.

The test covers two dimensions:
- **Config** — assert the workflow's `paths:` filter references the canonical file(s). If the canonical path changes, red CI forces the workflow to move with it. This is the exact class of bug that produced #289/#310/#311 (guard watched `supabase/schema.sql`, canonical was `mcp-memory/schema.sql` — guard silently passed for a sprint).
- **Logic** — reimplement the guard's decision rule in Python, assert it blocks/allows the scenarios it claims to. `schema-drift-check` is the proof-of-concept; new path-filtered guards follow the same pattern.

The meta-test suite runs via `.github/workflows/ci-meta.yml` on every PR (not itself path-filtered — that would be self-undermining).

### Milestone vs pillar hygiene

Entity definitions (pillar / milestone / slice, why "epic" is not used) live in CONTEXT.md → *Core entities*; the standing rules — no date in title, close on capability shipping, PRD in the milestone description, single slice = no milestone, no numerical WIP limit — are memory `milestone_hierarchy_v3` Rules 1–6 (always_load, injected every session). Shape:

```
pillar (narrative only) → goal (Type A) → milestone (capability + PRD) → slice (one PR)
```

Mechanics not covered there:
1. Retroactive — if related slices shipped without a milestone, create it, attach the issues+PRs, close it. History must be recoverable.
2. When user rushes and skips the milestone for grouped work — catch it: "milestone for these N slices?" before creating issues. Don't be a silent executor.

## Token economy

- Don't pay LLM tokens to run shell commands — fetch first, send only data.
- Prefer editing existing files over creating new ones.
- Use lighter models for mechanical tasks.

## Key files

Repo layout with intent — SOUL, device config, memory server, session-context hook, MCP registrations: CONTEXT.md → *Architectural shape*. Not in that tree: `scripts/memory-recall-hook.py` (UserPromptSubmit recall), `scripts/pretooluse-recall-hook.py`, and `.github/copilot-instructions.md` (process rules mirrored for GitHub).

If this file needs a change — propose it and explain why.
