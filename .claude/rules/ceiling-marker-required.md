---
paths:
  - "**/*.py"
  - "**/*.ts"
  - "**/*.js"
  - "scripts/**"
  - "src/**"
---

**Deliberate simplifications carry a `ceiling:` marker.** When you knowingly ship a shortcut with a known limit — global lock, O(n²) scan over a list assumed small, naive heuristic, hardcoded single-device path — leave an inline `ceiling:` comment naming *both* the limit and the upgrade path (`# ceiling: O(n²) over labels, fine <200; switch to a set-diff if a repo crosses that`). Not for ordinary "could be prettier" code — only for a corner cut against a limit you can name. This is the cheap end of «tech debt must be visible»: `grep -rn 'ceiling:'` is the debt list, so a shortcut no longer needs an issue to stay visible. Unnamed limit ⇒ you don't understand the shortcut well enough to ship it.
