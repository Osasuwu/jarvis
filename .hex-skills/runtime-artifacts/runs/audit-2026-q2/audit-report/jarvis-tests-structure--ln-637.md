# Test Structure Audit Report

<!-- AUDIT-META
worker: ln-637
category: Test Maintainability
domain: structure
scan_path: tests/
score: 8.0
total_issues: 5
critical: 0
high: 0
medium: 3
low: 2
status: completed
-->

## Checks

| ID | Check | Status | Details |
|----|-------|--------|---------|
| layout_pattern | Layout pattern detection | warning | Centralized-flat dominant with emerging subdirectories — hybrid without documented type-based rule |
| test_source_mapping | Test-to-source mapping | warning | No orphaned tests, but path mismatches due to hyphen/underscore naming convention differences |
| flat_dir_growth | Flat directory growth | failed | 51 files in root tests/ directory — well above the 20-file threshold |
| domain_grouping | Domain grouping alignment | warning | Source domains (agents, mcp-memory, scripts) lack corresponding test subdirectories |
| colocation_consistency | Co-location consistency | passed | Fully centralized — no inconsistency (all tests in tests/ directory) |
| fragmented_duplicates | Fragmented duplicate tests | warning | Minor overlap between agent test files; no severe duplication |

## Findings

| Severity | Location | Issue | Principle | Recommendation | Action | Effort |
|----------|----------|-------|-----------|----------------|--------|--------|
| MEDIUM | tests/ (root) | 51 test files in flat root directory — exceeds 20-file threshold for recommended restructuring | Structure: Flat directory | Group tests into subdirectories by domain prefix: e.g., `tests/agents/` (10 test_agents_* files), `tests/memory/` (~12 memory/recall/classifier/episode files), `tests/comm_patterns/` (4 files), `tests/decisions/` (8 record_decision/events/fok/trace files), `tests/security/` (2 test_secret_* files) | MOVE | M |
| MEDIUM | tests/ → source domains | No test subdirectories for major source domains: `agents/` (10 test files, 10+ source files), `mcp-memory/` (~12 test files, 8 source modules) | Structure: Domain grouping | Create `tests/agents/` and `tests/memory/` subdirectories and migrate matching test files; aligns test structure with source module organization | MOVE | M |
| MEDIUM | tests/ (root) | Layout is centralized-flat with 51 root files + 20 organized in subdirectories (ci/, skills/, install/, evals/) — hybrid pattern without documented type-based rule for what goes in a subdirectory vs root | Structure: Layout | Document the criteria for subdirectory placement (e.g., "CI guard tests go in tests/ci/, skill integration tests go in tests/skills/, everything else stays flat until a domain reaches 5+ files") | MOVE | S |
| LOW | tests/*.py naming | Test filenames use underscores (test_backfill_outcome_memories.py) while source filenames use hyphens (backfill-outcome-memories.py) — 9 files affected | Structure: Path mapping | Consider adopting a consistent naming convention, or add a comment mapping each test to its canonical source path | MOVE | S |
| LOW | tests/test_agents_*.py (10 files) | Fragmented agent test files across dispatcher, dispatcher_e2e, escalation, integration, perception_github, safety, scheduler, smoke, supabase_bridge, usage_probe — some overlap between dispatcher + dispatcher_e2e (both test dispatch flow, one is opt-in E2E) | Structure: Fragmentation | Consider consolidating shared mock/fixture code into `tests/conftest.py` or a `tests/agents/conftest.py`; the E2E/integration/smoke distinction is clear but boilerplate setup is duplicated | MERGE | S |

## Layout Pattern Analysis

The project uses a **centralized-flat layout with emerging subdirectories** (hybrid):

| Location | File Count | Pattern |
|----------|-----------|---------|
| tests/ (root) | 51 | Centralized-flat |
| tests/ci/ | 10 | Grouped (CI guard tests) |
| tests/skills/ | 4 | Grouped (skill integration tests) |
| tests/install/ | 3 | Grouped (installer tests) |
| tests/evals/ | 3 | Grouped (evaluation tests) |
| **Total** | **71** | |

- ~72% of files are in the flat root, ~28% are in subdirectories
- No documented rule for what goes in a subdirectory vs root — currently seems to follow "whole-subdomain coverage" (ci/, skills/, install/, evals/ are all self-contained testing subdomains)
- Root `tests/` mixes unit tests, integration tests, and schema sentinels from multiple source domains

## Flat Directory Growth — Suggested Grouping

The 51 root test files naturally cluster into domain groups by filename prefix:

```
tests/agents/              ← 10 files: test_agents_*.py
tests/memory/              ← ~12 files: test_memory_*.py, test_recall_*.py, 
                             test_classifier.py, test_episode_extractor.py,
                             test_evolve_neighbors.py, test_consolidation_review.py,
                             test_pre_compact_backup.py, test_migrate_memory_structure.py
tests/comm_patterns/       ← 4 files: test_comm_patterns_*.py
tests/decisions/           ← 8 files: test_record_decision*.py, test_events_canonical*.py,
                             test_fok_*.py, test_trace_context.py
tests/security/            ← 2 files: test_secret_*.py
tests/infrastructure/      ← 6 files: test_principal.py, test_protected_files.py,
                             test_installer.py, test_morning_check.py,
                             test_risk_radar.py, test_rework_policy.py
tests/misc/                ← remaining standalone files
```

## Scoring

| Penalty Source | Count | Weight | Penalty |
|---------------|-------|--------|---------|
| CRITICAL | 0 | 2.0 | 0 |
| HIGH | 0 | 1.0 | 0 |
| MEDIUM | 3 | 0.5 | 1.5 |
| LOW | 2 | 0.2 | 0.4 |
| **Total penalty** | | | **1.9** |
| **Score** | | | **8.0/10** |

## Summary

Overall Structure Score: **8.0/10**

- **5 findings** — 3 MEDIUM, 2 LOW
- **Primary concern**: 51 files in flat root `tests/` directory — the suite has outgrown the flat layout
- **Positive**: No true orphaned tests, strong co-location consistency (fully centralized), no severe fragmented duplication
- **Pilot prediction confirmed**: Flat-directory threshold (>20 files) flagged as expected by the issue description
- **Quick win**: Document subdirectory placement criteria (S effort); the ci/, skills/, install/, evals/ subdirectories are a good start but need documented rules
- **Medium-term**: Domain-based regrouping into `tests/agents/`, `tests/memory/`, `tests/decisions/`, etc. would improve navigability
