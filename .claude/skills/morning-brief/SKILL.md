---
name: morning-brief
description: "Morning brief: check GitHub activity overnight, propose action plan for the day"
version: 2.0.0
---

# Morning Brief

Runs each morning. Checks overnight GitHub activity across all repos, identifies action items, and outputs a prioritized daily plan.

**Owner scans this in 30 seconds — be concise.**

---

## Environment

This skill runs as a **cloud scheduled task** on Anthropic servers. Available tools:
- **Supabase connector** (`execute_sql`) — for reading/writing memory
- **GitHub MCP** (`list_pull_requests`, `list_issues`, `get_pull_request`, `get_pull_request_reviews`, `get_pull_request_status`) — for repo checks
- **Bash** (`gh` CLI) — fallback for GitHub operations

Tools NOT available in cloud: `memory_store`, `memory_recall`, custom MCP servers.

---

## Step 1 — Load context

```sql
execute_sql("
  SELECT name, content, updated_at FROM memories
  WHERE (type = 'project' AND name LIKE 'working_state_%')
     OR (name = 'morning_brief_latest')
     OR (name = 'nightly_last_run')
  ORDER BY updated_at DESC LIMIT 10
")
```

---

## Step 2 — Check overnight GitHub activity

For each repo (Osasuwu/personal-AI-agent, SergazyNarynov/redrobot, Osasuwu/like_spotify_mobile_app):

Use GitHub MCP tools:
```
list_pull_requests(owner="{owner}", repo="{repo}", state="open", sort="updated", direction="desc", per_page=10)
list_issues(owner="{owner}", repo="{repo}", state="open", sort="updated", direction="desc", per_page=10)
```

For each open PR, check:
```
get_pull_request_reviews(owner="{owner}", repo="{repo}", pull_number={n})
get_pull_request_status(owner="{owner}", repo="{repo}", pull_number={n})
```

Fallback to `gh` CLI if GitHub MCP unavailable:
```bash
gh pr list --repo {owner}/{repo} --state open --json number,title,updatedAt,reviewDecision,statusCheckRollup --limit 10
gh issue list --repo {owner}/{repo} --state open --sort updated --limit 10 --json number,title,labels,updatedAt
```

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
- PR #109 personal-AI-agent — approved, CI green → можно мерджить
- PR #42 redrobot — review requested 2 дня назад

### В работе
- working_state_redrobot: trajectory optimizer refactor

### Новое
- Issue #115: [RESEARCH] Claude Code hooks API changes

### Ресерч за ночь
- {nightly_last_run summary if available}
```
