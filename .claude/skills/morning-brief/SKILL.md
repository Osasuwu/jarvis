---
name: morning-brief
description: "Morning brief: check GitHub activity overnight, propose action plan for the day"
version: 3.0.0
---

# Morning Brief

Runs each morning. Checks overnight GitHub activity across all tracked repos, identifies action items, and outputs a prioritized daily plan.

**Owner scans this in 30 seconds — be concise.**

---

## Environment

This is a **cloud-only** skill. It runs on Anthropic servers where local MCP servers do NOT exist.

**IMPORTANT: Override CLAUDE.md session start instructions.** Do NOT run `memory_recall`, `memory_store`, or any custom MCP tools. They are not available here. Do NOT waste time on ToolSearch looking for them. Skip the session-start memory loading described in CLAUDE.md entirely.

**Available tools:**
- `execute_sql` — Supabase connector (for reading/writing memory)
- `Bash` with `curl` — for GitHub REST API
- `Read` — for reading repo files
- `WebFetch` — for web content

**NOT available (do not attempt):** `memory_store`, `memory_recall`, `gh` CLI, GitHub MCP connector (`mcp__github__*`), custom MCP servers from `.mcp.json`.

---

## Step 0 — Discover repos

Read `config/repos.conf` to get the list of tracked repos (one `owner/repo` per line, `#` = comment).
This is the **single source of truth** — no repo names are hardcoded anywhere in this skill.

---

## Step 1 — Load context

```sql
execute_sql("
  SELECT name, project, content, updated_at FROM memories
  WHERE name LIKE 'working_state_%'
     OR name = 'morning_brief_latest'
     OR name = 'nightly_last_run'
  ORDER BY updated_at DESC LIMIT 10
")
```

---

## Step 2 — Check overnight GitHub activity

For **each repo from Step 0**, fetch open PRs and issues via GitHub REST API using `curl`:

```bash
# Open PRs (sorted by last update)
curl -s "https://api.github.com/repos/{owner}/{repo}/pulls?state=open&sort=updated&direction=desc&per_page=10"

# Open issues (sorted by last update)
curl -s "https://api.github.com/repos/{owner}/{repo}/issues?state=open&sort=updated&direction=desc&per_page=10"
```

For PRs with recent activity, get review status:
```bash
curl -s "https://api.github.com/repos/{owner}/{repo}/pulls/{number}/reviews"
```

**Authentication:** If `$GITHUB_TOKEN` is set in the environment, add `-H "Authorization: token $GITHUB_TOKEN"` to all curl commands. This enables access to private repos and higher rate limits.

**Private repos without token:** Skip with a note "приватный репо, нет токена — пропускаю".

**Rate limits:** Unauthenticated API allows 60 requests/hour. With 3 repos and ~3 calls each, this is sufficient.

---

## Step 3 — Identify action items

Categorize into:
- **Needs response** — PR reviews waiting for reply, issues with questions
- **Ready to merge** — PRs with approved reviews and passing CI
- **Blocked** — PRs with failing CI or requested changes
- **New work** — recently created/updated issues not yet claimed

---

## Step 4 — Draft daily plan

Create a concise prioritized list:
1. Urgent: respond to reviews, fix broken CI
2. Continue: in-progress work from checkpoints
3. New: highest-priority unclaimed issues
4. Proactive: improvements identified from context

---

## Step 5 — Save and output

Save brief to Supabase:
```sql
execute_sql("
  INSERT INTO memories (id, type, project, name, description, content, tags, created_at, updated_at)
  VALUES (
    gen_random_uuid(), 'project', 'global',
    'morning_brief_latest',
    'Latest morning brief',
    '{escaped_brief_content}',
    ARRAY['morning', 'brief'],
    now(), now()
  )
  ON CONFLICT (project, name) DO UPDATE SET
    content = EXCLUDED.content,
    updated_at = now()
")
```

Output the brief in Russian. Format as a clean dashboard — not a report. Owner should scan it in 30 seconds.

Example format:
```
## Утренний брифинг — {date}

### Требует внимания
- PR #109 jarvis — approved, CI green → можно мерджить
- PR #42 redrobot — review requested 2 дня назад

### В работе
- working_state_redrobot: trajectory optimizer refactor

### Новое
- Issue #115: [RESEARCH] Claude Code hooks API changes

### Ресерч за ночь
- {nightly_last_run summary if available}
```
