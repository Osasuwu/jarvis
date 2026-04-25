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

### 3.5. Record decision (reasoning trace, #252, #334)

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

**Trigger list — emit `record_decision` when ANY of the following hold** (canonical rule; mirrored in global `record_decision_when_what` feedback memory):

1. **Issue implementation** — always, even if reversible. Outcome attribution needs the basis.
2. **`reversibility ∈ {hard, irreversible}`** — e.g. destructive DB ops, force-pushed history, published API changes.
3. **`confidence < 0.7`** — uncertain calls deserve a recorded rationale so `/reflect` can classify the outcome as reasoning-failure vs execution-failure.
4. **Policy / schema / tag / config change** — tagging memories `always_load`, editing protected files, adding/removing skills, changing hook config, schema migrations, installer manifest edits. These are *reversible* but affect the system's behavior across future sessions.
5. **Architectural direction picked** — a resolved "chose X over Y" after discussion, even if reversible. The rationale matters more than the bit that's set; `/reflect` can only learn if the picked direction is captured at pick time.

Rules of thumb:
- "I just made a call that will outlive this session" → emit.
- "I just clarified my own thinking on an approach" → don't emit (no persisted effect).
- When unsure, emit. The cost is one tool call; the cost of missing a decision is a blind spot for `/reflect`.

Pass `memories_used = [<uuids from step 0 recall>]` whenever recall surfaced something. Empty list is valid only when nothing in memory informed the decision — which itself is rare and should be noted in the rationale.

### 4. Implement

**Protected files — policy depends on who is editing.** The canonical list (repo-level + user-level `~/.claude/*`) lives in [`docs/security/agent-boundaries.md`](../../../docs/security/agent-boundaries.md). Don't duplicate it here — check that file before editing.

- **Subagent dispatch (`/delegate`)** — never edits protected files. If the task requires it, escalate to inline `/implement`.
- **Inline `/implement` with explicit owner approval in-session** — MAY edit protected files. Document the change prominently in the PR body (mark the file `[PROTECTED]` in the §Files Changed list + rationale) so the owner sees it before merge.
- **Inline `/implement` without explicit approval** — document the needed change in the PR body and leave the file untouched for the owner.

#### 4a. Already-done audit (mandatory gate)

Before writing any code, enumerate acceptance-criteria symbols from the issue body and grep each:
- `rg -n "<symbol>"` for functions, classes, flags, constants, test names — scoped to likely files
- Read the hits — confirm the existing code actually satisfies the criteria, including test coverage

Three outcomes:
- **All present + tests cover them** → STOP. Comment on the issue with `file:line` evidence, close as `not-planned` referencing the implementing PR/commit, record `success` outcome with `lessons` noting pre-existing implementation. No branch, no PR.
- **Partial** → proceed, but narrow scope to what is actually missing. Note the partial starting state in the PR body Summary.
- **None** → proceed with full scope.

Why this is a gate, not a suggestion: recurring pattern (#237 closed as dup of #209; #656 partial — only tie-breaker missing; tool-width Z absent for a month under shared assumption it existed; multi-run batch where 2 of 6 issues were already done). 30-second grep pays for itself every time.

#### 4b. For each change

- Read existing code first (Read tool)
- Check patterns in the codebase (Grep/Glob)
- Edit existing files, don't create new ones unless needed
- Run lint: `ruff check --fix && ruff format` (Python), `npx tsc --noEmit` (TS)
- Run relevant tests: `pytest tests/test_<module>.py -x -q`
- Build frontend: `npm run build`

#### 4c. E2E smoke before claiming done (I/O-heavy / schema-touching work)

Unit tests systematically miss integration bugs on:
- File I/O — Windows CRLF inflating byte budgets, path separators, encoding (#281)
- Network/DB I/O — composite unique constraints, PostgREST quirks (#281, #284)
- DB schema changes — migration + live row verification (#288)
- Hook registration — SessionStart, PreCompact, etc. (#281 settings.json)
- Subprocess invocation — APScheduler pickling, env propagation (#304, #298)
- Import-target scripts with venv re-exec guards (#313)

Rule: if the change touches any of the above, run one real-input smoke **before** marking the outcome `success`:
- File I/O — operate on a real file (not a synthetic fixture) and byte-compare output
- DB writes — run the write against live Supabase and verify the row shape
- Schema — apply the migration to a branch DB and run the affected smoke
- Hooks — trigger the hook event manually and confirm the side effect
- Subprocess/scheduler — run in a separate shell long enough to confirm restart / pickle behavior

If unit tests green but smoke fails → outcome is `partial`, and the `lessons` field must describe the gap so a future session knows what the unit tests did not catch.

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
  memory_id: "<primary informing memory id>",   # see rule below
  tests_passed: true/false,
  lessons: "<anything non-obvious learned>",
  pattern_tags: ["delegation", "inline", "<area>"]
)
```

**Rule — primary informing memory**: pass `memory_id = memories_used[0]` from the `record_decision` call at §3.5 (first element is the dominant basis). If `memories_used` was empty, omit `memory_id`. Never pass multiple — the FK is a single UUID and `memory_calibration` joins on one memory per outcome; richer attribution belongs at the view layer, not the row.

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
