---
name: self-improve
description: "Autonomous self-improvement of personal-AI-agent: identify gaps from context → ideate → research → implement. A meta-agent role: improves Jarvis by introducing new capabilities, not just fixing existing code."
---

# Self-Improve

**Goal: introduce something genuinely new to Jarvis** — not just fix existing code issues.

A meta-agent mindset: you are an agent whose job is to make Jarvis better. Read the current state, find the most impactful gap, research it, then implement if risk is low enough.

All commands run inside `personal-AI-agent/`:
prefix bash with `cd /c/Users/petrk/GitHub/personal-AI-agent &&`

## Usage

- `/self-improve` — full pipeline
- `/self-improve --dry-run` — plan only, no changes

---

## Pipeline

### Step 1 — Health baseline

Run the self-review skill to understand current state of the codebase.
Note: **don't fix self-review findings directly** — they're context for ideation, not the task list.

### Step 2 — Load context for gap identification

Call in parallel:
- `memory_recall(query="nightly research", limit=3)` — last nightly findings not yet acted on
- `memory_recall(type="decision", project="jarvis", limit=5)` — recent decisions
- `memory_recall(query="working state", project="jarvis", limit=2)` — open items

Combine with self-review findings to build a picture of:
- What's missing from Jarvis?
- What friction keeps appearing in sessions?
- What research findings have been sitting in memory without action?
- What did the owner flag as "do later"?

### Step 3 — Ideate

Invoke the ideate skill (Mode 1: generate ideas).
The ideate skill already reads memory + PROJECT_PLAN.md.

If ideate produces no strong ideas (all Low impact or High risk):
- Fallback to self-review findings for medium-risk code improvements
- These are valid but lower value — note this in output

### Step 4 — Pick the best idea

Select the top-1 idea by: **High impact + Low/Medium effort + Low/Medium risk**.

If multiple ideas tie: prefer the one that connects to nightly research findings (signals it's topical and grounded).

### Step 5 — Targeted research

Run a focused research pass on the selected idea:
- Formulate a specific question: not "research X" but "how do people implement X for Y use case?"
- Use firecrawl_search(limit=3) or WebSearch fallback
- Goal: validate the idea and find implementation patterns

If research shows the idea is bad or already solved differently → go back to Step 4, pick next idea.

### Step 6 — Risk classification

| Risk | Criteria | Action |
|------|----------|--------|
| **Low** | New skill/command, config update, prompt improvement, docs | Auto-implement |
| **Medium** | New hook, new MCP config entry, tool wiring changes | Show plan → wait for confirmation |
| **High** | Architecture change, mcp-memory/server.py, SOUL.md, CLAUDE.md | Propose only, no auto |

**Never auto-apply regardless of risk:** `.mcp.json`, `mcp-memory/server.py`, `config/SOUL.md`, `CLAUDE.md`, any secret/env file.

### Step 7 — Implement (skip in --dry-run)

For **Low risk**: implement directly.
For **Medium risk**: show the plan explicitly, wait for owner confirmation, then implement.
For **High risk**: output proposal only, stop.

After each change, verify:
```bash
cd /c/Users/petrk/GitHub/personal-AI-agent && python -m compileall <changed_file>
```

Run tests if relevant:
```bash
cd /c/Users/petrk/GitHub/personal-AI-agent && python -m pytest tests/ -v --tb=short
```

### Step 8 — Branch + PR (skip in --dry-run, skip for High risk)

```bash
git -C /c/Users/petrk/GitHub/personal-AI-agent checkout -b self-improve/<date>-<slug>
git -C /c/Users/petrk/GitHub/personal-AI-agent add <specific files>
git -C /c/Users/petrk/GitHub/personal-AI-agent commit -m "self-improve: <what was added and why>"
git -C /c/Users/petrk/GitHub/personal-AI-agent push -u origin self-improve/<date>-<slug>
gh pr create --repo Osasuwu/personal-AI-agent \
  --title "self-improve: <short description>" \
  --body "## What\n<what was added>\n\n## Why\n<gap identified>\n\n## Research basis\n<what research found>\n\n## Risk\nLow/Medium — <reasoning>"
```

---

## Output format

```markdown
## Self-Improve Run — YYYY-MM-DD

### Gaps identified
- <gap 1> (source: nightly research / working state / self-review)
- <gap 2>

### Selected idea
**[Idea title]** — Impact: H/M/L | Effort: H/M/L | Risk: L/M/H

### Research finding
<key insight that validates or shapes the implementation>

### Implemented (or: Proposed / Needs approval)
- <what was done / proposed>

### PR
<url> (or: --dry-run / high-risk, no PR)
```

---

## Cost estimate

~$0.15–0.40 per run (self-review + memory recalls + ideate + research + implementation)
