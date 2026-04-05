---
name: nightly-research
description: "Nightly research: identifies gaps from current project context, selects 3 topics editorially, researches them, saves to Supabase. Runs automatically at 03:00."
version: 1.0.0
---

# Nightly Research

Runs each night. Identifies what Jarvis/redrobot actually needs to know — based on open problems, recent decisions, and unresolved questions — then researches those topics.

**Not a fixed topic scanner. The agent decides what matters tonight.**

---

## Step 0 — Detect environment

Check which persistence tools are available. This determines how you save results in Step 5.

- If `memory_store` tool exists → use it (preferred, local MCP)
- If only `execute_sql` exists → use SQL fallback (remote/cloud environment)
- **NEVER write results to markdown files** — they don't sync across devices

Also check which search tools are available: `firecrawl_search` > `WebSearch` > skip.

---

## Step 1 — Load context

If `memory_recall` is available:
- `memory_recall(type="decision", project="jarvis", limit=5)` — recent jarvis decisions
- `memory_recall(type="decision", project="redrobot", limit=5)` — recent redrobot decisions
- `memory_recall(query="working state", limit=3)` — open checkpoints
- `memory_recall(query="nightly research", limit=3)` — what was already researched (avoid repeats)

If only `execute_sql` is available:
```sql
SELECT name, content, tags, updated_at FROM memories
WHERE (type = 'decision' AND project IN ('jarvis', 'redrobot'))
   OR (name LIKE 'working_state_%')
   OR (tags @> ARRAY['nightly'])
ORDER BY updated_at DESC LIMIT 15;
```

---

## Step 2 — Gap identification

Read the loaded context and find **genuine gaps** — things the owner needs to know but doesn't yet:

Look for:
- Problems flagged as unsolved in working state (e.g. "planner stagnates — investigate")
- Decisions made without sufficient research ("we'll figure this out later")
- Patterns that keep breaking (from feedback memories)
- Capabilities the owner mentioned wanting but hasn't explored
- Research findings from previous nights not yet acted on

**Score each gap**: impact (how much does knowing this help?) × urgency (is someone blocked on it?).

Pick **top 3**. Each gap becomes a specific research question — not a broad scan.

Bad: "research AI agents"
Good: "how do people tune convergence thresholds in iterative planners to avoid premature stagnation?"

---

## Step 3 — Fallback (if no gaps found)

Read `config/research-topics.yaml` for hint labels.
Pick 3 and formulate specific research questions based on current context — don't just scan the category generically.

---

## Step 4 — Research each topic

For each of the 3 topics, run a targeted search using the research skill pattern:

```
firecrawl_search(query="<specific question>", limit=3)
```

Or fallback to `WebSearch` if Firecrawl unavailable.

Rules:
- Max 3 searches per topic
- Skip SEO content, tutorials, outdated articles (>1 year for fast-moving topics)
- Prioritize: GitHub, HN, official docs, reputable tech blogs
- Extract only what's actionable or genuinely novel

---

## Step 5 — Save results

For each topic, upsert to Supabase. Use a **deterministic name** derived from the topic slug so the same topic always overwrites its previous entry (no accumulation).

Use `project="redrobot"` when the finding is about redrobot (MuJoCo, planning, trajectory, etc.) so project-scoped recall returns it correctly.

### Option A: `memory_store` available (local sessions)

```
memory_store(
  type="reference",
  name="nightly_{topic_slug}",
  project="jarvis",              # or "redrobot"
  description="Nightly research: {topic label}",
  content="## {topic}\n\n**Question:** ...\n**Finding:** ...\n**Actionable:** ...\n**Source:** {url}",
  tags=["nightly", "research"]
)
```

Run summary:
```
memory_store(
  type="project", name="nightly_last_run", project="jarvis",
  description="Last nightly research run",
  content="{date} — topics: {t1}, {t2}, {t3} — actionable={n}"
)
```

### Option B: `execute_sql` only (remote/cloud sessions)

```sql
INSERT INTO memories (id, type, project, name, description, content, tags, created_at, updated_at)
VALUES (
  gen_random_uuid(), 'reference', 'jarvis',
  'nightly_{topic_slug}',
  'Nightly research: {topic label}',
  E'## {topic}\n\n**Question:** ...\n**Finding:** ...\n**Actionable:** ...\n**Source:** {url}',
  ARRAY['nightly', 'research'],
  now(), now()
)
ON CONFLICT (project, name) DO UPDATE SET
  content = EXCLUDED.content,
  description = EXCLUDED.description,
  tags = EXCLUDED.tags,
  project = EXCLUDED.project,
  updated_at = now();
```

Run summary — same pattern with `name='nightly_last_run'`, `type='project'`.

**CRITICAL:** Never fall back to writing markdown files to the repo. If neither `memory_store` nor `execute_sql` is available, log a warning and skip saving (the research is still in the session transcript).

---

## Step 6 — Create GitHub issues for actionable findings

For each finding where `Actionable: yes`, create a GitHub issue so it surfaces in the board and gets triaged:

```bash
# Check for duplicate first
gh issue list --repo Osasuwu/personal-AI-agent \
  --search "[RESEARCH] {topic}" --state open --limit 1000 --json number --jq length
# Only create if result is 0

gh issue create \
  --repo Osasuwu/personal-AI-agent \
  --title "[RESEARCH] {topic — max 60 chars}" \
  --body "## Finding\n{key insight}\n\n## Question researched\n{specific question}\n\n## Source\n{url}\n\n## Why actionable\n{what to do with this — 1-2 sentences}\n\n---\n*Auto-created by nightly research — {date}*"
```

Rules:
- Only for `Actionable: yes` findings
- For redrobot findings: use `--repo Osasuwu/redrobot` instead
- Skip silently if `gh` fails or duplicate exists; log skipped count to run summary

---

## Step 7 — Surface in next session

At session start, `memory_recall(query="nightly research")` will surface these.
If findings are highly actionable (e.g. directly related to open working state), flag them proactively.

---

## Cost estimate

~$0.05–0.15 per run (3 topics × ~3 searches each, Haiku where possible)
