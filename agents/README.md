# agents/

Pillar 7 persistent LangGraph agents. Each module is a standalone agent
that runs alongside Claude Code (not as a replacement), uses Ollama as
the local LLM, and persists state in PostgreSQL via LangGraph's
`PostgresSaver` checkpointer.

See `docs/agents/` for per-module operational notes and architectural
detail. Per-module contents:

| Module | Doc | Role |
|--------|-----|------|
| `config.py` | — | `load_config()` — Postgres/Supabase URLs from env |
| `dispatcher.py` | [`docs/agents/dispatcher.md`](../docs/agents/dispatcher.md) | Task dispatcher (S2-3) — polls `task_queue`, spawns `claude -p <goal>` with sanitized env |
| `escalation.py` | [`docs/agents/escalation.md`](../docs/agents/escalation.md) | First-match triggers (S2-4) used by the dispatcher |
| `event_monitor.py` | [`docs/agents/langgraph-setup.md`](../docs/agents/langgraph-setup.md) | GitHub event monitor — fetch → classify → store |
| `github_client.py` | — | Thin wrapper over `gh` CLI / GitHub Events API |
| `ollama_client.py` | [`docs/agents/ollama-setup.md`](../docs/agents/ollama-setup.md) | Local LLM client |
| `safety.py` | [`docs/agents/safety.md`](../docs/agents/safety.md) | Identity + tier classifier + audit log (S2-0) |
| `scheduler.py` | [`docs/agents/scheduler.md`](../docs/agents/scheduler.md) | APScheduler run-loop engine (S2-5) |
| `supabase_client.py` | — | Supabase `get_client()` + `audit()` + `list_events()` |
| `usage_probe.py` | [`docs/agents/usage_probe.md`](../docs/agents/usage_probe.md) | 5h Claude Max budget probe (S2-2) |

## Running the dispatcher

Single tick (requires `DATABASE_URL` / `SUPABASE_*` env vars set)::

    python -m agents.dispatcher                 # real dispatch
    python -m agents.dispatcher --dry-run       # graph traversal, no subprocess
    python -m agents.dispatcher --thread prod   # override thread_id

As a scheduled job (S2-5 APScheduler)::

    from agents import scheduler, dispatcher

    handle = scheduler.build_scheduler()
    dispatcher.register(handle, interval_seconds=60)
    handle.scheduler.start()

## Running tests

Unit tests (no live services — run on every CI commit)::

    pytest tests/test_agents_*.py -x -q

End-to-end integration tests (opt-in, require live Supabase + Postgres):

    # Event monitor E2E (#175)
    AGENTS_E2E=1 pytest tests/test_agents_integration.py -v

    # Dispatcher E2E (#301) — proves S2-0..S2-5 compose correctly
    AGENTS_E2E=1 pytest tests/test_agents_dispatcher_e2e.py -v

E2E tests:

- Skipped by default (`pytestmark` guards on `AGENTS_E2E != "1"`) so CI
  stays green without infrastructure.
- Hermetic — every test tags its rows with a UUID marker embedded in
  `goal` / `target` / `title`, then sweeps them in teardown. Concurrent
  runs (two dev machines, CI + local) don't collide.
- Mock only the subprocess boundary (`agents.dispatcher.subprocess.Popen`)
  so we never spawn a real `claude -p` during the test. Supabase and
  LangGraph checkpointing run for real — the whole point is to prove the
  bridge works end-to-end.

Owner smoke-test (real `claude -p` dispatch) stays manual per #301 "out
of scope" — document the steps in the PR description if needed.

## Environment

Required env vars (loaded from `.env` by each module's `main()`)::

    DATABASE_URL=postgresql://user:pass@host:5432/db
    SUPABASE_URL=https://<project>.supabase.co
    SUPABASE_KEY=<service-role-or-anon>

Optional::

    TASK_DISPATCHER_DRY_RUN=1   # set by dispatcher.register(dry_run=True)
    AGENTS_E2E=1                 # opt in to E2E suite
