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
class BudgetConfig:
    per_query_usd: float
    per_day_usd: float


@dataclass(frozen=True)
class RuntimeConfig:
    anthropic_api_key: str | None
    telegram_bot_token: str | None
    telegram_allow_user_id: str | None
    models: ModelConfig
    budget: BudgetConfig


def load_config() -> RuntimeConfig:
    load_dotenv(ROOT_DIR / ".env")

    return RuntimeConfig(
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN"),
        telegram_allow_user_id=os.getenv("TELEGRAM_ALLOW_USER_ID"),
        models=ModelConfig(
            default_model=os.getenv("JARVIS_MODEL_DEFAULT", "haiku"),
            planning_model=os.getenv("JARVIS_MODEL_PLANNING", "sonnet"),
            critical_model=os.getenv("JARVIS_MODEL_CRITICAL", "opus"),
        ),
        budget=BudgetConfig(
            per_query_usd=float(os.getenv("JARVIS_MAX_BUDGET_PER_QUERY", "0.30")),
            per_day_usd=float(os.getenv("JARVIS_MAX_BUDGET_PER_DAY", "2.00")),
        ),
    )
