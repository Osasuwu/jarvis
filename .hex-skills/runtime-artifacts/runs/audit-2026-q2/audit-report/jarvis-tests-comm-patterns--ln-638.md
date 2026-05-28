# Oracle Effectiveness Audit Report

<!-- AUDIT-META
worker: ln-638
category: Oracle Effectiveness
domain: comm_patterns
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
| assertion_strength | Assertion quality and completeness | passed | Strong, behavior-level assertions throughout |
| meaningful_oracle | Oracle tied to product behavior | passed | All tests verify domain-meaningful behavior |
| snapshot_oracle | Snapshot-only testing | passed | No snapshot-only tests |
| over_mocking | Mock-proves-mock patterns | passed | No mock-proves-mock patterns; injected functions are tested through observable side effects |
| mutation_style_evidence | Mutation testing evidence | skipped | No mutation reports available |

## Findings

| Severity | Location | Issue | Principle | Recommendation | Effort |
|----------|----------|-------|-----------|----------------|--------|
| MEDIUM | tests/test_comm_patterns_scrubber.py:168-207 | schema drift sentinel test reads secret-scanner.py with regex-based label extraction — the regex pattern `r',\s*"([A-Za-z][A-Za-z0-9 /]+(?:Key|Token|PAT))"'` may silently break if the scanner file formatting changes | Oracle: Maintainability | Add a comment linking to the regex contract; consider a structured metadata format instead of regex extraction | S |
| LOW | tests/test_comm_patterns_backfill.py:136-143 | test_run_uses_shared_confidence_threshold verifies backfill imports the same threshold as the live extractor — oracle is `assert A == B` which is correct but narrow | Oracle: Scope | Consider adding what happens when thresholds drift (e.g., the backfill should use the live value, not the old one) | S |

## Oracle Quality by File

| Test File | Assertion Quality | Over-mocking Risk | Oracle Note |
|-----------|------------------|-------------------|-------------|
| test_comm_patterns_backfill.py | GOOD | LOW | Determinism guarantee: same input → same session ID; clean pass/fail assertions |
| test_comm_patterns_classifier.py | GOOD | LOW | JSON parsing with explicit expected shapes; schema sentinel reads real schema.sql — gold standard regression guard |
| test_comm_patterns_extractor.py | GOOD | LOW | Idempotency tested via re-run → zero-duplicate assertion; watermark advancement verified by position; flaky classifier retry tested with tracked counter |
| test_comm_patterns_scrubber.py | GOOD | LOW | Every secret type has explicit before/after assertion; two-segment JWT sentinel proves negative matching; dotenv short-value false-positive guard |

## Notable Strong Oracles

1. **test_comm_patterns_classifier.py:135-148** — `test_valid_labels_match_schema_check_constraint` reads schema.sql directly and compares Python enum values to the DB CHECK constraint. This is a permanent drift sentinel with no mock gap.

2. **test_comm_patterns_scrubber.py:167-207** — `test_scrubber_secret_labels_match_secret_scanner_coverage` cross-references two independent regex files and asserts coverage floor. Complex contract guard between subsystems.

3. **test_comm_patterns_extractor.py:151-177** — `test_re_run_produces_zero_duplicate_rows` proves idempotency through the store's observable state. The oracle is "second run writes 0 rows" — a strong behavioral assertion.

4. **test_comm_patterns_extractor.py:394-444** — `test_partial_failure_does_not_skip_failed_turn_on_next_run` has a multi-step flaky classifier scenario verified by final anchor set membership — tests watermark recovery with observable state.

## Summary

Overall Oracle Effectiveness Score: **9.0/10**

- **2 findings** — 1 MEDIUM, 1 LOW
- **Outstanding oracle quality** across all 4 files
- No over-mocking, no snapshot-only tests, no weak assertions
- Schema drift sentinels (classifier ↔ schema.sql, scrubber ↔ secret-scanner.py) are high-value
- The comm-patterns cluster sets the standard for test oracle quality in the project
