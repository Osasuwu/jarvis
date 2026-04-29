---
name: end-quick
description: "Quick session close: checkpoint + commit only. ~30 sec. Use when principal needs to leave fast."
---

# End Session (Quick)

Fast exit. No reflection, no memory scan. For full close, use `/end`.

**Note — compaction-safe:** end-quick skips the session-journal scan on purpose. The PreCompact hook (`scripts/pre-compact-backup.py`) already persists a pre-compact snapshot to Supabase under `session_snapshot_<session_id>` on every compaction, and `record_decision` writes decisions in real time. That's enough durable handoff. Run `/end` instead if you want reflection + decision reconciliation.

## Step 1 — Working state

If there is meaningful unfinished work:
- Save `working_state_jarvis` (type=project) to Supabase: what was done, what's pending, key context
- If nothing notable — skip

## Step 2 — Commit (leave nothing uncommitted)

Check ALL project repos for uncommitted changes (jarvis, redrobot, any other repo touched this session).

For each repo with changes:
1. `git status`
2. If on an **unrelated branch** → `git stash && git checkout $(git symbolic-ref refs/remotes/origin/HEAD | sed 's@^refs/remotes/origin/@@') && git pull --ff-only && git stash pop` (resolve conflicts if any)
3. Complete work → stage and commit. Mid-task → `git stash push -m "session YYYY-MM-DD: <description>"` and note stash ref.

## Step 3 — Output

One-liner:

```
Session saved. <committed: hash | no commit: reason>. <working state: saved | nothing to save>.
```

That's it. Go.
