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
python -m agents.scheduler                              # production: tick every 60s + jitter
python -m agents.scheduler --interval 30                # override interval
python -m agents.scheduler --once                       # fire one tick and exit
python -m agents.scheduler --once --dry-run             # traverse graph, skip 'claude -p'
python -m agents.scheduler --interval 60 --jitter 5     # explicit timing
python -m agents.scheduler --placeholder                # (dev) also register canary tick
```

Production CLI (``python -m agents.scheduler``) registers the dispatcher
with the default 60s interval and 10s jitter. The ``--placeholder`` dev
flag (off by default) also registers the canary tick — a test fixture
that verifies the jobstore pickle contract across restarts.

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

### Postgres prerequisite

The scheduler service requires a Postgres database to persist APScheduler jobs.
The dispatcher itself writes to Supabase; **Postgres is only for APScheduler's
jobstore and LangGraph's checkpoint tables**. Choose one of the two paths below:

#### Option 1: Docker Compose (recommended for dev/demo)

```bash
docker compose -f docker-compose.agents.yml up -d
docker compose -f docker-compose.agents.yml ps   # expect 'healthy'
```

This exposes Postgres on `localhost:5433`. The default `AGENTS_POSTGRES_URL`
in `agents/config.py` matches this port, so no env override is needed.

#### Option 2: Native install (winget PostgreSQL 18)

If you prefer a native system Postgres install (e.g., for production):

```powershell
winget install PostgreSQL.PostgreSQL.18
```

This installs Postgres on the default port `5432`. After installation, create
the `jarvis` role and `agents` database:

```powershell
# Open a Postgres prompt as the system admin:
psql -U postgres

# Then in the psql shell, run:
CREATE ROLE jarvis WITH LOGIN PASSWORD 'jarvis';
CREATE DATABASE agents OWNER jarvis;
\q
```

Then override the env var for the service to point at port 5432:

```powershell
nssm set jarvis-scheduler AppEnvironmentExtra "AGENTS_POSTGRES_URL=postgresql://jarvis:jarvis@localhost:5432/agents?sslmode=disable"
Restart-Service jarvis-scheduler
```

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

### Resolving the `claude` binary under LocalSystem (issue #385)

The dispatcher spawns `claude -p` for each tier-1 auto-dispatch row. NSSM
runs the service as `LocalSystem`, whose PATH is sparse — `shutil.which`
fails and every tick records `failure:FileNotFoundError` in `audit_log`.

`agents.dispatcher._resolve_claude_binary` resolves the executable in this
order: explicit override arg → `JARVIS_CLAUDE_BIN` env var → `shutil.which` →
documented Windows install paths (`%LOCALAPPDATA%\Programs\claude\`,
`%USERPROFILE%\.local\bin\`, `%APPDATA%\npm\`). Set the env var on the
service if your install lives elsewhere or if you want a hard pin:

```powershell
# Locate claude on this device, then attach to the service:
$claudeBin = (Get-Command claude).Source
nssm set jarvis-scheduler AppEnvironmentExtra "JARVIS_CLAUDE_BIN=$claudeBin"
Restart-Service jarvis-scheduler
```

Verify with `python -m scripts.observability.morning_check` after a few
ticks — `task-dispatcher` should report `success` outcomes, not
`failure:FileNotFoundError`.

### Running under a non-default account (issue #410)

LocalSystem cannot read user-scoped Claude Max session credentials at
`%USERPROFILE%\.claude\.credentials.json`. If the dispatcher needs them
(every tier-1 row that spawns `claude -p` does), the service has to run
under the user account that owns those credentials.

Switching the service account on Windows hits a sharp edge: even with
the **correct** password, `sc.exe config` and NSSM return error 1326
("logon failure for .\username with current password") when the
account is missing the **SeServiceLogonRight** privilege ("Log on as a
service"). The services.msc GUI grants it implicitly when you re-enter
the password through the Log On tab; `sc.exe` does not. This bit
workshop deploy on 2026-04-25.

The install script handles both halves of the dance via two opt-in
parameters:

```powershell
# Grant the right, set NSSM ObjectName, password handled in-process.
$pw = Read-Host -Prompt "Password for .\PC4_v" -AsSecureString
.\scripts\install\install-scheduler-service.ps1 `
    -ServiceAccount '.\PC4_v' `
    -ServicePassword $pw

# Or grant the right only; set the password later via services.msc:
.\scripts\install\install-scheduler-service.ps1 -ServiceAccount '.\PC4_v'
# Then: services.msc -> jarvis-scheduler -> Log On tab -> enter password.
```

Both forms are idempotent: if the account already has the right, the
secedit round-trip detects it and no-ops. The script must run from an
elevated PowerShell session so secedit can read/write the local
security policy. `-DryRun` extends to the secedit operations and
prints what it would do without mutating the policy.

LocalSystem stays the default. Don't pass `-ServiceAccount` unless you
specifically want the dispatcher to run under a user account.

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
# Should show task-dispatcher with a future next_run_time.

# Shell 1 again
python -m agents.scheduler --interval 30 --jitter 0
# Job should resume from persisted next_run_time, not restart the interval.
```

## Startup reaper

The scheduler's ``run()`` function performs a one-shot cleanup on startup:
it enumerates all persisted jobstore rows and removes any whose `id` is
not in the set of currently-registered agent ids. This guards against
drift if an agent is renamed or removed — orphan rows won't accumulate
forever. Each reaped job is logged at INFO level.
