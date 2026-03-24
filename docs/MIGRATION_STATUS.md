# Migration Status

Status date: 2026-03-24

## M1: Architecture Migration — COMPLETE

- [x] Runtime scaffold in `src/` with CLI entrypoint
- [x] Command routing for `/triage`, `/weekly-report`, `/issue-health`, `/research`
- [x] Environment and model configuration loader
- [x] `.mcp.json` bootstrap for GitHub + filesystem MCP servers
- [x] Telegram polling handler with end-to-end message flow
- [x] Native Claude Agent SDK integration (replaced CLI subprocess bridge)
- [ ] Scheduled runs (Task Scheduler or GitHub Actions trigger)

## M2: Core Features — IN PROGRESS

### Done
- [x] Native SDK executor (`query()` instead of `subprocess.run`)
- [x] Real token counting (SDK provides actual usage, no more `len(text)//4` heuristic)
- [x] Per-query budget limit (`max_budget_usd` on every SDK call)
- [x] Daily budget tracking and enforcement (blocks execution when limit reached)
- [x] Skill prompt optimization (15KB → 5.6KB, -63% token overhead)
- [x] Research skill implementation with web search + confidence scoring
- [x] Agent tool permissions (`allowed_tools` per agent type)

- [x] Delegation pipeline (Jarvis → coding agent → PR)

### Pending
- [ ] Port PM skills to Agent SDK subagents (currently work via prompt+query, not dedicated subagents)
- [ ] Scheduled execution (cron for daily triage, weekly reports)
- [ ] Self-check skill

## Architecture

### Standard commands (PM, research, chat)
```
User Input (CLI/Telegram)
    ↓
dispatcher.py → build prompt from SKILL.md
    ↓
registry.py → select AgentSpec (model, tools, budget)
    ↓
executor.py → claude_agent_sdk.query(prompt, options)
    ↓
costs.py → record real tokens + USD from SDK
    ↓
Response → user
```

### Delegation pipeline (/delegate)
```
/delegate #42
    ↓
delegate.py → fetch issue from GitHub (gh CLI)
    ↓
Jarvis brain (Sonnet, API) → decompose into coding prompt
    ↓
git checkout -b feature/42-title
    ↓
CodingAgent (Claude Code CLI, Pro subscription) → implement changes
    ↓
git commit + push → gh pr create
    ↓
PR URL → user
```

### Cost model
- **Jarvis brain** (Haiku/Sonnet via API): cents per query for analysis/routing
- **Coding agent** (Claude Code CLI via Pro subscription): included in $20/month
- **Architecture principle**: cheap coordinator + specialized workers

### Budget Safety Layers
1. **Per-query**: SDK `max_budget_usd` hard limit (default $0.30)
2. **Per-agent**: Each AgentSpec defines max budget (PM=$0.10, Research=$0.50, Delegate=$0.20)
3. **Per-day**: `JARVIS_MAX_BUDGET_PER_DAY` check before execution (default $2.00)
4. **Real tracking**: SDK provides actual token counts, no estimation
5. **Coding agent**: Uses Pro subscription (free), not API
