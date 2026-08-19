"""focus_signal v1: decision-episode drift vs goal priorities (#1594).

Pure-function module. Zero I/O. Intentionally coarse (v1): built exclusively
on decision episodes. Every output surface marks the signal as coarse — do not
upgrade precision here; that is #1577.

Public interface:
    compute(episodes, goals, window_days, *, now, source_available,
            source_failure_reason) -> FocusSignalResult

Two invariants that can never be crossed (decision 43e7493a):
  - The signal is marked as coarse in every output surface.
  - No reminders, nudges, day-counters, or escalations are emitted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Sequence


# ============================================================================
# Constants
# ============================================================================

WINDOW_DAYS_DEFAULT = 14
"""Default look-back window in days."""

COARSE_NOTICE = (
    "Сигнал грубый (v1): только decision-эпизоды, "
    "без событий owner-queue и активности сессий."
)
"""Fixed marker that MUST appear in every result surface. Describes v1 limits."""


# ============================================================================
# Data types
# ============================================================================


@dataclass
class GoalInfo:
    """Minimal goal representation for focus-signal comparison."""

    project: str
    priority: str  # "P0", "P1", "P2", etc.
    name: str = ""


@dataclass
class DecisionEpisode:
    """A recorded decision episode from the memory store."""

    episode_id: str
    project: str | None  # None or "" = unattributed
    created_at: str  # ISO 8601


@dataclass
class FocusSignalResult:
    """Output of compute().

    observations: list of plain observation strings — no nudges or reminders.
    unattributed_count: episodes inside the window with no project attribution.
    project_counts: map of project → episode count (attributed only).
    window_days: the look-back window used in this run.
    total_episodes: attributed + unattributed inside the window.
    coarse_notice: fixed marker that the signal is v1/coarse.
    provenance_ok: False when a required source was unavailable.
    provenance_reason: why provenance_ok is False (empty when ok).
    """

    observations: list[str] = field(default_factory=list)
    unattributed_count: int = 0
    project_counts: dict[str, int] = field(default_factory=dict)
    window_days: int = WINDOW_DAYS_DEFAULT
    total_episodes: int = 0
    coarse_notice: str = COARSE_NOTICE
    provenance_ok: bool = True
    provenance_reason: str = ""


# ============================================================================
# Helpers
# ============================================================================


def _parse_priority(priority: str) -> int:
    """Parse 'P0', 'P1', 'P2' → 0, 1, 2; unknown → 99."""
    p = priority.strip().upper()
    if p.startswith("P") and len(p) > 1 and p[1:].isdigit():
        return int(p[1:])
    return 99


def _parse_iso(iso_str: str) -> datetime | None:
    """Parse ISO 8601 string to a tz-aware datetime; return None on failure."""
    if not iso_str:
        return None
    try:
        dt = datetime.fromisoformat(iso_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def _top_goal_project(goals: Sequence[GoalInfo]) -> str | None:
    """Return the project of the highest-priority (lowest P-number) goal.

    Tie-breaks alphabetically so output is deterministic.
    Returns None when goals is empty.
    """
    if not goals:
        return None
    return min(
        goals,
        key=lambda g: (_parse_priority(g.priority), g.project),
    ).project


# ============================================================================
# Main entry point
# ============================================================================


def compute(
    episodes: Sequence[DecisionEpisode],
    goals: Sequence[GoalInfo],
    window_days: int = WINDOW_DAYS_DEFAULT,
    *,
    now: datetime | None = None,
    source_available: bool = True,
    source_failure_reason: str = "",
) -> FocusSignalResult:
    """Group decision episodes by project, compare against goal priorities.

    Returns observation strings only — no reminders, no nudges, no counters
    of 'days since a project was touched', no escalations (decision 43e7493a).

    When source_available is False, provenance_ok is set to False and
    observations is empty, regardless of the episodes/goals passed in.
    """
    if not source_available:
        return FocusSignalResult(
            window_days=window_days,
            coarse_notice=COARSE_NOTICE,
            provenance_ok=False,
            provenance_reason=source_failure_reason,
        )

    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=window_days)

    # Filter to window and separate attributed vs unattributed.
    project_counts: dict[str, int] = {}
    unattributed = 0

    for ep in episodes:
        dt = _parse_iso(ep.created_at)
        if dt is None or dt < cutoff:
            continue
        if ep.project:
            project_counts[ep.project] = project_counts.get(ep.project, 0) + 1
        else:
            unattributed += 1

    total = sum(project_counts.values()) + unattributed

    observations: list[str] = []

    if project_counts and goals:
        top_goal_project = _top_goal_project(goals)
        # Focus project: the one with the most attributed decisions.
        # Tie-break alphabetically for determinism.
        # ceiling: O(n) over project_counts — fine at solo-dev scale (<20 projects);
        # switch to a running-max accumulator in the loop above if that's crossed
        focus_project = max(
            project_counts,
            key=lambda p: (project_counts[p], p),
        )
        top_goal_priority = min(
            (_parse_priority(g.priority) for g in goals if g.project == top_goal_project),
            default=99,
        )

        if top_goal_project and focus_project != top_goal_project:
            focus_count = project_counts[focus_project]
            attributed_total = sum(project_counts.values())
            top_count = project_counts.get(top_goal_project, 0)
            p_label = f"P{top_goal_priority}" if top_goal_priority < 99 else "high-priority"
            observations.append(
                f"За {window_days}д: {focus_project} — {focus_count} из "
                f"{attributed_total} decision-эпизодов"
                + (f"; {top_goal_project} — {top_count}" if top_count > 0 else "")
                + f". {p_label}-цель в {top_goal_project}."
            )

    return FocusSignalResult(
        observations=observations,
        unattributed_count=unattributed,
        project_counts=project_counts,
        window_days=window_days,
        total_episodes=total,
        coarse_notice=COARSE_NOTICE,
        provenance_ok=True,
        provenance_reason="",
    )
