# ln-633 Portfolio Value Assessment — Sandcastle Cluster

**Cluster:** tests/sandcastle/ (1 PS1 file)
**Worker:** ln-633 (Portfolio Value)
**Date:** 2026-05-25
**Provenance:** sandcastle:agent:jarvis-watchdog-20260525-180516

---

## AUDIT-META

- **Files audited:** 1
  - `tests/sandcastle/Run-Sandcastle.Tests.ps1` — 1116 lines (Pester tests)
- **Supporting context:**
  - `scripts/sandcastle/Run-Sandcastle.ps1` — 837 lines (production watchdog)
  - `scripts/sandcastle/Register-SandcastleTask.ps1` — 257 lines (scheduled task registration)
- **Business criticality:** HIGH — sandcastle is the AFK autonomous agent loop. If broken, unattended issue processing stops.

---

## Checks

| Check | Finding | Severity |
|---|---|---|
| Business value alignment | Tests cover the entire daemon lifecycle (health, iteration, escalation, recording) | HIGH |
| Coverage breadth | 16 Describe blocks covering 66 individual tests | OK |
| Edge case coverage | OOM detection, tier escalation matrix, daemon-state matrix, window expiry, env save/restore | HIGH |
| Cost-to-value ratio | 1116 lines test for 837 lines production = excellent ratio (1.33x) | OK |
| Missing coverage | No tests for Register-SandcastleTask.ps1; no integration tests with real Docker/Ollama | MEDIUM |

---

## Findings

### FINDING-001: Register-SandcastleTask.ps1 has zero test coverage
**Severity:** MEDIUM
**File:** `tests/sandcastle/Run-Sandcastle.Tests.ps1`
**Detail:** The task registration script (`Register-SandcastleTask.ps1`) has no corresponding test file. This script configures Windows Task Scheduler entries for production AFK runs. Issues like device-guard logic, argument assembly, or per-repo default drift would go undetected until a scheduled task fails to fire.

### FINDING-002: No integration-level tests against real daemons
**Severity:** MEDIUM
**Detail:** All 66 tests use mocked health probes (Test-DockerRunning, Test-OllamaRunning). There is no integration test that verifies the watchdog against a real Docker or Ollama instance. A regression in how the watchdog interacts with actual daemon APIs would pass CI and only surface at runtime.

### FINDING-003: Invoke-Watchdog daemon-state matrix is the project's best example of state-based testing
**Severity:** (POSITIVE)
**Detail:** The 11-test daemon-state matrix (lines 650-900) covers every combination of Docker/Ollama up/down, window expiry, iteration counts, and failure modes. This is the most thorough state-based test pattern in the entire project.

---

## Score

**Score = max(0, 10 - (critical×2.0 + high×1.0 + medium×0.5 + low×0.2))**

| Severity | Count | Weight |
|---|---|---|
| Critical | 0 | 0.0 |
| High | 0 | 0.0 |
| Medium | 2 | 1.0 |
| Low | 0 | 0.0 |

**Final Score: 9.0 / 10**

Outstanding test coverage for the watchdog itself. Missing coverage of Register-SandcastleTask.ps1 and lack of integration tests are the main gaps.
