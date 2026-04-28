# Agent Sandbox Boundaries

Date: 2026-04-15 (revised 2026-04-23 for Federation & Delegation Phase 0 — #341; revised 2026-04-26 for principal-aware permissions — #426; isatty fallback removed in #429)
Scope: Permission rules for **all principals** running Claude — interactive owner, autonomous loop, /delegate subagent, and the future dispatcher.

## Principal model (#426, #429)

Permissions depend on **who is running Claude**. Four principals — detection lives in [`scripts/principal.py`](../../scripts/principal.py):

| Principal | Signal | Trust |
|---|---|---|
| `live` | Default when no `JARVIS_PRINCIPAL` and no headless env | Highest — owner watches, can correct in seconds |
| `autonomous` | `JARVIS_PRINCIPAL=autonomous` (set by scheduler/cron launchers) **or** `CLAUDE_CODE_NON_INTERACTIVE`/`CLAUDE_CODE_HEADLESS` | Low — corrections take hours |
| `subagent` | `JARVIS_PRINCIPAL=subagent` (auto-injection in /delegate is future work) | Medium — isolated worktree, parent reviews diff |
| `supervised` | `JARVIS_PRINCIPAL=supervised` (future dispatcher launcher will set this) | Delegated — permissions ⊆ supervisor's grant |

Detection chain (#429):
1. Explicit env `JARVIS_PRINCIPAL` — primary
2. Claude Code headless env vars → `autonomous`
3. Default → `live`

**Contract for autonomous entry points**: launchers that run Claude headless (scheduler, future dispatcher, any cron/task wrapper) MUST set `JARVIS_PRINCIPAL` explicitly. The scheduler does this via NSSM `AppEnvironmentExtra=JARVIS_PRINCIPAL=autonomous` ([`scripts/install/install-scheduler-service.ps1`](../../scripts/install/install-scheduler-service.ps1)).

The earlier "default-safe to autonomous" design (#426) was reverted in #429 because hook subprocesses always have piped stdin, so an `isatty()` fallback would mis-classify every interactive session as autonomous. Today's autonomous launchers explicitly set the env; future ones must do the same.

### Permission matrix (action × principal)

Action tier model is shared with `agents/safety.py` (T0 = AUTO, T1 = OWNER_QUEUE, T2 = BLOCKED).

| Action ↓ × Principal → | **live** | **autonomous** | **subagent** | **supervised** |
|---|---|---|---|---|
| **T0** narrow GitHub labels (`priority:*`, `area:*`, `needs-*`, `status:ready`); status updates; memory_store with `tag=auto-generated`; comment own PR; close issue with evidence; open jarvis tracking issue | ✅ act | ✅ act | ✅ act | ✅ act |
| **T1** code edit own repo; open PR; merge LOW-risk own PR per skill policy; `/implement` work; workflow files; drive-by fixes | ✅ act | ⚠️ enqueue `task_queue` *(future, lands with dispatcher)* | ✅ in worktree, no merge | ✅ within dispatcher grant *(future)* |
| **T2-canonical** repo-side sources of truth — see "Repo-level" table below | ⚠️ harness asks (hook exits 0) | ❌ block | ❌ block, escalate to `/implement` | ❌ block |
| **T2-mirror** `~/.claude/*` files installed by `install.ps1` — see "User-level" table below | ❌ block (use installer) | ❌ block | ❌ block | ❌ block |
| **T2-secret** `.env*` values; force push to main/master; impersonation; outbound to other humans (PR comments to others, Telegram, email) | ❌ always block | ❌ block | ❌ block | ❌ block |

Currently enforced in code: only **T2** rows, via [`scripts/protected-files.py`](../../scripts/protected-files.py). T1 routing (autonomous-enqueue, supervised-grant) lands when the dispatcher ships; until then T1 work is owner-driven through `/implement` and `/delegate`.

## Protected Files

These files must NEVER be modified by subagents. Changes require owner review in the main session. This table is the **single source of truth** — skills reference it rather than redefining their own lists.

### Repo-level (jarvis working copy)

| File | Why |
|------|-----|
| `.mcp.json` | MCP server config — affects all devices and projects |
| `config/SOUL.md` | Jarvis identity — changes alter all behavior |
| `CLAUDE.md` | Project instructions — affects all sessions |
| `mcp-memory/server.py` | Memory server entry — affects all projects |
| `mcp-memory/client.py` | Supabase client + audit log — split out by #360 |
| `mcp-memory/embeddings.py` | Voyage AI embedding pipeline — split out by #360 |
| `mcp-memory/tools_schema.py` | MCP tool schemas — schema drift breaks redrobot consumers |
| `mcp-memory/classifier.py` | Phase 2b write-side classifier — affects all writes |
| `mcp-memory/episode_extractor.py` | Episode → memory extractor — affects ingest |
| `mcp-memory/handlers/*.py` | Memory tool handlers (#360 split) — same blast radius as server.py |
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

Enforced via PreToolUse hook: `scripts/protected-files.py` (covers both surfaces; user-level paths anchored to `Path.home() / ".claude"` or `$JARVIS_CLAUDE_HOME` override). The hook is principal-aware (#426): `live` principal can edit canonical sources directly (the harness asks for one-off approval), but mirror files always block — the canonical source + installer flow is the only sanctioned path to update them.

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
