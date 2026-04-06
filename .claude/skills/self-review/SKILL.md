---
name: self-review
description: This skill should be used when the user asks to review the Jarvis codebase, check code quality, run tests, audit the personal-AI-agent project health, or when self-improve needs a baseline review. Trigger phrases include "проверь код", "self-review", "code quality", "запусти тесты", "проверь проект", "что не так с кодом".
version: 1.0.0
---

# Self-Review

Comprehensive health and code quality review of the personal-AI-agent project.
All commands run from the project root (determined at runtime via `git rev-parse --show-toplevel` or CWD).

## Checks

### Deterministic (fast, free)

1. **Runtime checks**:
   ```bash
   python -m compileall src mcp-memory
   ```

2. **Dependencies**:
   ```bash
   which gh && which claude && which python
   ```

3. **Config sanity** — verify `config/repos.conf` exists. Check `.mcp.json` is valid JSON.

4. **Git cleanliness**:
   ```bash
   git status && git diff --stat
   ```

5. **Tests**:
   ```bash
   python -m pytest tests/ -v --tb=short 2>&1 | tail -30
   ```

### LLM-powered analysis

6. **Code quality** — read source files and identify:
   - Dead code / unused imports
   - Missing error handling at system boundaries
   - Overly complex functions (>50 lines)
   - Security issues (hardcoded secrets, unsafe subprocess)
   - Tight coupling, wrong abstraction level

7. **Memory review** — `memory_recall(query="self-review findings")` for recurring patterns.

8. **Skills audit** — read all files in `.claude/skills/`. For each check:
   - Соответствует текущей архитектуре?
   - Есть дублирование?
   - Пути и команды актуальны?
   - Skill вообще используется?

## Output

```markdown
# Self-Review — YYYY-MM-DD

## Summary
N critical · N major · N minor findings

## Critical / Major / Minor
- **[file:line]** Description — why this matters

## Skills Audit
- ✅ research — актуален
- ⚠️ triage — путь к repos.conf устарел

## Recommendations
1. Most important fix
```

Save report to `reports/self-review-<timestamp>.md`.
Store via `memory_store(type="project", name="self_review_<date>", ...)`.
