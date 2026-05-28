# Test Trustworthiness Audit Report

<!-- AUDIT-META
worker: ln-635
category: Test Trustworthiness
domain: memory_cluster
scan_path: tests/
score: 8.5
total_issues: 4
critical: 0
high: 0
medium: 3
low: 1
status: completed
-->

## Checks

| ID | Check | Status | Details |
|----|-------|--------|---------|
| api_isolation | External API dependency control | passed | All external calls (Supabase, VoyageAI, Anthropic) stubbed via MockClient/MagicMock |
| db_isolation | Database dependency control | passed | All Supabase DB calls mocked — no real database connections in unit tests |
| fs_isolation | File system isolation | warning | test_memory_server_script_launch.py uses real subprocess to launch server.py; test_recall_audit.py writes temp jsonl files |
| time_isolation | Time/date dependency control | passed | Deterministic timestamps via fixed datetime or datetime.now(timezone.utc) with _iso_days_ago helper |
| random_isolation | Random value control | passed | No Math.random() usage; tests use seeded fixed data |
| network_isolation | Network request isolation | passed | All HTTP paths mocked or stubbed |
| flaky_tests | Flaky test detection | passed | No setTimeout/setInterval patterns; all async operations properly awaited |
| order_dependency | Order-dependent test detection | passed | No visible order dependency; shared state reset via fixtures |
| shared_state | Shared mutable state | passed | Module-level state isolated per test function/class |
| default_value_blindness | Default config value testing | warning | Some tests use default configs — see findings below |

## Findings

| Severity | Location | Issue | Principle | Recommendation | Effort |
|----------|----------|-------|-----------|----------------|--------|
| MEDIUM | tests/test_memory_server_script_launch.py:28-66 | Real subprocess.Popen to launch server.py — test spawns real Python process with subprocess.Popen; 3s sleep for race condition; process lifecycle management | Isolation: FS | Replace with import-based smoke test that verifies the MCP handler registration without spawning a subprocess | M |
| MEDIUM | tests/test_pretooluse_recall.py:240-474 | _run_main helper creates real temp directories and file I/O for each test invocation — uses tmp_path per test but still exercises real file system for stdin mock | Isolation: FS | Accepted — tmp_path is pytest-managed and cleaned up between runs; low risk | S |
| MEDIUM | tests/test_recall_audit.py:47-51 | _write_jsonl fixture writes real files to tmp_path; each test creates/reads actual JSONL files | Isolation: FS | Accepted — tmp_path scoping ensures isolation; risk is low | S |
| LOW | tests/test_memory_server.py | 2008-line monolithic test file likely uses default Supabase config values for mock setup | Determinism: Default Value | Audit mock Supabase config values — ensure test assertions use non-default values to detect config-drift | M |

## Isolation Analysis Detail

### External API Control (PASS)
All test files properly mock external dependencies:
- Supabase client is stubbed via MagicMock, _FakeClient, or custom fake classes in every file
- HTTP/HTTPS calls (Anthropic API, VoyageAI) are stubbed or guarded by API key checks
- MCP SDK imports are mocked via module-level stubs

### Database Isolation (PASS)
- No test file connects to a real database
- Supabase RPC calls return canned data via mock
- The pattern `client.rpc.return_value.execute.return_value = MagicMock(data=...)` is used consistently

### File System Isolation (WARNING)
Three areas where real filesystem operations occur:
1. **test_memory_server_script_launch.py** — actual subprocess to test import chain
2. **test_recall_audit.py** — _write_jsonl creates real temp JSONL files
3. **test_pretooluse_recall.py** — tmp_path is used for cache isolation

All use pytest's tmp_path which is ephemeral and scoped per-function — acceptable for unit tests.

### Time/Date Isolation (PASS)
- test_recall_orchestrator.py uses `_iso_days_ago` helper with `datetime.now(timezone.utc)` — time-dependent but deterministic within a single call
- test_session_context_recovery.py uses fixed `datetime.now(timezone.utc)` with timedelta arithmetic
- No flaky time-dependent assertions observed

### Network Isolation (PASS)
- All HTTP paths stubbed: supabase.create_client is a no-op when env vars missing
- httpx is module-level stubbed in files that need it (episode_extractor)
- No test makes real network calls

## Determinism Analysis Detail

### Flaky Test Risk (LOW)
- No setTimeout/setInterval patterns
- All async tests use proper await with pytest.mark.asyncio
- Subprocess test (test_memory_server_script_launch.py) has inherent timing variance from the 3s sleep — low flakiness risk but non-zero

### Order Dependency (LOW)
- Tests use function-level or class-level isolation
- No mutable module-level state shared between tests
- pytest tmp_path provides clean directories per function

### Shared Mutable State (NONE)
- No detected shared mutable state between test functions/classes
- _MockClient instances are created per-test
- monkeypatch is properly scoped

## Summary

Overall Trustworthiness Score: **8.5/10**

- **3 MEDIUM** findings — mostly related to real filesystem I/O via tmp_path (acceptable) and one subprocess-based test
- **1 LOW** finding — default value audit recommended for the large test_memory_server.py
- **No flaky tests detected**
- **No order-dependent tests detected**
- **No shared mutable state issues**

The memory cluster tests are highly trustworthy. The mock/stub architecture is consistent across all 13 files. The subprocess test is the primary isolation concern, but it serves a unique purpose (detecting circular import bugs) that can't be easily tested via pure import.
