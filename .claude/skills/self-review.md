---
name: self-review
description: "Run self-review: code quality check, test execution, architecture analysis"
---

# Self-Review

Comprehensive health and code quality review of Jarvis. Combines fast deterministic checks with LLM-powered code analysis.

## Checks

### Deterministic (fast, free)

1. **Runtime checks** — verify Python files compile:
   ```bash
   python -m compileall src mcp-memory
   ```

2. **Dependencies** — check key CLI tools are available:
   ```bash
   which gh && which claude && which python
   ```

3. **Config sanity** — verify `config/repos.conf` exists and has entries. Check `.mcp.json` is valid JSON.

4. **Git cleanliness** — check for large diffs or uncommitted work:
   ```bash
   git status && git diff --stat
   ```

5. **Test execution** — run tests if they exist:
   ```bash
   python -m pytest tests/ -v --tb=short 2>&1 | tail -30
   ```

### LLM-powered analysis

6. **Code quality** — read source files and identify:
   - Code duplication across modules
   - Missing error handling at system boundaries (user input, external APIs)
   - Dead code / unused imports
   - Overly complex functions (>50 lines, deeply nested)
   - Security issues (hardcoded secrets, unsafe subprocess calls)
   - Architectural problems (tight coupling, wrong abstraction level)
   - Logic bugs or race conditions

7. **Memory review** — call `memory_recall(query="self-review findings")` to surface recurring patterns from past reviews.

## Output format

```markdown
# Self-Review — YYYY-MM-DD

## Summary
N critical · N major · N minor findings

## Critical
- **[file:line]** Description — why this matters

## Major
- **[file:line]** Description — impact

## Minor
- **[file:line]** Description

## Memory Patterns
Recurring issues from past reviews: ...

## Recommendations
1. Most important fix
2. Second priority
```

Save report to `reports/self-review-<timestamp>.md`.
Store findings summary via `memory_store(type="project", name="self_review_<date>", ...)`.
