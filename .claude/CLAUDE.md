# CLAUDE.md — Jarvis (personal-AI-agent)

## Session start

1. Read `config/SOUL.md` — you are Jarvis
2. Load memory in parallel:
   - `memory_recall(type="decision", project="jarvis", limit=5)` — jarvis decisions
   - `memory_recall(query="working_state_jarvis", type="project", limit=1)` — open checkpoint
3. Then respond. Global behavioral rules (autonomy, memory, senior mindset) are in `~/Github/CLAUDE.md` — don't duplicate here.

---

## What this project is

**Jarvis** — universal personal AI agent. See `docs/PROJECT_PLAN.md` for full scope.

Architecture: Claude Code native (skills, hooks, MCP, subagents) + Supabase memory layer + SOUL.md identity.

## Project-specific rules

### Only justified Python: `mcp-memory/server.py`
Everything else is Claude Code native. Before writing Python, check: skills, MCP servers, hooks, subagents.

### Check native capabilities first
Telegram → Channels. Scheduling → /loop or scheduled tasks. Background work → Desktop agents. Don't reinvent.

### Cross-project impact
This project provides the memory server used by ALL projects. Changes to `mcp-memory/server.py`, `.mcp.json`, or Supabase schema affect redrobot too. Always check.

### MCP config portability
`.mcp.json` must work on all 3 devices. Never hardcode usernames, absolute paths with user-specific segments, or device-specific values. Use relative paths or environment variables.

## Development process

- Branches from `main`
- One issue per PR, body includes `Closes #NNN`
- Check GitHub Copilot auto-review before merging

## Key files

| What | Where |
|------|-------|
| Project plan | `docs/PROJECT_PLAN.md` |
| Jarvis personality | `config/SOUL.md` |
| MCP config | `.mcp.json` |
| Memory server | `mcp-memory/server.py` |
| Process rules | `.github/copilot-instructions.md` |
