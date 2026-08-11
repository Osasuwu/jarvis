---
name: task-implement
description: Headless per-issue executor for `task_queue` rows. Invoked ONLY as a spawned goal (`goal="/task-implement #N"`) via `/dispatch` → `task_dispatch.py`'s `executor_spawn` (`claude -p`, restricted tools, no MCP). Not principal-invoked — for one issue with full session context, use `/implement`.
version: 1.0.0
---

# Task-Implement Skill

Single canonical home for headless, per-issue routing (mechanical vs TDD-mode), HARD RULES, and AC discipline when a `task_queue` row's goal reaches a spawned `claude -p` worker with no operator present.

Everything below is **re-derived from the live issue at spawn time**. Nothing composed at `/dispatch` enqueue time is trusted beyond the issue number — the goal string may carry augmentations injected by `agents/task_dispatch.py::default_spawn` (`_augment_branch_directive`, `_augment_closes_mandate`) naming a branch and a PR-body requirement; honor those, but re-fetch title/body/labels/AC from GitHub rather than trusting anything else in the goal text.

## Why this skill exists, and why it is not `/delegate`'s subagent prompt

`/delegate`'s subagent template (the `Agent(subagent_type="coding", ...)` path) runs under the **interactive** Task/Agent tool — full tool access, including `mcp__memory__*`. This skill runs under the **reactive-core executor lane** — `claude -p --allowedTools <list>` with no operator and no MCP tools of any kind (verified against `agents/executor.py::_SPAWN_ALLOWED_TOOLS`, line 83):

```
Read, Glob, Grep, TodoWrite,
Bash(git status:*), Bash(git diff:*), Bash(git log:*), Bash(git show:*),
Bash(git rev-parse:*), Bash(git checkout:*), Bash(git fetch:*),
Bash(git add:*), Bash(git commit:*), Bash(git push:*),
Bash(gh pr view:*), Bash(gh pr create:*), Bash(gh pr list:*),
Bash(gh issue view:*), Bash(gh issue create:*), Bash(gh issue list:*),
Bash(gh issue comment:*), Bash(gh api repos/*/issues:*), Bash(gh api repos/*/pulls:*),
Bash(pytest:*), Bash(npm:*)
```

No `mcp__memory__*` entry exists in that list — this is an **environmental constraint**, not a style guideline this skill additionally enforces. It grounds every HARD RULE below in fact rather than in the issue body's prose claim.

## HARD RULES (environment-enforced, not advisory)

1. **No architectural decisions.** A decision-needing situation (ambiguous scope, a design fork, an AC that doesn't resolve cleanly from the issue body) ⇒ **stop, park, report** — do not decide and proceed. Post a comment on the issue explaining the fork, add `status:owner-queue`, and end the session. This is the headless analog of `/implement`'s `grill_required` exit: there is no operator here to grill, so the only safe move on genuine ambiguity is to hand it back.
2. **No `record_decision`.** Per decision `d72317df`: thin goals + `/task-implement` means the executor re-derives everything and never calls `mcp__memory__record_decision`. This is doubly enforced — the tool isn't in the allowlist even if this rule were forgotten.
3. **No `outcome_record` either.** Broader than rule 2: *no* `mcp__memory__*` tool is reachable here, so outcome recording cannot happen inside this skill at all. Per Slice 2 design (#1085), the four audit checks and outcome bookkeeping that `/delegate` used to run in its own §6/§7 now live in `/verify` as a **post-merge** audit — `/verify` runs interactively (or via a session with MCP access) and reads the merged PR/issue state after the fact. Do not attempt outcome recording, do not treat its absence as incomplete work — it is out of scope for this skill by design.
4. **Do not merge.** Open the PR, push it, stop. Merge policy and the merge decision belong to `/verify` or the principal, not the headless worker.
5. **Do not modify protected files** (`.mcp.json`, CLAUDE.md, etc. — see `docs/security/agent-boundaries.md`).
6. **Comply with goal-text augmentations you did not write.** `default_spawn` may have already appended a `(branch=task/<task_id>)` directive and/or a `(PR-body requirement: ...)` mandate to your goal before you ever saw it (`agents/task_dispatch.py::_augment_branch_directive`, `_augment_closes_mandate`). Follow them literally — branch name and `Closes #N`/`Refs #N` placement are not your call to make differently.

## Contract: dispatch routing (mechanical vs TDD-mode, self-applied)

By the time a row reaches this skill, it has already passed `check_issue` (`scripts/delegate_predispatch_gate.py`) **twice** — once as `/dispatch`'s advisory admission gate, once as `drain_tasks`'s mechanical pre-spawn re-check on a fresh fetch (#1085 Slice 2, S2-3). `check_issue` condition 4 is **required**, not optional: the issue body already cites a decision UUID or carries the explicit `[no-decision]` marker. This changes how routing is detected here relative to `/implement`/`/delegate`:

- **No `memory_get(working_state_...)` lookup** — that's an MCP tool, unreachable in this sandbox (see HARD RULE 3's grounding). Grill-artifact detection is **issue-body-only**.
- **Detection**: the issue body contains a heading starting with `## Decisions` (prefix match) citing at least one decision UUID → **TDD-mode**. The issue body carries `[no-decision]` instead (mechanical slice, no informing decision) → **mechanical-mode**. Since `check_issue` already guarantees one of these two is present, there is no third "neither" case here — that case was already refused upstream and never reached spawn.
- **No `grill_required` exit exists in this skill.** That branch belongs to the gates upstream (`/dispatch`'s advisory check, `drain_tasks`'s mechanical re-check) — by construction, a row that would exit `grill_required` never gets spawned. If you observe a body with neither a `## Decisions` UUID nor `[no-decision]` anyway (gate drift, a race, a hand-enqueued row), treat it as HARD RULE 1 territory: stop, park (`status:owner-queue` + explanatory comment), do not guess.

## Pipeline

### 1. Fetch the live issue

```bash
gh issue view <N> --repo <owner/repo> --json number,title,body,labels,milestone,assignees
```

`<N>` comes from the goal text (`/task-implement #N`) or the row's `issue_number` column if you were handed it directly — either way, everything else (title, body, AC, labels) is read fresh here, never assumed from the goal string.

### 2. Claim

```bash
gh issue edit <N> --add-label "status:in-progress"
gh issue comment <N> --body "Claimed by Jarvis (task-implement, task_id=<task_id>)."
```

Branch checkout/creation follows whatever `(branch=...)` directive is present in your goal text (HARD RULE 6) — do not invent a different branch name. If somehow no branch directive is present (should not happen for a fresh-shape goal per `_augment_branch_directive`), fall back to `task/<task_id>`.

### 3. Route: mechanical-mode or TDD-mode

Per §Contract above. TDD-mode follows `.claude-userlevel/skills/_shared/tdd/tdd-loop.md` exactly as `/implement`'s §4-TDD does — read it as a file, not a skill invocation (ADR-0001: no mid-task self-triggering of other skills).

### 3a. Already-done audit (mandatory, both routes)

Same gate as `/implement` §4a: enumerate AC symbols, grep for each, read the hits. All present + tested → close as `not-planned` with `file:line` evidence in a comment, no branch/PR. Partial → narrow scope. None → full scope. Do not skip this because the queue already deduped the issue — dedup checks in-flight *work*, not whether the work already shipped in an unrelated PR.

### 3b. Implement

- Mechanical-mode: direct implementation, same hygiene as `/implement` §4b (read existing code, lint, test, `git add --renormalize .` before first commit on Windows workers).
- TDD-mode: one AC bullet at a time, red → green, no horizontal batching, single refactor pass after all AC items are green (`tdd-loop.md` §4). Refactor scope is bounded to code freshly covered by a test written this session.

**Divergence & drive-by discipline** (both routes — carried forward from the retired `/delegate` orchestrator-review checklist; `/verify` Step 2b (#1085 S2-5) audits for violations of these post-merge, but the cheaper fix is not committing them in the first place):

- **Deliberate divergences must be surfaced.** If you depart from the AC's literal signature, parameter names, values, default constants, or interpretation for any reason (cleaner interface, stricter rule, fewer args, renamed field) — add a `## Deliberate divergences` section to the PR body listing each change as `<what diverged> — <why> — <impact>`. Silent design drift is a delivery defect even when the divergence is reasonable — nobody re-reads the diff line-by-line to catch it. (Lesson #634: subagent silently reshaped `decide(...)` from 4 args to 3 and picked a stricter rule than the AC suggested.)
- **Drive-by edits: remove means remove, not replace.** When an issue or instruction says "remove stale X" or "delete the line about Y", DELETE — do not rewrite the line with new content. If a replacement is genuinely needed, that is a separate scope question to escalate (§Escalation below), not a drive-by reinterpretation. Before inserting any text in a drive-by neighborhood, grep ±3 lines around the change to confirm the addition isn't duplicating an existing nearby line. (Lesson #662: subagent replaced a stale bullet with new text that duplicated the next existing line.)

### 3c. AC gate before PR

Same triple-check as `/implement` §4d: symbol exists, call sites exist outside tests, the AC-specific test passes. Fix now, not after.

### 4. Commit & PR

```bash
git add <specific files>
git commit -m "<type>(<scope>): <description> (#N)"
git push -u origin <branch from step 2>
gh pr create --title "<type>(<scope>): <description>" --body-file <path>
```

PR body uses `/implement` §5's rich template (Summary / Why / Decisions & Alternatives / Risk Assessment / Testing / Files Changed). The `Closes #N` (or `Refs #N` for partial-scope work) line is whatever `_augment_closes_mandate` told you to put there — HARD RULE 6, don't improvise a different keyword. Always use `--body-file`, never an inline `--body` string (heredocs and PowerShell both mangle inline bodies with backticks/quotes).

### 5. Stop

Report the PR URL and a two-line summary as your final output — this IS the return value read by `agents/task_dispatch.py` (per the Workflow/executor contract), not a message to a human in the loop. No merge, no `record_decision`, no `outcome_record` (HARD RULES 2-4). `/verify` picks up outcome bookkeeping and the four migrated audit checks post-merge.

## Escalation (HARD RULE 1 in practice)

```bash
gh issue comment <N> --body "task-implement stopped: <one-line description of the fork/ambiguity>. Needs owner decision before this can proceed."
gh issue edit <N> --add-label "status:owner-queue"
```

Then stop — do not guess, do not pick the option that "seems obviously right." The sandbox has no memory tools by design; a wrong guess here is unrecoverable until a human or a fresh interactive session with full context revisits it.

## Safety rules

- All `/implement` safety rules apply (protected files, no messages as principal, no value/constant changes not named in the issue).
- Never attempt an MCP tool call — it is not in the allowlist and will fail; treat that failure as confirmation you're in the wrong lane, not a bug to route around.
- Never merge, never force-push.
