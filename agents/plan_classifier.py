"""Plan-review change-set classifier (issue #1685).

Deep module, narrow interface: :func:`classify` is the single entry point
consumed by four call sites (interactive lane, drain, container pick,
CI diff-gate) — classification logic lives here once, not re-derived
per caller. Every threshold, glob, and criterion comes from a
:class:`~agents.plan_review_config.PlanReviewConfig` — nothing here is
hardcoded.

Classification is two-point per decision `d34dd65a`: the same
:func:`classify` call is used ex-ante (at admission, from an estimated
change-set) and ex-post (on the actual diff after the CI diff-gate runs).
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from typing import Any

from agents.plan_review_config import PlanReviewConfig


@dataclass(frozen=True)
class ChangeSet:
    """A change-set description — the classifier's sole input shape."""

    paths: tuple[str, ...]
    churn_lines: int
    prod_areas: int
    mechanical_criteria: tuple[str, ...] = ()


def _touches_shared_surface(paths: tuple[str, ...], globs: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatch(p, g) for p in paths for g in globs)


def classify(config: PlanReviewConfig, change: ChangeSet) -> str:
    """Return "class:3", "class:2", or "class:1" for ``change``.

    Precedence: a mechanical class:3 criterion short-circuits — a
    docs-only/typo-fix/etc. change never escalates to class:2 review even
    if it happens to touch a shared-surface path (e.g. a doc file living
    under a shared-surface glob). Otherwise class:2 triggers when any of
    the three thresholds trip (shared-surface glob hit, churn strictly
    above threshold, or prod-areas at or above the minimum). Default is
    class:1.
    """
    if any(c in config.class_3.mechanical_criteria for c in change.mechanical_criteria):
        return "class:3"

    if _touches_shared_surface(change.paths, config.class_2.shared_surface_globs):
        return "class:2"
    if change.churn_lines > config.class_2.churn_threshold:
        return "class:2"
    if change.prod_areas >= config.class_2.min_prod_areas:
        return "class:2"

    return "class:1"


def classify_task_row(config: PlanReviewConfig, row: dict[str, Any]) -> str:
    """Named class-2 bundle policy, readable per task row (AC7).

    The single entry point every consumer (interactive lane, drain,
    container pick, CI diff-gate) calls against a ``task_queue``-shaped
    dict — same ``scope_files`` key convention as :mod:`agents.scope_hash`
    and :mod:`agents.escalation`. Callers never re-derive the threshold
    conditions themselves; they read a task row and call this function.
    Missing fields default to the least-alarming values rather than
    raising, matching the ``row.get(...)`` convention used elsewhere in
    ``agents/``.
    """
    change = ChangeSet(
        paths=tuple(row.get("scope_files") or ()),
        churn_lines=int(row.get("churn_lines") or 0),
        prod_areas=int(row.get("prod_areas") or 0),
        mechanical_criteria=tuple(row.get("mechanical_criteria") or ()),
    )
    return classify(config, change)
