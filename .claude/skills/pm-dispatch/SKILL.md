---
name: pm-dispatch
description: Dispatch Project Manager agents for one or more projects. 3-level architecture: Jarvis (orchestrator) → PM agents (per-project) → Coding agents (per-task). Use when owner says "запусти PM", "dispatch PMs", "поработай над проектами", or when autonomous-loop decides multiple projects need attention.
version: 1.0.0
---

# PM Dispatch Skill

Launch PM agents for tracked projects. Each PM runs as a separate agent with its own project-scoped context — Jarvis stays at the strategic level.

## Architecture

```
Jarvis (this session) — strategic, cross-project
  │
  ├── PM Agent (project A) — background, autonomous
  │     └── Coding Agent(s) — spawned by PM as needed
  │
  └── PM Agent (project B) — background, autonomous
        └── Coding Agent(s) — spawned by PM as needed
```

## Usage

- `/pm-dispatch` — dispatch PMs for ALL projects that need attention
- `/pm-dispatch redrobot` — dispatch PM for specific project
- `/pm-dispatch redrobot jarvis` — dispatch PMs for specific projects
- `/pm-dispatch redrobot "fix CI and merge pending PRs"` — with specific mission

## Pipeline

### 1. Load Strategic Context

```python
# Parallel — Jarvis-level context
goal_list(status="active")
memory_recall(query="morning_brief_latest", type="project", limit=1)
```

Read `config/repos.conf` for tracked repos.

### 2. Decide Which Projects Need PM Dispatch

If user specified projects → use those.
If user said "all" or no args → check each project:
- Has open PRs needing action? → needs PM
- Has goal with deadline < 7 days? → needs PM
- Has risk-radar findings? → needs PM
- Working state has unfinished work? → needs PM

Skip projects with no actionable work. Don't waste tokens.

### 3. Build PM Prompts

Read `config/pm-prompt.md` template. For each project, fill variables:

| Variable | Source |
|----------|--------|
| `{{project_name}}` | Repo name (e.g., "RedRobot") |
| `{{repo}}` | Full repo path (e.g., "SergazyNarynov/redrobot") |
| `{{local_path}}` | Local clone path from known convention |
| `{{project_key}}` | Memory project key (e.g., "redrobot") |
| `{{mission}}` | From user input, or auto-generated from context |

**Local paths** (known):
- `jarvis` → `C:/Users/petrk/GitHub/jarvis`
- `redrobot` → `C:/Users/petrk/GitHub/redrobot`
- `like_spotify_mobile_app` → `C:/Users/petrk/GitHub/like_spotify_mobile_app`

**Auto-generated missions** (when user doesn't specify):
- Check open PRs: review, merge if approved, fix if CI failing
- Triage new issues: label, prioritize, link to goals
- Continue unfinished work from working_state
- Address risk-radar findings

### 4. Dispatch PM Agents

Launch each PM as a **background agent**:

```python
Agent(
    description=f"{project_name} PM",
    subagent_type="coding",  # needs full tool access
    prompt=filled_pm_prompt,
    run_in_background=True
)
```

**Critical:** Use `subagent_type="coding"` — PMs need Bash, Edit, Read, Write, and all MCP tools including memory and GitHub.

### 5. Report Dispatch

Output to user:
```
Dispatched 2 PM agents:
- RedRobot PM: "fix CI and merge pending PRs" (background)
- Jarvis PM: "continue memory 2.0 testing" (background)

PMs will save results to memory. Check with:
  memory_recall(query="pm_report", type="project")
```

Then continue with Jarvis-level work or wait for notifications.

### 6. Collect Results (when PMs finish)

When background agents complete, read their reports:
```python
memory_recall(query="pm_report_redrobot", type="project", limit=1)
memory_recall(query="pm_report_jarvis", type="project", limit=1)
```

Summarize for the owner:
- What each PM accomplished
- What's blocked / needs owner attention
- Cross-project impacts (if any)

## Project Registry

| Key | Repo | Local Path | Notes |
|-----|------|-----------|-------|
| jarvis | Osasuwu/jarvis | ~/GitHub/jarvis | This project |
| redrobot | SergazyNarynov/redrobot | ~/GitHub/redrobot | Industrial robot control |
| like_spotify | Osasuwu/like_spotify_mobile_app | ~/GitHub/like_spotify_mobile_app | Inactive, low priority |

## Safety

- PMs can only act within their project scope
- PMs report cross-project impacts, don't act on them
- PMs follow the same risk classification as autonomous-loop:
  - LOW/MEDIUM → auto-execute
  - HIGH → proposal in report, don't implement
- Jarvis reviews PM reports before acting on cross-project items
- If a PM report conflicts with goals → Jarvis overrides
