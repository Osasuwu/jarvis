---
name: risk-radar
description: This skill should be used when the user asks to check for risks, scan for problems, review CI health, check security alerts, look at overdue milestones, or audit PR review backlog. Trigger phrases include "риски", "risk", "проверь риски", "что сломано", "CI падает", "security alerts", "просроченные milestones", "review backlog".
version: 1.0.0
---

# Risk Radar

Scans configured repos for five early-warning risk patterns. All data from `gh` CLI — deterministic thresholds, no LLM inference.

## Step 1 — Load repos

Read `personal-AI-agent/config/repos.conf`. Each non-empty, non-comment line = `owner/repo`.

## Step 2 — Run 5 patterns per repo

### P1: CI Instability
```bash
gh run list --repo <owner/repo> --json conclusion,name,createdAt --limit 20
```
`failure_rate = failures / total` → ≥50% CRITICAL, 30–49% HIGH, 15–29% MEDIUM

### P2: Critical Issue Stagnation
```bash
gh issue list --repo <owner/repo> --state open --label priority:high --json number,title,updatedAt,assignees --limit 100
```
Issues not updated >7 days → ≥5 HIGH, 1–4 MEDIUM

### P3: Security Alerts
```bash
gh api repos/<owner/repo>/dependabot/alerts --jq '[.[] | select(.state == "open") | {severity:.security_vulnerability.severity, pkg:.dependency.package.name}]'
```
critical/high CVE → CRITICAL, medium → MEDIUM

### P4: Overdue Milestones
```bash
gh api repos/<owner/repo>/milestones --jq '[.[] | select(.state == "open" and .due_on != null) | {title:.title, due:.due_on, open:.open_issues, closed:.closed_issues}]'
```
Past due + open issues → <50% done HIGH, ≥50% done MEDIUM

### P5: Review Backlog
```bash
gh pr list --repo <owner/repo> --state open --json number,title,updatedAt,reviewDecision,isDraft --limit 100
```
Non-draft PRs with CHANGES_REQUESTED + >3 days old → ≥3 HIGH, 1–2 MEDIUM

## Step 3 — Format report

Sort: CRITICAL → HIGH → MEDIUM.

```markdown
# Risk Radar — YYYY-MM-DDTHH:MM:SS

**Repos scanned:** N
**Alerts:** N CRITICAL · N HIGH · N MEDIUM

### 🔴 [CRITICAL] <title>
- **Repo**: `owner/repo`
- **Pattern**: <P1–P5>
- **Details**: <explanation>
```

If no alerts: `No risks detected.`

## Constraints
- **Read-only**. Skip failed patterns, continue.
