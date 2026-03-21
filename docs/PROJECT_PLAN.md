# Jarvis Project Plan

Version: 2.0
Date: 2026-03-21
Status: Active

## 1. Purpose

Strategic plan for Jarvis — a universal personal AI agent built on the OpenClaw platform.

Use this document to:
- understand the full vision and current priorities,
- decide what to build next,
- keep scope focused on skills that deliver real value,
- track the migration from custom Python codebase to OpenClaw.

## 2. Problem and Vision

### Problem

One person managing multiple software projects and learning across many domains cannot do everything alone. Development coordination, research, and routine tasks consume time that should go to creative and strategic work.

### Vision

Jarvis is a universal personal AI agent that:
- manages development workflows across multiple GitHub projects,
- helps research and learn new topics,
- adapts to whatever the owner is working on right now,
- communicates via Telegram (mobile) and direct UI (workstation),
- runs locally on the owner's hardware.

The name "Jarvis" reflects the full ambition: a personal assistant that grows with its owner.

### Why OpenClaw

Building a universal agent from scratch is impractical for one person. OpenClaw provides the platform layer (gateway, messaging integrations, skills system, dashboard), freeing Jarvis to focus on custom skills and personalization. The previous Python MVP code is archived — it validated core ideas but the infrastructure burden was too high.

## 3. Scope

### In Scope

Phase 1 (current):
- OpenClaw setup with Telegram + direct UI
- PM skills: triage, issue management, project health across all owner's repos
- Local LLM via Ollama with free cloud fallback
- SOUL.md personality configuration

Phase 2 (next):
- Research skills: web research, topic analysis, learning assistance

Phase 3 (later):
- Daily companion features as needed
- Domain expansion based on real usage patterns

### Out of Scope (Current)

- Multi-user / team features (Jarvis serves one person)
- Paid LLM APIs as primary provider
- Cloud hosting (local-first, company server possible later)
- Plugin marketplace
- Mobile app (Telegram is the mobile interface)

## 4. Operating Model

- One human owner defines priorities and approves critical actions.
- Jarvis executes through OpenClaw skills triggered via Telegram or UI.
- PM skills work across all owner's GitHub repositories, not just this one.
- Safety: Jarvis does not get access to critical system resources that could break the machine.

## 5. Delivery Phases

### P1: OpenClaw Migration + PM Skills

Goal: Jarvis running on OpenClaw with PM capabilities usable in real work.

Exit criteria:
- OpenClaw installed and configured locally,
- Telegram and direct UI connected,
- SOUL.md defined,
- Ollama running with suitable model + free cloud fallback configured,
- PM skills ported: daily triage, weekly report, issue health check,
- Skills tested on real projects.

### P2: Research Skills

Goal: Jarvis helps with learning and information gathering.

Exit criteria:
- Web research skill functional,
- Topic summarization and analysis available,
- Research results storable and revisitable.

### P3: Expansion

Goal: Jarvis grows based on real usage patterns.

Exit criteria:
- New skills added based on actual friction points,
- Daily companion features if needed,
- Performance stable on local hardware.

## 6. Decision Rules

When a new idea appears:
1. Does it solve a real problem the owner has right now?
2. Can it be implemented as an OpenClaw skill?
3. Does it work within local hardware constraints?
4. If yes to all — create a task. Otherwise, park in backlog.

When uncertain what to do next:
1. Finish in-progress work first.
2. Prioritize skills that save the most time in daily work.
3. Prefer simple implementations that can be tested immediately.

## 7. Risk Register

R1: OpenClaw breaking changes.
- Mitigation: pin versions, monitor releases, keep skills loosely coupled.

R2: Local hardware insufficient for quality LLM.
- Mitigation: Ollama with quantized models (7B on RTX 3050 6GB), free cloud fallback.
- Future: company server with RTX 40 series if available.

R3: Scope creep into features nobody uses.
- Mitigation: only build skills for problems experienced in the last week.

R4: Security exposure through OpenClaw.
- Mitigation: no access to critical system paths, network exposure limited to localhost.

R5: Bus factor = 1.
- Mitigation: clear documentation, simple architecture, standard OpenClaw patterns.

## 8. Technical Constraints

- Hardware (home): Intel i5 9400f, RTX 3050 6GB, 32GB RAM
- Hardware (future server): 32GB+ RAM, RTX 40 series
- LLM: Ollama local (7B quantized models), free cloud fallback
- Platform: OpenClaw (Node.js, npm)
- Communication: Telegram Bot API, OpenClaw direct UI
- OS: Windows 11 (primary), potentially Linux (server)

## 9. Success Metrics

- Jarvis used daily for real work (not just testing)
- Time saved on PM tasks measurable (fewer manual triage sessions)
- Skills work reliably without constant debugging
- Response quality acceptable on local LLM
