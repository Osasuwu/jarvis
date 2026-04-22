# Scheduler primitive

Module: `agents/scheduler.py`. Ships as **S2-5** (issue #300) — the run-loop
engine that fires persistent agents on an interval. Dispatcher (S2-3, #298)
is the first consumer; future agents register via `register_agent()`.

## Why APScheduler

Claude Code Routines run Claude Code. Our agents are Python/LangGraph
talking to Ollama + Supabase — a different process, a different runtime.
APScheduler is in-process, uses the Postgres we already run for LangGraph
checkpoints, and survives restart.

## Usage

```python
from agents import scheduler

handle = scheduler.build_scheduler()          # reads AGENTS_POSTGRES_URL
scheduler.register_agent(
    handle,
    agent_id="task-dispatcher",
    fn=dispatcher_tick,                       # plain callable, no args
    interval_seconds=60,
    jitter_seconds=10,
)
handle.scheduler.start()
# ... main thread blocks / does other work ...
```

The returned `SchedulerHandle` is a frozen dataclass with the live
`BackgroundScheduler` and its jobstore alias. Keep it to add more jobs
or shut down.

## CLI

```bash
python -m agents.scheduler                   # tick every 60s + jitter
python -m agents.scheduler --interval 30     # override
python -m agents.scheduler --once            # fire one tick and exit
```

CLI runs `_placeholder_tick` — a log-only proof-of-life. Once the
dispatcher lands in S2-3, its entry point registers the real job
alongside.

## Restart semantics

- `replace_existing=True` — a re-registered `agent_id` replaces the
  persisted row; no duplicate.
- `max_instances=1` — two ticks of the same agent never overlap.
- `coalesce=True` — a backlog (scheduler was asleep N minutes) collapses
  to one catch-up run.
- `jitter` — avoids lockstep between devices hitting the same DB.

Combined: kill the process mid-tick, restart → APScheduler reads the
persisted job, resumes; the idempotency key from `agents/safety.py` is
the final guard against double-dispatch.

## Table co-existence with LangGraph

| Owner | Table |
|-------|-------|
| APScheduler | `apscheduler_jobs` (plus `apscheduler_jobs_history` if enabled) |
| LangGraph (`PostgresSaver`) | `checkpoints`, `checkpoint_writes`, `checkpoint_blobs` |

Disjoint sets — they share the database, not the namespace. Smoke-test
locally by starting `python -m agents.scheduler --once` and then
`python -m agents.event_monitor` in any order; neither should disturb
the other's rows.

## Windows signal gotcha

`SIGTERM` is exposed as a constant on Windows Python but installing a
handler raises `ValueError` (the OS doesn't have a Unix-style term
signal). `_install_signal_handlers` swallows that — Ctrl-C still
triggers `KeyboardInterrupt` in `run()`.

## Manual smoke test — restart recovery

The kill-mid-tick/restart path needs two shells and a live Postgres.
Can't automate inside pytest without flaky OS-specific plumbing.

```bash
# Shell 1
python -m agents.scheduler --interval 30 --jitter 0
# [wait for one tick logged, then Ctrl-C or kill the process]

# Shell 2 — same DB, check the jobs table:
psql "$AGENTS_POSTGRES_URL" -c 'select id, next_run_time from apscheduler_jobs;'
# Should show scheduler-placeholder with a future next_run_time.

# Shell 1 again
python -m agents.scheduler --interval 30 --jitter 0
# Job should resume from persisted next_run_time, not restart the interval.
```
