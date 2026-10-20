# Setup — Jarvis

Single setup guide for a new device: clone, secrets, MCP servers, plugins. Takes ~15
minutes. Supersedes the old `SETUP.md` / `config/SETUP.md` / `docs/telegram-setup.md`.

> **Cost of entry:** Claude Code requires a paid Claude.ai plan (Pro, Max, or Team) or
> Anthropic API billing — there is no free tier that covers it. Budget this before
> starting.

## Prerequisites

- [Claude Code](https://claude.ai/code) installed and authenticated (`claude --version`)
- [GitHub CLI](https://cli.github.com) installed and authenticated (`gh auth status`)
- Python 3.11+ and [`uv`](https://docs.astral.sh/uv/) (`pip install uv`)
- [Supabase](https://supabase.com) account (free tier is enough) — backs the tables still in use
  (goals, comm_patterns, credential_registry, audit_log, review_debt); memory itself is native, file-based
  (`~/.claude/projects/<project>/memory/`), not Supabase-backed
- Node.js 18+ (some MCP servers run via `npx`)
- Windows 11 (primary), Linux/macOS also supported

## 1. Clone and configure

```bash
git clone https://github.com/Osasuwu/jarvis.git
cd jarvis
```

**Edit `config/repos.conf` before running `/triage`** — it ships with the
original author's repos. Replace those lines with your own (`owner/repo` format, one per
line) so skill output refers to your projects, not someone else's.

```bash
# Windows
notepad config\repos.conf

# Linux / macOS
nano config/repos.conf
```

## 2. Create the Python environment

```bash
uv sync --project .
```

```bash
# Windows
copy .env.example .env

# Linux / macOS
cp .env.example .env
```

`uv sync` is idempotent — safe to re-run anytime — and creates `.venv/`, installing the
locked dependencies from `uv.lock`. Fill in the copied `.env` per [§3](#3-fill-in-secrets-env)
below. Install the Claude Code plugins listed in [§6](#6-plugins) separately — the
vendored fork from this repo's `.claude/marketplace/` (registered as a GitHub source), the
rest from the official Anthropic marketplace.

## 3. Fill in secrets (`.env`)

Minimum required values:

```env
ANTHROPIC_API_KEY=sk-ant-...
SUPABASE_URL=https://your-project-id.supabase.co
SUPABASE_KEY=your-anon-key-here
```

> **Where to get Supabase credentials:** Supabase dashboard → your project → Settings →
> API → Project URL + anon public key.

Apply the migrations under `supabase/migrations/` (in filename order) to your project via the
Supabase SQL Editor or CLI to create those tables. (The reactive-core tables the early migrations also create are retired; see `supabase/schema.sql`'s header.)
`supabase/schema.sql` is the declarative target shape those migrations converge on, not a
from-scratch bootstrap script — see [MCP & environment](reference/mcp-and-environment.md).

Optional, depending on what you use:

- `GITHUB_TOKEN` — for the `github` MCP server (see [§5](#5-manual-mcp-registration-checklist))
- `FIRECRAWL_API_KEY` — for web research

## 4. `~/.claude/` — make it your own private dotfiles repo

Jarvis used to ship an installer (`install.ps1` / `install.sh` /
`scripts/install/installer.py`) that synced skills, hooks, and MCP config from this
repo into `~/.claude/` on every device. **That installer was
retired in [#1800](https://github.com/Osasuwu/jarvis/issues/1800).** Per decision
[`57fd2895`](https://github.com/Osasuwu/jarvis), the target model is: `~/.claude/` is
*your own* private dotfiles repo, which you create and version yourself (like a
personal `dotfiles` repo for shell config) — not something synced in from
this repo by a script.

This repo ships no user-level skills (#1923). The reference instance
([`Osasuwu/jarvis-private`](https://github.com/Osasuwu/jarvis-private), private) keeps its
skills, subagents, hooks, `CLAUDE.md`, `SOUL.md`, `reference/` docs and their tests in a
private dotfiles repo that is **its own Claude Code plugin marketplace** — Claude Code clones
and updates it, so nothing is junctioned, symlinked or synced into `~/.claude/` by hand. The
pattern:

- **The repo is a one-plugin marketplace.** `.claude-plugin/marketplace.json` lists a single
  plugin whose `source` is `"./"` (the repo root), and `.claude-plugin/plugin.json` gives it
  a name. Leave `version` out of both: Claude Code then versions the plugin by commit SHA, so
  every pushed commit is an update.
- **Skills, subagents and hooks live in the plugin** — `skills/<name>/SKILL.md`,
  `agents/<name>.md`, and `hooks/hooks.json` (same shape as the `hooks` object in
  `settings.json`; reference the plugin's own scripts as `${CLAUDE_PLUGIN_ROOT}/...`).
  Plugin skills are namespaced `/<plugin>:<name>`; the bare `/<name>` also works unless
  another command already uses that name (e.g. a project skill in `.claude/skills/`).
  Plugin subagents are named `<plugin>:<agent>`.
- **Each device declares the marketplace** in `~/.claude/settings.json`:

  ```json
  {
    "extraKnownMarketplaces": {
      "<marketplace>": {
        "source": { "source": "github", "repo": "<you>/<dotfiles-repo>" },
        "autoUpdate": true
      }
    },
    "enabledPlugins": { "<plugin>@<marketplace>": true }
  }
  ```

  `autoUpdate` defaults to `false` for third-party marketplaces, so set it explicitly. A
  private repo is cloned with the device's normal git credentials (credential helper or SSH
  key).
- **`~/.claude/CLAUDE.md` stays a stub** of bare `@import` lines, each on its own line,
  pointing into the marketplace clone at
  `~/.claude/plugins/marketplaces/<marketplace>/` (e.g. its `CLAUDE.md` and `SOUL.md`).
  Claude Code doesn't load a `CLAUDE.md` at a plugin root, so the import is how rules ride
  the same auto-updated checkout.
- **Per-device settings stay per device.** A plugin's own `settings.json` applies only
  `agent` and `subagentStatusLine`; `permissions`, `env`, `autoMode`, `defaultMode` and the
  like stay in each device's `~/.claude/settings.json`.

Edit the rules and skills in a separate clone of the repo and push — never in
`~/.claude/plugins/marketplaces/`, which Claude Code updates in place. The reference
repo's README (*Per-device setup*) has the one-command install for a new device. Use
[`config/SOUL.md`](../config/SOUL.md) as the template for your own `SOUL.md`, and adapt the
layout to your own setup. Plugins enabled only in user settings don't load in cloud
sessions (see [§9](#9-cloud-scheduled-tasks)). The manual MCP registration checklist below is
exactly what replaces what the legacy installer would otherwise have auto-seeded.

## 5. Manual MCP registration checklist

Memory is native and file-based (`~/.claude/projects/<project>/memory/`) — no server to run
or verify. The `mcp-memory`/`mcp-status`/`mcp-morning` project-local MCP servers this section
used to describe were retired in [#1801](https://github.com/Osasuwu/jarvis/issues/1801); the
`telegram` plugin ([§7](#7-telegram-optional)) is the one remaining MCP-adjacent surface, and
it's a Claude Code Channels plugin, not a script you launch. Register the following by hand:

- [ ] **`github`** — HTTP transport, GitHub's own remote MCP endpoint:

  ```bash
  claude mcp add --transport http --scope user github https://api.githubcopilot.com/mcp \
    --header "Authorization: Bearer $GITHUB_TOKEN"
  ```

  (`$GITHUB_TOKEN` from your `.env`, or substitute `$(gh auth token)`.)

- [ ] **`obsidian`** — *device-gated*: only register this on a device where you actually
  keep an Obsidian vault. Skip it entirely otherwise.

  ```bash
  claude mcp add --transport stdio --scope user --env OBSIDIAN_VAULT_PATH="/path/to/your/vault" \
    obsidian -- npx -y @bitbonsai/mcpvault@latest "$OBSIDIAN_VAULT_PATH"
  ```

- [ ] Verify both: `claude mcp list` should show `github` and (if registered) `obsidian`
  as connected.

## 6. Plugins

Install commands below for each plugin:

| Plugin | Source | Install |
|---|---|---|
| `code-review` | **Fork** of `anthropics/claude-plugins-official`, tag-pinned in this repo's `.claude/marketplace/` ([`docs/reference/vendored-plugin-pins.md`](reference/vendored-plugin-pins.md)). Kept forked: upstream silently drops review results when a sub-reviewer runs backgrounded under headless CI (`claude -p`) — jarvis#1239 / PR #1237. | Declare the marketplace in `~/.claude/settings.json` (below), then `/plugin install code-review@jarvis-fork-plugins` |
| `pr-review-toolkit` | Official Anthropic marketplace, unmodified | `/plugin install pr-review-toolkit@claude-plugins-official` |
| `session-report` | Official Anthropic marketplace, unmodified | `/plugin install session-report@claude-plugins-official` |
| `hookify` | Official Anthropic marketplace, unmodified | `/plugin install hookify@claude-plugins-official` |
| `claude-md-management` | Official Anthropic marketplace, unmodified | `/plugin install claude-md-management@claude-plugins-official` |
| `mcp-server-dev` | Official Anthropic marketplace, unmodified | `/plugin install mcp-server-dev@claude-plugins-official` |

The fork's marketplace file sits at `.claude/marketplace/.claude-plugin/marketplace.json`,
not at the repo root, and `claude plugin marketplace add` has no option for a non-default
marketplace path — so declare it as a GitHub source in `~/.claude/settings.json`, with a
sparse checkout of just that directory:

```json
{
  "extraKnownMarketplaces": {
    "jarvis-fork-plugins": {
      "source": {
        "source": "github",
        "repo": "Osasuwu/jarvis",
        "path": ".claude/marketplace/.claude-plugin/marketplace.json",
        "sparsePaths": [".claude/marketplace"]
      },
      "autoUpdate": true
    }
  }
}
```

This tracks `main` on GitHub and works on any device, with or without a clone of this
repo. If you registered the fork the old way (`claude plugins marketplace add
./.claude/marketplace`, a `directory` source), remove that marketplace first — removing a
marketplace also uninstalls every plugin installed from it, so run the
`/plugin install code-review@jarvis-fork-plugins` again after switching.

If `/plugin install <id>@claude-plugins-official` fails with an unknown-marketplace
error, the official marketplace isn't registered on your device yet — check with
`claude plugins marketplace list`, and if it's missing, add it with
`claude plugins marketplace add anthropics/claude-plugins-official` first.

`telegram` is also an official-marketplace plugin, but it isn't part of the classified
list above (it's not in `.claude/marketplace/`) — see [§7](#7-telegram-optional).

## 7. Telegram (optional)

Jarvis uses [Claude Code Channels](https://code.claude.com/docs/en/channels) — the
official Anthropic plugin — to connect to Telegram. No custom relay needed.

1. Create a bot via [@BotFather](https://t.me/BotFather): `/newbot`, pick a display name
   and a username ending in `bot`. BotFather gives you a token like
   `123456789:AAHfiqksKZ8...`.
2. Install the plugin: `/plugin install telegram@claude-plugins-official`, then
   `/reload-plugins`.
3. Set the token:
   ```bash
   mkdir -p ~/.claude/channels/telegram
   echo "TELEGRAM_BOT_TOKEN=123456789:AAHfiqksKZ8..." > ~/.claude/channels/telegram/.env
   ```
   (or export `TELEGRAM_BOT_TOKEN` as a shell variable — takes precedence over the file)
4. Start with Channels: `claude --channels plugin:telegram@claude-plugins-official`
5. Pair your account: `/telegram:access pair` in the Claude Code session → send the code
   to your bot in Telegram → back in the session, run
   `/telegram:access policy allowlist` to lock access to just your paired account.
6. Test: message your bot from Telegram — Claude should respond.

For 24/7 availability, run step 4 on one always-on machine (home PC, server, or VPS) —
Channels runs on whichever machine has an active session; native memory files are
per-machine, not shared across devices by this mechanism.

**Troubleshooting:** bot silent → confirm the session is running with `--channels` and
the token has no extra whitespace. "Plugin not found" → run `/reload-plugins` after
install. Unauthorized senders getting through → re-run
`/telegram:access policy allowlist`.

> **`TELEGRAM_ALLOW_USER_ID` is a different thing** — it is *not* part of Channels
> pairing above. It was the target chat id read by the orchestrator-escalation notifier,
> `agents/notify.py`, demolished along with the rest of reactive-core in #1802 with no
> replacement yet — used when jarvis needed to page you outside of an active session.
> Currently unused; unrelated to whether Channels pairing succeeded.

## 8. GitHub Actions secrets (if you run this repo's CI)

Required secrets in GitHub repo settings (Settings → Secrets and variables → Actions):

| Secret | Used by | Purpose |
|--------|---------|---------|
| `CLAUDE_CODE_OAUTH_TOKEN` | `code-review.yml` | `anthropics/claude-code-action` for PR review |

`GITHUB_TOKEN` is auto-provisioned by GitHub Actions — no setup needed.

## 9. Cloud scheduled tasks

Scheduled tasks on claude.ai use connectors only, not project-local MCP config. Skills
are designed to work in both environments: locally via native memory files, in the cloud
via the Supabase connector's `execute_sql` and the `gh` CLI.

Task prompts should invoke skills via slash command — this resolves against whichever
Claude Code home (`~/.claude/`) is loaded:

```
Run /research
```

`/research` selects discovery mode automatically when no topic argument is supplied.
Cloud sessions (routines) don't load plugins enabled only in your user settings or skills
from your machine's `~/.claude/`: a skill a cloud task calls has to be enabled for your
claude.ai account or committed to the repo's `.claude/skills/`. Desktop scheduled tasks run
locally and do load your plugin, so they pick up each pushed skill change on its next update.

## 10. Lockfile regeneration

CI installs from `uv.lock` to guarantee reproducible dependency resolution.
Nothing regenerates it automatically: when Dependabot bumps a range in `pyproject.toml`,
`lockfile-check` (`uv lock --check`) goes red until a maintainer regenerates it. To
regenerate (after a Dependabot bump, or when adding a dependency locally):

```bash
uv lock --project .
```

Commit the regenerated `uv.lock` files — this ensures CI and local environments resolve
to byte-identical packages.

## Validation checklist

```bash
# Python dependencies
python -c "import mcp, supabase, httpx; print('deps OK')"

# Supabase connection
python -c "
from dotenv import load_dotenv; load_dotenv()
import os; from supabase import create_client
c = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_KEY'])
print('Supabase OK:', c.table('task_queue').select('id').limit(1).execute())
"

# Claude Code + GitHub CLI
claude --version
gh auth status

# MCP servers registered
claude mcp list
```

Then open the project in Claude Code and run `/triage`.

## Key paths

| What | Path |
|------|------|
| Secrets | `.env` (not committed) |
| Secrets template | `.env.example` |
| Personality | `config/SOUL.md` |
| Native memory | `~/.claude/projects/<project>/memory/` |
| Supabase schema (declarative target) | `supabase/schema.sql` |
| Vendored plugin fork + its pin | `.claude/marketplace/`, [`docs/reference/vendored-plugin-pins.md`](reference/vendored-plugin-pins.md) |
| Project-scoped skills (jarvis-only) | `.claude/skills/` |
| User-level skills source of truth | your private dotfiles repo, delivered as a Claude Code plugin from its own marketplace (clone at `~/.claude/plugins/marketplaces/<marketplace>/`) — not in this repo (#1923, see [§4](#4-claude--make-it-your-own-private-dotfiles-repo)) |
