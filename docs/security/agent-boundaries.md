# Agent Sandbox Boundaries

Date: 2026-04-15 (revised 2026-04-23 for Pillar 7 Phase 0 federation — #341)
Scope: Rules for subagents (current /delegate + future Pillar 7 agents)

## Protected Files

These files must NEVER be modified by subagents. Changes require owner review in the main session. This table is the **single source of truth** — skills reference it rather than redefining their own lists.

### Repo-level (jarvis working copy)

| File | Why |
|------|-----|
| `.mcp.json` | MCP server config — affects all devices and projects |
| `config/SOUL.md` | Jarvis identity — changes alter all behavior |
| `CLAUDE.md` | Project instructions — affects all sessions |
| `mcp-memory/server.py` | Memory server — affects all projects |
| `.claude/settings.json` | Hooks and permissions — security boundary |
| `.gitleaks.toml` | Secret scanning config — disabling = security bypass |
| `.pre-commit-config.yaml` | Pre-commit hooks — disabling = security bypass |

### User-level (installed under `~/.claude/` by `scripts/install/installer.py`)

Editing these changes behaviour for **every Claude Code session on the device**, across all projects — strictly broader blast radius than the repo-level copies.

| File | Why |
|------|-----|
| `~/.claude/settings.json` | User-level hooks — run in every session on this device |
| `~/.claude/SOUL.md` | User-level identity — loaded by SessionStart hook before project CLAUDE.md |
| `~/.claude/.mcp.json` | User-level MCP config — mounts servers for every project |
| `~/.claude/skills/*/SKILL.md` | User-level skill definitions — available in every project |

The source of truth for these files lives in the jarvis repo (`config/SOUL.md`, `.claude-userlevel/settings.json`, `.claude-userlevel/.mcp.json`, `.claude-userlevel/skills/*/SKILL.md`). The installer copies or templates them into `~/.claude/`. Direct edits to `~/.claude/` drift from source and are lost on the next `install.ps1 --apply`.

Enforced via PreToolUse hook: `scripts/protected-files.py` (covers both surfaces; user-level paths anchored to `Path.home() / ".claude"` or `$JARVIS_CLAUDE_HOME` override).

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
