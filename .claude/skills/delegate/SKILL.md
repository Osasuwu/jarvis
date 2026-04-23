---
name: delegate
description: This skill should be used when the owner asks Jarvis to dispatch one or more GitHub issues to coding subagents (typically multiple issues in parallel), or says "делегируй #X #Y", "раскидай на агентов", "параллельно реализуй #X #Y #Z". Also used by autonomous-loop to hand off a single subagent-scoped job (e.g. CI debug). For a single issue the main session will do itself, use /implement instead. Jarvis's own judgment on task complexity OVERRIDES blind delegation — if a task is unfit for a subagent (needs session context, cross-cutting reasoning, safety review), keep it inline even if owner said "раскидай".
version: 1.0.0
---

# Delegate Skill

Dispatch **multiple** GitHub issues to coding subagents running in parallel.

The main session stays as orchestrator: it reviews each subagent's diff, resolves scope drift, and decides merges. **Subagents NEVER merge.** They push the PR and stop.

## When to /delegate vs /implement

**Prefer /implement (inline, current session):**
- Single issue
- Task touches safety-critical zones (`driver/`, `planning/`, `mujoco/`)
- Task needs cross-cutting awareness (spans multiple projects, shared infra)
- Issue description alone isn't enough — requires the current session's reasoning trail or just-loaded memory context

**Prefer /delegate (subagent dispatch):**
- Multiple independent issues (any order works)
- Each issue description is self-contained — a fresh coding session could act on it without Jarvis's context
- Tasks touch disjoint files / areas

**Mixed batch — split the work:**
- Keep context-heavy or safety-critical issues for yourself (inline via /implement flow)
- Delegate the rest to subagents
- Report the split reasoning briefly to the owner

**Jarvis judgment overrides the owner's "параллельно":** The owner has explicitly delegated this call to Jarvis (memory: this decision). If a task looks deceptively complex or a subagent will struggle (needs memory context, cross-file reasoning, recent-decisions awareness), keep it inline even if asked to delegate. Don't silently downgrade — tell the owner "keeping #X inline because <reason>".

## Pipeline

### 0. Load context from memory (parallel)

Same as /implement §0:
- `memory_recall(query="delegation", limit=3)` — past delegation rules and feedback
- `memory_recall(query=<batch topic>, limit=3)` — decisions about this area
- `memory_recall(type="feedback", project="global", limit=3)` — behavioral rules

### 1. Classify each issue: delegatable or inline

For each issue in the batch:

1. Run pre-flight (5 checks — same as /implement §1).
2. Classify:
   - **Delegatable** → fresh subagent can handle it from the issue body alone
   - **Inline** → needs session context / safety review / cross-cutting peripheral vision

Produce a short split plan for the owner before acting. Example:

> Batch: #604, #613, #617.
> - #604 (uncertainty map) → **delegate** — self-contained, single module.
> - #613 (swept path) → **inline** — safety-adjacent, `planning/`.
> - #617 (docs tweak) → **delegate** — trivial.

### 2. Claim all issues

Claim *everything* in the batch up front (label `status:in-progress` + comment), even the ones staying inline. Prevents race with other Jarvis instances or owner forgetting to route.

```bash
for N in <N1> <N2> ...; do
  gh issue edit $N --add-label "status:in-progress"
  gh issue comment $N --body "Claimed by Jarvis. Branch: feat/$N-<slug>"
done
```

### 3. Record decision

Emit one `record_decision` covering the batch — which went to subagents, which stayed inline, why.

```
mcp__memory__record_decision(
  decision="delegate batch #<N1> #<N2> ... (split <inline>/<delegated>)",
  rationale="<why this split — subagent fitness, session-context dependency, safety zones>",
  memories_used=[<ids>],
  confidence=<0.0-1.0>,
  alternatives_considered=["all inline", "all delegated", "sequential"],
  reversibility="reversible"
)
```

### 4. Dispatch subagents

For each delegatable issue, spawn a coding subagent:

```
Agent(
  subagent_type="coding",
  isolation="worktree",  # REQUIRED — each agent in its own worktree
  description="Implement #<N>: <title>",
  prompt="<self-contained prompt — see template below>",
  run_in_background=true,  # parallel execution
)
```

**Subagent prompt template** (self-contained — subagent does NOT share main-session memory):

```
Implement GitHub issue #<N> in repo <owner/repo>.

Title: <title>
Body: <full issue body>
Acceptance criteria: <enumerated from issue>
Files likely to change: <list>

Branch name: feat/<N>-<slug>   (MUST use exactly this — branch-name race mitigation)
Target repo CWD: <absolute path to worktree>

Follow the /implement skill pipeline (loaded in your session). Specifically:
- §4 Implement — read existing code first, check if already done, lint, test
- §5 Commit & PR — use the rich PR body template, include "Closes #<N>"
- §6 Record outcome — always record, pattern_tags=["delegation", "subagent", "<area>"]

HARD RULES for you (subagent):
- Do NOT merge the PR. Open it, push it, record outcome, stop.
- Do NOT modify protected files (.mcp.json, CLAUDE.md, etc — see docs/security/agent-boundaries.md)
- Do NOT send messages as the owner
- Do NOT change values, defaults, or constants that are not explicitly named as targets in the issue body. Centralization / refactoring tasks are structural only — IK seeds, default timeouts, magic numbers, tuple constants must be preserved exactly unless the issue says to change them. If the issue is unclear, preserve the value and flag in the PR body.
- If you hit a blocker you can't resolve, record a "partial" outcome with a clear note about what's missing

Report back: PR URL + 2-line summary of what you did.
```

### 4a. Worktree-isolation caveat

**`isolation: "worktree"` is advisory only, not guaranteed.** Documented failures: #295, #640 v1, #640 v2, and 2026-04-20 parallel-delegate contamination (memory `parallel_delegate_worktree_isolation_failed_2026_04_20`). Observed modes:
- Branch-name races (two agents picked the same branch)
- Cross-worktree file contamination (writes from agent A showed up in agent B's worktree)
- Worktree not created at all — agent worked in the main repo directly

**Mitigations:**
- Branch names are explicit, per-issue, and unique (`feat/<N>-<slug>`) — encode in the prompt
- Cap parallelism: **2-3 agents concurrently** is the safe band; 5+ is a red flag
- **Review the diff in the main repo tree as the authoritative check** — `cd <main repo> && git fetch && git diff origin/main...origin/feat/<N>-<slug>`. Treat the agent's worktree as a staging area, not a trusted sandbox.
- If you see contamination, abort and re-dispatch sequentially

### 5. Implement inline tasks (parallel with the subagents)

While subagents run, use the /implement pipeline for anything you kept for yourself. The two streams are independent.

### 6. Review each subagent's diff

When a subagent reports done, review **in the main repo tree, not the agent's worktree** (§4a — worktree isolation is advisory):

```bash
cd <main repo>
git fetch origin
git diff origin/main...origin/feat/<N>-<slug> --stat
git diff origin/main...origin/feat/<N>-<slug>
```

Run the following checks in order — do NOT short-circuit:

- **Scope fit**: file list matches issue scope? Unrelated files → revert
- **Protected files** untouched?
- **Value-change audit**: grep the diff for numeric literals, default parameter values, seed arrays, tuple constants, timeouts, thresholds. For each value that changed, confirm the change is explicitly mandated by the issue body. Silent replacements are scope drift and must be reverted.
  - Lesson #648: subagent silently replaced IK seeds `[0,-30,30,0,-60,0]` with `ready_position` — same shape, different semantics (optimizer convergence inputs, not motion targets). Silent behavior change the subagent didn't flag.
- **Interaction audit**: for every non-trivial edit, trace data flow outward — what callers depend on the pre-existing behavior? what fallbacks or post-processors run after the changed code? Ask "does this still compose correctly?" not just "does the code do what it says?"
  - Lesson #649 v2: after 6-DOF IK fires for in-place rotation, the pre-existing J6-pin fallback would clobber J6 back to its previous value, silently undoing the rotation. The subagent's diff was locally correct but interacted incorrectly with existing code.
- **Tests added + passing?** Run them from the main repo on the branch (`git checkout feat/<N>-<slug> && pytest ...`).
- **PR body** rich? (matches /implement §5 template)
- **Debug code / secrets** leaked?
- **Symmetric patterns**: did the subagent fix only the one instance, or apply to siblings too?

If issues found:
- Push a fix yourself (faster than re-prompting for small stuff)
- Or use `SendMessage` to the agent with specific revision instructions
- If the diff contains ANY silent value change or broken interaction → revert those hunks before merge decision, even if the rest is fine

### 7. Decide merge (orchestrator only)

Per each PR (subagent's or your own):
- Tests green + Copilot clean + LOW/MEDIUM risk → **merge** (see /implement §7.5)
- HIGH/CRITICAL or safety-critical → wait for owner
- CI infra-blocked (billing, not failing tests) → merge if local tests pass + Copilot clean

### 8. Record outcomes

One `outcome_record` per issue (delegated or inline). Distinguish:
- Subagent: `pattern_tags: ["delegation", "subagent", "<area>"]`
- Inline: `pattern_tags: ["delegation", "inline", "<area>"]`

**Also pass `memory_id`** — the primary informing memory id from the per-task `record_decision` episode. Rule: `memory_id = memories_used[0]` (first = dominant basis). For batch-level inline work, use the inline task's own decision_made memories_used; for subagent work, the subagent's record_decision episode is the source. If `memories_used` was empty at decision time, omit `memory_id`.

In `lessons`, note anything non-obvious: subagent misread the issue, scope drift, worktree contamination, etc. These make future delegation decisions smarter.

### 9. Post-merge cleanup

For each merged PR:
```bash
git checkout master && git pull
git branch -d feat/<N>-<slug>
# if this was a subagent job:
git worktree remove <worktree-path>
```

Stale worktrees and branches accumulate fast with multi-issue batches. Clean up at the end.

## Safety rules
- All /implement safety rules apply
- **Subagents must NEVER**: merge PRs, force-push, modify protected files, send messages as owner
- Orchestrator reviews **every** subagent diff before merge
- Parallelism > 3 concurrent → red flag; prefer sequential or smaller batches
- If owner says "параллельно все" but one task is unfit → keep it inline and tell the owner why

## Recovery playbook

See `/implement` for general recovery (broken file, bad PR, wrong branch). Subagent-specific:
- Subagent edited wrong files → revert in its worktree, re-prompt with stricter scope
- Subagent broke its worktree → `git worktree remove --force <path>` + reclaim branch in fresh worktree
- Two subagents raced on same file → abort both, re-dispatch sequentially
- Subagent silently merged → revert merge on `main` immediately, open incident note, add to agent-boundaries.md
