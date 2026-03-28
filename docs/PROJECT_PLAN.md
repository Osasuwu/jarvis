# Jarvis Project Plan

Version: 4.0
Date: 2026-03-28
Status: Active

## 1. Purpose

Strategic plan for Jarvis — a universal personal AI agent built on Claude Agent SDK + MCP.

Use this document to:
- understand the full vision and current priorities,
- decide what to build next,
- keep scope focused on capabilities that deliver real value,
- track architecture evolution and key decisions.

## 2. Problem and Vision

### Problem

One person managing multiple software projects and learning across many domains cannot do everything alone. Development coordination, research, and routine tasks consume time that should go to creative and strategic work.

### Vision

Jarvis is a universal personal AI agent that:
- manages development workflows across multiple GitHub projects,
- helps research and learn new topics,
- executes routine tasks autonomously (with human review for critical actions),
- communicates via Telegram (mobile) and CLI (workstation),
- delegates code changes to specialized coding agents with safeguards,
- remembers conversations, decisions, and context across sessions,
- grows its capabilities through self-review and self-improvement.

The name "Jarvis" reflects the full ambition: a personal assistant that grows with its owner.

### Platform History

1. **Custom Python MVP** (archived) — validated core ideas, but infrastructure burden too high for one person.
2. **OpenClaw** (abandoned 2026-03-23) — promising platform, but critical security issues (512 vulnerabilities, ~20% malicious skills on ClawHub, creator departing for OpenAI) made it unsuitable as a foundation.
3. **Claude Agent SDK + MCP** (current) — production-ready framework from Anthropic. Same engine as Claude Code, programmable in Python/TypeScript, with MCP for external integrations.

## 3. Architecture

### Agent Roles

- **Jarvis (brain)**: orchestrator. Receives user input, classifies intent, routes to skills or delegates to coding agents. Has identity (SOUL.md), memory, and conversation context. Runs on Haiku/Sonnet.
- **Coding agent (executor)**: Claude Code CLI subprocess. Receives structured prompts from Jarvis, writes code, returns results. Has NO Jarvis identity — follows repo-specific CLAUDE.md instructions. Uses Pro subscription.
- **Owner (human)**: strategic decisions, PR review, go/no-go on critical actions.

### Key Principle

Jarvis is the brain, not a prompt router. It should:
1. Understand context from memory and conversation history
2. Decide whether to act itself or delegate
3. Provide its identity (SOUL.md) to its own LLM calls, NOT to coding agents
4. Receive structured summaries from every tool/agent it delegates to
5. Write important decisions and context to memory

The coding agent is just an executor. It gets: Jarvis's structured prompt + the target repo's CLAUDE.md. It doesn't need Jarvis's memory or identity.

### Memory Architecture

Three layers:
1. **Conversation log** — full chat history per user session. New session daily or on demand. Compressed when context grows large. Enables continuity within a session.
2. **Structured memory** — extracted knowledge: decisions, plans, user preferences, project context. Persists across sessions. Loaded into Jarvis prompts.
3. **Execution log** — append-only JSONL of skill runs (work_memory.jsonl). Used by self-review/self-improve. Auto-cleanup after retention period.

The coding agent does NOT receive Jarvis memory. It gets project context from the target repo's CLAUDE.md, plus a `[JARVIS-AUTOMATED]` tag to indicate it's running under automation.

## 4. Scope

### In Scope

Milestone 1 — Architecture Migration (DONE):
- Claude Agent SDK project setup
- Telegram integration
- Model tier configuration (Haiku/Sonnet/Opus)
- Basic agent loop: receive command → execute → respond

Milestone 2 — Core Features (DONE):
- PM skills on demand: triage, weekly report, issue health
- Research skill: source-backed research with confidence scoring
- Delegation pipeline: Jarvis decomposes → coding agent executes → PR
- Cost control: daily budget, per-query limits, model tier routing

Milestone 3 — Intelligence Layer (IN PROGRESS):
- Identity: SOUL.md loaded into every Jarvis LLM call
- Conversation memory: session-based chat history with compression
- Structured long-term memory: decisions, plans, preferences persisted
- Intent routing: plain text → skill classification without slash commands
- Self-improvement: self-review → opportunity scan → risk radar → self-improve loop

Milestone 4 — Expansion (PLANNED):
- Multi-repo delegation (coding agent CWD fix)
- Long-term memory with semantic search (vector store)
- Inbox aggregator (when solo dev gets inbound volume)
- Scheduled execution (when regular cadence becomes useful)
- Context-switch helper (may be obsoleted by memory)

### Out of Scope (Current)

- Multi-user / team features (Jarvis serves one person)
- Cloud hosting (runs on owner's machine, API calls to Claude)
- Plugin marketplace
- Mobile app (Telegram is the mobile interface)
- Local LLM as primary (deferred; possible as auxiliary MCP tool later)

### Deferred (Build When Needed)

- Scheduled cron execution — owner works irregular schedule, manual trigger preferred
- Weekly report automation — rarely reviewed, on-demand is sufficient
- Inbox aggregator — solo dev has minimal inbound; build when volume grows

## 5. Delivery Milestones

### M1: Architecture Migration ✅

Goal: Jarvis running on Claude Agent SDK with basic Telegram connectivity.

Exit criteria (all met):
- Agent SDK project created and runnable
- Claude API key configured with billing
- Telegram bot receives messages and responds via Agent SDK
- Model tiers configured (Haiku default, Sonnet for complex tasks)
- Basic command routing works (/triage, /weekly-report, /issue-health)

### M2: Core Features ✅

Goal: PM capabilities functional + delegation pipeline working.

Exit criteria (all met):
- PM skills available on demand via Telegram and CLI
- Research skill functional with source-backed findings
- Delegation pipeline: Jarvis decomposes issue → coding agent implements → PR created
- Cost control: daily budget tracking, per-query limits enforced

### M3: Intelligence Layer 🔧

Goal: Jarvis becomes a stateful assistant with identity and memory.

Exit criteria:
- SOUL.md loaded into every Jarvis LLM call (identity)
- Conversation history maintained per session (short-term memory)
- Important context extracted and persisted across sessions (long-term memory)
- Plain text messages routed to correct skills without slash commands
- Self-improvement cycle functional: review → analyze → propose → apply

### M4: Expansion 📋

Goal: Jarvis handles multiple repos and scales capabilities.

Exit criteria:
- Coding agent can work in any repo (not just Jarvis repo)
- Long-term memory searchable via semantic similarity
- Additional skills added as real needs emerge

## 6. Decision Rules

When a new idea appears:
1. Does it solve a real problem the owner has right now?
2. Can it be implemented within Claude Agent SDK architecture?
3. Is the cost acceptable within $10-30/month API budget?
4. If yes to all — create a task. Otherwise, park in GitHub Discussions (Ideas category).

When uncertain what to do next:
1. Finish in-progress work first.
2. Prioritize capabilities that save the most time in daily work.
3. Prefer simple implementations that can be tested immediately.
4. Memory and identity features take priority over new skills.

## 7. Risk Register

R1: Claude API cost overrun.
- Mitigation: use Haiku for routine tasks, Sonnet only when needed, Opus rarely. Monitor spending weekly.
- Budget ceiling: $30/month. Alert if approaching $25.

R2: Vendor lock-in to Anthropic.
- Mitigation: keep agent logic decoupled from SDK specifics where practical. MCP integrations are standard-based and portable.
- Accepted trade-off: Claude quality justifies lock-in at this scale.

R3: Scope creep into features nobody uses.
- Mitigation: only build for problems experienced in the last week. Park ideas in GitHub Discussions.
- New: defer inbox, scheduling, context-switch until real need emerges.

R4: Coding agent produces bad code.
- Mitigation: all code changes go through PR. Branch protection enforced. CLAUDE.md in each repo instructs conservative behavior for agent-generated tasks.

R5: Bus factor = 1.
- Mitigation: clear documentation, simple architecture, standard patterns.

R6: Memory bloat / noise.
- Mitigation: conversation logs compressed per session. Structured memory is selective — only decisions, plans, preferences. Execution logs auto-cleaned after retention period.

## 8. Technical Constraints

- Hardware (home): Intel i5 9400f, RTX 3050 6GB, 32GB RAM
- LLM: Claude API (Haiku $1/1M input, Sonnet $3/1M input, Opus $5/1M input)
- Budget: $10-30/month on API
- Platform: Claude Agent SDK (Python or TypeScript)
- Integrations: MCP servers (GitHub, Telegram, filesystem)
- Communication: Telegram Bot API via MCP, Claude Code CLI for workstation
- OS: Windows 11 (primary)

## 9. Success Metrics

- Jarvis used daily for real work (not just testing)
- Jarvis remembers context from previous sessions without re-explanation
- API cost stays within $30/month budget
- Delegation pipeline produces usable PRs that need minimal human editing
- Skills work reliably without constant debugging
- Self-improvement cycle identifies real issues and proposes useful fixes
