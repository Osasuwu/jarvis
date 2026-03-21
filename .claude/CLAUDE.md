# CLAUDE.md

Repository-level instructions for Claude-compatible agents.

## What this project is

Jarvis — universal personal AI agent built on OpenClaw. This repo contains custom skills, configuration, and documentation. See `docs/PROJECT_PLAN.md` for full context.

## Source of truth

Use `.github/copilot-instructions.md` as the canonical process and scope instruction set.

## Key distinction

- `skills/` = Jarvis features (OpenClaw skills)
- `.github/` = development process for this repo (CI, PR checks, issue templates)

Do not confuse the two.

## Key constraints

- One issue per PR.
- PR body must include linked issue (`Closes/Fixes/Resolves #NNN`).
- Preserve parent-child traceability across epics and tasks.
- Follow project scope — check `docs/PROJECT_PLAN.md` before expanding scope.

## Quality baseline

- Test skills against real GitHub projects before PR.
- Keep CI green.
- Add concise risk/rollback notes for non-trivial changes.
