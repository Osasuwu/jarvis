---
name: checkpoint
description: "This skill MUST be used proactively by Claude (not just when user asks) to save working state to Supabase memory. Trigger it automatically at these moments: (1) after understanding a complex multi-file task — before the first edit, (2) after resolving a merge conflict, (3) after each significant commit in a long session (4+ commits), (4) when context window has grown large. Also trigger when user says 'checkpoint', 'сохрани состояние', 'запомни где мы', or similar. Do NOT wait for the user to ask."
version: 1.0.0
---

# Checkpoint

Saves current working state to Supabase so it can be restored after context compression or in a new session. Call this proactively — do not wait for the user to ask.

## Steps

### 1. Determine active project scope

Pick ONE primary project for this checkpoint based on conversation context:
- What repo/directory is the current work in?
- What topic is being discussed?

Use the repo name or a short slug as the project value (e.g. `"redrobot"`, `"jarvis"`, `"spotify"`). Don't hardcode — derive from context.

### 2. Collect state

From current conversation context, identify:
- **task**: what is being worked on (one sentence)
- **branch**: current git branch if known
- **files**: key files changed or being worked on (comma-separated)
- **done**: what has been completed this session
- **next**: the immediate next action
- **context**: any non-obvious state that would be lost after compression (e.g. "merge conflict resolved by taking master's version", "test expects 3 linear calls not 2")

### 3. Save to Supabase

```
memory_store(
  name="working_state_<project>",
  project="<project>",
  type="project",
  content="task: <task>
branch: <branch>
files: <files>
done: <done>
next: <next>
context: <context>"
)
```

Use the stable name `working_state_<project>` — this upserts on repeat calls, not duplicates.

### 4. Confirm silently

Output exactly one line:
`Checkpoint saved — <project>: <one-line summary>`

No other output. Resume work immediately.

## On session restore

If `memory_recall(query="working state")` returns a checkpoint:
1. Announce it to the user: *"Есть незакрытый checkpoint: <project> — <summary>. Продолжим?"*
2. After confirmation: read only the files listed in `files` field (use `offset`/`limit`)
3. When task is fully done: `memory_delete(name="working_state_<project>", project="<project>")`
