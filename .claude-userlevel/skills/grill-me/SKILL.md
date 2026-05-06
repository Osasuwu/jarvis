---
name: grill-me
description: Interview the user relentlessly about a plan or design until reaching shared understanding, resolving each branch of the decision tree. Use when user wants to stress-test a plan, get grilled on their design, or mentions "grill me".
---

Interview the user relentlessly about every aspect of this plan until you reach shared understanding. Walk down each branch of the design tree, resolving dependencies between decisions one-by-one. For each question, provide your recommended answer.

Ask questions one at a time. If a question can be answered by exploring the codebase, explore the codebase instead of asking.

Resolve **WHY before HOW** — establish the problem the design solves before debating mechanism. If the user flags a "wrong question", you almost certainly skipped to mechanism.

## Memory protocol

The recall protocol (always_load gates, skill-name-in-query, brief-mode UUID map, mid-task refresh) and the staleness rules live in user-level CLAUDE.md `## Memory & decision protocol`. Apply them with `<skill-name>=grill-me`.

Per-grill specifics on top of that protocol:

- **Pre-grill outcomes pass.** `outcome_list(scope=<area or topic>, severity≥medium, since=90d)`. If 2+ failures cluster → surface them in the very first Q before the user starts answering: "before we start, X failed twice in this area due to Y, proceed or rethink?"
- **Repo context files.** Read `CONTEXT.md` (full — it's short by design). Glob `docs/adr/*.md` filenames; full-Read only when the grill walks into a topic the filename signals.
- **Per-branch refresh.** When the grill crosses into a new sub-area of the design tree (branch-shifts only, not every Q), re-run topic recall with sub-area entities. Goal: keep `memories_used` populated with sub-area-specific UUIDs at the moment of `record_decision`.

## Decision-recording contract — completeness gate (skill-specific)

The general `record_decision` contract (when to emit, what to pass, post-hoc marker) lives in user-level CLAUDE.md `### record_decision contract`. The grill adds a **completeness gate** on top — Tier 3, can't be lifted to global because only the grill knows what counts as a "resolved Q".

This gate exists because of a recurrent failure mode: grill resolves N sub-decisions, downstream `/to-issues` files them as issue bodies, the queryable decision log misses N entries, future sessions reconstruct from issue bodies (lossy) or working-state (frozen). See memory `decisions_belong_in_memory_not_gh_issue_bodies`.

For each architectural Q resolved during the grill, capture the returned episode UUID into a running `decision_uuids[]` list.

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
