# Bulk "epic" terminology sweep

This project does not chase the `epic` term across the codebase as a coordinated cleanup.

## Why this is out of scope

The decision to retire `epic` as a cadence-grouping primitive (in favor of `milestone` per `milestone_hierarchy_v3`, decision UUID `2a7ae10e-afc3-4523-b0bc-c4b90ddbe1a5`) was a *forward* policy: new work uses `milestone`. It was not retroactive — historical issue titles, commit messages, design-doc references to prior epics, and skill-installer manifest comments (`Epic #335 / M1 #336`) are correct as historical record and should not be rewritten.

The 2026-05-16 AFK-chain audit (issue #668) classified 30 hits / 15 files into four tiers:

- **Tier 1 — active runtime** (would shape future behavior): 1 site — `scripts/pretooluse-recall-hook.py:205` recall keyword. Fix inline; no ticket needed.
- **Tier 2 — generic-cadence drift** (could mislead readers): 1 site — `src/risk_radar.py:12` comment "address this sprint". Fix inline as a doc nit.
- **Tier 3 — historical-defensible**: ~25 sites quoting prior `Epic #N` titles or referencing closed epics. Correct as-is.
- **Tier 4 — fixed identifiers**: `/sprint-report` skill name — out of scope to rename.

The umbrella ticket bundling these as one sweep is paperwork: Tier 3+4 should not be touched, Tier 1+2 are two inline edits that don't need coordination. Per CLAUDE.md "Fix > track for trivial reversible" — handle inline next time the surrounding code is touched.

## Prior requests

- #668 — "docs+process: forbidden-terminology 'epic' drift — 30 hits / 15 files"
