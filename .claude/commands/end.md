---
name: end
description: "Close the session: save unsaved decisions to Supabase, output open items for next session"
---

# End Session

Closes the current session properly. Ensures nothing important is lost between sessions.

## Steps

### Step 1 — Scan the conversation
Review the full conversation history. Find anything that was NOT explicitly saved with `memory_store` during the session:
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

### Step 3 — Suggest reflect (if applicable)

Check: are there any `decision` memories updated in the last 14 days that do NOT have an `## Outcome` section, AND have a resolved PR (merged/closed)?

If yes, add one line to the output:
> "Есть N решений с разрешёнными PR без исхода — запусти `/reflect` чтобы зафиксировать уроки."

Don't run reflect automatically. Just surface it.

### Step 4 — Output

```
## Session closed — YYYY-MM-DD

### Saved to memory (N)
- <memory_name> — <one-line description>

### What was done
- <bullet>

### Open items / next session
- <anything unfinished, deferred, or worth picking up next time>
```

Keep it brief. This is a handoff, not a report.
