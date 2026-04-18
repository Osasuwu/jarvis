# Agent Sandbox Boundaries

Date: 2026-04-15
Scope: Rules for subagents (current /delegate + future Pillar 7 agents)

## Protected Files

These files must NEVER be modified by subagents. Changes require owner review in the main session.

| File | Why |
|------|-----|
| `.mcp.json` | MCP server config — affects all devices and projects |
| `config/SOUL.md` | Jarvis identity — changes alter all behavior |
| `CLAUDE.md` | Project instructions — affects all sessions |
| `mcp-memory/server.py` | Memory server — affects all projects |
| `.claude/settings.json` | Hooks and permissions — security boundary |
| `.gitleaks.toml` | Secret scanning config — disabling = security bypass |
| `.pre-commit-config.yaml` | Pre-commit hooks — disabling = security bypass |

Enforced via PreToolUse hook: `scripts/protected-files.py`

## Branch Rules

- Subagents work in feature branches (`feat/<N>-<slug>`), never commit directly to main
- One branch per issue — no multi-issue branches from agents
- Agent must push before reporting "done" — unpushed work is unverifiable

## Memory Rules

- Agents CAN: store project/decision memories, record outcomes
- Agents CANNOT: delete memories without owner confirmation (soft delete provides safety net)
- Secret scanner blocks credential values in memory_store

## Scope Rules

- Agent should only modify files relevant to its assigned issue
- If an agent needs to change a protected file, it must document the needed change in the PR description and leave it for the owner
- Cross-project changes (jarvis ↔ redrobot) require explicit mention in the issue

## Escalation

Agent must STOP and report (not attempt) when:
1. It needs to modify a protected file
2. It encounters a merge conflict it can't resolve
3. Tests fail and the fix requires architectural changes
4. The issue requirements are ambiguous and implementation could go multiple ways
5. The change would affect another project's behavior
