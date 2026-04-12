---
name: end
description: "Full session close: behavioral reflection, decision log, memory save, commit, handoff. ~5 min."
---

# End Session (Full)

Closes the session with quality reflection. For quick exit, use `/end-quick`.

## Step 1 — Behavioral reflection

Review your own behavior this session against feedback memories (already in context from session start):

1. **Rule violations**: did you break any known rules? (e.g., skipped memory load, assumed instead of verified, added unrequested features, was sycophantic)
2. **Missed context**: did you ignore goals, forget cross-project impact, miss something obvious?
3. **Quality**: did you deliver end-to-end or leave loose ends? Did you verify your work?
4. **Communication**: were you too verbose? Too terse? Did you ask when you should have acted, or act when you should have asked?

If you find a pattern worth recording (not a one-off): save as `feedback` memory. Include **why** it matters and **how to apply** next time.

If nothing notable — skip. Don't fabricate observations.

## Step 2 — Decision & knowledge scan

Review the conversation for unsaved items:
- **Decisions** made (architecture, approach, rejection of alternatives) → `decision` memory
- **User preferences** or profile updates → `user` memory
- **Project state** changes → `project` memory
- **Feedback** given by owner → `feedback` memory

Upsert existing memories, don't create duplicates. Check name before creating new.

## Step 3 — Working state (non-negotiable)

Save `working_state_jarvis` (type=project) to Supabase. Always. Content:
- What was done this session
- Open items: unfinished work, things to fix, deferred tasks
- Key context for next session (blockers, decisions pending review)

This is the handoff to the next session. If open items exist in Step 5 output, they MUST be in this memory too — output is ephemeral, memory persists.

Only exception: truly empty session (user asked one question and left).

## Step 4 — Commit

Run `git status` and `git diff --stat`.

**Commit if:**
- There are uncommitted changes
- Work is complete (not mid-refactor, not broken)
- Changes form a coherent unit

**Don't commit if:**
- Mid-task, experimental, tests failing, or merge conflicts
- Instead, note in output under "Open items"

Stage only session-related files. Standard commit format with Co-Authored-By.

## Step 5 — Output

```
## Session closed — YYYY-MM-DD

### Reflection
- <1-3 behavioral observations, or "Clean session — no issues">

### Saved to memory (N)
- <name> — <one-line>

### Committed
- <hash + message, or "No commit — <reason>">

### What was done
- <bullets>

### Open items
- <unfinished work, deferred tasks, things for next session>
```

Keep it concise. This is a handoff, not a report.
