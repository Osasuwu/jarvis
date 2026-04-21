---
name: implement
description: This skill should be used when the owner asks Jarvis to implement a SINGLE GitHub issue directly in the current session, or says "реализуй #42", "сделай #42", "implement #X". For MULTIPLE issues that can run in parallel use /delegate instead. Do NOT trigger for viewing, triaging, or discussing issues — only for actual implementation requests.
version: 1.0.0
---

# Implement Skill

Autonomously implement a GitHub issue **inline, in the current session** — no subagents.

Use this when the work benefits from the full session context (memories just loaded, recent decisions, cross-cutting awareness) or when the issue is safety-adjacent and you can't afford a context-blind coding agent.

## Usage

Invoke when owner says "реализуй #42", "сделай #42", "implement #X".
Single-issue by default. If multiple issues arrive but only one needs session context → implement the context-heavy one here, hand the rest to `/delegate`.

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
- Do NOT dispatch to subagents (keep inline — this skill is the right tool)

### 3. Claim & branch

```bash
gh issue edit <N> --add-label "status:in-progress"
gh issue comment <N> --body "Claimed by Jarvis. Branch: feat/<N>-<slug>"
git checkout master && git pull
git checkout -b feat/<N>-<slug>
```

### 3.5. Record decision (reasoning trace, #252)

After claim, before implementation — emit a `decision_made` episode so `/reflect` can later attribute outcomes to reasoning (missing memory / wrong memory / wrong reasoning):

```
mcp__memory__record_decision(
  decision="implement <issue title> (#<N>)",
  rationale="<one paragraph: why this issue matters now, what approach is planned, what non-obvious choices were made at claim time>",
  memories_used=[<ids from step 0 recall>],
  outcomes_referenced=[],
  confidence=<0.0-1.0>,
  alternatives_considered=["<rejected options — e.g. 'defer to next sprint', 'delegate to subagent'>"],
  reversibility="reversible"
)
```

Always emit for issue implementation — outcome attribution needs the basis. For non-issue decisions, emit only when `reversibility ∈ {hard, irreversible}` OR `confidence < 0.7`.

### 4. Implement

**Protected files — DO NOT modify (see `docs/security/agent-boundaries.md`):**
`.mcp.json`, `config/SOUL.md`, `CLAUDE.md`, `mcp-memory/server.py`, `.claude/settings.json`, `.gitleaks.toml`, `.pre-commit-config.yaml`
If a change to a protected file is needed, document it in the PR description and leave it for the owner.

**For each change:**
- Read existing code first (Read tool)
- **Check if already done** — grep for symbols/strings from the acceptance criteria. Lesson: in one batch, 2 of 6 issues turned out to be pre-implemented; don't re-do what's done.
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
  pattern_tags: ["delegation", "inline", "<area>"]
)
```

**Always record**, even on failure — failed outcomes are the most valuable for learning.

### 7. Batch (if multiple issues kept inline)

When implementing multiple related issues back-to-back:
- Group into one branch if they touch the same files
- Separate branches for independent changes (can be merged independently)
- Address Copilot review comments promptly

### 7.5. Merge policy

**The current session (the one running /implement) CAN merge — no permission needed for routine PRs:**
- Tests green + Copilot review addressed + LOW/MEDIUM risk → **merge without asking**
- HIGH/CRITICAL risk or safety-critical zone (`driver/`, `planning/`, `mujoco/`) → wait for owner explicit approval
- CI infra-blocked (billing failure, empty `steps` array — not *failing* tests) → merge if local tests green AND Copilot review clean
- Copilot findings are advisory — address substantive ones, ignore style nits

Waiting for manual review on every LOW-risk PR is the anti-pattern. See memories: `pm_autonomy_redrobot`, `copilot_review_advisory_only`, `no_confirm_commits_pushes_merges`.

### 8. Post-merge cleanup

After a PR is merged (or when returning to a previously merged branch):
```bash
git checkout master && git pull
git branch -d feat/<N>-<slug>
```

This prevents stale branch accumulation. If the branch has unmerged work, `-d` will refuse — that's correct, don't force it.

## Safety rules
- Check `git status` before branching — abort if dirty
- Never force-push to `master` / `main` or a shared branch
- If change fails tests or breaks build, fix before pushing
- Safety-critical code (`driver/`, `planning/`, `mujoco/`): analyze and comment, don't implement without approval
- Merge policy: see §7.5 — LOW/MEDIUM routine merges are autonomous, HIGH/CRITICAL wait for owner

## Diff review (before marking done)

Before creating the PR, review your own changes:
```bash
git diff main...HEAD --stat
git diff main...HEAD
```

Check for:
- **Scope fit**: does the file list match the issue scope? Unrelated files → revert them before pushing (memory `check_pr_scope_fit_at_open_time`)
- Files that shouldn't have been modified (especially protected files)
- Debug code, `console.log`, `print` statements left behind
- Unrelated changes that crept in
- Secrets or credentials in any form
- **Symmetric patterns**: when fixing a class of bug, grep for sibling instances across the file AND other files — not just the one the reviewer flagged (memory `feedback_symmetric_fixes`)

If the diff looks wrong, fix it before pushing.

## Recovery playbook

See `docs/security/recovery-playbook.md` for how to handle:
- Broke a file → revert from master
- Corrupted memory → `memory_restore`
- Created bad PR → close + delete branch
- Committed to wrong branch → cherry-pick + reset
