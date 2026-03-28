---
name: risk-radar
description: "Early-warning risk scan: CI instability, stagnant critical issues, security alerts, overdue milestones, review backlog"
---

# Risk Radar

Scans configured repos for five early-warning risk patterns. All data comes from `gh` CLI — no LLM inference, deterministic thresholds.

## Usage

`/risk-radar`

Or: "check for risks", "risk scan", "проверь риски"

## Step 1 — Load repos

Read `config/repos.conf`. Each non-empty, non-comment line = `owner/repo`.

## Step 2 — Run 5 patterns per repo

### P1: CI Instability

```bash
gh run list --repo <owner/repo> --json conclusion,name,createdAt --limit 20
```

Filter to terminal runs: `conclusion` in `{success, failure, timed_out, cancelled}`.
Compute `failure_rate = failures / total`.

| Rate | Severity |
|------|----------|
| ≥ 50% | CRITICAL |
| 30–49% | HIGH |
| 15–29% | MEDIUM |
| < 15% | skip |

---

### P2: Critical Issue Stagnation

```bash
gh issue list --repo <owner/repo> --state open --label priority:high --json number,title,updatedAt,assignees --limit 100
```

Count issues where `updatedAt` is more than 7 days ago.

| Count | Severity |
|-------|----------|
| ≥ 5 stagnant | HIGH |
| 1–4 stagnant | MEDIUM |
| 0 | skip |

---

### P3: Security Alerts

```bash
gh api repos/<owner/repo>/dependabot/alerts --jq '[.[] | select(.state == "open") | {severity:.security_vulnerability.severity, pkg:.dependency.package.name}]'
```

If Dependabot not enabled, skip silently.

| Top open severity | Severity |
|-------------------|----------|
| critical or high CVE | CRITICAL |
| medium CVE only | MEDIUM |
| low only | skip |

---

### P4: Overdue Milestones

```bash
gh api repos/<owner/repo>/milestones --jq '[.[] | select(.state == "open" and .due_on != null) | {title:.title, due:.due_on, open:.open_issues, closed:.closed_issues}]'
```

For each milestone where `due_on < now` and `open_issues > 0`:
- Compute `pct_done = closed / (open + closed) * 100`

| Condition | Severity |
|-----------|----------|
| Any milestone < 50% done | HIGH |
| All milestones ≥ 50% done | MEDIUM |

---

### P5: Review Backlog

```bash
gh pr list --repo <owner/repo> --state open --json number,title,updatedAt,reviewDecision,isDraft --limit 100
```

Count non-draft PRs where `reviewDecision == "CHANGES_REQUESTED"` and `updatedAt` > 3 days ago.

| Count | Severity |
|-------|----------|
| ≥ 3 stale PRs | HIGH |
| 1–2 stale PRs | MEDIUM |
| 0 | skip |

---

## Step 3 — Format report

Sort all alerts by severity: CRITICAL → HIGH → MEDIUM.

```markdown
# Risk Radar — YYYY-MM-DDTHH:MM:SS

**Repos scanned:** N
**Alerts:** N CRITICAL · N HIGH · N MEDIUM

## Active Risks

### 🔴 [CRITICAL] <title>
- **Repo**: `owner/repo`
- **Pattern**: <P1–P5 slug>
- **Details**: <explanation>
- **Evidence**: `<gh command used>`

### 🟠 [HIGH] <title>
...

### 🟡 [MEDIUM] <title>
...

## Escalation Policy

| Severity | Action |
|----------|--------|
| CRITICAL | ⚠ immediate — prefix all responses, include in every report |
| HIGH | Daily — surface in triage summary |
| MEDIUM | Weekly — include in weekly report |
| LOW | Archive — log to memory only |
```

If no alerts: `No risks detected. All patterns within acceptable thresholds.`

## Constraints
- **Read-only**: do NOT modify issues, PRs, or files.
- Process repos sequentially. If `gh` fails for a pattern, skip it and continue.
