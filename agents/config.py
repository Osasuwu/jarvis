"""Shared configuration for LangGraph agents.

Loaded from environment variables (with sensible defaults for local dev).
See `.env.example` for the canonical list.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# NOTE: `.env` loading happens in the application entry point (see `main.py`),
# not at module import. This keeps `load_config()` deterministic in tests —
# callers that clear env vars get the documented defaults regardless of
# whether a local `.env` is present.


DEFAULT_OLLAMA_HOST = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL = "qwen3:4b"
DEFAULT_POSTGRES_URL = "postgresql://jarvis:jarvis@localhost:5433/agents?sslmode=disable"


@dataclass(frozen=True)
class AgentConfig:
    """Runtime configuration for Pillar 7 agents."""

    ollama_host: str
    ollama_model: str
    postgres_url: str


def load_config() -> AgentConfig:
    """Read environment variables and return an immutable config object."""
    return AgentConfig(
        ollama_host=os.environ.get("OLLAMA_HOST", DEFAULT_OLLAMA_HOST),
        ollama_model=os.environ.get("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL),
        postgres_url=os.environ.get("AGENTS_POSTGRES_URL", DEFAULT_POSTGRES_URL),
    )
