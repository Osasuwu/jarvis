---
name: self-improve
description: "Autonomous self-improvement: run self-review → build fix plan → auto-apply low-risk → PR"
---

# Self-Improve

Autonomous self-improvement pipeline. Runs self-review, builds a prioritized plan, auto-applies safe fixes, creates a PR.

## Usage

- `/self-improve` — full pipeline (auto-apply low-risk, PR)
- `/self-improve --dry-run` — plan only, no changes applied

## Pipeline

### Step 1 — Self-review
Run `/self-review` to get current findings.

### Step 2 — Classify by risk

For each finding, assign risk level:

| Risk | Criteria | Action |
|------|----------|--------|
| **Low** | Dead code, unused imports, simple renaming, cosmetic | Auto-apply |
| **Medium** | Refactoring, error handling improvements, test additions | Report, ask for approval |
| **High** | Architecture changes, security fixes, logic changes, file deletions | Report, require manual work |

**Never auto-apply:** changes to `.mcp.json`, `CLAUDE.md`, `mcp-memory/server.py`, any secret/env file, git history.

### Step 3 — Build plan
For each low-risk item, write a specific fix description: what file, what change, why it's safe.
Present the plan before applying anything.

### Step 4 — Apply low-risk fixes (skip in --dry-run)
Apply each low-risk fix using Edit/Write tools. After each fix, verify the file still compiles:
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
git commit -m "self-improve: auto-apply N low-risk fixes"
git push -u origin self-improve/<date>
gh pr create --title "Self-improve: <date>" --body "<summary of changes>"
```

## Output

```markdown
## Self-Improve Run — YYYY-MM-DD

### Applied (N)
- file.py:42 — removed unused import `os`

### Needs Approval (N)
- file.py:100 — refactor long function (medium risk)

### Skipped / High Risk (N)
- server.py — architecture change, requires manual review

### PR
<url> (or: --dry-run mode, no PR created)
```

## Cost estimate
- Self-review: ~$0.05-0.15 (Sonnet)
- Plan + apply: ~$0.10-0.25 (Sonnet with tools)
- Total: ~$0.20-0.50 per run
