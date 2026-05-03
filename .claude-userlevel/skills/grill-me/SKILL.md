---
name: grill-me
description: Interview the user relentlessly about a plan or design until reaching shared understanding, resolving each branch of the decision tree. Use when user wants to stress-test a plan, get grilled on their design, or mentions "grill me".
---

Interview the user relentlessly about every aspect of this plan until you reach shared understanding. Walk down each branch of the design tree, resolving dependencies between decisions one-by-one. For each question, provide your recommended answer.

Ask questions one at a time. If a question can be answered by exploring the codebase, explore the codebase instead of asking.

Resolve **WHY before HOW** — establish the problem the design solves before debating mechanism. If the user flags a "wrong question", you almost certainly skipped to mechanism.

## Memory protocol (load-bearing)

Pocock's original /grill-me had no memory layer. Ours does. The grill must consult memory on input and surface what it leaned on, not just record what it decided.

### Pre-grill load (one-shot at start)

Before the first Q:

1. **Hybrid recall — three passes:**
   - `memory_list(project=<project>, type=feedback, always_load=true)` — session-wide gates, surface unconditionally.
   - `memory_recall(query="grill-me <args> <extracted entities>", type=decision/feedback, brief=true, limit=15)`. **Always include the literal skill name (`grill-me`) in the query** so this skill's own contract memory (`grill_me_record_decision_gate` and any successor) surfaces every invocation. Skill-specific contracts are not always_load — they ride on the skill's own recall, per `always_loaded_context_budget_principle`.
   - If args are short or meta (≤5 words, or entity names like skill names dominate), second-pass recall with the entities expanded — don't lean on a narrow query.
   - Capture `id=<uuid>` from each brief hit into a local `name → uuid` map. **memories_used in record_decision takes UUIDs, not names** — the brief output already carries them.
2. **Outcomes for the area.** `outcome_list(scope=<area or topic>, severity≥medium, since=90d)`. If 2+ failures cluster → surface them in the very first Q before the user starts answering: "before we start, X failed twice in this area due to Y, proceed or rethink?"
3. **Repo context files.** Read `CONTEXT.md` (full — it's short by design). Glob `docs/adr/*.md` filenames; do not full-Read ADRs at start. Full-Read an ADR only when the grill walks into a topic its filename signals.

### Per-branch refresh (mid-grill)

When the grill crosses into a new sub-area of the design tree (not every Q — only branch-shifts), re-run `memory_recall(query=<sub-area>, type=decision/feedback, brief=true, limit=10)`. Point of the refresh: keep `memories_used` populated with sub-area-specific UUIDs at the moment of `record_decision`, not generic top-level recall.

### Memory use & staleness

Memory records can be stale. Use them, but:

- **Auto-flag obvious red signals (don't ask, ignore + note).** If a recalled memory references a file/skill/issue that no longer exists, or names a path that's been moved, treat it as untrustworthy. Don't ask the user about every dead reference; note them in the grill output for `/reflect` to consume.
- **Show-and-continue ritual (every Q-block).** When a Q-block leans on memory records, list them inline as `(leaning on: <one-line summary> — <uuid>, <age>d)`. Lets the user catch staleness in real time without an explicit question per memory. Keep it terse: 1-3 records per Q max, not the whole recall dump.
- For `reversibility=reversible` decisions older than ~60 days, downgrade their weight: still surface, but don't treat as constraint.

## Decision-recording contract (load-bearing)

Decisions made during a grill are queryable knowledge. Issue bodies are *not*. Every architectural resolution that survives the session **must** land in `record_decision` in real time, not at the end.

This contract exists because of a recurrent failure mode: grill resolves N sub-decisions, downstream `/to-issues` files them as issue bodies, the queryable decision log misses N entries, future sessions have to reconstruct from issue bodies (lossy) or working-state (frozen). See memory `decisions_belong_in_memory_not_gh_issue_bodies` and `record_decision_during_refactors`.

### When to record (per-Q rule)

Record a decision **immediately on resolution** — the same turn the user agrees — when the resolution is any of:

- Architectural: shape of a system, module boundary, data flow, lifecycle.
- Cadence / trigger / scheduling rule that will be encoded somewhere.
- Choice between named alternatives where rejecting the loser has consequences.
- Anything you'd want to recover the *why* of, six weeks from now.

Skip the call only for purely mechanical resolutions (naming, ordering, labels, copy-edits).

### What to pass to `record_decision`

- `decision`: one-line statement (the resolved answer, not the question).
- `rationale`: one paragraph — the *why* the user gave, not just what was chosen.
- `alternatives_considered`: every option discussed, with one-clause reason for rejection.
- `reversibility`: reversible / hard / irreversible — be honest, this gates downstream caution.
- `confidence`: 0.0–1.0; if you're below 0.6, flag the uncertainty in the grill, don't bury it.
- `memories_used`: UUIDs of memories that informed the choice (not names — UUIDs, per `record_decision_always_pass_memories_used`).
- `actor`: `session:<short-slug>` so the trail is recoverable.
- `project`: scope to the project being designed for.

Capture the returned episode UUID. Maintain a running list `decision_uuids[]` for the grill.

### Final completeness gate (refuse to finish without it)

Before you produce the closing summary:

1. Enumerate every Q resolved this session.
2. For each Q, classify: architectural-or-equivalent vs mechanical.
3. For each architectural Q, verify a `decision_uuids[]` entry exists.
4. **If any architectural Q has no UUID — stop. Record it now. Do not produce the summary until the list is whole.**

This gate is the whole point. Loosening it brings the failure mode back.

### Closing summary shape

The summary the user sees at end of grill must contain:

- The list of resolved Qs.
- For each architectural Q: its `decision_uuid`.
- A one-block "Hand-off to downstream skill" listing the UUIDs in the order they should be referenced by `/to-prd` / `/to-issues`.

Also save / update `working_state_<project>` with `decision_uuids[]` so a fresh-session downstream skill can find them without re-reading the grill transcript.
