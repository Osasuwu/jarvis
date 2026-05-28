# Portfolio Value Audit Report

<!-- AUDIT-META
worker: ln-633
category: Portfolio Value
domain: memory_cluster
scan_path: tests/
score: 7.6
total_issues: 9
critical: 0
high: 1
medium: 6
low: 2
status: completed
-->

## Checks

| ID | Check | Status | Details |
|----|-------|--------|---------|
| value_score | Impact × Probability scoring | passed | All 13 test suites scored |
| delete_candidates | Low-value tests identified | passed | 0 DELETE candidates found |
| merge_candidates | Duplicate coverage detected | passed | 1 MERGE candidate found |
| rewrite_candidates | Medium-value tests needing rewrite | passed | 9 REWRITE candidates identified |
| keep_candidates | High-value tests | passed | 3 KEEP candidates identified |
| regression_guard_check | Layer-2 regression guard verification | passed | All DELETE/REWRITE candidates vetted |

## Findings

| Severity | Location | Issue | Principle | Recommendation | Effort |
|----------|----------|-------|-----------|----------------|--------|
| HIGH | tests/test_memory_server.py | Largest file (2008 lines) — single monolithic test file for mcp-memory server; high maintenance surface | Maintainability | Split into domain-specific modules (handlers, tools, auth) | L |
| MEDIUM | tests/test_episode_extractor.py | 675 lines with complex mock infrastructure (_MockTable, _MockClient, _MockQuery) — setup-heavy per-test class | Value | Consider shared fixtures via conftest.py to reduce boilerplate | M |
| MEDIUM | tests/test_consolidation_review.py | 810 lines of test support code (_FakeClient, _FakeTableQuery, _FakeRPC) — high infrastructure-to-assertion ratio | Value | Extract shared fake client into test utilities module | M |
| MEDIUM | tests/test_evolve_neighbors.py | 753 lines, extensive defensive parsing tests — good coverage but high maintenance | Value | Keep — valuable defensive layer for Haiku output parsing | S |
| MEDIUM | tests/test_memory_recall_hook.py | 912 lines, comprehensive but duplicated mock patterns with test_memory_server.py | Value | Extract shared mock strategies | M |
| MEDIUM | tests/test_migrate_memory_structure.py | Required structure + parse + validation tests well-scoped but contain duplicated fake client patterns | Value | Reuse consolidation_review's _FakeClient pattern | S |
| MEDIUM | tests/test_session_context_recovery.py | Good edge-case coverage for session recovery — keep as-is | Value | KEEP — no actionable issue | - |
| LOW | tests/test_memory_calibration.py | 143 lines, well-scoped unit tests for calibration handler | Value | KEEP — appropriate size, good coverage | - |
| LOW | tests/test_memory_server_script_launch.py | 66 lines, single test for script launch regression guard | Value | MERGE with test_memory_server.py or keep standalone | S |

## Detailed Scores

| Test File | Lines | Impact (1-5) | Probability (1-5) | Score | Decision | Notes |
|-----------|-------|-------------|-------------------|-------|----------|-------|
| test_memory_calibration.py | 143 | 4 | 3 | 12 | REWRITE | Well-scoped; schema guard adds unique value |
| test_memory_recall_hook.py | 912 | 4 | 3 | 12 | REWRITE | Comprehensive but could trim boilerplate |
| test_memory_server.py | 2008 | 5 | 4 | 20 | KEEP | Core infrastructure test — critical value |
| test_memory_server_script_launch.py | 66 | 3 | 3 | 9 | MERGE | Merge into test_memory_server.py |
| test_episode_extractor.py | 675 | 4 | 4 | 16 | KEEP | Core pipeline, high edge-case coverage |
| test_consolidation_review.py | 810 | 4 | 3 | 12 | REWRITE | Extract shared fake client infra |
| test_evolve_neighbors.py | 753 | 4 | 3 | 12 | REWRITE | Defensive parsing tests are valuable |
| test_pretooluse_recall.py | 473 | 4 | 3 | 12 | REWRITE | Good dedup + main integration tests |
| test_recall_audit.py | 511 | 3 | 3 | 9 | REWRITE | Medium priority but good coverage |
| test_recall_orchestrator.py | 248 | 5 | 3 | 15 | KEEP | Golden test for recall — high contract value |
| test_migrate_memory_structure.py | 275 | 4 | 3 | 12 | REWRITE | Good structure, minor duplication |
| test_session_context_recovery.py | 445 | 4 | 3 | 12 | REWRITE | Well-scoped, good edge cases |
| test_pre_compact_backup.py | 409 | 4 | 3 | 12 | REWRITE | Good coverage of fallback paths |

## Summary

Overall Portfolio Value Score: **7.6/10**

- **3 KEEP** — core infrastructure tests with critical value (memory server, episode extractor, recall orchestrator)
- **1 MERGE** — script launch test can merge into main memory server test file
- **9 REWRITE** — medium-value tests that could benefit from fixture extraction, boilerplate reduction, or scope trimming
- **0 DELETE** — no test files recommended for deletion; all provide valid regression guard value

The memory cluster tests are generally well-structured with comprehensive edge-case coverage. The primary improvement opportunity is extracting shared mock/fake infrastructure (repeated _FakeClient, _FakeTableQuery patterns across consolidation_review, evolve_neighbors, episode_extractor) into a shared test utility module.
