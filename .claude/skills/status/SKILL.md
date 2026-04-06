---
name: status
description: "Quick project dashboard — git state, open PRs, recent issues, last research findings, open checkpoints across all configured repos. Use when: session start context check, 'статус', 'status', 'что происходит', 'overview', 'dashboard'."
version: 1.0.0
---

# Status Dashboard

Single-command overview of all projects. Designed for session-start context loading — replaces manual git checks and memory recalls.

## Usage

- `/status` — all repos
- `/status <repo>` — single repo focus

## Step 1 — Load repos and memory (parallel)

Run in parallel:
- Read `config/repos.conf` for repo list (one `owner/repo` per line)
- `memory_recall(query="working_state", type="project", limit=3)` — open checkpoints
- `memory_recall(query="intel digest", limit=1)` — last intel run
- `memory_recall(query="nightly research", limit=1)` — last nightly findings

## Step 2 — Git state per project (parallel)

For each repo from `repos.conf`, check if a local directory exists for it (derive directory name from repo name — e.g. `Osasuwu/personal-AI-agent` → look for `../personal-AI-agent` relative to project root). If found:

```bash
git -C <path> log --oneline -5
git -C <path> status --short
git -C <path> branch --show-current
```

Skip repos without local directories — they're still checked via GitHub in Step 3.

## Step 3 — GitHub state per repo (parallel)

For each repo in repos.conf:

```bash
gh pr list --repo <owner/repo> --state open --json number,title,author,updatedAt --limit 5
gh issue list --repo <owner/repo> --state open --label "priority:high" --json number,title,updatedAt --limit 5
gh run list --repo <owner/repo> --json conclusion,name --limit 5
```

## Step 4 — Format output

```markdown
# Status — YYYY-MM-DD

## Open Checkpoints
- <checkpoint name> — <summary> (or: none)

## <Repo Name>
**Branch:** main | **Clean:** yes/no
**Recent commits:** (last 3, one-line each)
**Open PRs:** N (list titles)
**High-priority issues:** N (list titles)
**CI:** N/M passed (last 5 runs)

## <Repo 2>
...

## Intel / Research
**Last intel:** <date> — <top finding>
**Last nightly:** <date> — <top finding>

## Suggested next action
<based on what's most urgent: stale PR, failing CI, open checkpoint, etc.>
```

Keep the output concise. Skip sections with nothing to report.

## Cost estimate

~$0.02–0.05 per run (mostly gh CLI calls, minimal LLM)
