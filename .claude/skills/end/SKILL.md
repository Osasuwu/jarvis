---
name: end
description: "Close the session: save memories, commit changes, output handoff for next session"
---

# End Session

Closes the current session completely. Saves knowledge, commits work, hands off cleanly.

## Steps

### Step 1 — Scan the conversation
Review the full conversation history. Find anything NOT explicitly saved during the session:
- Decisions made (architecture, tools, approaches chosen or rejected)
- Preferences expressed by the owner
- New facts learned about the owner (profile, habits, goals)
- Project state changes (what was built, what was deferred)
- Feedback given (corrections, confirmations of non-obvious approaches)

### Step 2 — Save to Supabase
For each unsaved item, call `memory_store` with the appropriate type:
- `decision` — architectural/design choices with rationale
- `feedback` — behavioral rules, corrections, confirmed approaches
- `user` — owner profile, preferences, working style (project=null)
- `project` — project state, current work, what's pending

Don't batch. Save each one. Upsert existing memories rather than creating duplicates — check the name before creating new.

### Step 3 — Commit changes (if work is complete)

Run `git status` and `git diff --stat` to check for uncommitted changes.

**Commit if ALL of these are true:**
- There ARE uncommitted changes (staged or unstaged)
- The work from this session is **complete** — not half-done, not mid-refactor, not broken
- The changes form a **coherent unit** — not a mix of unrelated edits that should be separate commits

**Do NOT commit if ANY of these are true:**
- The session ended mid-task (interrupted, ran out of context, hit a blocker)
- Changes are experimental / exploratory and the owner hasn't approved the direction
- Tests are failing because of the changes
- There are merge conflicts

**If committing:** follow the standard commit flow (git add specific files, write a descriptive message, Co-Authored-By). Stage only files related to the session's work — don't accidentally include unrelated changes that were already in the working tree before the session.

**If NOT committing:** mention it in the output under "Open items" with a reason (e.g., "Uncommitted changes: mid-refactor, needs review before commit").

### Step 4 — Suggest reflect (if applicable)

Check: are there any `decision` memories updated in the last 14 days that do NOT have an `## Outcome` section, AND have a resolved PR (merged/closed)?

If yes, add one line:
> "There are N decisions with resolved PRs but no outcome — run `/reflect` to capture lessons."

### Step 5 — Output

```
## Session closed — YYYY-MM-DD

### Saved to memory (N)
- <memory_name> — <one-line description>

### Committed
- <commit hash + message, or "No commit — <reason>">

### What was done
- <bullet>

### Open items / next session
- <anything unfinished, deferred, or worth picking up next time>
```

Keep it brief. This is a handoff, not a report.
