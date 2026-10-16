# Payload under critique — AFK orchestration (milestone 71, Osasuwu/jarvis)

Repo checkout: `C:\Users\petrk\GitHub\jarvis\.claude\worktrees\issue-1073-3bd4a6`.
User-level skills (`/to-tickets`, `/file-issue`, `/triage`, `/implement`, `/dispatch`): `C:\Users\petrk\jarvis-private\skills`.
Other host repo: `Osasuwu/like-current-song` (read via `gh`).

## Problem statement

Unattended (AFK) work — an agent implementing a GitHub issue end-to-end without a human present —
has no working lane. This is the 8th automation design attempt; each earlier one built
infrastructure before a lane was proven at volume. The current lane (`.github/workflows/agent-dispatch.yml`,
`claude-code-action`) has 1 success / 1 failure / 54 cancelled / 222 skipped runs. Interactive
skills (`/implement`) carry interim rules for four coupling points (merge policy by risk; risk
line + `waiting-human-review`; `## Plan` format; `afk:*`/`needs-*` label contract) that this
design must replace with a final contract. The repos are public; issues can be filed by anyone.

## Proposed direction

1. **Canon lane:** jarvis `agent-dispatch.yml` on `claude-code-action`, hardened in place, shipped
   as a reusable workflow in jarvis with a thin caller per host repo. Repo state (protection,
   auto-merge, required checks) read from the API, no repo literals.
2. **Worker identity:** a dedicated GitHub App installation token replaces the operator PAT. App
   permissions: `contents:write`, `pull_requests:write`, `issues:write` only (no workflows,
   checks, statuses, administration). The code-review (`code-gate`) check-run comes from a
   different App. Every required check is pinned to its expected `app_id` in branch protection.
3. **Trigger:** label `agent:dispatch` on an issue. Applied by a human, or by the `/to-tickets`,
   `/file-issue`, `/triage` skills as their last step when run in an interactive session, only
   when the issue passes intake and has no open blocker. Never applied by an unattended run.
   Blocked issues are not auto-labelled (chaining on blocker close is out of scope).
4. **Intake job** (deterministic, replaces the `/dispatch` skill, which is deleted): a routing
   table keyed by label, one row today (implementation). Refuses with a comment when: any
   `needs-*` label; no `## Acceptance criteria`; `afk:3-human`; `afk:2-plan` without a `## Plan`
   that passes `agents/plan_lock.verify_lock`; issue author lacks write access; issue body edited
   after the label was applied (GraphQL `lastEditedAt` vs label time).
5. **Worker:** reads the issue body only from the `labeled` event payload snapshot, never
   re-reads it and never reads comments. Edits labels only on its own issue/PR, enforced by the
   tool allowlist. Follows a `## Plan` when present; deviation → escalation.
6. **Escalation:** worker adds `needs-human`, removes `agent:dispatch`, comments the blocker with
   the `run_id`, job ends red. Assignees never touched. Re-dispatch = human removes `needs-human`
   and re-applies `agent:dispatch`.
7. **Merge by risk:** PR body line `Risk: LOW|MEDIUM|HIGH|CRITICAL — <reason>`. New required check
   `risk-tier` (in `pr-body-check.yml`): fails if the line is missing; computed tier from the diff
   = machinery paths (`.github/**`, `AGENTS.md`, `.claude/**`, gate scripts, test deletions,
   dependency manifests) plus `agents/plan_classifier` ordinal (3→HIGH, 2→MEDIUM, 1→LOW);
   final = max(computed, declared). LOW/MEDIUM auto-merge on green required checks. HIGH/CRITICAL:
   the check stays red until a human with write access (not the worker App) approves;
   `waiting-human-review` label applied for visibility. Same rule for AFK and interactive PRs.
8. **Plan authoring:** the existing planner agent + critic panel (`.claude/agents/planner.md`,
   `critic-*.md`) run only interactively and write a `plan_lock`-grammar `## Plan` (heading,
   `- ` steps, `lock: <hash>`) into the issue body; the AFK lane never runs them.
   `scripts/plan_review_diff_gate.py` and its test are deleted.
9. **Label contract:** `agent:dispatch` trigger; no `afk:*` = class 1 AFK-eligible; `afk:2-plan` =
   AFK only with a locked plan; `afk:3-human` = never AFK (all `afk:*` applied by `/to-tickets`);
   `needs-*` blocks intake; `needs-human` = escalation; `waiting-human-review` = PR hold visibility.
10. **Hosts and rollout:** GitHub-hosted runners. jarvis first (2–3 smoke runs, one deliberately
    HIGH), then like-current-song immediately. Other repos only after the N-run gate. Private
    repos never AFK hosts for now.
11. **N-run gate:** no new infrastructure until 10 real runs across both host repos (≥3 per
    repo). Real run = dispatched on a backlog issue not created to test the lane. Every run must
    end in an artifact (PR merged/held, or escalation comment with `run_id`). Gate passes when ≥6
    of 10 PRs merge without a human editing their code. Counting starts once App identity,
    merge-by-risk and the trust boundary are in. Fixed: action version, model, `--max-turns`.
    Varied: host repo, task class (1 / 2-with-lock), trigger source (human / skill). Recorded:
    risk tier, diff size, concurrent runs, outcome (merged/held/escalated/refused/no-artifact).
    Before the gate only lane-defect fixes, attack-path controls and deletions are built.
    Existing unexplained `cancelled`/`skipped` runs are triaged before counting.
12. **Deferred:** research lane and other non-code lanes (#1941); planner in AFK (#1573);
    self-hosted runners for private repos; dependent-issue chaining; cost/quota measurement
    (#1809) is a precondition for scaling past N, not for starting.

## Acceptance criteria (milestone, as drafted)

- [ ] Cleanup slice first: `/dispatch` skill deleted; `plan_review_diff_gate.py` + test deleted; stale CONTEXT entries removed.
- [ ] Worker runs as the dedicated App; operator PAT removed from the lane; required checks pinned to `app_id` in jarvis and like-current-song.
- [ ] Lane is a reusable workflow in jarvis; thin callers in jarvis and like-current-song.
- [ ] Intake refuses (with comment) every condition in direction §4; each refusal path has a test.
- [ ] Worker reads only the label-event snapshot; label edits limited to its own issue/PR by allowlist.
- [ ] Escalation per §6; no assignee writes.
- [ ] `risk-tier` required check per §7, in both host repos; HIGH/CRITICAL cannot merge without a write-access human approval.
- [ ] `/to-tickets`, `/file-issue`, `/triage` apply `agent:dispatch` per §3; never in unattended runs.
- [ ] `/implement` interim AC2/AC3/AC3a replaced by pointers to the contract; AC2a (`--admin` deny hook) stays.
- [ ] `threat-model.md` names the trust boundary; `docs/reference/afk-orchestration.md` holds the readable contract.
- [ ] Unexplained cancelled/skipped runs triaged before counting starts.
- [ ] N-run gate executed and its result recorded per §11.
