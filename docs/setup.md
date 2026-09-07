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
- [Supabase](https://supabase.com) account (free tier is enough) — powers jarvis's memory
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

## 2. Run the device setup script

```bash
python scripts/setup-device.py
```

This is idempotent — safe to re-run anytime. It:

1. Creates `.venv/` and installs locked dependencies (`uv.lock`)
2. Copies `.env.example` → `.env` (you fill in the values, see below)
3. Validates Python packages, env vars, config files, CLI tools
4. Installs the Claude Code plugins listed in [§7](#7-plugins) — the vendored fork
   directly from `.claude/marketplace`, the rest from the official Anthropic marketplace

## 3. Fill in secrets (`.env`)

Minimum required values:

```env
ANTHROPIC_API_KEY=sk-ant-...
SUPABASE_URL=https://your-project-id.supabase.co
SUPABASE_KEY=your-anon-key-here
```

> **Where to get Supabase credentials:** Supabase dashboard → your project → Settings →
> API → Project URL + anon public key.

Then run `mcp-memory/schema.sql` in the Supabase SQL Editor (SQL Editor → paste the file
contents → Run) to create the `memories` table and vector search function.

Optional, depending on what you use:

- `GITHUB_TOKEN` — for the `github` MCP server (see [§6](#6-manual-mcp-registration-checklist))
- `FIRECRAWL_API_KEY` — for web research

### Semantic search — Voyage AI or Ollama (choose one)

Memory recall degrades to keyword-only without a vector embedding provider.

**Option A — Voyage AI** (cloud, free tier available):

```env
VOYAGE_API_KEY=pa-...
```

Get a key at [voyageai.com](https://www.voyageai.com). Free tier covers typical personal
use.

**Option B — Ollama** (local, GPU recommended, no external API needed):

```env
OLLAMA_EMBED_URL=http://localhost:11434
OLLAMA_EMBED_MODEL=mxbai-embed-large
EMBEDDING_MODEL_PRIMARY=mxbai-embed-large
```

Pull the model: `ollama pull mxbai-embed-large`. Requires [Ollama](https://ollama.com)
running locally. The `mxbai-embed-large` model uses 1024-dim vectors stored in the
`embedding_v2` Supabase column (created by the schema above). **Do not mix providers in
the same database instance** — vectors are model-specific.

## 4. `~/.claude/` — make it your own private dotfiles repo

Jarvis used to ship an installer (`install.ps1` / `install.sh` /
`scripts/install/installer.py`) that synced skills, hooks, and MCP config from this
repo's `.claude-userlevel/` into `~/.claude/` on every device. **That installer still
exists in this repo today** and remains the sync mechanism for the operator's own
existing devices while the migration tracked by
[#1798](https://github.com/Osasuwu/jarvis/issues/1798)/[#1799](https://github.com/Osasuwu/jarvis/issues/1799)/[#1800](https://github.com/Osasuwu/jarvis/issues/1800)/[#1803](https://github.com/Osasuwu/jarvis/issues/1803)
is in flight — if you're picking up an existing jarvis device that already runs it, keep
using it.

**If you're setting up `~/.claude/` for the first time, skip the legacy installer
entirely.** Per decision [`57fd2895`](https://github.com/Osasuwu/jarvis), the target
model is: `~/.claude/` is *your own* private dotfiles repo, which you create and version
yourself (like a personal `dotfiles` repo for shell config) — not something synced in
from `jarvis/.claude-userlevel/` by a script. Copy what you want from
`.claude-userlevel/CLAUDE.md`, `SOUL.md`, `DOCTRINE.md`, and `.claude-userlevel/skills/`
into your own `~/.claude/`, put it under `git`, and adapt it to your own setup. The
manual MCP registration checklist below is exactly what replaces what the legacy
installer would otherwise have auto-seeded into `.mcp.json`.

## 5. Verify the memory server

```bash
python mcp-memory/server.py
```

Expected: it starts and waits (no error). Press Ctrl+C to stop. If you see
`SUPABASE_URL and SUPABASE_KEY must be set`, check `.env`.

## 6. Manual MCP registration checklist

Jarvis's user-scope MCP servers are `memory`, `status` (both project-local — see
`scripts/run-memory-server.py` / `run-status-server.py`), plus two you register by hand:

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

## 7. Plugins

`python scripts/setup-device.py` (§2) installs all of these automatically. Manual
install commands below if you need to redo one:

| Plugin | Source | Install |
|---|---|---|
| `code-review` | **Fork** of `anthropics/claude-plugins-official`, tag-pinned in this repo's `.claude/marketplace/` ([`docs/reference/vendored-plugin-pins.md`](reference/vendored-plugin-pins.md)). Kept forked: upstream silently drops review results when a sub-reviewer runs backgrounded under headless CI (`claude -p`) — jarvis#1239 / PR #1237. | `claude plugins marketplace add ./.claude/marketplace` (from the repo root), then `/plugin install code-review@jarvis-fork-plugins` |
| `pr-review-toolkit` | Official Anthropic marketplace, unmodified | `/plugin install pr-review-toolkit@claude-plugins-official` |
| `session-report` | Official Anthropic marketplace, unmodified | `/plugin install session-report@claude-plugins-official` |
| `hookify` | Official Anthropic marketplace, unmodified | `/plugin install hookify@claude-plugins-official` |
| `claude-md-management` | Official Anthropic marketplace, unmodified | `/plugin install claude-md-management@claude-plugins-official` |
| `mcp-server-dev` | Official Anthropic marketplace, unmodified | `/plugin install mcp-server-dev@claude-plugins-official` |

If `/plugin install <id>@claude-plugins-official` fails with an unknown-marketplace
error, the official marketplace isn't registered on your device yet — check with
`claude plugins marketplace list`, and if it's missing, add it with
`claude plugins marketplace add anthropics/claude-plugins-official` first.

`telegram` is also an official-marketplace plugin, but it isn't part of the classified
list above (it's not in `.claude/marketplace/`) — see [§8](#8-telegram-optional).

## 8. Telegram (optional)

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
Channels runs on whichever machine has an active session, and memory (Supabase) is
shared across devices regardless of which one is hosting it.

**Troubleshooting:** bot silent → confirm the session is running with `--channels` and
the token has no extra whitespace. "Plugin not found" → run `/reload-plugins` after
install. Unauthorized senders getting through → re-run
`/telegram:access policy allowlist`.

> **`TELEGRAM_ALLOW_USER_ID` is a different thing** — it is *not* part of Channels
> pairing above. It's the target chat id read by the orchestrator-escalation notifier in
> [`agents/notify.py`](../agents/notify.py) (currently the env lookups at lines 148 and
> 297, doc comment at line 10) — used when jarvis needs to page you outside of an active
> session. Set it in `.env` if you want that notifier to reach you on Telegram; it's
> unrelated to whether Channels pairing succeeded.

## 9. GitHub Actions secrets (if you run this repo's CI)

Required secrets in GitHub repo settings (Settings → Secrets and variables → Actions):

| Secret | Used by | Purpose |
|--------|---------|---------|
| `CLAUDE_CODE_OAUTH_TOKEN` | `code-review.yml` | `anthropics/claude-code-action` for PR review |
| `SUPABASE_URL` | `event-dispatch.yml` | Supabase project URL for event logging |
| `SUPABASE_ANON_KEY` | `event-dispatch.yml` | Supabase publishable anon key for event logging |

`GITHUB_TOKEN` is auto-provisioned by GitHub Actions — no setup needed. `PROJECT_SYNC` is
optional — falls back to `github.token` if not set.

## 10. Cloud scheduled tasks

Scheduled tasks on claude.ai don't load `.mcp.json` — they use connectors only. Skills
are designed to work in both environments: locally via `memory_store`/`memory_recall`
through the custom MCP server, in the cloud via the Supabase connector's `execute_sql`
and the `gh` CLI.

Task prompts should invoke skills via slash command — this resolves against whichever
Claude Code home (`~/.claude/`) is loaded:

```
Run /research
```

`/research` selects discovery mode automatically when no topic argument is supplied.
Updating a skill in your own `~/.claude/` automatically updates scheduled-task behavior.

## 11. Lockfile regeneration

CI installs from `uv.lock` to guarantee reproducible dependency resolution.
`.github/workflows/dependabot-lockfile.yml` regenerates it automatically when Dependabot
bumps a range in `pyproject.toml` or `mcp-memory/requirements.txt`. For manual
regeneration (e.g. adding a dependency locally):

```bash
uv lock --project .
uv lock --project mcp-memory
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
print('Supabase OK:', c.table('memories').select('id').limit(1).execute())
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
| MCP config (project-scope) | `.mcp.json` (repo root) |
| Memory server | `mcp-memory/server.py` |
| Memory schema | `mcp-memory/schema.sql` |
| Vendored plugin fork + its pin | `.claude/marketplace/`, [`docs/reference/vendored-plugin-pins.md`](reference/vendored-plugin-pins.md) |
| Project-scoped skills (jarvis-only) | `.claude/skills/` |
| Legacy installer (existing devices, mid-migration) | `install.ps1` / `install.sh` / `scripts/install/installer.py`, source in `.claude-userlevel/` |
