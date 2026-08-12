# Vendored plugin pins

`.claude/marketplace/.claude-plugin/marketplace.json` vendors plugins via `git-subdir`
sources. The **`code-review`** plugin (`Osasuwu/claude-plugins-official`, fork of the
upstream Anthropic plugin) is pinned to an immutable **git tag** rather than `ref: main` —
it gates every PR's `review` required check, so a change there must be a deliberate,
reviewed bump, not something that silently rides in on the next merge to the fork's
`main` (#1209).

**Pin with a tag, never a raw commit SHA** — the plugin installer resolves `ref` via
`git clone --branch <ref>`, which only accepts branch/tag names. A bare 40-char SHA
fails with `Remote branch <sha> not found in upstream origin` and breaks `review` for
every PR in the repo until fixed (#1520 — regression from the first attempt at this pin,
#1517).

The other vendored plugins (`pr-review-toolkit`, `session-report`, `hookify`,
`claude-md-management`, `mcp-server-dev`) stay on `ref: main` — they're unmodified
upstream Anthropic plugins with no jarvis-specific behavior riding on them, so the
version-gate risk this doc addresses doesn't apply.

## Bumping the pin

1. Review what changed on the fork's `main` since the current pinned tag's commit:
   ```bash
   gh api repos/Osasuwu/claude-plugins-official/compare/<current-tag>...main --jq '.commits[].commit.message'
   ```
2. If the change is safe to adopt, create a new tag on the fork pointing at the commit to
   pin (`gh api repos/Osasuwu/claude-plugins-official/git/refs -f ref='refs/tags/<name>' -f sha='<commit-sha>'`)
   — do **not** put the raw SHA directly in `ref`, see above.
3. Update `ref` in `marketplace.json` to the new tag name.
4. Open a normal PR — the ref bump is reviewed like any other change, since it can alter
   the review pipeline's own behavior.

**Note on this PR's own review**: `.claude/marketplace/` is restored from `origin/main`
for every review run regardless of PR branch content ("PR head is untrusted"), so a PR
that changes this file cannot get a real verdict from the bot it's fixing/changing — same
review-blind class as editing `code-review.yml` directly.
