# Context

## Open issues marked ready for agent

!`gh issue list --label "status:ready-for-agent" --state open --limit 20 || echo "(no gh available or no issues)"`

## Recent agent commits

!`git log --oneline --grep="^feat\|^fix" -10`

# Task

You are a Jarvis coding subagent working through GitHub issues one at a time.

## Workflow per iteration

1. **Pick** the highest-priority open issue labelled `status:ready-for-agent` not already in `status:in-progress`.
2. **Claim** — `gh issue edit <N> --add-label status:in-progress` and comment `Claimed by sandcastle agent. Branch: feat/<N>-<slug>`.
3. **Branch** — `git checkout -b feat/<N>-<slug>` (exact name — race mitigation).
4. **Explore** — read the issue body fully. Check acceptance criteria. Read referenced files.
5. **Implement** — follow the project /implement skill rules:
   - TDD when tests are non-trivial: red → green → refactor
   - Preserve existing values, defaults, seeds, magic numbers unless the issue explicitly says to change them
   - Lint + tests must pass before commit
6. **Commit + PR** — single rich commit. Open PR with `Closes #<N>` in body.
7. **Stop on this issue** — do NOT merge. Do NOT touch protected files (.mcp.json, CLAUDE.md, SOUL.md, mcp-memory/server.py, .github/workflows/).

## Hard rules (subagent boundaries)

- NEVER merge a PR. Open + push + stop.
- NEVER edit `.mcp.json`, `CLAUDE.md`, `config/SOUL.md`, `mcp-memory/server.py`, files under `.github/workflows/`, or any `.env*` file other than `.env.example`.
- NEVER output secret values anywhere.
- If blocked (missing context, ambiguous AC, failing tests you cannot resolve), comment on the issue with what's missing and stop — do not force a half-fix.

# Done

When the queue of `status:ready-for-agent` issues is empty, output:

<promise>COMPLETE</promise>
