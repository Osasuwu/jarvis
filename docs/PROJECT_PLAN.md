# Jarvis 2.0 — Project Plan

Version: 7.0
Date: 2026-04-13

## Purpose

Reference document. When it's unclear what to build next, whether something belongs in Jarvis, or how to approach implementation — answer is here.

---

## Vision

> **Jarvis — cognitive extension of a developer: sees the full picture, works while you sleep, argues when you're wrong, and gets more accurate every day.**

Not a tool, not an assistant — an extension of thinking capacity, memory, and executive function. See `docs/VISION.md` for the full vision document.

---

## Pillars

9 pillars organized in two layers. Core pillars are internal capabilities (how Jarvis thinks and works). Reach pillars are external capabilities (how Jarvis interacts with the world).

### Core

| # | Pillar | Status | What it is |
|---|--------|--------|------------|
| 1 | Goals & Strategic Context | Mature | Goal-aware decision making, push-back, priority tracking |
| 2 | Autonomous Work Loop | Mature | Event perception, judgment, continuous operation without owner |
| 3 | Outcome Tracking & Learning | Mature | Verify results, learn from patterns, improve over time |
| 4 | Memory 2.0 | Mature | Graph relations, temporal awareness, auto-hygiene |

### Reach

| # | Pillar | Status | What it is |
|---|--------|--------|------------|
| 5 | Integrations / Data Access | Early | Read access to all owner's accounts and services |
| 6 | Data Intelligence | Not started | Cross-platform search, content curation, pattern detection |
| 7 | Agent System | Early | Scalable multi-agent architecture (PM is one use case) |
| 8 | Identity & Interface | Early | TTS/STT, Telegram, professional mask for documents |
| 9 | Security & Digital Hygiene | Mature | Threat model, secret scanner hooks, credential registry, MCP audit |

Pillars are stable — they only grow, never change. Implementation within each pillar is flexible.

Status levels: **Not started** → **Early** (first steps) → **Active** (regular work) → **Mature** (core complete, incremental improvements). No percentages — they create false precision.

---

## Planning process

Hybrid goals + agile:

- **Goals** (Supabase) — strategic layer: vision, directions, priorities
- **Milestones** (GitHub) — major deliverables within each pillar
- **Issues** (GitHub) — decomposed tasks within milestones
- **Labels** — `needs-research` (topic not studied yet) and `decision-made` (decision documented in issue)

Decisions are documented in GitHub issues, not in Supabase memory. Memory is for cross-cutting context only.

---

## Access philosophy

Jarvis has **read access to all owner's data** across all accounts and services. Full context = better decisions.

- **Read**: default for everything — email, calendar, messengers, dev tools, hobbies
- **Write**: configured manually per integration, never assumed
- **People**: factual context (who is who, role) — OK. Managing relationships — no
- **Professional mask**: draft documents/emails in owner's style — OK. Personal communications — no

---

## Infrastructure principles

### Current runtime
Claude Code (Claude Max subscription) + Supabase (memory, events, goals) + GitHub (issues, PRs, Actions).

### Flexibility rules
- Pillars are permanent. Implementation is swappable
- Abstract provider-specific details — no lock-in to Claude, Supabase, or any vendor
- Keep data portable (Supabase can be self-hosted)
- Design for expansion — every module should accommodate future integrations
- Future possibilities: own Linux server, local models, different LLM providers

### Extension hierarchy
Before building anything:
1. Can Claude Code do this natively? (hooks, skills, subagents, scheduled tasks)
2. Can an existing MCP server handle it?
3. New skill or new MCP server?
4. Only as last resort: custom Python service

The only justified custom Python today: `mcp-memory/server.py` (cross-device Supabase sync).

### Decision rule
> Would this still be needed if Anthropic shipped it natively next month? If no — don't build it.

---

## Boundaries

### Out of scope
- Multi-user features (Jarvis serves one person)
- Duplicate abstractions around what Claude Code already does
- Managing other people's personal information
- Impersonating owner in personal communications

### Learned the hard way
Three rewrites before the current architecture:
1. Custom Python MVP — too much infrastructure for one person
2. OpenClaw — 512 vulnerabilities, malicious skills
3. Claude Agent SDK wrappers — 6 of 8 skills unnecessarily wrapped native features

Lesson: self-hosting costs more time than it saves. Anthropic ships fast.

---

## Key files

| What | Where |
|------|-------|
| Vision | `docs/VISION.md` |
| Jarvis personality | `config/SOUL.md` |
| Device config | `config/device.json` |
| MCP config | `.mcp.json` |
| Memory server | `mcp-memory/server.py` |
| Session context loader | `scripts/session-context.py` |
| Process rules | `.github/copilot-instructions.md` |
