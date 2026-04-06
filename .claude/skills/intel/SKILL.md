---
name: intel
description: "Tech intelligence digest — scans for new Claude/MCP/AI agent developments relevant to the owner, filters by novelty, rates actionability"
---

# Intel Digest

Weekly tech intelligence scan. Finds what's new and relevant — Claude updates, MCP ecosystem, AI agent tools — and surfaces only high-signal, genuinely novel information.

## Usage

- `/intel` — full scan, save findings to memory
- `/intel --quick` — top 3 items only, no memory save
- `/intel <topic>` — focus scan on a specific area
- `/intel --week` — recap past 7 days from memory (no new searches)

## Owner profile (for relevance filtering)

Solo developer building a personal AI agent on Claude Code + MCP. Prioritize:
- **Claude Code** — new features, releases, hooks, channels
- **MCP protocol** — new servers, ecosystem tools, integrations
- **AI agent architecture** — autonomy, self-improvement, memory, orchestration
- **Open source alternatives** — tools that could replace/augment parts of the system
- **Cost optimization** — cheaper models, routing, caching
- **Claude API** — pricing, capabilities, model updates

Skip: general hype, marketing, beginner tutorials, anything >2 weeks old unless major.

## Step 0 — Recap mode (`--week`)

If `--week`: skip web searches. Load from memory:
- `memory_recall(query="nightly research", limit=10)`
- `memory_recall(query="intel digest", limit=10)`

Filter to last 7 days, group by theme, output summary. Then STOP.

## Step 1 — Check existing knowledge

`memory_recall(query="intel digest")` — don't re-surface what's already known.

## Step 2 — Search

Run 4-6 targeted searches via `firecrawl_search` or `WebSearch`:
- Claude Code new features / changelog (past 2 weeks)
- MCP model context protocol new servers tools
- AI agent orchestration architecture tools
- Anthropic news releases

## Step 3 — Filter by novelty and relevance

For each finding, score: Novel? Relevant? Actionable? Drop low-signal items.

## Step 4 — Format output

```markdown
# Intel Digest — YYYY-MM-DD

## High Signal
### [Title]
**What:** one sentence
**Why it matters:** how it affects the owner's work
**Action:** what to try/check/update (or "monitor")
**Source:** [link]

## Medium Signal
- **[Title]** — brief note. [link]

## Summary
N new items. Top action: ...
```

## Step 5 — Save to memory

For each High Signal item:
```
memory_store(
  type="reference", name="intel_<slug>_<date>",
  description="<one-line>",
  content="<what + why + action + source>",
  tags=["intel", "digest"]
)
```

Digest summary:
```
memory_store(
  type="project", name="intel_last_run", project="jarvis",
  content="<date> — <N items> — top: <title>"
)
```
