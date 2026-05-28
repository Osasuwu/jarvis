# Portfolio Value Audit Report

<!-- AUDIT-META
worker: ln-633
category: Portfolio Value
domain: decision_events
scan_path: tests/
score: 8.5
total_issues: 2
critical: 0
high: 1
medium: 1
low: 0
status: completed
-->

## Checks

| ID | Check | Status | Details |
|----|-------|--------|---------|
| value_score | Impact × Probability scoring | passed | All 9 test suites scored |
| delete_candidates | Low-value tests identified | passed | 0 DELETE candidates |
| merge_candidates | Duplicate coverage detected | passed | 0 MERGE candidates |
| rewrite_candidates | Medium-value tests needing rewrite | passed | 0 REWRITE candidates |
| keep_candidates | High-value tests | passed | 9 KEEP candidates |
| regression_guard_check | Layer-2 regression guard verification | passed | Schema sentinel tests verified in substrate, record_decision, fok_outcome_linkage |

## Detailed Scores

| Test File | Lines | Impact (1-5) | Probability (1-5) | Score | Decision | Notes |
|-----------|-------|-------------|-------------------|-------|----------|-------|
| test_record_decision.py | 561 | 4 | 4 | 16 | KEEP | Core handler with validation, insert, and schema guard; largest file in cluster |
| test_record_decision_canonical_dualwrite.py | 227 | 4 | 3 | 12 | KEEP | C17 dual-write integration; OTel key injection; failure tolerance |
| test_record_decision_gate.py | 177 | 4 | 4 | 16 | KEEP | Safety-critical Tier 2 hook gate; empty memories_used blocking |
| test_fok_batch.py | 454 | 4 | 4 | 16 | KEEP | Complex batch pipeline with edge cases for verdict routing, dedup, hit_count |
| test_fok_outcome_linkage.py | 213 | 3 | 3 | 9 | KEEP | Outcome linkage and schema regression guards for fok calibration |
| test_events_canonical_substrate.py | 313 | 5 | 3 | 15 | KEEP | Schema drift sentinel — columns, indexes, matviews, RLS, triggers, cron |
| test_events_canonical_writer.py | 228 | 4 | 3 | 12 | KEEP | Buffer/drain/overflow behavior for events_canonical writer |
| test_backfill_outcome_memories.py | 93 | 2 | 2 | 4 | KEEP | Well-scoped pure-function URL parsing tests |
| test_trace_context.py | 106 | 3 | 3 | 9 | KEEP | Trace ContextVar primitives with nesting and asyncio isolation |

## Findings

| Severity | Location | Issue | Principle | Recommendation | Effort |
|----------|----------|-------|-----------|----------------|--------|
| HIGH | tests/test_record_decision.py | 561 lines — largest file in the cluster; combines handler tests, validation, UUID resolution, name resolution, and schema guard in one monolith | Maintainability | Consider splitting into test_record_decision_handler.py, test_record_decision_validation.py, and retaining the schema guard as a standalone test | M |
| MEDIUM | tests/test_backfill_outcome_memories.py | Only tests pure-function URL parsing helpers (_parse_issue_number, _parse_pr_number, _extract_single_hash); DB-interaction paths (_build_hash_to_memory_index, _resolve_memory_name, backfill) are tested manually | Coverage | Consider adding integration tests for the DB paths using a mock store, or document manual test procedure in the PR template | S |

## Summary

Overall Portfolio Value Score: **8.5/10**

- **9 KEEP** — all test files provide strong value with minimal maintenance overhead
- **0 DELETE / 0 MERGE / 0 REWRITE** — no files recommended for deletion or consolidation
- The decision/events cluster is well-structured across 9 files covering the C17 events_canonical substrate, FOK calibration, trace propagation, and gate safety
- Schema sentinel tests (substrate, record_decision, fok_outcome_linkage) provide high-value regression guards
