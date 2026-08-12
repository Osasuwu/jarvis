---
paths:
  - "**/*.py"
  - "**/*.ts"
  - "**/*.js"
  - "scripts/**"
  - "src/**"
---

**Sibling-grep on fixes.** When a reviewer flags a bug in one helper/pattern, grep for sibling patterns across the whole file AND related files before declaring the fix done. A second-round review with the same class of finding = the first fix was partial. 30 seconds of grep beats a full CI cycle of rework.
