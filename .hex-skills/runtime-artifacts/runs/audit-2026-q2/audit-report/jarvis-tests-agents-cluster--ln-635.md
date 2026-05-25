# ln-635 Trustworthiness (Isolation) Assessment — Agents Cluster

**Cluster:** tests/test_agents_*.py (10 files)
**Worker:** ln-635 (Isolation/Psychometric)
**Date:** 2026-05-25
**Provenance:** sandcastle:agent:jarvis-watchdog-20260525-180516

---

## AUDIT-META

- **Files audited:** 10 (4,311 lines)
- **Testing style:** Pure unit with hand-rolled stubs (no unittest.mock); 2 E2E files use real Supabase with hermetic cleanup
- **Notable pattern:** Every file uses hand-rolled fakes (`_StubClient`, `_FakeClient`, `_FakeQuery`, `_CapturedPopen`, `_AuditSpy`) — zero usage of `mock.patch` across all 4,311 lines

---

## Checks

| Check | Finding | Severity |
|---|---|---|
| Isolation | All unit tests are fully isolated with per-test fresh stubs | OK |
| Deterministic time | Module-level `_NOW` snapshots and mutable `clock` lists control time precisely | HIGH |
| No mock.patch convention | Hand-rolled stubs avoid mock-patch fragility; deliberate project convention | HIGH |
| E2E cleanup | Hermetic cleanup via UUID markers and `_delete_by_marker` in teardown | OK |
| Flakiness potential | Very low — pure-mathematical assertions (escalation.py) and deterministic stubs | OK |
| Hardcoded path risk | test_agents_perception_github.py uses absolute path — fails outside owner's machine | MEDIUM |

---

## Findings

### FINDING-001: Hand-rolled stubs are a strong convention but have setup overhead
**Severity:** (POSITIVE)
**All files**
**Detail:** Every file in the cluster uses hand-rolled stub classes instead of `mock.patch`. This is a deliberate project convention that produces more readable test failures (no MagicMock cascades) and forces explicit interface design. The `_FakeQuery.__getattr__` pattern in `test_agents_supabase_bridge.py` and the `_CapturedPopen` in `test_agents_dispatcher.py` are particularly elegant solutions for testing chainable APIs without mock.

### FINDING-002: Deterministic time control via mutable state
**Severity:** (POSITIVE)
**Files:** `test_agents_dispatcher.py`, `test_agents_escalation.py`, `test_agents_usage_probe.py`
**Detail:** Three different time-control patterns are used: module-level `_NOW` snapshots (dispatcher, escalation), mutable `clock` lists with `now=lambda` (usage_probe), and `datetime.fromisoformat` for parsing ISO strings (safety, escalation). All are deterministic — no `time.sleep`, no freezegun, no mocking of datetime. The `clock` list approach in usage_probe is particularly elegant for TTL testing.

### FINDING-003: E2E tests use hermetic cleanup but risk orphan data on Ctrl+C
**Severity:** LOW
**Files:** `test_agents_dispatcher_e2e.py`, `test_agents_integration.py`
**Detail:** Both E2E files generate unique UUID markers and delete rows by marker in teardown. However, if the test process is killed (SIGKILL, Ctrl+C during a slow query), the teardown never runs and orphan rows remain in the DB. A session-level marker or TTL-based cleanup would be more robust.

---

## Score

**Score = max(0, 10 - (critical×2.0 + high×1.0 + medium×0.5 + low×0.2))**

| Severity | Count | Weight |
|---|---|---|
| Critical | 0 | 0.0 |
| High | 0 | 0.0 |
| Medium | 1 | 0.5 |
| Low | 1 | 0.2 |

**Final Score: 9.3 / 10**

Exceptional isolation discipline across all 10 files. Zero mock.patch usage, hand-rolled stubs, deterministic time control. The hardcoded path in perception_github is the only meaningful concern.
