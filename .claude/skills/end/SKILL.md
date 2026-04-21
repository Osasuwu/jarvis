---
name: end
description: "Full session close: behavioral reflection, decision log, memory save, commit, handoff. ~5 min."
---

# End Session (Full)

Closes the session with quality reflection. For quick exit, use `/end-quick`.

**Mindset — survives compaction:** *Supabase is the session journal. The conversation is working memory.* The post-compact conversation is a lossy summary; the journal (pre-compact snapshot + real-time `record_decision` entries) is the authoritative record. `/end` consolidates the journal into learnings. Don't rely on scanning the conversation alone — anything older than the last summary may already be gone from your window.

## Step 0 — Load the session journal (non-negotiable)

Before reflecting or scanning, pull everything durable from Supabase:

1. **Pre-compact snapshot** — `memory_recall(query="pre-compact session snapshot", project="jarvis", type="project", limit=5, brief=true)`. Results are live memories sorted by relevance + recency. Pick the entry whose name starts with `session_snapshot_` and whose tags include `session-snapshot` (ignore any with `test` in the name). Then `memory_get` on that name to load the full content.
   - If no snapshot found → this session never compacted. Fine, skip. Conversation alone is enough.
   - If the freshest snapshot looks like a *different* session's work (content references work unrelated to what you remember from the current context) → flag in Step 7 output and fall back to conversation only.
   - Multiple compacts in one session share a single snapshot (same session_id, upserted on each compaction); the one you pick is the latest state.
2. **Real-time decisions** — `memory_recall(query="decisions today <date>", project="jarvis", type="decision", limit=20, brief=true)` where `<date>` is today's ISO date. These should already be in place via `record_decision` calls made during the session. Step 2 will verify completeness.
3. **Recent episodes (optional)** — if you need finer-grained provenance, `events_list` surfaces `tool_call`, `decision`, and `observation` episodes the extractor captured.

Carry the snapshot + decisions into Steps 1-2 as the primary source. The conversation (post-compact) is only a hint overlay for anything that happened *after* the snapshot was written.

## Step 1 — Behavioral reflection

Review your own behavior this session against feedback memories (already in context from session start). Reflect against **snapshot + conversation union**, not conversation alone — the snapshot preserves what the LLM summary smoothed over:

1. **Rule violations**: did you break any known rules? (e.g., skipped memory load, assumed instead of verified, added unrequested features, was sycophantic)
2. **Missed context**: did you ignore goals, forget cross-project impact, miss something obvious?
3. **Quality**: did you deliver end-to-end or leave loose ends? Did you verify your work?
4. **Communication**: were you too verbose? Too terse? Did you ask when you should have acted, or act when you should have asked?

If you find a pattern worth recording (not a one-off): save as `feedback` memory. Include **why** it matters and **how to apply** next time.

If nothing notable — skip. Don't fabricate observations.

## Step 2 — Decision & knowledge scan

Reconcile pre-existing records with anything surfaced in reflection:

- **Decisions** made this session should already live in Supabase via `record_decision` (fires in real time). Go through the snapshot + conversation and check: every decision you can identify → is it in the list from Step 0?
  - If yes → do nothing. Don't re-save.
  - If no → save it now via `record_decision` (or `memory_store` type=decision) **and flag in Step 7 output**: "Decision X was not recorded in real time — consider why". Real-time capture is the goal; post-hoc saves are a regression.
- **User preferences** or profile updates → `user` memory (upsert existing, don't duplicate).
- **Project state** changes → `project` memory.
- **Feedback** given by owner → `feedback` memory.

Upsert existing memories, don't create duplicates. Check name before creating new.

## Step 3 — Goal progress log

If work this session advanced any active goal:

1. Call `goal_list(status="active")`
2. For each goal that was advanced, call `goal_update(slug=..., progress=[...])` — append new items as `{item: "<5-word summary> (YYYY-MM-DD)", done: true}`
3. Keep existing progress items unchanged. Only append new ones.

Keep items terse — "secret scanner + credential registry (2026-04-13)", not a sentence. Details live in git history.

Skip if the session didn't advance any goal (e.g., pure discussion, research without deliverables).

## Step 4 — Working state (non-negotiable)

Save `working_state_jarvis` (type=project) to Supabase. Always. Content:
- What was done this session
- Open items: unfinished work, things to fix, deferred tasks
- Key context for next session (blockers, decisions pending review)

This is the handoff to the next session. If open items exist in Step 7 output, they MUST be in this memory too — output is ephemeral, memory persists.

Only exception: truly empty session (user asked one question and left).

## Step 5 — Branch cleanup

Check for local branches whose remote tracking branch has been deleted:
```bash
git branch -vv | grep ': gone]' | awk '{print $1}'
```

If any found, for each branch:
1. Try `git branch -d <name>` (safe delete)
2. If it fails ("not fully merged") — this usually means the PR was squash-merged. Verify:
   ```bash
   gh pr list --head <branch> --state merged --json number --limit 1
   ```
3. If PR confirmed merged → `git branch -D <name>` (force delete is safe)
4. If no merged PR found → report in output, don't delete

Skip if none found.

## Step 6 — Commit (non-negotiable: leave nothing uncommitted)

Check ALL project repos for uncommitted changes (jarvis, redrobot, any other repo touched this session).

For each repo with changes:

1. `git status` and `git diff --stat`
2. Determine if changes are committable:
   - Complete work → commit
   - Mid-task, broken, merge conflicts → stash with descriptive message (`git stash push -m "session YYYY-MM-DD: <description>"`) and note in output
3. **Branch handling** (before committing):
   - On `main` → commit directly
   - On a feature branch **created/used for this session's work** → commit there
   - On an **unrelated branch** (pre-existing branch for different work) → relocate changes:
     ```bash
     git stash
     DEFAULT_BRANCH=$(git symbolic-ref refs/remotes/origin/HEAD | sed 's@^refs/remotes/origin/@@')
     git checkout $DEFAULT_BRANCH
     git pull --ff-only  # get latest, fail-safe
     git stash pop
     ```
     Then commit on the default branch. If stash pop has conflicts, resolve them (add our version). If pull fails, commit as-is (don't block on upstream).
4. Stage only session-related files. Standard commit format with Co-Authored-By.

**Goal: zero uncommitted changes across all repos after /end.**
If stashing (mid-task), report the stash ref and repo in output so next session can recover.

## Step 7 — Output

```
## Session closed — YYYY-MM-DD

### Journal source
- Snapshot: <session_snapshot_... name + "fresh" | "stale" | "none">
- Decisions loaded: N
- Post-hoc decision saves: N  (0 is ideal — every decision should have been recorded in real time)

### Reflection
- <1-3 behavioral observations, or "Clean session — no issues">

### Saved to memory (N)
- <name> — <one-line>

### Committed
- <hash + message, or "No commit — <reason>">

### What was done
- <bullets — draw from snapshot where applicable, not just post-compact conversation>

### Open items
- <unfinished work, deferred tasks, things for next session>
```

Keep it concise. This is a handoff, not a report.
