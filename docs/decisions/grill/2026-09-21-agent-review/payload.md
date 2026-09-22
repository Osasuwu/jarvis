# Proposal under review

Repos on this machine (read access is expected):

- `jarvis-oss` — public GitHub repo `Osasuwu/jarvis-oss`. Practice docs for
  people who work with coding agents: `docs/` (decision guides with options, "Fits only if" lines,
  a "How to choose" section, an "Our own choice" section), `examples/` (traces), `resources/`,
  `.agents/skills/` (`write-doc`, `review-doc`), `scripts/`, `tests/`, `.github/workflows/`.
- `jarvis/docs/decisions/2026-Q3.md` — the decision record this proposal
  amends (entries D15, D20, D26).
- `gh` CLI is authenticated; use `gh -R Osasuwu/jarvis-oss ...` for PRs, branch protection, secrets
  metadata. Never print secret values.

## Problem statement

Docs in jarvis-oss are written by an agent. Until now every doc needed a per-document human
sign-off (`signed_off` frontmatter + a ledger line in `docs/SIGNOFF.md`, enforced by
`tests/structure_gate.py`), and every PR was held by a `waiting-human-review` required check until
the human removed a label.

Two observations from the last PRs (#75, #81):

1. Every doc PR needed several review/fix rounds, and later rounds found defects both in text the
   fixes added and in text that had been reviewed earlier and not changed.
2. The human is a solo developer, not a domain expert on most doc topics. Their statement: the
   signature certifies nothing about factual correctness, because everything they know the agent
   also knows, and everything they tried is recorded. Their per-document reading does not catch
   the defect classes that matter (wrong plan-tier facts, misquoted sources, options that do not
   fit the reader).

## Proposed direction

Statements by the human, verbatim (Russian):

- "Я не эксперт и мой sign off ничего больше не подтверждает"
- "Мой sign-off сужается до … 0. Всё, что знаю я, знает и агент, всё, что я делал записано."
- "Мы собираем разбросанную по всему интернету информацию в одно место. У нас нет задачи покрыть
  всё. Документация даёт абстракцию, теорию, формулы. Примеры дают визуализацию теории на одном
  примере, потом каждый реализует теорию под себя."
- "'Для какого читателя документ гарантирует ответ' - ни для какого. Для выбранных типов читателей
  мы гарантируем предоставить информацию для обучения, мощную стартовую точку."
- On the README: "готов поставить в README [that no human read the docs], но вместе с этим нужно
  указать, что информация всё же проверенная … описал бы идею, и сказал, что придумал её человек,
  проверил, что автоматизация работает хорошо на тестовых заданиях, так что доверять информации
  можно, даже если сам автор её от корки до корки не читал."

The design as drafted:

1. **Sign-off.** The per-document human signature is removed. The human signs the result of a
   reviewer calibration run, and handles exceptions only: a `/doc-loop` stop after round 3, repo
   settings, disclosure of the project's own security posture, leaks of private material. D15,
   D20 and D26 are superseded by a new decision entry.

2. **Negative guarantee (defines `blocking`).** For each in-scope reader type, a doc never leads
   to an option that (i) is unavailable on that reader's plan, (ii) contradicts a quoted source,
   or (iii) leaves the reader with no next step. Where nothing fits, the doc states the next step,
   which may be "apply the principle; look for the analogue in your tooling". A review finding is
   `blocking` iff it violates this guarantee for some reader type; everything else is a follow-up
   filed as an issue.

3. **Scope.**
   - Four reader types: solo or team of ≤3, each with or without money. Large companies out of scope.
   - The attended/unattended-agent axis is a mandatory question wherever it changes the answer;
     otherwise one line says the answer does not depend on it.
   - Examples are GitHub-only. GitLab/Gitea/Bitbucket dropped; other hosts by analogy.
   - A plan-tier fact is restated only where a "Fits only if" line depends on it, with link and date.
     A weekly `scripts/check_quotes.py` run verifies quotes.
   - `tried` applies only to the human's own reader type (solo, GitHub Free, paid AI subscription);
     the README says so. Everything else is `sourced`.

4. **Private evidence** is published as scrubbed traces in `examples/`.

5. **Trust basis.**
   - Reviewer = the same model as the writer, in a fresh context, running the `review-doc` skill.
   - Calibration corpus = real escaped defects from PRs #75 and #81 (and later PRs). "Escaped" =
     found in round N+1 in text unchanged since round N. Seeded/planted defects are kept only as a
     smoke test and reported on a separate line.
   - Gate: recall on `blocking` defects, stated as the lower bound of a 95% interval ≥ X (X not yet
     set; the earlier draft was point recall ≥ 0.8 at n ≥ 30 with no defect class at zero). n = 30
     is a provisional gate, target n ≥ 60.
   - False-blocking rate (precision on blocking findings) is measured and reported next to recall;
     no threshold yet.
   - Held-out rule: defects that drove an edit to the reviewer skill are excluded from the recall
     number.
   - Drift: each calibration record carries model id and a hash of the skill; a mismatch with the
     running reviewer means recalibration.
   - Review runs in chunks (per option / per section); the 30,000-byte doc size cap stays.
   - Pass 3 (how-to-choose/value test) must write its reasoning before its verdict; in pass 1
     (claims) the verdict rests on the extracted quote.
   - Independence is claimed from the deterministic checks (`check_quotes.py`, structure gate,
     gitleaks), not from the fresh context. No second model vendor.
   - Issues filed by readers feed the corpus.

6. **Enforcement.**
   - `review-doc` runs in GitHub Actions using the `CLAUDE_CODE_OAUTH_TOKEN` repo secret, as a
     required status check on `main`.
   - Trigger: `pull_request` from same-repo branches only. Never `pull_request_target` with a
     checkout of PR code.
   - `enforce_admins` is enabled on `main`.
   - Frontmatter `signed_off` becomes `reviewed: {commit, report, recall}`; `docs/SIGNOFF.md`
     becomes a review ledger; the two-commit rule stays; `tests/structure_gate.py` is updated.
   - `docs/publishing-discipline.md` "Our own choice" is rewritten around its option 7, including
     the residual gap: the agent operates with an admin token, so it can turn `enforce_admins` off
     and remove labels.

7. **Process.**
   - `/doc-loop` is one command: write → self-check → review in Actions → fix → delta check →
     report as a PR comment → issues for follow-ups. Max 3 rounds; after round 3 it stops with
     "doc too broad — cut the scope", applies the `waiting-human-review` label and comments.
   - Weekly cron runs `check_quotes.py`.
   - The `waiting-human-review` hold on every PR is removed in stages: only after two consecutive
     docs each pass with ≤1 fix round while the corpus gate holds. Until then the human removes
     the label and merges.
   - The human always performs the merge of content PRs.

8. **README.** States: the project idea and that a human came up with it; that an agent writes
   and an agent reviews in a separate context; the measured recall with interval, n, date and
   commit; the four reader types; what `tried` and `sourced` mean; complete install steps; the
   named accountable human; "found an error → file an issue"; and that no human read each doc
   before publication.

Order of work: (1) finish PR #81 under the new scope; (2) classify #81 round-2 findings as
fix-added vs old text; (3) corpus + calibration run; (4) review workflow as required check;
(5) ledger replacement, decision entry, `publishing-discipline.md` rewrite; (6) README;
(7) staged removal of the PR hold.

## Acceptance criteria as drafted

- AC1. A new decision entry supersedes D15/D20/D26 and records the path of the raw critique file.
- AC2. A corpus file of real escaped defects exists: ≥30 entries, each with source PR/commit,
  defect class, blocking/follow-up label, held-out flag. Seeded defects are stored separately.
- AC3. `CALIBRATION.md` records a run on that corpus: blocking recall with 95% interval and n,
  false-blocking rate, per-class counts (no class at zero), model id, skill hash, date, commit.
  The gate is the interval's lower bound ≥ X. The human signs this result.
- AC4. A workflow runs `review-doc` on `pull_request` (same-repo branches only) with
  `CLAUDE_CODE_OAUTH_TOKEN`, posts the report as a PR comment, and its status is a required check.
  No `pull_request_target`. A PR the workflow cannot review does not pass.
- AC5. `tests/structure_gate.py` enforces `reviewed: {commit, report, recall}` and the review
  ledger with the two-commit rule; its tests are updated; existing docs are migrated.
- AC6. `review-doc`: chunked review; reasoning before verdict in pass 3; `blocking` defined by the
  negative guarantee over the four reader types.
- AC7. `/doc-loop` skill exists: max 3 rounds, stop behaviour as described, follow-ups filed.
- AC8. Weekly cron runs `check_quotes.py`; a failure opens or updates an issue.
- AC9. `docs/publishing-discipline.md` "Our own choice" rewritten, residual admin-token gap stated.
- AC10. README contains the items in design point 8; a CI test asserts the README recall figure
  equals the `real` line of `CALIBRATION.md` and includes the interval.
- AC11. The PR hold is removed only after two consecutive docs pass with ≤1 fix round while the
  corpus gate holds.
- AC12. A model-id or skill-hash mismatch against the latest calibration record makes the review
  check fail (or flags recalibration) rather than silently reusing the old recall figure.
