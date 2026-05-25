# ln-635 Trustworthiness (Isolation) Assessment — Memory-Eval Cluster

**Cluster:** tests/memory-eval/ (4 data files) + scripts/eval-recall.py
**Worker:** ln-635 (Isolation/Psychometric)
**Date:** 2026-05-25
**Provenance:** sandcastle:agent:jarvis-watchdog-20260525-180516

---

## AUDIT-META

- **Files audited:** 5
  - `tests/memory-eval/queries.yaml` — 128 lines
  - `tests/memory-eval/baseline.json` — 620 lines
  - `tests/memory-eval/context-rot-baseline.json` — 620 lines
  - `tests/memory-eval/README.md` — 72 lines
  - `scripts/eval-recall.py` — 1008 lines (evaluation harness)
- **Nature:** Integration/eval harness, not unit tests — requires live Supabase + VoyageAI

---

## Checks

| Check | Finding | Severity |
|---|---|---|
| Deterministic queries | Query strings are fixed in YAML, reproducible | OK |
| Baseline reproducibility | Same query set, same pipeline → same results (±embedding drift) | OK |
| External dependencies | Supabase + VoyageAI + Anthropic (rewriter) — fails without credentials | MEDIUM |
| Query independence | Each query is independent, no shared state between runs | OK |
| Data isolation | Baselines are timestamped and versioned in git | OK |
| Honest metric definition | recall@5/recall@10/MRR/must_not defined clearly and measured consistently | OK |

---

## Findings

### FINDING-001: Live external dependency prevents offline validation
**Severity:** MEDIUM
**Files:** `scripts/eval-recall.py`
**Detail:** The eval requires live Supabase (for match_memories RPC, keyword_search, confidence enrichment) and VoyageAI (for embeddings). There's no offline/mock mode with a snapshot corpus. This means the eval cannot run in CI without exposing secrets, and developers without access to the Supabase project cannot run it at all. A replay mode that uses a cached snapshot of RPC results would enable CI gating without secrets.

### FINDING-002: Embedding model drift is unmeasured
**Severity:** MEDIUM
**File:** `scripts/eval-recall.py`
**Detail:** The eval uses `voyage-3-lite` as the embedding model. If VoyageAI updates the model behind this name (a common practice), embeddings shift and baseline comparisons break. There is no pinned model version or vector comparison to detect embedding drift before attributing metric changes to pipeline changes.

### FINDING-003: Per-query results capture top-10 but score stack is absent
**Severity:** LOW
**File:** `tests/memory-eval/baseline.json`
**Detail:** The baseline captures top-10 memory names, hit rankings, and pass/fail per query, but does not capture the full score stack (_rrf_score, _temporal_score, similarity). This makes it impossible to distinguish "memory didn't surface at all" from "memory surfaced but was ranked below top-10" in post-hoc analysis.

---

## Score

**Score = max(0, 10 - (critical×2.0 + high×1.0 + medium×0.5 + low×0.2))**

| Severity | Count | Weight |
|---|---|---|
| Critical | 0 | 0.0 |
| High | 0 | 0.0 |
| Medium | 2 | 1.0 |
| Low | 1 | 0.2 |

**Final Score: 8.8 / 10**

Well-structured evaluation with clear metrics, but live external dependency prevents CI integration and broaders reproducibility. Embedding model drift is an unmeasured confound.
