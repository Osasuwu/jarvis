---
paths:
  - "**/*.md"
  - "docs/**"
---

**No state in static storage.** State (% done, ✅/❌ markers, "shipped in PR #X", sprint dates, "last audit YYYY-MM-DD") belongs in GitHub Issues/Projects/PRs/commit history — NOT in markdown files, NOT in memory. Static storage may hold: evergreen lessons, decisions+rationale, reference info (API shapes, config locations), target architecture, pointers ("see #633 for current status"). If a field would be wrong in 2 weeks → GH, not here.
