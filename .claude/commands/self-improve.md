---
name: self-improve
description: "Autonomous self-improvement of personal-AI-agent: run self-review → build fix plan → auto-apply low and medium risk → PR"
---

# Self-Improve

Autonomous self-improvement pipeline for Jarvis (personal-AI-agent).

## Usage

- `/self-improve` — full pipeline (auto-apply low + medium risk, PR)
- `/self-improve --dry-run` — plan only, no changes applied

## Pipeline

### Step 1 — Self-review
Run `/self-review` to get current findings.

### Step 2 — Classify by risk

For each finding, assign risk level:

| Risk | Criteria | Action |
|------|----------|--------|
| **Low** | Dead code, unused imports, simple renaming, cosmetic | Auto-apply |
| **Medium** | Refactoring, error handling improvements, test additions, missing docstrings | Auto-apply |
| **High** | Architecture changes, security fixes, logic changes, file deletions | Report, require manual work |

**Never auto-apply regardless of risk:** changes to `.mcp.json`, `CLAUDE.md`, `mcp-memory/server.py`, `config/SOUL.md`, any secret/env file, git history.

### Step 3 — Build plan
For each low/medium-risk item, write a specific fix description: what file, what change, why it's safe.
Present the plan before applying anything.

### Step 4 — Apply low + medium risk fixes (skip in --dry-run)
Apply each fix using Edit/Write tools. After each fix, verify the file still compiles:
```bash
python -m compileall <changed_file>
```

### Step 5 — Validate
Run full test suite:
```bash
python -m pytest tests/ -v --tb=short
```
If tests fail, revert the last change and mark it as failed.

### Step 6 — Branch + PR (skip in --dry-run)
```bash
git checkout -b self-improve/<date>
git add -A
git commit -m "self-improve: auto-apply N low/medium-risk fixes"
git push -u origin self-improve/<date>
gh pr create --title "Self-improve: <date>" --body "<summary of changes>"
```

## Output

```markdown
## Self-Improve Run — YYYY-MM-DD

### Applied (N)
- file.py:42 — removed unused import `os`

### Needs Approval (N)
- file.py:100 — high-risk architecture change

### PR
<url> (or: --dry-run mode, no PR created)
```

## Cost estimate
- Self-review: ~$0.05-0.15 (Sonnet)
- Plan + apply: ~$0.10-0.25 (Sonnet with tools)
- Total: ~$0.20-0.50 per run
