# GitHub Process Runbook (Jarvis)

This runbook defines the operating loop for the Jarvis management-agent project.

Primary plan: `docs/PROJECT_PLAN.md`

## 1. Daily Triage

Every day:
- Review open issues by status and priority.
- Move blocked items to `status:blocked` with blocker note.
- Ensure each active task has one owner and one next action.
- Ensure each task has:
  - parent linkage via GitHub Parent issue/Sub-issues,
  - one area label (`area:*`),
  - one priority label (`priority:*`),
  - valid status label.

## 2. Planning Rules

- Work starts from milestone goals and epics.
- Epic children are execution items (`task`/`bug`), not nested epics.
- Each task should map to one PR.
- Large tasks (`XL`) must be split before implementation.
- Hotfixes are allowed without parent only when labeled `priority:critical` and documented in triage notes.

## 3. Implementation Rules

- Branch naming:
  - `feature/<issue-number>-<slug>`
  - `fix/<issue-number>-<slug>`
  - `chore/<issue-number>-<slug>`
- PR body must include: `Closes #NNN` (or `Fixes`/`Resolves`).
- One PR should not close multiple unrelated tasks.

## 4. Validation Rules

- Run local test suite before PR.
- CI must pass before merge.
- Any behavior-changing PR must include risk and rollback notes.
- Keep `main` always releasable.

## 5. Parent/Epic Rules

- Use GitHub sub-issues to link child tasks/bugs to each parent epic.
- Keep `Parent: #NNN` in child issue body only as optional context.
- Parent epics are not auto-closed.
- When all children close, workflow adds `status:children-done`.
- Human supervisor verifies DoD and closes epic manually.

## 6. GitHub Project Sync

Project fields in use:
- `Status`
- `Priority`
- `Phase`
- `Area`

Automation responsibilities:
- built-in project workflows: auto-add items, close -> Done
- repository workflows: issue status from labels, priority/area/phase sync, PR open -> In Progress, issue reopen -> Todo

## 7. Weekly Cadence

Every week:
- publish automated weekly report,
- review velocity, blockers, and defect trend,
- adjust next-week priorities,
- confirm scope stays aligned with MVP non-goals.

## 8. Scope Guardrails

Current non-goals:
- self-improvement module rollout,
- multi-agent/debate orchestration,
- advanced vector memory,
- plugin marketplace,
- cloud sync.

Any issue that reintroduces non-goals must be flagged and explicitly approved before execution.
