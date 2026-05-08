# Sandcastle — local AFK smoke loop

This directory is the substrate for [epic #534](https://github.com/Osasuwu/jarvis/issues/534)
— Docker-isolated AFK coding agent. Slice 1 ([#537](https://github.com/Osasuwu/jarvis/issues/537))
ships only the **manual smoke command** on Main PC. No watchdog, no scheduler,
no memory bridge yet — those land in slices 2/4/8.

## What it does

`npm run sandcastle` builds nothing on its own — it expects the image to exist
already. It then:

1. Spins up a `sandcastle:jarvis` container with the Jarvis worktree bind-mounted.
2. Hands the agent prompt (`.sandcastle/prompt.md`) to Claude Code CLI inside
   the container.
3. Claude Code talks to **Ollama on the host** via Ollama's native
   Anthropic-compatible endpoint (no proxy).
4. Agent picks one issue labelled `sandcastle`, works on it, opens a PR, stops.
   It **never merges** — the live orchestrator session reviews and merges.

## Prerequisites

- **Docker Desktop** (Windows / macOS) running. On Linux Docker, you'll need to
  add `--add-host host.docker.internal:host-gateway` to whatever launches the
  container, or set `OLLAMA_BASE_URL` to your host IP.
- **Ollama ≥ v0.14** (Jan 2026 release — first to expose the native
  `/v1/messages` Anthropic-compatible endpoint) running on the host.
  Verify with `ollama --version`.
- **A coding model pulled on Ollama** with tool-use support and ≥64K context.
  Default in `.env.example` is `qwen2.5-coder:14b`. Pull once:
  ```powershell
  ollama pull qwen2.5-coder:14b
  ```
  Slice 7 ([#538](https://github.com/Osasuwu/jarvis/issues/538)) will benchmark
  and pick the production default — for slice-1 smoke any tool-use-capable
  coding model works.
- **A GitHub PAT** in `.sandcastle/.env` (`GH_TOKEN=…`) scoped to Issues: RW,
  PRs: RW, Contents: RW on this repo.
- **A tracer issue** labelled `sandcastle` exists in the repo and is small
  enough to land in one iteration (e.g. a typo fix). The agent will pick the
  highest-priority such issue.

## Smoke command

From the repo root:

```powershell
# 1. Build the image (one-time, or after Dockerfile changes).
docker build -t sandcastle:jarvis .sandcastle/

# 2. Copy env example and fill in GH_TOKEN.
cp .sandcastle/.env.example .sandcastle/.env
# edit .sandcastle/.env — set GH_TOKEN

# 3. Run the smoke loop. Picks one tracer issue, opens a PR, exits.
npm run sandcastle
```

Expected outcome: a new branch `feat/<N>-<slug>` is pushed, a PR with
`Closes #<N>` exists, and the container has exited cleanly with no Anthropic
API calls (since `ANTHROPIC_BASE_URL` is pointed at Ollama).

## What is intentionally NOT here

| Concern | Lands in |
|---|---|
| PowerShell watchdog (autostart, soft-stop, outcome_record) | slice 4 ([#541](https://github.com/Osasuwu/jarvis/issues/541)) |
| Memory MCP bridge inside container + skills baked in | slice 2 ([#540](https://github.com/Osasuwu/jarvis/issues/540)) |
| Supabase RLS for `sandcastle:agent` provenance | slice 3 ([#542](https://github.com/Osasuwu/jarvis/issues/542)) |
| Multi-tier model escalation (Ollama → small → DeepSeek → owner) | slice 5 ([#543](https://github.com/Osasuwu/jarvis/issues/543)) |
| Telegram alerting | slice 6 ([#544](https://github.com/Osasuwu/jarvis/issues/544)) |
| Workshop PC schedule + redrobot loop | slices 8/9 ([#545](https://github.com/Osasuwu/jarvis/issues/545), [#546](https://github.com/Osasuwu/jarvis/issues/546)) |

## Decisions (referenced by UUID)

- `894ac658-5697-4b89-b642-9a84c4b9c459` — Runtime: Claude Code + local Ollama, sterile container, no `~/.claude` mount.
- `436f9549-3acf-4ee0-85e5-c7259735d62e` — Sandcastle opens PRs only, never merges.

Slice-1 implementation choice (no proxy, native Ollama Anthropic endpoint)
recorded as `decision_made` episode `375449f9-5026-4471-a705-922c5baddf7f`.
