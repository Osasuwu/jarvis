"""Engine for the `morning` daily-digest capability (#1586).

Pure `analyze(sources) -> Digest`: assembles digest sections from gathered
data and synthesizes a day plan, with cut_line_after computed by cumulative
sum of S/M/L-converted estimates (never "first N").

Render (#1588) and the detector-gap-journal source (#1595) are wired in; the S/M/L
budget-unit translation and the day budget below are the single explicit
place either constant is defined — real calibration is deferred to #1578.

Provenance (#1589): each section carries its own SectionProvenance; fold_provenance
is called explicitly in analyze() so no per-section stamp is ever lost silently.
"""

from __future__ import annotations

from scripts.detector_gap_log import PromoteSuggestion
from scripts.digest_schema import (
    AbsenceKind,
    Digest,
    Plan,
    PlanItem,
    SCHEMA_VERSION,
    Section,
    SectionProvenance,
    fold_provenance,
)
from scripts.morning_gather import MorningGatherResult, MorningSourceKind

# below this repeat count, a gap is still noise, not a promote candidate
_PROMOTE_THRESHOLD = 2

# ceiling: nominal S/M/L->budget-unit mapping and day budget, not yet
# calibrated against real workload; real tuning tracked in #1578. This is
# the single explicit place both constants are defined.
ESTIMATE_UNITS = {"S": 1, "M": 3, "L": 8}
DAY_BUDGET_UNITS = 10


def compute_cut_line_after(items: list[PlanItem], budget_units: int | None = None) -> int:
    """Rank of the last plan item that fits under the day budget, by
    cumulative sum of estimate-converted units — not a fixed item count."""
    budget = DAY_BUDGET_UNITS if budget_units is None else budget_units
    running_total = 0
    cut_line_after = 0
    for item in items:
        cost = ESTIMATE_UNITS[item.estimate]
        if running_total + cost > budget:
            break
        running_total += cost
        cut_line_after = item.rank
    return cut_line_after


def _build_repo_hygiene_section(sources: MorningGatherResult) -> Section:
    milestones_prov = sources.provenance.get(MorningSourceKind.GH_MILESTONES, {})
    ran = milestones_prov.get("ran", False)
    ok = milestones_prov.get("ok", False)
    input_rows = milestones_prov.get("input_rows", 0)

    if not sources.repos:
        return Section(
            name="repo_hygiene",
            items=[],
            reason="no repos gathered",
            provenance=SectionProvenance(
                ran=ran,
                ok=ok,
                source="morning_gather",
                input_rows=input_rows,
            ),
        )

    items = [
        {"repo": repo, "open_milestones": len(sources.milestones.get(repo, []))}
        for repo in sources.repos
    ]
    return Section(
        name="repo_hygiene",
        items=items,
        reason=None,
        provenance=SectionProvenance(
            ran=ran,
            ok=ok,
            source="morning_gather",
            input_rows=input_rows,
        ),
    )


def _build_detector_gaps_section(sources: MorningGatherResult) -> Section:
    gaps_prov = sources.provenance.get(MorningSourceKind.DETECTOR_GAPS, {})
    promotable = [g for g in sources.detector_gaps if g.count >= _PROMOTE_THRESHOLD]

    if not promotable:
        return Section(
            name="detector_gaps",
            items=[],
            reason="no repeated gaps",
            provenance=SectionProvenance(
                ran=gaps_prov.get("ran", False),
                ok=gaps_prov.get("ok", False),
                source="morning_gather",
            ),
        )

    items = [
        PromoteSuggestion(description=g.description, count=g.count).render() for g in promotable
    ]
    return Section(
        name="detector_gaps",
        items=items,
        reason=None,
        provenance=SectionProvenance(
            ran=gaps_prov.get("ran", False),
            ok=gaps_prov.get("ok", False),
            source="morning_gather",
        ),
    )


def _build_learning_section() -> Section:
    """Learning section: always empty pending #1338 (exposition journal).

    Absence kind is NOT_CONNECTED — a stable known limitation, not a failure.
    It appears in the lead line as a known limitation rather than raising the
    degradation level.
    """
    return Section(
        name="learning",
        items=[],
        reason="exposition journal not yet available (blocked by #1338)",
        provenance=SectionProvenance(
            ran=False,
            ok=False,
            source="",
            absence_kind=AbsenceKind.NOT_CONNECTED,
            absence_reason="blocked by #1338",
        ),
    )


def _plan_item_from_row(
    row: dict, rank: int, default_estimate: str, ref_prefix: str, ref_key: str
) -> PlanItem:
    estimate = row.get("estimate")
    if estimate not in ESTIMATE_UNITS:
        estimate = default_estimate

    text = str(row.get("text") or row.get(ref_key) or row.get("title") or ref_prefix)
    ref_value = row.get(ref_key)
    refs = [f"{ref_prefix}:{ref_value}"] if ref_value else []

    return PlanItem(rank=rank, estimate=estimate, text=text, refs=refs, cites=[])


def _synthesize_plan(sources: MorningGatherResult) -> Plan:
    items: list[PlanItem] = []
    rank = 1

    for goal in sources.goals:
        items.append(
            _plan_item_from_row(goal, rank, default_estimate="M", ref_prefix="goal", ref_key="slug")
        )
        rank += 1

    for task in sources.owner_tasks:
        items.append(
            _plan_item_from_row(task, rank, default_estimate="S", ref_prefix="task", ref_key="id")
        )
        rank += 1

    cut_line_after = compute_cut_line_after(items)
    return Plan(items=items, cut_line_after=cut_line_after)


def analyze(sources: MorningGatherResult) -> Digest:
    """Assemble a Digest from gathered morning sources.

    Provenance (#1589): fold_provenance is called as an explicit operation so
    every per-section stamp survives into the top-level degradation summary.
    """
    sections = [
        _build_repo_hygiene_section(sources),
        _build_detector_gaps_section(sources),
        _build_learning_section(),
    ]
    plan = _synthesize_plan(sources)
    degradation = fold_provenance(sections)

    return Digest(
        schema_version=SCHEMA_VERSION,
        sections=sections,
        plan=plan,
        degradation=degradation,
        origin={"gathered_at": sources.gathered_at},
    )
