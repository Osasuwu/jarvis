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

## Offline replay / CI (no secrets needed)

```bash
# 1. Record a snapshot (requires live keys):
python scripts/eval-recall.py --record tests/memory-eval/snapshot.json

# 2. Replay offline (no keys needed):
python scripts/eval-recall.py --replay tests/memory-eval/snapshot.json --diff baseline

# 3. CI mode — replay + fail on regressions:
python scripts/eval-recall.py --ci tests/memory-eval/snapshot.json --diff baseline
```

The `--record` flag captures raw RPC results (embeddings + semantic/keyword search
rows) to a snapshot file. The `--replay` flag re-runs the post-RPC pipeline (RRF
merge → confidence → temporal scoring → metric computation) on the cached data
without needing Supabase or VoyageAI access. `--ci` replays and exits 1 if any
baseline-passing query regresses.

**`--replay`/`--ci` cannot detect embedding drift** (see below) — the snapshot's
embeddings are frozen at `--record` time, so replaying it never calls VoyageAI
again and has nothing fresh to diff against the baseline's fingerprints. Drift
detection only runs on the live path (`--diff baseline` / `--save-baseline`
without `--replay`/`--ci`).

## Metrics

| metric | meaning | target |
|---|---|---|
| `recall@3`  | fraction of queries where ≥1 expected memory is in top-3 | drive up |
| `recall@5`  | fraction of queries where ≥1 expected memory is in top-5 | drive up |
| `recall@10` | same, top-10                                              | drive up |
| `MRR`       | mean reciprocal rank of first expected hit (0 if no hit)   | drive up |
| `mean_rank` | average position of first expected hit (lower better)      | drive down |
| `must_not violations` | queries where a superseded/archived memory surfaced in top-5 | drive to 0 |

`must_not` is the **lifecycle signal**. Phase 0.5 baseline will have violations
(we have no supersedes filter yet). Phase 1 is expected to drive this to 0.

## Embedding drift check (#1216)

`--diff baseline` and `--save-baseline` (live path only, not `--replay`/`--ci`)
also fingerprint each query's VoyageAI embedding and compare it against the
fingerprints stored in `baseline.json`, independent of the recall metrics
above — a silent `voyage-3-lite` behavior change (model swap, API change)
would otherwise pass recall metrics unnoticed if hit-ranking happens to be
stable. Reuses the single canonical `_embed_query()` call site — no extra
VoyageAI calls beyond one per query.

`EMBEDDING_DRIFT_THRESHOLD` (`scripts/eval-recall.py`) is calibrated from two
live `--record` runs against the same 82-query set/corpus on 2026-08-09:
per-query cosine distance between runs ranged 0.0–0.000163 (float-precision +
API non-determinism noise floor). The threshold (0.01) sits ~2 orders of
magnitude above that ceiling so it flags genuine drift without false-firing
on run-to-run noise. A baseline saved before this feature shipped has no
`embedding_fingerprints` key — the drift check prints a skip notice and
otherwise no-ops until the baseline is refreshed with `--save-baseline`.

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
