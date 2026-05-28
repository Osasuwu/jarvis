# ln-638 Oracle Effectiveness Assessment — Sandcastle Cluster

**Cluster:** tests/sandcastle/ (1 PS1 file)
**Worker:** ln-638 (Oracle Effectiveness)
**Date:** 2026-05-25
**Provenance:** sandcastle:agent:jarvis-watchdog-20260525-180516

---

## AUDIT-META

- **Files audited:** 1
  - `tests/sandcastle/Run-Sandcastle.Tests.ps1` — 1116 lines
- **Total assertions:** ~140-160 (estimated across 66 tests)
- **Assertion density:** ~0.13 assertions/line
- **Assertion style:** `Should Be`, `Should BeNullOrEmpty`, `Should Be $true/$false`, `Should Match`, `Assert-MockCalled`

---

## Checks

| Check | Finding | Severity |
|---|---|---|
| Assertion presence | Every test has at least one assertion | OK |
| Assertion specificity | String equality, boolean, and regex match — appropriate granularity | OK |
| Mock invocation verification | Assert-MockCalled with exact parameter filters — best practice | HIGH |
| Edge case oracles | OOM detection, window roll-forward, message truncation, regex escaping | HIGH |
| Exception testing | `Should Throw` used for failure paths | OK |
| Test intent clarity | Descriptive test names document AC numbers and expected behavior | OK |

---

## Findings

### FINDING-001: Assert-MockCalled with script-scoped accumulators creates redundant oracles
**Severity:** LOW
**File:** Lines 314-316, 341-346, 375-379, 523-527
**Detail:** Several tests verify mock invocation via BOTH `Assert-MockCalled` AND a script-scoped accumulator (`$script:calls`). For example, the tier escalation matrix checks `Assert-MockCalled Invoke-Sandcastle -Times 2` AND `$script:calls[0]` AND `$script:calls[1]`. The accumulator check is redundant when `Assert-MockCalled -Times N` already verifies invocation count and `-ParameterFilter` verifies parameters.

### FINDING-002: Complex mock setup in BeforeEach creates oracle distance
**Severity:** MEDIUM
**File:** Lines 273-295, 483-504, 651-688
**Detail:** The BeforeEach blocks for the tier escalation matrix and daemon-state matrix set up 10-15 mocks each. A test failure could stem from the mock setup itself rather than the code under test. The distance between mock declaration (BeforeEach) and assertion (It) makes debugging harder. A helper function that returns a standard mock environment would reduce this distance.

### FINDING-003: Message truncation oracle is well-constructed
**Severity:** (POSITIVE)
**File:** Lines 153-165
**Detail:** The Send-TelegramAlert message truncation test is a model oracle: it constructs a 250-char message, asserts the result is exactly 200 chars, and verifies it ends with `...`. Simple, specific, and directly tied to the acceptance criterion.

### FINDING-004: Outcome record HTTP path tests verify exact shape
**Severity:** (POSITIVE)
**File:** Lines 1066-1115
**Detail:** The Write-OutcomeRecord HTTP path tests capture the full Invoke-RestMethod call (URI, method, headers, body) and assert every field. This is the most thorough HTTP call test in the project — it would catch any schema drift in the task_outcomes API.

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

Strong oracles with excellent assertion specificity. Complex BeforeEach mock setup creates oracle distance but test intent remains clear.
