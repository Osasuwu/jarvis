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

See issue #30 for Ollama setup. After Ollama is running:

```bash
openclaw config set models.providers.ollama.api ollama
openclaw config set models.providers.ollama.baseUrl "http://localhost:11434"
openclaw config set models.providers.ollama.apiKey "ollama-local"
openclaw config set models.default "ollama/<model-name>"
```

## 5. Telegram Bot

See issue #32 for Telegram setup. After creating bot via BotFather:

```bash
openclaw config set channels.telegram.enabled true
openclaw config set channels.telegram.token "$TELEGRAM_BOT_TOKEN"
openclaw gateway restart
```

## 6. Health Check

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
