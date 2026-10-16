# Dispositions — /grill risk-tier scope, 2026-10-16

Source: `sampling.md` in this directory (sampling tier only, so triage was skipped and each item went to the user as its own question). The user answered on 2026-10-16.

| ID | Item (short) | Disposition | Rationale |
|---|---|---|---|
| S1 [HIGH] | A green check on an admin-authored HIGH PR removes the `--admin` + marker trace that an agent session acting as the admin would otherwise leave. This reverses D12's rejection of D12c. | **reject**, residual accepted | User chose "green". This matches today's state, because `risk-tier` is not required, so the admin already merges HIGH with a plain `gh pr merge`. The risk is accepted and recorded as a D12 revisit. |
| S2 [MEDIUM] | The exemption keys on the `admin` role, so on a host with two or more admins an admin-authored HIGH PR goes green although another admin could review it. | **reject** | User: «Не важно сколько админов в проекте, кто создал PR, тот может мерджить». The hold exists so that machine-authored HIGH work never merges unattended. It was never meant to require four eyes between humans: D7 and D10 both rejected a second reviewer on the admin's own PRs. |
| S3 [MEDIUM] | Scoping by PR opener leaves an admin-opened PR green at HIGH even after another account pushes to its head. | **defer** | To the follow-up issue, and documented as a residual risk in `risk_tier.md`. |
| S4 (alt) | Make the check required now with the rule unchanged, and add a `sole-admin-author` admin-merge marker. | **reject** | User chose "green": red on roughly 90% of PRs is the always-red ritual this grill exists to remove. |
| S5 (alt) | Interactive sessions open PRs as `osasuwu-bot`, so the admin can approve them. | **reject** | Already rejected in round 1. It costs one approval click per push, and the bot PAT has no `workflow` scope, so PRs touching `.github/workflows/**` would still be the admin's. |
| S6 (alt) | Exempt only when no other admin human exists, or only for an explicit `self-release-login` input. | **reject** | Same reason as S2: the admin role is the key, whatever the admin count. |
| S7 (assumption) | That a green check on the admin's own HIGH PRs is a precondition for making the check required. | **reject** | User chose "green". The precondition is the user's own call ("can't be required while it is always red"), not an inference. The D12 reversal it points at is recorded under S1. |

Settled rule (round 1, held after the critic):
- A HIGH/CRITICAL PR by a non-admin author (`osasuwu-bot`, `dependabot[bot]`, a write collaborator) stays red until an admin human's APPROVED review on the head SHA exists.
- A HIGH/CRITICAL PR by an admin author is green, with the tier and its reasons in the check summary.
- For every author, admin included, red otherwise means a missing or malformed `Risk:` line. The existing fail-closed cases also stay red: a superseded head, or an API error.

Deferred to the follow-up issue:
- S3;
- whether `.md` docs and test renames should escalate to HIGH (the protected-path list);
- whether an understated declared tier (declared < computed) should be red.
