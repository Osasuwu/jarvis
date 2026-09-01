---
name: dispatch
description: Enqueue GitHub issues onto task_queue for headless pickup by /task-implement. Triggers: "делегируй #X #Y", "раскидай на агентов", "параллельно реализуй #X #Y #Z". Single issue with heavy context → /implement instead. Never spawns a subagent in-session — enqueues a thin row, reports enqueued/refused/collided. Context-heavy/cross-cutting/safety-critical work stays inline.
version: 3.0.0
---

# Dispatch Skill

Renamed from `/delegate` (#1085 Slice 2). Enqueues GitHub issues onto `task_queue` for headless execution by **`/task-implement`**, spawned by `agents/task_dispatch.py::drain_tasks` (running under `wake_driver` or a local `--once` loop) — never by this skill directly.

**This skill never spawns a subagent in-session.** The old `Agent(subagent_type="coding", isolation="worktree", ...)` dispatch path is retired: duplicate-dispatch prevention used to be a shared predicate invoked from two call sites (this skill's prose + `agents/task_dispatch.py`) plus a branch-push claim — prose-invoked enforcement is Tier 1, the same tier whose failure produced the #859/#860 incident. Routing everything through one `enqueue()` call makes `task_queue`'s partial unique index on `issue_number` (Slice 1, PR #1529) the single dedup choke point, enforced by the database, not by an LLM correctly following prose.

Memory recall and the `record_decision` contract come from user-level CLAUDE.md `### Memory & decision protocol`. The skill-specific gates below are what `/dispatch` adds on top.

Slice 2 itself ships behind a ship gate — `status:owner-queue` stays on
#1085 until 5 clean executor completions land; the query and per-candidate
check are in [`docs/reference/dispatch-ship-gate.md`](../../../docs/reference/dispatch-ship-gate.md).

## When to /dispatch vs /implement

**Prefer /implement (inline, current session):**
- Single issue
- Task touches safety-critical zones (`driver/`, `planning/`, `mujoco/`)
- Task needs cross-cutting awareness (spans multiple projects, shared infra)
- Issue description alone isn't enough — requires the current session's reasoning trail or just-loaded memory context

**Prefer /dispatch (queue-routed headless execution):**
- Multiple independent issues (any order works)
- Each issue description is self-contained — `/task-implement` re-derives everything from the live issue at spawn, with no memory-tool access
- Tasks touch disjoint files / areas

**Mixed batch — split the work:**
- Keep context-heavy or safety-critical issues for yourself (inline via /implement flow)
- Dispatch the rest to the queue
- Report the split reasoning briefly to the principal

**Jarvis judgment overrides the principal's "параллельно":** The principal has explicitly delegated this call to Jarvis (memory: this decision). If a task looks deceptively complex or a headless worker will struggle (needs memory context, cross-file reasoning, recent-decisions awareness), keep it inline even if asked to dispatch. Don't silently downgrade — tell the principal "keeping #X inline because <reason>".

## Contract: advisory readiness gate (runs before enqueue, per issue)

Every issue passes through the same readiness check `/task-implement`'s spawn path re-runs mechanically (`scripts/delegate_predispatch_gate.py::check_issue`) — but here it is **advisory**: a courtesy filter that avoids wasting a queue row + park cycle on an issue that is obviously not ready, and gives the operator the refusal message immediately instead of after a round-trip through the queue. The actual enforcement authority is `drain_tasks`'s fresh-fetch mechanical re-check (#1085 S2-3), which runs unconditionally regardless of what this skill did or didn't check.

**Five conditions, all required** (canonical implementation:
[`scripts/delegate_predispatch_gate.py`](../../../scripts/delegate_predispatch_gate.py)):

0. **Issue's repo matches `GITHUB_REPO`** (stopgap, #1651 — checked first,
   short-circuits before the four readiness conditions below). `task_queue`
   has no `repo` column yet and everything spawned from it runs against the
   local checkout's default repo, so a foreign-repo issue would silently
   dispatch work against the wrong repository. Refused with a message
   pointing at milestone 58 (#959) S3 (#1119)/S4a (#1121) — the slices where
   real per-row repo resolution belongs. Remove this condition once that
   ships.
1. Issue has label `sandcastle` (applied by `/to-tickets` per the AFK-fit
   checklist at slice creation — never manually, never at grill time).
2. Issue has **no** `needs-*` label (`needs-grill`, `needs-research`,
   `needs-prd`, `needs-refactor`, …). Each requesting skill removes its own
   label at terminal success.
3. Issue body contains an `## Acceptance criteria` heading (case-insensitive
   prefix match).
4. Issue body cites at least one decision UUID, or carries the explicit
   `[no-decision]` marker for slices that legitimately have none. `/to-tickets`
   emits this citation automatically at publish time — a missing one is a
   hard refuse here, not a legacy-backstop nudge.

**Invocation** (per issue, before enqueue):

```bash
gh issue view <N> --repo <owner/repo> --json number,title,body,labels \
  | jq --arg repo "<owner/repo>" '{issue: ., repo: $repo, open_prs: [], open_branches: []}' \
  | python scripts/delegate_predispatch_gate.py
# exit 0 ⇒ ready; exit 1 ⇒ refuse, message on stdout names each missing element
```

`<owner/repo>` in `--arg repo` must be the same value passed to `--repo` above — always the issue's own repo, never assumed. The empty `open_prs`/`open_branches` arrays are deliberate, not a stub to fill in later: `main()`'s envelope is strict (a missing `issue`/`repo`/`open_prs`/`open_branches` key fails closed as SKIP, exit 2), and `check_in_flight` (the PR/branch predicate) is **not** meant to be exercised here anymore — see §Contract: enqueue below for why the queue's own CAS replaces it for the dedup question. Passing empty lists makes `check_in_flight` a structural no-op while still satisfying the envelope shape.

**On refusal** (any one or more of the five conditions fail):

1. `mcp__memory__outcome_record(task_type="delegation", outcome_status="failure", outcome_summary="readiness gate refused: <message>", project="<repo>", issue_url=...)` — recorded so `/reflect` and `/self-improve` can spot patterns.
2. `gh issue edit <N> --add-label "status:owner-queue"` — surfaces in next `/status` run.
3. Report to the principal in the batch summary: `#N refused — <verbatim gate message>`.
4. The issue is **not** enqueued, not claimed, no label churn beyond the owner-queue flag. `/grill` / `/research` / sandcastle-label-add are the unblock paths — once fixed, re-dispatch flips the route.

**No Telegram escalation** even on repeat refuses — last-resort rule (decision `e9b9cfb8`). Owner discovers via `/status`.

**Interactive `/implement` is NOT gated by this check.** The gate guards
*queue-routed* dispatch where no operator is present at execution time.
Inline `/implement` keeps the grill trigger checkbox as its in-skill
backstop and can run on any issue (including `status:owner-queue`-tagged
ones) — the operator IS the gate.

## Contract: enqueue (replaces the old dispatch-dedup fetch + atomic branch-push claim)

Per issue that passed the readiness gate:

```python
task_queue.enqueue(
    goal=f"/task-implement #{N}",
    issue_number=N,
    priority=0,
    assignee="sandcastle",
    idempotency_key=f"delegate:{N}:r1",
    origin="dispatch",
)
```

The attempt suffix (`r1`, `r2`, …) increments on re-dispatch after a parked
row — always `r<k+1>`, never reuse `r<k>`. First dispatch of an issue is
always `r1`.

**Outcomes:**

- **Row returned (not `None`)** → **enqueued**. Report `#N enqueued
  (task_id=<id>)`. No label mutation, no claim — `/task-implement` claims
  (`status:in-progress` + comment) when it actually starts work, not at
  enqueue time. This keeps a queued-but-not-yet-drained issue visibly
  unclaimed rather than falsely showing "in progress" while sitting behind
  a stale driver.
- **`None` returned** → unique-violation on `issue_number` (Slice 1's
  partial index, `idx_task_queue_issue_number_active`) → **collided**:
  another non-terminal row already claims this issue — an orchestrator-emitted
  row, a prior `/dispatch`, or a live `/rework` row. Report `#N collided —
  already in flight (queue-owned)`. **No label mutation** — the issue is
  already owned by the in-flight row, same rule the old dispatch-dedup SKIP
  path used.

This single call replaces **both** the old two-step dedup predicate
(fetch open PRs + fetch open branches + `check_in_flight`) **and** the
atomic branch-push claim. The partial unique index IS the atomic claim now
— `enqueue()`'s explicit unique-violation handling (try/except → `None`,
Slice 1) turns what used to be a read-then-push race window into a single
round-trip with no window at all.

**Residual gap, not a race** (`ceiling:` this skill no longer owns the
mitigation for it): `enqueue()`'s CAS only catches issues that already have
a **queue-lane** claim. An issue with in-flight work from an old-style
branch/PR that predates Slice 2 (no queue row backing it) won't collide
here. `/task-implement`'s fresh-fetch and `drain_tasks`'s S2-3 mechanical
re-check both still carry `check_in_flight`'s legacy branch/PR detection
(kept per S2-4) as a second-line catch at spawn time. Not expected to fire
once Slice 2 is the only active dispatch path.

## Never spawns in-session

Unlike the retired `/delegate`, this skill's job ends at enqueue + report.
`agents/task_dispatch.py::drain_tasks` is the only thing that spawns work.
No `Agent(subagent_type="coding", ...)` call exists anywhere in this skill,
no worktree isolation setup here, no diff review, no merge decision — those
either move to `/task-implement` (the actual worker) or to `/verify` (the
post-merge audit, #1085 S2-5).

## Pipeline

### 1. Classify each issue: dispatchable or inline

For each issue in the batch:

1. Run pre-flight (5 checks — same as `/implement` §1: assignees, `status:in-progress` label, "Claimed by" comments, existing PR, existing branch).
2. Classify:
   - **Dispatchable** → issue body is self-contained; `/task-implement` can act on it with no operator present.
   - **Inline** → needs session context / safety review / cross-cutting peripheral vision (route through `/implement`).

Produce a short split plan for the principal before acting. Example:

> Batch: #604, #613, #617.
> - #604 (uncertainty map) → **dispatch** — self-contained, single module.
> - #613 (swept path) → **inline** — safety-adjacent, `planning/`.
> - #617 (docs tweak) → **dispatch** — trivial.

### 2. Advisory readiness gate

Per §Contract above, for every issue routed to **dispatch**. Refused issues exit immediately (owner-queue label, outcome recorded, excluded from the enqueue step).

### 3. Enqueue

Per §Contract above, for every issue that passed the gate. Collect enqueued/collided verdicts per issue.

### 3b. Heartbeat check (once per batch, not per issue)

If at least one issue **enqueued** in step 3, call `agents.driver_heartbeat.check_heartbeat()` **once** — one driver (`wake_driver`), one heartbeat row, not a per-issue check. Skip entirely if every issue in the batch refused or collided (nothing was enqueued, so a stale driver has nothing to warn about yet).

```python
from agents.driver_heartbeat import check_heartbeat, WARN_MESSAGE

status = check_heartbeat()
if status.is_stale:
    # surface WARN_MESSAGE ("driver stale — rows enqueued but may not run")
    # in the batch report (step 6). Then run the local-drain fallback below —
    # operator is present right now, so don't just warn and leave it.
    ...
```

`status.is_stale` is `True` for both `"stale"` (an old tick) and `"missing"` (no row yet — pre-Slice-3, or `wake_driver` has never ticked). The row is already durably enqueued regardless of driver liveness, so a stale heartbeat never blocks or retries the enqueue itself — but per the #1085 Slice 3 design, a stale heartbeat with an operator present is exactly the case the local-drain fallback exists for: don't leave freshly-enqueued rows sitting behind a driver that may not be ticking.

**On `status.is_stale`**, call `agents.task_dispatch.local_drain_until_terminal` with the task ids enqueued this batch (from each `enqueue()` row's `task_id` in step 3):

```python
from agents.task_dispatch import local_drain_until_terminal

final_statuses = local_drain_until_terminal(enqueued_task_ids)
# Blocking, operator-present is expected here — see the function's docstring
# for the ceiling: marker on the heartbeat-check-then-spawn race window (no
# distributed lock) and the DEFAULT_LOCAL_DRAIN_MAX_ITERATIONS cap.
```

This repeats a `wake_driver --once` tick, re-checking the heartbeat before each spawn, until every enqueued row in this batch reaches a terminal `task_queue` state (`done`/`failed`/`parked`/`skipped_duplicate`) or the heartbeat goes fresh again (resident driver recovered — stop, let it take over) or the iteration cap is hit. Report the final per-row statuses in step 6 alongside `WARN_MESSAGE`; a row still non-terminal after the loop is reported as such, not silently dropped.

This local drain also keeps the batch's rows out of the 6h reaper's false-fail path — operator-device spawns launched this way never fold into the resident driver's own completion map, so without an explicit drain-to-terminal here they'd otherwise look abandoned to the reaper. See #1085 Slice 3 design note in the issue body.

### 4. Record decision

Apply the `record_decision` contract from user-level CLAUDE.md. One call covers the batch — which issues enqueued, which refused, which collided, which stayed inline, why. Batch dispatch satisfies trigger #1 (issue implementation, even though the "implementation" itself is deferred to a headless worker) — non-optional.

### 5. Implement inline issues (parallel with the queue draining independently)

While enqueued issues wait for `drain_tasks` to pick them up, use the `/implement` pipeline for anything kept inline. The two streams are independent — this skill does not block on queue drain.

### 6. Report

Batch summary to the principal:

```
#604 enqueued (task_id=<id>)
#613 inline — dispatched via /implement instead
#617 enqueued (task_id=<id>)
```

If step 3b found the driver stale, prepend `WARN_MESSAGE` to the batch report so the principal sees it before the per-issue lines, not buried after them.

No further action from this skill. Outcome recording for *enqueued* rows
happens post-merge in `/verify` (#1085 S2-5) — enqueue is not completion,
so this skill does not call `outcome_record` on the enqueued/collided
success paths (it does on refusal, per §Contract above, since that's a
terminal-for-this-skill diagnostic event).

## Safety rules
- All `/implement` safety rules apply.
- Never spawn an `Agent` subagent from this skill — that path is retired.
- Never add `status:in-progress` at enqueue time — claiming is `/task-implement`'s job at actual spawn.
- If principal says "параллельно все" but one task is unfit for headless execution → keep it inline and tell the principal why.

## Recovery playbook

See `docs/security/recovery-playbook.md`. Queue-specific:
- Enqueued row stuck `pending` past heartbeat staleness → step 3b already ran `local_drain_until_terminal` at enqueue time if the driver was stale then; if it wasn't stale then but is now, run `agents.driver_heartbeat.check_heartbeat()` directly to confirm, then call `agents.task_dispatch.local_drain_until_terminal([<task_id>])` directly the same way step 3b does, or escalate — `/task-implement`'s escalation path applies once a worker is actually spawned and stuck, not while the row is still `pending`.
- Row `parked` by a readiness refusal at spawn time → fix the cited gap on the issue, re-dispatch at `delegate:<N>:r<k+1>` (never reuse the same key).
