---
name: nightly-research
description: "Nightly research: identifies gaps from current project context, selects 3 topics editorially, researches them, saves to Supabase. Runs as a local scheduled task."
version: 3.0.0
---

# Nightly Research

Runs each morning as a local scheduled task. Identifies what the owner actually needs to know — based on open problems, recent decisions, and unresolved questions across ALL active projects — then researches those topics.

**Not a fixed topic scanner. The agent decides what matters today.**

---

## Environment

This is a **local** skill. It runs on the owner's machine with full MCP access.

Use standard tools: `memory_recall`, `memory_store`, `mcp__github__*`, `WebSearch`, `Read`.

---

## Step 0 — Deduplication check

This skill may fire on multiple devices. Check Supabase before doing any work:

```
memory_recall(query="nightly_last_run", type="project", limit=1)
```

Parse the **first line** of `nightly_last_run` content — it starts with a date like `2026-04-08 — topics: ...`. Extract that date.

If the extracted date matches **today** (local calendar date) → output "Nightly research already ran today — skipping." and **stop**.

If not found, date parse fails, or last run was yesterday or earlier → proceed.

**Important:** Do NOT use `updated_at` for dedup — memory records can be touched by migrations without content changes.

---

## Step 1 — Discover projects

Read `config/repos.conf` to get the list of tracked repos (one `owner/repo` per line, `#` = comment).
This is the **single source of truth** — no repo names are hardcoded anywhere in this skill.

---

## Step 2 — Load context

Run in parallel:
```
memory_recall(type="decision", limit=10)
memory_recall(query="working_state", type="project", limit=5)
memory_recall(type="feedback", limit=5)
memory_recall(query="nightly", type="reference", limit=5)
```

Also check recent GitHub activity for each repo:
```
mcp__github__list_issues(owner, repo, state="OPEN", orderBy="UPDATED_AT", direction="DESC", perPage=10)
```

---

## Step 3 — Gap identification

From the loaded context, find **genuine gaps** — things the owner needs to know but doesn't yet:

Look for:
- Problems flagged as unsolved in working state (e.g. "planner stagnates — investigate")
- Decisions made without sufficient research ("we'll figure this out later")
- Patterns that keep breaking (from feedback memories)
- Capabilities the owner mentioned wanting but hasn't explored
- Research findings from previous runs not yet acted on

**Score each gap**: impact (how much does knowing this help?) x urgency (is someone blocked on it?).

Pick **top 3**. Each gap becomes a specific research question — not a broad scan.

Bad: "research AI agents"
Good: "how do people tune convergence thresholds in iterative planners to avoid premature stagnation?"

---

## Step 4 — Fallback (if no gaps found)

Read `config/research-topics.yaml` for hint labels.
Pick 3 and formulate specific research questions based on current context — don't just scan the category generically.

---

## Step 5 — Research each topic

For each of the 3 topics, use `WebSearch`:

```
WebSearch(query="<specific question>")
```

Rules:
- Max 3 searches per topic
- Skip SEO content, tutorials, outdated articles (>1 year for fast-moving topics)
- Prioritize: GitHub, HN, official docs, reputable tech blogs
- Extract only what's actionable or genuinely novel

---

## Step 6 — Save results

For each topic, save to Supabase memory:
```
memory_store(
  type="reference",
  name="nightly_{topic_slug}",
  project="{project}",
  description="Nightly research: {topic label}",
  content="{formatted_content}",
  tags=["nightly", "research"]
)
```

Where:
- `{project}` = the project this finding belongs to (derived from repos.conf)
- `{topic_slug}` = short snake_case id, e.g. `planner_convergence`

Content format:
```
## {topic}

**Question:** {the specific question researched}
**Finding:** {key insight, max 200 words}
**Actionable:** {yes/no — what to do with this}
**Source:** {url}
```

Save run summary:
```
memory_store(
  type="project",
  name="nightly_last_run",
  project="global",
  description="Last nightly research run",
  content="{date} — topics: {t1}, {t2}, {t3} — actionable={n}",
  tags=["nightly"]
)
```

---

## Step 7 — Create GitHub issues for actionable findings

For each finding where `Actionable: yes`, create a GitHub issue.

Determine the target `owner/repo` from `repos.conf` by matching the finding's project to the repo name.

```
# Check for duplicate first
mcp__github__search_issues(query="[RESEARCH] {topic}", owner="{owner}", repo="{repo}")

# Only create if no duplicate
mcp__github__issue_write(
  method="create",
  owner="{owner}",
  repo="{repo}",
  title="[RESEARCH] {topic — max 60 chars}",
  body="## Finding\n{key insight}\n\n## Question researched\n{question}\n\n## Source\n{url}\n\n## Why actionable\n{what to do}\n\n---\n*Auto-created by nightly research — {date}*",
  labels=["research"]
)
```

Rules:
- Only for `Actionable: yes` findings
- Skip silently if duplicate exists or creation fails
- Target repo derived from repos.conf — never hardcoded

---

## Cost estimate

~$0.05–0.10 per run (WebSearch + memory operations)
