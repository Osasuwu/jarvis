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
and does **not** write back to that file, so it goes stale. First iteration fails immediately with
`Failed to authenticate: OAuth session expired and could not be refreshed` (confirmed 2026-08-08
against jarvis#1461). Fix: run `claude auth login` once in a normal terminal (outside any
host-managed session) to rewrite the file with independently-refreshable tokens, then re-run.
There is no headless fix — the OAuth flow can't be driven non-interactively, and switching to
API-key auth is off the table without explicit consent (metered billing invariant).

## Where it lives

- Driver: [`scripts/ralph-loop.ps1`](../../scripts/ralph-loop.ps1)
- Logs: `logs/ralph-loop/<run-id>-{prompt.txt,summary.log,iterN.json}` (gitignored)
- State: `working_state_jarvis` in Supabase memory — same surface `/end`, `/grill`, and `/implement`
  already read/write. No new state file.

## How to start it

```powershell
./scripts/ralph-loop.ps1 -Task "Implement jarvis issue #1460 end to end via /implement" -MaxIterations 6
```

Useful flags: `-MaxBudgetUsdPerIteration <usd>` (per-iteration spend cap, default 3.0), `-Model
<alias>` (default `sonnet`), `-DryRun` (write the prompt file, print it, spawn nothing).

Each iteration's prompt instructs the fresh agent to: recall `working_state_jarvis` first (so it
picks up exactly where the prior iteration left off, not a stale plan), do one coherent unit of
verifiable progress, write the new state back to `working_state_jarvis` before finishing, and end
its final message with exactly `RALPH_STATUS: COMPLETE` or `RALPH_STATUS: CONTINUE`.

## How to stop it

Ctrl-C the running process — an in-flight `claude -p` iteration is not resumed automatically. What
it already wrote to `working_state_jarvis` and git stays; nothing is rolled back. To resume, just
re-run the same command — the next iteration recalls `working_state_jarvis` and continues from
there.

The driver also stops itself and exits non-zero on: a failed iteration (`claude` exit code != 0), a
missing status sentinel (treated as a stall), or reaching `-MaxIterations` without `COMPLETE`. In
every case, check `logs/ralph-loop/<run-id>-summary.log` before re-running — state already
persisted in `working_state_jarvis`, so a re-run is a genuine continuation, not a restart.

## Known limitation — host-managed session auth

See *Prerequisite* above. Full mechanism in memory `claude_p_subprocess_auth_fails_host_managed_session`.
