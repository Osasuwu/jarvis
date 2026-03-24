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

### Pending
- [ ] Port PM skills to Agent SDK subagents (currently work via prompt+query, not dedicated subagents)
- [ ] Scheduled execution (cron for daily triage, weekly reports)
- [ ] Delegation pipeline (Jarvis → coding agent → PR)
- [ ] Self-check skill

## Architecture

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

### Budget Safety Layers
1. **Per-query**: SDK `max_budget_usd` hard limit (default $0.30)
2. **Per-agent**: Each AgentSpec defines max budget (PM=$0.10, Research=$0.50, Chat=$0.05)
3. **Per-day**: `JARVIS_MAX_BUDGET_PER_DAY` check before execution (default $2.00)
4. **Real tracking**: SDK provides actual token counts, no estimation
