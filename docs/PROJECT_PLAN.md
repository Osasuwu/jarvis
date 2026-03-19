# Jarvis Project Plan

Version: 1.0
Date: 2026-03-20
Status: Active

## 1. Purpose

This is the strategic plan for Jarvis as a development-management AI agent.

Use this document to:
- decide what to build next,
- keep scope focused,
- align issue workflow with delivery outcomes,
- control risk in agent-assisted development.

## 2. Problem and Vision

### Problem

Single-developer and small-team software projects lose time on planning, triage, and delivery coordination. Code can be generated quickly, but process quality degrades without strict governance.

### Vision

Jarvis acts as PM + Tech Lead assistant:
- decomposes goals into epics/tasks,
- keeps GitHub project metadata consistent,
- guides coding agents through safe PR-based delivery,
- provides daily and weekly execution visibility.

## 3. Scope

### In Scope (Current)

- GitHub workflow orchestration (issues, labels, milestones, PR linkage)
- Delivery supervision loop (daily triage + weekly reports)
- Controlled Git operations through PR flow
- Repository health guardrails (CI + schema checks + process checks)

### Out of Scope (Current)

- self_improvement rollout
- multi-agent/debate orchestration
- vector DB long-term memory
- plugin marketplace
- cloud/multi-device sync

## 4. Operating Model

- One human supervisor owns priorities and final acceptance.
- Agents execute implementation tasks through issues and PRs.
- Every change must be traceable to a single issue.
- Project board fields are the source of delivery truth.

## 5. Delivery Phases

### P1 Foundation
Goal: establish governance and workflow scaffolding.
Exit criteria:
- issue templates/workflows active,
- labels and milestones normalized,
- CI and PR checks enforced.

### P2 PM+TechLead MVP
Goal: make Jarvis reliable for planning and supervision.
Exit criteria:
- daily triage loop running,
- project board sync in place,
- weekly reporting stable.

### P3 Reliability
Goal: strengthen quality and guardrails.
Exit criteria:
- stricter quality checks,
- reduced process drift,
- stable lead time and failure rate.

### P4 Capability Expansion
Goal: extend management features without scope creep.
Exit criteria:
- measurable planning improvements,
- prioritized expansion based on telemetry.

### P5 Stabilization
Goal: predictable and repeatable delivery.
Exit criteria:
- process documentation finalized,
- low operational friction,
- release readiness.

## 6. Decision Rules

When a new idea appears:
1. classify as in-scope or out-of-scope,
2. if out-of-scope, park in backlog with explicit label and no active task,
3. if in-scope, attach to the current phase or next phase with rationale,
4. split into epic/task before implementation.

When uncertain what to do next:
1. unblock `status:blocked` high-priority tasks,
2. finish in-progress work before starting new work,
3. prefer tasks that improve process reliability over feature expansion.

## 7. Risk Register

R1: Process drift from issue/PR rules.
- Mitigation: schema checks, PR body check, daily triage.

R2: Scope creep into non-goals.
- Mitigation: explicit non-goal policy, supervisor approval for exceptions.

R3: Agent-generated low-quality changes.
- Mitigation: CI gates, small PR policy, mandatory risk/rollback notes.

R4: Project board inconsistency.
- Mitigation: label sync + project sync automation.

R5: Bus factor = 1.
- Mitigation: documentation-first workflow and repeatable runbooks.

## 8. Cadence

Daily:
- triage statuses,
- fix metadata inconsistencies,
- review blockers.

Weekly:
- review report,
- adjust priorities and phase focus,
- validate scope alignment.

## 9. Success Metrics

- PRs linked to issues: 100%
- CI pass rate before merge: 100%
- tasks with valid parent linkage: >= 95%
- blocked task aging trend: decreasing
- weekly delivery predictability: improving phase-over-phase
