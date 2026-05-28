# Oracle Effectiveness Audit Report

<!-- AUDIT-META
worker: ln-638
category: Oracle Effectiveness
domain: ci
scan_path: tests/ci/
score: 9.5
total_issues: 2
critical: 0
high: 0
medium: 0
low: 2
status: completed
-->

## Checks

| ID | Check | Status | Details |
|----|-------|--------|---------|
| assertion_strength | Assertion quality and completeness | passed | Gold standard — every test has config + logic dimensions |
| meaningful_oracle | Oracle tied to product behavior | passed | All tests verify CI guard behavior, not mock wiring |
| snapshot_oracle | Snapshot-only testing | passed | No snapshot-only tests detected |
| over_mocking | Mock-proves-mock patterns | passed | Zero mocks across all 9 files — all tests verify real file content or pure functions |
| mutation_style_evidence | Mutation testing evidence | skipped | No mutation reports available |

## Findings

| Severity | Location | Issue | Principle | Recommendation | Effort |
|----------|----------|-------|-----------|----------------|--------|
| LOW | tests/ci/test_anchor_links_guard.py:248-261 | Temp files written to REPO_ROOT for cross-file anchor test — oracle tests find_broken_links behavior but creates real files as a side effect | Oracle: Side effects | Use tmp_path and adjust the corpus paths; the oracle quality (broken link detection) doesn't depend on writing to REPO_ROOT | S |
| LOW | tests/ci/test_powershell_encoding_guard.py:174-200 | test_allowlist_uncommented_warning uses recwarn fixture and prints warnings rather than asserting — oracle is informational, not a pass/fail assertion | Assertion Strength | Replace with assert-based check: fail CI when uncommented allowlist entries exist, with a transition period before tightening | S |

## Oracle Quality by File

| Test File | Assertion Quality | Over-mocking Risk | Oracle Note |
|-----------|------------------|-------------------|-------------|
| test_anchor_links_guard.py | GOLD | NONE | Three-layer guard (L1 string-not-found, L2 suffixed-N drift, L3 line-number annotations); live corpus scan is the strongest possible oracle |
| test_comm_patterns_schema.py | GOLD | NONE | Schema drift sentinel reads real schema.sql; parametrized column/index/enum/RLS/ADR cross-checks |
| test_memory_review_guard.py | GOOD | NONE | Migration file shape assertions with parametrized column checks |
| test_memory_review_schema.py | GOLD | NONE | Deriver schema sentinel with no-op backfill guard and decision-anchoring assertions |
| test_powershell_encoding_guard.py | GOOD | NONE | Allowlist-based lint with stale-entry validation; weak oracle on uncommented entries (recwarn print) |
| test_pr_body_check_guard.py | GOLD | NONE | Pure-Python reimplementation of workflow decision rule + YAML anchor assertions |
| test_sandcastle_prompt_md_guard.py | GOLD | NONE | Config check + logic check + semantic parity with sandcastle's own regex — triple-layer oracle |
| test_sandcastle_rls.py | GOLD | NONE | Full policy logic reimplementation with 4-table parametrized matrix; migration mirror cross-check |
| test_schema_drift_guard.py | GOLD | NONE | Founding meta-test (#326); config check + logic check + legacy-path regression guard |

## Notable Strong Oracles

1. **test_schema_drift_guard.py** — Founding meta-test for the project's entire CI guard pattern. Two-layer oracle: config check locks down the `paths:` filter, logic check reimplements the JS decision rule in Python. Includes a regression guard for the original #289/#310/#311 bug (supabase/schema.sql vs mcp-memory/schema.sql).

2. **test_sandcastle_rls.py** — Full pure-Python reimplementation of 4-table RLS policy logic (INSERT, UPDATE, DELETE) with 100+ parametrized assertions covering sandcastle prefix acceptance, host-owned rejection, provenance forgery prevention, and case-sensitive edge cases. Migration-to-schema mirror cross-check for both slice 3 and slice 3.5.

3. **test_anchor_links_guard.py:322-343** — `test_live_no_broken_anchors_in_corpus` runs the full anchor audit against every .md file in the repo. This is the strongest possible oracle: it proves the current state of the corpus is clean, not just that the detection logic works on synthetic data.

4. **test_comm_patterns_schema.py** — Enumerates all 6 labels, 13 columns, 3 indices, and cross-references the ADR document. The `test_primary_label_check_constraint_lists_six_labels` test parses the actual CHECK constraint from schema.sql and compares against expected set — drift is caught at PR time.

5. **test_memory_review_schema.py** — The `test_no_no_op_backfill_updates` test detects a specific anti-pattern (seqscan + ROW EXCLUSIVE lock for zero effect) and blocks it with a regex assertion. A value-add oracle that goes beyond "did the migration run" to "is the migration efficient."

## Scoring

| Penalty Source | Count | Weight | Penalty |
|---------------|-------|--------|---------|
| CRITICAL | 0 | 2.0 | 0 |
| HIGH | 0 | 1.0 | 0 |
| MEDIUM | 0 | 0.5 | 0 |
| LOW | 2 | 0.2 | 0.4 |
| **Total penalty** | | | **0.4** |
| **Score** | | | **9.5/10** |

## Summary

Overall Oracle Effectiveness Score: **9.5/10**

- **2 findings** — 0 MEDIUM, 2 LOW
- **Zero mocks across all 9 files** — every test verifies real file content or pure function behavior. The only project cluster with this property.
- **Gold standard pattern**: config check + logic check two-layer oracle is used consistently across all guard meta-tests
- **Strongest oracles in the project**: live corpus scan (anchor guard), full policy reimplementation (sandcastle RLS), schema-to-ADR cross-reference (comm_patterns schema)
- The tests/ci/ directory sets the standard for test oracle quality across the entire project
