"""Tests for morning_engine (#1586).

Engine tests go through analyze(sources) -> Digest per the AC. The critical
behavior is cut_line_after: computed by cumulative sum of S/M/L-converted
estimates, not "first N" — a day of three L's and a day of seven S's must
give different boundaries.
"""

from __future__ import annotations

from scripts.detector_gap_log import GapRecord
from scripts.digest_schema import PlanItem, VALID_ESTIMATES
from scripts.morning_gather import MorningGatherResult
from scripts.morning_engine import (
    DAY_BUDGET_UNITS,
    ESTIMATE_UNITS,
    analyze,
    compute_cut_line_after,
)


def _sources(**overrides) -> MorningGatherResult:
    defaults = dict(
        repos=["Osasuwu/jarvis"],
        milestones={"Osasuwu/jarvis": [{"number": 64, "title": "M64"}]},
        decisions=[],
        goals=[],
        owner_tasks=[],
        detector_gaps=[],
        provenance={"gh_milestones": {"ran": True, "ok": True, "input_rows": 1}},
        gathered_at="2026-08-17T12:00:00+00:00",
        errors=[],
    )
    defaults.update(overrides)
    return MorningGatherResult(**defaults)


def test_analyze_returns_digest_with_schema_version_2():
    digest = analyze(_sources())

    assert digest.schema_version == 2


def test_analyze_builds_repo_hygiene_section_from_sources():
    digest = analyze(_sources())

    section = digest.section("repo_hygiene")
    assert section is not None
    assert section.items == [{"repo": "Osasuwu/jarvis", "open_milestones": 1}]


def test_cut_line_differs_for_three_large_items_vs_seven_small_items():
    three_large = [
        PlanItem(rank=i, estimate="L", text=f"item {i}", refs=[], cites=[]) for i in range(1, 4)
    ]
    seven_small = [
        PlanItem(rank=i, estimate="S", text=f"item {i}", refs=[], cites=[]) for i in range(1, 8)
    ]

    cut_large = compute_cut_line_after(three_large)
    cut_small = compute_cut_line_after(seven_small)

    assert cut_large != cut_small
    assert cut_large == 1  # 8 units fits under budget, +8 more does not
    assert cut_small == 7  # all seven 1-unit items fit under the budget


def test_estimate_units_and_day_budget_are_the_single_defined_place():
    assert set(ESTIMATE_UNITS.keys()) == VALID_ESTIMATES
    assert isinstance(DAY_BUDGET_UNITS, int)
    assert compute_cut_line_after([]) == 0


def test_analyze_synthesizes_plan_items_with_all_required_fields():
    sources = _sources(
        goals=[{"slug": "ship-morning-digest", "text": "ship the digest", "estimate": "M"}],
        owner_tasks=[{"id": "task-1", "text": "review PR", "estimate": "S"}],
    )

    digest = analyze(sources)

    assert len(digest.plan.items) == 2
    for item in digest.plan.items:
        assert isinstance(item.rank, int)
        assert item.estimate in VALID_ESTIMATES
        assert isinstance(item.text, str) and item.text
        assert isinstance(item.refs, list)
        assert isinstance(item.cites, list)
    assert digest.plan.cut_line_after is not None


def test_analyze_builds_detector_gaps_section_only_for_repeated_gaps():
    sources = _sources(
        detector_gaps=[
            GapRecord(key="k1", description="gap seen twice", count=2),
            GapRecord(key="k2", description="gap seen once", count=1),
        ]
    )

    digest = analyze(sources)

    section = digest.section("detector_gaps")
    assert section is not None
    assert len(section.items) == 1
    assert "gap seen twice" in section.items[0]
    assert "2" in section.items[0]


def test_analyze_detector_gaps_section_empty_when_no_repeats():
    digest = analyze(_sources(detector_gaps=[GapRecord(key="k1", description="one-off", count=1)]))

    section = digest.section("detector_gaps")
    assert section is not None
    assert section.items == []
    assert section.reason == "no repeated gaps"
