# Memory recall eval

Measures recall quality of the memory system against a live Supabase corpus.
Used to quantify each phase of the memory overhaul (see Osasuwu/jarvis#185 and
[docs/design/memory-overhaul.md](../../docs/design/memory-overhaul.md)).

## Run

```bash
# from repo root, with .venv activated
python scripts/eval-recall.py                  # show per-query + aggregates
python scripts/eval-recall.py --quiet          # aggregates only
python scripts/eval-recall.py --save-baseline  # overwrite baseline.json
python scripts/eval-recall.py --diff baseline  # compare to saved baseline
```

Requires `VOYAGE_API_KEY`, `SUPABASE_URL`, `SUPABASE_KEY` in `.env`.

## Metrics

| metric | meaning | target |
|---|---|---|
| `recall@5`  | fraction of queries where ≥1 expected memory is in top-5 | drive up |
| `recall@10` | same, top-10                                              | drive up |
| `MRR`       | mean reciprocal rank of first expected hit (0 if no hit)   | drive up |
| `must_not violations` | queries where a superseded/archived memory surfaced in top-5 | drive to 0 |

`must_not` is the **lifecycle signal**. Phase 0.5 baseline will have violations
(we have no supersedes filter yet). Phase 1 is expected to drive this to 0.

## Query set

See [queries.yaml](queries.yaml). 20 queries across:

- `direct` — unique memory, name-based query
- `topic` — multiple valid memories on a topic
- `behavior` — feedback/rules
- `reference` — research digests
- `user` — owner profile
- `lifecycle` — **stress the superseded/stale handling** — expected memory
  must surface AND the superseded version must NOT surface in top-5

## Adding queries

- Use memory `name` not `id` (survives ID churn)
- Keep queries short-ish — real recall happens from fragmentary user prompts
- Mix Russian + English (we work bilingually)
- If a query exposes a new lifecycle problem, tag `kind: lifecycle` and add
  `must_not` names

## Phase workflow

1. Before a phase:  `python scripts/eval-recall.py --diff baseline`
2. Do the phase work.
3. After the phase:  `python scripts/eval-recall.py --diff baseline`
4. If phase succeeded (delta positive, no regressions):
   `python scripts/eval-recall.py --save-baseline`
5. Commit `baseline.json` alongside the phase PR — it's the quantitative
   record of what the phase bought us.

## Design notes

The harness deliberately **duplicates** the recall pipeline constants from
`mcp-memory/server.py` instead of importing them. This means:

- Eval is independent of server.py's MCP/async wiring
- When server.py's pipeline changes, the delta in eval output **is** the
  measurement we want
- When constants should follow server.py verbatim (e.g. Phase 0 adds new
  columns but same constants), keep in sync manually — there's a comment at
  the top of eval-recall.py flagging this
