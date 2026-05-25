# ln-638 Oracle Effectiveness Assessment — Memory-Eval Cluster

**Cluster:** tests/memory-eval/ (4 data files) + scripts/eval-recall.py
**Worker:** ln-638 (Oracle Effectiveness)
**Date:** 2026-05-25
**Provenance:** sandcastle:agent:jarvis-watchdog-20260525-180516

---

## AUDIT-META

- **Files audited:** 5
  - `tests/memory-eval/queries.yaml` — 128 lines (20 queries, 6 kinds)
  - `scripts/eval-recall.py` — 1008 lines (evaluation harness)
- **Oracle type:** Multi-metric recall evaluation (recall@5, recall@10, MRR, must_not violations)
- **Pass/fail criteria:** recall@5 >= 1 expected hit AND no must_not violations

---

## Checks

| Check | Finding | Severity |
|---|---|---|
| Oracle clarity | Pass/fail criteria clearly documented in README metrics table | OK |
| Metric completeness | recall@5, recall@10, MRR, must_not violations — good multi-dimensional signal | OK |
| Expected memory specificity | Names are exact memory names — unambiguous | OK |
| Must_not enforcement | Lifecycle queries verify superseded memories are excluded | HIGH |
| Pass/fail determinism | Same query + same pipeline → same result (modulo corpus changes) | OK |
| Diff usability | Baseline diff prints regression/improvement lists with delta formatting | OK |

---

## Findings

### FINDING-001: Pass/fail is binary recall@5 — misses ranking degradation within passing margin
**Severity:** MEDIUM
**File:** `scripts/eval-recall.py`
**Detail:** A query "passes" if any expected memory appears in top-5 with no must_not violations. But a memory dropping from rank 1 to rank 4 (still within top-5) is invisible — it passes just as cleanly. MRR captures this somewhat but is sensitive to a single outlier query. A stricter oracle like "expected memory must be in top-3" or "mean rank of expected memories" would catch ranking regressions earlier.

### FINDING-002: Must_not violations are binary — no severity gradient
**Severity:** LOW
**File:** `scripts/eval-recall.py`
**Detail:** A must_not violation is counted if ANY superseded memory appears in top-5, regardless of rank. Rank 5 violation is treated identically to rank 1 violation. Weighted must_not scoring (e.g., penalize by 1/rank) would provide a more nuanced lifecycle quality signal.

### FINDING-003: No query-level weighting or criticality tiers
**Severity:** LOW
**File:** `tests/memory-eval/queries.yaml`
**Detail:** All 20 queries are weighted equally in aggregate metrics. Lifecycle queries (q18, q19 — the most critical for the Phase 1 mission) have the same influence as user profile queries (q17, which already fails). Stratified reporting (e.g., separate recall@5 for lifecycle queries) would better track Phase 1 progress.

### FINDING-004: Expected memories use hardcoded names — brittle to renames
**Severity:** LOW
**File:** `tests/memory-eval/queries.yaml`
**Detail:** Expected and must_not lists reference memory names directly. If a memory is renamed (e.g., `jarvis_stays_goals_not_agile` → `jarvis_goals_not_agile_superseded`), the corresponding query silently loses its oracle. Names are more stable than UUIDs but still change during refactoring. A name-to-id resolution at eval runtime (already partially done in the harness) mitigates but doesn't eliminate this.

---

## Score

**Score = max(0, 10 - (critical×2.0 + high×1.0 + medium×0.5 + low×0.2))**

| Severity | Count | Weight |
|---|---|---|
| Critical | 0 | 0.0 |
| High | 0 | 0.0 |
| Medium | 1 | 0.5 |
| Low | 3 | 0.6 |

**Final Score: 8.9 / 10**

Multi-metric oracle design is sound. Binary recall@5 pass/fail is the main weakness — it misses ranking degradation within the passing window. Query set is well-structured with clear lifecycle signal.
