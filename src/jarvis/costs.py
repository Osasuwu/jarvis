from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
COSTS_FILE = ROOT_DIR / ".jarvis" / "costs.json"


def _read_costs() -> dict:
    if not COSTS_FILE.exists():
        return {"days": {}, "sessions": {}}
    return json.loads(COSTS_FILE.read_text(encoding="utf-8"))


def _write_costs(data: dict) -> None:
    COSTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    COSTS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=True), encoding="utf-8")


def get_today_spend() -> float:
    """Return total USD spent today."""
    data = _read_costs()
    day_key = datetime.now(UTC).strftime("%Y-%m-%d")
    day = data.get("days", {}).get(day_key, {})
    return day.get("cost_usd", 0.0)


def check_daily_budget(limit_usd: float) -> tuple[bool, float]:
    """Check if daily budget allows another query.

    Returns (allowed, remaining_usd).
    """
    spent = get_today_spend()
    remaining = limit_usd - spent
    return remaining > 0, round(remaining, 6)


def record_execution(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    session_id: str,
) -> float:
    """Record real cost from SDK (no estimation)."""
    day_key = datetime.now(UTC).strftime("%Y-%m-%d")

    data = _read_costs()

    day = data["days"].setdefault(day_key, {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0})
    day["input_tokens"] += input_tokens
    day["output_tokens"] += output_tokens
    day["cost_usd"] = round(day["cost_usd"] + cost_usd, 6)

    session = data["sessions"].setdefault(
        session_id,
        {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0, "updated_day": day_key},
    )
    session["input_tokens"] += input_tokens
    session["output_tokens"] += output_tokens
    session["cost_usd"] = round(session["cost_usd"] + cost_usd, 6)
    session["updated_day"] = day_key

    _write_costs(data)
    return round(cost_usd, 6)
