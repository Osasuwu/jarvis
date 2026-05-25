# ln-633 Portfolio Value Assessment — Memory-Eval Cluster

**Cluster:** tests/memory-eval/ (4 data files) + scripts/eval-recall.py
**Worker:** ln-633 (Portfolio Value)
**Date:** 2026-05-25
**Provenance:** sandcastle:agent:jarvis-watchdog-20260525-180516

---

## AUDIT-META

- **Files audited:** 5
  - `tests/memory-eval/queries.yaml` — 128 lines (20 benchmark queries)
  - `tests/memory-eval/baseline.json` — 620 lines (recall metrics baseline)
  - `tests/memory-eval/context-rot-baseline.json` — 620 lines (context-rot baseline)
  - `tests/memory-eval/README.md` — 72 lines (documentation)
  - `scripts/eval-recall.py` — 1008 lines (evaluation harness)
- **Supporting context:** `mcp-memory/recall.py` — 648 lines (pipeline under test)
- **Business criticality:** HIGH — recall quality is the foundation of the memory system. Without eval, regressions are invisible.

---

## Checks

| Check | Finding | Severity |
|---|---|---|
| Business value alignment | Measures core memory recall quality — highest-value test infra in project | HIGH |
| Coverage adequacy | 20 queries across 6 kinds (direct, topic, behavior, reference, user, lifecycle) — broad but shallow | OK |
| Regression sensitivity | Baseline diff mode catches regressions; context-rot detects session-start pollution | HIGH |
| Cost-to-value ratio | ~1700 lines of test infra for ~650 lines of pipeline code | OK |
| CI integration | No automated CI run — requires live Supabase+VoyageAI credentials | MEDIUM |

---

## Findings

### FINDING-001: No CI automation — eval is a manual-only workflow
**Severity:** MEDIUM
**Files:** `scripts/eval-recall.py`, `tests/memory-eval/*`
**Detail:** The eval requires `SUPABASE_URL`, `SUPABASE_KEY`, and `VOYAGE_API_KEY` at runtime. There's no CI workflow or scheduled task that runs the eval and diffs against baseline. This means regressions in recall quality pass silently until someone manually runs the harness. Given the memory system's centrality, automated post-deploy eval would catch regressions instantly.

### FINDING-002: Small query set limits statistical power
**Severity:** MEDIUM
**File:** `tests/memory-eval/queries.yaml`
**Detail:** 20 queries is a small sample size for a 400+ memory corpus. A single query flipping from pass→fail or fail→pass shifts recall@5 by 5 percentage points. Expanding to 50-100 queries would give more reliable metrics and allow stratified analysis (e.g., recall by memory type, by project scope).

### FINDING-003: Context-rot baseline is stale
**Severity:** LOW
**File:** `tests/memory-eval/context-rot-baseline.json`
**Detail:** The context-rot baseline is from 2026-04-21 with corpus_size=327, while the main baseline is from 2026-04-25 with corpus_size=412. The ~85 new memories and any pipeline changes since then likely changed the context-rot profile. Stale baselines produce misleading deltas.

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

Highest-value test infrastructure in the project — evaluates the core memory recall pipeline. Main gaps are lack of CI automation and small query set.
