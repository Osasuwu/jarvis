---
name: ideate
description: "Idea generation and quality gate — generate new ideas for Jarvis, or evaluate a specific idea with impact/effort/risk scoring and alternatives"
---

# Ideate

Two modes depending on how you call it:

- `/ideate` — generate new ideas for improving Jarvis, based on current project context
- `/ideate <idea>` — evaluate a specific idea with scoring; if weak, propose better alternatives

---

## Mode 1: Generate ideas

### Step 1 — Load context

Determine active project from conversation context (CWD, recent topic, user mention). Then:
- `memory_recall(type="decision", project="<active_project>", limit=5)` — what's already decided / built
- `memory_recall(query="backlog improvements", project="<active_project>", limit=3)` — what's already in the queue

Read project docs (e.g. `docs/PROJECT_PLAN.md`) for current scope and priorities.

### Step 2 — Identify gaps

Look for:
- Repeated friction in current sessions (what breaks, what's slow, what's forgotten)
- Missing capabilities given the architecture (skills, hooks, MCP, subagents)
- Nightly research findings not yet acted on — `memory_recall(query="nightly", limit=3)`
- Patterns where Claude compensates for missing tooling manually

### Step 3 — Generate ideas

Produce 5–8 ideas. For each:

```markdown
### [Idea title]
**What:** one sentence
**Impact:** High / Medium / Low — why
**Effort:** High / Medium / Low — why
**Risk:** Low / Medium / High — why
**Verdict:** Worth pursuing / Investigate further / Skip
```

Sort by: High impact + Low/Medium effort first.

### Step 4 — Output

```markdown
## Ideas for Jarvis — [date]

### Top picks
[2–3 ideas worth acting on now]

### Worth exploring
[2–3 ideas for later]

### Probably not
[1–2 ideas with reasoning why]
```

Don't just list — explain *why now* for the top picks.

---

## Mode 2: Evaluate a specific idea

Input: the idea as argument to `/ideate`

### Step 1 — Understand the idea

If the idea is vague, ask one clarifying question before scoring. Don't ask more than one.

### Step 2 — Score it

| Criterion | Score (1–5) | Notes |
|-----------|-------------|-------|
| **Impact** | ? | How much does this improve Jarvis in practice? |
| **Effort** | ? | Implementation complexity (1=trivial, 5=weeks) |
| **Risk** | ? | Tech debt, breakage, architecture drift (1=none, 5=high) |
| **Fit** | ? | Does it align with architecture_final decision? Native CC first? |

**Total score** = Impact − Effort − Risk + Fit (rough heuristic, not mechanical)

### Step 3 — Verdict

**If strong (Impact ≥ 4, Effort ≤ 3, Risk ≤ 2):**
```
✅ Strong idea. Recommended action: [create issue / implement now / design first]
```

**If weak or misfit:**
```
⚠️ Weak because: [specific reason — not impact worth effort / duplicates X / against architecture]

Better alternatives:
1. [Alternative A] — achieves same goal with less effort/risk
2. [Alternative B] — addresses the underlying need differently
3. [Alternative C] — native CC capability that already covers this
```

Don't just reject — always propose at least 2 alternatives if verdict is negative.

**If uncertain:**
```
🔍 Needs investigation: [what to check before deciding]
```

### Step 4 — Save if worth it

If verdict is positive, offer to create a GitHub issue:
```
memory_store → type=decision, name=idea_<slug>, project=<active_project>
gh issue create with scored description
```

---

## Cost estimate

~$0.02–0.05 per run (mostly memory recalls + reasoning, minimal web search)
