---
name: autonomous-loop
description: "Autonomous orchestrator: perceive events, evaluate against goals, decide and act within safety bounds. Runs daily via scheduled task or manual invocation."
version: 1.0.0
---

# Autonomous Loop Orchestrator

Daily orchestrator that perceives events and perception outputs (goals, risks, research findings), evaluates them against active goals, decides the top action within safety bounds, and executes it autonomously.

Implements the perceive→evaluate→decide→act→record loop from the Autonomous Work Loop architecture.

## Usage

- `/autonomous-loop` — manual invocation (full run)
- Scheduled: daily 09:00 (after morning-brief)
- Part of: Jarvis Pillar 2 — Autonomous Work Loop

## Architecture

```
Load Context → Build Candidates → Score → Pick Top → Risk-Gate → Execute → Record
```

## Step 1 — Load Context

In parallel, load:

- `goal_list(status="active")` — active goals for evaluation
- `memory_recall(query="morning brief")` — overnight activity + daily plan
- `memory_recall(query="risk radar")` — CI failures, security alerts, stale issues
- `memory_recall(query="research findings unacted")` — research outputs waiting for action
- `memory_recall(query="autonomous_loop_last_run")` — dedup check (don't run twice in same day)

**Dedup rule:** If `autonomous_loop_last_run` exists and is today's date, skip gracefully (return "Already ran today").

## Step 2 — Build Action Candidates

From perception outputs, generate candidates:

- **Risks** with severity HIGH+ → mitigation action
- **Goal deadline** < 3 days → escalation action (prioritize, nudge timeline)
- **Goal progress** stale > 7 days → review action (check status, unblock)
- **Actionable research** (marked in memory) → execute finding
- **Events** from event queue (HIGH+ severity) → handle event
- **Morning-brief** items marked "needs action" → act on them

## Step 3 — Score Each Candidate

```
score = goal_alignment(0-3) × urgency(1-3) + severity_bonus
```

- **goal_alignment**: 3 = directly serves P0 | 2 = serves P1 | 1 = serves P2 | 0 = unaligned
- **urgency**: 3 = blocking/deadline | 2 = should be soon | 1 = can wait
- **severity_bonus**: +3 for CRITICAL risk | +2 for HIGH | +1 for MEDIUM

**Disqualify:** unaligned (goal_alignment=0) or uncertain candidates.

## Step 4 — Pick Top Action

Select the highest-scoring action that:
1. Falls within autonomy bounds (risk classification in Step 5)
2. Is not a protected file (`mcp-memory/server.py`, `SOUL.md`, `CLAUDE.md`, `.mcp.json`)
3. Has not already been actioned (check memory)

**No high-priority candidates?** Skip gracefully — don't invent work.

## Step 5 — Risk Classification

| Risk | Examples | Autonomy |
|------|----------|----------|
| **Low** | Create issue, fix label, memory cleanup, triage | Auto-execute |
| **Medium** | Run self-improve, create PR, update goal, tag memory | Auto-execute + record |
| **High** | Architecture change, SOUL.md, memory schema, protected files | Save proposal only |

## Step 6 — Execute Action

Based on risk classification:

**Low** → execute immediately
- Create GitHub issue: `issue_write(method="create", ...)`
- Memory operations: `memory_store(...)`, `goal_update(...)`
- Tag or label work: `gh issue edit`, `gh pr edit`

**Medium** → execute and record
- Invoke skill: `/self-improve`, `/research`, `/risk-radar`
- Create PR: delegate via `/delegate` or `gh pr create`
- Update goal: `goal_update(slug=..., progress=...)`

**High** → save proposal to memory, skip execution
- Record: `memory_store(type="project", name="autonomous_proposals", ...)`
- Output proposal text to user

## Step 7 — Record Outcome

Every action logs to both memory and task_outcomes (Pillar 3):

```
outcome_record(
  task_type: "autonomous",
  task_description: "<action title>",
  outcome_status: "success" | "partial" | "failure",
  outcome_summary: "<what was done, reasoning, result>",
  goal_slug: "<aligned goal slug if any>",
  project: "jarvis",
  lessons: "<what was learned>",
  pattern_tags: ["autonomous-loop", "<action-area>"]
)
```

Also update dedup marker and goal progress:

```
memory_store(
  type="project",
  name="autonomous_loop_last_run",
  content="{\"date\": \"YYYY-MM-DD\", \"action\": \"...\", \"score\": N}",
  description="last orchestrator run"
)
```

If action advances a goal → `goal_update(slug=..., progress_pct=...)`.

## Safety Rules

**Never:**
- Touch protected files: `.mcp.json`, `SOUL.md`, `CLAUDE.md`, `mcp-memory/server.py`
- Create more than 1 PR per run
- Execute High-risk actions without explicit proposal

**Always:**
- Dedup: check `autonomous_loop_last_run` before acting
- Risk-gate: only auto-execute Low/Medium actions
- Record: every action goes to memory for learning
- Graceful exit: if no candidates, return "No high-priority actions" and exit

## Output

```markdown
# Autonomous Loop — YYYY-MM-DD

## Perception
- <N goals loaded, deadline alerts, stale work>
- <N risks flagged, severity summary>
- <N research findings, M events in queue>

## Candidates (scored)
| Action | Alignment | Urgency | Score | Risk |
|--------|-----------|---------|-------|------|
| <action 1> | <score> | <score> | <total> | Low/Med/High |

## Selected
**<Title>** — Score: N | Risk: Low/Medium/High

## Execution
- [EXECUTED / PROPOSED]: <what was done or proposed>
- <link to created issue/PR/memory>

## Status
- ✓ Action recorded to memory
- ✓ `autonomous_loop_last_run` updated
```

If no candidates: "No high-priority actions found. System running normally."

## Implementation Notes

1. **Parallel loads:** Use `memory_recall` with `limit=1` for each query to get most recent memory
2. **Scoring:** Treat missing fields conservatively (e.g., missing urgency = 1)
3. **Events:** Read from `events_list()` if available; skip if unavailable
4. **Graceful degradation:** If any perception output fails, continue with what loaded successfully
5. **Timezone:** All date comparisons use local time
