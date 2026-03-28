---
name: opportunity-scan
description: "Scan repos for improvement opportunities: stale work, CI instability, milestone drift, critical backlog"
model: haiku
max_budget_usd: 0.20
handler: jarvis.opportunity_scan:handle
---

# Opportunity Scanner

Scans configured repos for health signals and surfaces the top-5 most impactful improvement opportunities.

## What it checks

- **Stale issues** — open issues not updated in >14 days
- **Stale PRs** — non-draft open PRs not updated in >5 days
- **CI instability** — workflow run failure rate over last 20 runs
- **Milestone drift** — open milestones with low completion percentage
- **Critical backlog** — priority:high issues not updated in >30 days

## Output

Markdown report saved to `reports/opportunity-scan-<timestamp>.md` containing:
- Top-5 opportunities ranked by impact × confidence
- Per-opportunity: title, category, repo, rationale, effort/impact/confidence
- Signal summary per repo

## Usage

```
/opportunity-scan
```

Or plain text: "scan for opportunities", "what should we work on next", "opportunity scan"

## Configuration

Repos are read from `skills/triage/repos.conf` (shared with triage skill).
