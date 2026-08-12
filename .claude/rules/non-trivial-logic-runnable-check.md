---
paths:
  - "**/*.py"
  - "**/*.ts"
  - "**/*.js"
  - "scripts/**"
  - "src/**"
  - "tests/**"
---

**Non-trivial logic leaves one runnable check.** Any change with real logic in it ships with at least one thing that fails if the logic breaks — the smallest such thing, not a suite: one test in the existing file, or an assert-based self-check. Trivial one-liners, renames and doc edits need nothing. This is the floor under drive-by fixes where full TDD is overkill; it does **not** relax the TDD requirement inside `/implement` and `/rework`, which stays as-is. A fix you can't leave a check behind for is itself a finding — flag it.
