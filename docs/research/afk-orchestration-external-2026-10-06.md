---
topic: afk-orchestration-external
tags: area:infrastructure, research
source_provenance: https://github.com/Osasuwu/jarvis/issues/1958
status: open
audit: 2026-10-06 — 378 claims: 313 SUPPORTED, 62 PARTIAL, 2 UNSUPPORTED, 1 UNCHECKABLE
---

## Question

Research: substrate, orchestration patterns, merge policy and security for unattended agent runs

> ## Description
>
> Node 2 of the "AFK orchestration" milestone: external research before the architecture grill. The aim is to choose the automation shape once, on evidence, and not redesign it a 9th time.
>
> Topics:
>
> 1. **claude-code-action in detail.**
>    - Which events trigger it.
>    - Whether the prompt can carry a custom skill, or be replaced entirely.
>    - Plugins and `settings.json` on the runner.
>    - What loads headless (skills, `CLAUDE.md`/`AGENTS.md`, hooks, MCP) and what we have to pass in ourselves.
>    - Subagents, web tools, timeouts and turn limits.
>    - The rule that the workflow file must match the default branch.
> 2. **Execution substrate comparison.** Compare four substrates:
>    - claude-code-action;
>    - `claude -p` on a self-hosted runner;
>    - the Agent SDK;
>    - Claude Code cloud sessions or remote triggers.
>
>    Axes: cost, limits, available tools, secrets handling, and what we would have to maintain.
> 3. **Orchestration patterns.** Compare a label state machine with a scheduler or queue. Look at how Copilot coding agent, OpenHands and Pocock's sandcastle handle pickup, retries and hand-back, and collect published failure reports.
> 4. **Merge policy for agent PRs.** Holding HIGH/CRITICAL PRs for a human vs merging fast and reverting. Find any evidence on defect rates either way.
> 5. **Unattended-run security.**
>    - Prompt injection via issues, comments and fetched web pages.
>    - Token scope and `pull_request_target`.
>    - Limiting write scope by path.
>    - The owner-account identity problem (#1894).
> 6. **One source of truth for skills across interactive and headless.** Plugin marketplace, repo-level `.claude/skills`, packaging. This ties to an observed problem: one contract is duplicated in prose across about 7 skills, so every sizeable change goes hard.
> 7. **Cost and observability.** Subscription vs API key on runners; rate limits; logging run outcomes so that "did the lane work" can be answered from data.
> 8. **Multi-repo coverage.** Reusable workflows, the limits of private Free repos (no auto-merge, no protection), per-repo config.
> 9. **Failure handling.** Retries, stuck runs, concurrency, recovery after a half-finished run.
>
> Output: `docs/research/afk-orchestration-external-<date>.md` in jarvis, produced via `/research`. Facts and recommendations go in separate sections.
>
> `[no-decision]` — research input for the architecture grill.
>
> ## Area
>
> area:infrastructure
>
> ## Priority
>
> priority:high
>
> ## Phase
>
> N/A — pipeline design item, tracked by milestone.
>
> ## Acceptance criteria
>
> - [ ] Each of the 9 topics has an answer with cited sources, or is marked unanswered with the reason
> - [ ] claude-code-action claims are checked against its docs or source at a stated version, not only against blog posts
> - [ ] Topic 2 ends in a comparison table across the four substrates
> - [ ] Topic 5 lists the concrete attack paths for our setup, and which control breaks each one
> - [ ] Recommendations are in a separate section from facts
> - [ ] Report merged into jarvis `docs/research/`
>
> ## Size Estimate
>
> XL (> 8h — consider splitting)

Sub-questions: Q1 claude-code-action headless behaviour, the four-substrate comparison, and cost and observability (topics 1, 2, 7); Q2 orchestration patterns, multi-repo coverage and failure handling (topics 3, 8, 9); Q3 merge policy and security for unattended runs, including #1894 (topics 4, 5); Q4 one source of truth for skills across interactive and headless runs (topic 6).

## Summary

Every finding about claude-code-action was checked against source code. The version checked is v1.0.237, commit fd1c128, which is the version jarvis pins [C1]. It bundles Claude Code 2.1.285 [C5]. The latest release is v1.0.243, and floating `v1` points at the same commit [C2]. Between the two versions, only the CI hardening changed and the Claude Code version was bumped to 2.1.291; whether the Claude Code bumps matter here was not checked [C3], [C4], [C6]. This report adds external evidence to the two internal leads, `afk-orchestration-inventory-2026-10-01.md` and `afk-orchestration-handoff-2026-10-01.md`. They describe our current setup; this report sets it against vendor documentation, competing systems, studies and incident reports.

**Substrate (topics 1, 2, 7).**

The action on GitHub-hosted runners is the cheapest substrate that is also documented:

- Our repo is public and the jobs run on standard runners, so we pay no Actions minutes. With an OAuth token, model usage is billed to the subscription [C65], [C68], [C69].
- Using a personal setup token in CI is explicitly allowed. The advertised limits assume "ordinary, individual" usage, the policy text has been reworded since February 2026, and Anthropic may enforce its authentication restrictions without notice [C62], [C101], [C103], [C117].

The rival substrates each have a specific drawback:

- **`claude -p` on a self-hosted runner.** GitHub warns against self-hosted runners on public repos, because any PR author can compromise the runner, and the compromise can persist [C74], [C75].
- **The Agent SDK.** It is a library whose process we would have to run and maintain [C82].
- **Cloud routines.** They are a research preview [C88]. They cannot fire on an issue label [C91], [C93]. They drop webhook events above an hourly cap [C94]. They commit under the user's own GitHub identity [C90].

How the action behaves headless:

- **Prompt.** In agent mode the `prompt` input replaces the default prompt entirely. In tag mode it is only appended to the default [C14].
- **Permissions.** Agent mode sets no permission mode and no default allowed tools [C36].
- **Turn and time limits.** `--max-turns` works, but runs with parallel tool calls can false-fail it [C38], [C39]. There is no wall-clock input other than the job's `timeout-minutes` [C40].
- **Subagents.** Background subagents are dropped, and the run still ends green [C43], [C44].
- **Workflow file.** The rule that the workflow file must match the default branch is enforced server-side, and only on the OIDC path. Passing our own `github_token` skips it [C51].
- **Config on PR events.** `.claude/`, `.mcp.json` and the root `CLAUDE.md` come from the base branch. `AGENTS.md` does not: it is read from the PR head [C28], [C30], [C31].

What run records can and cannot tell us:

- GitHub run records have no token or cost fields [C113], [C114].
- Cost has to be read from the action's `execution_file` or session result, or from OpenTelemetry. Both give estimates [C71], [C86], [C87], [C110], [C111].

**Orchestration, multi-repo, failure handling (topics 3, 8, 9).**

Pickup across the systems surveyed:

- **Copilot** picks up issues on assignment and enforces a 59-minute cap. A stuck session is retried by hand, by unassigning and reassigning the agent [C142], [C143], [C144].
- **The OpenHands resolver** picks up on a label and forks a new `-tryN` branch on every re-pickup [C150], [C179].
- **Sandcastle** is a local loop that filters issues by label; no pickup lock is shown in its cited templates [C165].

None of them documents an idempotent resume of an existing branch on issue re-pickup; OpenHands reuses the branch only when the target is an existing PR [C188], [C180]. Duplicate PRs, and issues already fixed by another PR, are measured causes of rejection [C169], [C170], [C189].

GitHub's native controls cover concurrency:

- `concurrency` with `queue: max` holds up to 100 pending runs per group instead of replacing them [C124], [C125], [C131].
- Group names are repo-wide, so two workflows that share a name cancel each other's runs [C127].

For multi-repo, two points constrain the design:

- `secrets: inherit` is documented only for the same org or enterprise; personal accounts are not named [C135], [C182].
- Private repos on the Free plan get no branch protection, no rulesets and no auto-merge [C138], [C139], [C140]. jarvis-private is in exactly that state [C141].

**Merge policy (topic 4).**

No study compares holding agent PRs for a human against merging fast and reverting [C282]. The evidence that exists points toward a selective hold:

- Our only content gate is an LLM review parsed by regex [C201].
- In one benchmark (diff-only), LLM reviewers caught 15–31% of the issues humans flagged; in another evaluation, review quality collapsed as diffs grew [C251], [C252].
- Revert rates undercount post-merge defects [C242].
- DORA's data argues against heavyweight external approval, not against peer review [C249], [C250].

Together this supports holding the larger, riskier PRs for a human [C283], [C284], [C285].

**Security (topic 5).**

Twelve concrete attack paths against our setup are listed in Q3, each with the control that breaks it [C286]–[C297]. Five of them (AP4, AP5, AP6, AP8, AP9) rest on one fact: the worker acts as the owner's account, with a static PAT [C298].

The most direct path, AP1: an outsider files an issue on the public repo with hidden instructions in it. The owner labels it. The worker reads the raw body and ends up with an auto-merge queued, with only the LLM review in between [C286].

**Skills single source (topic 6).**

Three ways to deliver one skill set to every surface are documented:

- `--add-dir` loads skills from another directory, even in bare mode [C302], [C307].
- Plugins from a private marketplace [C313], [C315].
- `plugin_marketplaces` on the action [C339].

Each route has open defects:

- The action does not configure git credentials before cloning a private marketplace, and the fix PR is unmerged [C350], [C353].
- The marketplace input cannot pin a ref [C354].
- Repeating `--plugin-dir` silently keeps only the last value [C356].
- Repo-enabled plugins now auto-load their skills, but not their hooks [C377], [C378].
- Cloud sessions read neither personal skills nor repo-enabled plugins [C310], [C334].

## Findings

### Q1 — Claude-code-action headless behaviour, the four-substrate comparison, and cost and observability (topics 1, 2, 7) — answered with a gap

Scope: topics 1 (claude-code-action in detail), 2 (substrate comparison) and 7 (cost and observability).

Version basis: every claim about the action is taken from the source or documentation at v1.0.237 (commit fd1c128, the jarvis pin), unless it names another tag. The diff to the latest release, v1.0.243, is in [C3] and [C6].

**Four-substrate table.** Each cell cites only the claims listed below it. A "—" means no claim in this run covers that cell.

| Axis | claude-code-action, GitHub-hosted runner | `claude -p` on a self-hosted runner | Agent SDK in our own process | Claude Code cloud routines |
|---|---|---|---|---|
| Cost | No Actions minutes on a public repo with standard runners [C65], [C68], [C69]. Larger runners are billed [C67]. Model usage goes to the subscription when an OAuth token is used [C57]. | No Actions minutes, but we pay for and maintain the machine [C65], [C76]. Model usage goes to the subscription or the API. | We run the process [C82]. Building on the SDK points to API keys [C61]. Cost fields are client-side estimates [C87]. | Draws on subscription usage, like interactive sessions [C95]. |
| Limits | Job cap of 6 h [C129]. Default `timeout-minutes` is 360 [C128]. The action has no timeout input [C40]. `--max-turns` false-fails on parallel tool calls [C39]. Subscription limits apply: a 5 h window and a weekly cap [C104], [C105]. | Same subscription limits [C104], [C105]. When `--bare` becomes the `-p` default, setup-token auth breaks [C77], [C78], [C79]. | API tier spend caps [C108]. `error_max_turns` and `error_max_budget_usd` are result subtypes [C86]. | Research preview [C88]. Hourly caps drop excess webhook events [C94]. Only Pull request and Release triggers exist [C91], [C93]. |
| Tools | Agent mode sets no permission mode and no default allowed tools [C36]. Tag mode has a fixed allow-list, and anything that would prompt is denied [C32], [C33]. Background subagents are dropped [C43], [C44]. | Full CLI. `dontAsk` mode is meant for CI [C80]. Project hooks and `.mcp.json` load without a trust prompt [C21]. | Skills, hooks, subagents, MCP and plugins [C83]. A launching subagent does not wait for nested background subagents [C42]. | No approval stops (apart from some artifact actions): shell, repo skills and connectors [C89]. No personal skills [C310]. No plugins enabled by repo settings [C334]. |
| Secrets | OIDC App token with the default-branch rule, or our own `github_token` [C47], [C50], [C51]. A one-year OAuth token from `setup-token` [C59]. Subprocess secret scrub only under `allowed_non_write_users` [C240]. | GitHub says almost never use one on a public repo [C74]. Persistent compromise is possible [C75]. | An egress proxy can inject the key so the agent never sees it [C84], [C85]. | In Anthropic-hosted environments, GitHub credentials stay on Anthropic's servers [C96]. The API channel can still exfiltrate [C97]. Commits are made as the user [C90]. |
| Maintenance | Pin a SHA and follow releases. We are 7 commits behind: CI hardening plus Claude Code bumps, not checked for impact [C1], [C2], [C3], [C6]. | We maintain the machine [C76]. | We maintain the process and hosting [C82]. | Behaviour, limits and API may change [C88]. `/fire` is claude.ai-only [C92]. |
| Observability | Outputs: `conclusion`, `execution_file`, `session_id` [C71]. The GitHub run object has no cost field [C113], [C114]. | The stream-json result carries cost [C109]. OTel metrics [C110], [C111]. | Result message with cost, turns and denials [C86]. | — (no source found in this run) |

Gaps carried to Open questions:

- Whether `AGENTS.md` loads on a clean runner (the first-session caveat) [C25], [C26].
- Agent mode's effective permission mode.
- Absolute subscription numbers.
- Observability for routines.

- **C1** [measured] jarvis pin fd1c128 is the commit annotated tag v1.0.237 points to — Own measurements, M1
- **C2** [measured] Latest tag is v1.0.243 (86d88e6); floating v1 tag points at the same commit — Own measurements, M2
- **C3** [measured] v1.0.237 to v1.0.243 = 7 commits: one CI-hardening commit (#1867) + six CC version bumps; only action code file touched is src/entrypoints/run.ts — Own measurements, M3
- **C4** [quoted] v1.0.243 bundles CC 2.1.291 — "const claudeCodeVersion = "2.1.291";" — [S1], v1.0.243 run.ts:80
- **C5** [quoted] v1.0.237 installs CC 2.1.285 — "const claudeCodeVersion = "2.1.285";" — [S2], run.ts:80
- **C6** [inference] Between v1.0.237 and latest, action.yml keeps the same 46 input descriptions and the bundled CC moved from 2.1.285 to 2.1.291; whether those CC bumps matter for the seven topics was not checked — from [C3], [C4], [C5], Own measurements, M3
- **C7** [quoted] Automation events are a second fixed list (workflow_dispatch, repository_dispatch, schedule, workflow_run) — "const AUTOMATION_EVENT_NAMES = [" — [S3], context.ts:63-67
- **C8** [quoted] On comment events, a prompt selects agent mode — "// If prompt is provided on comment events, use agent mode" — [S4], detector.ts:40-42
- **C9** [quoted] On issues events, a prompt selects agent mode; otherwise a mention, label or assignee selects tag mode — "// Check for @claude mentions or labels/assignees" — [S4], detector.ts:51-60
- **C10** [quoted] Action docs still list workflow_dispatch as coming soon — "Manual workflow triggers (coming soon)" — [S5], docs/custom-automations.md:25
- **C11** [inference] The "coming soon" doc line is stale: workflow_dispatch is already a supported automation event in source — from [C7], [C10]
- **C12** [quoted] Agent mode uses the user's prompt as the entire prompt file (fallback: just the repo name) — "// Write the prompt file - use the user's prompt directly" — [S6], agent/index.ts:85-90
- **C13** [quoted] Tag mode keeps its generated prompt and appends the user prompt inside custom_instructions tags — "<custom_instructions>" — [S7], create-prompt/index.ts:484-486
- **C14** [inference] Agent mode: the action does not inject the trigger comment; prompt fully replaces the default. Tag mode: prompt cannot replace the comment-derived default prompt, it is appended to it — from [C8], [C12], [C13]
- **C15** [quoted] The prompt goes to Agent SDK query(), not `claude -p` — "for await (const message of query({ prompt, options: sdkOptions })) {" — [S8], run-claude-sdk.ts:190
- **C16** [quoted] settings is merged into the runner's ~/.claude/settings.json (user scope) — "const settingsPath = `${home}/.claude/settings.json`;" — [S9], setup-claude-code-settings.ts:10, 66
- **C17** [quoted] The action always forces enableAllProjectMcpServers = true — "settings.enableAllProjectMcpServers = true;" — [S9], setup-claude-code-settings.ts:62-63
- **C18** [quoted] Action docs: claude_args takes precedence over settings — "takes precedence over settings." — [S10], docs/configuration.md:356
- **C19** [quoted] Setting sources default to user + project + local unless --setting-sources is passed in claude_args — ": ["user", "project", "local"]," — [S11], parse-sdk-options.ts:338-348
- **C20** [quoted] CC docs: without --bare, -p loads the same context as an interactive session, incl. the working dir and ~/.claude — "Without it, `claude -p` loads the same" — [S12], "Start faster with bare mode", md line 37
- **C21** [quoted] CC docs: -p runs the project's .claude/settings.json hooks and connects .mcp.json servers with no trust prompt — "a `-p` session runs the hooks in a project's `.claude/settings.json` and connects the servers in its `.mcp.json`" — [S12], md line 41
- **C22** [quoted] CC docs: native AGENTS.md reading needs CC 2.1.277 or later — "Reading `AGENTS.md` directly requires Claude Code v2.1.277 or later." — [S13], AGENTS.md section, md line 360
- **C23** [quoted] CC docs: AGENTS.md is read only if no CLAUDE.md exists in the working dir or above — "By default, Claude reads `AGENTS.md` only when you have no `CLAUDE.md` in your working directory or above it." — [S13], md line 365
- **C24** [quoted] CC docs: a fresh CI container is a first session on every run — "every run is a first session" — [S14], "First session after an install or upgrade", md line 584
- **C25** [quoted] CC docs list the first session after upgrading as a case where AGENTS.md support is unavailable — "first session after you upgrade" — [S13], "When AGENTS.md support is unavailable", md line 414
- **C26** [inference] With CC 2.1.285 (≥ 2.1.277), a repo with only AGENTS.md should get it natively. The docs' caveat covers the first session after upgrading from v2.1.276 or earlier; whether a fresh-install runner counts as such a session is not documented. A repo with both files gets only CLAUDE.md unless CLAUDE.md imports @AGENTS.md — from [C5], [C22]-[C25]
- **C27** [quoted] On PRs the action restores Claude config from the base branch because the head checkout is untrusted — "// On PRs, .claude/ and .mcp.json in the checkout are attacker-controlled." — [S2], run.ts:254-255
- **C28** [quoted] Restored from base: .claude, .mcp.json, .claude.json, .gitmodules, .ripgreprc, CLAUDE.md, CLAUDE.local.md, .husky. AGENTS.md is not on the list — "export const SENSITIVE_PATHS = [" — [S15], restore-config.ts:26-35
- **C29** [quoted] Action docs describe the base-branch restore — "restores a fixed list of Claude configuration paths from the PR base branch" — [S16], docs/security.md:56
- **C30** [quoted] #1696 (open, 2026-08-19): AGENTS.md is not restored, so an @AGENTS.md import in the restored CLAUDE.md loads the PR head's AGENTS.md; fix PR #1703 unmerged — "AGENTS.md is not in SENSITIVE_PATHS" — [S17], issue title
- **C31** [inference] On PR events, .claude/ (skills, settings hooks), .mcp.json and root CLAUDE.md come from the base branch. AGENTS.md comes from the PR head — from [C27]-[C30]
- **C32** [quoted] Tag mode allows Glob, Grep, LS, Read, the comment MCP and CI MCP under acceptEdits, plus git Bash tools when API commit signing is off (with it on, mcp__github_file_ops__commit_files and delete_files instead) — "claudeArgs += ` --permission-mode acceptEdits --allowedTools "${tagModeTools.join(",")}"`;" — [S18], tag/index.ts:134 (list), 186
- **C33** [quoted] Tag mode: any call that falls through to "ask" is denied headless — "// Headless SDK has no prompt handler, so anything that falls through to "ask" is denied." — [S18], tag/index.ts:185
- **C34** [quoted] The WebSearch/WebFetch default-disallow env export is dead code at v1.0.237 — "// NOTE: these env var exports are dead — nothing reads ALLOWED_TOOLS / DISALLOWED_TOOLS." — [S7], create-prompt/index.ts:83-84, 984
- **C35** [inference] No live code at v1.0.237 disallows WebSearch/WebFetch. In tag mode they are effectively off: not on the allow-list, and "ask" is denied. In agent mode they depend on the permission mode and allow rules passed via claude_args — from [C32], [C33], [C34]
- **C36** [quoted] Agent mode sets no --permission-mode and no default --allowedTools; it passes only --mcp-config plus the user's claude_args — "claudeArgs = `${claudeArgs} ${userClaudeArgs}`.trim();" — [S6], agent/index.ts:93-132
- **C37** [quoted] CC docs: a plain-text automation prompt has no shell or GitHub API access until tools are granted — "Claude has no shell or GitHub API access until you grant the tools the prompt needs" — [S19], md line 259
- **C38** [quoted] --max-turns is parsed from claude_args into SDK maxTurns; if absent, maxTurns is left unset — "const maxTurnsFromClaudeArgs = extraArgs["max-turns"]" — [S11], parse-sdk-options.ts:207, 318-322
- **C39** [quoted] #1795 (open, 2026-09-04): that check counts tool results instead of API rounds, so runs with parallel tool calls false-fail — "max_turns check compares num_turns (one per tool result) against --max-turns (API rounds)" — [S20], issue title
- **C40** [quoted] No timeout input; use the job-level timeout-minutes — "Configure at job level instead of input level" — [S21], docs/migration-guide.md:29
- **C41** [quoted] CC docs: subagent fork mode is off in -p and the Agent SDK by default — "Fork mode is off in" — [S22], md line 899
- **C42** [quoted] CC docs: in non-interactive mode / SDK, a launching subagent does not wait for its nested background subagents — "the launching subagent doesn't wait" — [S22], md line 1016
- **C43** [quoted] #1852 (open, 2026-09-23): the action stops at the first result, so background subagents are dropped and the run ends green with no output — "Automation mode stops at the first `result`; background subagents leave the review silently empty" — [S23], issue title
- **C44** [inference] Background subagents are unreliable in this action — from [C15], [C41]-[C43]
- **C45** [quoted] Error code that sends the action down the skip path — ""workflow_not_found_on_default_branch"," — [S24], token.ts:24-26
- **C46** [quoted] Same path is also matched by message text — "const workflowValidationMessage = "workflow validation failed";" — [S24], token.ts:50
- **C47** [quoted] The check happens server-side, in Anthropic's OIDC-to-App-token exchange — ""https://api.anthropic.com/api/github/github-app-token-exchange"," — [S24], token.ts:120-121
- **C48** [quoted] Server message text (test fixture): workflow file must be identical to the default branch copy — "The workflow file must exist and have identical content to the version on the repository's default branch." — [S25], test/token.test.ts:75
- **C49** [quoted] On that error the action warns and skips; it does not fail — "core.warning(`Skipping action due to workflow validation: ${message}`);" — [S24], token.ts:131-133
- **C50** [quoted] If the github_token input is set (exported as OVERRIDE_GITHUB_TOKEN), the action returns it and never calls the exchange — "OVERRIDE_GITHUB_TOKEN" — [S24], token.ts:159-165
- **C51** [inference] The default-branch rule applies only on the default Claude-App/OIDC path; passing your own github_token skips it. Enforcement is server-side, so it is not visible exactly what gets compared — from [C45]-[C50]
- **C52** [quoted] allowed_non_write_users bypass works only when github_token is supplied — "if (allowedNonWriteUsers && githubTokenProvided) {" — [S26], permissions.ts:90
- **C53** [quoted] Non-human actors are rejected unless listed in allowed_bots — "Add bot to allowed_bots list or use '*' to allow all bots." — [S27], actor.ts:70-80
- **C54** [quoted] allowed_bots defaults to no bots — "Empty string (default) allows no bots." — [S28], action.yml:30-33
- **C55** [quoted] CC docs: the human-actor check also covers scheduled runs, which GitHub attributes to a repository user, usually the one who last changed the workflow's cron schedule — "If that user is a bot, list it in `allowed_bots`." — [S19], "Who can trigger runs", md line 160
- **C56** [quoted] CC docs: OAuth token available on Pro, Max, Team, Enterprise — "available on Pro, Max, Team, and Enterprise plans" — [S19], setup, md line 77
- **C57** [quoted] CC docs: OAuth-token runs bill the subscription, not the API — "runs use your Claude subscription instead of API billing" — [S19], md line 306
- **C58** [quoted] CC docs: prefer an API key for a shared secret, since an OAuth token is tied to one person's subscription — "an OAuth token is tied to the subscription of the person who ran" — [S19], md line 99
- **C59** [quoted] CC docs: setup-token issues a one-year token for CI — "generate a one-year OAuth token with" — [S29], md line 280
- **C60** [quoted] CC legal: Pro/Max limits assume ordinary individual use, including the Agent SDK — "assume ordinary, individual usage of Claude Code and the Agent SDK" — [S30], md line 48
- **C61** [quoted] CC legal: developers building products/services on the Agent SDK should use API keys — "should use API key authentication through" — [S30], md line 55
- **C62** [inference] A personal subscription token on your own repo's runner is documented and supported; the advertised Pro/Max limits assume "ordinary, individual" usage, which is not stated as a cap on permitted use; product, shared or org use is pointed at API keys or a cloud provider. No numeric limit for CI volume is stated — from [C56]-[C61]
- **C63** [quoted] #1614 (open, 2026-08-09): a setup-token OAuth token rejected with 401 in the action, while working locally — "claude_code_oauth_token from claude setup-token rejected with 401 in the action" — [S31], issue title
- **C64** [quoted] The action consumes GitHub Actions minutes — "runs on GitHub-hosted runners, which consume your GitHub Actions minutes" — [S19], Costs (L305)
- **C65** [quoted] Actions are free for self-hosted runners and for public repos on standard GitHub-hosted runners — "GitHub Actions usage is **free** for **self-hosted runners** and for **public repositories** that use standard GitHub-hosted runners." — [S32], intro (L7; contains markdown bold)
- **C66** [quoted] Private-repo free minutes reset monthly; the plan table lists GitHub Free = 2,000 min/month, Team = 3,000 — "At the start of each month, the minutes used by the account are reset to zero." — [S32], "Free use of GitHub Actions" + table rows L108–111
- **C67** [quoted] Larger runners are billed even on public repos — "Larger runners are always charged for, even when used by public repositories" — [S32], NOTE under free-use table
- **C68** [measured] Osasuwu/jarvis is a PUBLIC repository — Own measurements, M4
- **C69** [inference] The AFK lane (ubuntu-latest, public repo) pays no Actions minutes; when it authenticates with an OAuth token, model usage is billed to the subscription — from [C57], [C65], [C68], Own measurements, M5
- **C70** [quoted] Commits pushed with the default GITHUB_TOKEN do not trigger further workflows — "GitHub doesn't trigger workflows on commits made with the default" — [S19], L341
- **C71** [quoted] At v1.0.237 the action's outputs are conclusion, execution_file, branch_name, github_token, structured_output and session_id; conclusion is success/failure only — "Execution status of Claude Code ('success' or 'failure')" — [S33], outputs (L169–187)
- **C72** [quoted] The documented cost controls are --max-turns, workflow timeouts and concurrency — "Set `--max-turns` in `claude_args` to limit iterations" — [S19], Costs (L313–315)
- **C73** [quoted] GitHub disables scheduled workflows in public repos after 60 days without activity — "in public repositories, disables the schedule after 60 days without repository activity" — [S19], L259
- **C74** [quoted] GitHub says self-hosted runners should almost never be used on public repos because any PR author can compromise them — "because any user can open pull requests against the repository and compromise the environment" — [S34], Hardening for self-hosted runners (L193)
- **C75** [quoted] Self-hosted runners can be persistently compromised by untrusted workflow code — "can be persistently compromised by untrusted code in a workflow" — [S34], L191
- **C76** [quoted] Self-hosted runners are free but the owner pays for and maintains the machines — "Are free to use with GitHub Actions, but you are responsible for the cost of maintaining your runner machines." — [S35], bullet list
- **C77** [quoted] --bare is recommended for scripts and will become the -p default — "is the recommended mode for scripted and SDK calls, and will become the default for `-p` in a future release" — [S12], L70
- **C78** [quoted] Bare mode ignores the subscription OAuth token — "does not read `CLAUDE_CODE_OAUTH_TOKEN`" — [S29], Generate a long-lived token (L310)
- **C79** [inference] When --bare becomes the -p default, any setup-token-authenticated `claude -p` caller (self-hosted runner or the action if it inherits the default) loses auth unless it opts out — from [C77], [C78]
- **C80** [quoted] dontAsk mode denies every prompting call, intended for locked-down CI — "useful for locked-down CI runs" — [S12], permission modes (L285)
- **C81** [quoted] `claude setup-token` makes a one-year token for CI/scripts that can only make model requests — "Use this for CI pipelines and scripts where browser login isn't available." — [S29], Generate a long-lived token (L239; also "generate a one-year OAuth token with `claude setup-token`", "It can only make model requests, so it can't establish")
- **C82** [quoted] The Agent SDK is a library that runs the Claude Code binary in a process you operate — "A library that runs the Claude Code binary" — [S36], comparison table (L17)
- **C83** [quoted] The SDK loads skills, commands and memory from .claude/ and ~/.claude/ like Claude Code; it also supports hooks, subagents, MCP and plugins — "Load automatically from your project's `.claude/` and from `~/.claude/`, same as Claude Code" — [S36], Capabilities table (L31–37)
- **C84** [quoted] Production hosting should route egress through an allowlisting, credential-injecting, logging proxy — "route outbound traffic through an egress proxy that enforces domain allowlists, injects credentials, and logs requests" — [S37], L214
- **C85** [quoted] A proxy outside the agent can inject the API key so the agent never sees it — "The agent can make API calls, but it never sees the credential itself." — [S38], L38
- **C86** [quoted] SDK result messages carry subtype, session_id, duration_ms, num_turns, total_cost_usd, usage, modelUsage, permission_denials; error subtypes include error_max_turns, error_during_execution, error_max_budget_usd — "error_max_turns" — [S39], SDKResultMessage
- **C87** [quoted] SDK cost fields are client-side estimates — "fields are client-side estimates, not authoritative billing data" — [S40], L16
- **C88** [quoted] Routines are a research preview whose behaviour, limits and API may change — "Routines are in research preview. Behavior, limits, and the API surface may change." — [S41], L10
- **C89** [quoted] Routines have no permission-mode picker; they run shell commands, repo skills and connectors without stopping for approval, apart from some artifact actions — "there is no permission-mode picker" — [S41], L51
- **C90** [quoted] Routine commits/PRs are attributed to the user's GitHub identity — "commits and pull requests carry your GitHub user" — [S41], L65
- **C91** [quoted] GitHub triggers support only two event categories (Pull request, Release) — "GitHub triggers can subscribe to either of the following event categories." — [S41], Supported events (L263–270; re-fetched 2026-10-06, unchanged)
- **C92** [quoted] The /fire API endpoint is for claude.ai users only and is not part of the Platform API — "is available to claude.ai users only and is not part of the Claude Platform API surface" — [S41], L230 (beta header `experimental-cc-routine-2026-04-01`, L223)
- **C93** [inference] An issue-label trigger (the AFK lane's current trigger) cannot fire a routine natively; an Action calling /fire is one bridge — from [C91], [C92]
- **C94** [quoted] GitHub webhook events over the per-routine/per-account hourly caps are dropped — "Events beyond the limit are dropped until the window resets." — [S41], L237
- **C95** [quoted] Routines consume subscription usage like interactive sessions — "Routines draw down subscription usage the same way interactive sessions do." — [S41], L378
- **C96** [quoted] In Anthropic-hosted environments, GitHub credentials stay on Anthropic's servers, outside the session VM — "never enter a session's VM" — [S42], L58
- **C97** [quoted] Even with network disabled, the Anthropic API channel can carry data out — "Claude Code can still communicate with the Anthropic API, which may allow data to exit the VM" — [S42], L367
- **C98** [quoted] Cloud sessions always authenticate with subscription credentials — "always use your subscription credentials" — [S29], L251 (link-wrapped "Cloud sessions")
- **C99** [quoted] OAuth auth is for plan purchasers and ordinary use of Claude Code and native Anthropic apps — "is intended exclusively for purchasers of Claude Free, Pro, Max, Team, and Enterprise subscription plans" — [S30], Authentication and credential use (L54)
- **C100** [quoted] Routing requests through Free/Pro/Max credentials on behalf of users is not permitted — "or to route requests through Free, Pro, or Max plan credentials on behalf of their users" — [S30], L55
- **C101** [quoted] Anthropic may enforce these restrictions without notice — "Anthropic reserves the right to take measures to enforce these restrictions and may do so without prior notice." — [S30], L59
- **C102** [quoted] The Consumer Terms bar automated/scripted access except via API key or where explicitly permitted — "to access the Services through automated or non-human means, whether through a bot, script, or otherwise" — [S43], Use of our Services (effective Oct 8, 2025)
- **C103** [inference] A subscriber's own CI use of `claude setup-token` sits in the "explicitly permit it" exception (docs name CI pipelines); the advertised limits assume "ordinary, individual usage", and enforcement without prior notice is reserved for the authentication restrictions — from [C81], [C60], [C101], [C102]
- **C104** [quoted] The Max session limit resets every five hours — "Your session-based usage limit will reset every five hours." — [S44], usage section (L48)
- **C105** [quoted] Max plans also have a weekly limit across all models — "Max plans also have a weekly usage limit that applies across all models." — [S44], L48
- **C107** [quoted] Across enterprise deployments, Claude Code averages about $13 per developer per active day on API — "per developer per active day" — [S46], L11 (full: "around \$13 per developer per active day and \$150-250 per developer per month")
- **C108** [quoted] Reaching a tier spend cap pauses the API until month end, unless a higher limit is requested sooner; table: Start $500, Build $1,000, Scale $200,000; Custom has no cap — "Once you reach your tier's spend cap, API usage pauses until 00:00 UTC on the first day of the next month" — [S47], Spend limits / Reaching your spend cap
- **C109** [quoted] stream-json ends with a result message carrying cost and session metadata — "The last line of the stream is a `result` message with the final response text, cost, and session metadata." — [S12], L185
- **C110** [quoted] Metrics include claude_code.cost.usage (USD), plus token.usage, session.count, pull_request.count, commit.count, active_time.total — "Cost of the Claude Code session" — [S48], Metrics table (L600–607)
- **C111** [quoted] OTel cost metrics are approximations — "Cost metrics are approximations." — [S48], L1380
- **C112** [quoted] OTel exporter variables set in a repo's .claude/settings.json are ignored — "Claude Code ignores the" — [S48], L65 (the sentence continues through a link: "...OpenTelemetry exporter variables... in a repository's `.claude/settings.json`")
- **C113** [measured] The workflow-run REST object has conclusion, run_attempt, run_started_at, updated_at, etc. but no token or cost fields — Own measurements, M7
- **C114** [inference] GitHub run data has no token or cost fields; cost and turns have to come from the action's execution_file / session result or from OTel — from [C71], [C86], [C109], [C113]
- **C115** [quoted] An HN commenter (2026-02-19) quoted an earlier legal-page wording that banned OAuth tokens "in any other product, tool, or service", Agent SDK included — "in any other product, tool, or service" — [S49], comment by adastra22 on story 47069299 (655 pts)
- **C116** [measured] The current legal-and-compliance page no longer contains that sentence — Own measurements, M8
- **C117** [inference] The OAuth policy text has been revised since Feb 2026 (from an "exclusively for Claude Code and Claude.ai" wording to "ordinary use of Claude Code and other native Anthropic applications"), so it is a moving target (assuming the HN commenter's quotation of the old wording is accurate) — from [C99], [C115], [C116]
- **C118** [quoted] An HN user reports bans of 13 Max 20x accounts used for heavy personal business use, with the appeal rejected — "I was using 13 Claude Code 20x subscriptions." — [S50], story text (2026-07-14, 5 pts; anecdote)
- **C119** [quoted] Weekly limits change over time: Anthropic announced a 17% cut to Claude Code's current weekly limits (Sept 2026) — "Anthropic is cutting Claude Code's current weekly limits by 17%" — [S51], HN story title (2026-09-20)
- **C120** [quoted] A third-party guide (2026-04-20) claims routines support push, issues, check_run, workflow_run and more — "pull_request, push, issues, check_run, workflow_run, discussion, release, and merge_queue events" — [S52], "GitHub event triggers" section

### Q2 — Orchestration patterns, multi-repo coverage and failure handling (topics 3, 8, 9) — answered with a gap

Scope: topics 3 (orchestration patterns), 8 (multi-repo coverage) and 9 (failure handling).

**Pickup, retry and hand-back across the systems surveyed.**

| System | Pickup | Lock or concurrency | Retry and re-pickup | Hand-back |
|---|---|---|---|---|
| Copilot cloud agent | Issue assignment [C143], or event/schedule automations [C149] | — | Manual unassign and reassign after the 1 h timeout [C142], [C144] | Draft PR it cannot ready or merge [C146]; CI waits for human approval [C145] |
| OpenHands resolver (V0, deleted) | `fix-me` label [C150]; Cloud uses the `openhands` label or `@openhands` [C155] | None in the shipped workflow [C153] | New `-tryN` branch on every re-pickup [C179]; on an existing PR it pushes to that PR's branch [C180] | Comment on the issue; on failure, a branch with no PR [C151] |
| sandcastle | `gh issue list` label filter inside the prompt [C160], [C161] | None shown in the cited templates [C165] | Not documented; a blocked issue stays open [C162] | Comment on the issue; the agent closes the issue itself, with no PR [C162], [C163] |

**Label state machine vs scheduler.**

- None of the three runs a scheduler or queue with real locking. Copilot and OpenHands are event-triggered. Sandcastle's cited templates are a loop run as a script that filters by label [C164], [C165].
- GitHub's own concurrency primitive is therefore the available lock. `queue: max` keeps up to 100 pending runs per group [C124], [C125], [C131].
- `queue: max` cannot be combined with `cancel-in-progress` [C126].
- Group names collide across workflows [C127].

- **C122** [quoted] A concurrency group allows at most one running job/workflow; a newly queued one waits as pending while another in the group is in progress. — "This means that there can be at most one running job or workflow in a concurrency group at any time." — [S54], intro, fetched 2026-10-06
- **C123** [quoted] By default an existing pending run in the same group is canceled and replaced by the newly queued one (the "pending job canceled" behaviour). — "By default, any existing pending job or workflow in the same concurrency group will be canceled and the new queued job or workflow will take its place." — [S54], intro
- **C124** [quoted] A `queue` property now exists; `single` (default) keeps at most one pending run and cancels/replaces older pending ones. — "single (default): At most one job or workflow run can be pending in the concurrency group." — [S54], queue property list
- **C125** [quoted] `queue: max` lets up to 100 runs wait; beyond that further runs are canceled. — "max : Up to 100 jobs or workflow runs can be pending in the concurrency group. When the queue is full, any additional jobs or workflow runs are canceled." — [S54], queue property list
- **C126** [quoted] queue: max cannot be combined with cancel-in-progress: true. — "The combination of queue: max and cancel-in-progress: true is not allowed and will result in a workflow validation error." — [S54], queue property list
- **C127** [quoted] Concurrency group names are repository-wide across workflows; a name collision cancels runs of other workflows. — "If you have multiple workflows in the same repository, concurrency group names must be unique across workflows to avoid canceling in-progress jobs or runs from other workflows." — [S54], "Example: Using concurrency to cancel any in-progress job or run"
- **C128** [quoted] Job timeout-minutes defaults to 360 minutes, after which GitHub cancels the job. — "The maximum number of minutes to let a job run before GitHub automatically cancels it. Default: 360" — [S55], jobs.<job_id>.timeout-minutes
- **C129** [quoted] GitHub-hosted runner jobs are capped at 6 hours of execution. — "Each job in a workflow can run for up to 6 hours of execution time." — [S56], GitHub-hosted runners table, Job execution time
- **C130** [quoted] A workflow run can be re-run at most 50 times (full or partial). — "A workflow run can be re-run a maximum of 50 times. This limit includes both full re-runs and re-runs of a subset of jobs." — [S56], Workflow execution limits, Re-run
- **C131** [quoted] queue: max ceiling is 100 runs per concurrency group; extra runs are rejected. — "When using queue: max in the concurrency section, up to 100 jobs or workflow runs can be queued per concurrency group. Runs beyond this limit will be rejected." — [S56], Workflows queuing, Concurrency group queue
- **C132** [quoted] Reusable workflows: up to ten levels of nesting. — "You can connect up to ten levels of workflows." — [S57], Limitations of reusable workflows
- **C133** [quoted] A private-repo reusable workflow is callable only if the called repo's Actions Access policy explicitly allows the caller repos. — "For private repositories, the Access policy on the Actions settings page of the called workflow's repository must be explicitly configured to allow access from repositories containing caller workflows" — [S57], Access to reusable workflows
- **C134** [quoted] Visibility matrix: a private caller can use private and public reusable workflows; a public caller can only use public ones. — "Caller repository Accessible workflows repositories private private and public public public" — [S57], Access to reusable workflows, table (text flattened from an HTML table; grep the table cells, not this string)
- **C135** [quoted] secrets: inherit passes all caller secrets; documented scope is same org or same enterprise (personal-account cross-repo not mentioned). — "The inherit keyword can be used to pass secrets across repositories within the same organization, or across organizations within the same enterprise." — [S55], jobs.<job_id>.secrets.inherit
- **C136** [quoted] For a personal account, the private repo setting is "Accessible from repositories owned by 'USERNAME' user". — "To grant access to other private repositories, in the Access section at the bottom of the page, select Accessible from repositories owned by" — [S58], Sharing actions and workflows from your private repository, step 4
- **C137** [quoted] Protected branches, required reviewers and code owners for private repos are listed under GitHub Pro. — "Advanced tools and insights in private repositories:" — [S59], GitHub Pro list (items that follow: Required pull request reviewers, Multiple pull request reviewers, Protected branches, Code owners)
- **C138** [quoted] Protected branches (and so required status checks) are not available on private repos under GitHub Free. — "Protected branches are available in public repositories with GitHub Free and GitHub Free for organizations." — [S60], "Who can use this feature?" box
- **C139** [quoted] Rulesets have the same restriction: private repos need Pro/Team/Enterprise Cloud. — "Rulesets are available in public repositories with GitHub Free and GitHub Free for organizations, and in public and private repositories with GitHub Pro, GitHub Team, and GitHub Enterprise Cloud." — [S61], "Who can use this feature?" box
- **C140** [quoted] Auto-merge has the same restriction: not on private repos under Free. — "Auto-merge for pull requests is available in public repositories with GitHub Free and GitHub Free for organizations, and in public and private repositories with GitHub Pro, GitHub Team, GitHub Enterprise Cloud, and GitHub Enterprise Server." — [S62], "Who can use this feature?" box
- **C141** [measured] Of the operator's active repos, jarvis, jarvis-oss, music-intel-mcp, like-current-song are PUBLIC; jarvis-private and redrobot are PRIVATE; jarvis-private has allow_auto_merge false and its default branch (master) is unprotected. — Own measurements, M9
- **C142** [quoted] Copilot coding agent is now named "Copilot cloud agent"; old docs URLs redirect. Hard limit: 59-minute session, not extendable. — "Each Copilot cloud agent session has a maximum execution time of 59 minutes. This limit cannot be extended or bypassed." — [S63], Limitations and compatibility > Agentic work (redirect target of /copilot/concepts/agents/coding-agent/about-coding-agent)
- **C143** [quoted] Pickup via issue assignment: Copilot reacts with eyes, then opens a draft PR linked to the issue. — "Shortly after this, Copilot will open a draft pull request linked to the issue, which will be shown in the issue timeline." — [S64], "I assigned an issue to Copilot, but nothing is happening"
- **C144** [quoted] Failure handling for a stuck session is a 1-hour timeout, and the documented retry is manual unassign + reassign. — "If the session remains stuck, it will time out after an hour. You can retry by unassigning the issue and then reassigning it to Copilot." — [S64], "Based on the agent session logs, Copilot appears to be stuck"
- **C145** [quoted] CI does not run on Copilot pushes until a human approves. — "GitHub Actions workflows will not run automatically when Copilot pushes changes to a pull request." — [S64], "My GitHub Actions workflows are not running when Copilot pushes"
- **C146** [quoted] Hand-back to human is structural: Copilot PRs are drafts it cannot ready, approve or merge. — "Draft pull requests created by Copilot cloud agent must be reviewed and merged by a human." — [S65], "Requires human review before merging" (next sentence: it cannot mark its PRs Ready for review, approve or merge)
- **C147** [quoted] When the PR is under the app identity, an extra approval is required (when the repo already requires one); in rulesets this is on by default but administrators can turn it off, and it always applies to branch protection rules. — "When Copilot cloud agent opens a pull request under its own app identity, one more approval is required before it can be merged, as long as the repository already requires at least one approval." — [S65], "Requires an additional approval..."
- **C148** [quoted] By default, Actions workflows on the agent's PRs don't run until a user with write access approves them (configurable). — "GitHub Actions workflows don't run on a pull request until a user with write access approves them, which prevents workflows from running automatically as part of such a chain." — [S65], Automations, "Workflows still require human approval"
- **C149** [quoted] Copilot now has event/schedule "automations" (e.g. on issue opened) as a pickup path besides assignment. — "You can also start sessions automatically, on a schedule or in response to events such as an issue being opened, by setting up an automation." — [S66], intro (redirect target of .../coding-agent/create-a-pr)
- **C150** [quoted] OpenHands (V0) resolver was a GitHub Actions workflow triggered by labelling an issue 'fix-me'. — "This repository includes a GitHub Actions workflow that can automatically attempt to fix individual issues labeled with 'fix-me'." — [S67], line 13, tag 1.0.0
- **C151** [quoted] Resolver failure path: on failure it pushes a branch instead of a PR, and comments on the issue either way. — "Create a draft PR if successful, or push a branch if unsuccessful" — [S67], line 53 (repeated line 62 for @openhands-agent mention)
- **C152** [quoted] README says the label is removed after processing. — "Remove the 'fix-me' label once processed" — [S67], line 55
- **C153** [measured] The shipped workflow at the same tag has no label-removal call and no concurrency or timeout-minutes key (README/workflow disagree on [C152]). — Own measurements, M10
- **C154** [quoted] The in-repo V0 resolver was deleted in April 2026, superseded by the hosted integrations and the SDK. — "The V0 resolver code has been superseded by the integrations system and the OpenHands SDK." — [S68], PR body "Why", merged 2026-04-23
- **C155** [quoted] OpenHands Cloud pickup: `openhands` label or a message starting with `@openhands`. — "On your repository, label an issue with `openhands` or add a message starting with `@openhands`." — [S69], Working with Issues
- **C156** [quoted] Multi-repo pattern used by OpenHands: each target repo carries a thin caller workflow that `uses:` the central reusable workflow pinned to @main. — "uses: OpenHands/OpenHands/.github/workflows/openhands-resolver.yml@main" — [S70], jobs.call-openhands-resolver
- **C157** [quoted] Per-repo config in that pattern is via repository variables with defaults (macro, max iterations, model, target branch). — "macro: ${{ vars.OPENHANDS_MACRO || '@openhands-agent' }}" — [S70], with: block
- **C158** [quoted] The central resolver workflow is both `workflow_call` (reusable) and directly triggered by labels/comments. — "workflow_call:" — [S71], lines 3-4 and 53-60
- **C159** [quoted] Sandcastle (mattpocock/sandcastle) is a TypeScript library that orchestrates coding agents in sandboxes. — "A TypeScript library for orchestrating AI coding agents in isolated sandboxes:" — [S72], line 11
- **C160** [quoted] In the README's prompt example, pickup is a label filter evaluated inside the prompt: the prompt shells out to `gh issue list` for the `Sandcastle` label. — "gh issue list --state open --label Sandcastle --json number,title,body,comments,labels --limit 100" — [S72], line 588 (prompt example)
- **C161** [quoted] The prompt treats the filtered list as the only queue; the agent must not run its own unfiltered query. — "The list above has already been filtered to issues ready for work and is the sole source of truth for what work exists." — [S73], line 7
- **C162** [quoted] Hand-back on block is a comment on the issue, and the issue stays open. — "If you are blocked (missing context, failing tests you cannot fix, external dependency), leave a comment on the issue and move on — do not close it." — [S73], line 47
- **C163** [quoted] In the simple-loop template, done means the agent closes the issue itself, after commit plus passing tests. No PR is in that loop. — "Do not close an issue until you have committed the fix and verified tests pass." — [S73], line 45
- **C164** [quoted] The parallel-planner template is run as a script. — "//   npx tsx .sandcastle/main.mts" — [S74], line 15
- **C165** [inference] In the cited templates, sandcastle is a loop run as a script that filters by label, not a label state machine. No pickup lock is shown in the cited templates, so two concurrent loops on the same label could both take an issue. — from [C160], [C161], [C163], [C164]
- **C166** [quoted] AIDev (arXiv 2602.09185) covers 932,791 agent-authored PRs from five agents across 116,211 repos, with data cut off on Aug 1 2025. — "AIDev comprises 932,791 Agentic-PRs authored by five agents: OpenAI Codex , Devin , GitHub Copilot , Cursor , and Claude Code , across 116,211 repositories involving 72,189 developers (dataset cutoff: August 1, 2025)." — [S75], Introduction (spaces before commas are present in the HTML text; grep -F "932,791 Agentic-PRs authored by five agents")
- **C167** [quoted] The earlier AIDev paper (arXiv 2507.15003) reports agent PR acceptance below human: Codex 64%, Devin 49%, Copilot 35%. — "Among the Autonomous Coding Agents, OpenAI Codex achieves the highest acceptance rate at 64%, followed by Devin at 49% and GitHub Copilot at 35%." — [S76], Finding #2 (RQ on acceptance, Figure 3)
- **C168** [quoted] Fix-related agent PRs (8,106 from AIDEV-POP): 65.0% merged, 26.1% closed unmerged, 8.9% left open. — "Across 8,106 fix-related PRs, 65.0% are merged, while 26.1% are closed without merging and 8.9% remain open" — [S77], RQ1 summary (arXiv 2602.00164, 2026-01-29)
- **C169** [quoted] The top non-merge causes are failing tests and the same issue already fixed by another PR. — "test case failures and prior resolution of the same issues by other PRs are the most common causes of non integration" — [S78], Abstract (the abstract page has "non integration"; the HTML body hyphenates it)
- **C170** [quoted] A study of 33k failed agent PRs finds rejection patterns that include duplicate PRs and no reviewer engagement. — "including lack of meaningful reviewer engagement, duplicate PRs, unwanted feature implementations, and agent misalignment." — [S79], Abstract (arXiv 2601.15195, 2026-01-21)
- **C171** [quoted] Not-merged agent PRs tend to be larger and to fail CI. — "Not-merged PRs tend to involve larger code changes, touch more files, and often do not pass the project" — [S79], Abstract
- **C172** [quoted] Counter-evidence: rejection overstates agent error. Only 35.7% of rejected agent PRs were clear agent failures, and 31.2% came from workflow constraints. — "only 35.7% of rejected PRs reflected clear agentic failures, while 31.2% were driven by workflow constraints and 33.1% lacked observable decision rationale." — [S80], Abstract (arXiv 2605.22534, 2026-05-21)
- **C173** [quoted] First-party practitioner report from dotnet/runtime. Copilot cloud agent across seven repos: 2,963 PRs, 1,885 merged (68.6%). — "2,963 CCA pull requests with 1,885 merged (68.6% success rate)" — [S81], "Across all seven repositories" paragraph (data through 2026-03-22)
- **C174** [quoted] Before the setup changes, success was 38.1%. The fix was environment setup, not the agent. — "PRs created before our first setup changes: 38.1% success rate." — [S81], setup / instructions section
- **C175** [quoted] In the dotnet/runtime report, the bottleneck at volume is human review throughput. — "One person with good judgment and a phone can generate PRs faster than a team can review them." — [S81], "dark side to this superpower" paragraph
- **C176** [quoted] Some agent runs end with no diff: the task was abandoned, or the issue was already addressed. — "where CCA ended up not making any changes because the issue was already fully addressed" — [S81], PR size distribution, zero-line PRs (6.7%)
- **C177** [quoted] Re-run semantics: a re-run uses the original actor's privileges and the original SHA/ref, so it does not pick up a newer commit. — "The workflow will also use the same GITHUB_SHA (commit SHA) and GITHUB_REF (git ref) of the original event that triggered the workflow run." — [S82], intro
- **C178** [quoted] A re-run is possible only within 30 days of the initial run. — "You can re-run a workflow run, all failed jobs in a workflow run, or specific jobs in a workflow run up to 30 days after its initial run." — [S82], intro
- **C179** [quoted] Idempotency in the OpenHands resolver: re-pickup of an issue never reuses an existing branch. It probes for `openhands-fix-issue-N` and appends `-tryK`, so a second run pushes a second branch, and opens a PR only when pr_type is draft/ready (pr_type 'branch' creates no PR). — "branch_name = f'{base_branch_name}-try{attempt}'" — [S83], lines 209-215 get_branch_name (base name from send_pull_request.py line 311: base_branch_name = f'openhands-fix-issue-{issue.number}')
- **C180** [quoted] When the target is an existing PR, the resolver pushes to that PR's head branch instead of opening a new one. — "# Push the changes to the existing branch" — [S84], line 468, update_existing_pull_request (called at line 588 when issue_type == 'pr')
- **C181** [quoted] The comparison table says composite actions cannot use secrets, while reusable workflows can. — "Cannot use secrets" — [S85], Key differences table, composite column (table cell; paired cell "Can use secrets" for reusable)
- **C182** [quoted] secrets: inherit is scoped to the same org or enterprise in the how-to too. A personal account is not named either way. — "Workflows that call reusable workflows in the same organization or enterprise can use the inherit keyword to implicitly pass the secrets." — [S86], Passing inputs and secrets
- **C183** [quoted] Secrets do not flow transitively through nested reusable workflows; each hop must pass them. — "Secrets are only passed to directly called workflow, so in the workflow chain A > B > C, workflow C will only receive secrets from A if they have been passed from A to B, and then from B to C." — [S86], Nesting reusable workflows (HTML has &gt;, so grep -F "Secrets are only passed to directly called workflow")
- **C184** [quoted] Changelog confirms the pending-run replacement default and that `queue: max` (changelog dated 2026-05-07) changes it. — "Previously, a concurrency group could have one run in progress and one pending run. If another run entered the group, the pending run was canceled and replaced." — [S87], body
- **C185** [quoted] Event bursts above 500 runs per 10s are blocked rather than queued. — "When the limit is reached, the workflow runs that were supposed to be triggered by the webhook events will be blocked and will not be queued." — [S56], Workflows queuing, Workflow run queued (500 workflow runs / 10 seconds)
- **C186** [quoted] Free plan: 20 concurrent standard GitHub-hosted jobs (Pro: 40). — "Total concurrent jobs" — [S56], GitHub-hosted runners concurrency table, row "Standard GitHub-hosted runner / Free / 20 / 5" (table cells, not one sentence)
- **C187** [quoted] OpenHands docs now describe a "built-in GitHub resolver" in OpenHands Enterprise. The old /run-openhands/github-action page returns "Page Not Found". — "control the built-in GitHub resolver in OpenHands Enterprise." — [S88], GitHub integration line (github-action.md fetched 2026-10-06 returned "# Page Not Found")
- **C188** [inference] In the cited sources, no surveyed system (Copilot, the OpenHands resolver, sandcastle) documents an idempotent "resume the existing branch on issue re-pickup" path: Copilot needs unassign and reassign, and OpenHands forks a `-tryN` branch for an issue (it reuses the head branch only when the target is an existing PR, [C180]). — from [C144], [C179], [C180], [C161], [C162]
- **C189** [inference] Duplicate PRs and issues already resolved by another PR are measured rejection causes in the wild. — from [C169], [C170], [C176]

### Q3 — Merge policy and security for unattended runs, including #1894 (topics 4, 5) — answered with a gap

Scope: topics 4 (merge policy) and 5 (unattended-run security, including #1894).

Our current setup was measured at c6c848f: [C190]–[C207], [M11]. Merge-policy evidence is [C241]–[C255] and [C260]–[C263]. Merge-policy inferences are [C282]–[C285].

**Attack paths against our setup, and the control that breaks each.** The full reasoning and the claims each path rests on are in [C286]–[C297]. The table is an index to those claims.

| # | Entry | What the attacker gets | Control that breaks it |
|---|---|---|---|
| AP1 | Outsider's issue with hidden instructions; the owner applies `agent:dispatch` [C286] | Attacker-chosen code in a PR with auto-merge queued | A required non-author review or an auto-added hold; dispatch only issues authored by write-access users; strip hidden markup |
| AP2 | Issue body edited after the owner labels it [C287] | Same as AP1, even after the owner read the issue | Snapshot or hash the body at label time |
| AP3 | Subprocess (pytest/python) writes files that Edit/Write deny rules block [C288] | Arbitrary file writes in the checkout | Sandbox with `failIfUnavailable`; a server-side protected-path check; CODEOWNERS with required review |
| AP4 | PAT read from the subprocess environment and posted out [C289] | A static owner token, valid until rotated | GitHub App installation token; sandbox network allowlist |
| AP5 | Worker removes `waiting-human-review` from its own PR [C290] | Hold silently released | Required review by another identity; ignore label removals by the worker identity |
| AP6 | Worker labels or edits other issues [C291] | Self-propagating workers | Refuse dispatch when the labeler is the worker identity; scope `gh issue edit` to the run's own issue with a CI check |
| AP7 | `Closes #X` for unrelated issues [C292] | False completion; premature `status:ready` | A required check on the PR's closing set; `/dispatch` re-verifies blockers |
| AP8 | Status context spoofed for `code-gate` or `gitleaks` [C293] | Both gates bypassed | Pin the source app in branch protection |
| AP9 | Admin PAT merges past checks (unverified) [C294] | Every gate bypassable | `enforce_admins=true`; a non-admin worker identity |
| AP10 | Diff or PR text injects the code-review LLM [C295] | The only content gate goes green | A deterministic risk classifier that routes HIGH/CRITICAL to a human |
| AP11 | Fetched web page via Python under pytest [C296] | An indirect injection channel | Sandbox network allowlist |
| AP12 | PR edits `.github/scripts/unblock_ready.py` [C297] | Issue and label writes with `issues:write` | Protect `.github/**`; run scripts from the base ref |

**Identity problem (#1894).** #1894 is scoped as an audit and has no fix plan yet [C258]. Five paths share one root cause: the worker acts as the owner's account [C298]. The comment in our code-review workflow names a non-owner App identity. That comment is stale: the workflow that used the App was deleted [C259], [C280].

- **C190** [quoted] The worker workflow starts on any issue label-add; the job is gated on the `agent:dispatch` label name only. — "    if: github.event.label.name == 'agent:dispatch'" — [S89], .github/workflows/agent-dispatch.yml:8-10,37 @ c6c848f
- **C191** [quoted] The worker's GitHub credential is a fine-grained PAT (contents/issues/pull-requests write, this repo), not GITHUB_TOKEN, chosen so its pushes trigger downstream workflows. — "          # Fine-grained PAT (contents/issues/pull-requests write, scoped to" — [S89], .github/workflows/agent-dispatch.yml:54-62 @ c6c848f
- **C192** [quoted] That PAT is on the owner's own account. — "      # assignee change go out under AGENT_DISPATCH_PAT, which is the owner's" — [S89], .github/workflows/agent-dispatch.yml:196-198 @ c6c848f
- **C193** [quoted] The worker reads the issue body (untrusted text) as its task input. — "            1. `gh issue view ${{ github.event.issue.number }} --json" — [S89], .github/workflows/agent-dispatch.yml:76-78 @ c6c848f
- **C194** [quoted] The worker's allowlist includes unscoped Write/Edit, git push, `gh issue edit`, and `pytest`/`python -m pytest`. — "--allowed-tools "Read,Write,Edit,Glob,Grep,Bash(git status:*)" — [S89], .github/workflows/agent-dispatch.yml:143 @ c6c848f
- **C195** [quoted] Workflow/hook/settings paths are denied only for the Edit and Write tools (plus a few force-push Bash prefixes). — "--disallowed-tools "Edit(./.github/workflows/**)" "Write(./.github/workflows/**)"" — [S89], .github/workflows/agent-dispatch.yml:169 @ c6c848f
- **C196** [quoted] The workflow's own comment concedes Bash prefix rules are not a hard security boundary. — "            # differently-spelled command (a refspec force-push like `git" — [S89], .github/workflows/agent-dispatch.yml:151-161 @ c6c848f
- **C197** [quoted] A deterministic post-step queues squash auto-merge on the worker's PR, using the owner PAT, even if the worker step failed (`if: always()`). — "          gh pr merge "$pr" --squash --auto" — [S89], .github/workflows/agent-dispatch.yml:206-233 @ c6c848f
- **C198** [quoted] waiting-human-review fails only while a review request is pending or the label is present; removing the label (re-triggered by `unlabeled`) turns it green. — "              core.setFailed(`The \`${LABEL_NAME}\` label is present — a human look is owed.`);" — [S90], .github/workflows/waiting-human-review.yml:9-21,45-55 @ c6c848f
- **C199** [quoted] jarvis does not auto-add the waiting-human-review label to worker PRs (unlike jarvis-oss). — "Unlike jarvis-oss, it does not auto-add the label." — [S91], docs/research/afk-orchestration-inventory-2026-10-01.md:183 @ c6c848f
- **C200** [quoted] unblock-ready, on any issue close, promotes each dependent whose last open blocker it was to status:ready. — "# - issue closed: strip status:* (except status:hardware-*), then promote each" — [S92], .github/workflows/unblock-ready.yml:3-4,14-16 @ c6c848f
- **C201** [quoted] The code gate blocks merge only on an all-caps CRITICAL/MAJOR/BLOCKING/MEDIUM heading in the LLM review comment (prose-ladder path) — i.e., the gate is an LLM verdict parsed by regex. — "          if grep -qE '^#{1,6}[^[:alnum:]]*(CRITICAL|MAJOR|BLOCKING|MEDIUM)\b' <<<"$body"; then" — [S93], .github/workflows/code-review.yml:409-411,976-978 @ c6c848f
- **C202** [quoted] Inventory: dispatch PAT, review bot and owner share one account; the agent can release its own holds; jarvis has no authority detector. — "The dispatch PAT, review bot and owner share one account, so notifications are invisible (#1927, closed by failing red), and the agent can release its own holds." — [S91], docs/research/afk-orchestration-inventory-2026-10-01.md:298 (item 10) @ c6c848f
- **C203** [quoted] Inventory: worker PRs auto-merge with only the code-gate, which has known fail-open bugs. — "Worker PRs auto-merge with only the code-gate." — [S91], docs/research/afk-orchestration-inventory-2026-10-01.md:299 (item 11) @ c6c848f
- **C204** [quoted] Inventory: #1941 injection chain — unblock-ready runs on any close and the worker auto-merges, so an auto-merged report can promote a dependent. — "unblock-ready runs on any issue close, and the worker auto-merges, so an auto-merged report can promote a dependent." — [S91], docs/research/afk-orchestration-inventory-2026-10-01.md:302 (item 14) @ c6c848f
- **C205** [quoted] The repo threat model lists prompt injection via GitHub issues with mitigation "None (trusted input assumed)". — "| Prompt injection via GitHub issues | Medium | None (trusted input assumed) |" — [S94], docs/security/threat-model.md:27,91,117 @ c6c848f
- **C206** [quoted] In repo settings, the protected-files hook is wired only to Edit/Write/NotebookEdit; the Bash matcher runs only the secret scanner. — "        "matcher": "Edit|Write|NotebookEdit"," — [S95], .claude/settings.json:5-24 @ c6c848f
- **C207** [measured] main's protection has 5 required checks, NO required pull-request reviews, enforce_admins=false, no rulesets, no CODEOWNERS file; `code-gate` and `gitleaks` are required with app_id=null (any source may satisfy the context). — Own measurements, M11
- **C208** [quoted] PromptPwnd: the agent's own tools (e.g. gh issue edit) are the privileged action channel. — "The AI uses its built-in tools (e.g., gh issue edit) to take privileged actions in the repository." — [S96], attack pattern
- **C209** [quoted] PromptPwnd: with `allowed_non_write_users: "*"` set, token leakage possible even when untrusted input is fetched by the agent itself via tools rather than embedded in the prompt. — "Even if user input is not directly embedded into the prompt, but gathered by Claude itself using its available tools." — [S96], Claude Code Actions section
- **C210** [quoted] Vendor (Anthropic) doc at the SHA we pin: the action checks the triggering actor has write access for issue/PR/comment/review events. — "The action can only be triggered by users with write access to the repository." — [S97], docs/security.md:5 @ fd1c128
- **C211** [quoted] Same doc: when non-write users are allowed, do not use a PAT — a static token can be recovered over time via prompt injection. — "a static token does not rotate between runs and could be partially or fully recovered over time via prompt injection" — [S97], docs/security.md:18 @ fd1c128
- **C212** [quoted] Same doc: restricting tools reduces the token-recovery rate but may not eliminate it. — "Restricting allowed tools via `claude_args` reduces the rate of recovery but may not eliminate the risk." — [S97], docs/security.md:18 @ fd1c128
- **C213** [quoted] Same doc: hidden-markdown sanitization exists but new bypasses may emerge; review raw external input. — "new bypass techniques may emerge" — [S97], docs/security.md:78 @ fd1c128
- **C214** [quoted] Claude Code docs: Read/Edit deny rules DO cover recognized Bash file commands and redirections (so the brief's "deny doesn't apply to Bash" is too broad)... — "Read and Edit deny rules apply to Claude's built-in file tools, to file commands Claude Code recognizes in Bash, such as `cat`, `head`, `tail`, `sed`, and `tee`" — [S98], Read and Edit warning (fetched https://code.claude.com/docs/en/permissions.md 2026-10-06)
- **C215** [quoted] ...but NOT to subprocesses that open files themselves, e.g. a Python script. — "or to arbitrary subprocesses that read or write files indirectly, like a Python or Node script that opens files itself" — [S98], same warning
- **C216** [quoted] Claude Code docs: only the sandbox gives OS-level path enforcement against all processes. — "For OS-level enforcement that blocks all processes from accessing a path, [enable the sandbox](/docs/en/sandboxing)." — [S98], same warning
- **C217** [quoted] Claude Code docs: Bash patterns constraining arguments are fragile. — "Bash permission patterns that try to constrain command arguments are fragile." — [S98], Bash warning
- **C218** [quoted] GitHub docs: for GitHub Apps, the "Workflows" repository permission governs access to and editing of files in .github/workflows. — "If your app specifically needs to access or edit Actions files in the `.github/workflows` directory, request the "Workflows" repository permission." — [S99], Git access para
- **C219** [quoted] GitHub docs: PR authors cannot approve their own PRs — so a required review cannot be satisfied by the account that authored the PR. — "Pull request authors cannot approve their own pull requests." — [S100], note
- **C220** [quoted] GitHub docs: push rulesets are for private or internal repos — jarvis is public (Own measurements, M11), so the file-path push rule is unavailable to us. — "With push rulesets, you can block pushes to a private or internal repository and that repository's entire fork network" — [S61], Push rulesets
- **C221** [quoted] GitHub docs: CODEOWNERS enforcement requires turning on "Require review from Code Owners" in branch protection. — "Edit your branch protection rule and enable the option "Require review from Code Owners"." — [S101], Protecting branches
- **C222** [quoted] GitHub docs: events created with GITHUB_TOKEN don't start new workflow runs (except dispatch and approval-gated PR events); PAT/App tokens do. — "events triggered by the `GITHUB_TOKEN` will not create a new workflow run" — [S102], intro
- **C223** [quoted] Our worker allowlist includes gh issue edit (any issue number, any label) and arbitrary-code runners pytest / python -m pytest. — "Bash(gh issue view:*),Bash(gh issue edit:*),Bash(gh issue comment:*)" — [S89], .github/workflows/agent-dispatch.yml:143 @ c6c848f
- **C224** [quoted] Our unblock-ready writes labels with GITHUB_TOKEN, so its label writes trigger no other workflow (consistent with [C222]). — "Label writes use GITHUB_TOKEN, so they trigger no other workflows." — [S92], .github/workflows/unblock-ready.yml:10 @ c6c848f
- **C225** [quoted] Our unblock-ready runs on same-repo pull_request events with issues: write and executes .github/scripts from the checkout; .github/scripts is not in the worker's Edit/Write deny list ([C195]/L169). — "run: python3 .github/scripts/unblock_ready.py" — [S92], .github/workflows/unblock-ready.yml:61 @ c6c848f
- **C226** [quoted] Invariant mitigation: restrict the agent to one repository per session. — "This approach effectively restricts an agent to working with only one repository per session" — [S103], mitigations
- **C227** [quoted] Nx s1ngularity post-mortem: a PR-title injection in a pull_request_target workflow let attackers steal the npm publish token. — "injection vulnerability to steal our NPM publishing token and publish malicious packages for 4 hours" — [S104], summary
- **C228** [quoted] Comment and Control (Guan + JHU, 2026-04): GitHub comments/PR titles/issue bodies hijack Claude Code Security Review, Gemini CLI Action and Copilot Agent. — "Claude Code Security Review posts extracted API keys as PR comments" — [S105], finding 1 heading
- **C229** [quoted] Comment and Control: the C2 loop needs no infrastructure outside GitHub. — "The loop is entirely within GitHub" — [S105], flow
- **C230** [quoted] Comment and Control (Copilot): hidden HTML-comment instructions in a benign-looking issue that a victim then assigns to the agent — the same shape as an owner applying agent:dispatch. — "They file a benign-looking issue, and a victim unknowingly assigns it to Copilot" — [S105], Finding 3
- **C231** [quoted] Comment and Control: Copilot's env filtering, secret scanning and network firewall were all bypassed. — "I bypassed all of them." — [S105], Finding 3
- **C232** [quoted] Comment and Control: Anthropic said its security-review action is not hardened against prompt injection. — "is not designed to be hardened against prompt injection" — [S105], Finding 1 disclosure
- **C233** [quoted] Our worker fetches the raw issue body itself via gh (not via the action's sanitized prompt context). — "title,body,labels,milestone` — read the full issue body," — [S89], .github/workflows/agent-dispatch.yml:76-78 @ c6c848f
- **C234** [quoted] GitHub docs: by default branch-protection restrictions don't apply to repo admins (our enforce_admins is false, Own measurements, M11). — "By default, the restrictions of a branch protection rule don't apply to people with admin permissions to the repository" — [S60], intro
- **C235** [quoted] GitHub docs: anyone with write can set any status check unless the required check pins an expected source app (our code-gate and gitleaks have app_id null, Own measurements, M11). — "Any person or integration with write permissions to a repository can set the state of any status check in the repository" — [S60], Require status checks
- **C236** [quoted] GitHub docs: a fine-grained token needs the separate "Commit statuses" permission to POST a status — our PAT's declared scope (contents/issues/pull-requests) does not include it. — "## Repository permissions for "Commit statuses"" — [S106], Commit statuses table (POST /repos/{owner}/{repo}/statuses/{sha})
- **C237** [quoted] GitHub docs: GitHub Apps are not tied to a user account — the documented alternative to user-bound PAT identity. — "GitHub Apps are not tied to a user account and do not consume a seat." — [S107], GitHub Apps vs users
- **C238** [quoted] GitHub docs: a PAT is associated with a user. — "Since a personal access token is associated with a user, your automation could break if the user no longer has access to the resources you need." — [S107], PATs
- **C239** [quoted] The Claude Code sandbox (the control [C216] points to) fails open by default when it cannot start. — "By default, if the sandbox can't start because a dependency is missing or the platform is unsupported, Claude Code runs commands without sandboxing." — [S108], line 101 of the fetched sandboxing.md (2026-10-06)
- **C240** [quoted] claude-code-action documents the subprocess secret scrub only under allowed_non_write_users ("When set"). We don't set it, so the worker's subprocesses (pytest/python) should be assumed to see the token in their env. — "When set, Claude does a best-effort scrub of Anthropic, cloud, and GitHub Actions secrets from subprocess environments." — [S97], docs/security.md:16 @ fd1c128
- **C241** [quoted] Largest post-merge study found (37,623 PRs from five agents plus a matched human baseline: 33,596 agent + 4,027 human; Dec 2024–Jul 2025, AIDev + GitHub API): 90-day revert rate is vendor-specific — Codex ~half the human rate, Devin higher. — "Codex-authored PRs were reverted about half as often as human PRs (6.1% vs. 11.5%, odds ratio 0.50), while Devin PRs were reverted more often (14.5%, odds ratio 1.31)" — [S109], abstract (Kraishan et al., submitted 12 Sep 2026)
- **C242** [quoted] Same study's own limitation: reverts are detected by commit message, so silent rewrites are missed (revert rate is a lower bound on post-merge defects). — "revert detection by commit message misses silent rewrites" — [S110], Threats to validity
- **C243** [quoted] Claude Code PRs waited longest for first human review (median 12.6 hours). — "Claude Code PRs waited the longest for a first human review (median 12.6 hours)" — [S109], abstract
- **C244** [quoted] 9,799 human-reviewed agentic PRs: 15.4% of merged PRs required explicit reviewer feedback or direct commits; rejection overstates agent error. — "Among merged PRs, 15.4% required explicit reviewer involvement through feedback or direct commits" — [S80], abstract (May 2026)
- **C245** [quoted] METR: ~half of test-passing SWE-bench Verified agent PRs would not be merged by real maintainers (296 PRs, 4 maintainers, 3 repos, noise-adjusted) — passing the automated grader ≠ mergeable. — "roughly half of test-passing SWE-bench Verified PRs written by mid-2024 to mid/late-2025 agents would not be merged into main by repo maintainers" — [S111], Summary (10 Mar 2026)
- **C246** [quoted] METR's rejection categories include the PR breaking unrelated code — a class tests may not catch. — "Breaks other code: The PR touches unrelated code and causes breakages." — [S111], rejection-reason definitions
- **C247** [quoted] DORA 2024: AI adoption associated with lower delivery stability. — "an estimated reduction in delivery stability by 7.2%" — [S112], 2024 DORA announcement
- **C248** [quoted] DORA 2024's data suggest improving the development process does not improve delivery without basics such as small batch sizes and robust testing. — "at least not without proper adherence to the basics of successful software delivery, like small batch sizes and robust testing mechanisms" — [S112], 2024 DORA announcement
- **C249** [quoted] DORA: heavyweight EXTERNAL approval (CAB/senior manager) showed no change-fail benefit. — "no evidence was found to support the hypothesis that a more formal, external review process was associated with lower change fail rates" — [S113], capability page
- **C250** [quoted] DORA: approvals are best done as peer review during development plus automation — i.e. DORA's evidence is against external gates, not against peer review. — "change approvals are best implemented through peer review during the development process, supplemented by automation to detect, prevent, and correct bad changes early" — [S113], capability page (citing 2019 SoDR)
- **C251** [quoted] LLM reviewers on real PRs: in the diff-only configuration, judged by an LLM-as-judge, 8 frontier models catch only 15–31% of human-flagged issues (SWE-PRBench, 350 PRs). — "8 frontier models detect only 15-31% of human-flagged issues on the diff-only configuration" — [S114], abstract
- **C252** [quoted] In one evaluation (5 models, 150 samples), LLM review quality collapses with diff size. — "diff size is the dominant predictor of review quality, with F1 dropping from 0.657 on diffs under 10 lines to 0.043 on diffs over 150 lines" — [S115], abstract
- **C253** [quoted] Same paper: on real bug-fix PRs the best model's F1 is very low. — "on real PRs alone, the best model achieves F1 = 0.066" — [S115], abstract
- **C254** [quoted] AIDev: agent PRs reviewed only by code-review agents merge far less than human-reviewed ones (association, not causal). — "CRA-only PRs achieve a 45.20% merge rate, 23.17 percentage points lower than human-only PRs (68.37%)" — [S116], abstract
- **C255** [snippet] Counter-weight to [C249]/[C262]: an empirical study ("Four Eyes are Better than Two", unibz) reports that unreviewed commits are more than twice as likely to introduce bugs. Not verified on the page itself (repository page only). — "Unreviewed commits have over two times more chances of introducing bugs than reviewed commits" — [S117], search snippet
- **C256** [quoted] The worker job holds write on contents, pull-requests and issues. — "      contents: write" — [S89], .github/workflows/agent-dispatch.yml:40-43 @ c6c848f
- **C257** [quoted] The threat model relies on `permissions.deny` globs in the USER-level ~/.claude/settings.json for .env/credential reads; the worker prompt states the runner has no ~/.claude layer, and the repo's .claude/settings.json has no `permissions` block (Own measurements, M12). — "`permissions.deny` globs in `~/.claude/settings.json` (`Read`/`Edit` on `**/.env*`)" — [S94], docs/security/threat-model.md:55; agent-dispatch.yml:69-71 @ c6c848f
- **C258** [quoted] #1894 is scoped as an audit of single-developer-shaped mechanisms (role vs headcount), not as a fix for the PAT identity; it has no comments. — "Audit every mechanism in this repo that assumes a single developer and give each a form that" — [S118], issue body; comments: [] (M13)
- **C259** [quoted] A code-review.yml comment names a GitHub App identity in the pipeline (osasuwu-ci[bot], via a merge-train App token). — "          #     merge-train.yml's update-branch fires a `synchronize` whose" — [S93], .github/workflows/code-review.yml:163-171 @ c6c848f
- **C260** [quoted] 567 Claude Code PRs in 157 OSS projects: 83.8% merged, and 54.9% of merged ones were integrated without further modification. — "83.8% of these agent-assisted PRs are eventually accepted and merged by project maintainers, with 54.9% of the merged PRs are integrated without further modification" — [S119], abstract (Watanabe et al., Sep 2025)
- **C261** [quoted] METR's own caveat: agents got no chance to iterate on feedback; not claimed as a capability limit. — "Since the agents are not given a chance to iterate on their solution in response to feedback the way a human developer would" — [S111], Summary
- **C262** [quoted] Microsoft (Bacchelli & Bird, ICSE 2013): finding defects is the main motivation for review, but outcomes are less about defects than expected. — "reviews are less about defects than expected and instead provide additional benefits such as knowledge transfer, increased team awareness, and creation of alternative solutions to problems" — [S120], abstract (firecrawl directQuote)
- **C263** [quoted] Vendor report (CodeRabbit, sells AI review — conflict of interest; 470 PRs): AI-co-authored PRs had ~1.7x more issues. — "AI-generated PRs contained ~1.7× more issues overall." — [S121], blog, Dec 2025
- **C264** [quoted] Aikido (PromptPwnd, vendor research) claims the first confirmed real-world prompt injection compromising CI/CD pipelines. — "First confirmed real-world demonstration that AI prompt injection can compromise CI/CD pipelines." — [S96], intro
- **C265** [quoted] PromptPwnd: Google's Gemini CLI repo had the pattern; patched within four days of disclosure. — "Google's own Gemini CLI repository was affected by this vulnerability pattern, and Google patched it within four days of Aikido's responsible disclosure." — [S96], intro
- **C266** [quoted] PromptPwnd on claude-code-action: default runs only for write-permission triggers, but this can be disabled. — "By default, it will only run when the pipeline is triggered by a user with write permission. However, this can be disabled with the following setting:" — [S96], Claude Code Actions section
- **C267** [quoted] PromptPwnd remediation includes restricting the agent's toolset. — "Restrict the toolset available to AI agents" — [S96], remediation heading
- **C268** [quoted] Our agent-dispatch and code-review both pin claude-code-action at that SHA. — "uses: anthropics/claude-code-action@fd1c128679612beff4ca259c78021c506e8aa7a7 # v1" — [S89], .github/workflows/agent-dispatch.yml:51 @ c6c848f
- **C269** [quoted] GitHub docs: "Restrict file paths" push rule blocks commits touching specified paths. — "Prevent commits that include changes in specified file paths from being pushed to the repository." — [S122], Restrict file paths
- **C270** [quoted] GitHub Security Lab (2021): pull_request_target + explicit checkout of an untrusted PR can compromise the repo. — "Combining the pull_request_target workflow trigger with an explicit checkout of an untrusted Pull Request is a dangerous practice that may lead to repository compromise" — [S123], meta description / intro
- **C271** [quoted] Same: such workflows have access to target repo secrets. — "They also have access to target repository secrets" — [S123], body
- **C272** [quoted] GitHub docs: the issues event only triggers from the workflow file on the default branch (GITHUB_SHA = last commit on default branch) — i.e. issue-triggered runs use the default branch's workflow file and SHA. — "This event will only trigger a workflow run if the workflow file exists on the default branch." — [S124], issues
- **C273** [quoted] GitHub docs: pull_request_target/workflow_run with untrusted checkout are the named untrusted-code risk. — "The `pull_request_target` and `workflow_run` workflow triggers, when used with the checkout of an untrusted pull request, expose the repository to security compromises." — [S34], Mitigating the risks of untrusted code checkout
- **C274** [quoted] Our code-review sets allowed_bots "*" and justifies it by the same-repo-only job condition plus write-access requirement. — "branch pushes both require repo write access. No untrusted external" — [S93], .github/workflows/code-review.yml:175 @ c6c848f
- **C275** [quoted] Our code-review job runs only for same-repo PRs (forks excluded); the job also admits workflow_dispatch and excludes dependabot. — "(github.event.pull_request.head.repo.full_name == github.repository &&" — [S93], .github/workflows/code-review.yml:30 @ c6c848f
- **C276** [quoted] Invariant Labs (vendor): official GitHub MCP server exploitable by a malicious issue on a public repo that waits for an agent to read it. — "an attacker can now create a malicious issue on the public repository, containing a prompt injection waiting for the agent to interact" — [S103], attack setup
- **C277** [quoted] Invariant: it is an agent-flow (architectural) problem, not a server-code bug — so patching the tool doesn't fix it. — "this is not a flaw in the GitHub MCP server code itself" — [S103], discussion
- **C278** [quoted] Nx: the malicious packages attempted to use locally installed AI CLIs (Claude, Gemini) and uploaded the results to a public GitHub repo. — "attempted to use local AI tools (like Claude and Gemini), and uploaded the results to a public GitHub repo via the GitHub CLI" — [S104], summary
- **C279** [quoted] AWS bulletin: an inappropriately scoped GitHub token in CodeBuild let an actor commit malicious code that auto-shipped in a release (Amazon Q VS Code 1.84.0). — "With that access token, the threat actor was able to commit malicious code into the extension's open-source repository that was automatically included in a release." — [S125], bulletin body
- **C280** [measured] Correction to [C259]: merge-train.yml (the App-token consumer that code-review.yml's comment cites) is no longer in the repo; it was deleted in d2f3e7b (#1835). So the comment is stale, and "a non-owner App identity is already in use here" is NOT established. The App may still exist on the account. — Own measurements, M14
- **C281** [quoted] Counter to [C264]'s "first": Comment and Control's Claude finding was reported 2025-10-17, before PromptPwnd's Dec 2025 disclosure. The C&C post itself was published later (2026-04). — "I reported this on 2025-10-17" — [S105], Finding 1 disclosure timeline
- **C282** [inference] No source found compares "hold for a human" against "merge fast, then revert" on agent PRs. The closest evidence is observational. Agent PRs that got human review merge at 68% vs 45% for review-agent-only. Post-merge revert rates are vendor-specific: Codex is below the human rate, Devin above. — from [C241], [C244], [C254]
- **C283** [inference] Our only automated content gate is an LLM review whose verdict is parsed by regex. In one benchmark (diff-only) LLM reviewers caught 15–31% of human-flagged issues; in another evaluation review quality fell sharply with diff size; not-merged agent PRs tend to be larger. So relying on the gate likely lets many human-flaggable defects through, especially on large PRs, which supports holding large or risky PRs for a human. — from [C201], [C171], [C251], [C252], [C253]
- **C284** [inference] DORA's evidence is against heavyweight external approval, not against review. It supports peer review plus automated testing plus small batches. A human hold on a subset (HIGH/CRITICAL) fits that. One empirical counter (snippet-level) says reviewed commits introduce fewer bugs. — from [C247], [C248], [C249], [C250], [C255]
- **C285** [inference] "We'll revert" assumes we detect the defect, and that is weaker than it sounds. Revert counting misses silent rewrites, and "breaks other code" is one of METR's maintainer rejection categories for test-passing PRs. So revert counts understate merged defects, and merge-and-revert needs detection beyond revert counting. — from [C242], [C245], [C246]
- **C286** [inference] AP1 — outsider issue → main. ENTRY: anyone files an issue on the public repo with instructions hidden in an HTML comment, which GitHub's rendering does not show. The owner applies agent:dispatch. The action's write-access check passes because it checks the labeler, not the author. The worker reads the raw body itself via gh, so the action's hidden-markup sanitizer is not in the path. GETS: attacker-chosen code in a PR with auto-merge queued. The only content gate is the LLM review: there is no required human review, and the hold label is not auto-added. BREAKS IT: (a) a required review by a non-author identity, or auto-adding waiting-human-review to every worker PR; (b) dispatching only issues authored by write-access users; (c) stripping hidden markup from the body before the worker reads it. — from [C190], [C193], [C197], [C199], [C201], [C203], [C205], [C207], [C210], [C213], [C219], [C230], [C233]
- **C287** [inference] AP2 — TOCTOU body swap. ENTRY: the issue author edits the body after the owner has read it and applied agent:dispatch. The worker reads the body at run time, not a reviewed snapshot. GETS: the same as AP1, even when the owner did read the issue. BREAKS IT: snapshot or hash the body at label time and have the worker read that, or refuse to run if the body changed after the label was applied. — from [C190], [C193], [C233]
- **C288** [inference] AP3 — Edit/Write deny bypass via subprocess. ENTRY: an injected or wrong worker writes a non-denied file (e.g. tests/conftest.py) and runs the allowed pytest. Python opens files itself, which deny rules don't cover. There is no sandbox, and the sandbox fails open by default anyway. GETS: arbitrary file writes in the checkout, including the denied paths. Paths NOT in the deny list (.github/scripts/**, tests/ci/**, AGENTS.md) are writable even with plain Write. BREAKS IT: (a) a sandbox with failIfUnavailable=true; (b) protected-path enforcement on the server side (a required check that fails PRs touching protected paths) rather than a tool hook; (c) CODEOWNERS plus required code-owner review on .github/** and the guard files. Push rulesets (file-path restriction) are NOT available because the repo is public. — from [C194], [C195], [C196], [C206], [C214], [C215], [C216], [C218], [C220], [C221], [C239]
- **C289** [inference] AP4 — PAT exfiltration. ENTRY: if the token is in the subprocess env, as [C240] says to assume, an injected worker reads it (python under pytest; no scrub in our mode). It posts the token via the allowed `gh issue comment`, or writes it into a committed file. The Bash secret-scanner hook only inspects Bash command text, not what a Python subprocess sends. GETS: a static owner-account token with contents/issues/PR write, usable outside the run until rotated. This is exactly the case the vendor doc warns against. BREAKS IT: (a) a GitHub App installation token instead of the PAT, which also gives the worker its own identity; (b) a network allowlist via the sandbox. — from [C191], [C192], [C206], [C208], [C209], [C211], [C212], [C223], [C228], [C229], [C231], [C237], [C240]
- **C290** [inference] AP5 — the agent releases its own hold. ENTRY: the worker, or anyone holding the PAT, removes the waiting-human-review label from its PR (PR labels are issue labels). `gh issue edit` is allowed. Whether gh's issue subcommand accepts a PR number is unverified, but a REST call from Python would work if the token is in the subprocess env ([C240]). The check re-runs on `unlabeled` and passes, and auto-merge is already queued. Because the PAT is on the owner's account, the audit trail shows the owner removing the label. GETS: the hold silently released. BREAKS IT: (a) make the hold a required review from a different identity (authors can't approve their own PRs); (b) have the check ignore label removals sent by the worker identity, which requires the worker to have its own identity (an App). — from [C192], [C197], [C198], [C202], [C219], [C223], [C237], [C240]
- **C291** [inference] AP6 — worker fan-out. ENTRY: the worker runs `gh issue edit <other#> --add-label agent:dispatch`, or edits another issue's body to plant instructions. PAT-authored events DO trigger workflows (which is why the PAT was chosen). The sender is the owner, who has write, so the action's actor check passes. GETS: self-propagating workers, each auto-merging. Injection also spreads into issues the owner already vetted. BREAKS IT: (a) agent-dispatch refuses when the labeling sender is the worker identity (needs a distinct App identity); (b) limit `gh issue edit` to the run's own issue, enforced by a CI-side check because prefix rules are fragile; (c) one-issue-per-run scoping, as in Invariant's one-repo-per-session mitigation. — from [C191], [C208], [C210], [C217], [C222], [C223], [C226]
- **C292** [inference] AP7 — close-chain promotion. ENTRY: an injected worker PR body lists `Closes #X` for issues unrelated to the dispatched one. On auto-merge GitHub closes them, and unblock-ready promotes their dependents to status:ready. unblock-ready's label writes use GITHUB_TOKEN and trigger no workflow, so promotion alone does not auto-dispatch. The damage comes when the next /dispatch or a human trusts status:ready. GETS: false completion of unrelated issues plus premature readiness. BREAKS IT: (a) a required check that a worker PR closes only the issue it was dispatched for; (b) /dispatch re-verifying blockers instead of trusting the label. — from [C197], [C200], [C204], [C222], [C224]
- **C293** [inference] AP8 — status-context spoof. ENTRY: any identity with Commit statuses write posts `success` for code-gate or gitleaks on a PR head. Neither required check pins its source app. The worker PAT as declared lacks that permission (scope from a comment, not measured), so this path is closed for the worker but open to any other owner token or App with statuses write. GETS: the two gates bypassed. BREAKS IT: pin the expected source app for code-gate and gitleaks in branch protection, a one-line settings change. — from [C191], [C207], [C235], [C236]
- **C294** [inference] AP9 — admin bypass (UNVERIFIED). ENTRY: the PAT belongs to the repo admin, and enforce_admins is false. A direct merge API call from the worker's Python might merge past failing required checks. Whether a fine-grained PAT carries the user's admin bypass is not established here. GETS (if true): every gate is bypassable by the worker. BREAKS IT: enforce_admins=true, and moving the worker to a non-admin identity. — from [C192], [C207], [C234]
- **C295** [inference] AP10 — reviewer injection. ENTRY: worker-authored diff or PR text addresses the code-review LLM ("no findings"). The gate is a regex over that LLM's comment. A security-review action from the same vendor was hijacked via PR title in Comment and Control, and Anthropic says it is not hardened against injection. The action restores .claude/ and CLAUDE.md from base, but not AGENTS.md. GETS: the only content gate goes green. BREAKS IT: a deterministic risk classifier (paths, size) that routes HIGH/CRITICAL to a human hold regardless of the LLM verdict. — from [C201], [C28], [C228], [C232]
- **C296** [inference] AP11 — fetched web page. The worker allowlist has no WebFetch/WebSearch, so a web page is not a direct channel into the worker. The remaining routes are (a) Python under pytest fetching URLs, since there is no sandbox or network allowlist, and (b) repo files that quote web content. Lower priority than AP1–AP6. BREAKS IT: a sandbox network allowlist. — from [C194], [C215], [C216], [C239]
- **C297** [inference] AP12 — PR-supplied script in a privileged workflow (Nx shape, small blast radius). ENTRY: a worker PR edits .github/scripts/unblock_ready.py, which is not denied. unblock-ready runs on that same-repo PR's opened event and executes the script from the checkout with an issues:write GITHUB_TOKEN. GETS: arbitrary issue and label writes; there are no other secrets in that job. BREAKS IT: (a) add .github/** to the protected paths; (b) check out the base ref for script execution. Caveat: that the checkout is the PR merge ref is GitHub's default for pull_request events and was not verified per run. — from [C195], [C225], [C227]
- **C298** [inference] Cross-cutting: AP4, AP5, AP6, AP8 and AP9 all rest on one fact. The worker acts as the owner's account, with a static token. Moving the worker to a GitHub App installation token weakens all five at once: an App is not tied to a user account, so it is a distinct identity checks can test for, and the owner's approval would count as a non-author review. It is the highest-leverage single control. This is also exactly what the vendor doc says to avoid PATs for. Note: no App currently used in this repo was established ([C280]). — from [C192], [C211], [C219], [C234], [C237], [C238], [C280]

### Q4 — One source of truth for skills across interactive and headless runs (topic 6) — answered with a gap

Scope: topic 6 (one source of truth for skills across interactive and headless runs).

**Delivery routes per surface.**

| Route | Interactive CLI | `-p` / SDK on a runner | claude-code-action | Cloud sessions and routines |
|---|---|---|---|---|
| `~/.claude/skills` (personal) | Loads [C299] | Loads unless `--bare` or `--setting-sources` drops `user` [C306], [C361] | Only if the runner has a `~/.claude` layer | Not read [C310] |
| Repo `.claude/skills` | Loads [C300] | Loads [C300] | Loads after checkout [C348]; on PRs the base copy runs [C347] | Repo skills run [C89] |
| `--add-dir <path>` | Loads that directory's skills [C302] | Loads, even in bare mode [C307] | Converted to SDK `additionalDirectories` [C345]; skill loading not verified [C346] | — |
| Plugin from a private marketplace | Needs git credentials on the machine [C316], [C317] | Background install can miss turn 1 unless `CLAUDE_CODE_SYNC_PLUGIN_INSTALL=1` [C324] | `plugin_marketplaces` input since v1.0.15 [C339]; private clone fails without credentials, fix unmerged [C350], [C353]; no ref pin [C354] | Not installed from repo settings [C334] |
| Synced claude.ai skills | Sync to `~/.claude/skills/synced` [C311] | Need `CLAUDE_CODE_SYNC_SKILLS=1` [C312] | — | — |

**Shared contract text.** The issue's observed problem is one contract repeated in prose across about 7 skills.

- The agentskills.io spec has no include or import primitive [C375].
- A plugin's cache copy keeps only files inside the plugin directory, plus symlinks that point elsewhere in the same marketplace (not for plugins installed from a local path or a copy-mode command source, which keep only in-plugin symlinks) [C330], [C331], [C376].
- `CLAUDE.md` `@import` resolves relative to the importing file [C338]. An unresolvable import fails silently [C367].

- **C299** [quoted] Personal skills live at ~/.claude/skills/<name>/SKILL.md and load in all projects on that machine, not cloud/Cowork — "All your projects on this machine, but not [Cowork or cloud sessions](#skills-in-cowork-and-cloud-sessions)" — [S126], "Where skills live" table, Personal row
- **C300** [quoted] Project skills live at .claude/skills/<name>/SKILL.md and load for sessions in that repo — "Sessions in this repository. Commit it so your team gets it too" — [S126], "Where skills live" table, Project row
- **C301** [quoted] Plugin skills live under <plugin>/skills/ and are namespaced by plugin name — "Wherever the [plugin](/docs/en/plugins/overview) is enabled, as `/plugin-name:skill-name`" — [S126], "Where skills live" table, Plugin row
- **C302** [quoted] Skills from a directory passed with --add-dir load (that dir's .claude/skills) — "`.claude/skills/<skill-name>/SKILL.md` in a directory you pass with `--add-dir`" — [S126], "Where skills live" table, Additional directory row
- **C303** [quoted] Precedence for same-named skills: enterprise > personal > project — "Enterprise over personal, and personal over project." — [S126], "Resolve skills that share a name" table
- **C304** [quoted] A personal/project skill entry can be a symlink to a directory elsewhere — "a `<skill-name>` entry in the enterprise, personal, or project location can be a symlink to a directory elsewhere on disk." — [S126], "Skill folders also follow these rules" - Symlinked folders
- **C305** [quoted] permissions.additionalDirectories only grants file access, it does not load skills (unlike --add-dir) — "The `permissions.additionalDirectories` setting in `settings.json` grants file access only and loads none of these." — [S126], "Skills from additional directories"
- **C306** [quoted] --bare skips auto-discovery of skills, plugins, CLAUDE.md etc. — "Add `--bare` to reduce startup time by skipping auto-discovery of hooks, skills, custom commands" — [S12], "Start faster with bare mode"
- **C307** [quoted] In bare mode, --add-dir skills still load (partial exception) — "bare mode loads skills from its `.claude/skills/` folder, but still skips its `.claude/commands/` and `.claude/agents/` folders." — [S12], "Start faster with bare mode"
- **C308** [quoted] In bare mode a plugin can be passed explicitly with --plugin-dir / --plugin-url — "| A plugin | `--plugin-dir <path>`, `--plugin-url <url>` |" — [S12], bare-mode flags table
- **C309** [quoted] User-invoked skills work in -p mode via /skill-name in the prompt — "User-invoked [skills](/docs/en/skills) and custom commands work. Include `/skill-name` in the prompt string and Claude Code expands it before running." — [S12], line 328 of .md
- **C310** [quoted] Cloud sessions/routines don't read ~/.claude/skills; a personal-only skill is "not found" there — "If a skill exists only in `~/.claude/skills/` on your machine, Claude Code reports that the skill was not found when a [routine](/docs/en/routines) invokes it" — [S126], "Use skills in Cowork and cloud sessions"
- **C311** [quoted] claude.ai-account skills sync into ~/.claude/skills/synced in terminal sessions signed in with claude.ai — "Claude Code downloads your account's skills into `~/.claude/skills/synced/` in the background" — [S126], "Where synced skills load"
- **C312** [quoted] A non-interactive run can finish before synced skills download unless CLAUDE_CODE_SYNC_SKILLS=1 — "To make a non-interactive run download your skills and wait for the list before it answers the prompt, set [`CLAUDE_CODE_SYNC_SKILLS`](/docs/en/env-vars#variables) to `1`." — [S126], "Where synced skills load"
- **C313** [quoted] A plugin is a directory of skills/agents/hooks/MCP servers installed as one unit — "A Claude Code plugin is a directory of skills, agents, hooks, MCP servers, or other components that Claude Code installs and loads as one unit." — [S127], intro
- **C314** [quoted] A marketplace is a dir/repo with .claude-plugin/marketplace.json — "A plugin marketplace is a directory or repository with a `.claude-plugin/marketplace.json` file that lists your plugins and where to fetch each one." — [S128], intro
- **C315** [quoted] A marketplace repo can be private — "The repository can be private, it can list as many plugins as you like" — [S128], intro
- **C316** [quoted] Private marketplace auth: Claude Code runs non-interactive git with the machine's existing credentials; no token field — "Claude Code has no git token of its own, and `marketplace.json` has no field for one." — [S129], "Grant access to a private marketplace"
- **C317** [quoted] HTTPS works only with a credential the helper already stores; gh auth setup-git is the GitHub path — "A credential the helper already stores works; one it would have to ask for fails. On GitHub, `gh auth login` followed by `gh auth setup-git` stores one." — [S129], "Grant access to a private marketplace"
- **C318** [quoted] GITHUB_TOKEN in env alone doesn't authenticate the background check; works through a credential helper such as gh's — "If a user sets `GITHUB_TOKEN` or another provider token in the environment, that alone doesn't authenticate the background check." — [S129], "What background auto-update does with credentials"
- **C319** [quoted] On GitHub Actions: export a token as GH_TOKEN and run gh auth setup-git; default workflow token can't read another private repo — "The default workflow token can only access the workflow's own repository, so a private marketplace in another repository needs a personal access token or app token." — [S130], "Seed containers and CI" note
- **C320** [quoted] Per-repo requirement uses extraKnownMarketplaces + enabledPlugins in the repo's .claude/settings.json — "set `extraKnownMarketplaces` and `enabledPlugins` in that repository's `.claude/settings.json`." — [S130], "Require plugins per repository"
- **C321** [quoted] In -p runs, repo extraKnownMarketplaces apply only in a trusted folder (accepted interactively or hasTrustDialogAccepted in ~/.claude.json) — "the entries apply only in a folder whose trust the user already accepted interactively, or whose `hasTrustDialogAccepted` flag you set in `~/.claude.json`." — [S130], "Require plugins per repository"
- **C322** [quoted] In an untrusted folder the repo's extraKnownMarketplaces are ignored silently — "in an untrusted folder Claude Code ignores them without a message" — [S130], "Require plugins per repository"
- **C323** [quoted] Externally-sourced plugin entries don't auto-install from repo settings alone; relative-path entries do — "A plugin whose marketplace entry points at an external source instead, such as the plugin's own GitHub repository, doesn't install from the repository's settings alone." — [S130], "Require plugins per repository"
- **C324** [quoted] In -p/CI, plugins install in the background and can miss the first turn; CLAUDE_CODE_SYNC_PLUGIN_INSTALL=1 waits — "Set `CLAUDE_CODE_SYNC_PLUGIN_INSTALL=1` to make the run wait for the install before its first query." — [S130], "Where and when settings apply"
- **C325** [quoted] CI runners that can't clone at runtime can use a pre-built seed via CLAUDE_CODE_PLUGIN_SEED_DIR — "pre-populate a plugins directory at build time and point `CLAUDE_CODE_PLUGIN_SEED_DIR` at it." — [S130], "Seed containers and CI"
- **C326** [quoted] CI verification: init event of stream-json lists loaded plugins — "run `claude -p` with `--output-format stream-json --verbose`. The `init` event lists the loaded plugins under `plugins`." — [S130], "Confirm the rollout"
- **C327** [quoted] Plugin entries can pin ref (branch/tag) and sha (commit) — "`ref` names a branch or tag and `sha` names a commit for a `github`, `url`, or `git-subdir` source." — [S129], "Hold users on one version"
- **C328** [quoted] Omitting version makes users track commits (version = 12-char commit SHA for git sources) — "The commit SHA of the source, shortened to 12 characters." — [S131], "How Claude Code computes the version"
- **C329** [quoted] Background auto-update is off by default for third-party marketplaces — "Background auto-update is off for your marketplace by default, and `marketplace.json` has no field to turn it on." — [S129], "Turn on auto-update"
- **C330** [quoted] Marketplace plugins are copied into the cache; files outside the plugin dir are not copied — "Files outside the plugin directory aren't copied, so when a script inside a copied plugin reads a path above the plugin root, such as `../shared`, it doesn't find them" — [S131], "In-place and copied plugins"
- **C331** [quoted] Symlinks to elsewhere in the same marketplace are dereferenced (content copied) into the cache; this does not apply to plugins installed from a local path or from a copy-mode command source, which preserve only symlinks within the plugin's own directory — "The target's content is copied into the cache in its place." — [S129], "Share files within a marketplace with symlinks"
- **C332** [quoted] --plugin-dir plugins load in place, never copied — "the directory loads in place and is never copied." — [S131], "In-place and copied plugins"
- **C333** [quoted] A --plugin-dir plugin silently replaces a same-named installed marketplace plugin (unless managed-locked) — "**An installed marketplace plugin**: replaced silently." — [S131], "Name conflicts"
- **C334** [quoted] Cloud sessions don't install plugins enabled by repo .claude/settings.json — "A cloud session doesn't install the plugins a repository turns on under [`enabledPlugins`]" — [S132], "What carries over from your setup" table
- **C335** [quoted] Skills can bundle supporting files; SKILL.md should reference them so Claude knows when to load them — "Reference supporting files from `SKILL.md` so Claude knows what each file contains and when to load it" — [S126], "Add supporting files"
- **C336** [quoted] Local skills attach files named by `@` references (stated by contrast: synced skills leave @ literal) — "doesn't attach the files that `@` references name the way it does for a local skill" — [S126], "How Claude Code handles the body of a synced skill"
- **C337** [quoted] ${CLAUDE_SKILL_DIR} resolves to the skill's directory, usable to reference bundled files — "Use this in bash injection commands to reference scripts or files bundled with the skill, regardless of the current working directory." — [S126], "Available string substitutions"
- **C338** [quoted] CLAUDE.md @path imports: relative to the importing file, recursive up to 4 hops — "Imported files can recursively import other files, with a maximum depth of four hops." — [S13], "Import additional files"
- **C339** [measured] claude-code-action `plugins` and `plugin_marketplaces` inputs first shipped in v1.0.15 (2025-10-27); v1.0.14 contains none of the three plugin commits (#638, #642, #644) — Own measurements, M16, M17
- **C340** [measured] Local-path marketplaces in `plugin_marketplaces` (#761) first shipped in v1.0.28 (2026-01-05) — Own measurements, M16, M17
- **C341** [measured] Latest release is v1.0.243 (2026-10-06); floating tag `v1` is identical to v1.0.243; install-plugins.ts and the root action.yml unchanged (base-action/action.yml changed: CC 2.1.285→2.1.291) between v1.0.237 and v1.0.243 — Own measurements, M15, M18
- **C342** [quoted] The action validates marketplace inputs: must be https URL ending in `.git` (or a local path); no `owner/repo` shorthand, no `#ref` fragment — "/^https:\/\/[a-zA-Z0-9\-._~:/?#[\]@!$&'()*+,;=%]+\.git$/;" — [S133], L7-8 (identical at v1.0.243, M18)
- **C343** [quoted] The action runs `claude plugin marketplace add`, then `claude plugin install`, sequentially, aborting on the first failure — "If any plugin fails validation or installation (stops on first error)" — [S133], L210; addMarketplace L191-201
- **C344** [inference] Passing `extraKnownMarketplaces`/`enabledPlugins` through the `settings` input would place them at user scope; the trust gate of [C321] is documented only for a repository's .claude/settings.json, so whether user-scope entries load in a -p run is neither documented nor verified — from [C16], [C321], [C320]
- **C345** [quoted] `--add-dir` in `claude_args` is converted into SDK `additionalDirectories` (accumulating flag) — "const additionalDirectories = extraArgs["add-dir"]" — [S134], L210; flag list L22
- **C346** [inference] Checking out a private skills repo in a prior step and passing `--add-dir <path>` in `claude_args` may load its `.claude/skills` on the runner without a marketplace, depending on whether SDK additionalDirectories behaves like --add-dir (loads skills) or like permissions.additionalDirectories (does not, [C305]); not verified — from [C302], [C305], [C307], [C345]
- **C347** [inference] A PR that edits `.claude/skills/*` does not run its own edited skills on that PR's action run; the base-branch copy runs — from [C28]
- **C348** [quoted] Official docs: repo skills in the action need `actions/checkout` first, then `/skill-name` as prompt — "run `actions/checkout` before the `anthropics/claude-code-action` step so the skill files are available on the runner" — [S19], "Run a skill", L219
- **C349** [quoted] Official docs: `plugins` takes `plugin@marketplace`, marketplace name from the manifest, not the URL — "The `plugins` input takes `plugin-name@marketplace-name`, where the marketplace name comes from the marketplace's own manifest rather than its repository URL." — [S19], "Run a skill", L220
- **C350** [quoted] Practitioner report: private `plugin_marketplaces` clone fails with "repository not found" in the action even with GITHUB_TOKEN set, because no git credential is configured before install — "Git fails to authenticate during `git clone`" — [S135], issue body, 2026-01-22, open
- **C351** [quoted] Workaround: GitHub App token + global `insteadOf` rewrite in a step before the action — "x-access-token:${{ steps.generate-claude-token.outputs.token }}@github.com/" — [S136], comment 3848078413
- **C352** [quoted] Alternative workaround shipped by another org: sparse-checkout the skill dir and point the prompt at SKILL.md, bypassing plugins — "sparse-checkout the skill directory out of the marketplace repo ourselves" — [S137], comment 4298075590
- **C353** [measured] The fix PR (#1247, configure git credentials before installPlugins) is still open/unmerged as of 2026-10-06 — Own measurements, M19
- **C354** [quoted] `plugin_marketplaces` cannot pin a ref; always clones default-branch HEAD (feature request open) — "Currently, `plugin_marketplaces` only accepts URLs in the form `https://github.com/user/marketplace.git` and always clones the HEAD of the default branch." — [S138], issue body, 2026-04-17, open
- **C355** [quoted] The CLI accepts `#tag` fragments; the action's regex blocks them; SHA in fragment fails at CLI level too — "Only the action's `MARKETPLACE_URL_REGEX` blocks it, since it anchors on `\.git$`." — [S139], comment 5625753255 (v1.0.218 / CC 2.1.265)
- **C356** [quoted] Repeated `--plugin-dir` in `claude_args` silently collapses to the last one (not an accumulating flag) — "`--plugin-dir A --plugin-dir B` reaches the CLI as `B` alone, silently dropping `A`" — [S140], issue body, 2026-08-26, open
- **C357** [quoted] Skill-as-prompt in the action can exit immediately (a ~44 ms, 1-turn run reported in the issue body); one commenter reports it working by instructing the model to use the skill and including `Skill` in `--allowedTools` — "I got this working by instructing it to use the skill, and to ensure `Skill` is included in the list of `--allowedTools`" — [S141], comment 4126098248
- **C358** [quoted] Regression report: plugin skill installs (user scope) but `Skill` execution fails in v1 after SHA fad22eb — "invoking a plugin skill via the `prompt` parameter no longer works" — [S142], issue body, 2026-06-30, open, 0 comments
- **C359** [quoted] Symlinked `.claude/skills/<name>` pointing outside the restore set crashed restoreConfigFromBase (May 2026); later reruns on main no longer reproduce, trigger unidentified — "the exact trigger is still unidentified on any platform tested so far" — [S143], comment 5734160767; issue open
- **C360** [quoted] Stacked skills (`/a /b`) load only the first skill under `-p`/SDK; maintainer reproduced — "On the `--print` / SDK path it silently does nothing" — [S144], issue body (2.1.233); confirmed in comment 5321514618
- **C361** [quoted] User measurement: omitting `user` from `--setting-sources` drops all plugins and `~/.claude/skills` — "every plugin, including the plugins' hooks and skills" — [S145], issue body, "Dropped when `user` is omitted" list (2.1.261)
- **C362** [quoted] Committing `enabledPlugins` + `extraKnownMarketplaces` to a repo did not load the plugin without a per-project install record (2.1.212) — "the plugin's skills and hooks are silently absent — no warning, no auto-install." — [S146], issue body, open
- **C363** [quoted] Marketplace `autoUpdate` refreshed the clone but not installed plugins (2.1.212) — "refreshes the marketplace clone but never updates existing installs" — [S146], issue body
- **C364** [quoted] Independent repro (2.1.228, Windows, incl. `-p`): only explicit per-project `claude plugin update` moved installs; session start did not register a settings-sourced marketplace — "an explicit `claude plugin marketplace add` was required" — [S147], comment 5258983363
- **C365** [quoted] Skills-dir plugins are scanned before the trust dialog is answered; load only after reload/relaunch (maintainer repro 2.1.234) — "the plugin is scanned before you answer it, so it only loads after `/reload-plugins` or a relaunch." — [S148], comment 5322721679; issue closed not_planned (stale)
- **C366** [quoted] A CLAUDE.md `@import` pinned into a versioned plugin cache path silently kept resolving to the old version after update — "all sit on disk and the pinned import keeps resolving — to the old copy." — [S149], issue body, 2026-09-17, open
- **C367** [quoted] An unresolvable `@import` in CLAUDE.md is left as literal text with no warning (2.1.274) — "keeps the import line verbatim, and shows no warning that it did not resolve" — [S149], issue body, item 2
- **C368** [quoted] Hooks can inject text (`additionalContext`, capped) but cannot load a skill or file — "The same hook cannot load a skill either, and pasting is not an option there:" — [S150], issue body, feature request, open
- **C369** [quoted] agentskills.io spec: `references/` holds docs agents read when needed — "Contains additional documentation that agents can read when needed:" — [S151], "references/" section, L227
- **C370** [quoted] agentskills.io spec: reference files are loaded on demand — "Agents load these on demand, so smaller files mean less use of context." — [S151], L233
- **C371** [quoted] agentskills.io spec: resources load only when required (progressive disclosure tier 3) — "are loaded only when required" — [S151], "Progressive disclosure", L249
- **C372** [quoted] agentskills.io spec: file references are relative to the skill root — "When referencing other files in your skill, use relative paths from the skill root:" — [S151], "File references", L255
- **C373** [quoted] agentskills.io spec: keep references one level deep — "Keep file references one level deep from `SKILL.md`. Avoid deeply nested reference chains." — [S151], "File references", L264
- **C374** [quoted] agentskills.io spec: scripts should be self-contained or document dependencies — "Be self-contained or clearly document dependencies" — [S151], "scripts/" section, L219
- **C375** [inference] The agentskills.io spec defines no include/import mechanism and nothing about files outside the skill directory; cross-skill shared text has no portable primitive there — from [C369]-[C374] (spec read in full; absence)
- **C376** [inference] For a plugin-distributed skill set, a shared contract file survives the cache copy only if it sits inside the plugin dir, or is symlinked from elsewhere in the same marketplace (dereferenced); `../shared` outside the plugin is lost (for marketplace-copied plugins; local-path and copy-mode command plugins keep only in-plugin symlinks) — from [C330], [C331]
- **C377** [quoted] Maintainer triage (2.1.233, Linux, freshly trusted folder): repo-committed `extraKnownMarketplaces` + `enabledPlugins` with no prior install now auto-registers the marketplace and the plugin's skills load (supersedes the older [C362]/[C364] reports for skills) — "the marketplace was registered automatically and the plugin's skills loaded and ran" — [S152], comment 5415813477 (bcherny, 2026-08-25)
- **C378** [quoted] Same triage: in that settings-enabled-but-not-installed state the plugin's hooks do not run — "in that state (a `SessionStart` hook never fired until we explicitly installed the plugin)" — [S152], comment 5415813477

## Disconfirming evidence

- [C51] — query: `gh search issues --repo anthropics/claude-code-action "workflow validation failed"` — #443, #722 and #1314 show the same 401 "identical content" error, also in reusable workflows, so the rule applies beyond the case of a PR adding a new workflow. Nothing found against the `github_token` bypass.
- [C50] — query: `gh search issues --repo anthropics/claude-code-action "timeout"` — #716: an App token from create-github-app-token expires after 1 hour, which is a cost of the `github_token` route on long jobs. Nothing found against the bypass itself.
- [C26] — query: `gh search issues --repo anthropics/claude-code-action "AGENTS.md"` — [C30] (#1696) notes that at CC 2.1.235 `AGENTS.md` was not discovered natively, which fits the ≥2.1.277 gate. Nothing found reporting a failure at CC ≥2.1.277.
- [C38] — query: `gh search issues --repo anthropics/claude-code-action "max turns"` — counter-claim [C39]: the post-hoc guard false-fails (#1795, #1758). #1177 ("max_turns never passed") is superseded at v1.0.237.
- [C44] — query: `gh search issues --repo anthropics/claude-code-action "timeout"` — [C43] (#1852) and #1462 ("Headless run reports success after agent backgrounds work and ends turn") both count against "subagents just work". #1881 is a feature request for a wall-clock limit, which confirms there is no built-in one.
- [C36] — query: `gh search issues --repo anthropics/claude-code-action "WebSearch"` — #690 (2025): `--allowedTools` did not lift the default WebSearch/WebFetch disable. It predates the dead-code note [C35]. Nothing newer found.
- [C53] — query: `gh search issues --repo anthropics/claude-code-action "allowed_bots"` — #1299 and #1348 are failure modes of the actor check, not claims against it. Nothing found against.
- [C62] — query: `gh search issues --repo anthropics/claude-code-action "subscription"` and `"oauth token subscription"` — reliability problems with the subscription path: [C63] (#1614), plus #1613, #1386 (OAuth hangs on a hosted runner) and #727 (no refresh tokens). Nothing found saying that subscription use on runners is prohibited.
- [C348] — query: `gh search issues --repo anthropics/claude-code-action "skill"` (also "skills not loading", "slash command prompt") — counter-evidence [C357] (#1458) and [C358] (#1003): skill-as-prompt in the action exits early or regressed. Repo skills are documented but fragile in practice.
- [C103] — query: `Claude Code setup-token GitHub Actions account banned subscription automation` (WebSearch), and HN Algolia `claude code subscription ban` — the February 2026 policy was stricter and has since been reworded ([C115], [C116], [C117]). Account bans exist for extreme multi-account volume [C118]. No report found of a ban for single-account CI use with setup-token.
- [C74] — query: `self-hosted GitHub Actions runner public repository compromised pull request attack persistence` (WebSearch) — no verified supporting report. HN Algolia `self-hosted runner pull request compromise` returned 0 hits. Nothing found against.
- [C91] — query: `Claude Code routines GitHub trigger issues labeled event supported` (WebSearch) — counter-claim [C120]: a third-party guide from April 2026 lists more events. The official doc, re-fetched on 2026-10-06, still lists only Pull request and Release [C93]. The official doc is preferred, but the event set clearly changes over time.
- [C87] — query: HN Algolia `agent sdk cost`; WebSearch `claude code headless "-p" runaway cost unexpected bill CI loop API key` — nothing relevant against the estimate claim. One verified report: an API key silently overrode the subscription. Runaway-loop amounts were found only unverified.
- [C104] — query: HN Algolia `claude code weekly limits` — [C119]: limits are revised every few months, so the absolute numbers in [C104] and [C105] should not be relied on.
- [C108] — no dedicated disconfirming search was run, for API tier spend caps or for cloud-VM compute cost. This is stated as a gap.
- [C123] — query: `GitHub Actions concurrency "queue: max" changelog pending runs no longer cancelled` — the changelog confirms that replacing the pending run is the default, and that only opt-in `queue: max` changes it [C184]. Nothing found against.
- [C125] — queue-full behaviour, compared across GitHub's own docs — minor wording conflict: the how-to says extra runs "are canceled" [C125], while the limits page says they "will be rejected" [C131]. The outcome is the same; the status word differs. Unresolved.
- [C138] — query: `GitHub Free private repository rulesets branch protection now available 2026 changelog` — nothing found against [C138], [C139], [C140]. No changelog loosens the Pro/Team requirement.
- [C135] — query: `"secrets: inherit" reusable workflow personal account different repository private not passed github community discussion` — inconclusive. The docs say same org or enterprise [C182], and the community thread did not settle the personal-account case.
- [C142] — query: `Copilot coding agent session timeout stuck no pull request created issue github community 2026` — nothing found against the 59-minute cap or the unassign/reassign retry [C144]. A snippet mentions a githubstatus incident (2026-03-19/20), but the incident page rendered no text, so it is unverified.
- [C164] — query: `mattpocock sandcastle GitHub Actions workflow run AFK agent issue label` — nothing found against [C159], [C160], [C164]. No Actions workflow published by sandcastle surfaced.
- [C154] — query: `OpenHands resolver GitHub Action still supported 2026 replacement openhands-resolver deprecated` — nothing found against the deprecation. The old docs page returns "Page Not Found", and the docs index points to the hosted resolver [C187].
- [C167] — query: `agentic pull requests merged rate study 2026 Claude Code Copilot agent PRs abandoned unmerged arXiv` — counter-evidence found:
  - Rejection overstates agent error [C172].
  - The fix-PR merge rate is 65.0% [C168].
  - First-party Copilot in dotnet/runtime reaches 68.6% merged once set up properly [C173], [C174].
  - Acceptance rates depend on the population and on setup.
- [C179] — idempotency, checked in the resolver's source rather than by search — the resolver has a reuse path, but only when invoked on an existing PR [C180]. Re-pickup of an issue still forks a new `-tryN` branch.
- [C241] — query: `CodeRabbit AI generated pull requests more issues defects report` — counter-claim [C263]: a vendor report finds about 1.7x more issues in AI-co-authored PRs. The result is vendor-specific.
- [C264] — query: `PromptPwnd disputed OR earlier prompt injection GitHub Actions AI agent before 2025 first exploit` — counter-claim [C281]: Comment and Control reported a Claude Code action injection before PromptPwnd. "First" is contested; the vulnerability class is not.
- [C250] — query: `empirical study code review reduces production defects change failure rate evidence pre-merge review vs post-merge` — counter-claim [C255] (snippet only): unreviewed commits carry over twice the bug risk. This supports keeping review, and it adds nuance to [C262].
- [C215] — query: `Claude Code permission deny rules bypass python script subprocess sandbox headless GitHub Actions bubblewrap` — confirmed, nothing found against. Two related findings:
  - The sandbox fails open by default [C239].
  - Deny rules do apply to recognised Bash file commands [C214]; they do not reach subprocesses.
- [C210] — no web search here: the vendor doc was re-read for any check on the issue's author. It describes only a check on the triggering actor. This supports AP1, but it is not an independent disconfirmation.
- [C222] — no separate disconfirming search. The claim rests on the GitHub doc alone, plus our own `unblock-ready` comment, which agrees [C224].
- [C309] — query: `skills print mode`, `skills headless`, `skills non-interactive` (anthropics/claude-code issues) — counter-cases found:
  - Stacked `/a /b` loads only the first skill under `-p` [C360].
  - `--setting-sources` without `user` drops plugins and personal skills [C361].
  - Skill-as-prompt in the action fails [C357], [C358].
  - Nothing found showing a single `/skill` failing under plain `claude -p` [C20].
- [C316] — query: `private marketplace auth`, `private marketplace token`, `marketplace ssh https clone`, `gh auth setup-git marketplace` — counter-case: the action configures no git credentials before the marketplace clone, and the fix is unmerged ([C350], [C351], [C353]). Nothing found against the documented `GH_TOKEN` plus `gh auth setup-git` path in a plain CLI run [C319].
- [C323] — query: `extraKnownMarketplaces trust`, `hasTrustDialogAccepted plugins`, `enabledPlugins not installed` — counter-evidence:
  - Older versions silently dropped the plugin ([C362], [C364]).
  - A maintainer says this is fixed for skills, not hooks ([C377], [C378]).
  - A skills-dir plugin is scanned before the trust answer [C365].
  - Unresolved tension: [C377] reports a git-source marketplace plugin auto-loading, while [C323] says externally-sourced entries do not auto-install.
- [C363] — query: `plugin autoupdate`, `plugin stale cache`, `marketplace update not applied` — autoUpdate does not update installs [C363]. This is consistent with a manual update being the reliable path.
- [C330] — query: `plugin symlink cache shared` — [C366]: an import pinned into a versioned cache path resolves to the old copy. Nothing found against the copy semantics [C331].
- [C336] — query: `skill @ mention file not attached`, `SKILL.md @file reference expanded` — nothing found against. The direct probe failed on auth (M20), so the claim rests on the docs wording only.
- [C338] — query: `CLAUDE.md import not resolved` — [C367]: an unresolvable `@import` is kept verbatim with no warning.
- [C339] — check, not search: the plugin commits were compared against v1.0.14 (M17). v1.0.14 lacks all three commits, so nothing was found against.
- [C342] — query: `plugin_marketplaces ref pin` (claude-code-action) — [C354] and [C355] confirm that the input regex blocks `#ref`. Nothing found against.
- [C346] — query: `add-dir skills action`, `claude_args add-dir` (claude-code-action) — nothing found either way. The claim stays unverified.
- [C359] — query: `restoreConfigFromBase symlink` — symlinked skill directories crashed the config restore in May 2026. The trigger is not reproducible now.
- [C356] — query: `plugin-dir claude_args` — [C356] is itself the counter-case to assuming that repeated flags accumulate. Nothing newer reports a fix.
- [C313] — query: `claude code skills sync machines`, `claude code plugin marketplace` (hn.algolia.com, stories) — nothing substantive for or against.

## Coverage

| Channel | Read | Gap |
|---|---|---|
| Users | [S17], [S20], [S23], [S31], [S49], [S50], [S51], [S68], [S118], [S135], [S136], [S137], [S138], [S139], [S140], [S141], [S142], [S143], [S144], [S145], [S146], [S147], [S148], [S149], [S150], [S152] | Reddit not used; Hacker News and GitHub issue threads only |
| Specialists | [S1], [S2], [S3], [S4], [S5], [S6], [S7], [S8], [S9], [S10], [S11], [S12], [S13], [S14], [S15], [S16], [S18], [S19], [S21], [S22], [S24], [S25], [S26], [S27], [S28], [S29], [S30], [S32], [S33], [S34], [S35], [S36], [S37], [S38], [S39], [S40], [S41], [S42], [S43], [S44], [S45], [S46], [S47], [S48], [S52], [S54], [S55], [S56], [S57], [S58], [S59], [S60], [S61], [S62], [S63], [S64], [S65], [S66], [S67], [S69], [S70], [S71], [S72], [S73], [S74], [S81], [S82], [S83], [S84], [S85], [S86], [S87], [S88], [S89], [S90], [S91], [S92], [S93], [S94], [S95], [S97], [S98], [S99], [S100], [S101], [S102], [S106], [S107], [S108], [S122], [S124], [S126], [S127], [S128], [S129], [S130], [S131], [S132], [S133], [S134], [S151] | Devin and Jules docs not read |
| Data | [S75], [S76], [S77], [S78], [S79], [S80], [S109], [S110], [S111], [S112], [S113], [S114], [S115], [S116], [S117], [S119], [S120], [S121] | no study compares hold-for-human with merge-then-revert; Google's review study blocked |
| Adversarial | [S53], [S96], [S103], [S104], [S105], [S123], [S125] | no incident report specific to label-triggered agent workers found |

**Declared overruns.** All four sub-questions went past the ceiling of four searches and three full page reads. Each groups two or three of the issue's topics, and the issue asked for a four-substrate table and an attack-path list, which need more reads than one narrow question. Disconfirming searches are counted separately, as the skill requires.

**Tools that failed, and what was used instead.**

- The firecrawl connector reported low credits (and a 404 on one support article), so most reads used `curl` and `gh` against raw pages and the GitHub API.
- A local secret-pattern hook blocked a few commands and one ledger write as false positives (a quoted line shaped like a credential assignment; the word "environment"). No secret was involved; the commands were split or the quote narrowed to the variable name.
- The GitHub search API returned 403 (rate limit) on two plugin-cache queries; other queries partly covered them.
- Semantic Scholar returned 429; arXiv pages were read directly instead.
- research.google returned no text for Google's code-review study, so it is not quoted.
- bleepingcomputer.com sat behind a Cloudflare challenge; the weekly-limit claim rests on a Hacker News title only [C119].
- The githubstatus incident page rendered no text; the incident is marked unverified.
- `code.claude.com` `.md` pages open with a "Documentation Index" banner telling the reader to fetch the index. It was treated as page data. No fetched page's instructions were followed.

## Own measurements

### M1 — v1.0.237 resolves to the jarvis pin
Command: `gh api repos/anthropics/claude-code-action/git/ref/tags/v1.0.237 --jq '"\(.ref) \(.object.type) \(.object.sha)"'`; `gh api repos/anthropics/claude-code-action/git/tags/fccf022fdf80a6c41253d57e99293f208e484626 --jq '"\(.tag) -> \(.object.type) \(.object.sha)"'`; `gh api repos/anthropics/claude-code-action/commits/fd1c128679612beff4ca259c78021c506e8aa7a7` (committer date + first message line); `grep -n "claude-code-action@" .github/workflows/*.yml`
Output:
```
refs/tags/v1.0.237 tag fccf022fdf80a6c41253d57e99293f208e484626
v1.0.237 -> commit fd1c128679612beff4ca259c78021c506e8aa7a7
2026-09-29T19:29:07Z chore: bump Claude Code to 2.1.285 and Agent SDK to 0.3.285
.github/workflows/agent-dispatch.yml:51:        uses: anthropics/claude-code-action@fd1c128679612beff4ca259c78021c506e8aa7a7 # v1
.github/workflows/code-review.yml:157:        uses: anthropics/claude-code-action@fd1c128679612beff4ca259c78021c506e8aa7a7 # v1
```

### M2 — latest tag and floating v1
Command: `gh api "repos/anthropics/claude-code-action/tags?per_page=3" --jq '.[] | "\(.name) \(.commit.sha)"'`; `gh api repos/anthropics/claude-code-action/git/ref/tags/v1`, then `git/tags/<sha>`
Output:
```
v1.0.243 86d88e619d8e6caf07b5c3944dd14f441c533718
v1.0.242 6c690188da61cf16ee7debb28383ba67f02abb4c
v1.0.241 cab360f6565aa35a51d6ce9e43f1f4287c0a32ea
refs/tags/v1 tag 406a9aeaa7d4f7f7d03926349516b57ec096bf9a
v1 -> commit 86d88e619d8e6caf07b5c3944dd14f441c533718
```

### M3 — compare v1.0.237...v1.0.243
Command: `gh api repos/anthropics/claude-code-action/compare/v1.0.237...v1.0.243` (jq: ahead_by, file names, commit subject lines); `grep -c "description:" action.yml` at both tags
Output:
```
ahead_by=7
files: .github/egress-firewall.yaml, .github/scripts/check_workflow_hardening.py, .github/workflows/* (several), CLAUDE.md, base-action/action.yml, base-action/bun.lock, base-action/package.json, bun.lock, package.json, src/entrypoints/run.ts
ci: security hardening for GitHub Actions workflows that call Claude (#1867)
chore: bump Claude Code to 2.1.286 and Agent SDK to 0.3.286
... (one per version) ...
chore: bump Claude Code to 2.1.291 and Agent SDK to 0.3.291
description: count v1.0.237 = 46, v1.0.243 = 46
```

### M4 — repo visibility
Command: `gh repo view Osasuwu/jarvis --json visibility,isPrivate`
Output: {"isPrivate":false,"visibility":"PUBLIC"}

### M5 — action tag vs AFK workflow pin
Command: `gh api repos/anthropics/claude-code-action/git/ref/tags/v1.0.237 --jq '.object.sha,.object.type'`; `gh api repos/anthropics/claude-code-action/git/tags/fccf022fdf80a6c41253d57e99293f208e484626 --jq '.object.sha'`; `grep -n -E "runs-on|uses: anthropics|timeout-minutes|--max-turns" .github/workflows/agent-dispatch.yml`
Output:
fccf022fdf80a6c41253d57e99293f208e484626 / tag
fd1c128679612beff4ca259c78021c506e8aa7a7
38:    runs-on: ubuntu-latest
39:    timeout-minutes: 45
51:        uses: anthropics/claude-code-action@fd1c128679612beff4ca259c78021c506e8aa7a7 # v1
142:            --max-turns 100

### M6 — gh run list fields
Command: `gh run list --repo Osasuwu/jarvis --limit 5 --json conclusion,status,workflowName,event,createdAt,updatedAt`
Output (trimmed): [{"conclusion":"success","createdAt":"2026-10-06T11:07:16Z","event":"pull_request","status":"completed","updatedAt":"2026-10-06T11:07:24Z","workflowName":"PR Body Check"}, … {"conclusion":"failure",…,"updatedAt":"2026-10-06T11:09:46Z","workflowName":"Code Review"}, …]

### M7 — workflow run API object keys
Command: `gh api "repos/Osasuwu/jarvis/actions/runs?per_page=1" --jq '.workflow_runs[0] | keys | join(",")'`
Output: actor,artifacts_url,cancel_url,check_suite_id,check_suite_node_id,check_suite_url,conclusion,created_at,display_title,event,head_branch,head_commit,head_repository,head_sha,html_url,id,jobs_url,logs_url,name,node_id,path,previous_attempt_url,pull_requests,referenced_workflows,repository,rerun_url,run_attempt,run_number,run_started_at,status,triggering_actor,updated_at,url,workflow_id,workflow_url

### M8 — old OAuth sentence absent from current legal page
Command: `curl -sL https://code.claude.com/docs/en/legal-and-compliance.md` then python `'in any other product, tool, or service' in text`
Output: legal old sentence present: False

### M9 — visibility and Free-plan protection status of the operator's repos
Command: `gh repo list Osasuwu --limit 20 --json name,visibility --jq '.[] | "\(.name) \(.visibility)"'`
Output: jarvis-private PRIVATE / jarvis PUBLIC / jarvis-oss PUBLIC / claude-plugins-official PUBLIC / music-intel-mcp PUBLIC / like-current-song PUBLIC / awesome-android-apps PUBLIC / android-foss PUBLIC / claude-session-distill PUBLIC / redrobot PRIVATE / farming-evolution PUBLIC / dnd-calendar PUBLIC / Jarvis_planing PUBLIC / GitHub PRIVATE / Real-ESRGAN PUBLIC / EXAM PUBLIC / RL_Game PUBLIC / ML_Reinforcement_learning PUBLIC / Module_13_Lab PUBLIC / Module_13_Pr PUBLIC
Command: `gh api repos/Osasuwu/jarvis-private --jq '{allow_auto_merge, visibility, default_branch}'`
Output: {"allow_auto_merge":false,"default_branch":"master","visibility":"private"}
Command: `gh api repos/Osasuwu/jarvis-private/branches/master/protection`
Output: {"message":"Branch not protected","documentation_url":"https://docs.github.com/rest/branches/branch-protection#get-branch-protection","status":"404"}
Command: `gh api repos/Osasuwu/jarvis-private/rulesets`
Output: []

### M10 — OpenHands resolver workflow at tag 1.0.0: label removal, concurrency, timeout
Command: `curl -sL https://raw.githubusercontent.com/OpenHands/OpenHands/1.0.0/.github/workflows/openhands-resolver.yml -o oh-wf.yml; for p in removeLabel remove-label concurrency timeout-minutes "inputs.max_iterations || 50"; do printf "%s: " "$p"; grep -cF "$p" oh-wf.yml; done; grep -nF -- "--send-on-failure" oh-wf.yml; grep -nF "Fallback Error Comment" oh-wf.yml`
Output:
removeLabel: 0
remove-label: 0
concurrency: 0
timeout-minutes: 0
inputs.max_iterations || 50: 1
302:              --send-on-failure | tee branch_result.txt && \
418:      - name: Fallback Error Comment

### M11 — branch protection, rulesets, repo settings, CODEOWNERS
Command: `gh api repos/Osasuwu/jarvis/branches/main/protection --jq '{strict:.required_status_checks.strict,checks:.required_status_checks.checks,enforce_admins:.enforce_admins.enabled,allow_force_pushes:.allow_force_pushes.enabled,reviews:(.required_pull_request_reviews // "absent")}'`
Output: {"allow_force_pushes":false,"checks":[{"app_id":15368,"context":"require-linked-issue"},{"app_id":15368,"context":"pytest"},{"app_id":null,"context":"code-gate"},{"app_id":null,"context":"gitleaks"},{"app_id":15368,"context":"waiting-human-review"}],"enforce_admins":false,"reviews":"absent","strict":true}
Command: `gh api repos/Osasuwu/jarvis/rulesets`
Output: []
Command: `gh api repos/Osasuwu/jarvis --jq '{visibility,allow_auto_merge,owner:.owner.login}'`
Output: {"allow_auto_merge":true,"owner":"Osasuwu","visibility":"public"}
Command: `git ls-files | grep -ci codeowners`
Output: 0

### M12 — repo-level Claude settings
Command: `cat -n .claude/settings.json` (@ c6c848f)
Output: the top-level key is "hooks" only; no "permissions" block. PreToolUse matchers: "Edit|Write|NotebookEdit" (protected-files hook) and "Bash" (secret scanner).

### M13 — #1894 comments
Command: `gh issue view 1894 --json title,body,state,comments`
Output: ..."comments":[]...

### M14 — merge-train.yml presence
Command: `git ls-files | grep -i merge-train`
Output: (empty)
Command: `git log --oneline -1 --diff-filter=D -- .github/workflows/merge-train.yml`
Output: d2f3e7b refactor(ci): cut branch protection to code-gate/require-linked-issue/pytest/gitleaks (#1796) (#1835)

### M15 — latest claude-code-action release; v1 tag vs v1.0.243
Command: `gh api "repos/anthropics/claude-code-action/releases?per_page=5"`; `gh api repos/anthropics/claude-code-action/git/ref/tags/v1`; `gh api repos/anthropics/claude-code-action/compare/v1.0.243...v1`
Output:
v1.0.243 2026-10-06T04:03:51Z; v1.0.242 2026-10-05T23:38:07Z
v1 tag SHA 406a9aeaa7d4f7f7d03926349516b57ec096bf9a
v1.0.243 tag object 19981754ca4a7909e111121004efb75afe23c747
v1 vs v1.0.243: identical ahead_by=0 behind_by=0

### M16 — dates of the plugin-input commits
Command: `gh api repos/anthropics/claude-code-action/commits/<sha>`
Output:
d4c09790f5 2025-10-26T03:47:06Z feat: add plugins input to install Claude Code plugins (#638)
7b914ae5c0 2025-10-26T22:47:23Z feat: add plugin_marketplaces input for dynamic marketplace installation (#642)
29fe50368c 2025-10-27T16:01:34Z feat: change plugins input from comma-separated to newline-separated (#644)
653f9cd7a3 2026-01-05T10:43:32Z feat: support local plugin marketplace paths (#761)

### M17 — first tags containing those commits
Command: `gh api repos/anthropics/claude-code-action/compare/<sha>...<tag> --jq .status` ("ahead" = the tag contains the commit); `gh api repos/anthropics/claude-code-action/releases/tags/<tag> --jq .published_at`
Output:
v1.0.14: behind for all three plugin commits
v1.0.15: ahead for all three plugin commits
v1.0.27 vs 653f9cd7a3: behind
v1.0.28 vs 653f9cd7a3: ahead
v1.0.15 published 2025-10-27T23:57:39Z
v1.0.28 published 2026-01-05T20:41:03Z

### M18 — changes between v1.0.237 and v1.0.243
Command: `diff -q ip237.ts ip243.ts` (raw install-plugins.ts at both tags); `gh api repos/anthropics/claude-code-action/compare/v1.0.237...v1.0.243 --jq '[.files[].filename]'`, plus `.patch` for run.ts and base-action/action.yml
Output:
install-plugins.ts: SAME
status=ahead ahead_by=7 files=18
.github/egress-firewall.yaml .github/scripts/check_workflow_hardening.py .github/workflows/claude-review.yml .github/workflows/claude.yml .github/workflows/issue-triage.yml .github/workflows/test-base-action.yml .github/workflows/test-custom-executables.yml .github/workflows/test-mcp-servers.yml .github/workflows/test-settings.yml .github/workflows/test-structured-output.yml .github/workflows/workflow-hardening.yml CLAUDE.md base-action/action.yml base-action/bun.lock base-action/package.json bun.lock package.json src/entrypoints/run.ts
run.ts patch: -  const claudeCodeVersion = "2.1.285"; / +  const claudeCodeVersion = "2.1.291"; (base-action/action.yml: the same CLAUDE_CODE_VERSION bump). Root action.yml, install-plugins.ts, setup-claude-code-settings.ts and parse-sdk-options.ts are not in the list.

### M19 — status of the private-marketplace auth fix PR
Command: `gh api repos/anthropics/claude-code-action/pulls/1247` (number, state, merged, created_at, title)
Output: #1247 state=open merged=false created=2026-04-23T04:31:38Z title=fix: configure git credentials before installing plugin marketplaces

### M20 — local probe of `@` attach in a project SKILL.md (failed)
Command: `claude --version`; `claude -p "/probe" --setting-sources project --disallowedTools ...` in scratchpad/e/probe, with a SKILL.md referencing an `@`-file
Output:
2.1.291 (Claude Code)
Failed to authenticate: OAuth session expired and could not be refreshed

## Open questions

- Q1 — no new information: whether a clean GitHub-hosted runner loads `AGENTS.md` natively (the docs give a first-session caveat [C25]) — one probe run of the action on a repo with only `AGENTS.md`, asking the agent to quote a line from it.
- Q1 — not documented: the effective permission mode in agent mode when `claude_args` sets none [C36] — read the SDK default at the pinned CC version, or log `permission_denials` from one run's `execution_file`.
- Q1 — blocked: server-side internals of the workflow-validation check [C47] — only Anthropic can document them; the observable rule is stated in [C51].
- Q1 — no new information: the volume ceiling on subscription use in CI ("ordinary, individual" [C62], [C103]) — no published number; only a written answer from Anthropic would settle it.
- Q1 — not searched: egress restrictions on GitHub-hosted runners for the action — read the runner network docs, or probe one outbound request from a run.
- Q1 — no new information: absolute Max-plan session and weekly limit numbers; they are revised every few months [C119] — read the plan page at decision time, not from this report.
- Q1 — not verified: whether the action passes `--bare`, and what happens to it when `--bare` becomes the `-p` default [C77], [C79] — grep the pinned action's run path for `bare` on each bump.
- Q1 — not documented: what observability routines expose beyond the session view [C88] — a pilot routine run.
- Q1 — no disconfirming search run: API tier spend caps [C108] and cloud-VM compute cost for the SDK route — one search each against current pricing pages.
- Q2 — no new information: whether `secrets: inherit` passes secrets across repos owned by a personal account [C135], [C182] — one reusable-workflow call between two of the operator's repos.
- Q2 — sources disagree: whether runs past the `queue: max` ceiling end as "canceled" or "rejected" [C125], [C131] — observe the run status once the queue overflows.
- Q2 — not documented: how long a run may sit in a concurrency queue before GitHub drops it — GitHub docs or a long-queue observation.
- Q2 — not read: Devin and Jules pickup, lock and hand-back docs; the comparison covers Copilot, OpenHands and sandcastle only — read their current docs.
- Q3 — no source exists: no study compares holding agent PRs for a human against merge-then-revert [C282] — our own data: revert rate and time-to-detect over N merged AFK PRs.
- Q3 — not verified: AP9, whether the worker's PAT can merge past required checks while `enforce_admins=false` [C294] — read the PAT owner's role and test a merge on a throwaway branch protected the same way.
- Q3 — not verified: AP5, whether `gh issue edit` can remove a label from a PR with the worker's token [C290] — one call on a test PR.
- Q3 — not measured: the exact scopes of the worker PAT — `gh api -i user` with that token and read `X-OAuth-Scopes` (metadata only, not the value).
- Q3 — not verified: AP12, which ref the privileged workflow checks out before running `.github/scripts/unblock_ready.py` [C297] — read the workflow's checkout step.
- Q3 — blocked: Google's code-review study page refused fetching — read it from another mirror.
- Q4 — inconclusive: whether `@` references in a project `SKILL.md` attach files [C336]; the local probe failed on auth (M20) — rerun the probe with a working login.
- Q4 — not verified: whether the action's `settings` input reaches user scope, so personal skills could be configured there [C344] — one action run with a settings-defined skill path.
- Q4 — not verified: whether `--add-dir` in `claude_args` loads skills inside the action [C346] — one pilot run with a checked-out skills directory and `/skill-name` as the prompt.
- Q4 — open upstream: the fix for private `plugin_marketplaces` clones is unmerged [C353] — watch the upstream PR.
- Q4 — sources disagree: whether a repo-settings plugin from an external marketplace auto-installs [C323] vs [C377] — one fresh-runner test at the pinned CC version.
- Q4 — not read: skill-sync behaviour in the desktop app; the only reports found were desktop-only — test once on the desktop app.
- Label verdict open — the merge-policy answer has no hold-vs-revert evidence (Q3), and the security and skills recommendations rest on unverified paths (AP5, AP9, AP12; `--add-dir` and `settings` in the action, [C344]/[C346]); resolved unfavourably, these would change the Summary — settle them with the probes listed above and our own revert data.

## Sources

- [S1] claude-code-action v1.0.243 — src/entrypoints/run.ts — https://github.com/anthropics/claude-code-action/blob/v1.0.243/src/entrypoints/run.ts — read in full
- [S2] claude-code-action v1.0.237 — src/entrypoints/run.ts — https://github.com/anthropics/claude-code-action/blob/v1.0.237/src/entrypoints/run.ts — read in full
- [S3] claude-code-action v1.0.237 — src/github/context.ts — https://github.com/anthropics/claude-code-action/blob/v1.0.237/src/github/context.ts — read in full
- [S4] claude-code-action v1.0.237 — src/modes/detector.ts — https://github.com/anthropics/claude-code-action/blob/v1.0.237/src/modes/detector.ts — read in full
- [S5] claude-code-action v1.0.237 — docs/custom-automations.md — https://github.com/anthropics/claude-code-action/blob/v1.0.237/docs/custom-automations.md — read in full
- [S6] claude-code-action v1.0.237 — src/modes/agent/index.ts — https://github.com/anthropics/claude-code-action/blob/v1.0.237/src/modes/agent/index.ts — read in full
- [S7] claude-code-action v1.0.237 — src/create-prompt/index.ts — https://github.com/anthropics/claude-code-action/blob/v1.0.237/src/create-prompt/index.ts — read in full
- [S8] claude-code-action v1.0.237 — base-action/src/run-claude-sdk.ts — https://github.com/anthropics/claude-code-action/blob/v1.0.237/base-action/src/run-claude-sdk.ts — read in full
- [S9] claude-code-action v1.0.237 — base-action/src/setup-claude-code-settings.ts — https://github.com/anthropics/claude-code-action/blob/v1.0.237/base-action/src/setup-claude-code-settings.ts — read in full
- [S10] claude-code-action v1.0.237 — docs/configuration.md — https://github.com/anthropics/claude-code-action/blob/v1.0.237/docs/configuration.md — read in full
- [S11] claude-code-action v1.0.237 — base-action/src/parse-sdk-options.ts — https://github.com/anthropics/claude-code-action/blob/v1.0.237/base-action/src/parse-sdk-options.ts — read in full
- [S12] CC docs: headless — https://code.claude.com/docs/en/headless.md — passage
- [S13] CC docs: memory — https://code.claude.com/docs/en/memory.md — passage
- [S14] CC docs: env vars — https://code.claude.com/docs/en/env-vars.md — passage
- [S15] claude-code-action v1.0.237 — src/github/operations/restore-config.ts — https://github.com/anthropics/claude-code-action/blob/v1.0.237/src/github/operations/restore-config.ts — read in full
- [S16] claude-code-action v1.0.237 — docs/security.md — https://github.com/anthropics/claude-code-action/blob/v1.0.237/docs/security.md — read in full
- [S17] anthropics/claude-code-action issue #1696 — https://github.com/anthropics/claude-code-action/issues/1696 — passage
- [S18] claude-code-action v1.0.237 — src/modes/tag/index.ts — https://github.com/anthropics/claude-code-action/blob/v1.0.237/src/modes/tag/index.ts — read in full
- [S19] CC docs: Claude Code GitHub Actions — https://code.claude.com/docs/en/github-actions.md — read in full
- [S20] anthropics/claude-code-action issue #1795 — https://github.com/anthropics/claude-code-action/issues/1795 — passage
- [S21] claude-code-action v1.0.237 — docs/migration-guide.md — https://github.com/anthropics/claude-code-action/blob/v1.0.237/docs/migration-guide.md — read in full
- [S22] CC docs: subagents — https://code.claude.com/docs/en/sub-agents.md — passage
- [S23] anthropics/claude-code-action issue #1852 — https://github.com/anthropics/claude-code-action/issues/1852 — passage
- [S24] claude-code-action v1.0.237 — src/github/token.ts — https://github.com/anthropics/claude-code-action/blob/v1.0.237/src/github/token.ts — read in full
- [S25] claude-code-action v1.0.237 — test/token.test.ts — https://github.com/anthropics/claude-code-action/blob/v1.0.237/test/token.test.ts — read in full
- [S26] claude-code-action v1.0.237 — src/github/validation/permissions.ts — https://github.com/anthropics/claude-code-action/blob/v1.0.237/src/github/validation/permissions.ts — read in full
- [S27] claude-code-action v1.0.237 — src/github/validation/actor.ts — https://github.com/anthropics/claude-code-action/blob/v1.0.237/src/github/validation/actor.ts — read in full
- [S28] claude-code-action v1.0.237 — action.yml — https://github.com/anthropics/claude-code-action/blob/v1.0.237/action.yml — read in full
- [S29] CC docs: authentication — https://code.claude.com/docs/en/authentication.md — passage
- [S30] CC docs: legal and compliance — https://code.claude.com/docs/en/legal-and-compliance.md — passage
- [S31] anthropics/claude-code-action issue #1614 — https://github.com/anthropics/claude-code-action/issues/1614 — passage
- [S32] GitHub: Actions billing — https://docs.github.com/en/billing/concepts/product-billing/github-actions — passage
- [S33] claude-code-action action.yml @ v1.0.237 — https://raw.githubusercontent.com/anthropics/claude-code-action/v1.0.237/action.yml — passage (inputs/outputs)
- [S34] GitHub: Secure use reference (self-hosted hardening) — https://docs.github.com/en/actions/reference/security/secure-use — passage
- [S35] GitHub: Self-hosted runners concept — https://docs.github.com/en/actions/concepts/runners/self-hosted-runners — read in full
- [S36] Agent SDK overview — https://code.claude.com/docs/en/agent-sdk/overview.md — read in full
- [S37] Agent SDK hosting — https://code.claude.com/docs/en/agent-sdk/hosting.md — passage
- [S38] Agent SDK secure deployment — https://code.claude.com/docs/en/agent-sdk/secure-deployment.md — passage
- [S39] Agent SDK TypeScript reference — https://code.claude.com/docs/en/agent-sdk/typescript.md — passage (SDKResultMessage)
- [S40] Agent SDK cost tracking — https://code.claude.com/docs/en/agent-sdk/cost-tracking.md — passage
- [S41] Routines — https://code.claude.com/docs/en/routines.md — read in full
- [S42] Claude Code on the web — https://code.claude.com/docs/en/claude-code-on-the-web.md — passage
- [S43] Anthropic Consumer Terms — https://www.anthropic.com/legal/consumer-terms — passage
- [S44] Support: What is the Max plan — https://support.claude.com/en/articles/11049741-what-is-the-max-plan — read in full
- [S45] Support: Using Claude Code with Pro/Max — https://support.claude.com/en/articles/11145838 — snippet only
- [S46] Manage costs — https://code.claude.com/docs/en/costs.md — passage
- [S47] Claude API rate limits — https://platform.claude.com/docs/en/api/rate-limits.md — passage
- [S48] Monitoring (OpenTelemetry) — https://code.claude.com/docs/en/monitoring-usage.md — passage
- [S49] Hacker News comment 47069641 (adastra22, story 47069299) — https://news.ycombinator.com/item?id=47069641 — passage
- [S50] HN 48903047 "Anthropic banned my thirteen 20x accounts" — https://news.ycombinator.com/item?id=48903047 — passage
- [S51] HN 49778641 / 48126429 / 48964950 weekly-limit titles — https://news.ycombinator.com/item?id=49778641 — snippet only
- [S52] Verdent "What is Claude Code routines" — https://www.verdent.ai/guides/what-is-claude-code-routines — passage
- [S53] The Hacker News: TensorFlow CI/CD flaw exposed supply chain — https://thehackernews.com/2024/01/tensorflow-cicd-flaw-exposed-supply.html?m=1 — snippet only
- [S54] Control workflow concurrency (GitHub Docs) — https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency — read in full
- [S55] Workflow syntax (GitHub Docs) — https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax — passage (timeout-minutes, secrets.inherit)
- [S56] Actions limits (GitHub Docs) — https://docs.github.com/en/actions/reference/limits — read in full
- [S57] Reusing workflow configurations, reference (GitHub Docs) — https://docs.github.com/en/actions/reference/workflows-and-actions/reusing-workflow-configurations — read in full
- [S58] Share across private repositories (GitHub Docs) — https://docs.github.com/en/actions/how-tos/reuse-automations/share-across-private-repositories — read in full
- [S59] GitHub's plans (GitHub Docs) — https://docs.github.com/en/get-started/learning-about-github/githubs-plans — passage
- [S60] About protected branches — https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches — passage (availability box)
- [S61] About rulesets — https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets — passage (availability box)
- [S62] Automatically merging a pull request — https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/incorporating-changes-from-a-pull-request/automatically-merging-a-pull-request — passage (availability box)
- [S63] Copilot on GitHub, cloud agent limitations — https://docs.github.com/en/copilot/concepts/copilot-surfaces/copilot-on-github — passage
- [S64] Troubleshoot Copilot cloud agent — https://docs.github.com/en/copilot/how-tos/use-copilot-agents/cloud-agent/troubleshoot-cloud-agent — read in full
- [S65] Copilot cloud agent risks and mitigations — https://docs.github.com/en/copilot/concepts/security-governance-and-network-settings/risks-and-mitigations — read in full
- [S66] Start Copilot sessions — https://docs.github.com/en/copilot/how-tos/use-copilot-agents/cloud-agent/start-copilot-sessions — passage
- [S67] OpenHands resolver README @1.0.0 — https://raw.githubusercontent.com/OpenHands/OpenHands/1.0.0/openhands/resolver/README.md — read in full
- [S68] OpenHands PR #14062 (remove V0 resolver) — https://github.com/OpenHands/OpenHands/pull/14062 — passage (PR body)
- [S69] OpenHands Cloud GitHub installation — https://docs.openhands.dev/openhands/usage/cloud/github-installation.md — read in full
- [S70] OpenHands resolver example caller @1.0.0 — https://raw.githubusercontent.com/OpenHands/OpenHands/1.0.0/openhands/resolver/examples/openhands-resolver.yml — read in full
- [S71] OpenHands resolver workflow @1.0.0 — https://raw.githubusercontent.com/OpenHands/OpenHands/1.0.0/.github/workflows/openhands-resolver.yml — read in full
- [S72] Sandcastle README @62307ab — https://raw.githubusercontent.com/mattpocock/sandcastle/62307ab65ad9f8414f7a4893d96328a0353b0c3f/README.md — read in full
- [S73] Sandcastle simple-loop template (prompt.md, main.mts) @62307ab — https://raw.githubusercontent.com/mattpocock/sandcastle/62307ab65ad9f8414f7a4893d96328a0353b0c3f/src/templates/simple-loop/prompt.md — read in full
- [S74] Sandcastle parallel-planner main.mts @62307ab — https://raw.githubusercontent.com/mattpocock/sandcastle/62307ab65ad9f8414f7a4893d96328a0353b0c3f/src/templates/parallel-planner/main.mts — passage (header, Promise.allSettled)
- [S75] AIDev: Studying AI Coding Agents on GitHub (arXiv 2602.09185) — https://arxiv.org/html/2602.09185v1 — passage (abstract, intro)
- [S76] The Rise of AI Teammates in SE 3.0 (arXiv 2507.15003) — https://arxiv.org/html/2507.15003v1 — passage (acceptance, turnaround sections)
- [S77] Why Are AI Agent Involved Pull Requests (Fix-Related) Remain Unmerged? (arXiv 2602.00164) — https://arxiv.org/html/2602.00164 — passage
- [S78] Why Are AI Agent Involved Pull Requests (Fix-Related) Remain Unmerged? — abstract page (arXiv 2602.00164) — https://arxiv.org/abs/2602.00164 — passage
- [S79] Where Do AI Coding Agents Fail? (arXiv 2601.15195) — https://arxiv.org/abs/2601.15195 — passage (abstract only)
- [S80] Why Are Agentic Pull Requests Merged or Rejected? (arXiv 2605.22534) — https://arxiv.org/abs/2605.22534 — passage (abstract only)
- [S81] Ten Months with Copilot Coding Agent in dotnet/runtime (Microsoft .NET blog) — https://devblogs.microsoft.com/dotnet/ten-months-with-cca-in-dotnet-runtime — passage (found via HN algolia; most of the body grepped)
- [S82] Re-running workflows and jobs (GitHub Docs) — https://docs.github.com/en/actions/how-tos/manage-workflow-runs/re-run-workflows-and-jobs — read in full
- [S83] OpenHands/OpenHands @ 1.0.0 — openhands/resolver/interfaces/github.py — https://raw.githubusercontent.com/OpenHands/OpenHands/1.0.0/openhands/resolver/interfaces/github.py — read in full
- [S84] OpenHands send_pull_request.py and interfaces/github.py @1.0.0 — https://raw.githubusercontent.com/OpenHands/OpenHands/1.0.0/openhands/resolver/send_pull_request.py — passage (branch naming, existing-PR path)
- [S85] Reusing workflow configurations, concepts (GitHub Docs) — https://docs.github.com/en/actions/concepts/workflows-and-actions/reusing-workflow-configurations — passage (composite vs reusable)
- [S86] Reuse workflows, how-to (GitHub Docs) — https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows — passage (secrets)
- [S87] Changelog 2026-05-07: concurrency groups now allow larger queues — https://github.blog/changelog/2026-05-07-github-actions-concurrency-groups-now-allow-larger-queues — read in full
- [S88] OpenHands docs index — https://docs.openhands.dev/llms.txt — passage (grep)
- [S89] jarvis @ c6c848f — .github/workflows/agent-dispatch.yml — https://github.com/Osasuwu/jarvis/blob/c6c848f/.github/workflows/agent-dispatch.yml — read in full
- [S90] jarvis @ c6c848f — .github/workflows/waiting-human-review.yml — https://github.com/Osasuwu/jarvis/blob/c6c848f/.github/workflows/waiting-human-review.yml — read in full
- [S91] jarvis @ c6c848f — docs/research/afk-orchestration-inventory-2026-10-01.md — https://github.com/Osasuwu/jarvis/blob/c6c848f/docs/research/afk-orchestration-inventory-2026-10-01.md — read in full
- [S92] jarvis @ c6c848f — .github/workflows/unblock-ready.yml — https://github.com/Osasuwu/jarvis/blob/c6c848f/.github/workflows/unblock-ready.yml — read in full
- [S93] jarvis @ c6c848f — .github/workflows/code-review.yml — https://github.com/Osasuwu/jarvis/blob/c6c848f/.github/workflows/code-review.yml — read in full
- [S94] jarvis @ c6c848f — docs/security/threat-model.md — https://github.com/Osasuwu/jarvis/blob/c6c848f/docs/security/threat-model.md — read in full
- [S95] jarvis @ c6c848f — .claude/settings.json — https://github.com/Osasuwu/jarvis/blob/c6c848f/.claude/settings.json — read in full
- [S96] Aikido, PromptPwnd — https://www.aikido.dev/blog/promptpwnd-github-actions-ai-agents — read in full
- [S97] claude-code-action docs/security.md @ fd1c128 — https://github.com/anthropics/claude-code-action/blob/fd1c128679612beff4ca259c78021c506e8aa7a7/docs/security.md — read in full
- [S98] Claude Code permissions — https://code.claude.com/docs/en/permissions — passage
- [S99] GitHub, Choosing permissions for a GitHub App — https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/choosing-permissions-for-a-github-app — passage
- [S100] GitHub, Approving a PR with required reviews — https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/reviewing-changes-in-pull-requests/approving-a-pull-request-with-required-reviews — passage
- [S101] GitHub, About code owners — https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners — passage
- [S102] GitHub, GITHUB_TOKEN — https://docs.github.com/en/actions/concepts/security/github_token — passage
- [S103] Invariant Labs, GitHub MCP exploited — https://invariantlabs.ai/blog/mcp-github-vulnerability — read in full
- [S104] Nx, s1ngularity post-mortem — https://nx.dev/blog/s1ngularity-postmortem — passage
- [S105] Guan, Comment and Control — https://oddguan.com/blog/comment-and-control-prompt-injection-credential-theft-claude-code-gemini-cli-github-copilot — read in full
- [S106] GitHub, Permissions required for fine-grained PATs — https://docs.github.com/en/rest/authentication/permissions-required-for-fine-grained-personal-access-tokens — passage
- [S107] GitHub, Deciding when to build a GitHub App — https://docs.github.com/en/apps/creating-github-apps/about-creating-github-apps/deciding-when-to-build-a-github-app — passage
- [S108] Claude Code sandboxing — https://code.claude.com/docs/en/sandboxing — passage
- [S109] Kraishan et al., post-merge outcomes of agent PRs — https://arxiv.org/abs/2609.17598 — passage
- [S110] Kraishan et al., post-merge outcomes of agent PRs — HTML v1, threats to validity (arXiv 2609.17598v1) — https://arxiv.org/html/2609.17598v1 — passage
- [S111] METR, SWE-bench-passing PRs not mergeable — https://metr.org/notes/2026-03-10-many-swe-bench-passing-prs-would-not-be-merged-into-main — read in full
- [S112] 2024 DORA report announcement — https://cloud.google.com/blog/products/devops-sre/announcing-the-2024-dora-report — passage
- [S113] DORA, Streamlining change approval — https://dora.dev/capabilities/streamlining-change-approval — read in full
- [S114] SWE-PRBench — https://arxiv.org/abs/2603.26130 — passage (abstract)
- [S115] LLM review vs diff size — https://arxiv.org/abs/2606.15689 — passage (abstract)
- [S116] AIDev CRA vs human review — https://arxiv.org/abs/2604.03196 — passage (abstract)
- [S117] "Four Eyes are Better than Two" (unibz) — https://bia.unibz.it/esploro/outputs/conferenceProceeding/Four-Eyes-are-Better-than-Two/991005772673701241 — snippet only
- [S118] Osasuwu/jarvis issue #1894 — https://github.com/Osasuwu/jarvis/issues/1894 — passage
- [S119] Watanabe et al., Claude Code agentic PRs — https://arxiv.org/abs/2509.14745 — snippet only (abstract)
- [S120] Bacchelli & Bird, Modern Code Review (Microsoft) — https://www.microsoft.com/en-us/research/publication/expectations-outcomes-and-challenges-of-modern-code-review — passage (abstract)
- [S121] CodeRabbit, State of AI vs human code — https://coderabbit.ai/blog/state-of-ai-vs-human-code-generation-report — passage (vendor)
- [S122] GitHub, Available rules for rulesets — https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets — passage
- [S123] GitHub Security Lab, Preventing pwn requests — https://securitylab.github.com/resources/github-actions-preventing-pwn-requests — passage
- [S124] GitHub, Events that trigger workflows — https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows — passage
- [S125] AWS security bulletin AWS-2025-015 (Amazon Q) — https://aws.amazon.com/security/security-bulletins/AWS-2025-015 — read in full
- [S126] CC docs: skills — https://code.claude.com/docs/en/skills.md — passage
- [S127] Plugins overview — https://code.claude.com/docs/en/plugins/overview.md — passage
- [S128] Create and distribute a plugin marketplace — https://code.claude.com/docs/en/plugin-marketplaces.md — passage
- [S129] Host a marketplace — https://code.claude.com/docs/en/plugins/host-marketplace.md — passage (auth, pinning, versioning, cache copy)
- [S130] Plugins for an organization — https://code.claude.com/docs/en/plugins/org.md — passage (extraKnownMarketplaces, trust, CI seed, sync install)
- [S131] How plugins load — https://code.claude.com/docs/en/plugins/loading.md — passage
- [S132] Cloud environments — https://code.claude.com/docs/en/cloud-environments.md — passage
- [S133] install-plugins.ts @v1.0.237 (identical @v1.0.243) — https://raw.githubusercontent.com/anthropics/claude-code-action/v1.0.237/base-action/src/install-plugins.ts — read in full
- [S134] parse-sdk-options.ts @v1.0.237 — https://raw.githubusercontent.com/anthropics/claude-code-action/v1.0.237/base-action/src/parse-sdk-options.ts — passage
- [S135] anthropics/claude-code-action issues #850, #1003, #1229, #1319, #1458, #1728 — https://github.com/anthropics/claude-code-action/issues/850 — read in full (body + comments via gh api)
- [S136] anthropics/claude-code-action issue #850, comment 3848078413 — https://github.com/anthropics/claude-code-action/issues/850#issuecomment-3848078413 — passage
- [S137] anthropics/claude-code-action issue #850, comment 4298075590 — https://github.com/anthropics/claude-code-action/issues/850#issuecomment-4298075590 — passage
- [S138] anthropics/claude-code-action issue #1229 — https://github.com/anthropics/claude-code-action/issues/1229 — passage
- [S139] anthropics/claude-code-action issue #1229, comment 5625753255 — https://github.com/anthropics/claude-code-action/issues/1229#issuecomment-5625753255 — passage
- [S140] anthropics/claude-code-action issue #1728 — https://github.com/anthropics/claude-code-action/issues/1728 — passage
- [S141] anthropics/claude-code-action issue #1003, comment 4126098248 — https://github.com/anthropics/claude-code-action/issues/1003#issuecomment-4126098248 — passage
- [S142] anthropics/claude-code-action issue #1458 — https://github.com/anthropics/claude-code-action/issues/1458 — passage
- [S143] anthropics/claude-code-action issue #1319, comment 5734160767 — https://github.com/anthropics/claude-code-action/issues/1319#issuecomment-5734160767 — passage
- [S144] anthropics/claude-code issue #87113 — https://github.com/anthropics/claude-code/issues/87113 — passage
- [S145] anthropics/claude-code issue #92254 — https://github.com/anthropics/claude-code/issues/92254 — passage
- [S146] anthropics/claude-code issues #26588, #81699, #83422, #87113, #87325, #92254, #93252, #95095, #95175, #98303 — https://github.com/anthropics/claude-code/issues/83422 — read in full (body + comments via gh api)
- [S147] anthropics/claude-code issue #83422, comment 5258983363 — https://github.com/anthropics/claude-code/issues/83422#issuecomment-5258983363 — passage
- [S148] anthropics/claude-code issue #87325, comment 5322721679 — https://github.com/anthropics/claude-code/issues/87325#issuecomment-5322721679 — passage
- [S149] anthropics/claude-code issue #95095 — https://github.com/anthropics/claude-code/issues/95095 — passage
- [S150] anthropics/claude-code issue #93252 — https://github.com/anthropics/claude-code/issues/93252 — passage
- [S151] Agent Skills specification — https://agentskills.io/specification.md — read in full
- [S152] anthropics/claude-code issue #83422, comment 5415813477 — https://github.com/anthropics/claude-code/issues/83422#issuecomment-5415813477 — passage

## Recommendations

This section is opinion, built on the findings above. It cites no claims and is not covered by the audit. Where a recommendation is a standing rule the agent or pipeline must follow, it names the carrier, picked by the order in `~/.claude/reference/baseline-carriers.md` (the cost of the rule being violated), and says why a cheaper carrier would not do.

**Substrate.**

1. Stay on claude-code-action on GitHub-hosted runners. It is the only option that is free on a public repo, documented for subscription auth, and needs no machine of ours. Do not add a self-hosted runner to a public repo. Revisit the Agent SDK only if we need egress control we cannot get from the sandbox.
2. Re-check the `--bare` default on every action bump, because bare mode ignores the subscription token. Carrier: a CI test that greps the pinned action's run path for `bare` and fails on a change. It is checkable on an artifact, so prose would be strictly worse.
3. Do not use background subagents in AFK runs; the action drops them and reports green. Carrier: the worker prompt, plus a check on the `execution_file` for unfinished background tasks if this ever bites. A tool-call hook cannot tell foreground from background reliably.
4. Read cost and turns from the action's `execution_file` (or OpenTelemetry) and store them per run. GitHub run data will never carry them.

**Orchestration and failure handling.**

5. Use `concurrency` with `queue: max`, keyed per issue (for example `afk-worker-<issue>`), and make every group name unique to its workflow. This is the lock none of the surveyed systems provides. Carrier: a CI test over `.github/workflows/*.yml` that asserts unique group names, because a collision silently cancels runs.
6. Make re-pickup resume the existing branch or PR for the issue rather than forking a new one. Duplicate agent PRs are a measured rejection cause, and no surveyed system solves this for us.

**Merge policy.**

7. Replace "hold everything" vs "merge and revert" with a deterministic, risk-tiered hold: LOW merges on green gates; HIGH and CRITICAL wait for a human. The tier comes from the diff (paths, size, protected files), not from the LLM review. Carrier: a CI gate (the `waiting-human-review` check is the natural place). A prompt-level rule would be decided by the same agent the hold is meant to check.
8. Start collecting our own revert rate and time-to-detect for merged AFK PRs. Without it the hold-vs-revert question stays open forever.

**Security.**

9. Move the worker to a GitHub App installation token (#1894). It closes or narrows AP4, AP5, AP6, AP8 and AP9 at once, because the worker stops being the owner. This is a configuration change, not a rule.
10. Turn on `enforce_admins`, and pin the source app for the `code-gate` and `gitleaks` required checks in branch protection. Carrier: branch protection settings. A spoofed status or an admin merge never reaches a hook or a test.
11. Snapshot or hash the issue body when `agent:dispatch` is applied, and have the worker refuse a body that changed after labelling (AP2). Carrier: the dispatch workflow (code). Only issues authored by write-access users should be dispatchable without an extra confirmation (AP1).
12. Protect `.github/**` and `AGENTS.md` with a CI path check plus CODEOWNERS. Carrier: a CI gate, not a PreToolUse hook. A hook only sees the agent's own tool calls; a Python subprocess under pytest writes past it (AP3).
13. Enable the Claude Code sandbox with `failIfUnavailable`, so a sandbox that cannot start fails the run instead of running unsandboxed. Add a network allowlist (AP4, AP11).
14. Restrict `gh issue edit` in the worker to the run's own issue (AP6). Carrier: a CI check on the run's API activity, or the App token's permission scope once item 9 lands. An allow-list pattern in the tool settings cannot express "only this issue number".
15. Fix the stale comment in `code-review.yml` that points to a non-owner App identity. The workflow it describes was deleted. Trivial; fold it into #1894.

**Skills single source.**

16. Pilot the cheapest route first: check out the skills repo in a step before the action and pass `--add-dir`. It is unverified in the action, so run one pilot before building on it. If it fails, fall back to a plugin with `CLAUDE_CODE_SYNC_PLUGIN_INSTALL=1` and the git-credential workaround, and watch the upstream fix.
17. Keep shared contract text inside the skill set's own directory tree (a file referenced by relative path), not in a cross-repo import. Spec-level includes do not exist, and plugin caching drops anything outside the plugin directory. Carrier for "the shared file exists and each skill references it": a test in the skills repo.

## Audit

| Claim | Verdict | Note |
|---|---|---|
| C1 | SUPPORTED | M1 output matches |
| C2 | SUPPORTED | M2 output matches |
| C3 | SUPPORTED | M3 output matches |
| C4 | SUPPORTED |  |
| C5 | SUPPORTED |  |
| C6 | PARTIAL | M3 shows the input-description count is 46 at both tags, not that the text is identical, and nothing cited shows the CC 2.1.285-2.1.291 bumps are immaterial; narrowed |
| C7 | SUPPORTED | quote is the array opener; the four events are at the cited lines 64-67 |
| C8 | SUPPORTED |  |
| C9 | SUPPORTED |  |
| C10 | SUPPORTED |  |
| C11 | SUPPORTED |  |
| C12 | SUPPORTED |  |
| C13 | SUPPORTED |  |
| C14 | SUPPORTED |  |
| C15 | SUPPORTED |  |
| C16 | SUPPORTED |  |
| C17 | SUPPORTED |  |
| C18 | SUPPORTED |  |
| C19 | SUPPORTED |  |
| C20 | SUPPORTED |  |
| C21 | SUPPORTED |  |
| C22 | SUPPORTED |  |
| C23 | SUPPORTED |  |
| C24 | SUPPORTED |  |
| C25 | SUPPORTED |  |
| C26 | PARTIAL | C25's caveat is the first session after upgrading from v2.1.276 or earlier; nothing cited says a fresh-install runner counts; claim narrowed |
| C27 | SUPPORTED |  |
| C28 | SUPPORTED | quote is the array opener; the eight paths are at the cited lines |
| C29 | SUPPORTED |  |
| C30 | SUPPORTED | open/unmerged state re-read via gh api |
| C31 | PARTIAL | the nested-CLAUDE.md part (#1270) rests on no listed claim; removed |
| C32 | PARTIAL | git Bash tools are added only without API commit signing (else file-ops MCP tools); condition added |
| C33 | SUPPORTED |  |
| C34 | SUPPORTED |  |
| C35 | SUPPORTED |  |
| C36 | SUPPORTED | checked against cited lines 93-132 |
| C37 | SUPPORTED |  |
| C38 | PARTIAL | source shows absent max-turns leaves maxTurns undefined; "means no limit" is SDK behaviour not in the source; narrowed |
| C39 | SUPPORTED |  |
| C40 | SUPPORTED |  |
| C41 | SUPPORTED |  |
| C42 | SUPPORTED |  |
| C43 | SUPPORTED | "step finished green" is in the issue body |
| C44 | PARTIAL | "Agent tool available, the action removes nothing" and "foreground subagents work" rest on no listed claim; narrowed to the background-subagent finding |
| C45 | SUPPORTED |  |
| C46 | SUPPORTED |  |
| C47 | SUPPORTED |  |
| C48 | SUPPORTED |  |
| C49 | SUPPORTED | run.ts:179-182 catches the skip error and returns |
| C50 | SUPPORTED |  |
| C51 | SUPPORTED |  |
| C52 | SUPPORTED |  |
| C53 | SUPPORTED |  |
| C54 | SUPPORTED |  |
| C55 | PARTIAL | source says scheduled runs are attributed to a repository user, "usually" the one who last changed the cron; "usually" restored |
| C56 | SUPPORTED |  |
| C57 | SUPPORTED |  |
| C58 | SUPPORTED |  |
| C59 | SUPPORTED |  |
| C60 | SUPPORTED |  |
| C61 | SUPPORTED |  |
| C62 | PARTIAL | C60 says the advertised Pro/Max limits assume ordinary, individual usage; it is not stated as a bound on permitted use; reworded |
| C63 | SUPPORTED |  |
| C64 | SUPPORTED |  |
| C65 | SUPPORTED |  |
| C66 | SUPPORTED |  |
| C67 | SUPPORTED |  |
| C68 | SUPPORTED | M4 output matches |
| C69 | PARTIAL | that the AFK lane authenticates with an OAuth token is an unstated premise (M5 shows no auth line), and "only marginal cost" is not established; narrowed |
| C70 | SUPPORTED |  |
| C71 | SUPPORTED |  |
| C72 | SUPPORTED |  |
| C73 | SUPPORTED |  |
| C74 | SUPPORTED |  |
| C75 | SUPPORTED |  |
| C76 | SUPPORTED |  |
| C77 | SUPPORTED |  |
| C78 | SUPPORTED |  |
| C79 | SUPPORTED |  |
| C80 | SUPPORTED |  |
| C81 | SUPPORTED |  |
| C82 | SUPPORTED |  |
| C83 | SUPPORTED |  |
| C84 | SUPPORTED |  |
| C85 | SUPPORTED |  |
| C86 | SUPPORTED | fields and error subtypes checked in the SDKResultMessage type |
| C87 | SUPPORTED |  |
| C88 | SUPPORTED |  |
| C89 | PARTIAL | source says the session runs "without stopping for approval apart from some artifact actions"; "fully" dropped and exception added |
| C90 | SUPPORTED |  |
| C91 | SUPPORTED |  |
| C92 | SUPPORTED |  |
| C93 | PARTIAL | C91/C92 show issue-label events cannot trigger a routine natively; "would need an Action calling /fire" overstates; this is one way to bridge it, not the only one |
| C94 | SUPPORTED |  |
| C95 | SUPPORTED |  |
| C96 | PARTIAL | source limits this to "Anthropic-hosted environments"; condition added |
| C97 | SUPPORTED |  |
| C98 | SUPPORTED |  |
| C99 | SUPPORTED |  |
| C100 | SUPPORTED |  |
| C101 | SUPPORTED |  |
| C102 | SUPPORTED |  |
| C103 | PARTIAL | C60 says advertised limits assume ordinary, individual usage, not that volume is bounded by it; C101's enforcement is of the authentication restrictions; reworded |
| C104 | SUPPORTED |  |
| C105 | SUPPORTED |  |
| C106 | UNSUPPORTED | S45 read (Aug 19, 2026 version): no prompt-count figure on the page; removed |
| C107 | PARTIAL | source says "Across enterprise deployments, the average cost is around $13"; scope added |
| C108 | PARTIAL | source adds "unless you request a higher limit sooner"; condition added |
| C109 | SUPPORTED |  |
| C110 | SUPPORTED |  |
| C111 | SUPPORTED |  |
| C112 | SUPPORTED |  |
| C113 | SUPPORTED | M7 key list has no token or cost field |
| C114 | PARTIAL | M7 shows many fields, not "only pass/fail and duration"; narrowed to "no token or cost fields" |
| C115 | SUPPORTED | date and story checked via HN Algolia API |
| C116 | SUPPORTED | M8 output matches |
| C117 | PARTIAL | rests on an HN commenter's quotation of the old page being accurate; the condition is now stated |
| C118 | SUPPORTED | date and points checked via HN Algolia API |
| C119 | PARTIAL | S51 read: it supports a 17% cut to weekly limits (story 2026-09-20) and a commenter calls the earlier increase temporary; the +50% and May-Aug figures are not on the page; relabelled quoted and narrowed |
| C120 | SUPPORTED |  |
| C121 | UNSUPPORTED | S53 read: TensorFlow self-hosted-runner article; no runner-images or persistence passage; removed |
| C122 | SUPPORTED |  |
| C123 | SUPPORTED |  |
| C124 | SUPPORTED |  |
| C125 | SUPPORTED |  |
| C126 | SUPPORTED |  |
| C127 | SUPPORTED |  |
| C128 | SUPPORTED |  |
| C129 | SUPPORTED |  |
| C130 | SUPPORTED |  |
| C131 | SUPPORTED |  |
| C132 | SUPPORTED |  |
| C133 | SUPPORTED |  |
| C134 | SUPPORTED | quote matched across flattened table cells |
| C135 | SUPPORTED |  |
| C136 | SUPPORTED |  |
| C137 | SUPPORTED |  |
| C138 | SUPPORTED | verified in HTML fetch of the docs page (the .md version omits the "Who can use this feature?" box) |
| C139 | SUPPORTED | verified in HTML fetch of the docs page (the .md version omits the "Who can use this feature?" box) |
| C140 | SUPPORTED | verified in HTML fetch of the docs page (the .md version omits the "Who can use this feature?" box) |
| C141 | SUPPORTED | matches M9 output |
| C142 | SUPPORTED |  |
| C143 | SUPPORTED |  |
| C144 | SUPPORTED |  |
| C145 | SUPPORTED |  |
| C146 | SUPPORTED |  |
| C147 | PARTIAL | source: "by default" via rulesets, admins can disable; claim qualified |
| C148 | PARTIAL | source says Actions workflows on agent PRs wait for approval by a user with write access; "automation chaining is blocked" overstated; narrowed |
| C149 | SUPPORTED |  |
| C150 | SUPPORTED |  |
| C151 | SUPPORTED |  |
| C152 | SUPPORTED |  |
| C153 | SUPPORTED | matches M10 output; S71 has no label-removal call |
| C154 | SUPPORTED | PR merge date 2026-04-23 confirmed via gh api |
| C155 | SUPPORTED |  |
| C156 | SUPPORTED |  |
| C157 | SUPPORTED |  |
| C158 | SUPPORTED |  |
| C159 | PARTIAL | "not a hosted GitHub trigger" not in source; dropped |
| C160 | PARTIAL | scoped to the README prompt example |
| C161 | SUPPORTED |  |
| C162 | SUPPORTED |  |
| C163 | PARTIAL | scoped to the simple-loop template |
| C164 | PARTIAL | narrowed to the parallel-planner template running as a script |
| C165 | PARTIAL | narrowed to "no pickup lock shown in the cited templates" |
| C166 | SUPPORTED |  |
| C167 | SUPPORTED |  |
| C168 | SUPPORTED |  |
| C169 | PARTIAL | "relevant to re-pickup" is the author's gloss; dropped; 326-PR sample noted |
| C170 | SUPPORTED |  |
| C171 | SUPPORTED |  |
| C172 | SUPPORTED |  |
| C173 | SUPPORTED |  |
| C174 | SUPPORTED |  |
| C175 | PARTIAL | source describes review as the bottleneck in dotnet/runtime; claim generalized it to "the failure mode for AFK pickup"; scoped to the report |
| C176 | SUPPORTED |  |
| C177 | SUPPORTED |  |
| C178 | SUPPORTED |  |
| C179 | PARTIAL | the -tryK branch is confirmed; a PR is opened only when pr_type is draft/ready (pr_type 'branch' creates no PR, S84 line 259); qualified |
| C180 | SUPPORTED |  |
| C181 | PARTIAL | "they must arrive as inputs" not in S85; dropped |
| C182 | SUPPORTED |  |
| C183 | SUPPORTED |  |
| C184 | PARTIAL | changelog is an "Improvement" dated May 7, 2026; "GA" not stated; dropped |
| C185 | SUPPORTED |  |
| C186 | SUPPORTED | table cells, not one sentence |
| C187 | PARTIAL | llms.txt says "OpenHands Enterprise", not "hosted"; reworded. Page Not Found confirmed by re-fetch 2026-10-06 |
| C188 | PARTIAL | sandcastle "re-reading issue comments" does not follow from C161/C162 (C162 only says comment and move on); and C180 shows OpenHands does reuse the head branch when the target is a PR; narrowed to issue re-pickup in the cited sources |
| C189 | PARTIAL | C169/C170 measure duplicates as a rejection cause but do not attribute them to re-pickup; the "matches" link is an unstated premise; dropped |
| C190 | SUPPORTED | checked at c6c848f via git show |
| C191 | SUPPORTED |  |
| C192 | SUPPORTED |  |
| C193 | SUPPORTED |  |
| C194 | PARTIAL | the allowlist is as quoted; "executes arbitrary repo Python, e.g. a conftest.py the worker itself wrote" is not in the cited file; dropped |
| C195 | SUPPORTED |  |
| C196 | SUPPORTED |  |
| C197 | SUPPORTED |  |
| C198 | SUPPORTED |  |
| C199 | SUPPORTED |  |
| C200 | SUPPORTED |  |
| C201 | SUPPORTED | code-review.yml lines 400-404 make the prose ladder a fallback behind the structured block; the claim is scoped to that path |
| C202 | SUPPORTED |  |
| C203 | SUPPORTED |  |
| C204 | SUPPORTED |  |
| C205 | SUPPORTED |  |
| C206 | SUPPORTED |  |
| C207 | SUPPORTED | matches M11 output |
| C208 | SUPPORTED |  |
| C209 | PARTIAL | source states this under allowed_non_write_users: "*"; condition added |
| C210 | SUPPORTED |  |
| C211 | SUPPORTED |  |
| C212 | SUPPORTED |  |
| C213 | SUPPORTED |  |
| C214 | SUPPORTED |  |
| C215 | SUPPORTED |  |
| C216 | SUPPORTED |  |
| C217 | SUPPORTED |  |
| C218 | PARTIAL | S99 states the Workflows permission for GitHub Apps only; the PAT-table parenthetical is not in S99; dropped |
| C219 | SUPPORTED |  |
| C220 | SUPPORTED | HTML fetch also says push rulesets are available "in internal and private repositories" |
| C221 | SUPPORTED |  |
| C222 | SUPPORTED |  |
| C223 | SUPPORTED |  |
| C224 | SUPPORTED |  |
| C225 | PARTIAL | "(PR merge ref for pull_request events)" is not in the cited file (actions/checkout default, unsourced); dropped; cross-reference [C203] corrected to [C195] |
| C226 | SUPPORTED |  |
| C227 | SUPPORTED | pull_request_target and PR-title details are on the same page ("The Vulnerability") |
| C228 | SUPPORTED |  |
| C229 | SUPPORTED |  |
| C230 | SUPPORTED |  |
| C231 | SUPPORTED |  |
| C232 | SUPPORTED |  |
| C233 | SUPPORTED |  |
| C234 | SUPPORTED |  |
| C235 | SUPPORTED |  |
| C236 | SUPPORTED | quote is a markdown heading; present in the docs .md text; quote check NOT FOUND: the quote is a markdown heading; read verbatim in the docs page source via the GitHub docs API |
| C237 | SUPPORTED |  |
| C238 | SUPPORTED |  |
| C239 | SUPPORTED | quote at line 100 of sandboxing.md re-fetched 2026-10-06 |
| C240 | SUPPORTED | security.md:16 at fd1c128; agent-dispatch.yml sets no allowed_non_write_users |
| C241 | PARTIAL | 37,623 PRs include a 4,027-PR human baseline (33,596 agent PRs per S110 3.1); "37,623 agent PRs" corrected |
| C242 | SUPPORTED |  |
| C243 | PARTIAL | quote only gives the 12.6 h wait; "all PRs in human-reviewed repos" and "no arm merges without review" are not in S109/S110; dropped |
| C244 | SUPPORTED |  |
| C245 | SUPPORTED |  |
| C246 | SUPPORTED | PRs in METR's sample were test-passing, so the category is one tests did not catch |
| C247 | SUPPORTED |  |
| C248 | PARTIAL | source says "Our data suggest" improvement does not carry over without the basics; not an attribution of the 7.2%; reworded |
| C249 | SUPPORTED |  |
| C250 | SUPPORTED |  |
| C251 | PARTIAL | figure is for the diff-only configuration with an LLM-as-judge; condition added |
| C252 | PARTIAL | one evaluation (5 models, 150 samples) presented as general; scoped |
| C253 | SUPPORTED | 50 real bug-fix PRs per S115 abstract |
| C254 | SUPPORTED |  |
| C255 | UNCHECKABLE | snippet; S117 returns a 2.3 KB JS shell with no abstract text |
| C256 | SUPPORTED | agent-dispatch.yml:40-43 |
| C257 | SUPPORTED | threat-model.md:55; agent-dispatch.yml:69-71; M12 |
| C258 | SUPPORTED | #1894 body re-read; no PAT/identity mention; comments [] (M13) |
| C259 | PARTIAL | quote present (leading whitespace); comment names osasuwu-ci[bot] and a merge-train App token, but merge-train.yml is deleted (C280), so "a non-owner identity is already provisioned" dropped; quote check NOT FOUND: the code line is quoted with its leading whitespace; read verbatim in the raw file at c6c848f |
| C260 | PARTIAL | source gives 54.9% integrated without further modification; 45.1% is derived, not stated; reworded to the source figure |
| C261 | SUPPORTED |  |
| C262 | SUPPORTED | S120 re-fetched with a browser UA (first fetch was a block page); abstract matches |
| C263 | SUPPORTED |  |
| C264 | SUPPORTED |  |
| C265 | SUPPORTED |  |
| C266 | SUPPORTED |  |
| C267 | SUPPORTED |  |
| C268 | SUPPORTED | agent-dispatch.yml:51 and code-review.yml:157 |
| C269 | SUPPORTED |  |
| C270 | SUPPORTED | quote check NOT FOUND: the body text words it slightly differently ("untrusted PR"); the quote is verbatim in the page meta/og description |
| C271 | SUPPORTED |  |
| C272 | PARTIAL | quote and table show default-branch file and SHA; "with repo secrets" is not in the cited passage; dropped |
| C273 | SUPPORTED |  |
| C274 | SUPPORTED | allowed_bots "*" at code-review.yml:184, justification at 173-177 |
| C275 | PARTIAL | job condition also admits workflow_dispatch and excludes dependabot; added |
| C276 | SUPPORTED |  |
| C277 | SUPPORTED | same paragraph: "GitHub alone cannot resolve this vulnerability through server-side patches" |
| C278 | PARTIAL | source says "attempted to use local AI tools"; "weaponized ... for data theft" narrowed |
| C279 | SUPPORTED |  |
| C280 | SUPPORTED | M14 |
| C281 | SUPPORTED | S96 datePublished Dec 04, 2025 |
| C282 | PARTIAL | "every study reviewed by humans / no unreviewed arm" rests on the dropped part of C243 and is contradicted by C254's CRA-only arm; dropped |
| C283 | PARTIAL | 15-31% is diff-only; "lets most defects through" and "HIGH/CRITICAL PRs are typically larger" are unstated premises; narrowed |
| C284 | PARTIAL | "blanket hold = CAB-shaped" needs the unstated premise that the owner's hold is external approval (DORA defines it as people external to the team); dropped |
| C285 | PARTIAL | METR gives "breaks other code" as a category, not "recurring"; conclusion narrowed to what revert counting misses |
| C286 | SUPPORTED |  |
| C287 | SUPPORTED |  |
| C288 | PARTIAL | git checkout writing past deny rules is an unstated premise (C214 says deny rules cover recognized Bash file commands); the Workflows-permission point rests on C218, narrowed to GitHub Apps; both dropped |
| C289 | PARTIAL | token in the subprocess env is what C240 says to assume, not established; "short-lived" App token is an unstated premise; conditioned and dropped |
| C290 | PARTIAL | the Python REST route needs the token in the subprocess env (C240, assumed); conditioned |
| C291 | SUPPORTED |  |
| C292 | SUPPORTED |  |
| C293 | SUPPORTED |  |
| C294 | SUPPORTED | stated as unverified |
| C295 | PARTIAL | "a PR's own AGENTS.md is read by its reviewer" needs the unstated premise that the reviewer loads AGENTS.md; dropped |
| C296 | SUPPORTED |  |
| C297 | SUPPORTED | unblock-ready.yml resolve job runs the script from the checkout with issues: write; merge-ref caveat is explicit |
| C298 | PARTIAL | "short-lived" and "not admin" are not in any cited claim; narrowed |
| C299 | SUPPORTED |  |
| C300 | SUPPORTED |  |
| C301 | SUPPORTED |  |
| C302 | SUPPORTED |  |
| C303 | SUPPORTED |  |
| C304 | SUPPORTED |  |
| C305 | SUPPORTED |  |
| C306 | SUPPORTED |  |
| C307 | SUPPORTED |  |
| C308 | SUPPORTED |  |
| C309 | SUPPORTED |  |
| C310 | SUPPORTED |  |
| C311 | SUPPORTED |  |
| C312 | SUPPORTED |  |
| C313 | SUPPORTED |  |
| C314 | SUPPORTED |  |
| C315 | SUPPORTED |  |
| C316 | SUPPORTED |  |
| C317 | SUPPORTED |  |
| C318 | SUPPORTED |  |
| C319 | SUPPORTED |  |
| C320 | SUPPORTED |  |
| C321 | SUPPORTED |  |
| C322 | SUPPORTED |  |
| C323 | SUPPORTED |  |
| C324 | SUPPORTED |  |
| C325 | SUPPORTED |  |
| C326 | SUPPORTED |  |
| C327 | SUPPORTED |  |
| C328 | SUPPORTED |  |
| C329 | SUPPORTED |  |
| C330 | SUPPORTED |  |
| C331 | PARTIAL | S129 excludes plugins installed from a local path and copy-mode command sources (only symlinks inside the plugin preserved); condition added |
| C332 | SUPPORTED |  |
| C333 | SUPPORTED |  |
| C334 | SUPPORTED | quote check NOT FOUND: the page writes `enabledPlugins` as a markdown link; read verbatim in the .md page text |
| C335 | SUPPORTED |  |
| C336 | SUPPORTED |  |
| C337 | SUPPORTED |  |
| C338 | SUPPORTED |  |
| C339 | SUPPORTED |  |
| C340 | SUPPORTED |  |
| C341 | PARTIAL | M18 shows root action.yml unchanged but base-action/action.yml changed (CC 2.1.285 -> 2.1.291); narrowed to root action.yml |
| C342 | SUPPORTED |  |
| C343 | SUPPORTED |  |
| C344 | PARTIAL | S130 states the trust gate only for a repository .claude/settings.json; that user-scope entries escape it is an unstated premise; reworded as undocumented |
| C345 | SUPPORTED |  |
| C346 | PARTIAL | C302/C307 cover the CLI --add-dir; C345 shows the action maps it to SDK additionalDirectories, which C305 shows need not load skills; reworded as unverified either way |
| C347 | SUPPORTED | restore runs for PR contexts (S15 doc comment; run.ts call site at v1 checked) |
| C348 | SUPPORTED |  |
| C349 | SUPPORTED |  |
| C350 | SUPPORTED |  |
| C351 | SUPPORTED | quote check NOT FOUND: the comment is JS-rendered on github.com; read verbatim via the GitHub API (issue comments endpoint) |
| C352 | SUPPORTED | quote check NOT FOUND: the comment is JS-rendered on github.com; read verbatim via the GitHub API (issue comments endpoint) |
| C353 | SUPPORTED |  |
| C354 | SUPPORTED |  |
| C355 | SUPPORTED | quote check NOT FOUND: the comment is JS-rendered on github.com; read verbatim via the GitHub API (issue comments endpoint) |
| C356 | SUPPORTED |  |
| C357 | PARTIAL | comment says it worked by instructing the model to use the skill AND allowing Skill; "exit immediately" is the 44 ms/1-turn report in the issue body; reworded; quote check NOT FOUND: the comment is JS-rendered on github.com; read verbatim via the GitHub API (issue comments endpoint) |
| C358 | SUPPORTED |  |
| C359 | SUPPORTED | quote check NOT FOUND: the comment is JS-rendered on github.com; read verbatim via the GitHub API (issue comments endpoint) |
| C360 | SUPPORTED |  |
| C361 | SUPPORTED |  |
| C362 | SUPPORTED |  |
| C363 | SUPPORTED |  |
| C364 | SUPPORTED | quote check NOT FOUND: the comment is JS-rendered on github.com; read verbatim via the GitHub API (issue comments endpoint) |
| C365 | SUPPORTED | quote check NOT FOUND: the comment is JS-rendered on github.com; read verbatim via the GitHub API (issue comments endpoint) |
| C366 | SUPPORTED |  |
| C367 | SUPPORTED |  |
| C368 | SUPPORTED |  |
| C369 | SUPPORTED |  |
| C370 | SUPPORTED |  |
| C371 | SUPPORTED |  |
| C372 | SUPPORTED |  |
| C373 | SUPPORTED |  |
| C374 | SUPPORTED |  |
| C375 | SUPPORTED | absence confirmed: S151 read in full, no include/import or out-of-skill-dir text |
| C376 | PARTIAL | follows C331 as narrowed: local-path and copy-mode command plugins excluded |
| C377 | SUPPORTED | quote check NOT FOUND: the comment is JS-rendered on github.com; read verbatim via the GitHub API (issue comments endpoint) |
| C378 | SUPPORTED | quote check NOT FOUND: the comment is JS-rendered on github.com; read verbatim via the GitHub API (issue comments endpoint) |

Label verdict: open — Q3 has no hold-vs-revert evidence and the AP5/AP9/AP12 and in-action skills-loading paths are unverified; any of them resolved unfavourably would change the Summary's merge, security or skills recommendation.
Quote check: afk-orchestration-external-2026-10-06.md: 321 quoted claim(s): 308 found, 13 NOT FOUND, 0 unfetchable, 0 no source
