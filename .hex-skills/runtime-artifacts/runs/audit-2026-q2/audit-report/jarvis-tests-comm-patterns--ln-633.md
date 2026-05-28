# Portfolio Value Audit Report

<!-- AUDIT-META
worker: ln-633
category: Portfolio Value
domain: comm_patterns
scan_path: tests/
score: 9.0
total_issues: 1
critical: 0
high: 1
medium: 0
low: 0
status: completed
-->

## Checks

| ID | Check | Status | Details |
|----|-------|--------|---------|
| value_score | Impact × Probability scoring | passed | All 4 test suites scored |
| delete_candidates | Low-value tests identified | passed | 0 DELETE candidates |
| merge_candidates | Duplicate coverage detected | passed | 0 MERGE candidates |
| rewrite_candidates | Medium-value tests needing rewrite | passed | 0 REWRITE candidates |
| keep_candidates | High-value tests | passed | 4 KEEP candidates |
| regression_guard_check | Layer-2 regression guard verification | passed | All schemas sentinel tests verified |

## Detailed Scores

| Test File | Lines | Impact (1-5) | Probability (1-5) | Score | Decision | Notes |
|-----------|-------|-------------|-------------------|-------|----------|-------|
| test_comm_patterns_backfill.py | 178 | 3 | 2 | 6 | KEEP | Well-scoped backfill helpers; idempotency contract is valuable |
| test_comm_patterns_classifier.py | 154 | 4 | 3 | 12 | KEEP | Schema sentinel test has outsized value for its size |
| test_comm_patterns_extractor.py | 504 | 4 | 4 | 16 | KEEP | Core pipeline with comprehensive edge-case coverage |
| test_comm_patterns_scrubber.py | 216 | 4 | 3 | 12 | KEEP | Strong regression guards for secret redaction; drift sentinel vs secret-scanner.py |

## Findings

| Severity | Location | Issue | Principle | Recommendation | Effort |
|----------|----------|-------|-----------|----------------|--------|
| HIGH | tests/test_comm_patterns_extractor.py | 504 lines — largest file in the cluster; wall_clock_budget test uses real time.sleep(0.05) making it slow (≥100ms per run) | Maintainability | Consider reducing sleep duration to 0.01s or using a mock clock; the 5-iteration loop needs ~250ms real time vs <10ms for the rest of the suite combined | S |

## Summary

Overall Portfolio Value Score: **9.0/10**

- **4 KEEP** — all test files provide strong value with minimal maintenance overhead
- **0 DELETE / 0 MERGE / 0 REWRITE** — no files recommended for deletion or consolidation
- The comm-patterns cluster is the most consistently well-structured test group in the memory/comm area
- Schema sentinel tests (classifier vs schema.sql, scrubber vs secret-scanner.py) provide high-value regression guards in minimal lines
