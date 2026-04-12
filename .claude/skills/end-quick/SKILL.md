---
name: end-quick
description: "Quick session close: checkpoint + commit only. ~30 sec. Use when owner needs to leave fast."
---

# End Session (Quick)

Fast exit. No reflection, no memory scan. For full close, use `/end`.

## Step 1 — Working state

If there is meaningful unfinished work:
- Save `working_state_jarvis` (type=project) to Supabase: what was done, what's pending, key context
- If nothing notable — skip

## Step 2 — Commit

Run `git status`. If there are changes and they're complete:
- Stage relevant files, commit with descriptive message
- If mid-task or broken — don't commit, just note it

## Step 3 — Output

One-liner:

```
Session saved. <committed: hash | no commit: reason>. <working state: saved | nothing to save>.
```

That's it. Go.
