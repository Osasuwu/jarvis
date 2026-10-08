# Lane host setup

How a repository other than jarvis runs the AFK lane (#2013). The lane is one set of reusable
workflows in jarvis; a host repo adds thin callers pinned to a jarvis commit. Decisions: D2 (host
prerequisites), D7 (`risk-tier` from a pinned checkout), D16 (enablement order) in
`docs/decisions/2026-Q4.md`. Jarvis is itself a host and uses the same callers.

## What a host gets, and what it supplies

| Shared file in jarvis | What it is | Caller in the host |
|---|---|---|
| `.github/workflows/lane.yml` | intake, worker, publish, escalation, ledger row; owns the per-host-repo concurrency group | a workflow on `issues: labeled` |
| `.github/workflows/lane-watch.yml` | escalates a lane PR with a red watched check | a `workflow_run` workflow |
| `.github/workflows/lane-close.yml` | finalises the ledger row when a lane PR closes | a `pull_request_target: closed` workflow |
| `.github/actions/risk-tier/` | the `risk-tier` required check | one job in a `pull_request` workflow |

The shared files carry no operator or host literal: no repo list, login, model or issue number.
Everything host-specific is a caller input; the two secrets are passed by name. The jarvis
callers (`agent-dispatch.yml`, `lane-red-check-watcher.yml`, `lane-ledger-close.yml`, the
`risk-tier` job of `pr-body-check.yml`) are the reference copies.

### Inputs and secrets

`lane.yml`:

| Name | Kind | Meaning |
|---|---|---|
| `bot-login` | input, required | the lane bot's login (D1) |
| `bot-email` | input, required | its commit email (`<id>+<login>@users.noreply.github.com`) |
| `model` | input, required | the worker model; a D13 fixed axis, changing it resets the count |
| `operator` | input | login @-mentioned when a run escalates |
| `ledger-issue`, `ledger-smoke-issue` | input | `owner/repo#N` of the N-run gate tracking issue, and of the checkpoint issue whose open state marks rows `smoke`; empty `ledger-issue` writes no row (a warning only) |
| `class2-afk` | input, boolean, default false | whether `afk:2-plan` issues run unattended |
| `CLAUDE_CODE_OAUTH_TOKEN`, `AGENT_DISPATCH_PAT` | secrets | worker auth; the bot's PAT |

`lane-watch.yml` takes `bot-login`, `operator`, `watched-checks` (comma-separated check names,
required) and `AGENT_DISPATCH_PAT`. `lane-close.yml` takes `bot-login`, `ledger-issue` and
`AGENT_DISPATCH_PAT`. The `risk-tier` action takes `bot-login`.

Never `secrets: inherit`: it hands the host's whole secret store to the pinned callee. A guard
test in jarvis (`tests/ci/test_lane_distribution_guard.py`) fails on it in jarvis's own callers.

## Enablement order (D16)

Do the steps in this order. A caller that goes live before its labels and `risk-tier` exist runs
without the hold, and open PRs sit on a stale required-check set.

1. **Labels.** Create `agent:dispatch`, `afk:1-auto`, `afk:2-plan`, `afk:3-human` and
   `needs-human` (`gh label create <name> --description "…"`). `needs-human` is what an
   escalation applies.
2. **Bot invited, secrets set.** Invite the lane bot to the repo with write access (this is the
   access boundary: a caller in a repo the bot cannot reach cannot run). Set `AGENT_DISPATCH_PAT`
   (the bot's PAT) and `CLAUDE_CODE_OAUTH_TOKEN` as repository secrets. Set the `LANE_OPERATOR`,
   `LANE_LEDGER_ISSUE` and `LANE_LEDGER_SMOKE_ISSUE` repository variables if the callers read
   them.
3. **`risk-tier` required, open PRs re-synced.**
   1. Add `config/protected-paths.json` with an entry keyed by the repo's `owner/repo` (format:
      `docs/reference/github-repo-setup.md` § 4). Include `.github/**` in the `machinery`
      bucket. **A missing file, or a file with no entry for the repo, makes every diff HIGH**:
      fail-closed and visible, with the reason naming this doc.
   2. Merge the `risk-tier` caller job (below) so the check exists.
   3. Add `risk-tier` to the required status checks of the default branch.
   4. Re-sync open PRs (push, or edit the body) so they report the new required check.
4. **Push protection and auto-merge.** Where the host has no `gitleaks`, enable secret-scanning
   push protection in its place (free on a public repo). Enable `allow_auto_merge`.
   Private repos on the Free plan have no auto-merge: the lane's `gh pr merge --auto` is
   rejected there and the final merge is manual.
5. **Callers last.** Merge the three lane callers. Until this step nothing in the host reacts to
   `agent:dispatch`.

## Caller templates

Replace `<sha>` with a jarvis commit that is already on its default branch, and use the same SHA
in every file. Set the bot login, email, model and watched checks for the host.

`.github/workflows/agent-dispatch.yml`:

```yaml
name: Agent Dispatch
on:
  issues:
    types: [labeled]
jobs:
  lane:
    permissions:
      contents: read
      issues: write
      pull-requests: read
    uses: Osasuwu/jarvis/.github/workflows/lane.yml@<sha>
    with:
      bot-login: <bot login>
      bot-email: <bot id>+<bot login>@users.noreply.github.com
      model: <model id>
      operator: ${{ vars.LANE_OPERATOR }}
      ledger-issue: ${{ vars.LANE_LEDGER_ISSUE }}
      ledger-smoke-issue: ${{ vars.LANE_LEDGER_SMOKE_ISSUE }}
    secrets:
      CLAUDE_CODE_OAUTH_TOKEN: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}
      AGENT_DISPATCH_PAT: ${{ secrets.AGENT_DISPATCH_PAT }}
```

`.github/workflows/lane-red-check-watcher.yml`:

```yaml
name: Lane Red Check Watcher
on:
  workflow_run:
    workflows: [<names of the workflows that own the watched checks>]
    types: [completed]
jobs:
  watch:
    permissions:
      contents: read
    uses: Osasuwu/jarvis/.github/workflows/lane-watch.yml@<sha>
    with:
      bot-login: <bot login>
      operator: ${{ vars.LANE_OPERATOR }}
      watched-checks: <the host's required checks, comma-separated, less risk-tier and any deliberate hold>
    secrets:
      AGENT_DISPATCH_PAT: ${{ secrets.AGENT_DISPATCH_PAT }}
```

`.github/workflows/lane-ledger-close.yml`:

```yaml
name: Lane Ledger Close
on:
  pull_request_target:
    types: [closed]
jobs:
  finalise:
    permissions:
      contents: read
    uses: Osasuwu/jarvis/.github/workflows/lane-close.yml@<sha>
    with:
      bot-login: <bot login>
      ledger-issue: ${{ vars.LANE_LEDGER_ISSUE }}
    secrets:
      AGENT_DISPATCH_PAT: ${{ secrets.AGENT_DISPATCH_PAT }}
```

The `risk-tier` job, inside a workflow triggered on `pull_request` (opened, edited, reopened,
synchronize) and `pull_request_review` (submitted, dismissed). Keep the job id `risk-tier` and
no `name:`, so the check context stays `risk-tier`:

```yaml
jobs:
  risk-tier:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    permissions:
      contents: read
      pull-requests: read
    steps:
      - uses: Osasuwu/jarvis/.github/actions/risk-tier@<sha>
        with:
          bot-login: <bot login>
```

Declare no `concurrency` in a lane caller, at workflow or job level: the group belongs to
`lane.yml` (cap 1 per host repo, `queue: max`, `cancel-in-progress: false`), and a caller group
equal to the callee's deadlocks the run. A `risk-tier` workflow may keep its own per-PR group;
it is a different workflow.

## Bumping the pin

1. Pick the jarvis commit (on its default branch) with the lane change you want.
2. Replace `<sha>` in every caller file in one PR, in the host.
3. That PR is a `.github/**` change, so it is HIGH and waits for a human approval on its head SHA
   (below).

Changing the `model` input or the action version resets the N-run gate count (D13). A lane fix
does not.

## Residual: a PR that edits its own pin

`risk-tier` runs the classifier from the pinned commit, and reads protected paths from the host's
base commit. The workflow file that defines the check is, however, the one in the PR being
judged: a PR that rewrites the `risk-tier` job's pin runs the new pin on itself. The defence is
the host's protected list: keep `.github/**` in the `machinery` bucket (step 3.1) so such a PR
is HIGH by path, and a HIGH PR stays red until an admin human approves the head SHA.
