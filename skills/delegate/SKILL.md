---
name: delegate
description: "Delegate a GitHub issue to a coding agent: decompose -> branch -> implement -> PR"
model: sonnet
tools: [Read, Grep, Glob, Bash]
max_budget_usd: 0.30
handler: jarvis.delegate:handle
background: true
---

# Delegate Skill

Autonomously implement a GitHub issue by delegating to a coding agent.

## Usage

`/delegate <owner/repo>#<issue_number>`
`/delegate #<issue_number>` (uses default repo from repos.conf)

Examples:
- `/delegate Osasuwu/personal-AI-agent#42`
- `/delegate #55`

## What happens

1. **Fetch** — read the issue from GitHub
2. **Decompose** — Jarvis brain analyzes the issue and writes a structured coding prompt
3. **Branch** — create `feature/<number>-<title>` from main
4. **Code** — coding agent (Claude Code CLI) implements the changes autonomously
5. **PR** — commit, push, create PR linking to the issue

## Output

Success: PR URL + coding agent summary
Failure: step that failed + error details

## Requirements

- `gh` CLI authenticated
- Git repo with clean working tree
- Claude Code CLI installed and authenticated (Pro/Max subscription)
