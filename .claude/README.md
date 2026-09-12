# `.claude/` — project-scoped Claude Code config for jarvis

**Core Jarvis machinery lives at user-level (`~/.claude/`).** It was moved
out of this directory in EPIC #335 (Pillar 7 Phase 0: Federation) so that
Claude Code has the same SOUL, core skills, hooks, and MCP servers
regardless of which project's CWD it's launched from.

Source of truth for user-level skills lives in
[`.claude-userlevel/skills/`](../.claude-userlevel/skills/) at the repo root.
The custom installer that used to mirror the rest of `.claude-userlevel/`
(`scripts/install/`, `install.ps1`/`install.sh`) was retired in #1800 —
Claude Code's own hooks, MCP registrations, and settings live at user level
directly now, not as a build artifact of a repo-side installer.

## What stays here

Only jarvis-project-specific Claude Code config:

- [`agents/`](agents/) — project-scoped subagent definitions
  (e.g. `coding.md`).
- [`hooks/`](hooks/) — project-local hook scripts (`secret-scanner.py`,
  `protected-files.py`, `device-info.py`).
- `settings.json` — wires three `PreToolUse` matchers: `secret-scanner.py`
  on file writes (`Edit|Write|NotebookEdit`), on `Bash`, and on a ten-tool
  `mcp__github__` write matcher; `protected-files.py` on file writes.

Everything else (the core skills, plus SOUL.md and `.mcp.json`) was removed
in M5 (#340). They're still available in every session, just from
`~/.claude/` now.

## Where to look next

- **Editing a core skill** → `.claude-userlevel/skills/<name>/SKILL.md`.
- **Editing SOUL** → [`config/SOUL.md`](../config/SOUL.md) is the canonical
  location.
- **Protected-file rules** →
  [`docs/security/agent-boundaries.md`](../docs/security/agent-boundaries.md).
