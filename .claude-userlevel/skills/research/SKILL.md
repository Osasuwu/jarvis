---
name: research
description: "Investigate a topic, validate decisions, compare options, or run autonomous discovery. Absorbs intel and nightly-research. Trigger: 'исследуй', 'research', 'изучи', 'что лучше', 'сравни'."
version: 4.0.0
---

# Research

Investigate a topic and produce a sourced, confidence-rated finding.

**Mode is determined by the argument shape, not a flag:**

- **A topic is supplied** (`/research <topic>`, or principal asks a specific question) → interactive: focused on that one query.
- **No topic supplied** (`/research`, or scheduled run) → discovery: load context, find genuine gaps, pick top 3, research each.

The pipeline below works for both. Steps that only apply to one shape are flagged inline.

## Pipeline

### 1. Determine the question(s)

**Topic supplied:** classify it.
- **Decision validation** → focus on trade-offs, risks, real-world experience.
- **Knowledge gap** → authoritative explanations, practical examples.
- **Comparison** → objective criteria, benchmarks, community consensus.

**No topic (discovery):** load context first.

```
memory_recall(type="decision", limit=10)
memory_recall(query="working_state", type="project", limit=3)
```

Also scan recent GitHub issues for each repo in `config/repos.conf`.

Find genuine gaps from that context:
- Problems flagged as unsolved
- Decisions made without sufficient research
- Patterns that keep breaking
- Capabilities mentioned but not explored

Score `impact × urgency`. Pick **top 3**. Each becomes a specific, concrete research question. Bad: "research AI agents". Good: "how do iterative planners detect premature convergence?"

### 2. Search

Primary: `firecrawl_search(query="<topic>", limit=3)`.
Fallback: `WebSearch` if Firecrawl unavailable.

Per topic: 2-3 searches with different angles. Preview results with `head -c 4000`.

Prioritize: official docs, reputable blogs, GitHub discussions, benchmarks.
Skip: SEO spam, articles >2 years old for fast-moving topics.

For highly relevant results: `firecrawl_scrape(url=<url>, formats=["markdown"], onlyMainContent=true)` — max 2 scrapes per topic.

### 3. Analyze

1. Claims in multiple independent sources = strong signal
2. Note contradictions between sources
3. Distinguish facts (documented, benchmarked) from opinions
4. For technical decisions: real-world usage at similar scale

### 4. Output

One report per topic (single report when topic supplied, three when discovery):

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

### 5. Save

Save to Supabase if finding is significant:

```
memory_store(type="reference", name="research_{slug}", description="...", content="...", source_provenance="skill:research")
```

If finding is actionable → create GitHub issue in appropriate repo:

```
gh issue create --repo <R> --title "[RESEARCH] <topic>" --body "..."
```

**Discovery-only**: also write a dedup marker so the next scheduled run doesn't repeat topics:

```
memory_store(type="project", name="research_last_run", content="{date} — topics: {t1}, {t2}, {t3}", source_provenance="skill:research")
```

Check for duplicate research-spawned issues before creating new ones.

## Quality rules

- Non-trivial claims: 3+ independent sources when available
- Every finding references specific sources
- Source conflicts → list both sides
- Call out unknowns and weak evidence
- If confidence <50 → recommend follow-up
