# Decision-confidence calibration pipeline

This project does not compute a Brier score, or any other automated calibration, for the `confidence` field on recorded decisions.

## Why this is out of scope

The request (#1316) was reasonable. `/grill`'s research-pass gate fires on `confidence < 0.7`, and a verbalised confidence from a model is exactly the kind of self-report that runs high. The gate still exists. What the request was built on does not: `record_decision`, `task_outcomes` and the calibration views were deleted with the Supabase stack (#1867). Decisions now live in a plain `decisions.md` journal that has no outcome field.

The request was reviewed on 2026-09-24. Rebuilding calibration as a periodic manual review was rejected. Evaluation mechanisms that someone has to invoke by hand have died in this repo repeatedly; see `competence-measurement.md`. Instead, the decision-journal format in the user-level `CLAUDE.md` now asks for an outcome whenever a later entry revisits an earlier decision: `held` or `reversed`. The data for calibration then builds up as a side effect of normal journaling, and a Brier check becomes a one-off script once enough revisited decisions exist.

## Prior requests

- #1316 — Калибровка confidence решений: сверять record_decision.confidence с фактическим исходом
