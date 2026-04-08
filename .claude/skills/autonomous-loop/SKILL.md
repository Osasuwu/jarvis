---
name: autonomous-loop
description: "Autonomous orchestrator: loads perception outputs, scores actions by goal alignment, executes within safety bounds. Runs daily or on demand."
version: 1.0.0
---

# Autonomous Loop — Orchestrator

Proactive agent that turns perception into action. Reads outputs from morning-brief, risk-radar, nightly-research, and intel — then decides what to do based on active goals.

**Runs as scheduled task (daily 09:00) or manually via `/autonomous-loop`.**

---

## Environment

This is a **local** skill. It runs on the owner's machine with full MCP access.

Use standard tools: `memory_recall`, `memory_store`, `goal_list`, `goal_update`, `events_list`, `events_mark_processed`, `mcp__github__*`, `Bash(gh ...)`.

---

## Step 0 — Deduplication

```
memory_recall(query="autonomous_loop_last_run", type="project", limit=1)
```

If last run was **today** (same date in content) → stop. Output: "Already ran today, skipping."

If NOT a dedup hit → proceed.

---

## Step 1 — Load context (parallel)

Run all in parallel:
```
goal_list(status="active")
events_list(include_processed=false, limit=20)
memory_recall(query="morning_brief_latest", type="project", limit=1)
memory_recall(query="risk_radar_latest", type="project", limit=1)
memory_recall(query="nightly research", type="reference", limit=3)
memory_recall(query="working_state", type="project", limit=1)
memory_recall(query="autonomous_action_log", type="project", limit=1)
memory_recall(query="pm_report", type="project", limit=3)
```

PM reports (tagged `pm-report`) contain structured findings from PM agents. Parse the `Status` field: CRITICAL/BLOCKED → high-priority candidate.

---

## Step 2 — Build action candidates

Scan loaded context and extract actionable items. Sources:

### From events queue (highest priority — real-time signals):
- CRITICAL/HIGH events → immediate candidate (investigate, fix, escalate)
- `ci_failure` → check workflow, diagnose, create issue or fix
- `pr_approved` + CI green → merge candidate
- `security_alert` → investigate, create issue
- After handling, mark processed: `events_mark_processed(event_ids=[...], processed_by="autonomous-loop", action_taken="...")`

### From risk-radar:
- Any finding with severity CRITICAL or HIGH → candidate
- Action: investigate, create issue, or fix directly

### From goals:
- Goal with deadline < 3 days from today → escalation candidate
- Goal with no progress update > 7 days → review candidate
- P0 goal not being actively worked → flag candidate

### From morning-brief:
- PRs marked "ready to merge" → merge candidate
- PRs marked "needs response" → respond candidate
- Issues marked "new work" aligned with active goals → triage candidate

### From nightly-research:
- Findings with `Actionable: yes` that don't have a corresponding GitHub issue → create issue candidate
- Findings relevant to stalled goals → research-to-action candidate

### From previous action log:
- Actions from yesterday that need follow-up → follow-up candidate

If **no candidates** found → save log, stop. Don't invent work.

---

## Step 3 — Score candidates

For each candidate, compute:

```
score = goal_alignment × urgency + severity_bonus
```

Where:
- `goal_alignment`: 3 = directly serves P0 goal, 2 = P1, 1 = P2, 0 = unrelated
- `urgency`: 3 = blocking or deadline imminent, 2 = should be done soon, 1 = can wait
- `severity_bonus`: +3 for CRITICAL risk, +2 for HIGH risk, +1 for MEDIUM risk, 0 otherwise

**Tiebreaker:** prefer lower-effort actions (quick wins first).

---

## Step 4 — Pick top action

Select the highest-scoring candidate.

If the top candidate's score < 3 → skip (too low signal). Save log, stop.

---

## Step 5 — Risk classification

| Risk | Criteria | Action |
|------|----------|--------|
| **Low** | Create/close issue, fix labels, memory cleanup, goal update, merge approved PR | Auto-execute |
| **Medium** | Run `/triage`, run `/self-improve`, create PR, board reorganization | Auto-execute, record in detail |
| **High** | Architecture change, SOUL.md edit, memory schema change, CLAUDE.md edit | Save proposal to memory only |

**Never auto-execute:**
- Editing `.mcp.json`, `mcp-memory/server.py`, `config/SOUL.md`, `CLAUDE.md`, env files
- Creating more than 1 PR per run
- Force-pushing, deleting branches, closing issues in bulk (>3)

---

## Step 6 — Execute

Based on risk level:

### Low risk → do it
```bash
# Examples:
gh issue create --repo <owner/repo> --title "..." --body "..." --label "..."
gh pr merge <number> --repo <owner/repo> --squash
```
Or: `goal_update(slug=..., progress_pct=..., progress=[...])`, `memory_store(...)`, etc.

### Medium risk → do it with detailed record
Execute the action. Then record every detail in the action log (Step 7).

**Multi-project actions → dispatch PM agents:**
When the top candidate involves a specific project (CI fix, PR merge, bug triage), dispatch a PM agent instead of acting directly. This keeps Jarvis at the strategic level.

```python
# Read the PM prompt template and fill per-project variables
# Launch as background agent with full authority
Agent(
    description=f"{project_name} PM",
    subagent_type="coding",
    prompt=filled_pm_prompt,  # from config/pm-prompt.md with {{variables}} filled
    run_in_background=True
)
```

PM agents save structured reports to `pm_report_{project}` in memory. After PM completes, read the report and include findings in Step 7 action log.

**When to use PM dispatch vs direct action:**
- Single quick action (merge PR, close issue, update label) → direct
- Project-scoped work (triage, implement, review multiple issues) → PM dispatch
- Cross-project coordination → Jarvis directly

### High risk → proposal only
```
memory_store(
  type="project",
  name="autonomous_proposal_<date>",
  project="jarvis",
  description="Autonomous loop proposal: <title>",
  content="## Proposal\n\n**What:** ...\n**Why:** ...\n**Risk:** High\n**Suggested action:** ...",
  tags=["autonomous", "proposal"]
)
```

---

## Step 7 — Record

Always save what happened:

```
memory_store(
  type="project",
  name="autonomous_action_log",
  project="jarvis",
  description="Last autonomous loop run",
  content="## Autonomous Loop — <date>\n\n**Action taken:** <description>\n**Risk level:** <low/medium/high>\n**Candidate score:** <N>\n**Goal alignment:** <which goal>\n**Result:** <what happened>\n**Next steps:** <if any>",
  tags=["autonomous", "loop", "log"]
)
```

Also update dedup marker:
```
memory_store(
  type="project",
  name="autonomous_loop_last_run",
  project="jarvis",
  description="Dedup marker for autonomous loop",
  content="<today's date YYYY-MM-DD> — <action summary or 'no action needed'>",
  tags=["autonomous", "dedup"]
)
```

---

## Output format

When run interactively (not as scheduled task):

```markdown
## Autonomous Loop — YYYY-MM-DD

### Context loaded
- Goals: N active (P0: <name>, ...)
- Risks: N alerts (N CRITICAL, N HIGH)
- Research: N unacted findings
- Brief: <summary>

### Candidates (N)
| # | Action | Score | Source |
|---|--------|-------|--------|
| 1 | <description> | <score> | risk-radar / goal / brief / research |
| 2 | ... | ... | ... |

### Selected action
**<description>** — risk: <low/med/high>, score: <N>
Goal: <aligned goal>

### Result
<what was done or proposed>
```

When run as scheduled task: save everything to memory, no interactive output.
