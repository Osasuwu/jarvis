# CLAUDE.md

## What this project is

**Jarvis** — universal personal AI agent. See `docs/PROJECT_PLAN.md` for full scope.

Architecture: Claude Code native (skills, hooks, MCP, subagents) + Supabase memory layer + SOUL.md identity. Telegram via Channels, scheduling via /loop — no custom Python services.

## Memory — USE IT

This project has an **MCP Memory Server** (`memory` in .mcp.json) connected to Supabase.

### At session start
Call `memory_recall` with relevant keywords to load context. At minimum:
- `memory_recall(project="jarvis")` — project-specific context
- `memory_recall(type="user")` — who the owner is, preferences
- `memory_recall(type="feedback")` — behavioral rules from past sessions

### During work
When decisions are made, preferences expressed, or architecture discussed:
- `memory_store(...)` — save it immediately, don't wait until end of session
- If a memory exists, `memory_store` upserts (updates by name+project)

### Memory types
- `user` — owner profile, preferences, working style (project=null for cross-project)
- `project` — project-specific context, state, decisions
- `decision` — specific architectural/design decisions with rationale
- `feedback` — how to behave, what to do/avoid (from owner corrections)
- `reference` — pointers to external resources, docs, URLs

### Why this matters
The owner works from 3 devices across multiple projects. Local ~/.claude/ memory doesn't sync. This MCP server is the ONLY persistent memory that works everywhere. **If you don't use it, the next session starts from scratch and repeats past mistakes.**

## How you MUST behave

### Be proactive
Before building anything, check: does it align with `docs/PROJECT_PLAN.md`? Can Claude Code do it natively? Is this the highest priority? **Say so before executing** if something is wrong.

### Push back
Owner explicitly wants honest criticism. Challenge bad ideas. Don't build prompt wrappers when Claude Code skills suffice. Say "this is wrong because..." — owner prefers honesty.

### Save decisions
After conversations with decisions: `memory_store(...)`. The #1 frustration is context loss between sessions.

### Check native capabilities
Before writing Python: can Claude Code skills, MCP servers, hooks, or subagents handle this? The only justified Python is `mcp-memory/server.py`. Everything else (Telegram → Channels, scheduling → /loop, background tasks → Desktop agents) is handled natively.

### Data-first skills
Don't pay LLM tokens to run shell commands. Fetch data in Python, send only data to cheap LLM for analysis.

## Development process

- One issue per PR. PR body includes `Closes #NNN`.
- Branches from `main`. Check GitHub Copilot auto-review before merging.
- See `.github/copilot-instructions.md` for detailed rules.

## Key files

| What | Where |
|------|-------|
| Project plan | `docs/PROJECT_PLAN.md` |
| Jarvis personality | `config/SOUL.md` |
| MCP config | `.mcp.json` |
| Memory server | `mcp-memory/server.py` |
| Process rules | `.github/copilot-instructions.md` |
