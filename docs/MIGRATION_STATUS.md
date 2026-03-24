# Migration Status

Status date: 2026-03-24

## M1: Architecture Migration (from docs/PROJECT_PLAN.md)

- [x] Initialize runtime scaffold in `src/` with CLI command entrypoint
- [x] Add command routing for `/triage`, `/weekly-report`, `/issue-health`
- [x] Add baseline environment and model configuration loader
- [x] Add `.mcp.json` bootstrap for GitHub + filesystem MCP servers
- [ ] Connect Telegram handler and validate end-to-end message flow
- [ ] Configure Claude Agent SDK direct runtime integration (beyond CLI bridge)
- [ ] Add scheduled runs (Task Scheduler or GitHub Actions trigger)

## Notes

- Current bootstrap runs in dry-run and execution mode through `claude -p`.
- Skills remain source-of-truth prompts under `skills/*/SKILL.md`.
- Telegram polling handler exists in `src/handlers/telegram.py`; next step is live bot E2E validation.

## Issue mapping (M1)

- #50 Create Agent SDK project structure: in progress (core scaffold created, handler/agent folders added)
- #51 Configure model tiers: in progress (config and command-to-agent routing added, no cost tracking yet)
- #52 Telegram integration: in progress (polling bridge implemented, end-to-end live bot validation pending)
- #53 Command routing to subagents: in progress (command parser and agent registry added, enforcement still soft)
- #49 API key and billing: pending manual cloud/account steps
