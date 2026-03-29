---
name: research
description: This skill should be used when the user asks to research a topic, investigate something, validate a technical decision, compare options, or fill a knowledge gap. Trigger phrases include "исследуй", "research", "изучи", "что лучше", "сравни", "расскажи про", "как работает", "стоит ли использовать", "найди информацию".
version: 1.0.0
---

# Research Skill

Investigate a topic using web search, cross-reference sources, and deliver a structured analysis. Designed to help validate technical decisions and fill knowledge gaps efficiently.

## Execution

### Step 1 — Understand the query

Determine what kind of research this is:
- **Decision validation**: user has a choice to make → focus on trade-offs, risks, real-world experience
- **Knowledge gap**: user needs to learn about something → focus on authoritative explanations, practical examples
- **Comparison**: user is evaluating options → focus on objective criteria, benchmarks, community consensus

### Step 2 — Search and gather

1. Search for the topic using multiple queries to get diverse perspectives
2. Prioritize: official documentation, reputable tech blogs, StackOverflow answers with high votes, GitHub discussions, benchmark results
3. Skip: SEO spam, outdated articles (>2 years for fast-moving topics), content without concrete evidence

### Step 3 — Analyze and cross-reference

1. Identify claims that appear in multiple independent sources
2. Note contradictions between sources
3. Distinguish between facts (documented, benchmarked) and opinions (blog posts, anecdotal)
4. For technical decisions: look for real-world usage at similar scale to user's needs

### Step 4 — Format output

```markdown
## Summary
One paragraph answering the core question directly. Lead with the recommendation if it's a decision.

## Key Findings
- **Finding 1** — explanation with source context [source]
- **Finding 2** — explanation [source]

## Trade-offs & Risks
- **Risk/downside 1** — when this matters, how likely
- **Risk/downside 2** — mitigation if known

## Alternatives Considered
- **Alternative** — why it was rejected or when it would be better

## Sources
1. [Title](URL) — one-line note on what it contributed

## Confidence: N/100
One sentence explaining: what makes this confident or uncertain.
```

## Quality Rules

- Non-trivial claims must cite 3+ independent sources when available
- Every key finding must reference specific sources
- If sources conflict, list both sides explicitly
- Call out unknowns, data gaps, and weak evidence areas
- Distinguish "common recommendation" from "proven by benchmarks"
- If confidence is below 50, recommend specific follow-up research
