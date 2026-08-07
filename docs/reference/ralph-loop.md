# Ralph-loop — pull-only reference

Evicted from the always-loaded [`docs/context/invariants.md`](../context/invariants.md) by
[#1461](https://github.com/Osasuwu/jarvis/issues/1461). Describes a driver for long, multi-phase
work that would otherwise thrash on autocompaction — pull this file when starting a long task, or
debugging a stalled/failed ralph-loop run.

## What it is

`scripts/ralph-loop.ps1` runs a task through repeated, genuinely fresh `claude -p` invocations
instead of one long session. Each iteration is a brand-new process — no `--continue`/`--resume`/
`--session-id` — so there is nothing for that iteration to compact. Progress persists externally in
jarvis `working_state` (Supabase memory via `mcp__memory` tools), not in any LLM's context window.

This is the "Ralph Wiggum" technique (Geoffrey Huntley, 2025): a dumb outer loop feeding the same
task prompt to a fresh agent every round, relying on external state rather than in-context memory.
Chosen over pre-built ralph frameworks (Linear-backed, `PRD.md`-backed, `IMPLEMENTATION_PLAN.md`-backed)
because every one of them owns its own state file/service that would duplicate `working_state`
instead of reusing jarvis's existing handoff surface — decision recorded against jarvis#1461.

## Prerequisite — fresh CLI auth

`ralph-loop.ps1` spawns `claude -p` child processes. If you're driving it from inside a
host-managed Claude Code session (desktop app, VS Code extension), those children read
`~/.claude/.credentials.json` directly — and the host session's OAuth refresh happens out-of-band
and does **not** write back to that file, so it goes stale. Every iteration then fails immediately
with `Failed to authenticate: OAuth session expired and could not be refreshed` (confirmed
2026-08-08 against jarvis#1461).

Fix: run `claude auth login` once in a normal terminal (outside any host-managed session) to
rewrite the file with independently-refreshable tokens, then re-run. There is no headless fix — the
OAuth flow can't be driven non-interactively, and switching to API-key auth is off the table
without explicit consent (metered billing invariant). Symptom to watch for: iteration 1 failing in
~30s with zero token usage. That's auth, not the task.

## Per-iteration startup floor

Every iteration pays a fixed startup cost before doing any work. Measured 2026-08-08 on Main PC
with a trivial no-op prompt: **~66k tokens and ~$0.21**, against a ~136k auto-compact trigger. So an
iteration has roughly **70k of usable window** — that budget is what the one-phase-per-iteration
rule is sized against.

Budget accordingly: `-MaxBudgetUsdPerIteration` set too low produces `error_max_budget_usd` on
startup overhead alone, which looks like a task failure but isn't.

**The slim MCP profile does not help here.** [`mcp-slim-profile.md`](mcp-slim-profile.md) suggests
wiring `--mcp-config config/mcp-slim.json --strict-mcp-config` into these iterations, but its ~90k
baseline was measured *inside a host-managed desktop session*, where claude.ai connectors (Browser,
visualize, `ccd_*`) dominate the tool surface. Headless `claude -p` never loads those. A/B on
identical no-op prompts, same cwd, same model:

| profile | startup context |
|---|---|
| `mcp-slim.json` + `--strict-mcp-config` | 66 815 |
| full registered surface | 65 555 |

No gain, within noise. The driver therefore leaves `-McpConfig` empty by default; pass a profile
path to opt in. Note `--mcp-config` alone only *adds* servers — it needs `--strict-mcp-config` to
replace the surface, and the driver passes both together or neither.

## Where it lives

- Driver: [`scripts/ralph-loop.ps1`](../../scripts/ralph-loop.ps1)
- Logs: `logs/ralph-loop/<run-id>-{prompt.txt,summary.log,iterN.json}` (gitignored)
- State: `working_state_jarvis` in Supabase memory — same surface `/end`, `/grill`, and `/implement`
  already read/write. No new state file.

## How to start it

```powershell
./scripts/ralph-loop.ps1 -Task "Take jarvis issue #1455 from grill through merged PR" -MaxIterations 6 -PermissionMode bypassPermissions
```

Useful flags: `-MaxBudgetUsdPerIteration <usd>` (per-iteration spend cap, default 5.0), `-Model
<alias>` (default `sonnet`), `-PermissionMode` (default `acceptEdits`), `-DryRun` (write the prompt
file, print it, spawn nothing).

**On `-PermissionMode`**: `acceptEdits` auto-approves file writes *inside the project dir only*, and
nothing else. Real implementation work also runs `git`, `gh`, `pytest` — each of which would block
on a permission prompt that no one is there to answer, hanging the iteration until its budget cap
kills it. For genuinely unattended runs pass `bypassPermissions`. Note this does **not** lift the
`.claude/*` manual-confirmation rule — that's enforced separately, not by the permission mode.

## Phase awareness — one phase per iteration

The iteration prompt does not say "make progress"; it makes the fresh agent own the whole canonical
jarvis chain (`/reason` → `/grill` → `/to-spec` → `/to-tickets` → `/implement` → `/rework`) and pick
**the earliest phase not yet done**, doing exactly one per iteration.

This matters because of a specific deadlock: `/implement` on an issue where SOUL's grill trigger
checkbox fires with no grill artifact exits `grill_required` and does nothing. A driver whose prompt
just said "implement this issue" would replay that no-op every iteration until `-MaxIterations`,
burning the boot cost each round for zero progress. The prompt names `grill_required` explicitly as
a routing signal — next phase is `/grill`, not a retry.

Chaining phases inside one iteration is prohibited by the prompt for the same reason the loop exists
at all: chaining is what fills the context window. A short iteration that ends cleanly beats a long
one that compacts.

### HITL phases block the loop — `RALPH_STATUS: BLOCKED`

Some phases end at a human: `/grill` waits on owner answers, a PR waits on review sign-off. A fresh
iteration cannot manufacture that input, and `CONTINUE` would make the driver re-spawn a full-price
iteration every round just to re-discover the same missing answer (observed on the first real run:
iteration 1 of #1455 correctly ran `/grill`, posted its questions to the issue for async reply, and
had nowhere to go next). So the sentinel set is three-valued: `COMPLETE`, `CONTINUE`, and `BLOCKED` —
the latter meaning "waiting on a human, stop the loop." The driver exits 3 on it; answer what the
iteration asked for (the summary log names it), then re-run the same command to continue.

## Measuring the no-compaction claim

The loop's whole premise is one context per iteration, so the driver verifies it instead of
asserting it. After each iteration it locates that session's transcript by `session_id` (globbing
`~/.claude/projects/*/<session-id>.jsonl`, rather than reproducing the cwd-mangling scheme) and
counts `"compactMetadata":{"trigger":"auto"` records. Results land in a per-run ledger printed at
exit:

```
Iter Session                              StartCtxK CostUsd Turns Compactions Status
---- -------                              --------- ------- ----- ----------- ------
   1 9dda69c2-3008-49d3-be73-7d0899eb8947         66    1.84    41           0 CONTINUE
```

A non-zero `Compactions` value is a **failure signal even when the iteration produced good work** —
it means that iteration bit off more than one context, and the per-iteration phase needs to shrink.
This is what makes jarvis#1461 AC3 measurable rather than a claim.

`StartCtxK` is the same first-assistant-turn measurement `mcp-slim-profile.md` defines
(`input + cache_read + cache_creation`), and it is what the usable-window budget is computed from —
if it ever climbs, every iteration gets less room to work in before the numbers above go bad.

One parsing caveat the driver handles: stderr is merged into the captured stream on purpose, so
hook failures and CLI diagnostics land in the iteration log. That makes the capture invalid JSON as
a whole — a single `SessionEnd hook … failed` warning is enough to break a naive
`ConvertFrom-Json`. The driver extracts the one JSON result object out of the mixed stream instead.

## How to stop it

Ctrl-C the running process — an in-flight `claude -p` iteration is not resumed automatically. What
it already wrote to `working_state_jarvis` and git stays; nothing is rolled back. To resume, just
re-run the same command — the next iteration recalls `working_state_jarvis` and continues from
there.

The driver also stops itself and exits non-zero on: a failed iteration (`claude` exit code != 0,
exit 1), a missing status sentinel (treated as a stall, exit 1), `RALPH_STATUS: BLOCKED` (waiting on
a human, exit 3), or reaching `-MaxIterations` without `COMPLETE` (exit 2). In every case, check
`logs/ralph-loop/<run-id>-summary.log` before re-running — state already persisted in
`working_state_jarvis`, so a re-run is a genuine continuation, not a restart.

One host-specific hazard the driver defuses itself: PowerShell wraps a native command's stderr lines
in ErrorRecords under `2>&1`, and a host running `$ErrorActionPreference = 'Stop'` (e.g. the Claude
Code PowerShell tool) turns the first such record into a terminating error — a single benign
`SessionEnd hook … failed` warning killed the whole driver mid-iteration on the first real run,
losing a completed iteration's result. The invocation now relaxes the preference around the native
call only and normalizes the stream to plain strings.

Budget exhaustion and a genuine crash both exit non-zero, so the driver reads `subtype` out of the
result JSON and reports them differently — `error_max_budget_usd` prints an explicit "raise
`-MaxBudgetUsdPerIteration` and re-run" hint. Don't read a budget stop as the task failing: the
iteration's own checkpoint is already in `working_state_jarvis`, and re-running resumes from it.

## Known limitation — host-managed session auth

See *Prerequisite* above. Full mechanism in memory `claude_p_subprocess_auth_fails_host_managed_session`.
