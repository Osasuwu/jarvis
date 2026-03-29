---
name: delegate
description: This skill should be used when the user wants to implement a GitHub issue autonomously, delegate coding work to an agent, or asks to "реализуй", "сделай", "implement", "delegate", or references a specific issue number for implementation (e.g. "#42", "issue 55"). Do NOT trigger for issue viewing, triaging, or discussing — only for actual implementation requests.
version: 1.0.0
---

# Delegate Skill

Autonomously implement a GitHub issue by delegating to a coding agent.

## Usage

Invoke when user says "реализуй #42", "delegate issue 55", "implement #X in personal-AI-agent", etc.
Default repo: first entry in `personal-AI-agent/config/repos.conf`.

## Pipeline

1. **Fetch** the issue:
   ```bash
   gh issue view <number> --repo <owner/repo> --json number,title,body,labels,milestone
   ```

2. **Decompose** — write structured coding prompt:
   - Clear objective and acceptance criteria
   - Technical context (relevant files, patterns from CLAUDE.md)
   - Out of scope (what NOT to change)

3. **Branch** from main:
   ```bash
   git -C <project_path> checkout main && git -C <project_path> pull
   git -C <project_path> checkout -b feature/<number>-<slug>
   ```

4. **Code** — launch coding agent:
   ```bash
   claude --model claude-haiku-4-5-20251001 -p "<structured_prompt>" --allowedTools "Edit,Write,Bash,Read,Glob,Grep"
   ```
   Use Haiku for routine tasks, Sonnet for complex architectural work.

5. **PR**:
   ```bash
   git -C <project_path> add -A && git -C <project_path> commit -m "<summary>"
   git -C <project_path> push -u origin <branch>
   gh pr create --repo <owner/repo> --title "<title>" --body "Closes #<number>\n\n<summary>"
   ```

## Safety
- Check `git status` before branching — abort if dirty
- Never force-push, never merge the PR
- If coding agent fails or produces no changes, abort and report
