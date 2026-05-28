# Oracle Effectiveness Audit Report

<!-- AUDIT-META
worker: ln-638
category: Oracle Effectiveness
domain: memory_cluster
scan_path: tests/
score: 5.9
total_issues: 8
critical: 0
high: 2
medium: 3
low: 3
status: completed
-->

## Checks

| ID | Check | Status | Details |
|----|-------|--------|---------|
| assertion_strength | Assertion quality and completeness | warning | Several files have weak or missing assertions — see findings |
| meaningful_oracle | Oracle tied to product behavior | passed | Most assertions verify domain-meaningful behavior |
| snapshot_oracle | Snapshot-only testing | passed | No snapshot-only tests detected |
| over_mocking | Mock-proves-mock patterns | warning | Several tests verify mock-call chains rather than behavior — see findings |
| mutation_style_evidence | Mutation testing evidence | skipped | No mutation reports available; critical-module oracle is adequate |

## Findings

| Severity | Location | Issue | Principle | Recommendation | Effort |
|----------|----------|-------|-----------|----------------|--------|
| HIGH | tests/test_memory_server.py | 2008-line monolith contains 212 mock/call-assertion matches — confirmed mock-proves-mock pattern risk where primary assertion is mock wiring rather than downstream behavior | Over-mocking | Audit for tests where the primary assertion is `mock.assert_called_with(...)` without verifying the downstream effect | M |
| HIGH | tests/test_pretooluse_recall.py:277-279 | `client.rpc.return_value.execute.return_value = MagicMock(data=rpc_rows or [])` — deep mock chains make assertions about mock wiring, not actual behavior | Over-mocking | Consider contract-style test doubles that enforce real response shapes | M |
| MEDIUM | tests/test_consolidation_review.py:114-142 | _FakeClient.execute() returns _FakeResp with canned data — test verifies call routing, not actual RPC roundtrip | Oracle: Mock | Accepted pattern for unit-testing CLI dispatch; integration tests cover real RPCs | S |
| MEDIUM | tests/test_evolve_neighbors.py:38-247 | _parse_response tests verify JSON parsing edge cases with inline strings — good coverage but the primary oracle is "does not crash" + "returns expected structure" | Assertion Strength | Acceptable for a defensive parsing function; consider adding property-based tests | M |
| LOW | tests/test_recall_orchestrator.py:121-134 | Assertions like `assert isinstance(h.semantic_score, float)` verify type contracts but not correctness of score values — however, the same test also asserts explicit ordering and score constraints (a strong oracle); the isinstance check is a smaller secondary concern that does not warrant MEDIUM severity | Oracle: Meaningful | Strengthen with value-range assertions (0-1 bounds for scores) | S |
| MEDIUM | tests/test_memory_calibration.py:108-115 | RPC failure test asserts error text contains "rpc blew up" — asserts the error surfaced but not the error-handling behavior | Oracle: Error handling | Add assertion that error recovery completes (no partial state, no cascade) | S |
| LOW | tests/test_recall_audit.py:108-129 | "does not flag when populated" test verifies empty filter result — assertion is `assert [] == []` test variant | Assertion Strength | Assert that other detectors still ran (not just that the empty_memories_used detector was silent) | S |
| LOW | tests/test_pre_compact_backup.py:112-148 | _parse_transcript tests verify parsing of small/truncated/malformed input — good edge-case coverage, oracle is structural | Oracle: Structure | Accepted — oracle matches the function's contract; no improvement needed | - |

## Oracle Quality by File

| Test File | Assertion Quality | Over-mocking Risk | Oracle Note |
|-----------|------------------|-------------------|-------------|
| test_memory_calibration.py | GOOD | LOW | Schema guard is a strong regression oracle; handler tests use text-content assertions |
| test_memory_recall_hook.py | GOOD | MEDIUM | Main integration test verifies JSON payload shape; dedup tests verify boolean outcomes |
| test_memory_server.py | MIXED | HIGH | Largest file — confirmed 212 mock/call-assertion matches; likely has both strong and mock-proves-mock patterns |
| test_memory_server_script_launch.py | GOOD | NONE | Single strong regression guard with explicit failure conditions |
| test_episode_extractor.py | GOOD | LOW | Verifies inserted data shape, provenance, and processing outcomes |
| test_consolidation_review.py | GOOD | MEDIUM | JSON output shape verified; call routing verified through recorded calls |
| test_evolve_neighbors.py | GOOD | LOW | Extensive defensive parsing assertions with strong downgrade-path verification |
| test_pretooluse_recall.py | GOOD | MEDIUM | End-to-end payload shape verified; dedup timing verified |
| test_recall_audit.py | GOOD | LOW | Multi-detector architecture verified with explicit kind/flag assertions |
| test_recall_orchestrator.py | GOOD | LOW | Golden test with explicit ordering and score constraints — strong oracle |
| test_migrate_memory_structure.py | GOOD | LOW | Boolean + structural assertions with clear pass/fail criteria |
| test_session_context_recovery.py | GOOD | MEDIUM | Fake client records call chains — verifies query shape and filter predicates |
| test_pre_compact_backup.py | GOOD | LOW | Well-scoped with explicit output shape verification |

## Over-mocking Risk Analysis

The memory cluster tests follow a consistent pattern of creating fake/mock Supabase clients. This is **necessary** (no real DB in unit tests) but creates an over-mocking risk:

1. **Call-chain assertions** — tests like `test_pretooluse_recall.py` verify that `client.rpc.return_value.execute.return_value.data = rows` which tests the mock wiring, not the actual Supabase response handling
2. **Dual verification gap** — extensive mock-based testing means that real integration bugs (RLS policy changes, schema drift, RPC signature changes) won't be caught by these tests
3. **Mitigation** — the project mitigates this with separate integration tests (smoke tests, schema-drift checks) and CI guards

## Scoring

| Penalty Source | Count | Weight | Penalty |
|---------------|-------|--------|---------|
| CRITICAL | 0 | 2.0 | 0 |
| HIGH | 2 | 1.0 | 2.0 |
| MEDIUM | 3 | 0.5 | 1.5 |
| LOW | 3 | 0.2 | 0.6 |
| **Total penalty** | | | **4.1** |
| **Score** | | | **5.9/10** |

## Summary

Overall Oracle Effectiveness Score: **5.9/10**

- **8 findings** — 2 HIGH, 3 MEDIUM, 3 LOW
- **Primary concern**: Over-mocking pattern in files with deep mock chains (test_memory_server.py, test_pretooluse_recall.py)
- **Strength**: Most files have strong behavior-level oracles (test_recall_orchestrator.py golden test, test_episode_extractor.py provenance verification)
- **Recommendation**: Add integration-level contract tests for critical RPC interfaces; current unit tests provide good coverage of logic but mock-Supabase assertions don't verify real DB behavior
- **No snapshot-only tests detected** — all tests use semantic assertions tied to domain behavior
