---
name: delegate
description: "Delegate a GitHub issue to a coding agent: decompose → branch → implement → PR"
---

# Delegate Skill

Autonomously implement a GitHub issue by delegating to a coding agent.

## Usage

`/delegate <owner/repo>#<issue_number>`
`/delegate #<issue_number>` (uses default repo from config/repos.conf)

Examples:
- `/delegate Osasuwu/personal-AI-agent#42`
- `/delegate #55`

## What happens

1. **Fetch** — read the issue from GitHub:
   ```bash
   gh issue view <number> --repo <owner/repo> --json number,title,body,labels,milestone
   ```

2. **Decompose** — analyze the issue and write a structured coding prompt that includes:
   - Clear objective (what needs to be built/fixed)
   - Acceptance criteria (what done looks like)
   - Technical context (relevant files, patterns from CLAUDE.md)
   - Out of scope (what NOT to change)

3. **Branch** — create feature branch from main:
   ```bash
   git checkout main && git pull
   git checkout -b feature/<number>-<slug>
   ```

4. **Code** — launch Claude Code CLI as coding agent with the structured prompt:
   ```bash
   claude --model claude-haiku-4-5-20251001 -p "<structured_prompt>" --allowedTools "Edit,Write,Bash,Read,Glob,Grep"
   ```
   Use Haiku for routine tasks, Sonnet for complex architectural work.

5. **PR** — commit changes, push, create PR:
   ```bash
   git add -A && git commit -m "<summary>"
   git push -u origin <branch>
   gh pr create --title "<title>" --body "Closes #<number>\n\n<summary>"
   ```

## Output

Success: PR URL + coding agent summary
Failure: step that failed + error details

## Requirements

- `gh` CLI authenticated
- Git repo with clean working tree (`git status` must show no changes)
- Claude Code CLI (`claude`) installed and authenticated

## Safety

- Always check `git status` before branching — abort if dirty
- Never force-push
- Never merge the PR (user reviews and merges)
- If coding agent fails or produces no changes, abort and report
