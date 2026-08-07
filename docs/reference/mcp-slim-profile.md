# Slim MCP profile for work sessions (#1464)

`config/mcp-slim.json` starts a Claude Code session with only the MCP servers work
sessions actually use — `memory` and `github` — instead of the full registered surface
(context7, sequential-thinking, obsidian, uml, plus desktop/claude.ai connectors such as
Browser and visualize). Measured on transcript `420b43f3` (`/implement 1460`), the full
surface contributes ~42k tokens of tool schemas to a ~90k startup baseline against a
~136k auto-compact trigger — the direct cause of compaction thrash in `/implement`
sessions.

## Launch

From the repo root (the profile's `memory` entry uses a repo-relative script path):

```bash
claude --mcp-config config/mcp-slim.json --strict-mcp-config
```

The flags work the same on headless `claude -p`, but **there is nothing there for them to
strip** — measured 2026-08-08 (#1461), A/B on identical no-op prompts, same cwd and model:
66 815 tokens with the slim profile vs 65 555 on the full registered surface. No gain,
within noise. The ~90k baseline below is a *host-managed desktop session* number, where
claude.ai connectors (Browser, visualize, `ccd_*`) dominate the surface; headless never
loads those. `scripts/ralph-loop.ps1` therefore exposes `-McpConfig` but leaves it empty by
default — see [`ralph-loop.md`](ralph-loop.md) → *Per-iteration startup floor*.

Semantics (per Claude Code CLI reference, verified 2026-08-08): `--mcp-config` alone
**adds** to registered servers; paired with `--strict-mcp-config` it **replaces** all
other MCP configuration — user scope (`~/.claude.json`), project `.mcp.json`, plugin
servers, and claude.ai connectors. Excluded servers are fully absent: their tool schemas
never enter the context window. `settings.json` keys
(`enabledMcpjsonServers`/`disabledMcpjsonServers`) were rejected as the mechanism — they
only gate project-scope `.mcp.json` entries, not user-scope or connector servers where
the bulk of the cost lives.

The profile is **opt-in per launch**. Default interactive sessions keep the full MCP
surface; nothing is unregistered.

## Measuring the effect

Compare the first assistant turn's `message.usage` in the session transcript JSONL
(`~/.claude/projects/<project>/<session>.jsonl`): effective startup context ≈
`input_tokens + cache_read_input_tokens + cache_creation_input_tokens`. Full-surface
baseline: ~90k (transcript `420b43f3`). Target under the slim profile: ≥15k lower
(issue #1464 AC2).

## Drift guard

`tests/infrastructure/test_mcp_slim_profile.py` fails if the profile lists anything
beyond the allowed set or if a server definition drifts from the canonical
`.claude-userlevel/.mcp.json`. Changing the allowed set is a policy change —
`record_decision` applies (user-level CLAUDE.md trigger #4).
