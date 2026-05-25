# ln-638 Oracle Effectiveness Assessment — Agents Cluster

**Cluster:** tests/test_agents_*.py (10 files)
**Worker:** ln-638 (Oracle Effectiveness)
**Date:** 2026-05-25
**Provenance:** sandcastle:agent:jarvis-watchdog-20260525-180516

---

## AUDIT-META

- **Files audited:** 10 (4,311 lines)
- **Total assertions:** ~400-500 (estimated across 189 tests)
- **Assertion density:** ~0.10 assertions/line
- **Dominant oracle style:** Enum equality (`== Tier.AUTO`/`== Tier.BLOCKED`), containment, `pytest.raises` with match, shape assertions on recorded call chains

---

## Checks

| Check | Finding | Severity |
|---|---|---|
| Assertion specificity | Tier enums (safety), Trigger enums (escalation), call-chain shapes — excellent specificity | HIGH |
| Boundary coverage | escalation.py tests every trigger at/above/below/missing — gold standard | HIGH |
| Error-path coverage | pytest.raises with match strings throughout all files | OK |
| Call-chain verification | Files record and assert on stub call chains — verifies exact DB operation shape | HIGH |
| Idempotency verification | SHA-256 key format, label-order-independence, issue-number distinctness | HIGH |
| Dry-run contract | Verified across dispatcher, safety, and scheduler files | OK |

---

## Findings

### FINDING-001: escalation.py is the best oracle design in the project
**Severity:** (POSITIVE)
**File:** `test_agents_escalation.py`
**Detail:** The 33 test functions cover every escalation trigger with boundary-value analysis: fresh approval, exact threshold, past threshold, missing fields, bad timestamps, Z-suffix ISO, configurable params, callable hasher, hasher-exception fallback, same-id self-defense, goal-interruption pattern. This is the most thorough oracle design in any cluster — every input dimension is tested at its decision boundaries.

### FINDING-002: Call-chain assertions are precise but verbose
**Severity:** LOW
**Files:** `test_agents_dispatcher.py`, `test_agents_supabase_bridge.py`
**Detail:** Tests that verify DB operation shape use `client.calls` lists and helper functions like `_names(chain)` and `_find(chain, name)`. While these assertions are precise (they verify exact method names and arguments), they are verbose — a single assertion requires 2-3 lines of setup. A dedicated assertion helper (e.g., `assert_chain_contains(chain, "eq", "project", "jarvis")`) would reduce boilerplate.

### FINDING-003: 189 tests run in CI without external dependencies
**Severity:** (POSITIVE)
**All files**
**Detail:** All 189 tests are structured so that the 184 unit+smoke tests run in CI without any external credentials. Only the 5 E2E tests are opt-in. This means the cluster provides high confidence in CI with zero false negatives from credential availability.

### FINDING-004: Docstrings explain every test's "why"
**Severity:** (POSITIVE)
**All files**
**Detail:** Across all 10 files, virtually every test function has a docstring explaining why the test exists, what regression it guards, or what edge case it covers. This is the strongest documentation discipline of any cluster in the project.

---

## Score

**Score = max(0, 10 - (critical×2.0 + high×1.0 + medium×0.5 + low×0.2))**

| Severity | Count | Weight |
|---|---|---|
| Critical | 0 | 0.0 |
| High | 0 | 0.0 |
| Medium | 0 | 0.0 |
| Low | 1 | 0.2 |

**Final Score: 9.8 / 10**

The strongest oracle design in the entire project. escalation.py's boundary-value analysis is the gold standard. Call-chain assertion verbosity is the only minor nit.
