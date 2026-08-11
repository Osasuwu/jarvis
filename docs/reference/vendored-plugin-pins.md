# Vendored plugin pins

`.claude/marketplace/.claude-plugin/marketplace.json` vendors plugins via `git-subdir`
sources. The **`code-review`** plugin (`Osasuwu/claude-plugins-official`, fork of the
upstream Anthropic plugin) is pinned to an immutable commit SHA rather than `ref: main` —
it gates every PR's `review` required check, so a change there must be a deliberate,
reviewed bump, not something that silently rides in on the next merge to the fork's
`main` (#1209).

The other vendored plugins (`pr-review-toolkit`, `session-report`, `hookify`,
`claude-md-management`, `mcp-server-dev`) stay on `ref: main` — they're unmodified
upstream Anthropic plugins with no jarvis-specific behavior riding on them, so the
version-gate risk this doc addresses doesn't apply.

## Bumping the pin

1. Review what changed on the fork's `main` since the current pinned SHA:
   ```bash
   gh api repos/Osasuwu/claude-plugins-official/compare/<current-sha>...main --jq '.commits[].commit.message'
   ```
2. If the change is safe to adopt, update `ref` in `marketplace.json` to the new commit SHA
   (`gh api repos/Osasuwu/claude-plugins-official/commits/main --jq '.sha'` for the latest).
3. Open a normal PR — the ref bump is reviewed like any other change, since it can alter
   the review pipeline's own behavior.
