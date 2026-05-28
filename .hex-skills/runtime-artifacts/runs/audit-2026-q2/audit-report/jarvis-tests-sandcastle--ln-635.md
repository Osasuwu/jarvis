# ln-635 Trustworthiness (Isolation) Assessment — Sandcastle Cluster

**Cluster:** tests/sandcastle/ (1 PS1 file)
**Worker:** ln-635 (Isolation/Psychometric)
**Date:** 2026-05-25
**Provenance:** sandcastle:agent:jarvis-watchdog-20260525-180516

---

## AUDIT-META

- **Files audited:** 1
  - `tests/sandcastle/Run-Sandcastle.Tests.ps1` — 1116 lines
- **Testing style:** Pester 3.4-compatible with heavy mocking (Mock, Assert-MockCalled)
- **Isolation strategy:** Temp directories via GUID, env var save/restore, function-level mocks

---

## Checks

| Check | Finding | Severity |
|---|---|---|
| Test isolation | Each test uses fresh temp dirs (GUID-based) and local mocks | OK |
| Side-effect containment | Env var save/restore before/after Invoke-Sandcastle calls | OK |
| Mock scoping | All Assert-MockCalled uses `-Scope It` — tightest possible scope | HIGH |
| Deterministic | No shared state, no test ordering dependencies | OK |
| Real I/O exposure | Minimal — only temp file writes for log/result simulation | OK |
| Pester version constraints | Stuck on Pester 3.4 syntax (no Should -BeExactly, no Should -HaveCount) | LOW |

---

## Findings

### FINDING-001: Script-scoped variables in BeforeEach create theoretical bleed risk
**Severity:** LOW
**File:** `tests/sandcastle/Run-Sandcastle.Tests.ps1`, lines 298, 319, 349, 475-503
**Detail:** Several test blocks use `$script:calls` and `$script:n` as accumulator variables in BeforeEach. While each Describe has its own BeforeEach that reinitializes these, a test failure mid-block could leave stale values for the next test. The use of `-Scope It` in assertions mitigates this but doesn't eliminate it.

### FINDING-002: Temp directory cleanup is reliable but verbose
**Severity:** LOW
**Detail:** All temp directory tests use the pattern `$script:tmpRoot = Join-Path $env:TEMP "sandcastle-*-$([guid]::NewGuid())"` followed by BeforeEach/AfterEach cleanup. This is correct but verbose — a shared test fixture or Pester 5.x `-Tag` cleanup would reduce boilerplate.

### FINDING-003: Mock-heavy tests are fast but fragile to production API changes
**Severity:** MEDIUM
**Detail:** Every external dependency is mocked (Docker, Ollama, npm, Supabase, Telegram, GitHub CLI). While this makes tests fast and deterministic, it means a change in any external API signature (e.g., Docker's `docker info --format` output format) would not be caught by tests. The Invoke-Sandcastle env-save/restore tests (lines 933-954) are the closest to integration-level verification.

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

Strong isolation with excellent mock hygiene (tight scoping, env save/restore). Script-scoped variables and mock fragility are minor concerns.
