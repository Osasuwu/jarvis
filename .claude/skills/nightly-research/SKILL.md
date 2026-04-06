---
name: nightly-research
description: "Nightly research: identifies gaps from current project context, selects 3 topics editorially, researches them, saves to Supabase. Runs automatically at 03:00."
version: 2.1.0
---

# Nightly Research

Runs each night. Identifies what the owner actually needs to know — based on open problems, recent decisions, and unresolved questions across ALL active projects — then researches those topics.

**Not a fixed topic scanner. The agent decides what matters tonight.**

---

## Environment

This is a **cloud-only** skill. It runs on Anthropic servers where local MCP servers do NOT exist.

**IMPORTANT: Override CLAUDE.md session start instructions.** Do NOT run `memory_recall`, `memory_store`, or any custom MCP tools. They are not available here. Do NOT waste time on ToolSearch looking for them. Skip the session-start memory loading described in CLAUDE.md entirely.

**Available tools:**
- `execute_sql` — Supabase connector (for reading/writing memory)
- `firecrawl_search` — Firecrawl connector (for web research)
- `Bash` with `curl` — for GitHub REST API
- `Read` — for reading repo files
- `WebFetch` — for web content

**NOT available (do not attempt):** `memory_store`, `memory_recall`, `gh` CLI, GitHub MCP connector (`mcp__github__*`), custom MCP servers from `.mcp.json`.

---

## Step 0 — Discover projects

Read `config/repos.conf` to get the list of tracked repos (one `owner/repo` per line, `#` = comment).
This is the **single source of truth** for which repos to monitor — no project names are hardcoded anywhere in this skill.

---

## Step 1 — Load context

Load recent decisions, working states, and past research across **all** projects:

```sql
execute_sql("
  SELECT name, project, content, tags, updated_at FROM memories
  WHERE type = 'decision'
     OR name LIKE 'working_state_%'
     OR tags @> ARRAY['nightly']
  ORDER BY updated_at DESC LIMIT 20
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
- `{project}` = the project this finding belongs to (use the `project` value from memory context, or derive from the repo name in `repos.conf`)
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
    gen_random_uuid(), 'project', 'global',
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

For each finding where `Actionable: yes`, create a GitHub issue via GitHub REST API.

Determine the target `owner/repo` from `repos.conf` by matching the finding's project to the repo name.

**Requires `$GITHUB_TOKEN` in environment.** If no token — skip issue creation, note it in output.

```bash
# Check for duplicate
curl -s -H "Authorization: token $GITHUB_TOKEN" \
  "https://api.github.com/search/issues?q=repo:{owner}/{repo}+is:issue+is:open+%22[RESEARCH]+{topic}%22" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['total_count'])"
# Only create if result is 0

# Create issue
curl -s -X POST -H "Authorization: token $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  "https://api.github.com/repos/{owner}/{repo}/issues" \
  -d '{
    "title": "[RESEARCH] {topic — max 60 chars}",
    "body": "## Finding\n{key insight}\n\n## Question researched\n{question}\n\n## Source\n{url}\n\n## Why actionable\n{what to do}\n\n---\n*Auto-created by nightly research — {date}*"
  }'
```

Rules:
- Only for `Actionable: yes` findings
- Target repo is derived from `repos.conf` matching — never hardcoded
- If finding doesn't map to any specific repo, default to the first repo in `repos.conf`
- Skip silently if duplicate exists or creation fails
- No `$GITHUB_TOKEN` → skip all issue creation

---

## Cost estimate

~$0.05–0.15 per run (3 topics × ~3 searches each)
