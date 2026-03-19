# Jarvis GitHub Operating System

This folder defines the delivery workflow for Jarvis as an AI-managed software project.

## Objective

Enable one human supervisor and multiple coding agents to deliver safely through:
- structured issue hierarchy,
- strict PR linkage and quality gates,
- synchronized GitHub Project fields,
- daily triage and weekly reporting.

## Files

| File | Purpose |
|------|---------|
| `copilot-instructions.md` | Workspace instructions for GitHub Copilot in VS Code |
| `github-process-runbook.md` | Day-to-day operating runbook |
| `ISSUE_TEMPLATE/*.yml` | Epic/Task/Bug issue templates |
| `PULL_REQUEST_TEMPLATE.md` | Required PR structure |
| `workflows/*.yml` | Automation (validation, sync, reports) |

## Project Hierarchy

```
Milestone -> Epic -> Task/Bug
```

- Every task or bug should reference `Parent: #NNN` unless it is an approved hotfix.
- Every epic must include `## Children` with task checkboxes.
- Epics are closed manually after DoD review.

## Required Labels

Type:
- `epic`, `task`, `bug`

Priority:
- `priority:critical`, `priority:high`, `priority:medium`, `priority:low`

Status:
- `status:ready`, `status:in-progress`, `status:review`, `status:blocked`, `status:children-done`

Area:
- `area:core-agent`, `area:workflow-github`, `area:tools`, `area:quality`, `area:docs`, `area:release`

## Required Workflows

- `pr-body-check.yml`: PR must include linked issue (`Closes/Fixes/Resolves #NNN`).
- `parent-notify.yml`: tracks parent epic progress and adds `status:children-done`.
- `issue-schema-check.yml`: validates issue body schema.
- `ci.yml`: test and quality gate.
- `weekly-report.yml`: weekly delivery summary.
- `project-sync.yml`: sync labels/events to Project fields.

## Default Flow

1. Create or refine epic and child tasks.
2. Pick one `status:ready` task.
3. Implement in one branch and one PR linked to that task.
4. Pass CI and checks, merge to `main`.
5. Review parent epic when children complete.

## Notes

- Current product scope is management-agent MVP (PM + Tech Lead behavior).
- `self_improvement`, multi-agent orchestration, marketplace, and cloud sync are out of scope for current MVP.
