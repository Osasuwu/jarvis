---
paths:
  - ".github/workflows/**"
  - "tests/ci/**"
  - "tests/install/**"
  - "scripts/**"
---

### Path-filtered CI guards require a meta-test (#326)

Enforced mechanically by [`tests/ci/test_guard_test_convention.py`](../../tests/ci/test_guard_test_convention.py) — it fails the PR, so you don't need this rule in your head. It cannot check the **logic** half (the decision rule blocks/allows what it claims); that's on you. Naming, scope and the #289/#310/#311 precedent: [`docs/reference/ci-guard-meta-tests.md`](../../docs/reference/ci-guard-meta-tests.md).
