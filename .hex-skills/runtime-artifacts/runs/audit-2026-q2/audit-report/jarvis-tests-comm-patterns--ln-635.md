# Test Trustworthiness Audit Report

<!-- AUDIT-META
worker: ln-635
category: Test Trustworthiness
domain: comm_patterns
scan_path: tests/
score: 8.5
total_issues: 2
critical: 0
high: 0
medium: 2
low: 0
status: completed
-->

## Checks

| ID | Check | Status | Details |
|----|-------|--------|---------|
| api_isolation | External API dependency control | passed | All HTTP calls monkeypatched (urllib.request.urlopen) or replaced |
| db_isolation | Database dependency control | passed | InMemoryStore used instead of real DB |
| fs_isolation | File system isolation | warning | Real file I/O via tmp_path for JSONL fixtures |
| time_isolation | Time/date dependency control | warning | test_comm_patterns_extractor.py uses real time.sleep() for wall clock budget test |
| random_isolation | Random value control | passed | No random value dependencies |
| network_isolation | Network request isolation | passed | All network paths stubbed |
| flaky_tests | Flaky test detection | passed | No detected flaky patterns |
| order_dependency | Order-dependent test detection | passed | Tests isolated per function |
| shared_state | Shared mutable state | passed | No module-level mutable state |
| default_value_blindness | Default config value testing | skipped | All files test non-default values adequately |

## Findings

| Severity | Location | Issue | Principle | Recommendation | Effort |
|----------|----------|-------|-----------|----------------|--------|
| MEDIUM | tests/test_comm_patterns_extractor.py:447-479 | test_wall_clock_budget_aborts_loop uses real time.sleep(0.05) × up to 5 iterations (250ms minimum) — makes the test the slowest in the suite | Isolation: Determinism | Reduce sleep to 0.01s or use a mock time source; the test validates logic not timing precision | S |
| MEDIUM | tests/test_comm_patterns_extractor.py:24-27 | _write_jsonl helper writes real files to tmp_path per test — all extractor tests depend on real file I/O | Isolation: FS | Accepted — tmp_path is pytest-managed and isolated per-function; risk is minimal | S |

## Isolation Analysis Detail

### External API Control (PASS)
- test_comm_patterns_classifier.py patches `urllib.request.urlopen` for all HTTP paths
- test_comm_patterns_extractor.py injects `classify_fn` as a parameter — no real classifier called
- test_comm_patterns_backfill.py monkeypatches `call_ollama` for Ollama calls
- test_comm_patterns_scrubber.py is pure logic — no external deps at all

### Database Isolation (PASS)
- InMemoryStore is used consistently across all extractor tests
- No real Supabase or database connections in any test
- Backfill tests operate on synthetic cache files

### File System Isolation (WARNING)
- Real JSONL file writes in test_comm_patterns_extractor.py via `_write_jsonl` helper to tmp_path
- test_comm_patterns_backfill.py creates real cache directories and pattern files
- All use pytest tmp_path which is ephemeral and scoped per-function — acceptable

### Time/Date Isolation (WARNING)
- test_comm_patterns_extractor.py: `test_wall_clock_budget_aborts_loop` uses `time.sleep(0.05)` to simulate slow classification
- Not flaky per se (deterministic timing) but slower than necessary
- test_comm_patterns_backfill.py uses `datetime.fromisoformat` for validation — no time dependency issues

## Summary

Overall Trustworthiness Score: **8.5/10**

- **2 MEDIUM** findings — both in extractor tests (real time.sleep, real file I/O)
- **No flaky tests detected**
- **No shared mutable state**
- Strong isolation through InMemoryStore and monkeypatched HTTP
- The wall-clock budget test is the only meaningful risk — all other tests run cleanly and deterministically
