# Jarvis Roadmap

Universal personal AI agent built on OpenClaw.

## Current: P1 — OpenClaw Migration + PM Skills

Goal: Jarvis running on OpenClaw, usable for daily PM work across all projects.

Tasks:
- [ ] Archive Python MVP code to `archive/python-mvp` branch
- [ ] Install and configure OpenClaw locally
- [ ] Configure Ollama with suitable 7B model + free cloud fallback
- [ ] Connect Telegram Bot
- [ ] Set up direct UI for workstation use
- [ ] Write SOUL.md (Jarvis personality and behavior)
- [ ] Port daily triage logic as OpenClaw skill
- [ ] Port weekly report logic as OpenClaw skill
- [ ] Port issue health check as OpenClaw skill
- [ ] Test skills on all 3 real projects

## Next: P2 — Research Skills

Goal: Jarvis helps with learning, research, and information analysis.

Tasks:
- [ ] Web research skill (search, summarize, cite)
- [ ] Topic deep-dive skill (structured analysis)
- [ ] Research persistence (save and revisit findings)

## Later: P3 — Expansion

Goal: Jarvis grows based on real friction points in daily work.

Candidates (prioritized by actual need):
- Daily companion (morning brief, reminders, context-keeping)
- Context fusion (merge notes, tasks, calendar, code context)
- Self-improvement loop (detect weak spots, propose skill upgrades)
- Domain-specific skills as needed

## Long-Term Vision

From [Ideas.md](archive/legacy-design/Ideas.md):
- Agent factory: spawn specialized sub-agents
- Living memory graph: people, projects, concepts
- Personal research lab: multi-step investigations
- Vertical scaling: deeper expertise per domain
- Horizontal scaling: more domains and tools
- Temporal scaling: memory across months/years

These are aspirational — they enter the roadmap only when driven by real need.

## Archived

The original Python MVP (ReAct loop, tool registry, safety layer, triage engine) validated core concepts. Code archived in `archive/python-mvp` branch. Key lessons carried forward:
- Safety-first approach matters but shouldn't be over-engineered
- Triage and reporting are the highest-value PM features
- Local LLM fallback is essential for cost-free operation
