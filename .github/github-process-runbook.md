# GitHub Process Runbook (Jarvis)

This runbook defines the development process for the Jarvis repository itself.

**Important**: this is a dev process document, not a Jarvis feature spec. Jarvis features are OpenClaw skills in `skills/`.

Primary plan: `docs/PROJECT_PLAN.md`

## 1. Daily Development

When working on this repo:
- Check open issues by status and priority.
- Finish in-progress work before starting new tasks.
- Ensure each task has parent linkage, area label, priority label, and valid status.

## 2. Planning Rules

- Work starts from milestone goals and epics.
- Epic children are execution items (`task`/`bug`), not nested epics.
- Each task should map to one PR.
- Large tasks must be split before implementation.

## 3. Implementation Rules

- Branch naming:
  - `feature/<issue-number>-<slug>`
  - `fix/<issue-number>-<slug>`
  - `chore/<issue-number>-<slug>`
- PR body must include: `Closes #NNN` (or `Fixes`/`Resolves`).
- One PR should not close multiple unrelated tasks.

## 4. Validation Rules

- Test skills against real GitHub projects before PR.
- CI must pass before merge.
- Any behavior-changing PR must include risk and rollback notes.
- Keep `main` always releasable.

## 5. Parent/Epic Rules

- Use GitHub sub-issues to link child tasks/bugs to each parent epic.
- Keep `Parent: #NNN` in child issue body only as optional context.
- Parent epics are not auto-closed.
- When all children close, workflow adds `status:children-done`.
- Human owner verifies DoD and closes epic manually.

## 6. Scope Guardrails

Current scope: OpenClaw skills development (PM, then research).

See `docs/PROJECT_PLAN.md` for full scope definition and out-of-scope items.

Any issue that introduces out-of-scope work must be flagged and explicitly approved before execution.
