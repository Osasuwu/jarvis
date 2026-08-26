# User-level CLAUDE.md

Process and protocol rules that apply across every project, loaded into every Claude Code session. Project-specific rules live in `<repo>/CLAUDE.md`; SOUL.md holds identity, this file holds process.

**Edit the source, never the mirror** — `<jarvis-repo>/.claude-userlevel/CLAUDE.md` is canonical, `install.ps1 -Apply` propagates it to `~/.claude/CLAUDE.md`.

The two imports below are what actually load identity and shared doctrine. Keep them **bare and on their own line** — that is the only form with evidence of resolving. Both files sat referenced mid-prose for months and silently never loaded, while a substring-matching guard stayed green (#1426).

@SOUL.md

@DOCTRINE.md

`SOUL.md` is identity, installed alongside this file from `<jarvis-repo>/config/SOUL.md`; no SessionStart hook step delivers it (#1328). `DOCTRINE.md` carries shared cross-repo norms — merge gates, protocol-layer model, owner-queue semantics, the sanctioned admin-merge cases. This file carries jarvis's own process on top of that shared floor — every project-repo CLAUDE.md, including jarvis's own, is a repo like any other and points *up* to this file and DOCTRINE.md, never the reverse.

## Memory & decision protocol

Skills consume this section instead of restating it. Three load-bearing rules: **recall before deciding**, **brief-mode UUIDs**, and the **`record_decision` contract**.

This is the **Tier 1** layer (soft prompt rule); Tier 2 hooks and Tier 3 skill gates back it up — DOCTRINE.md → *Protocol layers*. If the empty-`memories_used` rate rises after centralising here, the relevant rule escalates Tier 1 → Tier 2 (jarvis `CONTEXT.md` → *Protocol layers (ADR-0002)*, #532).

### 1. Recall before deciding

Before any non-trivial decision, save, or skill invocation, consult memory. Three passes — run in parallel where possible:

- **Always-load gates** — memories **tagged `always_load`**, surfaced by the SessionStart hook (`session-context.py` → `_query_always_load`, a `tags @> ['always_load']` query). There is **no `always_load` parameter** on `memory_list`/`memory_recall` — the gate is tag-based, not a query flag. Flipping the tag on a memory requires `record_decision` (trigger #4 below). Surface unconditionally; these are session-wide rules that bind every skill. (Mechanism detail: memory `always_load_tag_mechanism`.)
- **Topic recall with skill name** — `memory_recall(query="<skill-name> <topic + entities>", type=decision/feedback, brief=true, limit=10–15)`. **The literal skill name MUST appear in the query** so skill-specific contract memories (e.g. `grill_me_record_decision_gate`) surface every invocation. Skill contracts are not always_load — they ride on this recall.
- **Outcomes for the area** — `outcome_list(project=<area-project>, outcome_status="failure", limit=20)`, filtering the returned rows by `created_at` client-side for a recency window, when the work touches a known-failure region. 2+ failures cluster → surface in the first turn before acting. (`scope`/`severity`/`since` are not parameters of this tool — see its actual schema before calling.)

For mid-task branch shifts (entering a new sub-area of a design tree), re-run topic recall with sub-area-specific entities. Goal: keep `memories_used` populated with sub-area UUIDs at decision time, not generic top-level recall.

If args are short or meta (≤5 words, or entity names dominate), a second pass with entities expanded — don't lean on a narrow query.

### 2. Brief-mode → UUID map

`memory_recall(brief=true, ...)` returns `name=<slug>` AND `id=<uuid>` per hit. Parse both into a local `name → uuid` map at recall time.

**Every later `record_decision` call passes UUIDs in `memories_used`, not names.** The schema demands UUIDs; slugs drift. Per #325 audit: of 33 historical `decision_made` episodes, 12 stored names not UUIDs — every one was a broken FK in the outcome→memory join.

### 3. record_decision contract

When a resolution is architectural / cadence-defining / between named alternatives / has consequences past this session — emit `mcp__memory__record_decision` **immediately on resolution** (not batched at end).

Pass:

- `decision` — one line, the resolved answer (not the question).
- `rationale` — one paragraph, the *why* the user gave (not just what was chosen).
- `alternatives_considered` — every option discussed, each with one-clause rejection reason. Empty list is rare; "none discussed" is itself a flag.
- `reversibility` — `reversible | hard | irreversible`. Be honest; this gates downstream caution.
- `confidence` — `0.0–1.0`. If <0.6, flag the uncertainty in-line, don't bury it.
- `memories_used` — UUIDs (not names) from the recall map. Empty list valid only when nothing in memory informed the choice (rare; the rationale should note it).
- `actor` — `session:<short-slug>` so the trail is recoverable.
- `project` — scope to the project being designed for.

Capture the returned episode UUID. Maintain a running `decision_uuids[]` per session for handoff to downstream skills.

#### Trigger list — emit when ANY of these hold

1. **Issue implementation** — always, even if reversible. Outcome attribution needs the basis.
2. **`reversibility ∈ {hard, irreversible}`** — destructive DB ops, force-pushed history, published API changes.
3. **`confidence < 0.7`** — uncertain calls deserve recorded rationale so `/reflect` can classify failures as reasoning vs execution.
4. **Policy / schema / tag / config change** — `always_load` tags, protected-file edits, skill add/remove, hook config, schema migrations, installer manifest. Reversible but affects future sessions.
5. **Architectural direction picked** — resolved "chose X over Y" after discussion, even if reversible. The rationale matters more than the bit set.

Rule of thumb: "I just made a call that will outlive this session" → emit. "I just clarified my own thinking" → skip. When unsure, emit — one tool call vs. a `/reflect` blind spot.

#### Post-hoc marker

If a decision is recorded after-the-fact (catching up on a missed call, e.g. during `/end` reconciliation), encode `:post-hoc` into the `actor` field — `actor="session:<id>:post-hoc"`. `/self-improve` greps actor for regression patterns; real-time capture is the goal, post-hoc saves are a regression. (#517 tracks adding a structured `post_hoc` field.)

### Memory staleness

Memory records can be wrong:

- **Dead references** — file/skill/issue that no longer exists: ignore + note in skill output for `/reflect`. Don't ask the user about every dead reference.
- **Show-and-continue** — when a turn leans on memory, list inline as `(leaning on: <one-line> — <uuid>, <age>d)`. Catches staleness in real time without a question per memory. Keep terse: 1–3 records per turn max.
- **Old reversibles** — `reversibility=reversible` decisions older than ~60 days: surface but don't treat as a constraint.

### Decisions belong in memory, not in issue/PR bodies

Architectural resolutions go to `record_decision`. Issue bodies, PR bodies, PRD prose all decay; the queryable decision log doesn't. Skills that produce issues (`/to-spec`, `/to-tickets`) reference `decision_uuids[]` rather than restating the *why* — see each skill for the section template.

## Repo policy — auto-merge & merge gates

Merging in an owned repo is gated by four required CI checks on the default branch — `review`
(the code-review verdict), `owner-queue-guard`, `require-linked-issue`, and the repo's own test
gates. They are branch-protection-enforced, so they need no cooperation from you: gate-by-gate
semantics, the per-repo files that implement them, and the repo-baseline settings that apply
them live in `~/.claude/reference/merge-gates.md`. Read it when changing a gate, onboarding a
repo, or diagnosing a stuck PR. What you must act on without reading anything:

- **Drafts are the manual hold.** A PR stays in draft while your attention is owed (design
  feedback pending, intentional batching); drafts never auto-merge. Once flipped to ready, the
  four gates are the merge gate. Use `status:owner-queue` only for the rarer case:
  content-complete, so it can pass review, but you still want to eyeball it. Don't reach for
  the label when draft already covers it.
- **Private+Free repos have no auto-merge.** `gh pr merge --auto` is rejected on
  `SergazyNarynov/redrobot`. The gates still apply; the final merge is manual when CI is green
  (`gh pr merge <N> --squash --delete-branch`). Don't retry `--auto`.
- **Never normalize a bypass.** A gate that cannot run is not a gate that passed. The two
  sanctioned admin-merge cases and the freeze rule are in DOCTRINE.md → *Review-blind
  carve-out*, *Sanctioned stop-gap merge*, *Merge-freeze doctrine*.

## Filing issues — route through the right skill

Do **not** open issues with a raw `gh issue create` / `mcp github issue_write` mid-session. Raw creation bypasses the project's issue schema, so the issue lands missing type/milestone/required-field metadata and rots off milestone-scoped triage — the exact leak `/file-issue`'s hygiene gate exists to catch.

| What you have | Skill |
|---|---|
| One follow-up / finding / tech-debt / drive-by bug | **`/file-issue`** |
| A plan/PRD to break into multiple end-to-end slices | **`/to-tickets`** |

Both skills read the project's label/field vocabulary from its CLAUDE.md and issue templates — they do not hardcode it. A project may ship a concrete `/file-issue` override under `.claude/skills/` that bakes in its repo slug and required fields; that shadows this generic one within that repo. This is the adoption pair for the skill: the capability is only used if the routing points at it (per `capability_needs_adoption_slice`).

## Tooling — MCP servers

User-scope MCP servers (registered by the installer from `.claude-userlevel/.mcp.json`): `memory`, `status`, `github`, `obsidian` (device-gated — only where `OBSIDIAN_VAULT_PATH` is set). A server may declare `"x-jarvis-requires-env": "<VAR>"`; the installer skips it on devices where that var is unset, so the same source installs correctly everywhere. (`uml`, `context7`, `sequential-thinking` removed 2026-08-26 — `uml` unused; `context7`/`sequential-thinking` audited across ~25 session transcripts and found chronically disconnected with zero evidence of a successful call, only tool-schema overhead. For library/framework/API docs, use `WebFetch`/`WebSearch` or the `claude-code-guide` agent for harness-specific questions; re-add if a future session confirms they actually connect.)

## Pull-only references — check before guessing terminology

Some repos keep a Glossary or reference index deliberately **pull-only** (not always-loaded, to keep it out of every session's token budget) — the repo's own `CLAUDE.md`/`CONTEXT.md` names where it lives. Before asserting the meaning of an unfamiliar repo-specific term, flag, or mechanism name, `Read` or `Grep` that repo's pull-only index first — a guess from training data or a prior repo's conventions is the same failure mode the context7 rule above exists to prevent for libraries, just aimed at a repo's own vocabulary instead of a library's API. This rule is generic on purpose: it says "check the current repo's own pointer," not any specific repo's file, so it holds across every repo this file loads into (per the one-directional layering invariant — user-level cites the pattern, never a specific repo's `CONTEXT.md`).
