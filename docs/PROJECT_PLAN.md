# Jarvis Project Plan

Version: 6.0
Date: 2026-03-31

## Purpose

Reference document. When it's unclear what to build next or whether something belongs in Jarvis — answer is here.

---

## Vision

Jarvis is a **thin, permanent layer on top of Claude Code** that provides:

1. **Identity** — consistent personality across all sessions (`config/SOUL.md`)
2. **Cross-device memory** — context that survives sessions and syncs across all machines (Supabase MCP)
3. **Custom extensions** — skills and MCP servers tailored to the owner's workflow

Everything else is handled by Anthropic's native stack. Jarvis only adds what Claude Code genuinely can't do.

---

## Workspace architecture

| Workspace | Purpose |
|-----------|---------|
| `~/GitHub/` | Primary orchestrator — all sessions start here. Houses shared skills and commands. |
| `personal-AI-agent/` | Identity (`SOUL.md`), memory server (`mcp-memory/`), project docs |
| `redrobot/`, etc. | Project-specific work — opened directly in VS Code when working on that project |

Skills created in `personal-AI-agent/.claude/skills/` are auto-synced to `~/GitHub/.claude/skills/` via post-commit hook.

---

## What Claude Code handles natively (don't rebuild)

| Need | Native solution |
|------|----------------|
| Scheduling / cron | `/loop` + Desktop scheduled tasks |
| Background agents | Claude Code Desktop background agents |
| Delegation (issue → PR) | Subagents with model routing |
| Mobile access | Dispatch (Claude mobile → Desktop) |
| Messaging interfaces | Claude Code Channels |

---

## What Jarvis adds on top

| Gap | Solution |
|-----|----------|
| Cross-device memory | `mcp-memory/server.py` → Supabase |
| Identity continuity | `config/SOUL.md` loaded at every session start |
| Workflow automation | `.claude/skills/` — task-specific skills |
| External integrations | MCP servers (where skills aren't enough) |

---

## Extension principles

**Skills** (`.claude/skills/`) — for workflow automation: anything that involves reading context, making decisions, calling tools, producing output. Claude invokes these automatically or on request.

**MCP servers** — for persistent services, external data sources, or capabilities that need to run outside Claude's context. Use when a skill would require repeated identical tool calls.

**Rule: native first.** Before adding anything:
1. Can Claude Code do this natively? (hooks, /loop, subagents, Desktop agents)
2. Can an existing MCP server handle it?
3. Skill or new MCP server?
4. Only as last resort: new Python in `mcp-memory/`-style

---

## Permanently out of scope

- Custom messaging relay (Channels handles it)
- Custom scheduler (/ loop handles it)
- Budget tracking (Anthropic dashboard)
- Multi-user features (Jarvis serves one person)
- Duplicate abstractions around what Claude Code already does

---

## Why not custom Python services

Jarvis went through three rewrites before reaching this architecture:

1. **Custom Python MVP** — validated ideas, too much infrastructure to maintain alone
2. **OpenClaw** — abandoned (512 security vulnerabilities, malicious skills)
3. **Claude Agent SDK wrappers** — 6 of 8 skills were unnecessary wrapping of native Claude Code capabilities

Lesson: self-hosting costs more time than it saves. Anthropic ships fast — building duplicates means maintaining things that get obsoleted in weeks.

The only justified Python: `mcp-memory/server.py` (cross-device Supabase sync — genuinely not possible natively).

---

## Decision rule

When unsure whether to build something: **would this still be needed if Anthropic shipped this natively next month?** If no — don't build it.
