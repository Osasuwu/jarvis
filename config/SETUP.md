# Jarvis / OpenClaw Setup Guide

## Prerequisites

- Node.js 22+ (tested with v24.14.0)
- npm 11+
- OpenSSL (for token generation) or PowerShell
- Windows 11 (primary), Linux (server)

## 1. Install OpenClaw

```bash
npm install -g openclaw@latest
openclaw --version  # verify: 2026.3.13+
```

## 2. Configure Gateway

```bash
# Local-only, not exposed to network
openclaw config set gateway.mode local
openclaw config set gateway.bind loopback
openclaw config set gateway.port 18789

# Auth token (generate once)
# Linux/macOS:
GATEWAY_TOKEN=$(openssl rand -hex 32)
# Windows PowerShell (if openssl not available):
# $GATEWAY_TOKEN = -join ((1..32) | ForEach-Object { "{0:x2}" -f (Get-Random -Max 256) })
openclaw config set gateway.auth.mode token
openclaw config set gateway.auth.token "$GATEWAY_TOKEN"

# Disable memory search (no embedding provider)
openclaw config set agents.defaults.memorySearch.enabled false
```

Config is stored at `~/.openclaw/openclaw.json`.

## 3. Start Gateway

```bash
# Foreground (for testing):
openclaw gateway

# Check status:
openclaw gateway status

# Dashboard:
# http://127.0.0.1:18789/
```

Note: on Windows, `openclaw gateway install` may fail due to permissions. Run gateway manually or via startup script.

## 4. LLM Providers

### Model priority chain

1. **Google Gemini 2.5 Flash** (primary) — free tier: 1000 req/day, fast, high quality
2. **Groq Qwen3-32B** (fallback #1) — free tier, very fast inference, strong tool use
3. **Ollama qwen3:8b** (fallback #2) — local, unlimited, slow on weak GPU

Cloud models are primary while hardware is limited (RTX 3050 6GB). Ollama serves as unlimited offline safety net. When better GPU is available, flip Ollama back to primary.

### Cloud API keys

Set as environment variables (or in `.env`):

```bash
# Google Gemini (https://aistudio.google.com/apikey — free tier: 1000 req/day on Flash)
export GEMINI_API_KEY="..."

# Groq (https://console.groq.com — free tier)
export GROQ_API_KEY="gsk_..."
```

Groq and Google are built-in providers — no `models.providers` config needed, just the env vars.

### Ollama (local fallback)

Install Ollama from https://ollama.com, then pull the model:

```bash
ollama pull qwen3:8b
```

### OpenClaw model config

Set directly in `~/.openclaw/openclaw.json` (individual `config set` commands fail validation because `baseUrl` and `models` are both required). **Merge** these sections into the existing config — do not replace the whole file:

Add a `"models"` top-level key:

```json
"models": {
  "providers": {
    "ollama": {
      "baseUrl": "http://localhost:11434",
      "apiKey": "ollama-local",
      "api": "ollama",
      "models": [
        {
          "id": "qwen3:8b",
          "name": "Qwen3 8B",
          "reasoning": true,
          "input": ["text"],
          "cost": { "input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0 },
          "contextWindow": 32768,
          "maxTokens": 4096
        }
      ]
    }
  }
}
```

Add `"model"` inside the existing `agents.defaults` section:

```json
"agents": {
  "defaults": {
    "model": {
      "primary": "google/gemini-2.5-flash",
      "fallbacks": ["groq/qwen/qwen3-32b", "ollama/qwen3:8b"]
    }
  }
}
```

Important: do NOT add `/v1` to Ollama baseUrl — it breaks tool calling.

Verify with `openclaw models list` — should show Gemini as default, Groq as fallback#1, Ollama as fallback#2.

## 6. Telegram Bot

### Create the bot

1. Open Telegram, find [@BotFather](https://t.me/BotFather)
2. Send `/newbot`, choose a name and username
3. Copy the bot token (format: `123456:ABC-DEF...`)

### Connect to OpenClaw

```bash
# Add Telegram channel with bot token (replace with your token from BotFather)
openclaw channels add --channel telegram --token "123456:ABC-DEF..."

# Restrict to your Telegram user ID only (get yours from @userinfobot)
openclaw config set channels.telegram.allowFrom "[123456789]"

# Restart gateway to apply
openclaw gateway restart
```

### Verify

Send any message to your bot in Telegram. It should reply and the conversation should appear in the dashboard at `http://127.0.0.1:18789/`.

### Settings reference

| Setting | Description |
|---|---|
| `channels.telegram.enabled` | Enable/disable the channel |
| `channels.telegram.botToken` | Bot token from BotFather |
| `channels.telegram.allowFrom` | Primary safety control: array of allowed Telegram user IDs. If unset, the bot may respond to anyone. |
| `channels.telegram.dmPolicy` | `pairing` (default) — within `allowFrom` set, pair with whoever writes first. Without `allowFrom`, replies to anyone. |
| `channels.telegram.groupPolicy` | `allowlist` (default) — only respond in explicitly allowed groups. Without allowlist, drops all group messages. |
| `channels.telegram.streaming` | `partial` — stream responses as they generate |

## 7. Health Check

```bash
openclaw doctor
openclaw doctor --fix  # auto-fix common issues
```

## Key Paths

| What | Path |
|---|---|
| Config | `~/.openclaw/openclaw.json` |
| Workspace | `~/.openclaw/workspace/` |
| SOUL.md | `~/.openclaw/workspace/SOUL.md` |
| Custom skills | `~/.openclaw/workspace/skills/` |
| Logs | Linux: `/tmp/openclaw/`, Windows: see gateway output for log path |
| Sessions | `~/.openclaw/agents/main/sessions/` |
