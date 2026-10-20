# Single-developer audit — 2026-10-20 (#1894)

Every mechanism in this repo that assumes exactly one developer, where it is defined, what it
assumes, and its devs-agnostic form. The rule applied throughout: **name the role and the
condition, never the headcount** (decision `docs/decisions/2026-Q4.md`, 2026-10-20). A dated
record: line numbers are as of `main` at 39501f2.

Kinds:

- **rename** — the wording changes, the behaviour does not.
- **semantic** — the rule means something different at N>1, so the behaviour or the accepted
  risk changes.
- **correct** — correctly single-developer as stated; the condition under which that stops being
  true is named.

Follow-ups: #2123 (stale required-check claims), #2124 (merge-hold and release wording), #2125
(lane operator fallback, frozen), #2126 (security docs), #2127 (owner → principal/operator
rename sweep), #2128 (protected-file patches for a human).

## Mechanisms

| # | Mechanism | Where | Assumes | Kind | Devs-agnostic form | Follow-up |
|---|---|---|---|---|---|---|
| 1 | `waiting-human-review` hold | AGENTS.md:37-40 (protected); docs/reference/github-repo-setup.md:74, 97, 429-431; .github/scripts/waiting_human_review.py:4; .github/workflows/waiting-human-review.yml:3 | "the solo-developer path" = the label, N>1 = a review request | rename | Red while a review is owed: a pending review request to someone with the reviewing role, or, when no one but the author holds that role, the label. The check already reads both inputs; only the prose counts heads. | #2124, #2128 |
| 2 | `risk-tier` release | AGENTS.md:37 (protected); .github/scripts/risk_tier.py:21-23, 272, 302, 375; .github/scripts/risk_tier.md:32, 54; CONTEXT.md:40, 151 | "an admin human approves" | rename | An APPROVED review at the head SHA from a holder of the releasing role (admin; on opt-in lane hosts the labeller, #2107). Matches the 2026-10-16 "admin role, not admin count" decision. | #2124, #2128 |
| 3 | "a second collaborator merges" / "a human merges it" | .github/scripts/code_gate_verdict.py:566; docs/reference/ci-guard-meta-tests.md:90 | the second person performs the merge | rename | The second person *approves*; the platform (or the agent, under #2006's guard) merges. | #2124 |
| 4 | `status:owner-queue` label | AGENTS.md:41; github-repo-setup.md:99, 433 | one "owner" whose queue it is | correct (retired) | Already retired; the remaining mentions are history and say so. No action. | — |
| 5 | `T1 = OWNER_QUEUE` tier in `agents/safety.py` | docs/security/agent-boundaries.md:28; docs/agents/perception.md:52 | a module and tier that no longer exist | semantic (stale claim) | Remove the citation or point to the mechanism that replaced it (`waiting-human-review`). | #2123 |
| 6 | Lane fallback reviewer | .github/workflows/lane.yml:532 (`LANE_REVIEWER`); .github/scripts/lane_publish.py:13-16, 56-59; docs/reference/lane-host-setup.md:54-55, 94-96; lane-red-check-watcher.yml:40 | `github.repository_owner` is a person who reviews | semantic | An unset `operator` is reported visibly instead of defaulting to the repository owner (wrong on org-owned and team hosts). **Frozen lane** (2026-10-17): recorded, not worked; see #2107, #1966, #1810, #1809, #2014, #2015, #2027, #2013, #2009. | #2125 |
| 7 | Dispatch and unattended-run rules | AGENTS.md:55-59; docs/decisions/2026-Q4.md 2026-10-17 D3 | "the user selected it" | correct | Already stated as a condition (selection by the principal of this instance; collaborators' content is data). Stays correct while one principal per instance holds — see row 9. | — |
| 8 | "no owner review required" | config/plan_review.yaml:9, 32; agents/plan_review_config.py:5, 12, 45, 105 | "owner" = the human reviewer | rename | "no human review" / "the principal"; the error-message text included. | #2127 |
| 9 | Single-principal identity | config/SOUL.md (protected); docs/VISION.md:3, 12, 242; docs/security/agent-boundaries.md:81, 87 | one principal per Jarvis instance | correct | Correct by design: each operator hosts their own instance, and the instance serves one principal. It is a statement about the instance, not about the host repo's team. VISION.md:12 "a solo developer doing the work of a team" describes the target user, not a mechanism. | — |
| 10 | Security accepted risks justified by "single-user" / "solo project" | docs/security/threat-model.md:123; docs/security/mcp-audit.md:36, 40, 151 | the host repo has no other people | semantic | Restate each accepted risk with its condition ("one principal per instance; collaborator content is data") and re-check it with collaborators present — redrobot already has them. | #2126 |
| 11 | "Never as the owner" (weekly-release gate) | config/SOUL.md:34 (protected) | "owner" = the principal | rename | "the principal" (SOUL.md:58 already forbids "owner"). | #2128 |
| 12 | `protected-files.py` "live owner" | .claude/hooks/protected-files.py:8, 10, 125 (protected) | "owner" = the human editing | rename | "live principal". | #2128 |
| 13 | Related projects "second reader" | AGENTS.md:93 (protected) | a headcount for redrobot | rename | "has collaborators who read and may contribute". | #2128 |
| 14 | Owner-flavoured prose elsewhere | docs/reference/milestone-hygiene.md:15; .github/github-process-runbook.md:47; scripts/notify_telegram.py:1; scripts/weekly_release_engine.py:348; docs/architecture.md:132; CONTEXT.md:47, 71, 96, 132, 184, 223; docs/reference/eval-design.md:8 | "owner" for whoever approves, reviews or is notified | rename | `principal`, `operator` or the named role; eval-design states the condition (one person holds author, scorer and subject) rather than "solo". | #2127 |
| 15 | D7: no CODEOWNERS | docs/decisions/2026-Q4.md:365-373 | an author cannot self-approve, so code-owner review would block Osasuwu's own PRs | correct (conditional) | Correct while the only holder of the code-owner role is the usual author. Revisit when a second person holds the reviewing role: then code-owner review stops being self-blocking. | — |
| 16 | D10: no native required reviews | docs/decisions/2026-Q4.md:376-384 | same — native required reviews would require a review on the sole maintainer's PRs | correct (conditional) | Same condition as row 15; at that point `required_pull_request_reviews` is a candidate replacement for part of `risk-tier`'s release. | — |

Reviewed and excluded: `owner/repo` placeholders in API paths, `repository_owner` used as the
GitHub namespace (not a person), and the GitHub "owner" permission level — these name a
platform concept, not a headcount.

## Stale required-check claims

### Found by the scanner

`.github/scripts/branch_protection_drift.py` now scans the docs for prose that names a required
check and fails when the name is not required live. Two hits were stale when the scanner landed:

- docs/reference/vendored-plugin-pins.md:6 — `review` (replaced by `code-gate`, #1816). Fixed by
  #2139, which now names `code-gate`; no longer a `KNOWN_STALE` entry.
- docs/reference/ci-guard-meta-tests.md:30 — `Detect secrets with gitleaks` (the live context is
  `gitleaks`). A `KNOWN_STALE` entry (reported as a warning) tracked by #2123.

### Found by the manual sweep (outside the scanner's reach)

- .github/workflows/gitleaks.yml:3 — header comment names `Detect secrets with gitleaks`; workflow
  YAML is not scanned. #2123.
- docs/reference/github-repo-setup.md:79-80 — `risk-tier` "is added by the operator once the check
  is live", although it is live and required: a stale status, not a missing name. #2123.
- CONTEXT.md:93, 119, 137 — checked, not stale: 93 and 137 say `code-gate` replaces `review`, and
  119 describes a past incident (#1109). No present-tense claim that `review` is required.
- docs/security/threat-model.md:30 — "required `pytest` check": the "required `X` check" form is
  not in the grammar (the name is live, so nothing is stale today). #2123 extends the grammar.

### Scanner limits

Markdown only, under AGENTS.md, README.md, CONTEXT.md, SECURITY.md, docs/reference, docs/security
and .github. Dated records (docs/decisions, docs/research, docs/incidents) and workflow YAML are
not scanned. Only these sentence forms are recognised: "`X` is a required check", "make `X` a
required check", "`X` required check", "required check `X`", "add `X` to the required status
checks", and an enumeration after "required … checks:" / "(" / "are" (all case-insensitive). A
required-check name in any other phrasing goes uncaught until the grammar is extended. A missing
scan root, or a scan that finds no file, fails the run rather than reading as "no claims".

## Public repo

The same constraint applies to the public repo's docs: umbrella Osasuwu/jarvis-oss#38 (closed) and its open
child Osasuwu/jarvis-oss#44. Rows 1–3, 15 and 16 (merge gates and branch protection) and the
scanner map to its merge-gates/branch-protection practice area; rows 9 and 10 map to its identity
and security docs.
