# Jarvis Copilot Instructions

Use when working in this repository with GitHub Copilot in VS Code.

## Product Goal

Build and operate a development-management AI agent that can:
- plan and decompose IT project work,
- coordinate delivery through issues, PRs, and project board states,
- execute limited Git workflows safely under human supervision.

Current non-goals:
- self-improvement/autonomous self-editing,
- multi-agent/debate orchestration,
- vector DB long-term memory,
- plugin marketplace,
- cloud/multi-device sync.

## Operating Model

Single human supervisor, agent-assisted delivery.

1. Plan in issues and epics.
2. Execute through small PRs linked to one issue.
3. Keep GitHub Project fields in sync.
4. Run daily triage and weekly reporting.

## Git Rules

- Branch naming: `feature/<issue-number>-<short-desc>`, `fix/<issue-number>-<short-desc>`, `chore/<issue-number>-<short-desc>`.
- PR body must include linked issue line: `Closes #<issue-number>` (or `Fixes`/`Resolves`).
- Do not merge directly to `main`.
- Keep one task per PR.

## Issue Hierarchy

Milestone -> Epic -> Task/Bug

- Every task must include a parent epic reference in the body: `Parent: #NNN`.
- Every epic must have a `Children` section with markdown checkboxes.
- Epics are closed manually after DoD verification.

## Labels

Type labels:
- `epic`, `task`, `bug`

Priority labels:
- `priority:critical`, `priority:high`, `priority:medium`, `priority:low`

Status labels:
- `status:ready`, `status:in-progress`, `status:review`, `status:blocked`, `status:children-done`

Area labels:
- `area:core-agent`, `area:workflow-github`, `area:tools`, `area:quality`, `area:docs`, `area:release`

## Project Phases

- `P1 Foundation` - governance and delivery scaffolding
- `P2 PM+TechLead MVP` - planning/triage/supervision loop
- `P3 Reliability` - stronger guardrails and quality automation
- `P4 Capability Expansion` - broaden management capabilities
- `P5 Stabilization` - consistency, predictability, and release readiness

## Quality Gates

For code changes:
- run tests locally before PR,
- keep CI green,
- document risks and rollback notes in PR.

For process changes:
- ensure issue templates and workflows remain consistent,
- preserve parent-child traceability,
- avoid introducing automations that silently mutate scope.
