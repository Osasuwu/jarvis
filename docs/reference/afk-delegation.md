# AFK lane & delegation mechanics — pull-only reference

How the unattended lane behaves, for sessions that are mostly not dispatching. Pull this file when
running `/dispatch`, reviewing a lane PR, or debugging a run of
[`agent-dispatch.yml`](../../.github/workflows/agent-dispatch.yml). The lane is
`claude-code-action` on a GitHub-hosted runner: `intake` → `worker` → `publish` / `escalate` /
`ledger`. Decisions D1–D17 behind it: [`docs/decisions/2026-Q4.md`](../decisions/2026-Q4.md).

The supervisor, task-queue, Docker/Sandcastle and pause-switch rules that used to live here went
with the reactive-core demolition (#1802); `git log -- docs/reference/afk-delegation.md` has them.

## Verify subagent work via diff, not self-report

Agents hallucinate when files don't exist. Check `git diff` before trusting a subagent's account
of what it changed — and for a lane run, read the PR's diff and check results, not the worker's
`pr-body.md`.

## The worker writes files; deterministic steps do every GitHub write

The worker holds a read-only token and is denied `git push` (D4). It commits locally and leaves
`lane-out/` behind; `publish` pushes `claude/issue-N-<run_id>` and opens the PR with the bot PAT.
A fix that has the worker push, comment or label is wrong by construction — change a post-step.

**Zero commits is never a silent no-op.** A run that passes intake and ends without a PR — the
worker escalated, crashed, timed out or ran out of turns — gets `needs-human` and one comment
naming the cause (`escalate` job, D3). A runner crash that kills that job too shows up only as a
`no-artifact` ledger row.

## Issue labels are the lane's state

There is no queue table: the issue's labels are the truth, and the lane owns their transitions
(D14). Intake swaps `agent:dispatch` for `status:in-progress`; escalation sets `needs-human` and
clears in-progress; the PR moves it to `status:review`. Intake refuses an issue that is closed,
`status:in-progress`/`review`/`rework-in-progress`, `needs-human`, has an open PR closing it, or an
open blocker (D8). Re-dispatch = a human clears `needs-human` and re-applies `agent:dispatch`;
editing the labels by hand mid-run races the lane.

## The model is pinned; a failure is not a reason to swap it

`--model` is fixed in the workflow (F3) and a change resets the N-run gate count (D13), as does a
change of action version or `--max-turns`. There is no retry ladder: a failed run escalates to a
human, who decides whether the issue, not the model, needs changing.

## Stopping the lane

There is no pause switch. Not applying `agent:dispatch` stops new work. To stop the executor
itself, `gh workflow disable agent-dispatch.yml`; cancel a run in flight with `gh run cancel`.
Runs queue one at a time per repo (`queue: max`, `cancel-in-progress: false`), so a re-label
never cancels a running worker.

## Threat model matches defense

Defense should answer the threat model actually in force, not the strongest one imaginable. The
runner is ephemeral and GitHub-hosted, so host-grade hardening adds nothing; the live threat is
prompt injection through the issue body reaching a write-capable token. That is answered
mechanically — read-only worker token (D4), payload-equality body check (D9), Edit-denied paths
— not by prompt rules. See [`docs/security/threat-model.md`](../security/threat-model.md).
