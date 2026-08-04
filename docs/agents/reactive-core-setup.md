# Reactive-core Agents — Dev Setup

Federation & Delegation pillar (milestone #44). The reactive-core loop wakes on
Postgres `LISTEN/NOTIFY`, routes each event through a deterministic orchestrator,
and spawns `claude -p` workers for coding tasks. Agents run alongside Claude Code
(not as a replacement) and share state with it through Supabase — the events,
`task_queue`, memories, goals, and `audit_log` tables are the same rows Claude
Code reads via `memory_recall` / `events_list` / `goal_list`.

This document covers local setup: dependencies, environment, and running the loop.

## Prerequisites

- Python 3.11+ (project requirement)
- A Supabase project (shared knowledge base) **or** a local `supabase start`
  stack — the `events` / `task_queue` NOTIFY triggers that wake the driver live
  in `supabase/migrations/`
- Ollama (optional, staged-dormant — no live consumer yet) — see
  [ollama-setup.md](ollama-setup.md)

## Install dependencies

From repo root:

```bash
pip install -e ".[agents]"
```

This pulls:

| Package | Purpose |
|---------|---------|
| `psycopg[binary,pool]` | Direct-Postgres driver — the `LISTEN/NOTIFY` socket wake_driver opens (the PostgREST client can't `LISTEN`) |
| `supabase` | Agent bridge to the shared knowledge base (memories, events, `task_queue`, goals, `audit_log`) |
| `httpx` | GitHub Events API client |
| `ollama` | Official Python client — **staged-dormant**, no live consumer yet (see [ollama-setup.md](ollama-setup.md)) |

## Configure environment

Copy the relevant lines from `.env.example` into `.env`:

```
# Direct-Postgres session-mode DSN — wake_driver's LISTEN/NOTIFY socket.
AGENTS_POSTGRES_URL=postgresql://postgres:[YOUR-PASSWORD]@db.your-project-ref.supabase.co:5432/postgres

# Supabase bridge — same vars the MCP memory server uses; re-used here.
SUPABASE_URL=https://<project>.supabase.co
SUPABASE_KEY=<anon-or-service-key>

# Optional — Ollama local inference (staged-dormant, no live consumer yet)
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=qwen3:4b
```

`AGENTS_POSTGRES_URL` needs a **session** connection — a direct
`db.<ref>.supabase.co:5432` or session-pooler `:5432` endpoint, **never** the
transaction pooler `:6543` (transaction mode drops `LISTEN`). The direct
endpoint may be IPv6-only on newer projects. There is **no default**:
`wake_driver._build_psycopg_queue()` raises a clear `RuntimeError` naming the
var if it's unset, mirroring the `SUPABASE_URL` / `SUPABASE_KEY` fail-loud
contract. See `.env.example` for the full comment.

### Local Supabase (optional)

To run against a local stack instead of the cloud project:

```bash
supabase start          # boots local Postgres + PostgREST
supabase db reset       # applies supabase/migrations/ (events + task_queue NOTIFY triggers)
```

Point `AGENTS_POSTGRES_URL` at the local session endpoint (`supabase status`
prints the DB URL). The NOTIFY triggers that wake the driver ship in
`supabase/migrations/` — a bare Postgres without them will never fire a wake.

## Run the loop

```bash
# Long-running: LISTEN on the events channel, drain tasks, watchdog stale rows.
python -m agents.wake_driver

# One-shot tick (watchdog + drain, then exit) — smoke test.
python -m agents.wake_driver --once

# Custom watchdog / wait-for-wake timeout (seconds).
python -m agents.wake_driver --watchdog-seconds 120
```

The driver `LISTEN`s on the `events` channel; each `NOTIFY` (fired by the
`notify_events_insert` trigger on `events` insert) wakes a tick. A tick
re-claims stale rows, drains pending events through `orchestrator.handle_event`,
enqueues the resulting `task_queue` rows, and spawns `claude -p` workers via
`executor.spawn`. Ctrl-C stops cleanly.

`SUPABASE_URL` / `SUPABASE_KEY` have no default — the Supabase bridge fails
loudly (`RuntimeError`) if an agent tries to call Supabase without them.

## Production deploy / teardown

`scripts/install/register-wake-driver.ps1` registers a Windows Task Scheduler
entry that runs `python -m agents.wake_driver` (the long-running loop, not
`--once`) as a supervised daemon: starts at logon, restarts on crash, and
sets `JARVIS_PRINCIPAL=autonomous` on the launched process — see
[../security/agent-boundaries.md](../security/agent-boundaries.md). It is a
thin restart wrapper, not a resident poller — the loop itself stays
event-driven via `LISTEN/NOTIFY`.

```powershell
# Register (idempotent — safe to re-run after a script update).
scripts/install/register-wake-driver.ps1

# Inspect the plan without registering anything.
scripts/install/register-wake-driver.ps1 -WhatIfOnly

# Custom watchdog / wait-for-wake timeout (seconds), default 300.
scripts/install/register-wake-driver.ps1 -WatchdogSeconds 120
```

The script is device-guarded to the Workshop PC (`config/device.json`'s
`name`) — the single-driver invariant in `agents/pid_sidecar.py` assumes
exactly one supervised instance, and Workshop is the production target for
always-on agents. Pass `-Force` to register on another device for dev
rehearsal. No Workshop-specific paths/IPs/usernames are hardcoded in the
script itself — `RepoRoot` and the Python interpreter are resolved from the
local machine at registration time.

The earlier NSSM `jarvis-scheduler` resident service was retired in #743 (the
loop is event-driven, not a resident poller). If a device still has that service
registered, remove it cleanly:

```powershell
scripts/install/uninstall-scheduler-service.ps1
```

## Architecture notes

### Why a direct-Postgres socket, not the Supabase client?

The wake signal is Postgres `LISTEN/NOTIFY`. PostgREST (what `supabase-py`
speaks) cannot hold a `LISTEN` — it's stateless HTTP. So wake_driver opens one
direct `psycopg` session connection for the wake channel, while everything else
(reads, task rows, audit) rides `supabase-py`. That split is why
`AGENTS_POSTGRES_URL` and `SUPABASE_URL` are both required and point at the same
project through different endpoints.

### Why a separate Supabase bridge (not MCP)?

MCP is Claude Code's protocol; it isn't available outside a Claude session.
`agents/supabase_client.py` is a thin wrapper over `supabase-py` exposing the
subset of reads/writes agents need. Both sides hit the same tables, so what an
agent writes shows up in Claude Code's `memory_recall` / `events_list` /
`goal_list` and vice versa. Agent writes to `audit_log` set `agent_id`; MCP
writes leave it NULL — the column doubles as the actor differentiator.

## Troubleshooting

| Symptom | Cause / Fix |
|---------|-------------|
| `RuntimeError: AGENTS_POSTGRES_URL is not set` | Set the direct-Postgres session DSN in `.env` — see *Configure environment*. |
| Driver wakes but never spawns a task | NOTIFY triggers missing from the target DB — apply `supabase/migrations/` (`supabase db reset` locally). |
| `LISTEN` returns no notifications | DSN points at the transaction pooler `:6543` — switch to a session `:5432` endpoint. |
| Supabase bridge `RuntimeError` on startup | `SUPABASE_URL` / `SUPABASE_KEY` unset — the bridge fails loud by design. |
