# Portfolio Value Audit Report

<!-- AUDIT-META
worker: ln-633
category: Portfolio Value
domain: ci
scan_path: tests/ci/
score: 9.5
total_issues: 1
critical: 0
high: 0
medium: 0
low: 1
status: completed
-->

## Checks

| ID | Check | Status | Details |
|----|-------|--------|---------|
| value_score | Impact × Probability scoring | passed | All 9 test files scored |
| delete_candidates | Low-value tests identified | passed | 0 DELETE candidates |
| merge_candidates | Duplicate coverage detected | passed | 0 MERGE candidates |
| rewrite_candidates | Medium-value tests needing rewrite | passed | 0 REWRITE candidates |
| keep_candidates | High-value tests | passed | 9 KEEP candidates |
| regression_guard_check | Layer-2 regression guard verification | passed | All 9 files are regression guards — meta-tests for CI workflows |

## Detailed Scores

| Test File | Lines | Impact (1-5) | Probability (1-5) | Score | Decision | Notes |
|-----------|-------|-------------|-------------------|-------|----------|-------|
| test_schema_drift_guard.py | 191 | 5 | 4 | 20 | KEEP | Founding meta-test for all CI guards (#326); config + logic dimensions |
| test_anchor_links_guard.py | 398 | 5 | 3 | 15 | KEEP | Anchor lint across entire corpus; L3 line-number annotation detection |
| test_comm_patterns_schema.py | 187 | 4 | 3 | 12 | KEEP | Comm_patterns schema sentinel + ADR cross-reference |
| test_sandcastle_rls.py | 425 | 4 | 3 | 12 | KEEP | Full RLS policy gate with pure-Python reimplementation of 4-table policy matrix |
| test_memory_review_schema.py | 278 | 4 | 3 | 12 | KEEP | Deriver schema sentinel with no-op backfill guard |
| test_memory_review_guard.py | 114 | 3 | 3 | 9 | KEEP | Compact migration shape guard |
| test_powershell_encoding_guard.py | 201 | 3 | 3 | 9 | KEEP | PS encoding lint with allowlist; prevents UTF-16 BOM drift |
| test_pr_body_check_guard.py | 136 | 3 | 3 | 9 | KEEP | PR body escape hatch logic; workflow YAML anchor |
| test_sandcastle_prompt_md_guard.py | 171 | 3 | 3 | 9 | KEEP | Bang-backtick guard; sandcastle regex semantic parity test |

## Findings

| Severity | Location | Issue | Principle | Recommendation | Effort |
|----------|----------|-------|-----------|----------------|--------|
| LOW | tests/ci/test_anchor_links_guard.py:248-261 | Temp test files written to REPO_ROOT instead of tmp_path — crash before finally block leaves stale .md files in repo root | Maintainability | Use tmp_path fixture instead of REPO_ROOT for temp file creation | S |

## Summary

Overall Portfolio Value Score: **9.5/10**

- **9 KEEP** — all test files provide exceptional value; this is the highest-value test directory in the project
- **0 DELETE / 0 MERGE / 0 REWRITE** — no files recommended for deletion or consolidation
- The tests/ci/ directory implements the meta-test pattern from #326: every path-filtered CI guard ships with a co-located fixture test proving config + logic coverage
- test_schema_drift_guard.py (score 20) is the founding meta-test and highest-value file — it was the direct response to the #289/#310/#311 schema-drift failure mode
