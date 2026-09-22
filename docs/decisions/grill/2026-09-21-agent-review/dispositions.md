# Dispositions — grill loopback, agent-review replaces per-doc sign-off

Raw verdicts: `critique-raw.md` (117 IDs). Triage: `triage.md`. Option letters refer to `triage.md`.

## Block A — answered 2026-09-19

User's reply: "по D прочитал, везде согласен с рекомендацией." One reply covering ten clusters, given
after reading each; recorded per cluster below with the concrete commitment each one carries.

| Cluster | Disposition | Option | What it commits to |
|---|---|---|---|
| D1 | accept | (c) + label rules + held-out rule | No numeric gate until n supports one. Publish counts only (caught / missed / n). The label rules and the held-out rule are written down before any corpus result is read. |
| D2 | accept | (b) | blocking = clauses (i)–(iii) + every pass-1 `mismatch` + every wrong `tried`/`sourced` status. `unverifiable` gets a rule. The doc states when the fallback line satisfies (iii). A `missing` option is a follow-up unless it leaves a reader type with no option (clause iii). |
| D3 | accept | (b) + (c) | The human reads `examples/` traces and any PR that adds scrubbed private-derived material. A local pre-push gate, with detection widened to variants, commit messages and the PR/issue text `/doc-loop` writes. |
| D4 | accept | (b) | No human signature on `CALIBRATION.md`. The human does a clerical click-through audit: k randomly drawn blocking-class claims per doc or release; misses go to the corpus. This is recurring human work, so "sign-off → 0" is not reached. |
| D5 | accept | (b), as a separate check | `pull_request` review stays. A second small required check runs on `pull_request_target` WITHOUT checkout, reads only the changed-file list through the API, and fails any PR that touches the workflow, skill, calibration or gate files. Such PRs need the human. |
| D6 | accept | (a) now; (b) before the hold is removed | Disclosure extended to the merge path and unattributable label removal. A separate non-admin agent identity is the precondition for removing the PR hold. |
| D7 | accept | (c), worded as (a) until data exists | The published figure is labelled a floor on same-model agreement, not recall, until a defect source the model did not select (D4 audit, reader reports) has data. |
| D8 | accept | (a) + the D4 audit | The independence claim is withdrawn: the blocking classes are guarded by same-model review, plus the human click-audit for clauses (i) and (ii). |
| D9 | accept | (b) | Guarantee reworded as a dated, as-of-review aim. The figure ships with class, denominator, n and provisional status. Plain statement that wrong non-blocking facts may ship. |
| D13 | accept | (b) | The new decision supersedes D15/D20/D26 and amends D1, D11, D18, AC items 1/3/5 and the v0.9.0 binding; written after `claude/journal-1895` lands in jarvis. |

## F — applied (no veto)

- F1 (C63, G24): point 6 of the design no longer lists `enforce_admins` as a new step; it is already on.
  `docs/publishing-discipline.md:287` is corrected in the AC9 rewrite.
- F2 (G6): the hold is described as it works: the label is auto-applied only on `opened` /
  `ready_for_review` at run attempt 1 when no reviewer is requested; the check fails while the label is
  present or a review is requested.

## L — accepted as triaged (not mentioned in the reply)

- L1–L3 → one follow-up issue (see below). L4 dropped as stale.

## Held options of PR #81 (B19 vendor-hosted cloud agent, B20 private staging repo)

Under D2 (b) a `missing` option is a follow-up: round 3 pass 3 found no setup that ends with nothing
left. They do not block #81 and go to #94.

L follow-up issue: #95 (filed 2026-09-19). Held options B19/B20: comment on #94 (issuecomment-5740809300).

## Block B — answered 2026-09-19 (one answer per cluster)

| Cluster | Disposition | Option | What it commits to |
|---|---|---|---|
| D10 | accept | (b) | The record lives outside the doc body. Frontmatter carries one flat key `review: <PR URL>`; the report is a PR comment; the measured counts live in the README only. `docs/SIGNOFF.md` and the two-commit rule go. Departs from the phase-2 form `reviewed: {commit, report, recall}`, which cannot describe its own head commit. |
| D12 | accept | (b) | Drift key = workflow file + pinned action version + explicit `--model` + `SKILL.md` hash. A mismatch fails the check until recalibration. `CALIBRATION.md` moves out of the hashed path. The untracked `.claude/skills/review-doc` copy becomes a symlink. A silent vendor update under the same model id is not detected; disclosed. |
| D14 | accept | (a) | The job always runs, classifies the PR inside a step, passes non-doc PRs explicitly and fails unreviewable ones explicitly. Delta versus full is decided by a deterministic diff rule. |
| D15 | accept | (b) | `check_quotes.py` is a required PR check that fails on `NOT FOUND` only; the unfetchable count is printed in the report. The full `tests/` suite runs in CI (#84). |
| D17 | accept | (a) | A red or pending check means wait; nothing routes to a human hold. User: "квоты хватит. Хотя если получится уменьшить стоимость, без риска, конечно делаем". Cost reduction is allowed only where it cannot fail open: a draft PR fails the check explicitly with "not reviewed: draft", review runs on ready PRs, `concurrency: cancel-in-progress`. |
| D19 | accept | (c) | An empty `review` key is allowed. The README lists which docs passed the calibrated review, with dates; the six existing docs go through `/doc-loop` one by one. |
| D24 | accept | (c) | One run per commit. Every run posts a new comment and never edits an old one; blocking findings from all runs on the same commit are unioned, so a re-run cannot erase a finding. k=3 runs happen at calibration time only, and the spread is published next to the counts. |

## Block C — answered 2026-09-21 (one answer per cluster)

| Cluster | Disposition | Option | What it commits to |
|---|---|---|---|
| D11 | accept | (b), cap 3 | A round = one full review plus its fix/delta cycle. The workflow counts rounds (full-review reports on distinct commits); the agent does not count itself. No false-blocking threshold until data exists; the count is published (consistent with D1 (c)). The stop message reports observed facts: open blocking count per round and the share of fix-induced findings. |
| D16 | accept | (c), cheap form | Baseline run before enabling, explicit file enumeration, one rolling issue with a closure rule, the agent's next session acts on it. README carries the cron workflow's status badge and one line on the 60-day rule. Verified 2026-09-21 against docs.github.com "Events that trigger workflows": "In a public repository, scheduled workflows are automatically disabled when no repository activity has occurred in 60 days." No keep-alive commits. |
| D18 | accept | (d) | AC extended to `doc-structure-gate.md` option 9, `docs/SIGNOFF.md` and the paired resource and examples. Scope migration to the four reader types happens doc by doc as each passes `/doc-loop`. In `publishing-discipline.md` option 7 (human read) stays; a NEW option "model review as a required check + human sample audit" is added and "Our own choice" points at it. Departs from the phase-2 wording "rewritten around option 7". |
| D20 | accept | (b) | One rolling follow-up issue per doc, de-duplicated across rounds, filed by `/doc-loop` through the `/file-issue` process. The Actions reviewer only comments. |
| D21 | accept | (a) | Issues accept doc errors through a new `doc-error` template (doc, quote or line, what is wrong, source link). The agent triages; an entry reaches the corpus only after the human's D4 click-check. README "Support" is rewritten. jarvis D17 and D19 join the D13 supersession/amendment list. |
| D22 | accept | (b) public / (a) private | `tried` on a public source project must link the public commit, PR or run. `tried` on either of the two private source projects keeps a scrubbed trace in `examples/` (read by the human under D3) and README states it is self-reported. Trace-less `tried` markers and the combined "tried and sourced" status in `agent-safety-hooks.md` go to that doc's follow-up issue. |
| D23 | accept | (c) | AC: `/doc-loop` invokes the write-doc fix protocol (`.agents/skills/write-doc/SKILL.md:133`). The review report carries a separate "fix-induced" line, which feeds the D11 stop message. |
| D25 | OPEN | — | User, 2026-09-21: "отдельную учётку для агента не получится сделать." This contradicts the accepted D6 "(b) before the hold is removed", so D6 is reopened under the answer-vs-answer conflict rule. D25 and D6 are re-asked together. AC-lock stays blocked. |

## D25 + D6 reopened — answered 2026-09-21

User: "25 и 6 — согласен с рекомендацией" (one reply to one combined question; recorded per cluster).

| Cluster | Disposition | Option | What it commits to |
|---|---|---|---|
| D6 | accept (replaces the 2026-09-19 answer) | re-ask (b) + (c) | No separate agent identity. A harness deny hook on `gh pr merge`, removal of `waiting-human-review`, and the branch-protection API — documented as a hold, not proof (`publishing-discipline.md:104-107`). A detector workflow on `branch_protection_rule` (created/edited/deleted; file must be on the default branch) and `pull_request: unlabeled` opens an issue on every such event. Disclosure: "the human merges" is a convention with a detector, not a mechanism; README and the doc say so. GitHub App identity is recorded as the known upgrade; return condition: the detector fires once on an act the human did not perform. Rejected: keep auto-hold forever (the agent can remove the label with the same token, so it protects nothing against this threat). |
| D25 | accept | (c), single trigger | `waiting-human-review` stays a required check permanently; only its auto-application is removed. Trigger: on two consecutive docs chosen by the human, the D4 click-audit finds zero misses. The identity precondition is dropped (the hold never protected against the D6 threat). |

Facts verified 2026-09-21: GitHub ToS B.3 allows one machine account; `branch_protection_rule` and `pull_request: unlabeled` triggers exist (docs.github.com, "Events that trigger workflows").

All D clusters (D1–D25) now have a disposition. F applied. L filed as #95. AC-lock unblocked.

## Post-lock addendum — answered 2026-09-21, during ticketing

Two gaps surfaced while the locked design was cut into issues. Both were put to the user as
separate questions with a recommendation; reply: "A–D согласен с рекомендацией". Neither changes
an AC; each fills in a mechanism an AC left open.

| Gap | Belongs to | What it commits to |
|---|---|---|
| A. How a reviewer-machinery PR ever merges | D5, AC5 | The guard does not fail such a PR forever. It runs from the base branch, re-applies `waiting-human-review` on every push of a PR that touches machinery files, and is red while the label is present. The human removes the label after reading; the detector (D6) records the removal. Finding behind it: the existing `waiting-human-review.yml` runs on `pull_request`, so a PR can rewrite the check that holds it; the guard on `pull_request_target` without checkout closes that. |
| B. Click-audit size and draw | D4, AC17 | k = 5 claims per doc, or all of them if the doc has fewer. A script draws them, seeded with the PR head SHA, so the draw is reproducible and the agent does not pick. k is revisited on the first audited miss. |

Ticketing (jarvis-oss, milestone v0.9.0, parent #38): #96–#112. AC2a + AC17 → #96; AC2b → #101;
AC8 → #102; AC4 + AC15 → #104; AC3 → #106; AC5 → #97; AC6 → #98; required checks → #107;
AC7 → #108; AC9 → #109; AC13 → #111; AC11 → #103; AC14 → #110; AC12 → #99 (hook, detector) and
#100 (leak gate); AC10 → #105; AC16 → #112.
