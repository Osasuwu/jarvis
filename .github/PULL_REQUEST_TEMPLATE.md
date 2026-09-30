## Summary

<!-- What changed and why, 2-3 sentences -->

## Why

<!-- Problem being solved, motivation -->

Closes #

<!--
PR scope rules:
  - Code change       → keep "Closes #NNN" above.
  - Hotfix            → remove the line and apply the priority:critical label.
  - Design / RFC      → wrong place. Use GitHub Discussions, not a PR.
-->


## Decisions & Alternatives

<!-- Key choices made during implementation. What alternatives were considered and why they were rejected. Non-obvious decisions that a reviewer would question. -->

-

## Risk Assessment

<!-- Classify ALL changes by risk level -->

- **LOW**: <!-- cosmetic, imports, naming -->
- **MEDIUM**: <!-- refactors, new helpers -->
- **HIGH**: <!-- logic changes, safety-adjacent -->
- **CRITICAL**: <!-- data loss, security, breaking API -->

## Testing

<!--
What holds this section: docs/reference/test-quality.md. A pass count is not evidence.
  - Each acceptance criterion: the test that goes red for it, a command's output, or
    (one-off static facts only) reading.
  - Every test added or changed appears in a line, one line per distinct mutation:
    <production file>:<line> <mutation> → <tests it turns red> red
    (or "no probe — …" / "not probed — …" where test-quality.md allows it)
  - Every test deleted: the kept test and the mutation that reddens it, or why the
    deleted one could not fail, or its "Never write" class.
  - Tests touched: keep the "CI run" line below until the PR run's passed and skipped
    counts have been read against main's, then replace it with the two pairs of numbers.
  - No test touched: say so and delete the "CI run" line.
-->

-
- CI run not checked for skips

- [ ] Manual verification (if needed)

## Files Changed

<!-- For each file: why it was modified, what changed -->

| File | Change |
|------|--------|
| | |

## Scope Check

- [ ] One issue → one PR
- [ ] No out-of-scope changes
