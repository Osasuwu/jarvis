---
topic: code-gate-evidence-mechanics
tags: [area:ci, research]
source_provenance: /research invocation (parent agent, implement-1964 worktree)
status: open
audit: 2026-10-06 — 81 claims: 66 SUPPORTED, 15 PARTIAL, 0 UNSUPPORTED, 0 UNCHECKABLE
---

# Can a required check on a public user-owned repo be decided by default-branch code?

## Question

As asked:

> Can a GitHub Actions required status check on a public, user-owned (not org) repository be produced by a workflow that executes from the default branch — triggered via `workflow_run` (after a `pull_request` workflow completes) or via `pull_request_target` — so that a pull request cannot alter the code that decides the check's result; and how does that interact with app_id-bound required checks, fork PRs, and Dependabot PRs?

Context given by the caller: the gate reads only PR issue comments (a `claude[bot]` review carrying a JSON marker with the reviewed SHA) plus a deterministic changed-files classification, and writes one pass/fail. The repo is public and user-owned, so org-level "required workflows" rulesets are out of scope.

Sub-questions:

1. **Attribution to the PR head SHA.** Does a status or check run posted with `GITHUB_TOKEN` from `workflow_run` / `pull_request_target` onto the PR head SHA count for branch protection? Does the job's auto-created check run attach to the PR head or to the default-branch SHA? Gotchas (strict mode, re-runs).
2. **app_id binding.** Does a `GITHUB_TOKEN` commit status satisfy a check bound to app 15368? Does a Checks-API check run created with `GITHUB_TOKEN` carry 15368? What does binding protect against?
3. **Forks and Dependabot.** Which of the triggers run, with what token and secrets? Does a `workflow_run` downstream of a fork PR get write access and secrets? What does the pwn-request guidance say?
4. **Dependabot + OIDC for claude-code-action.** What do the GitHub docs and the claude-code-action docs say?

## Summary

**`pull_request_target`: yes.** It runs the workflow file from the default branch [C5] [C42], its job check run attaches to the PR head commit (measured on a fork PR [C12]), and it is one of the six events whose job checks are evaluated for a pull request [C7]. It runs for fork PRs regardless of approval settings [C59] and with write token and secrets [C40] [C41]; GitHub Security Lab calls it generally safe when PR content is treated as passive data [C62] [C63] — the gate as described (comments + changed-file list, no checkout of PR code) fits that pattern, with script injection through PR-controlled strings as the residual risk [C67].

**`workflow_run`: the job's own check cannot be the required check.** Its run and check suite attach to the default-branch commit [C1] [C11], and `workflow_run` is not in the list of events whose job checks count [C7] [C8]. To use `workflow_run`, the job has to post its own evidence onto the PR head SHA — a commit status or an API check run. None of the cited docs says whether such a status/check counts [C17]; the docs only say required checks may be checks or statuses [C13] and that the job-event restriction does not cover external apps [C9].

**app_id binding (15368).** An API check run created with the default `GITHUB_TOKEN` carries app 15368 (measured [C35]). Whether a commit status posted with `GITHUB_TOKEN` satisfies a 15368 binding is not settled by the cited docs [C36]. Binding blocks statuses from other people and integrations [C30] [C31], but a 15368 binding alone cannot tell the gate's job apart from other GitHub Actions jobs in the same repo [C14] [C37]. In jarvis today `code-gate` is bound to `null` (any source) [C38].

**Forks/Dependabot.** Fork and Dependabot `pull_request` runs get a read-only token and no Actions secrets [C39] [C44] [C49]; `pull_request_target` and `workflow_run` get write tokens and secrets [C2] [C40] [C46], except Dependabot `pull_request_target` on a Dependabot-created base ref [C54]. The current dotcom docs do not state what token a `workflow_run` downstream of a Dependabot PR gets.

**claude-code-action on Dependabot PRs.** The cited GitHub docs do not settle whether `id-token: write` works for Dependabot-triggered runs [C72]; one community run log shows OIDC succeeding and the action then refusing the `dependabot` actor [C77] because bots are refused unless `allowed_bots` lists them [C74] [C75]. GitHub's own docs conflict on whether Dependabot runs get any secrets [C51] [C68].

The report is `open`: Q2's central question (does a `GITHUB_TOKEN` status count for a 15368-bound check) and whether a `workflow_run`-posted status/check counts at all have no documentary answer; a 15-minute experiment (under Open questions) would settle both.

## Findings

### Q1 — Attribution to the PR head SHA — answered with a gap

- **C1** [quoted] For `workflow_run`, `GITHUB_SHA` is the last commit on the default branch, not the PR head. — "Last commit on default branch" — [S1], `workflow_run` event table
- **C2** [quoted] A `workflow_run` workflow gets secrets and write tokens even when the triggering workflow did not. — "The workflow started by the `workflow_run` event is able to access secrets and write tokens, even if the previous workflow was not." — [S1], `workflow_run`
- **C3** [quoted] Re-running a workflow does not re-fire `workflow_run` for the requested activity type. — "The requested activity type does not occur when a workflow is re-run." — [S1], `workflow_run`
- **C4** [quoted] `workflow_run` fires whatever the upstream conclusion was. — "A workflow run is triggered regardless of the conclusion of the previous workflow." — [S1], `workflow_run`
- **C5** [quoted] `pull_request_target` runs in the default-branch context of the base repo, not the merge commit. — "This event runs in the context of the default branch of the base repository, rather than in the context of the merge commit, as the `pull_request` event does." — [S1], `pull_request_target`
- **C6** [quoted] By default `pull_request_target` fires only on opened, synchronize, reopened. — "By default, a workflow only runs when a `pull_request_target` event's activity type is `opened`, `synchronize`, or `reopened`." — [S1], `pull_request_target`
- **C7** [quoted] Only job checks from workflow runs triggered by six events are evaluated for a PR's required checks; `workflow_run` is not among them, `pull_request_target` is. — "For checks created by workflow jobs to be evaluated for a pull request, the workflow run must be triggered by one of these events: push pull_request pull_request_review pull_request_target deployment deployment_status" — [S2], "Checks from some workflow jobs are not evaluated"
- **C8** [quoted] A job check from an ineligible event does not satisfy a required status check in a branch ruleset even when it passes on the head commit (the quote names rulesets; classic branch protection is not mentioned). — "Even if the checks pass for the head commit, they do not satisfy a required status check in a branch ruleset." — [S2], "Checks from some workflow jobs are not evaluated"
- **C9** [quoted] That restriction covers checks created by workflow jobs only, not checks created by an external GitHub App. — "This restriction applies only to checks created by workflow jobs, not to checks created by an external GitHub App." — [S2], "Checks from some workflow jobs are not evaluated"
- **C10** [inference] A `workflow_run` job's own auto-created check cannot serve as the required context for a PR; a `pull_request_target` job's check can. — from [C1], [C7], [C11], [C12]
- **C11** [measured] One `workflow_run` run's check suite sat on a default-branch commit (NixOS/nixpkgs run 36608172959: suite `head_sha` 4f21089…, `head_branch=master`; that SHA is an ancestor of `master`); the measurement does not record which upstream run or PR triggered it. — see M5
- **C12** [measured] A `pull_request_target` run's check suite and check run attach to the PR head commit, including for a fork PR (python/cpython run 25066296099: suite `head_sha` 77e73c2…, `head_branch=warsaw/829`; 77e73c2 is in PR #149109's commit list and diverged from `main`). — see M6
- **C13** [quoted] Required status checks can be satisfied by either check runs or commit statuses. — "Required status checks can be checks or commit statuses." — [S3], "Require status checks before merging"
- **C14** [quoted] `GITHUB_TOKEN` is an installation token of the GitHub App that GitHub installs when Actions is enabled. — "When you enable GitHub Actions, GitHub installs a GitHub App on your repository. The `GITHUB_TOKEN` secret is a GitHub App installation access token." — [S5], "About the GITHUB_TOKEN"
- **C15** [quoted] Anyone with push access can create a commit status for any SHA. — "Users with push access in a repository can create commit statuses for a given SHA." — [S6], "Create a commit status"
- **C16** [quoted] Only GitHub Apps can create check runs through the REST API. — "Write permission for the REST API to interact with checks is only available to GitHub Apps. OAuth apps and authenticated users can view check runs and check suites, but they are not able to create them." — [S7], "About check runs"
- **C17** [inference] A commit status that a `workflow_run` job POSTs onto the PR head SHA is not a check, so the wording of the "checks created by workflow jobs" restriction does not cover it; whether an API check run created from inside a workflow job falls under that restriction is ambiguous in the wording. None of the cited docs confirms or excludes either one counting. — from [C7], [C9], [C13], [C15]
- **C18** [quoted] Required checks are evaluated on the latest commit only; checks on earlier commits do not count. — "Required checks must pass on the latest commit SHA. Checks from earlier commits don't satisfy the requirement." — [S2], "Required checks are not passing"
- **C19** [quoted] A required check that was never reported blocks the PR with a waiting message. — "If `build` is required, the pull request is blocked with "Waiting for status to be reported."" — [S2]
- **C20** [quoted] When a check run and a commit status share a required name, both must pass. — "If a check and a commit status have the same name, both must pass when that name is required." — [S2]
- **C21** [quoted] A context can only be selected as required if it completed successfully in the repo in the past seven days. — "A required status check must have completed successfully in the chosen repository during the past seven days." — [S2]
- **C22** [quoted] Duplicate job names across workflows make required-check results ambiguous. — "make sure that job names are unique across all workflows. Using the same job name in multiple workflows can cause ambiguous status check results and block pull requests from being merged." — [S3], tip at top of page
- **C23** [quoted] Actions workflows produce check runs, not commit statuses. — "GitHub Actions generates checks, not commit statuses, when workflows are run." — [S8], "Types of status checks on GitHub"
- **C24** [quoted] Community pattern (corroboration only): a separate workflow listening to the CI workflow and posting a commit status. — "have an independent GitHub workflow which listen to the CI workflow (success AND failure), and set a status accordingly" — [S33]
- **C25** [quoted] Repo-local finding: a `workflow_dispatch` check run does attach to the PR head SHA (yet, per [C7]/[C8], an ineligible event's job check does not count — attachment and eligibility are separate). — "a workflow_dispatch check-run DOES attach" — [S34], `code-review.yml` lines 451–452
- **C26** [quoted] Repo-local finding: a stale failing check run next to a later successful one of the same name kept the PR blocked. — "success left `mergeStateStatus` BLOCKED with no self-heal" — [S34], `code-review.yml` line 457
- **C27** [measured] jarvis `main` protection has `strict: true`; with [C18], every new head commit on a PR needs its own passing result. — see M3

### Q2 — app_id binding — open

- **C28** [quoted] The REST `checks[].app_id` field names the app that must provide the check; omitted means "recent provider", `-1` means any app. — "The ID of the GitHub App that must provide this check. Omit this field to automatically select the GitHub App that has recently provided this check, or any app if it was not set by a GitHub App. Pass -1 to explicitly allow any app to set the status." — [S9], "Update branch protection" body parameters
- **C29** [quoted] Binding exists because any writer can set any status. — "Any person or integration with write permissions to a repository can set the state of any status check in the repository" — [S3], "Require status checks before merging"
- **C30** [quoted] With an expected source selected, a status set by any other person or integration blocks merging. — "If the status is set by any other person or integration, merging won't be allowed." — [S3], "Require status checks before merging"
- **C31** [quoted] Binding blocks a different app or a user-posted commit status. — "If status is then provided by a different app or by a user via a commit status, merging will be prevented." — [S10]
- **C32** [quoted] New required checks default to the most recent reporting app. — "Newly-added required status checks will default to the app that most recently reported the status, but you can choose a different app or allow any app to provide the status." — [S10]
- **C33** [quoted] A mismatched source produces a specific error. — "was not set by the expected GitHub App" — [S2]
- **C34** [quoted] `GITHUB_TOKEN` authenticates as the Actions GitHub App installed on the repo. — "You can use the installation access token to authenticate on behalf of the GitHub App installed on your repository." — [S5]
- **C35** [measured] A check run created through the Checks API with the default `github.token` carries app 15368 (`github-actions`) and sits in a different app-15368 check suite from the "Deploy to GitHub" job check (EnricoMi/publish-unit-test-result-action `master`, "Test Results (…)" runs with `details_url` `/runs/<id>` rather than `/actions/runs/…/job/…`). — see M8
- **C36** [inference] [C14] says `GITHUB_TOKEN` is an app installation token, and [C31] groups commit statuses with users ("by a user via a commit status"); neither says how a commit status posted with `GITHUB_TOKEN` is attributed, so the cited docs do not settle whether it meets a 15368 binding. — from [C14], [C31]
- **C37** [inference] Binding to 15368 keeps out statuses from other people and integrations, but `GITHUB_TOKEN` is the Actions app's token and checks it creates carry 15368, so a 15368 binding alone does not distinguish the gate's job from other Actions jobs in the repo; same-named jobs give ambiguous results. — from [C14], [C22], [C29], [C30], [C35]
- **C38** [measured] In jarvis, `code-gate` and `gitleaks` are bound to `app_id: null`; `pytest`, `require-linked-issue`, `waiting-human-review` are bound to 15368; all five are delivered as app-15368 check runs and no commit statuses exist on the measured head. — see M3, M4

### Q3 — Forks and Dependabot — answered with a gap

- **C39** [quoted] For workflows triggered from a fork, only `GITHUB_TOKEN` — no other secret — reaches the runner, and that token is read-only in fork PRs. — "With the exception of `GITHUB_TOKEN`, secrets are not passed to the runner when a workflow is triggered from a forked repository. The `GITHUB_TOKEN` has read-only permissions in pull requests from forked repositories." — [S1], `pull_request`
- **C40** [quoted] `pull_request_target` runs have write permission and the target repo's secrets; `pull_request` from forks does not. — "Workflows triggered via `pull_request_target` have write permission to the target repository. They also have access to target repository secrets. The same is true for workflows triggered on `pull_request` from a branch in the same repository, but not from external forks." — [S12]
- **C41** [quoted] GitHub's 2025 changelog restates that `pull_request_target` runs on user-supplied PRs with secrets. — "`pull_request_target` events execute based on user-supplied pull requests, which can come from external forks, and are executed with access to action secrets." — [S11]
- **C42** [quoted] Since 8 Dec 2025 the `pull_request_target` workflow file and checkout commit always come from the default branch. — "The workflow file and checkout commit will always be taken from the repository's default branch, regardless of the pull request's base branch." — [S11]
- **C43** [quoted] The 2025 change took effect on 8 December 2025. — "These changes will take effect on 12/8/2025." — [S11]
- **C44** [quoted] Dependabot PR runs are treated like fork runs. — "Workflows triggered by Dependabot pull requests are treated as though they are from a forked repository, and are also subject to these restrictions." — [S1], `pull_request`
- **C45** [quoted] `pull_request_target` is meant for labelling/commenting on fork PRs, not for building PR code. — "This event allows your workflow to do things like label or comment on pull requests from forks. Avoid using this event if you need to build or run code from the pull request." — [S1], `pull_request_target`
- **C46** [quoted] Security Lab describes the downstream `workflow_run` as privileged even when the upstream was a fork PR. — "The following workflow then starts on `workflow_run` where it is granted write permission to the target repository and access to repository secrets" — [S12]
- **C47** [quoted] A `workflow_run` file must exist on the default branch to trigger. — "This event will only trigger a workflow run if the workflow file exists on the default branch." — [S1], `workflow_run`
- **C48** [quoted] The `workflow_run` context does not contain the PR number. — "The `workflow_run` context is different from the `pull_request` context and it doesn't contain, for example, the PR number." — [S12]
- **C49** [quoted] Dependabot-triggered runs get a read-only `GITHUB_TOKEN` and none of the secrets normally available. — "Unlike workflows triggered by other actors, this means they receive a read-only `GITHUB_TOKEN` and do not have access to any secrets that are normally available." — [S13], "Dependabot fails to trigger workflows / access secrets"
- **C50** [quoted] The documented workaround is a two-step process with `pull_request_target`. — "You can modify your workflows to use a two-step process that includes `pull_request_target` which does not have these limitations." — [S13]
- **C51** [quoted] Dependabot-triggered runs see only Dependabot secrets. — "When a Dependabot event triggers a workflow, the only secrets available to the workflow are Dependabot secrets. GitHub Actions secrets are not available." — [S13]
- **C52** [quoted] The read-only default for Dependabot runs can be raised with `permissions`. — "By default, GitHub Actions workflows triggered by Dependabot get a `GITHUB_TOKEN` with read-only permissions. You can use the `permissions` key in your workflow to increase the access for the token" — [S13]
- **C53** [quoted] The 2021 changelog introduced the fork treatment for Dependabot and pointed at `pull_request_target` for write/secrets. — "If your workflow needs to have a write token or access to secrets, you can use the `pull_request_target` event" — [S14]
- **C54** [quoted] Dependabot `pull_request_target` runs whose base ref Dependabot created get read-only and no secrets. — "GitHub Actions workflows triggered by Dependabot for the `pull_request_target` event on pull requests where the base ref was created by Dependabot will always receive a read-only token and no secrets." — [S15]
- **C55** [quoted] A legacy (GHES 3.3) doc lists a `workflow_run` "trusted" workflow downstream of Dependabot as having secrets and a read-write token. — "access to secrets and a read-write token" — [S22]
- **C56** [quoted] Fork PR runs may need maintainer approval. — "Workflow runs triggered by a contributor's pull request from a fork may require manual approval from a maintainer with write access." — [S16]
- **C57** [quoted] Unapproved runs expire after 30 days as failed. — "Workflow runs that have been awaiting approval for more than 30 days expire and are marked as failed." — [S16]
- **C58** [quoted] Approval for first-time contributors is the default. — "By default, all first-time contributors require approval to run workflows." — [S17]
- **C59** [quoted] Approval does not gate `pull_request_target`. — "Workflows triggered by `pull_request_target` events are run in the context of the base branch. Since the base branch is considered trusted, workflows triggered by these events will always run, regardless of approval settings." — [S17]
- **C60** [inference] A `pull_request_target` gate runs for fork PRs regardless of approval settings; a `workflow_run` gate on `completed` cannot fire before its upstream run completes, so it posts nothing while that run awaits approval. Whether the 30-day expiry (marked failed) fires it is not stated in the cited docs. — from [C4], [C56], [C57], [C59]
- **C61** [quoted] Security Lab: `pull_request_target` plus checkout of untrusted PR code is dangerous. — "Combining `pull_request_target` workflow trigger with an explicit checkout of an untrusted PR is a dangerous practice that may lead to repository compromise." — [S12]
- **C62** [quoted] Generally speaking, treating PR content as passive data — not in a position of influence over the build/testing process — is safe. — "Generally speaking, when the PR contents are treated as passive data, i.e. not in a position of influence over the build/testing process, it is safe." — [S12]
- **C63** [quoted] Comment-only workflows are the sanctioned `pull_request_target` use. — "If your workflow scenario simply requires commenting on the PR, but does not require a check out of the modified code, using `pull_request_target` is a logical shortcut." — [S12]
- **C64** [quoted] Artifacts produced from untrusted PR data stay untrusted in the privileged workflow. — "Artifacts resulting from untrusted PR data are themselves untrusted and should be treated as such when handled in privileged contexts." — [S12]
- **C65** [quoted] GitHub's secure-use reference prefers `workflow_run` for privilege separation. — "Avoid using the `pull_request_target` workflow trigger if it's not necessary. For privilege separation between workflows, `workflow_run` is a better trigger." — [S18]
- **C66** [quoted] The 2025 changelog advises `pull_request` when no elevated permissions are needed. — "If your workflow does not require elevated permissions or access to secrets, use `pull_request` instead." — [S11]
- **C67** [quoted] PR-controlled context fields (titles, bodies, branch names) are script-injection vectors. — "These contexts typically end with `body`, `default_branch`, `email`, `head_ref`, `label`, `message`, `name`" — [S19], "Understanding the risk of script injections"

### Q4 — Dependabot + OIDC for claude-code-action — answered with a gap

- **C68** [quoted] The workflow-syntax reference says Dependabot PR runs cannot access any secrets — contradicting [C51]. — "Workflow runs triggered by Dependabot pull requests run as if they are from a forked repository, and therefore use a read-only `GITHUB_TOKEN`. These workflow runs cannot access any secrets." — [S20], `permissions`
- **C69** [quoted] For fork PR events other than `pull_request_target`, write permissions are downgraded to read unless "Send write tokens" is enabled. — "if the workflow was triggered by a pull request event other than `pull_request_target` from a forked repository, and the **Send write tokens to workflows from pull requests** setting is not selected, the permissions are adjusted to change any write permissions to read only." — [S20], `permissions`
- **C70** [quoted] Fetching an OIDC token requires `id-token: write`. — "Fetch an OpenID Connect (OIDC) token. This requires `id-token: write`." — [S20], `permissions`
- **C71** [quoted] claude-code-action fails with an explicit message when no OIDC token is obtainable. — "Could not fetch an OIDC token. Did you remember to add `id-token: write` to your workflow permissions?" — [S26]
- **C72** [inference] [C52] says the read-only default for Dependabot runs can be raised with `permissions`, while [C69] says write permissions are downgraded to read on fork PR events other than `pull_request_target` (and Dependabot runs are treated as forks [C44]); neither names `id-token`, so the cited docs do not settle whether `id-token: write` is granted to Dependabot-triggered `pull_request` runs. — from [C44], [C52], [C69], [C70]
- **C73** [quoted] Without OIDC, the action can run on a caller-supplied `github_token`. — "The OIDC token is required in order for the Claude GitHub app to function. If you wish to not use the GitHub app, you can instead provide a `github_token` input to the action for Claude to operate with." — [S27]
- **C74** [quoted] The action refuses bot actors unless `allowed_bots` lists them. — "Comma-separated list of allowed bot usernames, or '*' to allow all bots. Empty string (default) allows no bots." — [S23], `allowed_bots`
- **C75** [quoted] The refusal message names the bot and points at `allowed_bots`. — "Add bot to allowed_bots list or use '*' to allow all bots." — [S24]
- **C76** [quoted] Allowed bots skip the repository-permission check. — "Allowed bots are not checked for repository permissions." — [S25]
- **C77** [quoted] Community run log (corroboration only): a same-repo Dependabot `pull_request` run obtained an OIDC token and the app token, then failed on the bot-actor check. — "Workflow initiated by non-human actor: dependabot (type: Bot)." — [S30], [S31]
- **C78** [quoted] The action's own security doc warns that `pull_request_target` and `workflow_run` carry base-repo secrets. — "`pull_request_target` and `workflow_run` execute with the **base repository's secrets**." — [S25]
- **C79** [quoted] Upstream issue (community): a Dependabot-triggered `pull_request` run failed for lack of the Anthropic credential; the reporter points to Dependabot secrets as the remedy. — "Either ANTHROPIC_API_KEY or CLAUDE_CODE_OAUTH_TOKEN is required when using direct Anthropic API." — [S35]
- **C80** [quoted] Upstream issue (community, open): the OIDC exchange rejected a `pull_request_target` run. — "Error: Failed to setup GitHub token: Error: Invalid OIDC token" — [S36]
- **C81** [quoted] One community report: on fork `pull_request` runs of one repo, no OIDC request URL was present despite `id-token: write`. — "Unable to get ACTIONS_ID_TOKEN_REQUEST_URL env variable" — [S30]

## Disconfirming evidence

- **Against [C7]/[C10] (job checks of `workflow_run` cannot count).** Searched "workflow_run check run not showing on pull request default branch commit required status check" and code search for `workflow_run` + commit-status publishers. Found nothing claiming a `workflow_run` job's own check satisfies a PR's required check. The repo-local finding [C25] that a `workflow_dispatch` check run attaches to the PR head is consistent with [C8]: attaching is not counting.
- **Against [C17] (a POSTed status from `workflow_run` is unconfirmed).** Searched `commit status created by GITHUB_TOKEN "expected source" GitHub Actions required status check workflow_run` and `"workflow_run" "commit status" required check pull request head sha branch protection satisfied github discussion`. Results were doc restatements and community discussion 65321 (PRs created by `GITHUB_TOKEN` not triggering workflows — unrelated). Code search found EvaristeGalois11/sonar-fork-analysis (commit d574548d), which posts a `workflow_run` status for fork PRs and warns that requiring it "would block them forever" for same-repo PRs that never receive it — an operational warning, neither confirming nor refuting that the status counts. The community pattern [C24] implies it works but is one practitioner post.
- **Against [C36] (GITHUB_TOKEN status vs 15368).** Searched for evidence either way; nothing. Community discussion 181487 concerns review requirements and is unrelated.
- **Against [C35] (API check runs carry 15368).** First probe on dorny/test-reporter was non-evidence: its `workflow_run` report workflow has only `contents: read, actions: read`, and no "Workflow Report" check run exists on the commit (M7). The EnricoMi probe (M8) is the positive case.
- **Against [C51] vs [C68].** GitHub's own pages conflict: the Dependabot troubleshooting page says Dependabot secrets are available [C51]; the workflow-syntax reference says "cannot access any secrets" [C68]. Unresolved; the community issue [C79] (reporter points to Dependabot secrets as the remedy) sides with [C51].
- **Against [C77].** Searched for reports of same-repo Dependabot runs being denied OIDC; found none. One community report says fork `pull_request` runs lacked OIDC [C81].
- **Against [C42].** The older Security Lab note that PRs opened before a fix keep running the old workflow is superseded by [C42] for `pull_request_target`.

## Coverage

| Channel | Searched | Found |
|---|---|---|
| Users (practitioners, community) | WebSearch for `workflow_run` status patterns, GitHub code search for status-posting `workflow_run` workflows, claude-code-action issues | dev.to Doctolib post [S33]; sonar-fork-analysis README; MacTorn run log/issue [S30][S31]; claude-code-action #744, #713 [S35][S36] |
| Specialists (vendor docs, security research) | docs.github.com (events, troubleshooting required checks, protected branches, rulesets, REST statuses/checks/branch protection, GITHUB_TOKEN, secure-use, script injections, Dependabot, approvals), GitHub changelog, GitHub Security Lab, claude-code-action repo at 86d88e6 | [S1]–[S22], [S23]–[S29] |
| Data (live measurement) | `gh api` against jarvis, NixOS/nixpkgs, python/cpython, dorny/test-reporter, EnricoMi/publish-unit-test-result-action | M1–M8 |
| Adversarial | One disconfirming search per load-bearing claim (see above), plus a search for status/app-binding counter-reports | No contradiction to [C7], [C12], [C35]; a doc-vs-doc conflict on Dependabot secrets |

Tool notes: Firecrawl returned HTTP 402 (out of credits) on every call, so the documented fallback was used — WebSearch for discovery, `curl` against the docs.github.com article-body API (`https://docs.github.com/api/article/body?pathname=/en/...`) for page text, `gh api` for GitHub content and measurements. Every sub-question overran the skill's budget: Q1 about 8 searches and 9 reads; Q2 4 searches and 7 page reads; Q3 5 searches and about 15 reads; Q4 about 7 repo-file reads, 3 docs pages and 6 community pages; plus about 12 author-side `gh` probes for M1–M8. Not read: Security Lab pwn-request parts 2–4; GHES-version history of the Dependabot re-run wording.

## Own measurements

### M1 — jarvis `main` check runs and their app

Command: `gh api repos/Osasuwu/jarvis/commits/main/check-runs --jq '.check_runs[] | "\(.name) app=\(.app.id) \(.app.slug)"'`

Output:
```
sync (1957, close) app=15368 github-actions
sync (1960, promote) app=15368 github-actions
sweep app=15368 github-actions
sync app=15368 github-actions
resolve app=15368 github-actions
sweep app=15368 github-actions
resolve app=15368 github-actions
lockfile-check app=15368 github-actions
pytest app=15368 github-actions
```

### M2 — jarvis `main` commit statuses

Command: `gh api repos/Osasuwu/jarvis/commits/main/status --jq '"state=\(.state) total_count=\(.total_count) statuses=\(.statuses|length)"'`

Output:
```
state=pending total_count=0 statuses=0
```

### M3 — jarvis `main` required status checks

Command: `gh api repos/Osasuwu/jarvis/branches/main/protection/required_status_checks --jq '{strict,contexts,checks}'`

Output (whitespace removed):
```
{"checks":[{"app_id":15368,"context":"require-linked-issue"},{"app_id":15368,"context":"pytest"},{"app_id":null,"context":"code-gate"},{"app_id":null,"context":"gitleaks"},{"app_id":15368,"context":"waiting-human-review"}],"contexts":["require-linked-issue","pytest","code-gate","gitleaks","waiting-human-review"],"strict":true}
```

### M4 — required contexts on the latest merged PR head (jarvis #1974, d1130634f49fb513e34b19cbc56a342d7f74c71d)

Command: `gh api "repos/Osasuwu/jarvis/commits/<sha>/check-runs?per_page=100" --jq '... select(.name|test("^(code-gate|pytest|gitleaks|require-linked-issue|waiting-human-review)$")) | "\(.name) app=\(.app.id) \(.conclusion)"' | sort | uniq` and `gh api repos/Osasuwu/jarvis/commits/<sha>/status --jq '"statuses total_count=\(.total_count)"'`

Output:
```
code-gate app=15368 success
gitleaks app=15368 success
pytest app=15368 success
require-linked-issue app=15368 success
waiting-human-review app=15368 success
statuses total_count=0
```

### M5 — `workflow_run` check suite location (NixOS/nixpkgs run 36608172959)

Commands: `gh api repos/NixOS/nixpkgs/actions/runs/36608172959`, `gh api repos/NixOS/nixpkgs/check-suites/99138492839`, `gh api repos/NixOS/nixpkgs/compare/4f2108965fc9dee4f1b34d6c97a61d2519e94ce0...master`

Output:
```
run event=workflow_run head_branch=master head_sha=4f2108965fc9dee4f1b34d6c97a61d2519e94ce0 created=2026-09-29T17:53:46Z
suite head_sha=4f2108965fc9dee4f1b34d6c97a61d2519e94ce0 head_branch=master app=github-actions
compare: status=ahead behind_by=0 ahead_by=4077
```

### M6 — `pull_request_target` check suite location on a fork PR (python/cpython run 25066296099)

Commands: `gh api repos/python/cpython/actions/runs/25066296099`, `gh api repos/python/cpython/check-suites/66570635197`, `gh api repos/python/cpython/pulls/149109`, `gh api repos/python/cpython/pulls/149109/commits` (grep for 77e73c2), `gh api repos/python/cpython/compare/main...77e73c243552aa2961c53e544e4159ea14edffc9`, check runs of the suite

Output:
```
run event=pull_request_target head_branch=warsaw/829 head_sha=77e73c243552aa2961c53e544e4159ea14edffc9 created=2026-04-28T16:55:04Z prs=[]
suite head_sha=77e73c243552aa2961c53e544e4159ea14edffc9 head_branch=warsaw/829 app=github-actions
pr head=50191318e59e... head_ref=warsaw/829 head_repo=warsaw/cpython
PR commits containing 77e73c2: 1
compare main...77e73c2: status=diverged ahead_by=23 behind_by=2399
check run: documentation-links head_sha=77e73c243552aa2961c53e544e4159ea14edffc9
```
(The PR head has moved on since; 77e73c2 was a PR-head commit at run time.)

### M7 — dorny/test-reporter `workflow_run` report (non-evidence)

Commands: read `.github/workflows/test-report.yml`; `gh api "repos/dorny/test-reporter/commits/3d49bf4e0715e7fe48375099bd6b1058d42e673c/check-runs?check_name=Workflow%20Report&filter=all" --jq .total_count`; `gh run view 37124206207 --log` grep

Output:
```
permissions:
  contents: read
  actions: read
Check runs will be created with SHA=3d49bf4e0715e7fe48375099bd6b1058d42e673c
0
```
Every check run on that commit was app 15368, but all of them are job checks; the action had no `checks: write`, and no API-created "Workflow Report" run exists. Inconclusive for [C35].

### M8 — API-created check runs with default `github.token` (EnricoMi/publish-unit-test-result-action)

Commands: `gh api repos/EnricoMi/publish-unit-test-result-action/commits/master/check-runs` (filtered), `gh api .../check-suites/95431301109`, `gh api .../check-runs/110476319649`, `action.yml` grep for `github_token:`, `publish.yml` grep count for `github_token`

Output:
```
Deploy to GitHub | app=15368 github-actions | suite=99923685666 | details=https://github.com/EnricoMi/publish-unit-test-result-action/actions/runs/36891292542/job/110476731635
Test Results (Docker Image arm64) | app=15368 github-actions | suite=95431301109 | details=https://github.com/EnricoMi/publish-unit-test-result-action/runs/110476319649
Test Results (Linux python 3.8) | app=15368 github-actions | suite=95431301109 | details=https://github.com/EnricoMi/publish-unit-test-result-action/runs/110475360493
suite 95431301109 app=15368 head_sha=071ec54125241f64de06e2a790236c1fd8ce9dce head_branch=master created=2026-09-17T14:56:20Z
cr 110476319649 name=Test Results (Docker Image arm64) external_id= details=https://github.com/EnricoMi/publish-unit-test-result-action/runs/110476319649
action.yml:  github_token:  default: ${{ github.token }}
publish.yml github_token occurrences: 0   (jobs declare permissions: checks: write)
```
The "Test Results (…)" names are the action's `check_name` inputs, not job names (the jobs are "Publish Test Results (…)"), and their `details_url` is a bare check-run URL rather than a job URL — they are API-created, with the default token, and carry app 15368. The repo's `workflow_run` publisher (`test-results.yml`) has only `startup_failure` runs recently, so a PR-head example from `workflow_run` could not be observed.

## Open questions

- Does a commit status POSTed with `GITHUB_TOKEN` from a `workflow_run` (or `pull_request_target`) job onto the PR head SHA satisfy a required context bound to app 15368, and one bound to `null`? Settle on a throwaway public user repo: require context X, POST `/statuses/{head_sha}` from a `workflow_run` job, read the PR's `mergeStateStatus` and GraphQL `isRequired`.
- Does an API-created check run (not a job check) from a `workflow_run` job on the PR head SHA satisfy the required context, or does the "checks created by workflow jobs" event restriction [C7] apply to it as well (it is app 15368 and in an Actions-owned suite, M8)? Same experiment with `POST /check-runs`.
- What token and secrets does a `workflow_run` downstream of a Dependabot `pull_request` get on current github.com? Only a legacy GHES 3.3 page [C55] says so.
- Does `workflow_run` stay silent while an upstream fork run awaits approval, and fire on approval or 30-day expiry? [C60] is inference.
- Is `id-token: write` honoured for Dependabot-triggered `pull_request` runs in general? One community log [C77] says yes; no GitHub doc says either way.
- Which GitHub page is right about Dependabot runs and secrets — [C51] or [C68]?
- [C8]'s quote speaks of a required status check "in a branch ruleset"; jarvis uses classic branch protection. Does the job-event restriction [C7] apply identically there? Settle with the same throwaway-repo experiment under classic protection.
- Is a `workflow_run`-downstream gate fired when an approval-held fork run expires after 30 days, and with what conclusion? Settle by reading the run list of a fork PR left unapproved past expiry, or by GitHub support confirmation.

## Implications

- **Q1 (default-branch code produces a check bound to the PR head): YES for `pull_request_target`** — runs default-branch code [C5] [C42], its job check attaches to the PR head [C12], and the event is eligible [C7]. **UNCLEAR for `workflow_run`** — its own job check is ineligible and sits on the default-branch SHA [C1] [C7] [C11]; a POSTed status/check on the head SHA is undocumented [C17]. Gotchas: every new head SHA needs a fresh result under strict mode [C18] [C27]; a re-run does not produce a `workflow_run` `requested` event [C3]; a stale failing same-named run can block [C26]; duplicate names are ambiguous [C20] [C22].
- **Q2 (app_id 15368 binding): UNCLEAR** — API check runs from `GITHUB_TOKEN` carry 15368 [C35]; statuses from `GITHUB_TOKEN` are undocumented [C36]; binding blocks other people and integrations [C30] [C31] but not, on its own, other Actions jobs in the repo [C37].
- **Q3 (forks and Dependabot): YES, with gaps** — fork/Dependabot `pull_request`: read-only, no Actions secrets [C39] [C44] [C49]; `pull_request_target`: write + secrets, runs regardless of approval settings [C40] [C59], except Dependabot-created base refs [C54]; `workflow_run`: write + secrets [C2] [C46]; pwn-request guidance: checking out untrusted PR code is dangerous, PR content treated as passive data is generally safe [C61] [C62] [C63] [C64], watch script injection [C67]. Dependabot-downstream `workflow_run` and approval timing are undocumented [C55] [C60].
- **Q4 (Dependabot + OIDC for claude-code-action): UNCLEAR, leaning yes for same-repo Dependabot `pull_request`** — no GitHub doc on `id-token` for Dependabot [C72]; one log shows OIDC obtained, then the bot-actor refusal [C77] [C74] [C75]; secrets availability conflicts between GitHub pages [C51] [C68]; `pull_request_target` OIDC was rejected in one report [C80]; one report says fork `pull_request` runs got no OIDC [C81].

## Sources

- [S1] Events that trigger workflows — https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows — passage (`pull_request`, `pull_request_target`, `workflow_run` sections)
- [S2] Troubleshooting required status checks — https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/collaborating-on-repositories-with-code-quality-features/troubleshooting-required-status-checks — read in full
- [S3] About protected branches — https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches — passage (top-of-page tip; "Require status checks before merging")
- [S5] GITHUB_TOKEN — https://docs.github.com/en/actions/concepts/security/github_token — read in full
- [S6] REST API endpoints for commit statuses — https://docs.github.com/en/rest/commits/statuses — read in full
- [S7] REST API endpoints for check runs — https://docs.github.com/en/rest/checks/runs — passage
- [S8] About status checks — https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/collaborating-on-repositories-with-code-quality-features/about-status-checks — read in full
- [S9] REST API endpoints for protected branches — https://docs.github.com/en/rest/branches/branch-protection — passage (`checks[].app_id`)
- [S10] Changelog 2021-11-30: Ensure required status checks provided by the intended app — https://github.blog/changelog/2021-11-30-ensure-required-status-checks-provided-by-the-intended-app/ — read in full
- [S11] Changelog 2025-11-07: Actions pull_request_target and environment branch protections changes — https://github.blog/changelog/2025-11-07-actions-pull_request_target-and-environment-branch-protections-changes/ — read in full
- [S12] GitHub Security Lab: Keeping your GitHub Actions and workflows secure Part 1: Preventing pwn requests — https://securitylab.github.com/resources/github-actions-preventing-pwn-requests/ — read in full
- [S13] Troubleshooting Dependabot on GitHub Actions — https://docs.github.com/en/code-security/dependabot/troubleshooting-dependabot/troubleshooting-dependabot-on-github-actions — read in full
- [S14] Changelog 2021-02-18: Workflows triggered by Dependabot PRs will run with read-only permissions — https://github.blog/changelog/2021-02-18-github-actions-workflows-triggered-by-dependabot-prs-will-run-with-read-only-permissions/ — read in full
- [S15] Changelog 2021-12-09: Changes to permissions in workflows triggered by Dependabot — https://github.blog/changelog/2021-12-09-github-actions-changes-to-permissions-in-workflows-triggered-by-dependabot/ — read in full
- [S16] Approving workflow runs from forks — https://docs.github.com/en/actions/how-tos/manage-workflow-runs/approve-runs-from-forks — read in full
- [S17] Managing GitHub Actions settings for a repository — https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository — passage (fork approval)
- [S18] Secure use reference — https://docs.github.com/en/actions/reference/security/secure-use — passage
- [S19] Script injections — https://docs.github.com/en/actions/concepts/security/script-injections — read in full
- [S20] Workflow syntax for GitHub Actions — https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax — passage (`permissions`)
- [S22] Automating Dependabot with GitHub Actions (GHES 3.3, legacy) — https://docs.github.com/en/enterprise-server@3.3/code-security/supply-chain-security/keeping-your-dependencies-updated-automatically/automating-dependabot-with-github-actions — passage
- [S23] claude-code-action `action.yml` @86d88e6 — https://github.com/anthropics/claude-code-action/blob/86d88e619d8e6caf07b5c3944dd14f441c533718/action.yml — read in full
- [S24] claude-code-action `src/github/validation/actor.ts` @86d88e6 — https://github.com/anthropics/claude-code-action/blob/86d88e619d8e6caf07b5c3944dd14f441c533718/src/github/validation/actor.ts — read in full
- [S25] claude-code-action `docs/security.md` @86d88e6 — https://github.com/anthropics/claude-code-action/blob/86d88e619d8e6caf07b5c3944dd14f441c533718/docs/security.md — read in full
- [S26] claude-code-action `src/github/token.ts` @86d88e6 — https://github.com/anthropics/claude-code-action/blob/86d88e619d8e6caf07b5c3944dd14f441c533718/src/github/token.ts — read in full
- [S27] claude-code-action `docs/faq.md` @86d88e6 — https://github.com/anthropics/claude-code-action/blob/86d88e619d8e6caf07b5c3944dd14f441c533718/docs/faq.md — passage
- [S30] MacTorn issue #98 (community) — https://github.com/pawelorzech/MacTorn/issues/98 — read in full
- [S31] MacTorn Actions run 31926902344 log (community) — https://github.com/pawelorzech/MacTorn/actions/runs/31926902344 — passage (job log)
- [S33] Doctolib on dev.to: GitHub Actions — how to push a GitHub status in addition of GitHub checks (community) — https://dev.to/doctolib/github-actions-how-to-push-a-github-status-in-addition-of-github-checks-3d27 — passage (read by the auditor)
- [S34] jarvis `.github/workflows/code-review.yml` @a8f930d (repo-local) — https://github.com/Osasuwu/jarvis/blob/a8f930d6db75f13c9bd12a7c4042c453e7b0f7d9/.github/workflows/code-review.yml — passage (lines 450–462)
- [S35] claude-code-action issue #744 (community) — https://github.com/anthropics/claude-code-action/issues/744 — passage
- [S36] claude-code-action issue #713 (community) — https://github.com/anthropics/claude-code-action/issues/713 — passage

## Audit

| Claim | Verdict | Note |
|---|---|---|
| C1 | SUPPORTED |  |
| C2 | SUPPORTED |  |
| C3 | SUPPORTED |  |
| C4 | SUPPORTED |  |
| C5 | SUPPORTED |  |
| C6 | SUPPORTED |  |
| C7 | SUPPORTED | quote flattens a markdown list of the six events; words match |
| C8 | PARTIAL | quote says "in a branch ruleset"; claim narrowed to rulesets |
| C9 | SUPPORTED |  |
| C10 | SUPPORTED | follows from C7 and C12 (C11 repaired) |
| C11 | PARTIAL | M5 shows the suite on a master ancestor but not which upstream run/PR triggered it; claim narrowed to what was measured |
| C12 | SUPPORTED | M6 matches |
| C13 | SUPPORTED |  |
| C14 | SUPPORTED |  |
| C15 | SUPPORTED |  |
| C16 | SUPPORTED |  |
| C17 | PARTIAL | claim treated API check runs created inside a job as outside the "checks created by workflow jobs" wording, which is ambiguous; narrowed to commit statuses, check runs marked ambiguous |
| C18 | SUPPORTED |  |
| C19 | SUPPORTED |  |
| C20 | SUPPORTED |  |
| C21 | SUPPORTED |  |
| C22 | SUPPORTED |  |
| C23 | SUPPORTED |  |
| C24 | SUPPORTED | snippet; page read (dev.to HTML), passage present; relabelled quoted |
| C25 | SUPPORTED |  |
| C26 | SUPPORTED |  |
| C27 | PARTIAL | M3 shows strict: true only; dropped the unsourced "head changes whenever the branch is updated" step |
| C28 | SUPPORTED |  |
| C29 | SUPPORTED |  |
| C30 | SUPPORTED |  |
| C31 | SUPPORTED |  |
| C32 | SUPPORTED |  |
| C33 | SUPPORTED |  |
| C34 | SUPPORTED |  |
| C35 | PARTIAL | M8 shows the suite differs from the one Deploy job suite, not from all job-check suites; narrowed |
| C36 | PARTIAL | "is undocumented" and "leans toward" go beyond C14/C31; narrowed to what the two claims say |
| C37 | PARTIAL | the PR-added same-named workflow scenario needs a premise not in the named claims; narrowed to "other Actions jobs in the repo" |
| C38 | SUPPORTED | M3 and M4 match |
| C39 | PARTIAL | quote covers secrets and the read-only token only; "events are delivered to the base repo" dropped |
| C40 | SUPPORTED |  |
| C41 | SUPPORTED |  |
| C42 | SUPPORTED |  |
| C43 | SUPPORTED |  |
| C44 | SUPPORTED |  |
| C45 | SUPPORTED |  |
| C46 | SUPPORTED |  |
| C47 | SUPPORTED |  |
| C48 | PARTIAL | source offers an artifact or listing PRs as options; "must be found by head SHA" dropped |
| C49 | PARTIAL | S13 lists several remedies; "pull_request_target is the documented escape" dropped (C50 covers it); "pull_request" restriction not in quote, dropped |
| C50 | SUPPORTED |  |
| C51 | SUPPORTED |  |
| C52 | SUPPORTED |  |
| C53 | SUPPORTED |  |
| C54 | SUPPORTED |  |
| C55 | SUPPORTED |  |
| C56 | SUPPORTED |  |
| C57 | SUPPORTED |  |
| C58 | SUPPORTED |  |
| C59 | SUPPORTED |  |
| C60 | PARTIAL | expiry clause and "posts a result for every fork PR" went beyond C57/C59; rewritten to "runs regardless of approval settings" and expiry left open |
| C61 | SUPPORTED |  |
| C62 | PARTIAL | source says "Generally speaking ... it is safe"; qualifier restored |
| C63 | SUPPORTED |  |
| C64 | SUPPORTED |  |
| C65 | SUPPORTED |  |
| C66 | SUPPORTED |  |
| C67 | SUPPORTED |  |
| C68 | SUPPORTED |  |
| C69 | SUPPORTED |  |
| C70 | SUPPORTED |  |
| C71 | SUPPORTED |  |
| C72 | PARTIAL | "No GitHub doc states" is a search claim, not a consequence of C52/C69/C70; narrowed to "the cited docs do not settle", C44 added to premises |
| C73 | SUPPORTED |  |
| C74 | SUPPORTED |  |
| C75 | SUPPORTED |  |
| C76 | SUPPORTED |  |
| C77 | SUPPORTED | quote found in S31 log and S30; S30 states the run obtained its OIDC token |
| C78 | SUPPORTED |  |
| C79 | PARTIAL | issue does not say the Dependabot secret fixed the run; narrowed to failure + reporter's suggested remedy |
| C80 | SUPPORTED | read via gh api issues/713 |
| C81 | PARTIAL | one repo's report, fork pull_request runs only; narrowed |

Label verdict: open — Q2 (does a `GITHUB_TOKEN` commit status satisfy a 15368-bound check) and whether a status/check POSTed from `workflow_run` counts at all are unresolved, and either resolved unfavourably changes the `workflow_run` and app-binding parts of the Summary.
Quote check: code-gate-evidence-mechanics-2026-10-06.md: 70 quoted claim(s): 70 found, 0 NOT FOUND, 0 unfetchable, 0 no source
