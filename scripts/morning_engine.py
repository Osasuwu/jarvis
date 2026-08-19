"""Engine for the `morning` daily-digest capability (#1586).

Pure `analyze(sources) -> Digest`: assembles digest sections from gathered
data and synthesizes a day plan, with cut_line_after computed by cumulative
sum of S/M/L-converted estimates (never "first N").

Render (#1588) and the detector-gap-journal source (#1595) are wired in; the S/M/L
budget-unit translation and the day budget below are the single explicit
place either constant is defined — real calibration is deferred to #1578.

Provenance (#1589): each section carries its own SectionProvenance; fold_provenance
is called explicitly in analyze() so no per-section stamp is ever lost silently.

Goals/milestones section and architecture-sweep reminders (#1590) are also
assembled here, alongside the pre-existing repo_hygiene/detector_gaps/learning
sections.

Escalations section (#1591) surfaces owner-task escalations that survived the
two-channel dedup-by-id filter; it renders first so the owner sees anything
that already escalated before the rest of the digest.
"""

from __future__ import annotations

from datetime import datetime, timezone

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

# ceiling: arch-sweep window and min-slices threshold are not calibrated;
# real tuning deferred to #1578. Single explicit definition.
_SWEEP_MIN_SLICES = 3
_SWEEP_WINDOW_DAYS = 7


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


def _build_escalations_section(sources: MorningGatherResult) -> Section:
    tasks_prov = sources.provenance.get(MorningSourceKind.OWNER_TASKS, {})
    ran = tasks_prov.get("ran", False)
    ok = tasks_prov.get("ok", False)

    if not ran:
        return Section(
            name="escalations",
            items=[],
            reason="источник не подключён",
            provenance=SectionProvenance(ran=False, ok=False, source="morning_gather"),
        )

    if not ok:
        return Section(
            name="escalations",
            items=[],
            reason="запрос не вернул данных",
            provenance=SectionProvenance(ran=True, ok=False, source="morning_gather"),
        )

    items = [
        {
            "id": str(t.get("id", "")),
            "goal": str(t.get("goal", "")),
            "reason": str(t.get("escalated_reason", "")),
        }
        for t in sources.owner_tasks
    ]
    return Section(
        name="escalations",
        items=items,
        reason=None,
        provenance=SectionProvenance(ran=True, ok=True, source="morning_gather"),
    )


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

    ran = gaps_prov.get("ran", False)
    ok = gaps_prov.get("ok", False)
    input_rows = gaps_prov.get("input_rows", 0)
    # No production GapStore adapter exists yet (#1595) — when the source
    # never ran (no gap_store injected) that's a stable known limitation,
    # not a failure. Only a source that ran and came back not-ok is FAILED.
    absence_kind = None
    absence_reason = None
    if not ok:
        if not ran:
            absence_kind = AbsenceKind.NOT_CONNECTED
            absence_reason = "no GapStore adapter wired (#1595)"
        else:
            absence_kind = AbsenceKind.FAILED

    if not promotable:
        return Section(
            name="detector_gaps",
            items=[],
            reason="no repeated gaps",
            provenance=SectionProvenance(
                ran=ran,
                ok=ok,
                source="morning_gather",
                input_rows=input_rows,
                absence_kind=absence_kind,
                absence_reason=absence_reason,
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
            ran=ran,
            ok=ok,
            source="morning_gather",
            input_rows=input_rows,
            absence_kind=absence_kind,
            absence_reason=absence_reason,
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


def _repo_to_project(repo: str) -> str:
    """Extract project name from 'owner/name' -> 'name'."""
    return repo.split("/")[-1].lower()


def _detect_arch_sweep_items(
    closed_milestones: dict[str, list[dict]],
    gathered_at: str,
    window_days: int = _SWEEP_WINDOW_DAYS,
    min_slices: int = _SWEEP_MIN_SLICES,
) -> list[dict]:
    """Return arch_sweep items for recently-closed milestones with enough closed slices.

    External text (milestone titles) is treated as data — not executed.
    """
    try:
        now = datetime.fromisoformat(gathered_at.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        now = datetime.now(timezone.utc)

    items: list[dict] = []
    for repo, milestones in closed_milestones.items():
        for m in milestones:
            closed_at_str = m.get("closed_at")
            closed_issues = m.get("closed_issues", 0)
            if not closed_at_str or not isinstance(closed_issues, (int, float)):
                continue
            if int(closed_issues) < min_slices:
                continue
            try:
                closed_at = datetime.fromisoformat(closed_at_str.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                continue
            age_days = (now - closed_at).total_seconds() / 86400
            if age_days > window_days:
                continue
            items.append(
                {
                    "type": "arch_sweep",
                    "id": f"sweep:{repo}:{m.get('number', 0)}",
                    "repo": repo,
                    "number": m.get("number", 0),
                    # title is external text — stored as data, not interpreted
                    "title": str(m.get("title", "")),
                    "closed_issues": int(closed_issues),
                    "age_days": round(age_days, 1),
                }
            )

    items.sort(key=lambda x: x["age_days"])
    return items


def _build_goals_milestones_section(sources: MorningGatherResult) -> Section:
    """Build the goals-and-milestones section for the morning digest (#1590).

    Contains: goals with priority/pct, open milestones (flagging no-slice ones),
    goals without an open milestone, and architecture-sweep reminders.
    External text (titles, goal why fields) is stored as data, not executed.
    """
    prov = sources.provenance
    goals_prov = prov.get(MorningSourceKind.GOALS, {})
    ms_prov = prov.get(MorningSourceKind.GH_MILESTONES, {})

    ran = goals_prov.get("ran", False) or ms_prov.get("ran", False)
    ok = goals_prov.get("ok", False) or ms_prov.get("ok", False)

    if not ran:
        return Section(
            name="goals_and_milestones",
            items=[],
            reason="source not available",
            provenance=SectionProvenance(ran=False, ok=False, source="morning_gather"),
        )

    items: list[dict] = []

    # Projects that have at least one open milestone
    projects_with_open_milestones: set[str] = {
        _repo_to_project(repo) for repo, ms in sources.milestones.items() if ms
    }

    # Goals (flag if the goal's project has no open milestone)
    for goal in sources.goals:
        slug = str(goal.get("slug") or "")
        # title/why are external text — stored as data
        title = str(goal.get("title") or slug)
        priority = str(goal.get("priority") or "—")
        pct = goal.get("progress_pct")
        pct_val = int(pct) if isinstance(pct, (int, float)) else None
        project = str(goal.get("project") or "").lower()

        flags: list[str] = []
        if project and project != "cross-project":
            if project not in projects_with_open_milestones:
                flags.append("no_milestone")

        items.append(
            {
                "type": "goal",
                "id": f"goal:{slug}",
                "slug": slug,
                "title": title,
                "priority": priority,
                "pct": pct_val,
                "project": project,
                "flags": flags,
            }
        )

    # Open milestones (flag if no slices at all: both open_issues=0 and closed_issues=0)
    for repo, milestones in sources.milestones.items():
        for m in milestones:
            open_issues = int(m.get("open_issues") or 0)
            closed_issues = int(m.get("closed_issues") or 0)
            number = m.get("number", 0)
            flags = ["no_slices"] if open_issues == 0 and closed_issues == 0 else []
            items.append(
                {
                    "type": "open_milestone",
                    "id": f"ms:{repo}:{number}",
                    "repo": repo,
                    "number": number,
                    # title is external text — stored as data
                    "title": str(m.get("title", "")),
                    "open_issues": open_issues,
                    "closed_issues": closed_issues,
                    "flags": flags,
                }
            )

    # Architecture-sweep reminders from recently closed milestones
    sweep_items = _detect_arch_sweep_items(sources.closed_milestones, sources.gathered_at)
    items.extend(sweep_items)

    section_ok = ok or bool(sweep_items)
    return Section(
        name="goals_and_milestones",
        items=items,
        reason=None if section_ok else "sources not available",
        provenance=SectionProvenance(
            ran=ran,
            ok=section_ok,
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


def _synthesize_plan(
    sources: MorningGatherResult,
    goals_ms_section: Section | None = None,
) -> Plan:
    items: list[PlanItem] = []
    rank = 1

    # Build a slug->id map from the goals_and_milestones section so plan items
    # can cite their section counterpart (AC6 — machine attribution, not rendered)
    slug_to_section_id: dict[str, str] = {}
    if goals_ms_section is not None:
        for it in goals_ms_section.items:
            if it.get("type") == "goal":
                slug_to_section_id[str(it.get("slug", ""))] = str(it.get("id", ""))

    for goal in sources.goals:
        slug = str(goal.get("slug") or "")
        item = _plan_item_from_row(
            goal, rank, default_estimate="M", ref_prefix="goal", ref_key="slug"
        )
        if slug in slug_to_section_id:
            item = PlanItem(
                rank=item.rank,
                estimate=item.estimate,
                text=item.text,
                refs=item.refs,
                cites=[slug_to_section_id[slug]],
            )
        items.append(item)
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

    Escalations (#1591) render first in the section list so the owner sees
    anything that already escalated before the rest of the digest.
    """
    goals_ms_section = _build_goals_milestones_section(sources)
    sections = [
        _build_escalations_section(sources),
        _build_repo_hygiene_section(sources),
        _build_detector_gaps_section(sources),
        _build_learning_section(),
        goals_ms_section,
    ]
    plan = _synthesize_plan(sources, goals_ms_section=goals_ms_section)
    degradation = fold_provenance(sections)

    return Digest(
        schema_version=SCHEMA_VERSION,
        sections=sections,
        plan=plan,
        degradation=degradation,
        origin={"gathered_at": sources.gathered_at},
    )
