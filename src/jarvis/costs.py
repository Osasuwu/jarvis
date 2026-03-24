from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
COSTS_FILE = ROOT_DIR / ".jarvis" / "costs.json"


@dataclass(frozen=True)
class ModelPrice:
    input_per_million: float
    output_per_million: float


MODEL_PRICES = {
    "claude-haiku-4.5": ModelPrice(input_per_million=1.0, output_per_million=5.0),
    "claude-sonnet-4.6": ModelPrice(input_per_million=3.0, output_per_million=15.0),
    "claude-opus-4.6": ModelPrice(input_per_million=5.0, output_per_million=25.0),
}


def estimate_tokens(text: str) -> int:
    # Coarse heuristic to keep tracking simple without model-side usage metadata.
    return max(1, len(text) // 4)


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    price = MODEL_PRICES.get(model)
    if price is None:
        return 0.0
    return (
        (input_tokens / 1_000_000) * price.input_per_million
        + (output_tokens / 1_000_000) * price.output_per_million
    )


def _read_costs() -> dict:
    if not COSTS_FILE.exists():
        return {"days": {}, "sessions": {}}
    return json.loads(COSTS_FILE.read_text(encoding="utf-8"))


def _write_costs(data: dict) -> None:
    COSTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    COSTS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=True), encoding="utf-8")


def record_execution(model: str, input_tokens: int, output_tokens: int, session_id: str) -> float:
    day_key = datetime.now(UTC).strftime("%Y-%m-%d")
    cost = estimate_cost_usd(model, input_tokens, output_tokens)

    data = _read_costs()

    day = data["days"].setdefault(day_key, {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0})
    day["input_tokens"] += input_tokens
    day["output_tokens"] += output_tokens
    day["cost_usd"] = round(day["cost_usd"] + cost, 6)

    session = data["sessions"].setdefault(
        session_id,
        {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0, "updated_day": day_key},
    )
    session["input_tokens"] += input_tokens
    session["output_tokens"] += output_tokens
    session["cost_usd"] = round(session["cost_usd"] + cost, 6)
    session["updated_day"] = day_key

    _write_costs(data)
    return round(cost, 6)
