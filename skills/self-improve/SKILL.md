---
name: self-improve
description: "Auto-apply low-risk fixes from self-review findings, create PR for changes"
model: sonnet
max_budget_usd: 0.50
handler: jarvis.self_improve:handle
background: true
---

# /self-improve

Autonomous self-improvement pipeline for Jarvis.

## What it does

1. Runs a full self-review (deterministic checks + LLM code analysis)
2. Classifies each finding by risk level (low/medium/high)
3. Builds a prioritized improvement plan using LLM
4. Auto-applies **only low-risk** fixes (dead code, minor duplication, simple bugs)
5. Medium/high-risk items are reported but require manual approval
6. Validates changes (compile + tests)
7. Creates a branch and PR with applied fixes

## Usage

- `/self-improve` — full pipeline (auto-apply low-risk, PR)
- `/self-improve --dry-run` — plan only, no changes applied

## Safety

- Never modifies `.env`, `.git/`, secrets, or `safety.py`
- Forbidden shell commands are blocked (rm -rf, force push, etc.)
- All changes validated before commit (compile + tests)
- High-risk findings always need human approval
- Safety module itself cannot be self-modified

## Cost

- Self-review: ~$0.05-0.15 (Sonnet code review)
- Plan generation: ~$0.05-0.10 (Sonnet)
- Fix application: ~$0.10-0.25 (Sonnet with tools)
- Total: ~$0.20-0.50 per run
