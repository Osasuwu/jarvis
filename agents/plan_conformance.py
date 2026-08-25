"""Plan-conformance check + rework-round metric for /verify (#1692).

**Conformance half (AC1/AC2/AC3).** A class-2 PR is expected to carry two
body sections the executor fills in: ``## Plan-conformance`` (what shipped
against the plan) and ``## Plan-divergences`` (where it diverged and why,
distinct from ``## Deliberate divergences`` — that heading, used by
``task-implement``/``verify``'s Step 2b divergence audit, flags a subagent
reshaping an AC's literal signature; this one is class-2-specific and
answers "did the shipped PR follow its reviewed plan"). Missing either
section on a class-2 PR is itself a finding (AC2) — :func:`missing_sections`
returns which ones. Declared divergences are surfaced with their stated
reason via :func:`extract_divergences`, not merely counted (AC3) — an
undeclared divergence is the defect, not a divergence by itself.

# ceiling: no PR-template addendum yet instructs a class-2 executor to
# actually write ``## Plan-conformance``/``## Plan-divergences`` —
# missing_sections will fire on effectively every class-2 PR until
# implement/SKILL.md's PR-body template gets a class-2-specific addendum
# (follow-up issue), and extract_divergences will stay empty in practice
# until then.

**Metric half (AC4/AC5/AC6/AC7).** The plan-review stage was justified by a
rework-cost argument, so its success metric is a rework-round delta, not a
gut check.

- *Rework round* (AC4): one attempt of ``scripts/rework_policy.py``'s
  existing ``/rework`` loop — the same counter that already drives that
  module's CONTINUE/CONVERGED/STUCK_* decision. :func:`rework_round_count`
  is deliberately ``len(history)``: no new counter, no new ledger. A class-2
  PR that never entered the ``/rework`` loop (clean first review) has 0
  rework rounds.
- *PR set* (AC4): class-2 PRs only (decision ``3bb07f67-f815-4459-9023-
  dc652678c9fa``) — the set the plan-review stage actually gates.
- *Baseline* (AC5): the retro-classification of PR #963 by #1683 — 3 of 34
  review findings were plan-level (memory
  ``d20e20b4-a769-4335-bef6-0a34070488e1``), i.e.
  :data:`REWORK_BASELINE_PLAN_LEVEL_FRACTION`. #1683's own conclusion:
  a plan-review stage on a PR shaped like #963 would plausibly shave 1-2
  rework rounds off a 5-round PR, not eliminate the bulk of the churn — so
  the checkpoint compares *average rework rounds per class-2 PR*
  post-stage against that PR's realized round count (5), not a naive
  zero-tolerance target.
- *Checkpoint* (AC6): :func:`checkpoint_reached` fires at
  :data:`CHECKPOINT_THRESHOLD` (~10) class-2 PRs shipped under the stage.
  The decision it feeds is exactly one of :data:`CHECKPOINT_DECISIONS`,
  stated in advance so the checkpoint can't be argued into a fourth option
  after the fact:
    - ``"retune"`` — average rework rounds improved but not decisively;
      adjust `class:2` thresholds (config/plan_review.yaml) and re-run the
      window.
    - ``"keep"`` — average rework rounds materially below the #963
      baseline; stage stays as-is.
    - ``"rollback"`` — no measurable improvement, or rework rounds are flat
      /worse; execute :data:`ROLLBACK_STEPS`.
- *Rollback* (AC7): :data:`ROLLBACK_STEPS` is the concrete, ordered
  teardown — labels, gates, config entries — not a paragraph.
"""

from __future__ import annotations

from dataclasses import dataclass

from agents.plan_lock import NEXT_HEADING_RE

_PLAN_CONFORMANCE_HEADING = "## Plan-conformance"
_PLAN_DIVERGENCES_HEADING = "## Plan-divergences"

_REQUIRED_CLASS_2_SECTIONS = ("Plan-conformance", "Plan-divergences")

# #1683's retro-classification of PR #963 (memory d20e20b4-a769-4335-bef6-
# 0a34070488e1): 3 of 34 review-comment findings were plan-level.
# ceiling: n=1 heuristic — derived from a single historical PR, not a
# distribution. Holds as ground truth until the #1692 AC6 checkpoint
# (~10 class-2 PRs, see checkpoint_reached below) recomputes it from the
# real post-stage sample; treat it as provisional until then.
REWORK_BASELINE_PLAN_LEVEL_FRACTION = 3 / 34

CHECKPOINT_THRESHOLD = 10
CHECKPOINT_DECISIONS = ("retune", "keep", "rollback")

ROLLBACK_STEPS = (
    "Set class_2.churn_threshold and class_2.min_prod_areas in "
    "config/plan_review.yaml high enough that classify_task_row never "
    "returns class:2 in practice (functional disable, no code deleted).",
    "Remove the plan-review-diff-gate.yml required-check entry from "
    "branch protection on main, so a stale class:2 verdict can't block "
    "merges while the stage winds down.",
    "Stop applying needs-plan/plan:locked in agents/sandcastle_admission.py "
    "and agents/plan_review_drain.py's pick/drain paths (feature-flag via "
    "PlanReviewConfig, not a delete — keeps the two-writer discipline "
    "intact if the stage is later re-enabled).",
    "Leave scripts/rework_policy.py, the /rework loop, and the CI diff-gate "
    "workflow file in place untouched — they are the pre-existing safety "
    "net this stage was layered on top of, not part of the stage itself.",
    "File a milestone-closing issue recording the checkpoint's measured "
    "rework-round delta and the rollback decision, citing the checkpoint's "
    "outcome data — so the next attempt at a plan-review stage starts from "
    "evidence instead of repeating the same argument from #1573.",
)


@dataclass(frozen=True)
class Divergence:
    what: str
    reason: str


def missing_sections(pr_body: str, is_class_2: bool) -> list[str]:
    """Which of the two required class-2 body sections are absent (AC1/AC2).

    Returns an empty list for a non-class-2 PR unconditionally — the check
    only applies where a plan was required in the first place.
    """
    if not is_class_2:
        return []
    return [name for name in _REQUIRED_CLASS_2_SECTIONS if f"## {name}" not in pr_body]


def extract_divergences(pr_body: str) -> list[Divergence]:
    """Parse ``## Plan-divergences`` bullets into (what, reason) pairs (AC3).

    A bullet is split on the first " — " (em dash, the same separator
    ``## Deliberate divergences`` already uses) into what/reason; a bullet
    with no em dash is kept whole with an empty reason rather than dropped,
    since an author who forgot the separator still declared *something*.
    A body with no ``## Plan-divergences`` heading, or a section reading
    "None." with no bullets, both correctly yield no divergences.
    """
    start = pr_body.find(_PLAN_DIVERGENCES_HEADING)
    if start == -1:
        return []
    start += len(_PLAN_DIVERGENCES_HEADING)

    next_heading_match = NEXT_HEADING_RE.search(pr_body, start)
    section = pr_body[start:] if next_heading_match is None else pr_body[start:next_heading_match.start()]

    divergences: list[Divergence] = []
    for line in section.splitlines():
        line = line.strip()
        if not line.startswith("- "):
            continue
        bullet = line[2:].strip()
        if " — " in bullet:
            what, reason = bullet.split(" — ", 1)
            divergences.append(Divergence(what=what.strip(), reason=reason.strip()))
        else:
            divergences.append(Divergence(what=bullet, reason=""))

    return divergences


def rework_round_count(history: list[dict]) -> int:
    """Rework rounds for one PR: the length of its /rework attempt history (AC4).

    Deliberately identical to what scripts/rework_policy.py's decide()
    already receives as ``history`` — no parallel counter. A PR whose first
    review had zero CRITICAL/MAJOR findings never entered the loop and has
    0 rework rounds.
    """
    return len(history)


def checkpoint_reached(class_2_pr_count: int) -> bool:
    """Whether the ~10-PR checkpoint has been reached (AC6, inclusive)."""
    return class_2_pr_count >= CHECKPOINT_THRESHOLD


__all__ = [
    "CHECKPOINT_DECISIONS",
    "CHECKPOINT_THRESHOLD",
    "REWORK_BASELINE_PLAN_LEVEL_FRACTION",
    "ROLLBACK_STEPS",
    "Divergence",
    "checkpoint_reached",
    "extract_divergences",
    "missing_sections",
    "rework_round_count",
]
