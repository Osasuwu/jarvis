# risk-tier

The required check `risk-tier` (job `risk-tier` in `.github/workflows/pr-body-check.yml`,
script `.github/scripts/risk_tier.py`, issue #2004) turns the PR body's `Risk:` line into a merge
hold. Decisions: D7, D10, D11 and "Risk-tier check — the hold is the check itself" in
`docs/decisions/2026-Q4.md`.

It runs on `pull_request` (opened, edited, reopened, synchronize) and on `pull_request_review`
(submitted, dismissed), so an approval or a dismissal re-evaluates it without a push.

## The verdict

1. The body must carry **exactly one** well-formed `Risk:` line (grammar below). Missing,
   malformed or duplicate → red.
2. The **computed tier** is the highest of:
   - **path tier** — HIGH when a changed path (or a rename's old path) matches any bucket
     (`hitl`, `guarded`, `machinery`) of this repo's entry in `config/protected-paths.json`;
   - **test weakening** — HIGH when the PR removes a test function that no file of the PR
     re-adds, removes a test file, touches a test file GitHub could not diff, or adds
     `pytest.mark.skip`, `skipif`, `xfail`, `pytest.skip(`, `pytest.xfail(`,
     `pytest.importorskip(`, `unittest.skip` or `collect_ignore` to a test file (a path under
     `tests/`, or `test_*.py`, `*_test.py`, `conftest.py`);
   - **classifier tier** — `agents.plan_classifier.classify` on the diff: ordinal 3 → HIGH,
     2 → MEDIUM, 1 → LOW.

   Anything the check cannot read (the protected list, `config/plan_review.yaml`, a files
   listing shorter than the PR's `changed_files`) is HIGH: unreadable never reads as clean.
3. **Final tier = max(computed, declared).** The declared line can raise the tier, never lower it.
4. LOW and MEDIUM → green. HIGH and CRITICAL → red until **an admin human has an APPROVED review
   on the current head SHA**: the reviewer's latest non-comment review is APPROVED, its
   `commit_id` is the live head, the reviewer is not a `Bot` account and not `LANE_BOT_LOGIN`
   (default `osasuwu-bot`), and `GET /repos/{repo}/collaborators/{login}/permission` says
   `admin`. A new push moves the head, so it re-reds; a dismissed or superseded review does not
   count. There is no author-based exemption.

## Base-commit trust model

The job checks out the PR's **base branch** and runs the script from it. The protected list, the
classifier and `plan_review.yaml` are therefore the base's: a PR that adds a path to
`config/protected-paths.json`, or loosens the classifier, gets no benefit from it for its own
verdict. The PR itself is read through the API as data and is never checked out, imported or
executed. It is a `pull_request` workflow, not `pull_request_target` (D11/D11b).

Reconciliation with the classifier's exempt short-circuit (docs-only, dependency-bump, …): the
exemption lowers only the classifier ordinal. It never lowers the path floor, so a change to a
dependency manifest or a doc under `docs/security/` stays HIGH through the `machinery` bucket.

## The `Risk:` grammar

One line of the PR body, anywhere outside a code fence, HTML comment or `>` blockquote:

```
Risk: LOW|MEDIUM|HIGH|CRITICAL — <reason>
```

- An optional list marker `- ` or `* ` may precede it.
- `Risk` and the tier are case-insensitive; the tier is read as upper case.
- The tier may be wrapped in `**` (bold). The *label* may not: `**Risk**:` is malformed. `__x__` bold is
  not accepted either: the lenient parser in `lane_publish.py` cannot read it.
- The separator is an em dash (U+2014), an en dash (U+2013), `--` or `-`, with whitespace on both
  sides. The reason after it must be non-empty.
- Lines inside ``` or ~~~ fences, inside `<!-- -->` comments and in `>` blockquotes are ignored.
- A line that opens like a Risk line (`Risk:` after the optional marker) but does not match the
  rest is **malformed**, not ignored. Two such lines, well-formed or not, are **duplicate**.
- The grammar is a subset of the lenient `parse_risk` in `lane_publish.py`: every accepted line
  parses to the same tier there.

`<br>` stands for a line break in the examples. The test `tests/ci/test_risk_tier.py` runs every
row against the parser, so the table cannot drift from the code.

| example | verdict |
|---|---|
| `Risk: LOW — docs only` | LOW |
| `risk: medium – small refactor` | MEDIUM |
| `- Risk: HIGH -- touches auth` | HIGH |
| `* Risk: CRITICAL - data loss` | CRITICAL |
| `Risk: **HIGH** — logic change` | HIGH |
| `Risk: __low__ — naming` | malformed |
| `Risk : LOW — space before the colon` | LOW |
| `Risk:LOW — no space after the colon` | LOW |
| `## Summary<br>text<br>Risk: LOW — among other lines` | LOW |
| `Risk: LOW — kept<br>~~~<br>Risk: HIGH — fenced, ignored<br>~~~` | LOW |
| `Risk: LOW` | malformed |
| `Risk: LOW —` | malformed |
| `Risk: LOW—no spaces` | malformed |
| `Risk: LOWER — x` | malformed |
| `Risk: URGENT — x` | malformed |
| `Risk: — x` | malformed |
| `**Risk**: LOW — bold label` | malformed |
| `Risk: LOW — a<br>Risk: HIGH — b` | duplicate |
| `Risk: LOW — a<br>Risk: oops` | duplicate |
| `~~~<br>Risk: LOW — x<br>~~~` | missing |
| `<!-- Risk: LOW — x -->` | missing |
| `<!--<br>Risk: LOW — x<br>-->` | missing |
| `> Risk: LOW — quoted` | missing |
| `Risk assessment: LOW` | missing |
| `no risk line here` | missing |

The PR template (`.github/PULL_REQUEST_TEMPLATE.md`) carries `Risk: <LOW|MEDIUM|HIGH|CRITICAL> —
<reason>` unfilled, which is malformed on purpose: the check stays red until the author fills it in.

## Residual risks

1. **A `pull_request` workflow runs the workflow file of the PR head.** A PR that edits
   `.github/workflows/pr-body-check.yml` can alter this job. Mitigations: the worker's token
   carries no `workflow` scope (D1), so the lane cannot push such a change, and fork PRs need a
   maintainer's approval to run. D11 rejected the alternative (`pull_request_target`) for the
   larger exposure it brings.
2. **No eligible releaser for the sole admin's own HIGH PRs.** GitHub does not let an author
   approve their own PR, and the repo has one admin human. A HIGH or CRITICAL PR authored by that
   admin stays red until the operator picks a route (open the PR from the bot account, add a second
   admin, or a recorded admin-merge). This is the D1 "no independent approver" residual, not a bug
   of the check.
