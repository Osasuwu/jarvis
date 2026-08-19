"""Tests for focus_signal pure-function module (#1594).

Covers: compute() directly (not through a digest engine), grouping by project,
drift detection, unattributed records, coarse marker, absence of nudges,
provenance contract, and window filtering.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

import pytest

from focus_signal import (
    COARSE_NOTICE,
    WINDOW_DAYS_DEFAULT,
    DecisionEpisode,
    FocusSignalResult,
    GoalInfo,
    compute,
)


# ============================================================================
# Fixture helpers
# ============================================================================


def _iso(days_ago: float = 0, *, now: datetime | None = None) -> str:
    base = now or datetime.now(timezone.utc)
    return (base - timedelta(days=days_ago)).isoformat()


def _ep(
    episode_id: str,
    project: str | None,
    days_ago: float = 1,
    now: datetime | None = None,
) -> DecisionEpisode:
    return DecisionEpisode(
        episode_id=episode_id,
        project=project,
        created_at=_iso(days_ago, now=now),
    )


def _goal(project: str, priority: str, name: str = "") -> GoalInfo:
    return GoalInfo(project=project, priority=priority, name=name)


# ============================================================================
# AC1: compute is a pure function testable directly
# ============================================================================


def test_compute_returns_focus_signal_result():
    """compute() returns a FocusSignalResult, no I/O required."""
    result = compute(episodes=[], goals=[])
    assert isinstance(result, FocusSignalResult)


# ============================================================================
# AC2: window_days is explicitly defined and used
# ============================================================================


def test_compute_window_explicitly_defined():
    """window_days in result matches the argument passed."""
    result = compute(episodes=[], goals=[], window_days=7)
    assert result.window_days == 7


def test_compute_default_window():
    """Default window is WINDOW_DAYS_DEFAULT."""
    result = compute(episodes=[], goals=[])
    assert result.window_days == WINDOW_DAYS_DEFAULT


def test_compute_window_filters_old_episodes():
    """Episodes older than window_days are excluded from the count."""
    now = datetime.now(timezone.utc)
    episodes = [
        _ep("old", "jarvis", days_ago=15, now=now),  # outside 14-day window
        _ep("new", "jarvis", days_ago=5, now=now),  # inside
    ]
    goals = [_goal("redrobot", "P0"), _goal("jarvis", "P1")]
    result = compute(episodes=episodes, goals=goals, window_days=14, now=now)
    # Only the recent episode should count
    assert result.project_counts.get("jarvis", 0) == 1
    assert result.total_episodes == 1


# ============================================================================
# AC3: skew detection → observation
# ============================================================================


def test_compute_observation_on_skew():
    """40/40 decisions in jarvis, P0 goal in redrobot → observation emitted."""
    now = datetime.now(timezone.utc)
    episodes = [_ep(f"ep{i}", "jarvis", days_ago=1, now=now) for i in range(40)]
    goals = [_goal("redrobot", "P0"), _goal("jarvis", "P1")]

    result = compute(episodes=episodes, goals=goals, window_days=14, now=now)

    assert len(result.observations) >= 1
    obs_text = "\n".join(result.observations)
    assert "jarvis" in obs_text
    assert "redrobot" in obs_text


def test_compute_no_observation_when_aligned():
    """Decisions in top-priority-goal project → no drift observation."""
    now = datetime.now(timezone.utc)
    episodes = [_ep(f"ep{i}", "redrobot", days_ago=1, now=now) for i in range(10)]
    goals = [_goal("redrobot", "P0"), _goal("jarvis", "P1")]

    result = compute(episodes=episodes, goals=goals, window_days=14, now=now)

    assert result.observations == []


def test_compute_no_observation_when_no_goals():
    """No goals → no comparison possible → no observations."""
    now = datetime.now(timezone.utc)
    episodes = [_ep(f"ep{i}", "jarvis", days_ago=1, now=now) for i in range(5)]

    result = compute(episodes=episodes, goals=[], window_days=14, now=now)

    assert result.observations == []


def test_compute_no_observation_when_no_episodes():
    """No episodes → no observations."""
    goals = [_goal("redrobot", "P0")]
    result = compute(episodes=[], goals=goals, window_days=14)
    assert result.observations == []


def test_compute_observation_cites_counts():
    """Observation string includes count data (numbers appear)."""
    now = datetime.now(timezone.utc)
    episodes = [_ep(f"ep{i}", "jarvis", days_ago=1, now=now) for i in range(5)]
    goals = [_goal("redrobot", "P0"), _goal("jarvis", "P1")]

    result = compute(episodes=episodes, goals=goals, window_days=14, now=now)

    assert result.observations
    obs = result.observations[0]
    # focus_count=5, attributed_total=5 — the "N из M" fraction must be cited verbatim.
    assert "5 из 5" in obs, f"Observation doesn't cite the count fraction: {obs!r}"


# ============================================================================
# AC4: unattributed records handled gracefully
# ============================================================================


def test_compute_unattributed_counted_separately():
    """Mix of attributed/unattributed: unattributed_count is correct, no crash."""
    now = datetime.now(timezone.utc)
    episodes = [
        _ep("a1", "jarvis", days_ago=1, now=now),
        _ep("a2", "jarvis", days_ago=1, now=now),
        _ep("u1", None, days_ago=1, now=now),
        _ep("u2", "", days_ago=1, now=now),
    ]
    goals = [_goal("redrobot", "P0")]

    result = compute(episodes=episodes, goals=goals, window_days=14, now=now)

    assert result.unattributed_count == 2
    assert result.project_counts.get("jarvis", 0) == 2


def test_compute_all_unattributed_no_crash():
    """All episodes unattributed → no crash, unattributed_count = total."""
    now = datetime.now(timezone.utc)
    episodes = [_ep(f"u{i}", None, days_ago=1, now=now) for i in range(5)]
    goals = [_goal("jarvis", "P0")]

    result = compute(episodes=episodes, goals=goals, window_days=14, now=now)

    assert result.unattributed_count == 5
    assert result.project_counts == {}
    assert result.observations == []  # can't detect skew without attribution


def test_compute_unattributed_not_in_project_counts():
    """Unattributed entries don't appear in project_counts."""
    now = datetime.now(timezone.utc)
    episodes = [_ep("u1", None, days_ago=1, now=now)]

    result = compute(episodes=episodes, goals=[], window_days=14, now=now)

    assert None not in result.project_counts
    assert "" not in result.project_counts


# ============================================================================
# AC5: output marks signal as coarse
# ============================================================================


def test_compute_output_marks_coarse():
    """coarse_notice is non-empty and describes v1 coarseness."""
    result = compute(episodes=[], goals=[])
    assert result.coarse_notice
    assert len(result.coarse_notice) > 10


def test_compute_coarse_notice_matches_constant():
    """coarse_notice is the canonical COARSE_NOTICE string."""
    result = compute(episodes=[], goals=[])
    assert result.coarse_notice == COARSE_NOTICE


def test_compute_coarse_notice_names_basis():
    """coarse_notice names 'decision' as what the signal is built on."""
    # The signal is built on decision episodes — the notice must say so.
    assert "decision" in COARSE_NOTICE.lower() or "решени" in COARSE_NOTICE.lower()


# ============================================================================
# AC6: no reminders, nudges, counters, escalations
# ============================================================================

_FORBIDDEN_PATTERNS = [
    "переключи",
    "напоминани",
    "эскалац",
    "игнорир",
    "дней без",
    "switch to",
    "reminder",
    "escalat",
    "you should",
    "вам следует",
    "рекоменду",
]


def test_compute_no_reminders_or_nudges_in_observations():
    """Observation strings contain no reminder/nudge/escalation language."""
    now = datetime.now(timezone.utc)
    episodes = [_ep(f"ep{i}", "jarvis", days_ago=1, now=now) for i in range(10)]
    goals = [_goal("redrobot", "P0"), _goal("jarvis", "P1")]

    result = compute(episodes=episodes, goals=goals, window_days=14, now=now)

    all_text = "\n".join(result.observations).lower()
    for pattern in _FORBIDDEN_PATTERNS:
        assert pattern.lower() not in all_text, (
            f"Observation contains forbidden nudge pattern {pattern!r}: {result.observations!r}"
        )


def test_compute_no_days_ignored_counter():
    """Observation must not count 'days ignored' for any project."""
    now = datetime.now(timezone.utc)
    episodes = [_ep(f"ep{i}", "jarvis", days_ago=i + 1, now=now) for i in range(5)]
    goals = [_goal("redrobot", "P0")]

    result = compute(episodes=episodes, goals=goals, window_days=14, now=now)

    all_text = "\n".join(result.observations).lower()
    # No language about days since last touching a project.
    # "за 14д" (window prefix) is fine; a counter like "14 дней без" is not.
    assert not re.search(r"\d+\s*дн(я|ей)\s*без", all_text), (
        f"Observation contains a 'days ignored' counter: {result.observations!r}"
    )
    assert "days since" not in all_text
    assert "дней с" not in all_text


# ============================================================================
# AC7: provenance contract — section carries provenance marker;
#      when source unavailable, prints empty with reason
# ============================================================================


def test_compute_provenance_ok_when_source_available():
    """Normal run: provenance_ok=True."""
    result = compute(episodes=[], goals=[], source_available=True)
    assert result.provenance_ok is True
    assert result.provenance_reason == ""


def test_compute_provenance_not_ok_when_source_unavailable():
    """source_available=False → provenance_ok=False, observations empty."""
    result = compute(
        episodes=[],
        goals=[],
        source_available=False,
        source_failure_reason="goals table unavailable",
    )
    assert result.provenance_ok is False
    assert result.observations == []


def test_compute_provenance_reason_preserved():
    """source_failure_reason is reflected in provenance_reason."""
    reason = "Supabase connection timeout"
    result = compute(
        episodes=[],
        goals=[],
        source_available=False,
        source_failure_reason=reason,
    )
    assert result.provenance_reason == reason


def test_compute_source_unavailable_suppresses_observations():
    """Even with real episodes+goals, source_available=False → no observations."""
    now = datetime.now(timezone.utc)
    episodes = [_ep(f"ep{i}", "jarvis", days_ago=1, now=now) for i in range(40)]
    goals = [_goal("redrobot", "P0")]

    result = compute(
        episodes=episodes,
        goals=goals,
        window_days=14,
        now=now,
        source_available=False,
        source_failure_reason="goals unavailable",
    )

    assert result.observations == []
    assert result.provenance_ok is False
