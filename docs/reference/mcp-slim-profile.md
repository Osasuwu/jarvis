# Slim MCP profile for work sessions (#1464)

`config/mcp-slim.json` starts a Claude Code session with only the MCP servers work
sessions actually use — `memory` and `github` — instead of the full registered surface
(context7, sequential-thinking, obsidian, uml, plus desktop/claude.ai connectors such as
Browser and visualize).

> **Measured outcome (2026-08-08, CLI 2.1.224): the profile does NOT reduce startup
> tokens.** Headless full surface 65,586 vs slim 66,835 (first-turn usage sum; delta is
> noise). Cause: MCP tool search ships enabled by default since CLI 2.1.221 — MCP tool
> schemas are deferred out of the context window and loaded on demand, so unused servers
> already cost ~0 tokens at start. Issue #1464 AC2 (≥15k reduction) is therefore
> unachievable by server exclusion on current CLI versions. The profile's remaining
> value is startup latency (no npx/python server processes spawned) and tool-surface
> hygiene in strict autonomous runs — not context budget.
>
> For **interactive/desktop** sessions the context levers are: `/mcp` toggles (persist
> per-project in `~/.claude.json` → `disabledMcpServers`), and
> `disableClaudeAiConnectors: true` in `~/.claude/settings.json` — connectors such as
> Browser/visualize are loaded upfront (not deferred) and are the main real cost.

The original motivation — transcript `420b43f3` (`/implement 1460`), where a ~90k
startup baseline against a ~136k auto-compact trigger caused compaction thrash — is
still real, but its ~42k "system prompt + tool schemas" component is dominated by the
system prompt, native tools, and upfront-loaded connectors, not by registered MCP
servers.

## Launch

From the repo root (the profile's `memory` entry uses a repo-relative script path):

```bash
claude --mcp-config config/mcp-slim.json --strict-mcp-config
```

Headless is the same flags on `claude -p`. Wiring them into `scripts/ralph-loop.ps1`
(PR #1463) is optional after the measurement below: it buys startup latency and a
stricter tool surface, not context budget.

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
`input_tokens + cache_read_input_tokens + cache_creation_input_tokens`.

Measured 2026-08-08 on CLI 2.1.224 (`claude -p "Reply with exactly: OK"
--output-format json`, same cwd, GITHUB_TOKEN set): full surface **65,586**, slim
profile **66,835** — no reduction; see the callout above for the tool-search
explanation. Re-measure if `ENABLE_TOOL_SEARCH=false` is ever set (that restores the
classic upfront loading this profile was designed against).

## Drift guard

`tests/infrastructure/test_mcp_slim_profile.py` fails if the profile lists anything
beyond the allowed set or if a server definition drifts from the canonical
`.claude-userlevel/.mcp.json`. Changing the allowed set is a policy change —
`record_decision` applies (user-level CLAUDE.md trigger #4).
