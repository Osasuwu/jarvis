import pytest

from scripts.digest_schema import (
    SCHEMA_VERSION,
    Digest,
    Plan,
    PlanItem,
    Section,
    SectionProvenance,
)


def _sample_digest() -> Digest:
    return Digest(
        schema_version=SCHEMA_VERSION,
        sections=[
            Section(
                name="repo_hygiene",
                items=[{"repo": "Osasuwu/jarvis", "note": "3 stale PRs"}],
                reason=None,
                provenance=SectionProvenance(ran=True, ok=True, source="status_gather"),
            ),
        ],
        plan=Plan(
            items=[
                PlanItem(
                    rank=1,
                    estimate="M",
                    text="redrobot #1943 — CI runner outage",
                    refs=["redrobot#1943"],
                    cites=["drift-1"],
                ),
            ],
            cut_line_after=1,
        ),
        origin={"gathered_at": "2026-08-17T12:00:00+00:00"},
    )


def test_digest_round_trip_serialization_loses_no_fields():
    original = _sample_digest()

    restored = Digest.deserialize(original.serialize())

    assert restored.to_dict() == original.to_dict()
    assert restored.schema_version == SCHEMA_VERSION


def test_arbitrary_new_section_name_round_trips_with_no_schema_change():
    digest = Digest(
        schema_version=SCHEMA_VERSION,
        sections=[Section(name="a_brand_new_section_kind", items=[{"x": 1}])],
    )

    restored = Digest.deserialize(digest.serialize())

    assert restored.section("a_brand_new_section_kind").items == [{"x": 1}]


def test_empty_section_with_reason_is_valid_and_distinct_from_absent_section():
    digest = Digest(
        schema_version=SCHEMA_VERSION,
        sections=[
            Section(name="ci_health", items=[], reason="no CI configured for this repo"),
        ],
    )

    present_but_empty = digest.section("ci_health")
    absent = digest.section("goals")

    assert present_but_empty is not None
    assert present_but_empty.items == []
    assert present_but_empty.reason == "no CI configured for this repo"
    assert absent is None


def test_plan_item_rejects_invalid_estimate():
    with pytest.raises(ValueError):
        PlanItem(rank=1, estimate="XL", text="too big", refs=[], cites=[])
