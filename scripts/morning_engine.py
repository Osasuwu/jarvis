"""Engine for the `morning` daily-digest capability (#1586).

Pure `analyze(sources) -> Digest`: assembles digest sections from gathered
data and synthesizes a day plan, with cut_line_after computed by cumulative
sum of S/M/L-converted estimates (never "first N").

Render, MCP surface, and skill wiring are out of scope (#1588). The S/M/L
budget-unit translation and the day budget below are the single explicit
place either constant is defined — real calibration is deferred to #1578.
"""

from __future__ import annotations

from scripts.digest_schema import Digest, Plan, PlanItem, SCHEMA_VERSION, Section, SectionProvenance
from scripts.morning_gather import MorningGatherResult, MorningSourceKind

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

    if not sources.repos:
        return Section(
            name="repo_hygiene",
            items=[],
            reason="no repos gathered",
            provenance=SectionProvenance(
                ran=milestones_prov.get("ran", False),
                ok=milestones_prov.get("ok", False),
                source="morning_gather",
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
            ran=milestones_prov.get("ran", False),
            ok=milestones_prov.get("ok", False),
            source="morning_gather",
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
    """Assemble a Digest from gathered morning sources."""
    sections = [_build_repo_hygiene_section(sources)]
    plan = _synthesize_plan(sources)

    return Digest(
        schema_version=SCHEMA_VERSION,
        sections=sections,
        plan=plan,
        origin={"gathered_at": sources.gathered_at},
    )
