---
name: morning-brief
description: "Morning brief: check GitHub activity overnight, propose action plan for the day"
version: 4.0.0
---

# Morning Brief

Runs each morning locally. Checks overnight GitHub activity across all tracked repos, identifies action items, and outputs a prioritized daily plan.

**Owner scans this in 30 seconds — be concise.**

---

## Environment

This is a **local** skill. It runs on the owner's machine with full MCP access.

Use standard tools: `memory_recall`, `memory_store`, `mcp__github__*`, `Read`, `Bash`.

---

## Step 0 — Discover repos

Read `config/repos.conf` to get the list of tracked repos (one `owner/repo` per line, `#` = comment).
This is the **single source of truth** — no repo names are hardcoded anywhere in this skill.

---

## Step 1 — Load context

Run in parallel:
```
memory_recall(query="working_state", type="project", limit=5)
memory_recall(query="morning_brief_latest", type="project", limit=1)
memory_recall(query="nightly_last_run", type="project", limit=1)
memory_recall(query="risk_radar_latest", type="project", limit=1)
goal_list(status="active")
```

---

## Step 2 — Check overnight GitHub activity

For **each repo from Step 0**, use GitHub MCP tools:

```
mcp__github__list_pull_requests(owner, repo, state="open", sort="updated", direction="desc", perPage=10)
mcp__github__list_issues(owner, repo, state="OPEN", orderBy="UPDATED_AT", direction="DESC", perPage=10)
```

For PRs with recent activity (updated in last 24h), check reviews:
```
mcp__github__pull_request_read(method="get_reviews", owner, repo, pullNumber)
mcp__github__pull_request_read(method="get_check_runs", owner, repo, pullNumber)
```

**Parallelize:** fetch all repos' PRs and issues in parallel. Then fetch reviews for active PRs in parallel.

---

## Step 3 — Identify action items

Categorize into:
- **Needs response** — PR reviews waiting for reply, issues with questions
- **Ready to merge** — PRs with approved reviews and passing CI
- **Blocked** — PRs with failing CI or requested changes
- **New work** — recently created/updated issues not yet claimed

---

## Step 3.5 — Goal health check

For each active goal from Step 1:
- **Deadline alert**: if deadline is within 3 days → flag as urgent
- **Stale progress**: if no progress update in goal data for >7 days → flag
- **P0 neglect**: if P0 goal exists but no related work in overnight activity → flag

Include any flags in the output under "Goal alerts".

## Step 4 — Draft daily plan

Create a concise prioritized list:
1. Urgent: respond to reviews, fix broken CI, **goal deadline alerts**
2. Continue: in-progress work from checkpoints
3. New: highest-priority unclaimed issues (aligned with active goals)
4. Proactive: improvements identified from context

---

## Step 5 — Save and output

Save brief to Supabase memory:
```
memory_store(
  type="project",
  name="morning_brief_latest",
  project="global",
  description="Latest morning brief",
  content="{brief_content}",
  tags=["morning", "brief"]
)
```

Output the brief in Russian. Format as a clean dashboard — not a report. Owner should scan it in 30 seconds.

Example format:
```
## Утренний брифинг — {date}

### Цели
- P0 redrobot-apr13-workshop — дедлайн через 3 дня!
- P1 autonomous-loop — прогресс 30%, обновлений за 7 дней нет

### Риски (из risk-radar)
- [HIGH] CI Instability: redrobot failure rate 40%

### Требует внимания
- PR #109 jarvis — approved, CI green -> можно мерджить
- PR #42 redrobot — review requested 2 дня назад

### В работе
- working_state_redrobot: trajectory optimizer refactor

### Новое
- Issue #115: [RESEARCH] Claude Code hooks API changes

### Ресерч за ночь
- {nightly_last_run summary if available}
```
