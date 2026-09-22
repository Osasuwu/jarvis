# Agent review replaces the per-document human sign-off — design locked 2026-09-21

Inputs: `payload.md` (what the critics saw), `critique-raw.md` (117 verdict IDs), `triage.md`,
`dispositions.md` (every D cluster, F and L). Research:
`jarvis/docs/research/agent-reviews-agent-2026-09-19.md`.

## 1. What the human still does

The per-document signature is removed. It certified nothing: the human is not a domain expert on
most topics, and everything they know or tried is already available to the agent. "Sign-off → 0"
is NOT reached. Residual recurring human work:

1. **Click-audit (D4).** Per doc or release, k randomly drawn blocking-class claims are
   click-checked against their source. A miss goes to the corpus. No signature on `CALIBRATION.md`.
2. **Leak read (D3).** `examples/` traces and any PR that adds scrubbed private-derived material.
3. **Reviewer-machinery PRs (D5).** Any PR that touches the review workflow, the skills, the
   calibration files or the gates.
4. **The merge of content PRs.** A convention with a detector, not a mechanism (D6).
5. **Stops.** A `/doc-loop` stop after round 3.

## 2. Negative guarantee and `blocking`

Dated, as-of-review aim (D9), not a promise: for each in-scope reader type a doc does not lead to an
option that (i) is unavailable on that reader's plan, (ii) contradicts a quoted source, or (iii)
leaves the reader with no next step. Wrong non-blocking facts may ship; the README says so.

`blocking` (D2) = clauses (i)–(iii) + every pass-1 `mismatch` + every wrong `tried`/`sourced`
status. `unverifiable` gets a written rule. The doc states when the fallback line satisfies (iii).
A `missing` option is a follow-up unless it triggers (iii).

## 3. Scope

- Four reader types: solo or team ≤3, each with or without money. The attended/unattended axis is
  asked wherever it changes the answer. Examples are GitHub-only.
- `tried` only for the author's own reader type (solo, GitHub Free, paid AI subscription).
  Admissibility (D22): a public source project → link to the public commit, PR or run; either of the
  two private source projects → scrubbed trace in `examples/`, README says it is self-reported.
- Existing docs migrate to this scope one at a time as each passes `/doc-loop` (D18 (d), D19 (c)).

## 4. Trust basis

- Reviewer = same model, fresh context, `review-doc` skill. The independence claim is withdrawn
  (D8): the blocking classes are guarded by same-model review plus the click-audit for (i), (ii).
- Corpus of real escaped defects. Label rules and the held-out rule are written before any corpus
  result is read (D1). No numeric gate. Published: counts only (caught / missed / n), per class,
  with the k=3 calibration-time spread (D24), labelled "a floor on same-model agreement", not
  recall, until a defect source the model did not select has data (D7): the click-audit and reader
  reports.
- Reader reports (D21): a `doc-error` issue template; the agent triages; an entry reaches the
  corpus only after the human click-check.
- Drift (D12): key = workflow file + pinned action version + explicit `--model` + `SKILL.md` hash.
  Mismatch fails the check until recalibration. `CALIBRATION.md` is outside the hashed path. A
  silent vendor update under the same model id is not detected; disclosed.

## 5. Enforcement

- Review job (D14, D17): always runs on `pull_request` (same-repo branches); classifies the PR in a
  step; passes non-doc PRs explicitly; fails unreviewable ones explicitly; a draft fails with
  "not reviewed: draft"; `concurrency: cancel-in-progress`. Delta versus full by a deterministic
  diff rule. One run per commit; each run posts a new comment; blocking findings from all runs on a
  commit are unioned (D24). Red or pending means wait.
- Machinery guard (D5): a second required check on `pull_request_target` WITHOUT checkout; reads
  the changed-file list through the API; fails PRs touching workflow, skill, calibration or gate
  files. How such a PR is released: `dispositions.md`, post-lock addendum A.
- `check_quotes.py` is a required PR check, failing on `NOT FOUND` only; the unfetchable count is
  printed. The full `tests/` suite runs in CI (#84) (D15).
- Record (D10): one flat frontmatter key `review: <PR URL>`, may be empty (D19). The report is a PR
  comment. Counts live in the README only. `docs/SIGNOFF.md`, `signed_off` and the two-commit rule
  go; `tests/structure_gate.py` and its tests follow.
- Agent/human separation (D6): no separate identity. A harness deny hook on `gh pr merge`, removal
  of `waiting-human-review` and the branch-protection API (a hold, not proof). A detector workflow
  on `branch_protection_rule` and `pull_request: unlabeled` opens an issue on every event. Known
  upgrade: GitHub App identity, if the detector ever fires on an act the human did not perform.
- Leak gate (D3): local pre-push gate with detection widened to variants, commit messages and the
  PR/issue text `/doc-loop` writes.
- `enforce_admins` is already on (F1). The hold works as in F2.

## 6. Process

- `/doc-loop`: write → self-check → review in Actions → fix (write-doc fix protocol, D23) → delta
  → report. Converts the PR to draft during fixes. Cap 3 rounds; a round = one full review plus its
  fix/delta cycle, counted by the workflow (D11). Stop: applies `waiting-human-review`, comments
  the observed facts (open blocking per round, fix-induced share). One rolling follow-up issue per
  doc, de-duplicated, via the `/file-issue` process (D20).
- Weekly cron (D16): baseline run first, explicit file list, one rolling issue with a closure
  rule, README badge, one line on the 60-day disable rule.
- Hold removal (D25): `waiting-human-review` stays required permanently; only auto-application is
  removed, after the click-audit finds zero misses on two consecutive human-chosen docs.
- `publishing-discipline.md` (D18): option 7 stays; a new option "model review as a required check
  + human sample audit" is added; "Our own choice" points at it and states the D6 gap.
  `doc-structure-gate.md` option 9, `SIGNOFF.md`, the paired resource and examples follow.

## 7. README

Project idea and that a human invented it; an agent writes and an agent reviews in another context;
the counts with class, denominator, n, date, provisional status; which docs passed the calibrated
review, with dates; the four reader types; `tried`/`sourced` and self-reporting; complete install
steps; how to report a doc error; that no human read each doc, next to what was checked and how;
that "the human merges" is a convention; the cron badge.

## Acceptance criteria

- AC1. A decision entry in `jarvis/docs/decisions/2026-Q3.md` supersedes D15/D20/D26, amends D1,
  D11, D17, D18, D19, AC items 1/3/5 and the v0.9.0 binding, and records the raw-critique path.
- AC2. Label rules and the held-out rule are committed before the corpus. The corpus holds real
  escaped defects with source PR/commit, class, blocking/follow-up label, held-out flag and
  selection source (model / click-audit / reader). Seeded defects are stored separately.
- AC3. `CALIBRATION.md` records k=3 runs: caught / missed / n per class with spread, the drift key,
  date, commit. No threshold, no signature. It sits outside the hashed path.
- AC4. Review workflow as in §5; required check; a PR it cannot review does not pass; drafts fail
  explicitly.
- AC5. Machinery-guard check as in §5; required; never checks out PR code.
- AC6. `check_quotes.py` required on PRs (`NOT FOUND` only); full `tests/` in CI.
- AC7. `structure_gate.py` enforces `review:` (URL or empty); `signed_off`, `SIGNOFF.md` and the
  two-commit rule removed; contract tests updated in the same PR (#95 L3).
- AC8. `review-doc`: `blocking` per §2; `unverifiable` rule; reasoning before verdict in pass 3; a
  "fix-induced" report line; `.claude/skills/review-doc` is a symlink.
- AC9. `/doc-loop` as in §6, including the fix protocol, draft conversion, workflow-counted rounds,
  factual stop message and the rolling follow-up issue.
- AC10. Weekly cron as in §6, enabled only after a baseline run.
- AC11. `doc-error` issue template; README "Support" rewritten; triage path documented.
- AC12. Deny hook + detector workflow as in §5; pre-push leak gate.
- AC13. `publishing-discipline.md` and `doc-structure-gate.md` updated as in §6;
  `publishing-discipline.md:287` corrected (F1).
- AC14. README as in §7; a CI test asserts the README counts equal `CALIBRATION.md`.
- AC15. A drift-key mismatch fails the review check.
- AC16. Auto-application of the hold is removed only on the D25 trigger; the label stays required.
- AC17. Click-audit procedure written down: k, how claims are drawn, where misses are recorded.
  (k and the draw: `dispositions.md`, post-lock addendum B.)
