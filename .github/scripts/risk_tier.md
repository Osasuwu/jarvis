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
   - **path tier** — HIGH when a changed path (or a rename's old path) matches the `guarded`
     bucket of this repo's entry in the host's `config/protected-paths.json` at the base
     commit, in the glob dialect of `agents/path_policy.py` (#2067). The `hitl`, `machinery`
     and `gate` buckets set no floor (#2200): their paths reach the tier through test
     weakening and the classifier like any other path. A missing file, or no entry for the
     repo, is HIGH on every diff (D2), with a reason that points at
     `docs/reference/lane-host-setup.md`;
   - **test weakening** — HIGH when the PR removes a test function that no file of the PR
     re-adds, removes a test file, touches a test file GitHub could not diff, or adds
     `pytest.mark.skip`, `skipif`, `xfail`, `pytest.skip(`, `pytest.xfail(`,
     `pytest.importorskip(`, `unittest.skip` or `collect_ignore` to a test file (a path under
     `tests/`, or `test_*.py`, `*_test.py`, `conftest.py`);
   - **classifier tier** — `agents.plan_classifier.classify` on the diff: ordinal 3 → HIGH,
     2 → MEDIUM, 1 → LOW.

   Anything the check cannot read (the protected list, `config/plan_review.yaml`, a files
   listing shorter than the PR's `changed_files`) is HIGH: unreadable never reads as clean.

   **Comment-only exemption** (#2201). A diff that matches a protected path loses the path
   tier, and the classifier loses its shared-surface input, when it changes comments alone.
   Test weakening, churn and the area count still apply, so a comment-only diff can still
   read MEDIUM or HIGH. The rule covers Python only. It applies when all of these hold:
   - Every listed file is a `.py` file with status `modified`. An added, removed or renamed
     file has no two sides of one path, so the diff gets no exemption. Neither does any
     other file type, a `.md` or `.yml` beside the Python included.
   - The PR lists at most 30 files (`MAX_SOURCE_FILES`). Past that, nothing is read, and
     the summary says `comment-only exemption not checked: <n> files, more than 30`.
   - Both sides are readable. Each file is read through the contents API at the PR's
     merge base (from `compare/{base}...{head}`, the commit the file list is a diff
     against) and at its head. A failed read, or an entry that is not an inline base64
     file, keeps the floor. That includes a directory and a file over the API's 1 MB
     inline limit. The summary says `comment-only exemption not checked: <why>`.
   - The `ast.dump` of both sides is equal. A docstring is a node of the AST, so a
     docstring edit is a code change here.
   - Every directive comment is unchanged and at the same anchor: its count of code tokens
     before it, and whether it trails code on its line. A shebang or coding cookie must
     also keep its line number. The directives covered are `noqa`, `type:`, `pragma`, `fmt:`, `isort:`,
     `pylint:`, `mypy:`, `pyright:`, `pyre-`, `ruff:`, `flake8`, `nosec`, `gitleaks:`,
     `yapf:`, a shebang and a coding cookie, in any case. They steer a linter, a type
     checker or a scanner, so moving one changes what the code is checked for.
   - Neither side has a lone CR. Python versions and tools disagree on whether it ends a
     line, so the line a directive sits on is not well defined.
   - Neither side fails to decode, parse or tokenize. Any such failure keeps the floor.

   When the exemption applies, the summary carries `comment-only exemption: protected
   path(s) <paths> changed in comments only`, and the job emits the same text as a
   `::notice title=risk-tier::` annotation. The annotation is where an adoption count reads
   it. A new language gets no exemption until it has a comparison rule of its own, as
   Python's AST is here.
3. **Final tier = max(computed, declared, the reviewer's raise).** The declared line and the CI
   reviewer's raise (*The reviewer's raise* below, #2202) can raise the tier, never lower it.
   While the code review of the head has not completed, the check is red, waiting for it.
4. LOW and MEDIUM → green. HIGH and CRITICAL → green when **the PR's author holds the releasing
   role (admin)** (#2088): the author of the live PR object (`GET pulls/{n}`) is not a `Bot`
   account, is not `LANE_BOT_LOGIN` (the caller's `bot-login`, compared case-insensitively;
   empty fails the check), and `GET /repos/{repo}/collaborators/{login}/permission` says
   `admin`. The summary still names the tier and its reasons, followed by `<TIER> hold skipped:
   author <login> has admin permission`. An author whose permission cannot be read counts as
   not admin.

   Every other author (the lane's bot, Dependabot, a `write` collaborator) → red until **a holder
   of the releasing role (admin, not a `Bot` account, not `LANE_BOT_LOGIN`) has an APPROVED review
   on the current head SHA**: the reviewer's latest non-comment review is APPROVED, its
   `commit_id` is the live head, the reviewer is not a `Bot` account and not `LANE_BOT_LOGIN`,
   and the same permission lookup says `admin`. A new push moves the head, so it re-reds; a
   dismissed or superseded review does not count. A bad `Risk:` line (step 1) stays red for every author, an admin included.

## Dependabot PRs

A Dependabot PR body carries upstream release notes, not a `Risk:` line, and Dependabot rewrites
it on every rebase, so step 1 would hold it red with nothing able to release it (#2059). For a PR
whose author, read from the live PR object of the API (`GET pulls/{n}`), has login
`dependabot[bot]` **and** type `Bot`, the check does not read the body at all: the declared tier
is fixed at **HIGH** and the summary says `declared HIGH (fixed: dependabot[bot] PR, body not
read)`. Steps 2–4 run unchanged. A `Bot` author never qualifies for step 4's admin-author pass,
so the PR holds until a holder of the releasing role (admin, not a `Bot` account, not the lane's bot)
approves its current head.

- The match is on the API's author object, never on PR text. The `[bot]` suffix is reserved for
  GitHub Apps; a look-alike human login (`dependabot`) or another bot (`renovate[bot]`) gets the
  ordinary missing-line verdict.
- A `Risk:` line in the body, of any tier, malformed or duplicated, changes nothing: the body is
  third-party text.
- HIGH rather than the computed tier alone: on a host whose protected list omits the dependency
  manifests, the classifier's dependency-bump exemption reads LOW, and a commit a maintainer pushes
  onto the Dependabot branch would ride it. Since #2200 the `machinery` bucket no longer floors
  a dependency manifest, so this fixed tier is what holds a Dependabot diff at HIGH.

## Base-commit trust model

Two trees, neither the PR's. The **host's protected list** is read from the PR's base branch
(`RISK_TIER_HOST_ROOT`): a PR that adds a path to `config/protected-paths.json` gets no benefit
from it for its own verdict. The **classifier code and `plan_review.yaml`** come from the
script's own checkout: the `.github/actions/risk-tier` composite action's download of jarvis at
the pinned SHA (jarvis included, since #2013 PR2), so a host
runs a reviewed classifier rather than whatever its own base holds (D7). The PR itself is read
through the API as data and is never checked out, imported or executed. It is a `pull_request`
workflow, not `pull_request_target` (D11/D11b). Host setup: `docs/reference/lane-host-setup.md`.

Reconciliation with the classifier's exempt short-circuit (docs-only, dependency-bump, …): the
exemption lowers only the classifier ordinal. It never lowers the path floor, so a docs-only
change to a `guarded` path stays HIGH.
The one rule that lowers the path floor is the comment-only exemption above. It decides
from the code on both sides of the diff, never from the paths alone.

## The `Risk:` grammar

One line of the PR body, anywhere outside a code fence, HTML comment or `>` blockquote:

```
Risk: LOW|MEDIUM|HIGH|CRITICAL — <reason>
```

- Up to three spaces of indentation and an optional list marker `- ` or `* ` may precede it. A line indented four spaces or more (or by a tab) is an indented code block and is ignored.
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
| `    Risk: LOW — indented code` | missing |
| `   Risk: LOW — three spaces` | LOW |

The PR template (`.github/PULL_REQUEST_TEMPLATE.md`) carries `Risk: <LOW|MEDIUM|HIGH|CRITICAL> —
<reason>` unfilled, which is malformed on purpose: the check stays red until the author fills it in.

## The reviewer's raise

The CI reviewer (`code-review.yml`) may raise the tier when the diff is riskier than the
`Risk:` line and the path rules say (#2202). Its evidence (`review-evidence.json`, validated by
`code_gate_verdict.py`) carries an optional top-level `"raise": {"tier": "MEDIUM"|"HIGH",
"reason": "<1..300 chars>"}` (`LOW` validates but can never apply). Any other shape
(another key, `CRITICAL`, an empty or overlong reason) fails validation: the reviewer retries, then the
review run fails, so no evidence exists and `code-gate` stays red.

- **Only up.** Final = max(declared, computed, raise). A raise at or below that max changes
  nothing; the summary still logs it as `reviewer raise to <T> not applied: at or below <F>`.
  An applied one reads `reviewer raise to <T> applied (was <F>)`, with the reviewer's reason.
- **Which evidence.** The same runs `code-gate` reads (`gather_entries`): every attempt of
  every `code-review.yml` run on the head SHA bound to this PR. The highest raise wins.
- **Fail closed.** Evidence that is unreadable, malformed, bound to another commit, expired or
  deleted, a run listing that cannot be read, or a lookup of `code-review.yml` that fails with
  anything but 404, each read as a raise to HIGH: an unknown raise is not "no raise".
- **Waiting.** Until a bound review run on the head has completed successfully with evidence
  (`reviewed` or `skipped`), the check is red, `waiting for the code review of <sha7>`. A run
  still in progress or awaiting approval also waits.
- **Not read**: on a host with no `.github/workflows/code-review.yml` (404), and on a PR into a
  branch other than the default one (`code-gate` does not review those). The summary notes why.
- **Re-decision.** `risk-tier` is a job of `pr-body-check.yml`, so only a run of that job
  changes its check. When a review completes, the `risk-tier-redecide` job of
  `code-gate-verdict.yml` (the only job there with `actions: write`) re-runs the latest
  `risk-tier` job on the reviewed head (`risk_tier_redecide.py`), unless a run created after
  the review completed already reads its evidence; a run still in progress is awaited up to
  600 s. The `verdict` job needs it, so `code-gate` is not posted for that review before
  `risk-tier` is re-queued; a failed re-run leaves `code-gate` unposted for the event.

Residuals:

1. **Re-running a successful review on the same SHA floors the tier at HIGH.** The re-run
   deletes the earlier attempt's artifact; that attempt then reads as deleted evidence.
   Pushing a new commit clears it.
2. **The re-run API refuses runs older than 30 days.** The redecide job then fails and
   `code-gate` stays unposted for that event; a new push re-runs both.
3. **A failed redecide followed by the scheduled sweep.** The sweep in `code-gate-verdict.yml`
   can post a green `code-gate` while `risk-tier` still shows the run from before the review,
   which was red (waiting) unless an earlier review had completed on the same head. Narrow
   case: a draft marked ready, or a dispatched review, on a head already reviewed once.
4. **A job re-run with `GITHUB_TOKEN` is unverified live** at merge time of #2202; the tests
   drive the script against a fake API.

## Residual risks

1. **A `pull_request` workflow runs the workflow file of the PR head.** A PR that edits
   `.github/workflows/pr-body-check.yml` can alter this job. Mitigations: the worker's token
   carries no `workflow` scope (D1), so the lane cannot push such a change, and fork PRs need a
   maintainer's approval to run. D11 rejected the alternative (`pull_request_target`) for the
   larger exposure it brings.
2. **An admin-authored HIGH or CRITICAL PR merges without a second look.** That includes a PR an
   agent session opens under the admin's own account: the check sees an admin author and skips
   the hold, and no `--admin` merge with its marker is left as a trace. Accepted by the 2026-10-16
   `/grill` (`docs/decisions/2026-Q4.md`, "risk-tier hold scoped to non-admin authors"; critic S1):
   it is the state before the check was required, when the admin already merged HIGH PRs with a
   plain `gh pr merge`. GitHub does not let an author approve their own PR, so a hold on the
   admin's own PRs had no eligible releaser.
3. **The author is read from the PR object, not from each push.** A push to an admin-opened PR's
   head by another account does not re-apply the hold: the PR's author is still the admin.
   Deferred to #2089.
