# Jarvis Project Plan

Version: 3.0
Date: 2026-03-23
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
- delegates code changes to specialized coding agents with safeguards.

The name "Jarvis" reflects the full ambition: a personal assistant that grows with its owner.

### Platform History

1. **Custom Python MVP** (archived) — validated core ideas, but infrastructure burden too high for one person.
2. **OpenClaw** (abandoned 2026-03-23) — promising platform, but critical security issues (512 vulnerabilities, ~20% malicious skills on ClawHub, creator departing for OpenAI) made it unsuitable as a foundation.
3. **Claude Agent SDK + MCP** (current) — production-ready framework from Anthropic. Same engine as Claude Code, programmable in Python/TypeScript, with MCP for external integrations.

## 3. Scope

### In Scope

Milestone 1 — Architecture Migration:
- Claude Agent SDK project setup
- Telegram integration via MCP
- Model tier configuration (Haiku/Sonnet/Opus)
- Basic agent loop: receive command → execute → respond

Milestone 2 — Core Features:
- PM skills: triage, weekly report, issue health (ported from OpenClaw markdown skills)
- Scheduled execution (cron for daily triage, weekly reports)
- Delegation pipeline: Jarvis decomposes tasks → coding agent executes → PR for review
- Self-check: Jarvis validates its own configuration and skill consistency

Milestone 3 — Expansion:
- Research skills: web research, topic analysis, learning assistance
- Inbox aggregator: unified view of what needs attention
- Context-switch helper: quick summary when switching between projects
- Self-improvement: changelog watching, skill quality analysis

### Out of Scope (Current)

- Multi-user / team features (Jarvis serves one person)
- Cloud hosting (runs on owner's machine, API calls to Claude)
- Plugin marketplace
- Mobile app (Telegram is the mobile interface)
- Local LLM as primary (deferred; possible as auxiliary MCP tool later)

## 4. Operating Model

### Decision Hierarchy

- **Owner (human)**: strategic decisions, PR review, go/no-go on critical actions.
- **Jarvis (planner)**: read-only access to repos, triage, research, task decomposition, monitoring. Runs on Haiku/Sonnet.
- **Jarvis (coder)**: write access limited to branches + PRs. Executes specific tasks delegated by planner. Runs on Sonnet.
- **Safeguard layer**: branch protection, required PR reviews, CLAUDE.md conservative mode instructions.

### Key Principle

The owner is the bridge between physical and virtual worlds. Jarvis handles tactical execution; the owner makes strategic decisions. The owner's job is not writing prompts for individual issues, but directing the agent at a higher level.

## 5. Delivery Milestones

### M1: Architecture Migration

Goal: Jarvis running on Claude Agent SDK with basic Telegram connectivity.

Exit criteria:
- Agent SDK project created and runnable,
- Claude API key configured with billing,
- Telegram bot receives messages and responds via Agent SDK,
- Model tiers configured (Haiku default, Sonnet for complex tasks),
- Basic command routing works (/triage, /weekly-report, /issue-health).

### M2: Core Features

Goal: PM capabilities from OpenClaw era fully functional + new capabilities.

Exit criteria:
- Daily triage runs on schedule and delivers report via Telegram,
- Weekly report runs on Friday and delivers via Telegram,
- Issue health check available on demand,
- Delegation pipeline: Jarvis can create structured prompts for coding tasks,
- Self-check: Jarvis validates its own repos.conf and skill consistency.

### M3: Expansion

Goal: Jarvis grows beyond PM into research and self-improvement.

Exit criteria:
- Web research skill functional,
- Inbox aggregator available,
- Context-switch helper works across all owner's projects,
- Scheduled skill execution reliable (cron-based).

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

## 7. Risk Register

R1: Claude API cost overrun.
- Mitigation: use Haiku for routine tasks, Sonnet only when needed, Opus rarely. Monitor spending weekly.
- Budget ceiling: $30/month. Alert if approaching $25.

R2: Vendor lock-in to Anthropic.
- Mitigation: keep agent logic decoupled from SDK specifics where practical. MCP integrations are standard-based and portable.
- Accepted trade-off: Claude quality justifies lock-in at this scale.

R3: Scope creep into features nobody uses.
- Mitigation: only build for problems experienced in the last week. Park ideas in GitHub Discussions.

R4: Coding agent produces bad code.
- Mitigation: all code changes go through PR. Branch protection enforced. CLAUDE.md in each repo instructs conservative behavior for agent-generated tasks.

R5: Bus factor = 1.
- Mitigation: clear documentation, simple architecture, standard patterns.

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
- Time saved on PM tasks measurable (fewer manual triage sessions)
- API cost stays within $30/month budget
- Delegation pipeline produces usable PRs that need minimal human editing
- Skills work reliably without constant debugging
