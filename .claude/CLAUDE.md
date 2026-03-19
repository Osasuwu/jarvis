# CLAUDE.md

Repository-level instructions for Claude-compatible agents.

## Source of truth

Use `.github/copilot-instructions.md` as the canonical process and scope instruction set.

## Key constraints

- One issue per PR.
- PR body must include linked issue (`Closes/Fixes/Resolves #NNN`).
- Preserve parent-child traceability across epics and tasks.
- Follow project non-goals and avoid unauthorized scope expansion.

## Quality baseline

- Run tests before submitting changes.
- Keep CI green.
- Add concise risk/rollback notes for non-trivial changes.
