# ln-633 Portfolio Value Assessment — Agents Cluster

**Cluster:** tests/test_agents_*.py (10 files)
**Worker:** ln-633 (Portfolio Value)
**Date:** 2026-05-25
**Provenance:** sandcastle:agent:jarvis-watchdog-20260525-180516

---

## AUDIT-META

- **Files audited:** 10 (3,877 lines total)
  - `test_agents_escalation.py` — 499 lines (33 tests)
  - `test_agents_executor.py` — 298 lines (17 tests)
  - `test_agents_integration.py` — 211 lines (3 tests)
  - `test_agents_perception_github.py` — 514 lines (24 tests)
  - `test_agents_safety.py` — 415 lines (28 tests)
  - `test_agents_scheduler.py` — 433 lines (19 tests)
  - `test_agents_smoke.py` — 371 lines (13 tests)
  - `test_agents_supabase_bridge.py` — 363 lines (15 tests)
  - `test_agents_task_queue.py` — 414 lines (25 tests)
  - `test_agents_usage_probe.py` — 359 lines (22 tests)
- **Business criticality:** HIGH — agents subsystem handles GitHub issue triage, safety gating, scheduling, and dispatch of autonomous work

---

## Checks

| Check | Finding | Severity |
|---|---|---|
| Business value alignment | Covers every agent subsystem: safety, dispatch, escalation, scheduling, perception, bridge, usage, integration | HIGH |
| Coverage breadth | 199 total test functions across 10 files — largest cluster | HIGH |
| Test-level depth | escalation.py (33 tests for ~500 lines) has best ratio; integration tests are sparse | OK |
| E2E coverage | 1 E2E file (3 tests) opt-in, rest are unit with stubs | MEDIUM |
| Edge case coverage | escalation.py is the most thorough boundary testing in the project | HIGH |

---

## Findings

### FINDING-001: E2E tests are opt-in and require real credentials
**Severity:** MEDIUM
**Files:** `test_agents_integration.py`
**Detail:** The 3 E2E tests require `AGENTS_E2E=1`, a real Supabase instance, and a real Ollama server. They are skipped by default in CI. This means the bridge between stubs and reality is only verified when a developer explicitly runs them. Critical paths like the full dispatch pipeline (task queue → safety gate → subprocess → audit log) are never exercised in CI.

### FINDING-003: test_agents_perception_github.py has a hardcoded absolute path
**Severity:** MEDIUM
**File:** `test_agents_perception_github.py`
**Detail:** The test file uses `sys.path.insert(0, "/d/Github/jarvis")` to import the production module. This is an absolute Windows development path that would fail on any other machine (CI, Linux, other developers). The test passes on the owner's Workshop PC but would silently skip or fail elsewhere.

### FINDING-002: No cross-subsystem integration test
**Severity:** LOW
**Detail:** Each agent subsystem (safety, scheduling, dispatch, escalation, perception) is tested in isolation. There is no test that exercises the full chain: perception polls GitHub → safety gates classification → dispatch routes → escalation monitors — all connected. The LangGraph state machine in `test_agents_integration.py` comes closest but only covers the event monitor subgraph.

---

## Score

**Score = max(0, 10 - (critical×2.0 + high×1.0 + medium×0.5 + low×0.2))**

| Severity | Count | Weight |
|---|---|---|
| Critical | 0 | 0.0 |
| High | 0 | 0.0 |
| Medium | 2 | 1.0 |
| Low | 1 | 0.2 |

**Final Score: 8.8 / 10**

Largest and most thorough test cluster in the project. E2E gaps and the hardcoded path in perception_github are the main issues. escalation.py and supabase_bridge.py are standout files.
