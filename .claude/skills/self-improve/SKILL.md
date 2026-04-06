---
name: self-improve
description: "Autonomous self-improvement: identify gaps from context, ideate, research, implement. A meta-agent role — improves Jarvis by introducing new capabilities."
---

# Self-Improve

**Goal: introduce something genuinely new** — not just fix existing issues.

A meta-agent mindset: you are an agent whose job is to make the system better.

## Usage

- `/self-improve` — full pipeline
- `/self-improve --dry-run` — plan only, no changes

## Pipeline

### Step 1 — Health baseline

Run the self-review skill to understand current codebase state.
Note: **don't fix self-review findings directly** — they're context for ideation.

### Step 2 — Load context

In parallel:
- `memory_recall(query="nightly research", limit=3)` — unacted findings
- `memory_recall(type="decision", limit=5)` — recent decisions
- `memory_recall(query="working state", limit=2)` — open items

Build a picture of: what's missing, what friction repeats, what research sits unacted.

### Step 3 — Ideate

Invoke the ideate skill (Mode 1: generate ideas).

If no strong ideas: fallback to self-review findings for code improvements (lower value, note this).

### Step 4 — Pick the best idea

Top-1 by: **High impact + Low/Medium effort + Low/Medium risk**.
Prefer ideas connected to nightly research (topical, grounded).

### Step 5 — Targeted research

Focused search on the selected idea:
- Specific question, not generic scan
- `firecrawl_search(limit=3)` or `WebSearch`
- If research invalidates the idea, go back to Step 4

### Step 6 — Risk classification

| Risk | Criteria | Action |
|------|----------|--------|
| **Low** | New skill, config, prompt improvement, docs | Auto-implement |
| **Medium** | New hook, MCP config, tool wiring | Show plan, wait for confirmation |
| **High** | Architecture, memory server, SOUL.md, CLAUDE.md | Propose only |

**Never auto-apply:** `.mcp.json`, `mcp-memory/server.py`, `config/SOUL.md`, `CLAUDE.md`, env files.

### Step 7 — Implement (skip in --dry-run)

Low risk: implement directly.
Medium risk: show plan, wait for confirmation.
High risk: output proposal only.

Verify after changes:
```bash
python -m compileall <changed_files>
python -m pytest tests/ -v --tb=short
```

### Step 8 — Branch + PR (skip in --dry-run or High risk)

```bash
git checkout -b self-improve/<date>-<slug>
git add <specific files>
git commit -m "self-improve: <what and why>"
git push -u origin self-improve/<date>-<slug>
gh pr create --title "self-improve: <description>" --body "..."
```

## Output

```markdown
## Self-Improve — YYYY-MM-DD

### Gaps identified
- <gap> (source: nightly / working state / self-review)

### Selected idea
**[Title]** — Impact: H/M/L | Effort: H/M/L | Risk: L/M/H

### Research finding
<key insight>

### Result
- Implemented / Proposed / Needs approval
- PR: <url> (or --dry-run / high-risk)
```
