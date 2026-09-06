# Native-first substrate

Pull-only detail for AGENTS.md → *Substrate rule*.

## Routing table

- Telegram → Channels
- Scheduling → `/loop` or scheduled tasks
- Background → desktop agents

## Existing justified custom code

`mcp-memory/server.py`, `src/risk_radar.py` — the native options were awkward or incomplete for
these, so they stay custom code on merit.

## Relaxation history

The substrate rule was relaxed 2026-05-20 from a prior near-prohibition on custom scripts/services
to the current merit-based "native-first, not a ban" framing, covering any language — decision
`d9be0390`.
