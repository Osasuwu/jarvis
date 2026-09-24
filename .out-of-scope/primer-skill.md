# Primer skill

This project does not ship a `/primer` skill. `/primer` would have prepared paste-ready NotebookLM sources to fill in the background knowledge a `docs/research/` doc assumes, and it would have kept a per-domain exposure ledger of what the reader had been shown.

## Why this is out of scope

The skill was designed in July 2026 (decisions `70b36a50`, `d2aa6aa5`) and marked `status:ready`, but nobody built it. It was reviewed on 2026-09-24 and closed.

Reasons:

- Two of its dependencies were deleted in the rebuild: the Supabase memory that held `exposure_ledger_<domain>`, and the status-MCP pending-primer detector (#1867). What is left is a manual paste-and-generate flow.
- The design depended on the reader's research-reading habit, and that habit did not create enough demand for the skill in two months to get it built.

If the need comes back, the design in #1338 still applies: the doc is used as the syllabus, sources are filtered on "teaches vs assumes", and firecrawl is used for the search, with no MCP. The ledger would become a file under native memory instead of a Supabase row.

## Prior requests

- #1338 — skill: /primer — paste-ready источники для NotebookLM-праймера по research-доку + exposure ledger
