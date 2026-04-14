---
name: delegate
description: This skill should be used when the user wants to implement a GitHub issue autonomously, delegate coding work to an agent, or asks to "реализуй", "сделай", "implement", "delegate", or references a specific issue number for implementation (e.g. "#42", "issue 55"). Do NOT trigger for issue viewing, triaging, or discussing — only for actual implementation requests.
version: 2.1.0
---

# Delegate Skill

Autonomously implement one or more GitHub issues.

## Usage

Invoke when user says "реализуй #42", "delegate issue 55", "implement #X", etc.
Supports multiple issues: "реализуй #42 #43" batches related work.
Target repo: determined from context (CWD, recent conversation, user mention). If ambiguous, ask. Read `config/repos.conf` for the full list of tracked repos.

## Pipeline

### 0. Load context from memory (parallel)

Before anything else, recall relevant memories:
- `memory_recall(query="delegation", limit=3)` — past delegation rules and feedback
- `memory_recall(query=<issue topic>, limit=3)` — decisions about this area
- `memory_recall(type="feedback", project="global", limit=3)` — behavioral rules

Apply recalled context to all subsequent steps. Skip if memories are empty.

### 1. Pre-flight checks (parallel work protocol)

Before claiming ANY issue, run 5 checks:
1. `assignees` — someone already assigned?
2. `status:in-progress` label?
3. Comments with "Claimed by"?
4. `gh pr list` — existing PR for this issue?
5. `git branch -r | grep feat/<N>-` — existing branch?

If ANY check positive → issue is taken, skip it.

### 2. Fetch & analyze

```bash
gh issue view <N> --repo <owner/repo> --json number,title,body,labels,milestone
```

Read the issue body carefully. Check parent issue/epic for context.
Identify: files to change, acceptance criteria, safety implications.

**Safety-critical zones** (`driver/`, `planning/`, `mujoco/`):
- Post analysis + plan as comment
- Wait for owner approval before implementing
- Do NOT delegate to agents

### 3. Claim & branch

```bash
gh issue edit <N> --add-label "status:in-progress"
gh issue comment <N> --body "Claimed by Jarvis. Branch: feat/<N>-<slug>"
git checkout master && git pull
git checkout -b feat/<N>-<slug>
```

### 4. Implement

**Prefer implementing directly** over spawning subagents:
- Direct implementation is faster and avoids agent coordination overhead
- Use Agent tool only for truly parallel independent tasks

**For each change:**
- Read existing code first (Read tool)
- Check patterns in the codebase (Grep/Glob)
- Edit existing files, don't create new ones unless needed
- Run lint: `ruff check --fix && ruff format` (Python), `npx tsc --noEmit` (TS)
- Run relevant tests: `pytest tests/test_<module>.py -x -q`
- Build frontend: `npm run build`

### 5. Commit & PR

```bash
git add <specific files>
git commit -m "<type>(<scope>): <description> (#N)"
git push -u origin feat/<N>-<slug>
```

**PR body must be rich and informative** — this is the primary context for reviewers (human and Copilot). Use this template:

```markdown
## Summary
<what changed, 2-3 sentences — the "what">

## Why
<problem being solved, link to issue — the "why">
Closes #<N>

## Decisions & Alternatives
- **Chose X because Y** (alternative Z was rejected because...)
- Trade-offs: <what we gained, what we gave up>
- <any non-obvious choices that a reviewer would question>

## Risk Assessment
- **LOW**: <cosmetic, imports, naming — safe to auto-apply>
- **MEDIUM**: <refactors, new helpers — review recommended>
- **HIGH**: <logic changes, safety-adjacent — must review manually>
- **CRITICAL**: <data loss risk, security, breaking API — block merge until reviewed>

## Testing
- <commands run: pytest, ruff, tsc, npm run build>
- <what was verified: specific scenarios, edge cases>

## Files Changed
- `file.py` — <why this file, what changed>
```

Create PR:
```bash
gh pr create --title "<type>(<scope>): <description>" --body "$(cat <<'EOF'
<filled template above>
EOF
)"
```

**Why this matters**: Copilot and human reviewers see reasoning inline, not just diff. HIGH/CRITICAL risks are flagged before review starts. No back-and-forth asking "why did you do X?"

### 6. Record outcome

After PR creation (or failure at any step), record the outcome for Pillar 3 tracking:

```
outcome_record(
  task_type: "delegation",
  task_description: "<issue title> (#N)",
  outcome_status: "success" | "partial" | "failure",
  outcome_summary: "<what happened — PR created, tests passed/failed, etc.>",
  goal_slug: "<related goal if known>",
  project: "<repo name>",
  issue_url: "<issue URL>",
  pr_url: "<PR URL if created>",
  tests_passed: true/false,
  lessons: "<anything non-obvious learned>",
  pattern_tags: ["delegation", "<area>"]
)
```

**Always record**, even on failure — failed outcomes are the most valuable for learning.

### 7. Batch optimization

When implementing multiple related issues:
- Group into one branch if they touch the same files
- Separate branches for independent changes (can be merged independently)
- Address Copilot review comments promptly

### 8. Post-merge cleanup

After a PR is merged (or when returning to a previously merged branch):
```bash
git checkout master && git pull
git branch -d feat/<N>-<slug>
```

This prevents stale branch accumulation. If the branch has unmerged work, `-d` will refuse — that's correct, don't force it.

## Safety rules
- Check `git status` before branching — abort if dirty
- Never force-push, never merge PRs without review
- If change fails tests or breaks build, fix before pushing
- Safety-critical code: analyze and comment, don't implement without approval
