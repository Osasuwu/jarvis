# ln-633 Portfolio Value Assessment — Install Cluster

**Cluster:** tests/install/ (3 files)
**Worker:** ln-633 (Portfolio Value)
**Date:** 2026-05-25
**Provenance:** sandcastle:agent:jarvis-watchdog-20260525-180516

---

## AUDIT-META

- **Files audited:** 3 (895 lines total)
  - `tests/install/__init__.py` — 2 lines (package marker)
  - `tests/test_installer.py` — 545 lines (installer unit tests)
  - `tests/install/test_install_script_portable.py` — 348 lines (PS1 portability tests)
- **Scope:** Installer bootstrap + cross-device script portability
- **Business criticality:** HIGH — installer is the entry point for all new device setups. If broken, the project cannot scale to new machines.

---

## Checks

| Check | Finding | Severity |
|---|---|---|
| Business value alignment | Tests cover the critical bootstrap path | OK |
| Coverage adequacy | Broad edge-case coverage (unicode, empty groups, missing git, missing manifest, JSONC caveat) | OK |
| Regression sensitivity | Portability tests catch hardcoded paths that would silently break on other devices | HIGH |
| Cost-to-value ratio | 895 lines of test for ~500 lines of install infra — good ratio | OK |
| Documentation debt | No test-level docstrings explaining *why* specific portability checks exist | LOW |

---

## Findings

### FINDING-001: No test for end-to-end install dry-run
**Severity:** MEDIUM
**File:** `tests/test_installer.py`
**Detail:** All tests exercise individual functions (`_include_for`, `_set_env`, `rollback`, etc.) in isolation. There is no end-to-end test that simulates a full install sequence (manifest → env setup → service registration) in a temp directory. The rollback test is the closest but only validates cleanup of a single operation.

### FINDING-002: Portability tests depend on current PS1 file content
**Severity:** LOW
**File:** `tests/install/test_install_script_portable.py`
**Detail:** Tests read live PS1 files from the repo. If install scripts are significantly refactored, regex patterns may silently match different constructs. The tests verify structural patterns (e.g., "uses Join-Path correctly") but not semantic correctness.

### FINDING-003: __init__.py is pure ceremony
**Severity:** LOW
**File:** `tests/install/__init__.py`
**Detail:** Single docstring, no test utilities, no fixtures. Valid as a package marker but represents an opportunity to share install-test utilities (e.g., temp-directory setup, PS1 path resolution).

---

## Score

**Score = max(0, 10 - (critical×2.0 + high×1.0 + medium×0.5 + low×0.2))**

| Severity | Count | Weight |
|---|---|---|
| Critical | 0 | 0.0 |
| High | 0 | 0.0 |
| Medium | 1 | 0.5 |
| Low | 2 | 0.4 |

**Final Score: 9.1 / 10**

High business-criticality coverage with reasonable cost-to-value. Missing end-to-end dry-run test is the main gap.
