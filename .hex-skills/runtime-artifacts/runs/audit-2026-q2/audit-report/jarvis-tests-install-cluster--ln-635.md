# ln-635 Trustworthiness (Isolation) Assessment — Install Cluster

**Cluster:** tests/install/ (3 files)
**Worker:** ln-635 (Isolation/Psychometric)
**Date:** 2026-05-25
**Provenance:** sandcastle:agent:jarvis-watchdog-20260525-180516

---

## AUDIT-META

- **Files audited:** 3
  - `tests/install/__init__.py` — no tests
  - `tests/test_installer.py` — 545 lines
  - `tests/install/test_install_script_portable.py` — 348 lines
- **Fixture style:** TemporaryDirectory + mock.patch (test_installer.py); static file reads (test_install_script_portable.py)

---

## Checks

| Check | Finding | Severity |
|---|---|---|
| Isolation (no shared state) | All tests use fresh fixtures per call | OK |
| Deterministic ordering | No reliance on test ordering | OK |
| External dependency mocking | mock.patch used for subprocess; acceptable for unit level | MEDIUM |
| Real I/O safety | TemporaryDirectory used; no orphan file risk | OK |
| Flakiness potential | Low — static analysis and tempfile-based tests are deterministic | OK |
| Characterization vs generated | test_install_script_portable reads real PS1 files (characterization); test_installer is generative | OK |

---

## Findings

### FINDING-001: mock.patch on subprocess masks real interpreter behavior
**Severity:** MEDIUM
**File:** `tests/test_installer.py`
**Detail:** Several tests patch `subprocess.run` or similar to avoid calling real system commands. This means the tests verify that the correct commands *would* be issued, but not that they actually succeed. A real subprocess call in a containerized temp directory would be more trustworthy. Acceptable for unit tests but creates a gap vs. integration coverage.

### FINDING-002: Static portability tests are mock-free (gold standard pattern)
**Severity:** (POSITIVE)
**File:** `tests/install/test_install_script_portable.py`
**Detail:** Zero mocks used. Tests parse real PS1 files with regex and assert structural properties. This is the same pattern seen in the CI meta-test cluster and is the most trustworthy testing approach in the project.

### FINDING-003: No shared fixtures or conftest.py
**Severity:** LOW
**File:** `tests/install/`
**Detail:** No `conftest.py` in the install test directory. The temp-directory setup in `test_installer.py` is duplicated per test function. A shared fixture would reduce boilerplate and ensure consistent isolation.

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

Strong isolation overall. The portability tests are mock-free (gold standard). Minor subprocess mocking and missing conftest prevent a perfect score.
