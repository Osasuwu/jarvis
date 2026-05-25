# Portfolio Value Audit Report

<!-- AUDIT-META
worker: ln-633
category: Portfolio Value
domain: misc_skills
scan_path: tests/
score: 9.0
total_issues: 1
critical: 0
high: 0
medium: 1
low: 0
status: completed
-->

## Checks

| ID | Check | Status | Details |
|----|-------|--------|---------|
| value_score | Impact × Probability scoring | passed | All 6 test suites scored |
| delete_candidates | Low-value tests identified | passed | 0 DELETE candidates |
| merge_candidates | Duplicate coverage detected | passed | 0 MERGE candidates |
| rewrite_candidates | Medium-value tests needing rewrite | passed | 0 REWRITE candidates |
| keep_candidates | High-value tests | passed | 6 KEEP candidates |
| regression_guard_check | Layer-2 regression guard verification | passed | test_principal.py guards #429 fix; test_protected_files.py guards #426 principal-aware decisions |

## Detailed Scores

| Test File | Lines | Impact (1-5) | Probability (1-5) | Score | Decision | Notes |
|-----------|-------|-------------|-------------------|-------|----------|-------|
| test_classifier.py | 175 | 3 | 3 | 9 | KEEP | Pure parsing + prompt assembly; well-scoped edge-case coverage |
| test_principal.py | 134 | 3 | 4 | 12 | KEEP | #429 regression guard (piped stdin); parametrized env var tests |
| test_protected_files.py | 251 | 4 | 3 | 12 | KEEP | #426 classify/should_block matrix; cross-platform path handling |
| test_morning_check.py | 423 | 4 | 3 | 12 | KEEP | Custom stubs for alarm enqueue; idempotency key tests |
| test_secret_scanner.py | 266 | 5 | 4 | 20 | KEEP | Highest-value file — 25+ secret patterns, bash dangers, heredocs |
| test_risk_radar.py | 388 | 3 | 3 | 9 | KEEP | 5 risk patterns with severity thresholds; report generation |

## Findings

| Severity | Location | Issue | Principle | Recommendation | Effort |
|----------|----------|-------|-----------|----------------|--------|
| MEDIUM | tests/test_morning_check.py:397 | Imports `_hash_scope_files` from `agents.dispatcher` — a private function from another module; dispatcher refactors could silently break this test | Maintainability | Use public API or duplicate the hash logic inline; alternatively add a comment linking to the contract | S |

## Summary

Overall Portfolio Value Score: **9.0/10**

- **6 KEEP** — all test files provide strong value with minimal maintenance overhead
- **0 DELETE / 0 MERGE / 0 REWRITE** — no files recommended for deletion or consolidation
- **Highest value**: test_secret_scanner.py (score 20) — critical security surface with comprehensive pattern coverage
- **Strongest regression guards**: test_principal.py (#429 piped stdin fix), test_protected_files.py (#426 principal-aware decisions)
- The misc skills cluster is small but delivers high-value, low-maintenance test coverage
