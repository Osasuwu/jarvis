# LangGraph Agents — Dev Setup

Pillar 7 persistent agents run alongside Claude Code. LangGraph handles the lifecycle (graph definition, state, checkpointing), Ollama handles inference, local Postgres stores checkpoints.

This document covers the Sprint 1 foundation (issue #172). Agent implementations live in later sprints.

## Prerequisites

- Python 3.11+ (project requirement)
- Ollama running locally — see [ollama-setup.md](ollama-setup.md)
- Docker Desktop (for local Postgres)

## Install dependencies

From repo root:

```bash
pip install -e ".[agents]"
```

This pulls:

| Package | Purpose |
|---------|---------|
| `langgraph` | Graph runtime + state machine |
| `langchain-ollama` | LangChain adapter (reserved for future graph nodes) |
| `langgraph-checkpoint-postgres` | Postgres checkpointer backend |
| `psycopg[binary,pool]` | Postgres driver + connection pool |
| `ollama` | Official Python client (used directly for chat with `think=False`) |

## Start local Postgres

```bash
docker compose -f docker-compose.agents.yml up -d
docker compose -f docker-compose.agents.yml ps   # expect 'healthy'
```

Exposes Postgres on `localhost:5433` (port 5432 left free for any system-wide Postgres).

Credentials in the compose file are dev-only:
- user `jarvis`, password `jarvis`, database `agents`
- data lives in named volume `agents_postgres_data`

To stop without losing checkpoints: `docker compose -f docker-compose.agents.yml stop`.
To wipe state: `docker compose -f docker-compose.agents.yml down -v`.

## Configure environment

Copy the relevant lines from `.env.example` into `.env`:

```
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=qwen3:4b
AGENTS_POSTGRES_URL=postgresql://jarvis:jarvis@localhost:5433/agents?sslmode=disable
```

Defaults in `agents/config.py` match these values, so `.env` is optional for the dev setup. Override when pointing at a different Ollama host or a self-hosted Postgres.

## Run the minimal graph

```bash
# First run: creates checkpoint tables, executes the graph, prints the reply.
python -m agents.main

# Second run in a fresh process: loads the saved state.
python -m agents.main --resume

# Custom thread ID:
python -m agents.main --thread smoke-2
```

Expected output (first run):

```
[run]  thread=demo-thread
[run]  reply:         ok.
[run]  step:          1
[run]  checkpoint_id: 1ef4f797-8335-6428-8001-8a1503f9b875
```

`--resume` in a brand-new Python process should print the same `reply`, `step`, and `checkpoint_id` — that is what validates "survives restart".

## Architecture notes

### Why both `ollama` and `langchain-ollama`?

`ollama` (the official Python client) has first-class support for the `think` parameter needed to disable Qwen3 reasoning. At the time of writing `langchain-ollama`'s `ChatOllama` does not expose `think` cleanly. The minimal graph therefore calls `ollama.Client.chat(..., think=False)` directly through `agents/ollama_client.py`.

`langchain-ollama` stays as a dependency so future graph nodes that need LangChain tool-calling / structured output primitives can adopt it without a new install step.

### Why local Postgres, not Supabase?

See memory `self_hosted_postgres_future_plan`. Sprint 1 uses local Docker Postgres to keep scope tight; migration to a self-hosted Postgres on the workshop server is a separate infra track scheduled for when the home LAN is in place.

### Why port 5433?

Port 5432 is the default for system Postgres installs. Running the dev container on 5433 avoids collisions and lets the two coexist.

## Troubleshooting

| Symptom | Cause / Fix |
|---------|-------------|
| `connection refused` on invoke | Docker not up — `docker compose -f docker-compose.agents.yml up -d` |
| `TypeError: tuple indices must be integers` from checkpointer | psycopg connection not opened via `PostgresSaver.from_conn_string`. Always use the context manager — `main.py` does this already. |
| `message.content` is empty | `think=False` was dropped — see `ollama-setup.md`. The shared wrapper defaults to `False`; override only when you want the reasoning trace. |
| `No prior checkpoint for thread 'X'` on `--resume` | Run without `--resume` first, then `--resume`. Different `--thread` values are independent. |
