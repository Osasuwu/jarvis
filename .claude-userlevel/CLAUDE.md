# User-level CLAUDE.md

Process and protocol rules that apply across every project. Loaded into every Claude Code session as user-level memory.

**Source of truth:** `<jarvis-repo>/.claude-userlevel/CLAUDE.md`. The live file at `~/.claude/CLAUDE.md` is a mirror — `install.ps1 -Apply` propagates from source. Never edit the mirror; edits drift on next install.

Project-specific rules live in `<repo>/CLAUDE.md`. SOUL.md (`~/.claude/SOUL.md`) holds identity/personality; this file holds process.

## Memory & decision protocol

Skills consume this section instead of restating it. Three load-bearing rules: **recall before deciding**, **brief-mode UUIDs**, and the **`record_decision` contract**.

This is the **Tier 1** layer (soft prompt rule). Backstops:

- **Tier 2 — hooks.** Mechanical enforcement that can't be skipped (e.g. `PreToolUse` on `record_decision` blocks calls with empty `memories_used`).
- **Tier 3 — skill-specific gates.** Things that genuinely belong to one skill (e.g. `/grill`'s completeness gate, `/implement`'s already-done audit). Stay in the skill file.

If the empty-`memories_used` rate rises after centralising here, the relevant rule escalates Tier 1 → Tier 2 (issue #532 tracks this).

### 1. Recall before deciding

Before any non-trivial decision, save, or skill invocation, consult memory. Three passes — run in parallel where possible:

- **Always-load gates** — `memory_list(project=<project>, type=feedback, always_load=true)`. Surface unconditionally; these are session-wide rules that bind every skill.
- **Topic recall with skill name** — `memory_recall(query="<skill-name> <topic + entities>", type=decision/feedback, brief=true, limit=10–15)`. **The literal skill name MUST appear in the query** so skill-specific contract memories (e.g. `grill_me_record_decision_gate`) surface every invocation. Skill contracts are not always_load — they ride on this recall.
- **Outcomes for the area** — `outcome_list(scope=<area>, severity≥medium, since=90d)` when the work touches a known-failure region. 2+ failures cluster → surface in the first turn before acting.

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

Architectural resolutions go to `record_decision`. Issue bodies, PR bodies, PRD prose all decay; the queryable decision log doesn't. Skills that produce issues (`/to-prd`, `/to-issues`) reference `decision_uuids[]` rather than restating the *why* — see each skill for the section template.
