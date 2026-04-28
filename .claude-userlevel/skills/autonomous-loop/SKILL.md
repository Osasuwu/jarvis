---
name: autonomous-loop
description: "Autonomous orchestrator: perceive events, evaluate against goals, decide and act within safety bounds. Runs daily via scheduled task or manual invocation."
version: 1.2.0
---

# Autonomous Loop Orchestrator

Daily orchestrator that perceives events and perception outputs (goals, risks, research findings), evaluates them against active goals, decides actions within safety bounds, and executes them autonomously. Batches multiple Low-risk actions per run; limits Medium-risk to one.

Implements the perceive→evaluate→decide→act→record loop from the Autonomous Work Loop architecture.

## Usage

- `/autonomous-loop` — manual invocation (full run)
- Scheduled: daily 09:00 (after morning-brief)
- Part of: Jarvis Autonomous Work Loop pillar

## Architecture

```
Load Context → Build Candidates → Score → Select (batch Low, pick 1 Medium) → Risk-Gate → Execute → Record
```

## Step 1 — Load Context

In parallel, load:

- `goal_list(status="active")` — active goals for evaluation
- `memory_recall(query="morning brief")` — overnight activity + daily plan
- `memory_recall(query="risk radar")` — CI failures, security alerts, stale issues
- `memory_recall(query="research findings unacted")` — research outputs waiting for action
- `memory_recall(query="autonomous_loop_last_run")` — dedup check (don't run twice in same day)
- `memory_recall(query="outcome patterns feedback")` — past pattern detections to inform scoring
- Read `config/repos.conf` — target repos for perception + hygiene sweep

**Dedup rule:** If `autonomous_loop_last_run` exists and is today's date, skip gracefully (return "Already ran today").

## Step 2 — Build Action Candidates

From perception outputs, generate candidates:

- **Risks** with severity HIGH+ → mitigation action
- **Goal deadline** < 3 days → escalation action (prioritize, nudge timeline)
- **Goal progress** stale > 7 days → review action (check status, unblock)
- **Actionable research** (marked in memory) → execute finding
- **Events** from event queue (HIGH+ severity) → handle event
- **Morning-brief** items marked "needs action" → act on them
- **Memory clusters** from `find_consolidation_clusters()` → consolidation action (Low-risk)
- **Workflow hygiene sweep** (per repo in `config/repos.conf`) — see Step 2a.

### Step 2a — Workflow hygiene sweep

For each repo `R` in `config/repos.conf`, query in parallel:

```bash
# Milestones
gh api "repos/<R>/milestones?state=open&per_page=50" --jq '.[] | {number,title,state,open_issues,closed_issues,due_on}'
# Epics without milestone
gh issue list --repo <R> --label epic --state open --json number,title,milestone,labels --limit 30
# CI runs for failure rate
gh run list --repo <R> --json conclusion,name,createdAt --limit 20
```

Generate candidates:

| Signal | Detection | Risk | Action |
|--------|-----------|------|--------|
| **Orphan milestone** | `state==open && open_issues==0` | Low | `gh api repos/<R>/milestones/<N> -X PATCH -F state=closed` |
| **Orphan sprint** | `label==epic && /Sprint/i.test(title) && milestone==null` | Medium | Create milestone from epic title + attach epic + merged-PRs that reference it |
| **CI workflow broken** | Same-name workflow ≥50% fail rate in last 10 runs AND ≥24h old | Medium | Spawn debug task via `/delegate` pointing at the workflow file |
| **Milestone deadline risk** | `due_on within 3 days && open_issues > 0` | — (flag only) | Add to `## Alerts` in output; don't auto-act |
| **Epic missing Children heading** | body fails `/##+\s*Children/i` regex | Low | Flag + record proposal (don't auto-rewrite body — content judgment) |

**Write-action permissions (enforced here):**
- Repos under `Osasuwu/*` → all Low/Medium actions execute normally.
- Repos under any other owner (e.g. `SergazyNarynov/redrobot`) → **flag-only**: record the finding in memory (`type=project, name=hygiene_sweep_proposals_<repo>_<date>, source_provenance="skill:autonomous-loop"`) and surface it in the output, but never execute the action. Owner acts manually or flips the repo to an owned org.

**Dedup per-finding:** before closing a milestone / creating a retroactive one, check `outcome_list(task_type='autonomous', pattern_tags=['hygiene'])` for matching description from last 3 days. Skip if same finding already actioned.

### Step 2b — Escalate stale flag-only findings (#327)

After writing (or skipping, per dedup) today's `hygiene_sweep_proposals_<repo>_<date>` memory, count consecutive prior flags for the same repo to detect ignored findings. This closes the loop for foreign-owner repos where Jarvis can't take the action itself.

**Count** — via `execute_sql`:

```sql
SELECT name, created_at
FROM memories
WHERE name LIKE 'hygiene_sweep_proposals_<repo>_%'
  AND archived = false
  AND created_at >= now() - interval '10 days'
ORDER BY created_at ASC;
```

`N = row count`, `first_flagged_at = min(created_at)`, `days_unaddressed = date(today) - date(first_flagged_at)`.

**Branch by repo ownership** (#433): own-repo findings (`Osasuwu/*`) are auto-actionable in Step 2a, so paper-tracking them as a separate issue is redundant. Foreign-owner repos keep the full ladder because Jarvis can't action them directly.

Detect via `gh repo view <R> --json owner --jq .owner.login`:
- `Osasuwu` → **own-repo path** (rungs 1-3 + critical-event escalation at rung 4)
- anything else → **foreign-repo path** (existing ladder, tracking issue at rung 4)

**Escalation rungs:**

| Rung | Threshold | Foreign-owner repo | Own repo (Osasuwu/*) |
|----|----|----|----|
| 1 | N ≥ 1 | Memory exists | Memory exists |
| 2 | N ≥ 2 or days_unaddressed ≥ 1 | `/status` surfaces `STALE FLAG` badge | Same |
| 3 | N ≥ 3 | Emit `events` row, `severity=high`, `event_type=hygiene_stale` | Same |
| 4 | N ≥ 5 | Create jarvis-side tracking issue (visibility on GitHub) | Emit `events` row, `severity=critical`, `event_type=hygiene_unaddressed_critical` — owner-facing nudge that auto-actionable findings are still untouched after 5 days; **no tracking issue** (would be paperwork) |

The own-repo critical-event payload should include `memory_names`, `detail`, and a one-line "next action" suggestion (e.g. "delegate to subagent" / "promote to next /implement cycle").

**Dedup before emitting (rung 3):** skip if an unprocessed `events` row with `event_type='hygiene_stale'` and `repo=<R>` already exists.

```sql
SELECT id FROM events
WHERE event_type = 'hygiene_stale'
  AND repo = '<R>'
  AND processed = false
ORDER BY created_at DESC LIMIT 1;
```

If none, insert:

```sql
INSERT INTO events (event_type, severity, repo, source, title, payload)
VALUES (
  'hygiene_stale',
  'high',
  '<R>',
  'skill:autonomous-loop',
  'Flag ignored <N>d: <repo> hygiene findings unaddressed',
  jsonb_build_object(
    'days_flagged', <N>,
    'first_flagged_at', '<first_flagged_at ISO>',
    'memory_names', <array of hygiene_sweep_proposals_* names>,
    'detail', '<brief: top finding from latest memory>',
    'url', 'https://github.com/<R>'
  )
);
```

**Rung 4 — foreign-owner repo (tracking issue):**

Dedup first:

```bash
gh issue list --repo Osasuwu/jarvis --state open --search "in:title stale flag <repo>" --json number --limit 1
```

If empty → create:

```bash
gh issue create --repo Osasuwu/jarvis \
  --title "Stale flag: <repo> findings unaddressed <N>d" \
  --label "process,autonomous-loop" \
  --body "Autonomous-loop has flagged findings for \`<R>\` on <N> consecutive days without owner action. Memories: <list>. First flagged: <date>. Jarvis cannot open issues in \`<R>\` (flag-only repo), so tracking here for visibility. Close this when the upstream finding is resolved."
```

Record the issue URL in the event payload (`payload.jarvis_tracking_issue = <url>`) via an update to the event row.

**Rung 4 — own repo (critical-event escalation, no tracking issue):**

Dedup first:

```sql
SELECT id FROM events
WHERE event_type = 'hygiene_unaddressed_critical'
  AND repo = '<R>'
  AND processed = false
ORDER BY created_at DESC LIMIT 1;
```

If none, insert:

```sql
INSERT INTO events (event_type, severity, repo, source, title, payload)
VALUES (
  'hygiene_unaddressed_critical',
  'critical',
  '<R>',
  'skill:autonomous-loop',
  'Auto-actionable findings unaddressed <N>d: <repo>',
  jsonb_build_object(
    'days_flagged', <N>,
    'first_flagged_at', '<first_flagged_at ISO>',
    'memory_names', <array of hygiene_sweep_proposals_* names>,
    'detail', '<brief: top finding from latest memory>',
    'next_action_hint', 'delegate via /delegate, or promote to /implement cycle',
    'url', 'https://github.com/<R>'
  )
);
```

Telegram-notify-hook.py picks this up at `severity=critical` and pings owner. Owner decides: action inline, /delegate, or mark the finding obsolete (which clears it from the next sweep).

**Ordering:** run Step 2b for every repo in `config/repos.conf` after Step 2a. Emitting an event here creates work the Low-risk batch will count (counts toward the 5-max limit).

## Step 3 — Score Each Candidate

```
score = goal_alignment(0-3) × urgency(1-3) + severity_bonus + outcome_adjustment
```

- **goal_alignment**: 3 = directly serves P0 | 2 = serves P1 | 1 = serves P2 | 0 = unaligned
- **urgency**: 3 = blocking/deadline | 2 = should be soon | 1 = can wait
- **severity_bonus**: +3 for CRITICAL risk | +2 for HIGH | +1 for MEDIUM
- **outcome_adjustment**: check outcome history for the candidate's area (pattern_tags overlap):
  - Area has 3+ recent failures → -2 (deprioritize, needs investigation first)
  - Area has high success rate (>80%) → +1 (proven approach)
  - No outcome data → 0 (neutral)

**Disqualify:** unaligned (goal_alignment=0) or uncertain candidates.

## Step 4 — Select Actions

Classify each candidate by risk (see Step 5), then select:

1. **All Low-risk** candidates with score ≥ 3 (up to 5 max)
2. **Top-1 Medium-risk** candidate (only if score ≥ 5 and no High-risk in the batch)
3. **High-risk** candidates → save as proposals only, never batch

Selection filters (apply to all):
- Not a protected file — see [`docs/security/agent-boundaries.md`](../../../docs/security/agent-boundaries.md) (covers repo-level + user-level `~/.claude/*`)
- Not already actioned (check memory)

**No candidates pass?** Skip gracefully — don't invent work.

**Ordering:** Execute Low-risk batch first, then the Medium-risk action (if any). This ensures quick wins land even if the Medium action fails.

## Step 5 — Risk Classification

| Risk | Examples | Autonomy |
|------|----------|----------|
| **Low** | Create issue, fix label, memory cleanup, triage | Auto-execute |
| **Medium** | Run self-improve, create PR, update goal, tag memory | Auto-execute + record |
| **High** | Architecture change, SOUL.md, memory schema, protected files | Save proposal only |

## Step 6 — Execute Actions

Process the selected actions in order. Track results as `{action, status, detail}`.

**Partial failure rule:** if one action fails, log it and continue with the rest. Don't abort the batch.

### Low-risk batch (up to 5)
Execute each independently:
- Create GitHub issue: `gh issue create --repo <R> --title "..." --body "..."`
  - **Epics** (`--label epic`) MUST use the `.github/ISSUE_TEMPLATE/epic.yml` structure: body requires `### Children` heading with `- [ ]` checkbox items, else `Issue Checks` CI fails. No `Parent: #NNN` — epics use milestones, not parent links.
  - **Tasks/bugs**: link parent via GitHub sub-issue relationship or `Parent: #NNN` at top of body.
- Memory operations: `memory_store(..., source_provenance="skill:autonomous-loop")`, `goal_update(...)`
- Tag or label work: `gh issue edit`, `gh pr edit`
- Triage events: `events_mark_processed(...)`
- Memory consolidation: run `find_consolidation_clusters()` via `execute_sql`, for each cluster: read all memories, merge content into one authoritative memory via `memory_store(..., source_provenance="skill:autonomous-loop")`, archive originals via `archive_memories(ids)`
- **Hygiene: close orphan milestone** (only on `Osasuwu/*` repos): `gh api repos/<R>/milestones/<N> -X PATCH -F state=closed` — for each milestone with `state=open && open_issues==0`.
- **Hygiene: flag epic missing Children heading**: record proposal via `memory_store(type="project", name="hygiene_epic_<N>_needs_children", ..., source_provenance="skill:autonomous-loop")`. Don't auto-rewrite bodies.

### Medium-risk (at most 1)
Execute after Low-risk batch completes:
- Invoke skill: `/self-improve`, `/research`, `/verify`
- Create PR: delegate via `/delegate` or `gh pr create`
- Update goal: `goal_update(slug=..., progress=...)`
- **Hygiene: retroactive milestone** for orphan sprint — `gh api repos/<R>/milestones -X POST` with title from epic, attach epic + linked merged PRs, close milestone. Only on `Osasuwu/*`.
- **Hygiene: broken CI debug** — `/delegate` a task to investigate the failing workflow, pointing at the specific workflow file and failure rate. Only on `Osasuwu/*`.

### High-risk (proposals only)
Never execute — save to memory:
- Record: `memory_store(type="project", name="autonomous_proposals", ..., source_provenance="skill:autonomous-loop")`
- Output proposal text to user

## Step 7 — Record Outcomes

**Each action** gets its own `outcome_record` (Outcome Tracking & Learning pillar):

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

After all actions complete, update dedup marker with batch summary:

```
memory_store(
  type="project",
  name="autonomous_loop_last_run",
  content="{\"date\": \"YYYY-MM-DD\", \"actions_count\": N, \"succeeded\": N, \"failed\": N, \"top_action\": \"...\"}",
  description="last orchestrator run",
  source_provenance="skill:autonomous-loop"
)
```

If any action advances a goal → `goal_update(slug=..., progress=[...])` — append `{item: "<5-word summary> (YYYY-MM-DD)", done: true}` to existing progress array.

## Step 7.5 — Drain high-severity events to Telegram (#327)

Any `severity=high` events emitted this run (including Step 2b escalations) need to reach the owner outside of `/status`. Run the notifier as the final durable side effect:

```bash
python scripts/telegram-notify-hook.py --min-severity high
```

- Reads unprocessed `events` at or above the threshold, sends one message each, marks them processed.
- Requires `TELEGRAM_BOT_TOKEN` and `TELEGRAM_ALLOW_USER_ID` in env. If either is missing, the script exits 1 — log the failure in the output but don't abort the run.
- The script is idempotent via `processed=true`, so running it multiple times in one day is safe (it drains only what's pending).

Skip silently if the script doesn't exist (older checkouts) — don't make this a hard blocker.

## Safety Rules

**Never:**
- Touch protected files — authoritative list in [`docs/security/agent-boundaries.md`](../../../docs/security/agent-boundaries.md) (both repo-level and user-level `~/.claude/*` are covered)
- Create more than 1 PR per run (even in a batch)
- Execute more than 5 Low-risk + 1 Medium-risk per run
- Execute High-risk actions without explicit proposal
- Execute write actions (close milestone, create milestone, delete branch, `gh issue/pr edit`) on repos outside `Osasuwu/*`. For other owners (e.g. `SergazyNarynov/redrobot`): flag-only — record the finding and surface in output, owner executes manually.

**Always:**
- Dedup: check `autonomous_loop_last_run` before acting
- Risk-gate: only auto-execute Low/Medium actions
- Record: every action gets its own `outcome_record`
- Partial failure: if one action fails, continue with the rest
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

## Selected (N actions)
| # | Action | Score | Risk | Status |
|---|--------|-------|------|--------|
| 1 | <action> | N | Low | success/failure |

## Execution
- [EXECUTED / PROPOSED]: <per-action summary>
- <links to created issues/PRs/memories>

## Status
- ✓ N/M actions succeeded
- ✓ Each action recorded via `outcome_record`
- ✓ `autonomous_loop_last_run` updated
```

If no candidates: "No high-priority actions found. System running normally."

## Implementation Notes

1. **Parallel loads:** Use `memory_recall` with `limit=1` for each query to get most recent memory
2. **Scoring:** Treat missing fields conservatively (e.g., missing urgency = 1)
3. **Events:** Read from `events_list()` if available; skip if unavailable
4. **Graceful degradation:** If any perception output fails, continue with what loaded successfully
5. **Timezone:** All date comparisons use local time
