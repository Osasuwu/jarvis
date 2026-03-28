---
name: risk-radar
description: "Detect early risk signals: CI instability, stagnant critical issues, security alerts, overdue milestones, review backlog"
model: haiku
max_budget_usd: 0.05
handler: jarvis.risk_radar:handle
---

# Risk Radar

Scans configured repos for five validated early-warning risk patterns and raises severity-classified alerts.

## Risk patterns

| Pattern | Signal | CRITICAL | HIGH | MEDIUM |
|---------|--------|----------|------|--------|
| P1: CI instability | Workflow run failure rate | >50% | 30–50% | 15–30% |
| P2: Critical stagnation | priority:high issues not updated | — | ≥5 issues >7d | 2–4 issues >7d |
| P3: Security alerts | Open Dependabot alerts | any critical/high CVE | — | any medium CVE |
| P4: Overdue milestones | Milestone past due_on with open work | — | <50% done | ≥50% done |
| P5: Review backlog | CHANGES_REQUESTED PRs stale | — | ≥3 PRs >3d | 1–2 PRs >3d |

## Escalation policy

| Severity | Action |
|----------|--------|
| **CRITICAL** | ⚠ header in Telegram response · included in all daily/weekly reports |
| **HIGH** | Surfaced in daily triage summary |
| **MEDIUM** | Included in weekly report |
| **LOW** | Logged to work memory only, not surfaced |

## Output

Markdown report saved to `reports/risk-radar-<timestamp>.md` with:
- Active risks sorted by severity
- Per-alert: pattern, repo, details, evidence command
- Escalation policy table

## Usage

```
/risk-radar
```

Or plain text: "check for risks", "risk scan", "проверь риски", "есть ли проблемы"

## Configuration

Repos are read from `skills/triage/repos.conf` (shared with triage and opportunity-scan).
