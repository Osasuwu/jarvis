---
name: nightly-research
description: "Nightly research: identifies gaps from current project context, selects 3 topics editorially, researches them, saves to Supabase. Runs automatically at 03:00."
version: 1.0.0
---

# Nightly Research

Runs each night. Identifies what Jarvis/redrobot actually needs to know — based on open problems, recent decisions, and unresolved questions — then researches those topics.

**Not a fixed topic scanner. The agent decides what matters tonight.**

---

## Step 1 — Load context

Call in parallel:
- `memory_recall(type="decision", project="jarvis", limit=5)` — recent jarvis decisions
- `memory_recall(type="decision", project="redrobot", limit=5)` — recent redrobot decisions
- `memory_recall(query="working state", limit=3)` — open checkpoints
- `memory_recall(query="nightly research", limit=3)` — what was already researched (avoid repeats)

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

Read `personal-AI-agent/config/research-topics.yaml` for hint labels.
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

For each topic, upsert to Supabase (fixed name = no accumulation):

```
memory_store(
  type="reference",
  name="nightly_{id}",
  project="jarvis",
  description="Nightly research: {topic label}",
  content="## {topic}

**Question:** {the specific question researched}
**Finding:** {key insight, max 200 words}
**Actionable:** {yes/no — what to do with this}
**Source:** {url}",
  tags=["nightly", "research"]
)
```

Also upsert a run summary:
```
memory_store(
  type="project",
  name="nightly_last_run",
  project="jarvis",
  description="Last nightly research run",
  content="{date} — topics: {topic1}, {topic2}, {topic3} — {N} actionable findings"
)
```

---

## Step 6 — Create GitHub issues for actionable findings

For each finding where `Actionable: yes`, create a GitHub issue so it surfaces in the board and gets triaged:

```bash
# Check for duplicate first
gh issue list --repo Osasuwu/personal-AI-agent \
  --search "[RESEARCH] {topic}" --state open --json number --jq length
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
