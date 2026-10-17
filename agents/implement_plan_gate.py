"""Interactive `/implement` lane's plan-gate trigger evaluation (#1688).

Ex-ante half of two-point plan-review classification (decision `d34dd65a`):
runs off whatever files-to-touch and estimated churn are known before any
code edit exists. It is best-effort, so it does not need to be exact; the
ex-post half is the `risk-tier` check on the real diff.

Reuses `agents.plan_classifier.classify_task_row` — the one named policy
entry point every consumer (interactive lane, drain, container pick) calls
per its own docstring — and `prod_areas_from_paths` for
deriving `prod_areas` from an estimated file list. No second
implementation of thresholds or classification logic here (AC1).
"""

from __future__ import annotations

from dataclasses import dataclass

from agents.plan_classifier import classify_task_row, prod_areas_from_paths
from agents.plan_review_config import PlanReviewConfig


@dataclass(frozen=True)
class TriggerResult:
    classification: int
    requires_plan: bool


def build_task_row(
    paths: tuple[str, ...],
    churn_lines: int = 0,
    mechanical_criteria: tuple[str, ...] = (),
) -> dict:
    """Build a task_queue-shaped row from an estimated file list — the
    input shape `classify_task_row` already expects (AC1)."""
    return {
        "scope_files": tuple(paths),
        "churn_lines": churn_lines,
        "prod_areas": prod_areas_from_paths(tuple(paths)),
        "mechanical_criteria": tuple(mechanical_criteria),
    }


def evaluate_trigger(
    config: PlanReviewConfig,
    paths: tuple[str, ...],
    labels: tuple[str, ...] = (),
    churn_lines: int = 0,
    mechanical_criteria: tuple[str, ...] = (),
) -> TriggerResult:
    """Classify the estimated change and decide whether the plan stage runs.

    Every class-2 change requires a plan. No label waives it: `labels` is
    supplied by the calling agent, not read from GitHub, so a waiver keyed
    on it (the old `priority:critical` carve-out) let any agent skip the
    planner + critic panel by labelling the issue or by passing the label
    (#2110). `labels` stays in the signature so existing callers (the
    `/implement` step 2a one-liner) keep working; it is not consulted.
    Ordinal 3 (true-HITL, #1707) never requires the class-2 plan gate
    either — it routes to a human, not the planner.
    """
    del labels  # accepted for caller compatibility, never a waiver (#2110)
    row = build_task_row(paths, churn_lines, mechanical_criteria)
    classification = classify_task_row(config, row)
    return TriggerResult(classification=classification, requires_plan=classification == 2)
