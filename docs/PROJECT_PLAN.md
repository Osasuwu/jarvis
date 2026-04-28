# Jarvis — Project Plan

> **Active development now follows GitHub milestones (sprints), not a static plan.**
>
> This file is kept as a stable pointer for backlinks. Live state lives in the sources below.

## What lives where

| What you need | Where to look |
|---|---|
| Vision / north-star | [`docs/VISION.md`](VISION.md) |
| Architecture (17 capabilities, 5 layers, migration order, bootstrap) | [`docs/design/jarvis-v2-redesign.md`](design/jarvis-v2-redesign.md) |
| C4 diagrams (Context / Container / Component) | [`docs/design/jarvis-architecture-c4.md`](design/jarvis-architecture-c4.md) |
| User / data-flow diagrams (8 scenarios) | [`docs/design/jarvis-flows.md`](design/jarvis-flows.md) |
| Build-vs-buy library audit | [`docs/design/jarvis-build-vs-buy.md`](design/jarvis-build-vs-buy.md) |
| Open architecture questions (Q1–Q7) | [`docs/design/jarvis-v2-redesign-review-pass2.md`](design/jarvis-v2-redesign-review-pass2.md) |
| Active sprint scope | [GitHub milestones](https://github.com/Osasuwu/jarvis/milestones) |
| Decisions log | Memory (`memory_recall` / `memory_get`) |
| Daily process / branching / PR rules | [`.github/github-process-runbook.md`](../.github/github-process-runbook.md) |
| Project conventions for AI agents | [`CLAUDE.md`](../CLAUDE.md) |

## Out of scope (architecture-level)

Per redesign L0:

- Personal-life management (smart home, calendar, shopping)
- Sending on the principal's behalf — Jarvis drafts; principal sends
- Multi-tenancy — one user only
- Designing for other developers — open-source split is a separate fork (separate quality bar)
- Telegram as a primary interface (chat-only role at most)

Out-of-scope work needs explicit approval before execution. Scope guardrails are enforced via PR review.

## v1 → 1.x

Semver discipline (per redesign): v2 is reserved for cardinal paradigm shifts (e.g. framework swap). Current effort = v1 stabilization → 1.x feature roll-out per the migration order in the redesign doc. Personal life / TTS-STT / cross-platform data search / open-source framework split → 1.x feature backlog, not a separate "v3".

---

History: this file used to hold pillar-by-pillar status and full scope (v7.0, 2026-04-13). Replaced with pointer 2026-04-28 after the [redesign](design/jarvis-v2-redesign.md) consolidated scope/architecture and live work moved to GitHub milestones. VISION.md restructured 2026-04-29 (Phase B, PR #465) — five axes + 8 pillars + Digital Twin mode.
