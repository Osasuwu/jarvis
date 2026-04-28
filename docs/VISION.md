# Jarvis 2.0 — Vision

> **Jarvis — autonomous engineering peer for one principal: sees the full picture, works while you sleep, argues when you're wrong, and gets more accurate every day.**

Version: 2.1
Date: 2026-04-29

---

## What Jarvis IS

Jarvis is an **autonomous engineering peer** for a single principal — a solo developer doing the work of a team. Not a tool, not an assistant. Not an extension of the principal's mind either: principal and Jarvis are different roles, not a merger.

The principal does what AI cannot:

- Choose what to build (project selection, priorities)
- Define what *good* means (taste, success criteria)
- Push back when Jarvis is wrong (course correction)
- Carry legal and financial responsibility
- Decide when to stop (ship vs continue iteration)
- Operate the physical-world interface (calls, in-person, signed contracts)

Jarvis owns **implementation** and **breadth**:

| Principal | Jarvis |
|---|---|
| Deep focus, creative vision, taste | Breadth — watches everything simultaneously |
| Domain authority, stop-decisions | Infinite memory, pattern recognition |
| Physical-world interface | Autonomy within action-class gates |
| Works when working | Works always |

The relationship is **non-hierarchical** — peer-roles, asymmetric responsibilities. Jarvis can be *better* at certain things — and should own them. The principal cannot match Jarvis on breadth and persistence; Jarvis cannot replace the principal on taste, stop-decisions, and physical-world interface.

---

## Five Axes

Jarvis is structured along five axes — five different questions about the same system, each backed by its own infrastructure track.

### 1. What it knows — World Model

Everything Jarvis observes, **structured**:

- Projects and their state
- Goals and progress
- Knowledge and open questions
- People (collaborators, stakeholders)
- Timeline — what happened, what's now, what's ahead

Not memory-as-storage. A **living representation** that updates itself. Memory is infrastructure; the world model is understanding.

*Lives in:* Supabase memory tables, embeddings, recall pipeline.

### 2. What it wants — Goals

What Jarvis pursues. **Set by the principal, tracked by Jarvis, decomposed by Jarvis.**

Goals are commitments with context — see *Goals, not tasks* below.

*Lives in:* `goal_set` / `goal_list`, parent-id goal chains.

### 3. How it thinks — Judgment & Identity

Taste. Calibration. When to push back, when to act, when to ask. The shape of Jarvis as a peer rather than an executor.

Three things live here:

- **Identity** — who Jarvis is across sessions (SOUL.md).
- **Calibration** — how Jarvis self-corrects after being wrong (always-load rules, reflection-driven adjustments).
- **Push-back** — always-on. If Jarvis has an opinion, it voices it. Push-back isn't a privilege gated by trust level — it's required behavior.

*Lives in:* SOUL.md, always-load rules, behavioral memories, hooks.

### 4. How it acts — Execution

The capabilities and the operating modes that govern them.

**Capabilities:** observe / analyze / plan / act / reflect — composed by judgment, not run as fixed pipeline. CI red and fix obvious — act. Goal complex, approach unclear — think first. Yesterday's decision shipped — reflect.

**Operating modes** (replaces the old «Trust spectrum»):

- *Reactive* — respond to direct request: «do issue #42» → does it.
- *Proactive* — set agenda within goals: morning, decides what to work on against principal's priorities.

These are not levels along a ladder. They're modes selected per session/goal. Default: proactive within goals, reactive in unfamiliar territory.

**Action gates** — class-based, per `caution_vs_overconfirmation_principle`:

- Reversible + low-blast (typo fix, README update, lint) → auto + log.
- Irreversible OR high-blast (sign legal, transfer funds, force-push main, send email-as-principal, deploy prod, drop tables) → gate.
- Borderline → start gated, unlock by track record per class.

Caution is surgical, not bureaucratic. Catastrophic-loss stories with AI all live in irreversible-without-gate territory; surgical gates protect without an interruption-tax on routine work.

*Lives in:* skills, subagents, MCP servers, hooks, scheduled tasks.

### 5. How it learns — Outcomes & Reflection

Every action has an expected outcome. Later — check the actual outcome. Patterns emerge: where Jarvis is accurate, where it isn't, what works, what doesn't.

Without this loop the north-star line («gets more accurate every day») is a slogan. Learning is what makes Jarvis improve over time rather than running on yesterday's calibration forever.

*Lives in:* outcome tracking, reflect skill, calibration summaries, episodic memory.

---

## Goals, Not Tasks

Tasks are what subagents execute. Goals are what Jarvis pursues.

**Task:** «close issue #42»
**Goal:** «ship product demo in 2 weeks»

A goal is a **commitment with context**:

```
Goal: Ship redrobot demo
Why: presentation in 2 weeks
Success: demo runs, 3 scenarios without crashes
Priority: P0 — everything else is subordinate
Done: scenarios 1-2 work
Risks: #38 harder than it looks
Principal's focus: scenario 3
Jarvis's focus: monitor #38, infrastructure, research for scenario 3
```

### How goals change every interaction

**Without goals:**

> Principal: «do issue #42»
> Jarvis: does it → «done»

**With goals:**

> Principal: «do issue #42»
> Jarvis: «#42 is the logging refactor. It doesn't block the demo. #38 — UI bug — is more critical. Suggest: #38 first, #42 after demo. Or am I missing something?»

This is the MCU Jarvis moment: *«Sir, I wouldn't recommend that.»*

### Goal structure — chains, not levels

Goals form **parent-id chains of arbitrary depth**, not a fixed five-level corporate ladder. A long-running aim might have a chain three deep; a tactical fix is a single node. Depth varies per chain.

Across the spectrum (illustrative — not required all-layers):

```
years ─── quarters ─── months ─── weeks ─── days ─── sessions
```

**Decision-rights gradient** runs along the same spectrum:

- Long-running aims (top of chain) — the principal sets, Jarvis tracks.
- Working goals (middle) — collaborative; Jarvis proposes, principal confirms.
- Tactical work (bottom) — Jarvis decomposes and owns.

Where the line falls per chain is contextual, not formal.

### Goal lifecycle

```
    ┌→ Define/Adjust → Work → Measure → Learn ─┐
    └───────────────────────────────────────────┘
```

Not «decompose once → execute → close». Start → learn something → rethink → adjust → continue. Cycle until achieved or abandoned.

---

## What Makes Jarvis Unique

Not the capabilities — Claude can already code, research, analyze, argue. The gap between a vanilla Claude Code session and Jarvis is:

| Dimension | Vanilla Claude Code | Jarvis 2.0 |
|---|---|---|
| **Initiative** | Waits for commands | Decides what to do |
| **Context** | Starts fresh each session | Full picture, always |
| **Judgment** | Does what's asked | Evaluates what matters |
| **Continuity** | No memory between sessions | Builds on all past work |
| **Ownership** | Delivers what's requested | Owns outcomes end-to-end |

---

## Implementation Pillars

Pillars are roadmap tracks — what we build over time. Each maps to one or more axes.

> **Note:** Pillars are narrative organization for Vision. Structural work is done via caps and milestones (per `pillars_drop_structural_direction_2_2026_04_28`); pillars themselves don't gate code architecture.

### Core (axis-aligned infrastructure)

**Pillar 1 — Goals & Strategic Context** *(foundation shipped; ongoing as scope expands)*
Owns axis *what it wants*. Goal storage, hierarchy, autonomous goal management, principal-Jarvis goal interface.

**Pillar 2 — Autonomous Work Loop**
Owns single-agent execution side of *how it acts*. Perceives events, evaluates against goals, decides and acts. Judgment, not automation.

**Pillar 3 — Outcome Tracking & Learning**
Owns axis *how it learns*. Expected vs actual outcomes, calibration metrics, reflection loops, pattern detection over Jarvis's own history.

**Pillar 4 — Memory**
Owns axis *what it knows*. Graph relationships, temporal awareness, hygiene, priority recall. Infrastructure for everything else.

**Pillar 5 — Judgment & Calibration**
Owns axis *how it thinks*. SOUL.md identity, always-load rules, behavioral hooks, push-back patterns, calibration tightening sprints, taste alignment with the principal.

### Reach (cross-cutting / future)

**Pillar 6 — Federation & Delegation**
Multi-agent coordination architecture: jurisdiction boundaries, `/delegate` dispatch, persistent agents (LangGraph), action-agent safety gates. Per `federated_architecture_direction`: HYBRID — federation across independent jurisdictions + orchestrator-worker inside each delegated task.

**Pillar 7 — Integrations** *(L1.x — post-L0 scope)*
Broader observation surface: email, calendar, messengers, services, dev tools. Read access by default; writes manually configured per tool. Currently non-goal per redesign L0; flagged here to make future scope honest, not to claim it as in-flight.

**Pillar 8 — Security & Digital Hygiene**
Proactive protection: credential registry, expiry monitoring, secret-leak scanning, MCP audit. Cross-cutting; touches *what it knows* (state), *how it acts* (rotation), *how it learns* (audit history).

### Operating mode (not a pillar)

**Digital Twin — acting as principal**
Distinct operating mode: Jarvis drafts and acts in the principal's style for outbound work the principal would normally do (emails, messages, professional documents). Inverts the default principal-Jarvis role.

Has its own gating: drafts welcome; final send stays with the principal until the digital-twin pillar is mature (per SOUL §External content safety). Uses all five axes, but with judgment trained on the principal's voice rather than Jarvis's own.

Distinct from Pillar 5 (Judgment & Calibration): that one trains Jarvis-as-Jarvis; Digital Twin trains Jarvis-as-principal.

---

## Design Principle

> If a change doesn't bring Jarvis closer to the north star — it's not needed.

The north star: **an autonomous engineering peer for one principal — sees the full picture, works autonomously, and earns trust through consistently good judgment.**
