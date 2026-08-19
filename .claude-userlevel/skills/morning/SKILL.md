---
name: morning
model: haiku
description: "Owner-facing daily digest read — plan with S/M/L estimates + cut-line, repo hygiene, goals/decisions evidence — via morning_digest MCP tool, rendered deterministically (0 LLM tokens by default). Anchored routing: only `утро`/`morning`/`доброе утро` fire it."
disable-model-invocation: true
---

# Morning

The owner-facing **read** side of the daily-digest capability (#1588, M64). Once-a-day call, so the default surface is **deterministic Python — no LLM narration, no tokens spent on rendering**. The judgment already happened upstream: `morning_digest` wraps `morning_gather.gather() → morning_engine.analyze()` and hands back a fully-decided `Digest` (schema_version, sections, plan, degradation, origin). This skill's only job is to surface it.

**Boundary:** this skill reads and renders. It does not investigate, open issues, comment, act on plan items, or negotiate the cut-line — those belong to the owner. Surfacing the day's plan is the whole contract; what to do about it is the reader's call.

**Anchored routing (CLAUDE.md skill-routing table).** Only the exact triggers `утро`, `morning`, or `доброе утро` route here. A sentence that merely contains one of these words — "when did that meeting move to this morning", "good morning" as a passing greeting mid-conversation with no digest intent — is a normal in-context reply, NOT a command to run the daily digest. Do not self-fire on incidental uses of the word. This trigger set is deliberately disjoint from `/status`'s (`статус`/`status`/`статус <repo>`) — the two skills never intercept each other's routing.

## Step 1 — Call the digest tool

```
mcp__morning__morning_digest(jarvis_home="<JARVIS_HOME or empty to auto-detect>")
```

Pass `jarvis_home` when `JARVIS_HOME` is set (cron / non-repo CWD); leave it empty to let the server auto-detect from CWD via `git rev-parse`. The tool returns the digest as a JSON text block matching `scripts/digest_schema.py`'s `Digest.to_dict()` shape (`schema_version`, `sections`, `plan`, `degradation`, `origin`).

**Registration ceiling:** `mcp-morning/server.py` exists and is fully tested (`tests/morning/test_mcp_morning_server.py`) but is deliberately **not yet registered** in `.claude-userlevel/.mcp.json` — that wiring is a separate, later slice (#1588 body). Until `mcp__morning__morning_digest` is reachable, fall back to calling `gather()`/`analyze()` directly in-process:

```bash
python -c "
import json
from scripts.morning_gather import gather
from scripts.morning_engine import analyze
print(json.dumps(analyze(gather('')).to_dict(), indent=2, default=str))
"
```

Switch back to the MCP tool call the moment registration lands — the fallback exists only to keep this skill usable in the gap, not as a permanent second code path.

If the tool response begins with `Error in morning_digest:` — surface that verbatim to the owner and stop. A failed gather must read as suspicious, never as "all clear".

## Step 2 — Render deterministically (default path, 0 LLM tokens)

Do **not** narrate, summarize, or reformat the digest yourself — that would spend tokens and drift from the snapshot test. Pipe the exact JSON from Step 1 through the pure renderer and print its output verbatim:

```bash
python "${JARVIS_HOME:-.}/scripts/morning_render.py" < /tmp/morning_digest.json
```

`scripts/morning_render.py` ([renderer](../../../scripts/morning_render.py)) is a pure function over the digest (`render(digest: dict) -> str`). Block order is fixed: degradation → «Знать» (compact summary) → plan (each item tagged `[S]`/`[M]`/`[L]`, cut-line marker after `cut_line_after`) → evidence sections (collapsed `<details>` by default; `repo_hygiene` prints as one line when there are no problems).

Print the renderer's stdout exactly. That is the default deliverable.

## Failure modes

- `morning_digest` returns an `Error in ...` text (or the in-process fallback raises) → surface verbatim, stop. Never substitute a synthesized "looks fine".
- Degradation line present in the render (`⚠ Деградация источников: ...`) → a gather source failed; that IS the finding. Surface it; do not retry hoping for a clean run.
- `JARVIS_HOME` unset and CWD outside the repo → `${JARVIS_HOME:-.}` resolves to `.`; if `scripts/morning_render.py` isn't found, the owner is in the wrong directory — say so rather than guessing a path.
- MCP tool unreachable and the in-process fallback also fails → both paths ultimately call the same `gather()`/`analyze()`; a failure here is a real gather/analyze bug, not a routing issue.
