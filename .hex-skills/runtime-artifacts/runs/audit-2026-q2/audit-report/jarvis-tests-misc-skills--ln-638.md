# Oracle Effectiveness Audit Report

<!-- AUDIT-META
worker: ln-638
category: Oracle Effectiveness
domain: misc_skills
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
| assertion_strength | Assertion quality and completeness | passed | Strong behavioral assertions across all 6 files |
| meaningful_oracle | Oracle tied to product behavior | passed | All tests verify domain-meaningful behavior |
| snapshot_oracle | Snapshot-only testing | passed | No snapshot-only tests detected |
| over_mocking | Mock-proves-mock patterns | passed | 4 of 6 files are pure logic with zero mocks; remaining 2 use well-designed stubs with behavioral assertions |
| mutation_style_evidence | Mutation testing evidence | skipped | No mutation reports available |

## Findings

| Severity | Location | Issue | Principle | Recommendation | Effort |
|----------|----------|-------|-----------|----------------|--------|
| MEDIUM | tests/test_morning_check.py:23-128 | Custom stub layer (_StubClient, _Table, _UpsertQuery, _SelectQuery — 4 classes, ~100 lines) creates indirection between test and real Supabase query behavior | Oracle: Maintainability | Add a contract test that verifies the stub methods match real Supabase query builder method signatures; or reduce stub surface by using MagicMock for non-critical paths | M |
| LOW | tests/test_risk_radar.py:105-107, 112-113, 117-118 | _check_ci_instability and other pattern checkers patch _run_gh with canned JSON responses — oracle depends on response shape matching real gh CLI output | Oracle: Mock shape | Add a regression guard that verifies the expected JSON keys match real gh CLI output for each pattern | S |

## Oracle Quality by File

| Test File | Assertion Quality | Over-mocking Risk | Oracle Note |
|-----------|------------------|-------------------|-------------|
| test_classifier.py | GOOD | NONE | Pure function tests with strong edge-case coverage (truncation, JSON parsing, normalization, downgrade path) |
| test_principal.py | GOOD | NONE | Clean parametrized assertions for env var parsing; #429 regression guard (piped stdin) is a strong behavioral oracle |
| test_protected_files.py | GOOD | NONE | Comprehensive should_block matrix (4 principals × 2 categories + 2 edge classes); cross-platform path normalization |
| test_morning_check.py | GOOD | LOW | Custom stubs record operations for inspection; assertions verify payload shape, not mock call counts |
| test_secret_scanner.py | GOLD | NONE | 25+ binary oracles for secret patterns, bash dangers, heredocs, memory extraction — every assertion is a pass/fail on real behavior |
| test_risk_radar.py | GOOD | LOW | Severity boundary tests for all 5 patterns; parametrized classes with explicit threshold-to-severity mappings |

## Notable Strong Oracles

1. **test_secret_scanner.py** — Comprehensive binary oracle coverage for the entire security surface: 15+ secret patterns (API keys, tokens, JWT, private keys), 15+ bash danger patterns (cat .env, env dump, base64, netcat), heredoc stripping, field extraction, memory content scanning. Every assertion is a clear pass/fail on real detection behavior. No mocks, no indirection. Gold standard for security test oracles.

2. **test_principal.py:56-57** — `test_explicit_env_invalid_falls_through_to_default_live` proves the #429 behavioral contract: invalid env values return "live", not "autonomous". Regression guard for the isatty fallback removal fix.

3. **test_protected_files.py:203-211** — `test_canonical_blocks_non_live_principals` parametrized across 3 principals asserting the should_block matrix. Combined with `test_mirror_blocks_all_principals` (lines 217-233), the entire classify/should_block contract is verified in ~30 lines.

4. **test_risk_radar.py:95-145** — `TestCiInstability` class with 6 test methods proving critical/high/medium/none severity boundary logic. Each threshold is tested with explicit ratios that verify the constants are correctly applied.

## Scoring

| Penalty Source | Count | Weight | Penalty |
|---------------|-------|--------|---------|
| CRITICAL | 0 | 2.0 | 0 |
| HIGH | 0 | 1.0 | 0 |
| MEDIUM | 1 | 0.5 | 0.5 |
| LOW | 1 | 0.2 | 0.2 |
| **Total penalty** | | | **0.7** |
| **Score** | | | **9.0/10** |

## Summary

Overall Oracle Effectiveness Score: **9.0/10**

- **2 findings** — 1 MEDIUM, 1 LOW
- **Outstanding oracle quality** across all 6 files
- **No over-mocking** — 4 of 6 files are pure logic with zero mocks; the remaining 2 use well-factored stubs that verify behavioral outcomes
- **Gold standard**: test_secret_scanner.py is the project's best example of comprehensive binary oracle testing for security-critical code
- **No snapshot-only tests detected** — all tests use semantic assertions tied to domain behavior
- The misc skills cluster is the most consistently well-oracled group in the project
