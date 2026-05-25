# Test Trustworthiness Audit Report

<!-- AUDIT-META
worker: ln-635
category: Test Trustworthiness
domain: ci
scan_path: tests/ci/
score: 7.5
total_issues: 3
critical: 0
high: 0
medium: 3
low: 0
status: completed
-->

## Checks

| ID | Check | Status | Details |
|----|-------|--------|---------|
| api_isolation | External API dependency control | passed | No external API calls |
| db_isolation | Database dependency control | passed | No database dependencies |
| fs_isolation | File system isolation | failed | 8/9 files read real repo files; test_anchor_links_guard.py writes temp files to REPO_ROOT |
| time_isolation | Time/date dependency control | passed | No time.sleep() calls |
| random_isolation | Random value control | passed | No random value dependencies |
| network_isolation | Network request isolation | passed | No network calls |
| flaky_tests | Flaky test detection | passed | No detected flaky patterns |
| order_dependency | Order-dependent test detection | passed | Tests isolated per function/class |
| shared_state | Shared mutable state | passed | No module-level mutable state |
| default_value_blindness | Default config value testing | passed | All tests replicate workflow logic with explicit values |

## Findings

| Severity | Location | Issue | Principle | Recommendation | Effort |
|----------|----------|-------|-----------|----------------|--------|
| MEDIUM | tests/ci/test_anchor_links_guard.py:248-261 | test_find_broken_links_cross_file_anchor_missing creates temp test1.md + test2.md directly in REPO_ROOT via write_text; cleanup is try/finally unlink(missing_ok=True) — crash before finally leaves stale files in repo root | Isolation: FS | Use pytest tmp_path fixture for all temp file creation; read_text from tmp_path paths for the corpus | S |
| MEDIUM | tests/ci/test_anchor_links_guard.py:322-343 | test_live_no_broken_anchors_in_corpus calls get_corpus() which scans the entire repo for .md files and runs find_broken_links against the live corpus — real file I/O across hundreds of files | Isolation: FS | Accepted — this is the core live assertion of the anchor lint guard. The assertion is the feature, not a side effect. | S |
| MEDIUM | tests/ci/test_powershell_encoding_guard.py:44-51 | _tracked_ps_files() runs real `git ls-files` subprocess to enumerate tracked PowerShell files — real subprocess dependency | Isolation: FS | Accepted — git ls-files is a local read-only operation and the canonical way to list tracked files; risk is minimal | S |

## Isolation Analysis Detail

### External API Control (PASS)
- No test makes external API calls — all dependencies are local (repo files, git commands)

### Database Isolation (PASS)
- No database dependencies in any CI test file

### File System Isolation (FAILED)

The tests/ci/ directory has the **highest FS dependency** of any cluster in the project:

1. **8 of 9 files read real repo files** — workflow YAML, schema.sql, migration files, .pre-commit-config.yaml, .sandcastle/prompt.md. This is intentional (schema sentinel pattern requires reading real DDL), but makes tests dependent on specific file paths.

2. **test_anchor_links_guard.py writes to REPO_ROOT** — lines 248-261 create `REPO_ROOT / "test1.md"` and `REPO_ROOT / "test2.md"` directly. While cleanup exists, a crash between write_text and unlink leaves stale files in the repo root. This is the only test in the project writing real files outside of pytest tmp_path.

3. **test_live_no_broken_anchors_in_corpus** scans every .md file in the repo — hundreds of files. This is by design: it's a live assertion.

4. **test_powershell_encoding_guard.py** runs `git ls-files` subprocess — read-only but real subprocess.

### Network Isolation (PASS)
- No network calls in any CI test

## Determinism Analysis Detail

### Flaky Test Risk (LOW)
- test_live_no_broken_anchors_in_corpus depends on the current state of all repo .md files — if a PR introduces a broken anchor, this test fails. This is the intended behavior (the CI guard).
- No time-dependent or async flakiness patterns

### Order Dependency (NONE)
- Tests use function-level isolation
- No shared mutable state

## Summary

Overall Trustworthiness Score: **7.5/10**

- **3 MEDIUM** findings — all related to FS isolation (the cluster's defining characteristic as meta-tests for CI infrastructure)
- **No flaky tests detected**
- **No time/random/network isolation issues**
- The FS dependency is inherent to the meta-test pattern — these tests MUST read real workflow files to verify they haven't drifted
- The main actionable item is moving test_anchor_links_guard.py temp file creation from REPO_ROOT to tmp_path
