---
name: research
description: "Investigate a topic, validate decisions, compare options, or run autonomous discovery. Absorbs intel and nightly-research. Trigger: 'исследуй', 'research', 'изучи', 'что лучше', 'сравни'."
version: 3.0.0
---

# Research

Two modes: **interactive** (user asks a question) and **discovery** (autonomous, finds gaps and researches them).

## Mode: Interactive (default)

User asks to research something specific.

### Step 1 — Understand the query

Determine type:
- **Decision validation** → focus on trade-offs, risks, real-world experience
- **Knowledge gap** → authoritative explanations, practical examples
- **Comparison** → objective criteria, benchmarks, community consensus

### Step 2 — Search

Primary: `firecrawl_search(query="<topic>", limit=3)`.
Fallback: `WebSearch` if Firecrawl unavailable.

Run 2-3 searches with different angles. Preview results with `head -c 4000`.

Prioritize: official docs, reputable blogs, GitHub discussions, benchmarks.
Skip: SEO spam, articles >2 years old for fast-moving topics.

For highly relevant results: `firecrawl_scrape(url=<url>, formats=["markdown"], onlyMainContent=true)` — max 2 scrapes per run.

### Step 3 — Analyze

1. Claims in multiple independent sources = strong signal
2. Note contradictions between sources
3. Distinguish facts (documented, benchmarked) from opinions
4. For technical decisions: real-world usage at similar scale

### Step 4 — Output

```markdown
## Summary
One paragraph, lead with recommendation if it's a decision.

## Key Findings
- **Finding** — explanation [source]

## Trade-offs & Risks
- **Risk** — when it matters, mitigation

## Alternatives
- **Alternative** — why rejected or when better

## Sources
1. [Title](URL) — what it contributed

## Confidence: N/100
One sentence: what makes this confident or uncertain.
```

### Step 5 — Save

Save to Supabase if finding is significant:
```
memory_store(type="reference", name="research_{slug}", description="...", content="...", source_provenance="skill:research")
```

If finding is actionable → create GitHub issue in appropriate repo:
```
gh issue create --repo <R> --title "[RESEARCH] <topic>" --body "..."
```

---

## Mode: Discovery (autonomous)

For scheduled runs. Finds gaps in current knowledge and researches them.

### Step 1 — Load context

```
memory_recall(type="decision", limit=10)
memory_recall(query="working_state", type="project", limit=3)
```

Also check recent GitHub issues for each repo in `config/repos.conf`.

### Step 2 — Identify gaps

From context, find genuine gaps:
- Problems flagged as unsolved
- Decisions made without sufficient research
- Patterns that keep breaking
- Capabilities mentioned but not explored

Score: impact × urgency. Pick **top 3**. Each becomes a specific research question.

Bad: "research AI agents"
Good: "how do iterative planners detect premature convergence?"

### Step 3 — Research

For each topic: `WebSearch` or `firecrawl_search`, max 3 searches per topic.

### Step 4 — Save

Per topic:
```
memory_store(type="reference", name="research_{slug}", project="{project}", content="...", source_provenance="skill:research")
```

Actionable findings → GitHub issues (check for duplicates first).

Dedup marker:
```
memory_store(type="project", name="research_last_run", content="{date} — topics: {t1}, {t2}, {t3}", source_provenance="skill:research")
```

---

## Quality rules (both modes)

- Non-trivial claims: 3+ independent sources when available
- Every finding references specific sources
- Source conflicts → list both sides
- Call out unknowns and weak evidence
- If confidence <50 → recommend follow-up
