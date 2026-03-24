---
name: research
description: "Source-backed research with confidence scoring — helps validate decisions and fill knowledge gaps"
---

# Research Skill

Investigate a topic using web search, cross-reference sources, and deliver a structured analysis. Designed to help validate technical decisions and fill knowledge gaps efficiently.

## Usage

`/research <topic or question>`

Examples:
- `/research best Python async HTTP libraries 2026`
- `/research is SQLite suitable for 10k concurrent reads`
- `/research Claude Agent SDK vs LangChain for personal agents`

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
- (3-7 findings, ordered by relevance)

## Trade-offs & Risks
- **Risk/downside 1** — when this matters, how likely
- **Risk/downside 2** — mitigation if known
- (include risks of BOTH choosing and not choosing, if decision-type)

## Alternatives Considered
- **Alternative** — why it was rejected or when it would be better
- (skip this section if not a comparison/decision query)

## Sources
1. [Title](URL) — one-line note on what it contributed
2. [Title](URL) — note
- (only sources actually used in findings)

## Confidence: N/100
One sentence explaining: what makes this confident or uncertain.
- 80-100: strong consensus, multiple authoritative sources agree
- 50-79: mixed signals, some sources disagree, or topic is nuanced
- 0-49: limited data, mostly opinions, or topic too new/niche
```

## Quality Rules

- Every finding must cite at least one source
- If sources conflict, say so explicitly — don't pick a winner without evidence
- Distinguish "this is the common recommendation" from "this is proven by benchmarks"
- If the topic is too broad, narrow it and explain what was scoped out
- If confidence is below 50, explicitly recommend what additional research the user should do
