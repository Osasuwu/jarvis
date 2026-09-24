# Competence measurement

This project does not run a programme that measures the principal's competence — no construct-C review-verdict series, no construct-A (project map) or construct-B (code reading) instruments, and no published competence band.

## Why this is out of scope

The programme was pre-registered on 2026-08-04 (`docs/design/competence-measurement-protocol.md`, #1378) and reviewed on 2026-09-24. It never produced data, so the direction was closed rather than left parked.

Reasons:

- Series 1 never started. In the 51 days after pre-registration, about 100 PRs merged and none carried a `вердикт:` comment.
- The capture mechanism assumes a draft-PR window: the reader posts a verdict before flipping draft→ready. No lane opens draft PRs any more — the AFK lane (`agent-dispatch.yml`) opens non-draft PRs queued for auto-merge, and `/implement` opens them with a plain `gh pr create`. Restoring the window would take a manual habit that never formed.
- The motivating signal — the `owner_competence_profile` memory with its documented underestimation pattern — was deleted with the Supabase memory stack (#1867) and was not migrated. `/grill` no longer reads an expertise profile at all.
- #1375 (publish the band) and #1377 (a redrobot series) were gated on a finished construct-C series, so they cannot move. #1372 and #1373 (constructs A and B) were never grilled into an instrument.

`docs/design/competence-measurement-protocol.md` is kept and marked retired, and `scripts/competence_scoring.py` stays with its test. To restart, begin a new series under that protocol: it needs a lane that opens draft PRs and a verdict habit that sticks before any scoring is worth running.

## Prior requests

- #1372 — Дизайн замера конструкта A: карта проекта по памяти и темп расхождения
- #1373 — Дизайн замера конструкта B: чтение незнакомого кода
- #1375 — Публикация полосы компетенции — гейт: ≥2 C-серии + заранее написанное правило сравнения
- #1377 — C-серия на redrobot: тот же протокол замера ревью, отдельная серия
