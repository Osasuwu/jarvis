import pytest

from scripts.digest_schema import (
    AbsenceKind,
    SCHEMA_VERSION,
    Digest,
    Plan,
    PlanItem,
    Section,
    SectionProvenance,
    fold_provenance,
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


# ============================================================================
# #1589 — section provenance fields: input_rows, absence_reason, absence_kind
# ============================================================================


def test_section_provenance_carries_input_rows_and_absence_fields():
    prov = SectionProvenance(
        ran=True,
        ok=False,
        source="morning_gather",
        input_rows=5,
        absence_reason="query timed out",
        absence_kind=AbsenceKind.FAILED,
    )

    d = prov.to_dict()

    assert d["input_rows"] == 5
    assert d["absence_reason"] == "query timed out"
    assert d["absence_kind"] == AbsenceKind.FAILED


def test_section_provenance_round_trips_new_fields():
    original = SectionProvenance(
        ran=False,
        ok=False,
        source="",
        input_rows=0,
        absence_reason="blocked by #1338",
        absence_kind=AbsenceKind.NOT_CONNECTED,
    )

    restored = SectionProvenance.from_dict(original.to_dict())

    assert restored.input_rows == 0
    assert restored.absence_reason == "blocked by #1338"
    assert restored.absence_kind == AbsenceKind.NOT_CONNECTED


# ============================================================================
# #1589 — fold_provenance: explicit operation, no silent stamp loss
# ============================================================================


def _section(name: str, ok: bool, absence_kind: str | None = None) -> Section:
    return Section(
        name=name,
        items=[],
        provenance=SectionProvenance(
            ran=not ok if absence_kind == AbsenceKind.NOT_CONNECTED else True,
            ok=ok,
            absence_kind=absence_kind,
        ),
    )


def test_fold_provenance_preserves_all_stamps_without_silent_loss():
    sections = [
        _section("good", ok=True),
        _section("failed_source", ok=False, absence_kind=AbsenceKind.FAILED),
        _section("not_wired", ok=False, absence_kind=AbsenceKind.NOT_CONNECTED),
    ]

    result = fold_provenance(sections)

    assert result["failures"] == ["failed_source"]
    assert result["known_limitations"] == ["not_wired"]
    assert result["degradation_level"] == 1


def test_fold_provenance_distinguishes_not_connected_from_failed():
    not_connected = Section(
        name="learning",
        items=[],
        provenance=SectionProvenance(ran=False, ok=False, absence_kind=AbsenceKind.NOT_CONNECTED),
    )
    failed = Section(
        name="goals",
        items=[],
        provenance=SectionProvenance(ran=True, ok=False, absence_kind=AbsenceKind.FAILED),
    )

    result = fold_provenance([not_connected, failed])

    assert "learning" in result["known_limitations"]
    assert "learning" not in result["failures"]
    assert "goals" in result["failures"]
    assert "goals" not in result["known_limitations"]
    assert result["degradation_level"] == 1


def test_fold_provenance_all_ok_returns_clean_state():
    sections = [_section("a", ok=True), _section("b", ok=True)]

    result = fold_provenance(sections)

    assert result["degradation_level"] == 0
    assert result["failures"] == []
    assert result["known_limitations"] == []


def test_fold_provenance_multiple_stamps_of_same_kind_all_preserved():
    sections = [
        _section("s1", ok=False, absence_kind=AbsenceKind.FAILED),
        _section("s2", ok=False, absence_kind=AbsenceKind.FAILED),
        _section("s3", ok=False, absence_kind=AbsenceKind.NOT_CONNECTED),
        _section("s4", ok=False, absence_kind=AbsenceKind.NOT_CONNECTED),
    ]

    result = fold_provenance(sections)

    assert set(result["failures"]) == {"s1", "s2"}
    assert set(result["known_limitations"]) == {"s3", "s4"}
    assert result["degradation_level"] == 2


# ============================================================================
# #1589 — Digest carries degradation field; round-trip preserves it
# ============================================================================


def test_digest_degradation_field_round_trips():
    degradation = {"degradation_level": 1, "failures": ["goals"], "known_limitations": ["learning"]}
    digest = Digest(
        schema_version=SCHEMA_VERSION,
        degradation=degradation,
    )

    restored = Digest.deserialize(digest.serialize())

    assert restored.degradation == degradation
