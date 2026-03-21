# Jarvis Architecture

Version: 2.0
Date: 2026-03-21
Status: Active

## 1. System Overview

Jarvis is a universal personal AI agent built on the OpenClaw platform. OpenClaw provides the runtime, communication gateway, and extensibility framework. Jarvis adds custom skills, personality, and domain-specific logic.

## 2. Platform: OpenClaw

OpenClaw handles:
- **Gateway**: central process managing connections and sessions
- **Messaging**: Telegram (mobile), direct UI (workstation)
- **LLM integration**: Ollama (local), cloud providers (fallback)
- **Skills framework**: directory-based skills with SKILL.md metadata
- **Dashboard**: web UI for configuration, chat, and monitoring

Jarvis does NOT fork or modify OpenClaw — it configures and extends it.

## 3. Jarvis Layer

What this repository contains:

```
jarvis/
├── SOUL.md              # Jarvis personality, expertise, communication style
├── skills/              # Custom OpenClaw skills
│   ├── triage/          # Daily triage across GitHub projects
│   │   └── SKILL.md
│   ├── weekly-report/   # Weekly delivery report
│   │   └── SKILL.md
│   ├── issue-health/    # Issue metadata validation
│   │   └── SKILL.md
│   └── ...              # Future skills
├── config/              # OpenClaw configuration
└── docs/                # Project documentation
```

Each skill is a directory with:
- `SKILL.md` — metadata, description, tool permissions, instructions for the LLM
- Supporting files as needed (templates, scripts)

## 4. Communication Flow

```
User (Telegram / Direct UI)
    ↓
OpenClaw Gateway
    ↓
LLM (Ollama local → free cloud fallback)
    ↓
Skill execution (gh CLI, file ops, web search, etc.)
    ↓
Response back to user
```

## 5. LLM Strategy

Primary: Ollama running locally
- Hardware constraint: RTX 3050 6GB limits to ~7B quantized models
- Candidates: Mistral 7B, Llama 3 8B (Q4 quantization)

Fallback: free cloud model
- Must not lose significant quality vs local
- Activated when local model is unavailable or task exceeds local capability

Future: company server with RTX 40 series enables larger models (13B+).

## 6. Skills Architecture

### PM Skills (P1)

**Triage skill**: runs `gh` CLI commands across configured repositories, checks for stale issues, missing metadata, blocked items. Produces summary report.

**Weekly report skill**: collects closed issues and merged PRs from the past week across all projects. Generates markdown summary.

**Issue health skill**: validates issue templates compliance, parent-child linkage, label consistency.

### Research Skills (P2)

**Web research skill**: search, retrieve, summarize, cite sources. Store results for later reference.

### Future Skills (P3+)

Added based on real usage patterns, not speculation.

## 7. Safety Model

Pragmatic approach:
- OpenClaw runs on localhost only, not exposed to network.
- Skills do not get access to critical system paths.
- Destructive operations (file deletion, system commands) require explicit user confirmation through OpenClaw's built-in mechanisms.
- No over-engineering — trust the platform's defaults, add restrictions only where real risk exists.

## 8. Data and State

- **Conversation memory**: managed by OpenClaw
- **Skill state**: files in skill directories as needed
- **GitHub data**: accessed live via `gh` CLI (no local cache/DB)
- **Configuration**: OpenClaw config files + SOUL.md

## 9. Development Workflow

This repository is developed using Claude Code with GitHub workflows for CI and process checks. The `.github/` directory contains workflows and templates for developing Jarvis itself — they are NOT Jarvis features.

Jarvis features = OpenClaw skills in `skills/` directory.
Dev process tools = `.github/` workflows, issue templates, PR checks.
