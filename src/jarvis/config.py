from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class ModelConfig:
    default_model: str
    planning_model: str
    critical_model: str


@dataclass(frozen=True)
class RuntimeConfig:
    anthropic_api_key: str | None
    telegram_bot_token: str | None
    telegram_allow_user_id: str | None
    models: ModelConfig



def load_config() -> RuntimeConfig:
    load_dotenv(ROOT_DIR / ".env")

    return RuntimeConfig(
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN"),
        telegram_allow_user_id=os.getenv("TELEGRAM_ALLOW_USER_ID"),
        models=ModelConfig(
            default_model=os.getenv("JARVIS_MODEL_DEFAULT", "claude-haiku-4.5"),
            planning_model=os.getenv("JARVIS_MODEL_PLANNING", "claude-sonnet-4.6"),
            critical_model=os.getenv("JARVIS_MODEL_CRITICAL", "claude-opus-4.6"),
        ),
    )
