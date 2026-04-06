---
name: nightly-research
description: "Nightly research: identifies gaps from current project context, selects 3 topics editorially, researches them, saves to Supabase. Runs automatically at 03:00."
version: 2.0.0
---

# Nightly Research

Runs each night. Identifies what Jarvis/redrobot actually needs to know — based on open problems, recent decisions, and unresolved questions — then researches those topics.

**Not a fixed topic scanner. The agent decides what matters tonight.**

---

## Environment

This skill runs as a **cloud scheduled task** on Anthropic servers. Available tools:
- **Supabase connector** (`execute_sql`) — for reading/writing memory
- **Firecrawl connector** (`firecrawl_search`) — for web research
- **GitHub MCP** (`search_issues`, `create_issue`, `list_issues`) — for issue management
- **Bash** (`gh` CLI) — fallback for GitHub operations

Tools NOT available in cloud: `memory_store`, `memory_recall`, custom MCP servers.

---

## Step 1 — Load context

```sql
execute_sql("
  SELECT name, project, content, tags, updated_at FROM memories
  WHERE (type = 'decision' AND project IN ('jarvis', 'redrobot'))
     OR (name LIKE 'working_state_%')
     OR (tags @> ARRAY['nightly'])
  ORDER BY updated_at DESC LIMIT 15
")
```

Also load recent feedback to understand pain points:
```sql
execute_sql("
  SELECT name, content FROM memories
  WHERE type = 'feedback' AND updated_at > now() - interval '14 days'
  ORDER BY updated_at DESC LIMIT 5
")
```

---

## Step 2 — Gap identification

From the loaded context, find **genuine gaps** — things the owner needs to know but doesn't yet:

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

For each of the 3 topics:

```
firecrawl_search(query="<specific question>", limit=3)
```

Rules:
- Max 3 searches per topic
- Skip SEO content, tutorials, outdated articles (>1 year for fast-moving topics)
- Prioritize: GitHub, HN, official docs, reputable tech blogs
- Extract only what's actionable or genuinely novel

---

## Step 5 — Save results to Supabase

For each topic, upsert via `execute_sql`. Use a **deterministic name** so the same topic always overwrites its previous entry:

```sql
execute_sql("
  INSERT INTO memories (id, type, project, name, description, content, tags, created_at, updated_at)
  VALUES (
    gen_random_uuid(), 'reference', '{project}',
    'nightly_{topic_slug}',
    'Nightly research: {topic label}',
    '{escaped_content}',
    ARRAY['nightly', 'research'],
    now(), now()
  )
  ON CONFLICT (project, name) DO UPDATE SET
    content = EXCLUDED.content,
    description = EXCLUDED.description,
    tags = EXCLUDED.tags,
    updated_at = now()
")
```

Where:
- `{project}` = `'jarvis'` or `'redrobot'` depending on topic
- `{topic_slug}` = short snake_case id, e.g. `planner_convergence`
- `{escaped_content}` = content with single quotes doubled (`'` → `''`)

Content format:
```
## {topic}

**Question:** {the specific question researched}
**Finding:** {key insight, max 200 words}
**Actionable:** {yes/no — what to do with this}
**Source:** {url}
```

Run summary:
```sql
execute_sql("
  INSERT INTO memories (id, type, project, name, description, content, tags, created_at, updated_at)
  VALUES (
    gen_random_uuid(), 'project', 'jarvis',
    'nightly_last_run',
    'Last nightly research run',
    '{date} — topics: {t1}, {t2}, {t3} — actionable={n}',
    ARRAY['nightly'],
    now(), now()
  )
  ON CONFLICT (project, name) DO UPDATE SET
    content = EXCLUDED.content,
    updated_at = now()
")
```

**CRITICAL:** Never fall back to writing markdown files. If `execute_sql` fails, log the error and continue — the research is still in the session transcript.

---

## Step 6 — Create GitHub issues for actionable findings

For each finding where `Actionable: yes`, create a GitHub issue.

Use GitHub MCP tools if available:
```
# Check for duplicate
list_issues(owner="Osasuwu", repo="personal-AI-agent", state="open")
# Filter results for "[RESEARCH] {topic}" in title

# If no duplicate:
create_issue(
  owner="Osasuwu",
  repo="{personal-AI-agent or redrobot}",
  title="[RESEARCH] {topic — max 60 chars}",
  body="## Finding\n{key insight}\n\n## Question researched\n{question}\n\n## Source\n{url}\n\n## Why actionable\n{what to do}\n\n---\n*Auto-created by nightly research — {date}*"
)
```

Fallback to `gh` CLI if GitHub MCP unavailable:
```bash
gh issue list --repo Osasuwu/personal-AI-agent \
  --search "[RESEARCH] {topic}" --state open --json number --jq length
# Only create if result is 0

gh issue create \
  --repo Osasuwu/personal-AI-agent \
  --title "[RESEARCH] {topic}" \
  --body "..."
```

Rules:
- Only for `Actionable: yes` findings
- For redrobot findings: use repo `Osasuwu/redrobot`
- Skip silently if duplicate exists or creation fails

---

## Cost estimate

~$0.05–0.15 per run (3 topics × ~3 searches each)
