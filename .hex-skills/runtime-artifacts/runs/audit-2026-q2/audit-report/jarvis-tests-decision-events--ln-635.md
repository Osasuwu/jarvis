# Test Trustworthiness Audit Report

<!-- AUDIT-META
worker: ln-635
category: Test Trustworthiness
domain: decision_events
scan_path: tests/
score: 9.0
total_issues: 2
critical: 0
high: 0
medium: 1
low: 1
status: completed
-->

## Checks

| ID | Check | Status | Details |
|----|-------|--------|---------|
| api_isolation | External API dependency control | passed | All external calls (Supabase, VoyageAI, httpx) stubbed via MagicMock or custom fakes |
| db_isolation | Database dependency control | passed | All Supabase RPC/table calls mocked — no real database connections |
| fs_isolation | File system isolation | warning | test_events_canonical_substrate.py reads real migration and schema.sql files from the repo |
| time_isolation | Time/date dependency control | passed | No time.sleep() usage; all time references use fixed datetime or contextvars |
| random_isolation | Random value control | passed | UUID generation in trace_context tested for uniqueness, not specific values |
| network_isolation | Network request isolation | passed | All HTTP paths stubbed (httpx, urllib) |
| flaky_tests | Flaky test detection | passed | No detected flaky patterns; all async operations properly awaited |
| order_dependency | Order-dependent test detection | passed | Tests isolated per function; no module-level mutable state between tests |
| shared_state | Shared mutable state | warning | test_events_canonical_writer.py uses module-level buffer with _isolate_buffer autouse fixture — properly managed but crash during yield would leave state dirty |
| default_value_blindness | Default config value testing | passed | Tests use explicit non-default values for config assertions |

## Findings

| Severity | Location | Issue | Principle | Recommendation | Effort |
|----------|----------|-------|-----------|----------------|--------|
| MEDIUM | tests/test_events_canonical_substrate.py:28-29, 62-70 | Schema sentinel tests read real migration and schema.sql files via Path.read_text() — real file I/O dependency | Isolation: FS | Accepted — files are checked into the repo and tests fail loudly if paths change; the schema sentinel pattern requires reading real DDL | S |
| LOW | tests/test_events_canonical_writer.py:30-35 | _isolate_buffer fixture manages module-level buffer state; autouse fixture clears before yield, but a crashing test would skip the post-yield cleanup | Isolation: Shared State | The pre-yield clear() ensures each test starts clean regardless; post-yield clear is a safety net only. Risk is minimal | S |

## Isolation Analysis Detail

### External API Control (PASS)
- All Supabase clients are stubbed via MagicMock or custom _stub_client helpers
- test_fok_batch.py patches httpx for VoyageAI (judge_via_haiku) and Supabase calls
- test_events_canonical_writer.py uses _stub_client factory with controlled insert_returns/insert_raises
- No test makes real external API calls

### Database Isolation (PASS)
- No test file connects to a real database
- Supabase RPC/table calls return canned data via MagicMock or custom fakes
- test_record_decision_gate.py tests gate evaluate() with MockSupabaseClient — no real DB
- test_fok_batch.py patches Supabase calls at the table/RPC level

### File System Isolation (WARNING)
- test_events_canonical_substrate.py reads real migration SQL and schema.sql files
- This is intentional — the schema sentinel pattern requires reading actual DDL to verify column/index/matview declarations
- All other files use in-memory data structures; no temp directories or file writes

### Time/Date Isolation (PASS)
- No time.sleep() usage found in any test file
- test_fok_batch.py uses deterministic datetime references
- test_trace_context.py is pure ContextVar logic — no time dependency
- test_events_canonical_writer.py tests buffer behavior synchronously

### Network Isolation (PASS)
- test_fok_batch.py patches httpx.post for LLM judge calls
- test_record_decision.py mocks Supabase client at the instance level
- test_events_canonical_writer.py _stub_client never makes real network calls
- All other files have no network dependencies

## Determinism Analysis Detail

### Flaky Test Risk (NONE)
- No setTimeout/setInterval patterns
- No time.sleep() calls
- All async tests use proper await with pytest.mark.asyncio
- No subprocess spawning

### Order Dependency (NONE)
- Tests use function-level isolation
- No mutable module-level state shared between tests (buffer state is fixture-managed)
- pytest fixtures ensure clean state per test

### Shared Mutable State (LOW)
- test_events_canonical_writer.py module-level _buffer dict managed via _isolate_buffer autouse fixture
- Pre-yield clear() guarantees clean start; post-yield clear() is safety net
- If a test crashes during execution, the post-yield cleanup is skipped, but the next test's pre-yield clear() still works
- Acceptable for module-internal buffer state that is not read by other modules

## Summary

Overall Trustworthiness Score: **9.0/10**

- **1 MEDIUM** finding — real file I/O for schema sentinel tests (accepted, intentional)
- **1 LOW** finding — module-level buffer state with fixture-managed lifecycle
- **No flaky tests detected**
- **No order-dependent tests detected**
- **No subprocess-based tests** (unlike the memory cluster)
- The decision/events cluster is the most trustworthy test group in the project
