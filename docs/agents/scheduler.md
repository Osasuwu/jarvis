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

## Production deploy (NSSM)

On Windows, use NSSM (Non-Sucking Service Manager) to run the scheduler as
a persistent Windows service. This is the production recommended approach
for issue #368.

### Prerequisites

- Windows 10+ (tested on Windows 11)
- NSSM installed (download from https://nssm.cc/download or `winget install NSSM.NSSM`)
- `config/device.json` populated with `repos_path` on each target machine, or
  environment variables `JARVIS_REPO_PATH` and `JARVIS_PYTHON` set

### One-command install

```powershell
# From the repo root:
.\scripts\install\install-scheduler-service.ps1

# Or with explicit paths:
$env:JARVIS_REPO_PATH = "C:\path\to\jarvis"
$env:JARVIS_PYTHON = "C:\path\to\python.exe"
.\scripts\install\install-scheduler-service.ps1
```

The script is idempotent — run it again to update service parameters without
downtime.

### After install

The service is installed as `jarvis-scheduler`, set to `Automatic` startup.
Start it manually with:

```powershell
Start-Service -Name jarvis-scheduler
```

Or restart Windows to auto-start.

### View logs

Logs are written to `<repo>/logs/scheduler/stdout.log` and `stderr.log`:

```powershell
# Live tail (like `tail -f`):
Get-Content "C:\path\to\jarvis\logs\scheduler\stdout.log" -Tail 50 -Wait

# Or in PowerShell ISE / VS Code with automatic refresh:
Start-Process notepad++ "C:\path\to\jarvis\logs\scheduler\stdout.log"
```

Check `audit_log` table in Supabase for dispatcher tick outcomes.

### Uninstall

```powershell
.\scripts\install\uninstall-scheduler-service.ps1
```

Or manually:

```powershell
Stop-Service -Name jarvis-scheduler
nssm remove jarvis-scheduler confirm
```

### Service restart behavior

- On successful completion: service loops back to sleep for `--interval` seconds
- On exception during tick: service logs the error, drains, and restarts
  (configurable via NSSM `AppExit` / `AppRestartDelay`)
- On signal (Windows service stop): signal handler calls `scheduler.shutdown(wait=True)`,
  allowing in-flight ticks to complete gracefully

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
