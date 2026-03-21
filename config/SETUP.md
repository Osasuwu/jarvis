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

## 4. LLM Provider (Ollama)

Install Ollama from https://ollama.com, then pull the model:

```bash
ollama pull qwen3:8b
```

OpenClaw provider config must be set directly in `~/.openclaw/openclaw.json` (individual `config set` commands fail validation because `baseUrl` and `models` are both required). Add to the JSON:

```json
{
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
  },
  "agents": {
    "defaults": {
      "model": {
        "primary": "ollama/qwen3:8b",
        "fallbacks": ["groq/llama-4-scout-17b-16e-instruct", "google/gemini-2.5-flash"]
      }
    }
  }
}
```

Important: do NOT add `/v1` to Ollama baseUrl — it breaks tool calling.

## 5. Cloud Fallback

Cloud providers activate automatically when Ollama is unavailable. Set API keys as environment variables:

```bash
# Groq (https://console.groq.com — free tier)
export GROQ_API_KEY="gsk_..."

# Google Gemini (https://aistudio.google.com/apikey — free tier: 1000 req/day on Flash)
export GEMINI_API_KEY="..."
```

Groq and Google are built-in providers — no `models.providers` config needed, just the env vars.

Verify with `openclaw models` — fallbacks should show under "Fallbacks".

## 6. Telegram Bot

See issue #32 for Telegram setup. After creating bot via BotFather:

```bash
openclaw config set channels.telegram.enabled true
openclaw config set channels.telegram.token "$TELEGRAM_BOT_TOKEN"
openclaw gateway restart
```

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
