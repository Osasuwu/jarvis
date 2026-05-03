---
name: to-issues
description: Break a plan, spec, or PRD into independently-grabbable issues on the project issue tracker using tracer-bullet vertical slices. Use when user wants to convert a plan into issues, create implementation tickets, or break down work into issues.
---

# To Issues

Break a plan into independently-grabbable issues using vertical slices (tracer bullets).

Issue tracker conventions and triage label vocabulary should be defined in the project's CLAUDE.md or context docs. If unclear, ask the user before publishing anything.

## Process

### 0. Memory & context load

Run before anything else, even before fetching a passed-in issue reference:

1. **Always-load gates.** `memory_list(project=<project>, type=feedback, always_load=true)`. These rules constrain how the breakdown is shaped (e.g. label vocabulary, PR-scope rules, naming conventions).
2. **Topic recall — include the skill name in the query.** `memory_recall(query="to-issues <source-material topic>", type=decision/feedback, brief=true, limit=10)`. The literal skill name `to-issues` ensures this skill's own contract memory (e.g. `grill_me_record_decision_gate`, which tags `to-issues`) surfaces every invocation. Skill-specific contracts are not always_load — they ride on the skill's own recall. Capture `id=<uuid>` from the brief output into a local `name → uuid` map — these UUIDs feed the `## Decisions` section in each issue body.
3. **Repo context files.** Read `CONTEXT.md`. Glob `docs/adr/*.md` filenames; full-Read only ADRs whose filename matches the area being broken down. Issue titles + descriptions must use this vocabulary.

If a recalled memory references a file/skill/issue that no longer exists, ignore it and note in output for `/reflect` — don't ask the user about every dead reference. For load-bearing memory hits surface them inline as `(leaning on: <one-line> — <uuid>)` so the user can interject if stale.

### 1. Gather context

Work from whatever is already in the conversation context. If the user passes an issue reference (issue number, URL, or path) as an argument, fetch it from the issue tracker and read its full body and comments.

**If the source material came from `/grill-me`** (current conversation contains a grill, OR the upstream working-state has `decision_uuids[]`), collect the list of decision episode UUIDs. They will be referenced from each issue body. If the conversation looks like a grill (long Q-resolved thread on architectural choices) but no UUIDs exist — **stop and run the grill-me completeness gate first** (record the missing decisions). Issues that ship without decision references when a grill preceded them re-introduce the failure mode that this contract exists to prevent.

### 2. Explore the codebase (optional)

If you have not already explored the codebase, do so to understand the current state of the code. Issue titles and descriptions should use the project's domain glossary vocabulary, and respect ADRs in the area you're touching.

### 3. Draft vertical slices

Break the plan into **tracer bullet** issues. Each issue is a thin vertical slice that cuts through ALL integration layers end-to-end, NOT a horizontal slice of one layer.

Slices may be 'HITL' or 'AFK'. HITL slices require human interaction, such as an architectural decision or a design review. AFK slices can be implemented and merged without human interaction. Prefer AFK over HITL where possible.

<vertical-slice-rules>
- Each slice delivers a narrow but COMPLETE path through every layer (schema, API, UI, tests)
- A completed slice is demoable or verifiable on its own
- Prefer many thin slices over few thick ones
</vertical-slice-rules>

### 4. Quiz the user

Present the proposed breakdown as a numbered list. For each slice, show:

- **Title**: short descriptive name
- **Type**: HITL / AFK
- **Blocked by**: which other slices (if any) must complete first
- **User stories covered**: which user stories this addresses (if the source material has them)

Ask the user:

- Does the granularity feel right? (too coarse / too fine)
- Are the dependency relationships correct?
- Should any slices be merged or split further?
- Are the correct slices marked as HITL and AFK?

Iterate until the user approves the breakdown.

### 5. Publish the issues to the issue tracker

For each approved slice, publish a new issue to the issue tracker. Use the issue body template below. Apply the project's **triage-entry label** (the label that signals "needs triage"; commonly `needs-triage`, but use whatever the project's CLAUDE.md / context docs define). If no such mapping exists, ask the user before applying any label.

Publish issues in dependency order (blockers first) so you can reference real issue identifiers in the "Blocked by" field.

<issue-template>
## Parent

A reference to the parent issue on the issue tracker (if the source was an existing issue, otherwise omit this section).

## What to build

A concise description of this vertical slice. Describe the end-to-end behavior, not layer-by-layer implementation.

## Acceptance criteria

- [ ] Criterion 1
- [ ] Criterion 2
- [ ] Criterion 3

## Blocked by

- A reference to the blocking ticket (if any)

Or "None - can start immediately" if no blockers.

## Decisions

References to `decision_made` episode UUIDs that this slice implements. Format: `- <uuid> — one-line summary of the decision`. Omit this section ONLY if no upstream grill informed the slice. If a grill preceded and this section is missing, the issue is invalid.

</issue-template>

Do NOT close or modify any parent issue.
