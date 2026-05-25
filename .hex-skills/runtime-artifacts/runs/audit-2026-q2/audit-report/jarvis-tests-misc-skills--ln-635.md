# Test Trustworthiness Audit Report

<!-- AUDIT-META
worker: ln-635
category: Test Trustworthiness
domain: misc_skills
scan_path: tests/
score: 8.5
total_issues: 3
critical: 0
high: 0
medium: 2
low: 1
status: completed
-->

## Checks

| ID | Check | Status | Details |
|----|-------|--------|---------|
| api_isolation | External API dependency control | passed | All external calls (gh CLI, Supabase, httpx) stubbed via mock/patch |
| db_isolation | Database dependency control | passed | morning_check uses _StubClient — no real DB connections |
| fs_isolation | File system isolation | warning | protected_files.py and risk_radar.py use tmp_path for real file I/O |
| time_isolation | Time/date dependency control | warning | morning_check uses real datetime.now(UTC) for seed timestamps (intentional — see docstring) |
| random_isolation | Random value control | passed | No random value dependencies |
| network_isolation | Network request isolation | passed | All network paths stubbed (gh CLI → _run_gh, Supabase → _StubClient, httpx → MagicMock) |
| flaky_tests | Flaky test detection | passed | No detected flaky patterns |
| order_dependency | Order-dependent test detection | passed | Tests isolated per function/class |
| shared_state | Shared mutable state | passed | No module-level mutable state |
| default_value_blindness | Default config value testing | passed | All tests use explicit non-default values |

## Findings

| Severity | Location | Issue | Principle | Recommendation | Effort |
|----------|----------|-------|-----------|----------------|--------|
| MEDIUM | tests/test_protected_files.py:24-31 | fake_claude_home fixture creates real temp directory with monkeypatched JARVIS_CLAUDE_HOME — exercises real file system for path resolution | Isolation: FS | Accepted — tmp_path is pytest-managed and isolated per-function; testing path normalization inherently needs real paths | S |
| MEDIUM | tests/test_risk_radar.py:81-88, 339-365 | _load_repos writes conf files to tmp_path; _write_report creates real report files to tmp_path | Isolation: FS | Accepted — tmp_path scoping ensures isolation; risk is minimal | S |
| LOW | tests/test_morning_check.py:135-147 | _now_utc() returns real datetime.now(UTC) instead of a frozen value — intentional design choice to prevent seed date staleness (documented in detailed comment) | Isolation: Time | Accepted — assertions depend on relative behavior (exit codes, call counts), not absolute time values | S |

## Isolation Analysis Detail

### External API Control (PASS)
- test_risk_radar.py patches `_run_gh` for all gh CLI calls — no real GitHub API calls
- test_morning_check.py patches `get_client` with `_StubClient` — no real Supabase
- test_classifier.py stubs httpx via sys.modules guard — no real HTTP
- test_principal.py, test_protected_files.py, test_secret_scanner.py are pure logic — no external deps

### Database Isolation (PASS)
- test_morning_check.py uses _StubClient with seeded in-memory rows — no real DB
- All other files have no database dependencies

### File System Isolation (WARNING)
Two test files use real file I/O via tmp_path:
1. **test_protected_files.py** — fake_claude_home fixture creates a tmp directory to simulate ~/.claude/ structure for path resolution tests
2. **test_risk_radar.py** — _load_repos writes conf files; _write_report creates report files
All use pytest tmp_path which is ephemeral and scoped per-function.

### Time/Date Isolation (WARNING)
- test_morning_check.py: `_now_utc()` returns `datetime.now(UTC)` instead of a frozen value
- This was a deliberate fix (documented in lines 138-147): frozen time caused silent failures when the repo's "today" drifted more than 24h past the seed timestamp
- Assertions use relative behavior (exit code 0 vs 1, call count), not absolute time values — low risk
- test_risk_radar.py: `_iso()` helper uses `datetime.now(UTC)` — same pattern, same reasoning

### Network Isolation (PASS)
- test_risk_radar.py patches _run_gh at module level for all gh CLI interactions
- test_morning_check.py patches get_client with _StubClient
- test_classifier.py stubs httpx import
- No test makes real network calls

## Determinism Analysis Detail

### Flaky Test Risk (LOW)
- No time.sleep() calls in any test file
- The real-time `_now_utc()` in morning_check could theoretically produce different timestamps across runs, but assertions are relative (counts, exit codes, string containment) — not absolute time comparisons
- test_risk_radar.py _iso() helper is similarly benign

### Order Dependency (NONE)
- Tests use function-level or class-level isolation
- pytest tmp_path provides clean directories per function
- clean_env autouse fixture in test_principal.py ensures env var isolation

### Shared Mutable State (NONE)
- No detected shared mutable state between test functions/classes
- All stubs and mocks are created per-test
- monkeypatch is properly scoped

## Summary

Overall Trustworthiness Score: **8.5/10**

- **2 MEDIUM** findings — real file I/O via tmp_path in protected_files and risk_radar (acceptable, pytest-managed)
- **1 LOW** finding — real datetime.now(UTC) in morning_check (intentional, documented)
- **No flaky tests detected**
- **No order-dependent tests detected**
- **No shared mutable state issues**
- The misc skills cluster is highly trustworthy — 4 of 6 files are pure logic with zero isolation concerns
