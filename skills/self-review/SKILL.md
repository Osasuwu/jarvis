---
name: self-review
description: "Run self-review: deterministic ops checks, test execution, and LLM-powered code review"
---

# Self-Review

Comprehensive health and code quality review of Jarvis. Combines fast deterministic checks with LLM-powered code analysis.

## Checks

### Deterministic (fast, free)

1. **Runtime checks** — `python -m compileall src` + import smoke test
2. **Budget and config sanity** — budget values, per-query vs daily, model names
3. **Delegation health** — `gh` + `claude` CLI, `repos.conf`, git tree cleanliness
4. **Changed-files risk** — large pending diffs, high-impact modified paths
5. **Test execution** — runs `pytest`, flags failures or missing test suite

### LLM-powered (async, ~$0.05-0.15)

6. **Code quality review (Sonnet)** — reads all source files and finds:
   - Code duplication
   - Missing error handling at system boundaries
   - Dead code / unused imports
   - Overly complex functions
   - Security issues
   - Architectural problems
   - Logic bugs / race conditions

### Memory integration

- Reads last 5 self-review memory entries and summarizes patterns (Haiku)
- Writes findings summary to work memory for cross-run tracking

## Output

- Structured markdown report with findings by severity (Critical / Major / Minor)
- Memory context summary (recurring patterns from past reviews)
- Report saved under `reports/self-review-<timestamp>.md`
