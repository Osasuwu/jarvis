# Jarvis Project Plan

Version: 5.0
Date: 2026-03-28
Status: Active

## 1. Purpose

Strategic plan for Jarvis — a personal AI agent built on top of Claude Code (Anthropic).

This document answers:
- what Jarvis is and what it adds on top of Claude Code,
- what to build next and what to skip,
- architectural decisions and why they were made.

## 2. Vision

Jarvis is a **thin, permanent layer on top of Claude Code** that provides:
1. **Identity** — consistent personality and behavior across all sessions (SOUL.md)
2. **Cross-device memory** — context that survives sessions and syncs across machines (Supabase MCP)
3. **Custom skills** — task-specific automation tailored to the owner's workflow

Everything else — mobile access, scheduling, background tasks, Telegram — is handled by Anthropic's native stack (Pro subscription).

### Platform History

1. **Custom Python MVP** (archived) — validated core ideas, too much infrastructure for one person.
2. **OpenClaw** (abandoned 2026-03-23) — 512 security vulnerabilities, malicious skills, creator leaving.
3. **Claude Agent SDK wrappers** (abandoned 2026-03-28) — 6 of 8 skills were unnecessary Python around what Claude Code does natively.
4. **Claude Code native + Supabase memory** (current, final) — Claude Code handles orchestration, delegation, agents, scheduling, Telegram. Jarvis adds only what Claude Code genuinely can't do.

## 3. Architecture

### What Claude Code handles natively (don't rebuild)

| Need | Native solution |
|------|----------------|
| Mobile access (phone) | Dispatch (Claude mobile → Desktop, QR pairing) |
| Telegram interface | Claude Code Channels (`--channels` flag, official plugin) |
| Scheduling / cron | `/loop` + Desktop scheduled tasks (up to 50 concurrent) |
| Background agents | Claude Code Desktop background agents |
| Delegation (issue → PR) | Claude Code subagents with model routing |
| GitHub/Slack connectors | Cowork connectors |

### What Jarvis adds on top

| Gap | Solution |
|-----|----------|
| Cross-device memory | `mcp-memory/server.py` → Supabase (syncs all devices/projects) |
| Identity continuity | `config/SOUL.md` loaded at session start via `CLAUDE.md` |
| Custom workflow skills | `.claude/skills/` (triage, risk-radar, intel, delegate, etc.) |

### Memory architecture

Single source of truth: **Supabase** via MCP.

- `memory_recall` at session start → loads project context, owner preferences, past decisions
- `memory_store` during work → saves decisions, findings, architectural notes
- Cross-device: same Supabase URL on all machines, same memory everywhere
- Cross-project: `project=null` for global memories, `project="jarvis"` for project-specific

`~/.claude/` local files are supplementary only — not relied upon for persistence.

## 4. Scope

### In scope

**M3: Intelligence Layer** (current milestone):
- Identity: SOUL.md loaded every session *(PR #88)*
- Telegram: Claude Code Channels setup *(PR #89)*
- Custom skills: triage, issue-health, risk-radar, research, delegate, self-review, self-improve, intel
- Memory: cross-device Supabase MCP *(done)*
- Self-improvement loop: self-review → intel → self-improve cycle

**M4: Depth** (next):
- Memory upgrade: vector/semantic search (Hindsight migration from ILIKE)
- Skills refinement based on real usage
- Intel digest: automated weekly scan for Claude/MCP updates

### Out of scope (permanently, handled natively)

- Custom Telegram relay (→ use Channels)
- Custom scheduler / cron service (→ use /loop)
- Custom background task runner (→ use Desktop agents)
- Budget tracking (→ Anthropic dashboard, Pro subscription)
- Multi-user features (Jarvis serves one person)
- Local LLM as primary (deferred; possible as MCP tool later)

## 5. Milestones

### M1: Architecture Migration ✅
Claude Agent SDK setup, Telegram bot, basic routing. *(Superseded by reboot)*

### M2: Core Features ✅
PM skills, research, delegation pipeline, cost control. *(Redefined: skills now in .claude/skills/)*

### M3: Intelligence Layer 🔧

Exit criteria:
- [ ] SOUL.md loaded every session (PR #88)
- [ ] Telegram via Channels working (PR #89, requires manual setup)
- [ ] Cross-device memory working on all owner's devices
- [ ] Self-improve cycle functional: `/self-review` → `/self-improve` → PR

### M4: Depth 📋

Exit criteria:
- [ ] Memory semantic search (Hindsight or pgvector migration)
- [ ] `/intel` producing useful weekly digests
- [ ] All skills validated with real usage data

## 6. Decision rules

**Default to native first.** Before writing any code:
1. Can Claude Code do this natively? (skills, hooks, /loop, subagents, Channels, Desktop)
2. Can an existing MCP server handle it?
3. Only if both answers are no: write Python, but only for `mcp-memory/`-type gaps.

**Build for real problems.** Only build features needed in the last week. Park ideas in GitHub Discussions.

**No duplicate abstractions.** Don't wrap what Claude Code already does. The 2x rebuild from Claude Agent SDK happened because of wrapping — don't repeat.

## 7. Technical setup

- **Subscription**: Anthropic Pro (covers Claude Code, Desktop, Channels, Dispatch)
- **Memory**: Supabase free tier (PostgreSQL, REST API)
- **Skills runtime**: Claude Code (Claude Code handles all skill execution)
- **Python**: only `mcp-memory/server.py` (MCP stdio server)
- **OS**: Windows 11, 3 devices
- **Hardware**: Intel i5 9400f / RTX 3050 6GB / 32GB RAM (home)

## 8. Success metrics

- Jarvis used daily for real work, not just testing
- Memory recall at session start requires zero re-explanation of context
- Skills work without debugging across all 3 devices
- `/intel` surfaces genuinely new information weekly
- Self-improve cycle produces usable PRs
