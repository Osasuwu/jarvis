# Decision-confidence calibration

This project does not compute an automated calibration of the `confidence` field on recorded decisions: no Brier score, no stored outcome table, no scheduled job. Calibration is read off by hand-review.

## How it works now

Decisions live in the plain `decisions.md` journal in each project's memory directory (user-level `CLAUDE.md` § Memory). Each entry states `predicts: <observable result> by <date>` and a `confidence`, written before the outcome exists. A later entry that revisits it records `held` or `reversed`.

`/decision-retro` judges due entries on two separate verdicts: process (blind, from the transcript cut at the lock) and outcome. Each run writes a `review of <date> "<first clause>"` line back into the journal. Its report includes a calibration table: held rate per stated-confidence bucket (<0.6, 0.6–0.8, >0.8), each with its N, with a note that a bucket below N=10 is a trend, not a calibration.

The skill is still invoked by hand, and hand-invoked evaluation has died in this repo before (see `competence-measurement.md`). So a SessionStart hook in the `jarvis` plugin (`hooks/decision-overdue.py` in `Osasuwu/jarvis-private`, #2130) lists, at the start of a new or cleared session, each prediction whose by-date has passed with no `revisits` line and no `review of` line. The overdue backlog is visible without anyone remembering to look. It lists at most five entries and a count, and prints nothing when none is due.

## Still out of scope

An automated calibration pipeline: a computed Brier score, an outcome database, or a scheduled scorer. `record_decision`, `task_outcomes` and the calibration views went with the Supabase stack (#1867). Reviewed on 2026-09-24 and again when #2130 landed; the hook makes the manual review visible but does not make it automatic, and nothing scores a decision without someone running `/decision-retro`.

Revisit this once enough revisited decisions exist for a score to mean something (the retro's own N=10 floor per bucket); that would be a one-off script over the journal.

## Prior requests

- #1316 — Калибровка confidence решений: сверять record_decision.confidence с фактическим исходом
