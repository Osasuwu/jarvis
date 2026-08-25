"""Tests for the /verify plan-conformance + rework-round metric (#1692).

Covers agents/plan_conformance.py: missing-section detection on class-2 PR
bodies (AC1/AC2), divergence extraction with stated reasons (AC3), the
rework-round metric definition built on scripts/rework_policy.py's existing
attempts/history concept (AC4/AC5), the ~10-PR checkpoint (AC6), and the
rollback plan (AC7).
"""

from __future__ import annotations

from agents.plan_conformance import (
    CHECKPOINT_DECISIONS,
    CHECKPOINT_THRESHOLD,
    REWORK_BASELINE_PLAN_LEVEL_FRACTION,
    ROLLBACK_STEPS,
    Divergence,
    checkpoint_reached,
    extract_divergences,
    missing_sections,
    rework_round_count,
)

# ---------------------------------------------------------------------------
# AC1/AC2 — missing plan-conformance / plan-divergences sections
# ---------------------------------------------------------------------------


def test_missing_sections_empty_when_both_present():
    body = (
        "## Summary\nfoo\n\n"
        "## Plan-conformance\nImplemented exactly per plan.\n\n"
        "## Plan-divergences\nNone.\n"
    )
    assert missing_sections(body, is_class_2=True) == []


def test_missing_sections_flags_both_absent_on_class_2():
    body = "## Summary\nfoo\n"
    assert missing_sections(body, is_class_2=True) == [
        "Plan-conformance",
        "Plan-divergences",
    ]


def test_missing_sections_flags_only_the_absent_one():
    body = "## Summary\nfoo\n\n## Plan-conformance\nDid the thing.\n"
    assert missing_sections(body, is_class_2=True) == ["Plan-divergences"]


def test_missing_sections_not_class_2_is_never_a_finding():
    body = "## Summary\nfoo\n"
    assert missing_sections(body, is_class_2=False) == []


# ---------------------------------------------------------------------------
# AC3 — divergences surfaced with their stated reason, not merely counted
# ---------------------------------------------------------------------------


def test_extract_divergences_parses_bullet_and_reason():
    body = (
        "## Plan-divergences\n"
        "- Used a dict instead of a dataclass — simpler for this call site\n"
        "- Skipped the CLI wrapper — not needed until #1702 wires a caller\n"
        "\n## Testing\nfoo\n"
    )
    result = extract_divergences(body)
    assert result == [
        Divergence(
            what="Used a dict instead of a dataclass",
            reason="simpler for this call site",
        ),
        Divergence(
            what="Skipped the CLI wrapper",
            reason="not needed until #1702 wires a caller",
        ),
    ]


def test_extract_divergences_no_section_is_empty_list():
    assert extract_divergences("## Summary\nfoo\n") == []


def test_extract_divergences_none_declared_is_empty_list():
    body = "## Plan-divergences\nNone.\n\n## Testing\nfoo\n"
    assert extract_divergences(body) == []


def test_extract_divergences_bullet_without_dash_separator_kept_whole():
    body = "## Plan-divergences\n- Renamed the helper for clarity\n"
    result = extract_divergences(body)
    assert result == [Divergence(what="Renamed the helper for clarity", reason="")]


# ---------------------------------------------------------------------------
# AC4/AC5 — rework-round metric, built on rework_policy.py's attempts/history
# ---------------------------------------------------------------------------


def test_rework_round_count_is_history_length():
    history = [
        {"attempt": 1, "n_critical": 2, "n_major": 1},
        {"attempt": 2, "n_critical": 0, "n_major": 1},
        {"attempt": 3, "n_critical": 0, "n_major": 0},
    ]
    assert rework_round_count(history) == 3


def test_rework_round_count_zero_rounds_no_rework_needed():
    assert rework_round_count([]) == 0


def test_baseline_fraction_matches_1683_classification():
    # #1683's retro-classification of PR #963: 3 of 34 findings were
    # plan-level (memory d20e20b4-a769-4335-bef6-0a34070488e1).
    assert REWORK_BASELINE_PLAN_LEVEL_FRACTION == 3 / 34


# ---------------------------------------------------------------------------
# AC6 — checkpoint at ~10 class-2 PRs
# ---------------------------------------------------------------------------


def test_checkpoint_not_reached_below_threshold():
    assert checkpoint_reached(9) is False


def test_checkpoint_reached_at_threshold():
    assert checkpoint_reached(CHECKPOINT_THRESHOLD) is True


def test_checkpoint_reached_stays_true_past_threshold():
    assert checkpoint_reached(25) is True


def test_checkpoint_decisions_are_the_three_stated_in_advance():
    assert CHECKPOINT_DECISIONS == ("retune", "keep", "rollback")


# ---------------------------------------------------------------------------
# AC7 — rollback path concrete enough to execute
# ---------------------------------------------------------------------------


def test_rollback_steps_nonempty_and_ordered_strings():
    assert len(ROLLBACK_STEPS) > 0
    assert all(isinstance(step, str) and step for step in ROLLBACK_STEPS)
