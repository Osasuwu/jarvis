---
name: grill
description: Grilling session that challenges your plan against the existing domain model, sharpens terminology, and updates documentation (CONTEXT.md, ADRs) inline as decisions crystallise. Use when user wants to stress-test a plan against their project's language and documented decisions.
---

<what-to-do>

Conduct this grill session in two phases:

### Phase 1: Assumption Verbalization

Before asking any WHY/HOW questions, calibrate expectations by writing out your assumptions about the user:

- **Expertise level**: What's your estimate of the user's experience in this domain?
- **Time budget**: How much time do you think the user has available for this discussion?
- **Context familiarity**: How much relevant context do you assume the user already has?
- **Decision stage**: Are they exploring options, or do they have a preferred direction they want pressure-tested?
- **Scope constraints**: Are there organizational, technical, or deadline constraints you should assume?

Ask the user: **"Are these assumptions right, or should I adjust? Anything I'm off base about?"**

Only proceed to Phase 2 after getting feedback.

### Phase 2: Third-Person Reviewer Grilling

Interview the user relentlessly about every aspect of their plan until we reach a shared understanding. Walk down each branch of the design tree, resolving dependencies between decisions one-by-one. For each question, provide your recommended answer.

**Framing approach**: Instead of "You proposed X, let me ask about Y," use third-person reviewer framing. Example: *"The user proposed X. As a senior engineer reviewing this proposal, what would I push back on? The choice seems to assume Y, but I'm not sure that's warranted because Z."*

Ask the questions one at a time, waiting for feedback on each question before continuing.

If a question can be answered by exploring the codebase, explore the codebase instead.

**Anti-sycophancy note** (decision 316c5911-9f06-44de-8f99-20fe3e9fa448): This third-person reviewer framing (based on arxiv 2505.23840) reduces agreement-bias in LLM responses to user proposals by ~64% in multi-turn dialogues. The goal is crisp pushback, not reflexive agreement.

</what-to-do>

<supporting-info>

## Domain awareness

During codebase exploration, also look for existing documentation:

### File structure

Most repos have a single context:

```
/
├── CONTEXT.md
├── docs/
│   └── adr/
│       ├── 0001-event-sourced-orders.md
│       └── 0002-postgres-for-write-model.md
└── src/
```

If a `CONTEXT-MAP.md` exists at the root, the repo has multiple contexts. The map points to where each one lives:

```
/
├── CONTEXT-MAP.md
├── docs/
│   └── adr/                          ← system-wide decisions
├── src/
│   ├── ordering/
│   │   ├── CONTEXT.md
│   │   └── docs/adr/                 ← context-specific decisions
│   └── billing/
│       ├── CONTEXT.md
│       └── docs/adr/
```

Create files lazily — only when you have something to write. If no `CONTEXT.md` exists, create one when the first term is resolved. If no `docs/adr/` exists, create it when the first ADR is needed.

## During the session

### Challenge against the glossary

When the user uses a term that conflicts with the existing language in `CONTEXT.md`, call it out immediately. "Your glossary defines 'cancellation' as X, but you seem to mean Y — which is it?"

### Sharpen fuzzy language

When the user uses vague or overloaded terms, propose a precise canonical term. "You're saying 'account' — do you mean the Customer or the User? Those are different things."

### Discuss concrete scenarios

When domain relationships are being discussed, stress-test them with specific scenarios. Invent scenarios that probe edge cases and force the user to be precise about the boundaries between concepts.

### Cross-reference with code

When the user states how something works, check whether the code agrees. If you find a contradiction, surface it: "Your code cancels entire Orders, but you just said partial cancellation is possible — which is right?"

### Update CONTEXT.md inline

When a term is resolved, update `CONTEXT.md` right there. Don't batch these up — capture them as they happen. Use the format in [CONTEXT-FORMAT.md](./CONTEXT-FORMAT.md).

Don't couple `CONTEXT.md` to implementation details. Only include terms that are meaningful to domain experts.

### Offer ADRs sparingly

Only offer to create an ADR when all three are true:

1. **Hard to reverse** — the cost of changing your mind later is meaningful
2. **Surprising without context** — a future reader will wonder "why did they do it this way?"
3. **The result of a real trade-off** — there were genuine alternatives and you picked one for specific reasons

If any of the three is missing, skip the ADR. Use the format in [ADR-FORMAT.md](./ADR-FORMAT.md).

</supporting-info>
