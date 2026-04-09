---
name: memory-manager
description: "Browse, manage, and maintain memory health. Use when: 'память', 'memory', 'покажи что помнишь', 'memory health', 'stale memories', 'cleanup', 'что ты помнишь про X', '/memory'."
version: 1.0.0
---

# Memory Manager

Browse, audit, and maintain Jarvis's memory system. Adds structured retrieval tiers and staleness detection on top of Supabase.

## Usage

- `/memory` — health overview: count by type, staleness report, recent activity
- `/memory browse [type]` — list all memories, optionally filtered by type
- `/memory search <query>` — semantic search across all memories
- `/memory stale` — find memories older than 14 days that haven't been validated
- `/memory cleanup` — interactive cleanup of stale/orphaned working states
- `/memory stats` — count by type, project, tag distribution
- `/memory graph` — link graph overview: stats, top connected, orphans
- `/memory links <name>` — all connections for a specific memory
- `/memory clusters` — tightly connected memory groups (consolidation candidates)

## Memory Tiers

Jarvis uses four conceptual tiers mapped onto Supabase memory types:

| Tier | Purpose | Supabase types | TTL guidance |
|------|---------|---------------|--------------|
| **Working** | Current task context, checkpoints | `project` with name `working_state_*` | Delete when task done. Flag if >3 days old |
| **Episodic** | Session summaries, what happened | `project` with tag `session` or `episode` | Keep 30 days, then compress or delete |
| **Semantic** | Facts, preferences, decisions | `user`, `decision`, `feedback` | Permanent, but review if >30 days without access |
| **Procedural** | How-to knowledge, learned workflows | `feedback` with tag `procedural` | Permanent, update when workflow changes |
| **Reference** | External pointers, research | `reference` | Review if >60 days old |

## Step 1 — Load all memories

First discover all projects:
```
memory_recall(query="*", type="project", limit=50)
```
Or via SQL: `SELECT DISTINCT project FROM memories WHERE project IS NOT NULL ORDER BY project`

Then load memories across all discovered projects.

## Step 2 — Classify and report

For `/memory` (health overview):

```markdown
# Memory Health — YYYY-MM-DD

## Stats
- Total: N memories
- By type: user(N) | project(N) | decision(N) | feedback(N) | reference(N)
- By project: <dynamically list all projects with counts>

## Working Memory (active checkpoints)
- <name> — <description> (age: N days) [OK / STALE]

## Staleness Alerts
- ⚠️ <name> — last updated N days ago, type: <type>
- ...

## Recent Activity (last 7 days)
- <name> — created/updated YYYY-MM-DD
```

## Step 3 — Staleness detection

A memory is **stale** if:
- Working state (`working_state_*`): >3 days old
- Episodic (tag `session`/`episode`): >30 days old
- Reference with tag `intel`/`research`: >60 days old
- Any memory: >90 days without update

For stale memories, recommend:
- Working states → delete (task is likely done or abandoned)
- Episodic → compress into a decision or delete
- References → verify link still works, delete if outdated
- Decisions → re-validate (is this still true?)

## Step 4 — Cleanup (interactive)

For `/memory cleanup`:
1. List all stale memories with staleness reason
2. For each, suggest: **keep** / **update** / **delete**
3. Wait for owner confirmation before any deletes
4. Execute approved changes via `memory_delete` or `memory_store` (update)

**Never auto-delete without confirmation.**

## Step 5 — Session end integration

At session end (when `/end` runs), automatically:
1. Check for orphaned working states (>3 days)
2. If session produced decisions/learnings not yet saved → prompt to save
3. One-line staleness summary if any alerts

This step is advisory — include it in `/end` output, don't block on it.

## Structured Retrieval Patterns

When other skills need memory, use these patterns instead of generic recall:

```python
# Get active context (working tier)
memory_recall(query="working_state", type="project", limit=3)

# Get owner profile (semantic tier)
memory_recall(type="user", limit=3)

# Get behavioral rules (procedural tier)
memory_recall(type="feedback", limit=5)

# Get recent decisions — scope to active project if known
memory_recall(type="decision", project="<current_project>", limit=5)

# Get research pointers (reference tier)
memory_recall(type="reference", limit=5)
```

## Graph Exploration (Memory 2.0)

Memory 2.0 auto-links memories on store via semantic similarity. Use the `memory_graph` MCP tool to explore the link graph.

**`/memory graph`** — overview:
```
memory_graph(mode="overview")
```
Shows: link stats by type (related/supersedes/consolidates), top-10 most connected memories, orphans (embedded but unlinked).

**`/memory links <name>`** — per-memory connections:
```
memory_graph(mode="links", name="<memory_name>")
```
Shows: all outgoing (→) and incoming (←) links with type and strength.

**`/memory clusters`** — find consolidation candidates:
```
memory_graph(mode="clusters")
```
Shows: groups of tightly connected memories (strength >= 0.7). These are candidates for consolidation — merging related memories into one.

## Naming Conventions (enforced)

| Tier | Name pattern | Example |
|------|-------------|---------|
| Working | `working_state_<project>` | `working_state_redrobot` |
| Episodic | `session_<date>_<slug>` | `session_2026_04_02_auth_refactor` |
| Decision | `<topic>_<slug>` | `instructions_overhaul_2026_04_01` |
| Feedback | `feedback_<slug>` | `feedback_no_trailing_summaries` |
| Reference | `<source>_<slug>` | `intel_claude_computer_use` |
| Procedural | `procedure_<slug>` | `procedure_pr_review_workflow` |

## Cost estimate

~$0.01–0.03 per run (memory_list + memory_recall calls, minimal LLM)
