# Agents Configuration (Workspace)

This repository is optimized for agent-assisted development under one human supervisor.

Primary instructions for GitHub Copilot are in `.github/copilot-instructions.md`.

## Rules for All Agents

- Follow issue hierarchy: Milestone -> Epic -> Task/Bug.
- Always link implementation PRs to one issue (`Closes #NNN`).
- Respect branch naming convention and small-PR policy.
- Keep project metadata healthy (status, priority, area, phase).
- Do not introduce out-of-scope systems without explicit approval.

## Active Scope

- PM + TechLead MVP for development process management.
- Controlled Git workflow execution with human supervision.

## Out of Scope (Current)

- self_improvement rollout
- multi-agent/debate
- vector database memory
- plugin marketplace
- cloud/multi-device sync
