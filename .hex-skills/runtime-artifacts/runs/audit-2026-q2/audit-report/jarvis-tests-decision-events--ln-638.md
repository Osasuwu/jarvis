# Oracle Effectiveness Audit Report

<!-- AUDIT-META
worker: ln-638
category: Oracle Effectiveness
domain: decision_events
scan_path: tests/
score: 7.0
total_issues: 7
critical: 0
high: 0
medium: 5
low: 2
status: completed
-->

## Checks

| ID | Check | Status | Details |
|----|-------|--------|---------|
| assertion_strength | Assertion quality and completeness | warning | Several files have mock-call-chain assertions — see findings |
| meaningful_oracle | Oracle tied to product behavior | passed | Most assertions verify domain-meaningful behavior |
| snapshot_oracle | Snapshot-only testing | passed | No snapshot-only tests detected |
| over_mocking | Mock-proves-mock patterns | warning | Several tests verify mock call arguments — see findings |
| mutation_style_evidence | Mutation testing evidence | skipped | No mutation reports available |

## Findings

| Severity | Location | Issue | Principle | Recommendation | Effort |
|----------|----------|-------|-----------|----------------|--------|
| MEDIUM | tests/test_record_decision.py | Handler tests assert mock call chains (`mock_client.table.assert_called_with`, `mock_client.rpc.return_value.execute.assert_called_once`) — verifies mock wiring, not actual DB behavior | Over-mocking | Strengthen with contract-style test doubles that enforce real response shapes; the schema regression guard at end of file already mitigates schema drift | M |
| MEDIUM | tests/test_record_decision_canonical_dualwrite.py | Dual-write assertions rely on `mock_client.rpc.return_value.execute.return_value = MagicMock(data=...)` — deep mock chains verify call structure rather than response handling | Over-mocking | Reduce mock depth; use lightweight fake that returns real-shaped responses; the OTel injection assertions are behavior-level and should be preserved | M |
| MEDIUM | tests/test_fok_batch.py | judge_via_haiku tests patch httpx.post with MagicMock and assert `mock_post.call_args` — verifies call structure, not actual LLM response parsing | Over-mocking | Consider a response fixture that exercises the JSON-parsing path; the `try_insert_known_unknown` dedup/hit_count tests are strong and should be kept as-is | M |
| MEDIUM | tests/test_fok_outcome_linkage.py | Core linkage logic tested via simple boolean assertions (`assert result is True`) — narrow oracle that doesn't verify the linking mechanism | Oracle: Scope | Extend assertions to verify the linked data shape (which outcome_id was assigned, that the join produces expected fields) | S |
| MEDIUM | tests/test_events_canonical_writer.py | Deep mock chains (`client.table.return_value.insert.call_args[0][0]`) extract inserted data but the assertion target is mock-wiring structure | Over-mocking | Buffer/drain/overflow tests are strong behavioral oracles; only the `insert.call_args` pattern needs de-risking — consider a RecordingClient that captures inserted rows in a plain list | S |
| LOW | tests/test_trace_context.py | Assertions are structural: `isinstance(tid, str)`, `len(tid) == 32`, `uuid.UUID(tid)` — verify type contracts but not behavioral correctness of trace propagation | Oracle: Structure | Accepted — the module's contract IS structural (ContextVar set/reset, UUID format); type-level assertions are appropriate | - |
| LOW | tests/test_backfill_outcome_memories.py | Pure-function URL parsing tests with `assert X == Y` — correct but narrow; the real complexity (DB backfill logic) is untested | Oracle: Scope | Add mock-based tests for the DB-interaction helpers, or document manual test procedure in the docstring | S |

## Oracle Quality by File

| Test File | Assertion Quality | Over-mocking Risk | Oracle Note |
|-----------|------------------|-------------------|-------------|
| test_record_decision.py | GOOD | MEDIUM | Schema regression guard at end of file reads schema.sql — gold standard; handler tests use mock call chains |
| test_record_decision_canonical_dualwrite.py | GOOD | MEDIUM | OTel key injection assertions are strong; dual-write failure tolerance verifies fallback behavior |
| test_record_decision_gate.py | GOOD | LOW | Clear boolean pass/fail on gate decisions; subprocess path verified through mock call count |
| test_fok_batch.py | GOOD | MEDIUM | Extensive dedup/hit_count/verdict routing edge cases; httpx patch weakens LLM judge oracle |
| test_fok_outcome_linkage.py | GOOD | MEDIUM | Schema regression guards are strong; core logic uses narrow boolean assertions |
| test_events_canonical_substrate.py | GOLD | NONE | Full schema drift sentinel — columns, indexes, matviews, RLS, triggers, cron — no mocks |
| test_events_canonical_writer.py | GOOD | MEDIUM | Buffer/drain/overflow verified through observable state; insert assertions use mock wiring |
| test_backfill_outcome_memories.py | GOOD | NONE | Pure-function URL parsing with edge cases; DB paths untested |
| test_trace_context.py | GOOD | NONE | Appropriate structural assertions for ContextVar contract; asyncio isolation test is strong |

## Notable Strong Oracles

1. **test_events_canonical_substrate.py** — Full schema drift sentinel covering events_canonical table shape (12 columns), 4 indexes (1 partial), 2 materialized views, pg_notify trigger with payload contract, RLS policies (migration vs post-#542 split-anon), and pg_cron schedules. Reads real migration and schema.sql files. This is the gold standard for regression guard tests in the project.

2. **test_record_decision.py:final-guard** — Schema regression guard reads schema.sql and asserts stored_procedure name matches the Python handler's expectation. Cross-reference between two independent sources (DDL + handler code).

3. **test_fok_batch.py:zero-confidence-guard** — `test_fok_judgments_have_non_null_confidence` asserts that every fok_judgments row has a non-null confidence value. Proves the insert path always writes confidence.

4. **test_events_canonical_writer.py:drain-test** — `test_buffered_events_drain_on_next_success` proves degraded=true replay through observable state: buffer length transitions (1→0), drain insert carries `degraded=True`, new insert does not. Multi-step behavioral assertion with no mocks in the assertion path.

5. **test_trace_context.py:async-isolation** — `test_async_tasks_have_isolated_context` proves per-task ContextVar isolation via asyncio.gather with yield-to-other. Strong behavioral assertion about concurrent trace propagation.

## Scoring

| Penalty Source | Count | Weight | Penalty |
|---------------|-------|--------|---------|
| CRITICAL | 0 | 2.0 | 0 |
| HIGH | 0 | 1.0 | 0 |
| MEDIUM | 5 | 0.5 | 2.5 |
| LOW | 2 | 0.2 | 0.4 |
| **Total penalty** | | | **2.9** |
| **Score** | | | **7.0/10** |

## Summary

Overall Oracle Effectiveness Score: **7.0/10**

- **7 findings** — 0 HIGH, 5 MEDIUM, 2 LOW
- **Primary concern**: Moderate over-mocking in 4 of 9 files — record_decision, dualwrite, fok_batch, and events_canonical_writer all use mock call-chain assertions that verify mock wiring rather than real behavior
- **Strength**: Schema sentinel tests (substrate, record_decision, fok_outcome_linkage) provide strong regression guards; buffer/drain behavioral tests in events_canonical_writer prove multi-step state transitions
- **Gold standard**: test_events_canonical_substrate.py sets the bar for schema drift sentinels with comprehensive column/index/matview/trigger/RLS/cron coverage
- **No snapshot-only tests detected** — all tests use semantic assertions tied to domain behavior
