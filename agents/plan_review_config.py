"""Loader for the plan-review classification config (issue #1685).

Single classification artifact: class-2 trigger thresholds and the class-3
mechanical criteria list live in one YAML file (``config/plan_review.yaml``),
loaded by :func:`load_plan_review_config`. No threshold, glob, or criterion
is hardcoded on any code path that consumes this config — every value comes
from the file on disk.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class Class2Thresholds:
    shared_surface_globs: tuple[str, ...]
    churn_threshold: int
    min_prod_areas: int


@dataclass(frozen=True)
class Class3Criteria:
    mechanical_criteria: tuple[str, ...]


@dataclass(frozen=True)
class ModelFloors:
    """Model floors for the plan-review stage (issue #1686 AC9): read from
    operator config, never hardcoded on a call path."""

    planner: str
    critic: str


@dataclass(frozen=True)
class PlanReviewConfig:
    class_2: Class2Thresholds
    class_3: Class3Criteria
    models: ModelFloors


_REQUIRED_CLASS_2_KEYS = ("shared_surface_globs", "churn_threshold", "min_prod_areas")
_REQUIRED_CLASS_3_KEYS = ("mechanical_criteria",)
_REQUIRED_MODELS_KEYS = ("planner", "critic")


def load_plan_review_config(path: Path) -> PlanReviewConfig:
    """Load and validate the plan-review classification config.

    Raises ``FileNotFoundError`` if ``path`` does not exist, ``ValueError``
    if the file is missing a required key.
    """
    if not path.exists():
        raise FileNotFoundError(f"plan-review config not found: {path}")

    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    class_2_raw = raw.get("class_2") or {}
    missing_2 = [k for k in _REQUIRED_CLASS_2_KEYS if k not in class_2_raw]
    if missing_2:
        raise ValueError(f"plan-review config {path}: class_2 missing keys {missing_2}")

    class_3_raw = raw.get("class_3") or {}
    missing_3 = [k for k in _REQUIRED_CLASS_3_KEYS if k not in class_3_raw]
    if missing_3:
        raise ValueError(f"plan-review config {path}: class_3 missing keys {missing_3}")

    models_raw = raw.get("models") or {}
    missing_models = [k for k in _REQUIRED_MODELS_KEYS if k not in models_raw]
    if missing_models:
        raise ValueError(f"plan-review config {path}: models missing keys {missing_models}")

    return PlanReviewConfig(
        class_2=Class2Thresholds(
            shared_surface_globs=tuple(class_2_raw["shared_surface_globs"]),
            churn_threshold=int(class_2_raw["churn_threshold"]),
            min_prod_areas=int(class_2_raw["min_prod_areas"]),
        ),
        class_3=Class3Criteria(
            mechanical_criteria=tuple(class_3_raw["mechanical_criteria"]),
        ),
        models=ModelFloors(
            planner=str(models_raw["planner"]),
            critic=str(models_raw["critic"]),
        ),
    )
