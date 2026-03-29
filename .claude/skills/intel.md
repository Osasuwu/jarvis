---
name: intel
description: "Tech intelligence digest — scans for new Claude/MCP/AI agent developments relevant to Jarvis, filters by novelty, rates actionability"
---

# Intel Digest

Weekly tech intelligence scan. Finds what's new and relevant — Claude updates, MCP ecosystem, AI agent tools, open source alternatives — and surfaces only high-signal, genuinely novel information.

## Usage

`/intel` — full scan, save findings to memory
`/intel --quick` — top 3 items only, no memory save
`/intel <topic>` — focus scan on a specific area

## Owner profile (for relevance filtering)

The owner is a solo developer building a personal AI agent (Jarvis) on Claude Code + MCP. Prioritize:

- **Claude Code** — new features, releases, plugins, hooks, channels updates
- **MCP protocol** — new servers, ecosystem tools, official integrations
- **AI agent architecture** — autonomy patterns, self-improvement, memory systems, orchestration
- **Open source alternatives** — tools that could replace or augment parts of Jarvis
- **Cost optimization** — cheaper models, routing strategies, caching
- **Personal AI / productivity** — assistants, automation, cross-device workflows
- **Claude API** — pricing, new capabilities, model updates

Skip: general ChatGPT/GPT-4 hype, marketing fluff, tutorials for beginners, anything >2 weeks old unless it's a major release.

## Step 1 — Check what we already know

Call `memory_recall(query="intel digest")` and `memory_recall(query="claude update release")` to load previously saved findings. Don't re-surface what's already in memory.

## Step 2 — Search

Run these searches (adapt based on `--quick` or focus args):

```
1. "Claude Code" new features release changelog site:github.com OR docs.anthropic.com (past 2 weeks)
2. MCP model context protocol new servers tools 2026
3. Claude Code Channels plugins updates 2026
4. open source personal AI agent self-improvement memory 2026
5. Anthropic news releases March 2026
6. AI agent orchestration new architecture tools 2026
```

For each search:
- Skip results >2 weeks old (unless major release)
- Skip: SEO content farms, obvious reposts, tutorial sites
- Prioritize: official docs, GitHub releases, Hacker News, reputable tech blogs

## Step 3 — Filter by novelty and relevance

For each candidate finding, evaluate:

| Criterion | Question |
|-----------|----------|
| **Novel** | Is this genuinely new? Not in memory, not obvious from existing knowledge? |
| **Relevant** | Does it affect how Jarvis is built or used? |
| **Actionable** | Can the owner do something with this? (try it, integrate it, update the plan) |
| **Signal/noise** | Is this real information or marketing? |

Score each: High / Medium / Low. Drop Low on all three criteria.

## Step 4 — Format output

```markdown
# Intel Digest — YYYY-MM-DD

## High Signal

### [Title]
**What:** one sentence describing what this is
**Why it matters:** how it affects Jarvis or the owner's work
**Action:** what to try/check/update (or "monitor")
**Source:** [link]

---

## Medium Signal

- **[Title]** — brief note. [link]
- ...

## Already known / skip
(list titles only, no details)

## Summary
N new items. Top action: ...
```

## Step 5 — Save to memory

For each High Signal item, save:
```
memory_store(
  type="reference",
  name="intel_<slug>_<date>",
  description="<one-line>",
  content="<what + why + action + source>",
  project=null,
  tags=["intel", "digest"]
)
```

Also save a digest summary:
```
memory_store(
  type="project",
  name="intel_last_run",
  description="Last intel digest run date and top findings",
  content="<date> — <N items found> — top: <top item title>",
  project="jarvis"
)
```

## Cost estimate

~$0.05–0.15 per run (Sonnet, 6–10 web searches + analysis)
Use Haiku for the memory recall/save steps to reduce cost.
