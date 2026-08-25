"""Sandcastle pick admission (#1691).

Pick eligibility is exactly two mechanical label queries — never a class-2
issue waiting on a plan (:func:`build_pick_queries`, :func:`is_pickable`).
:func:`build_pick_queries`'s two queries are wired live into
``.sandcastle/prompt.md``'s pick step. :func:`verify_pick_time` is likewise
wired: ``scripts/sandcastle_pick_verify.py`` wraps it, and
``.sandcastle/prompt.md``'s Claim step invokes that script and branches on
its exit code before honoring a ``plan:locked`` label — digest (via
:mod:`agents.plan_lock`) plus a config-held age ceiling (AC7/AC8).

The rest of this module — :func:`pick_pass_outcome` (AC3, flag an unlocked
class-2 candidate ``needs-plan`` and skip, never block),
:func:`service_needs_plan` (AC4, service ``needs-plan`` via the same
synchronous planner path :mod:`agents.plan_review_drain` already built for
the queue lane, #1689), and :func:`release_lock` /
:func:`classify_lock_release` / :func:`service_lock_releases` (AC6, release
``plan:locked`` on park/staleness/replan) — is implemented and unit-tested
but has **no production caller yet**; nothing periodically invokes it. That
wiring (a new isolated step in :mod:`agents.wake_driver`'s ``tick()``, plus
a candidate-fetch mechanism) is tracked in #1702. Only
:func:`service_needs_plan` and :func:`release_lock` are permitted to write
``plan:locked``/``needs-plan`` once wired — single-writer discipline (AC5).

The container never merges — that boundary is untouched by this module
(AC9); the ex-post CI diff-gate and review gate stand as the safety net.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from agents.github_client import GitHubClient
from agents.plan_lock import MalformedPlanError, parse_plan
from agents.plan_lock import hash_plan as _hash_plan
from agents.plan_review_config import PlanReviewConfig
from agents.plan_review_drain import PlannerPort, write_plan_section

_SANDCASTLE = "sandcastle"
_CLASS_2 = "class:2"
_PLAN_LOCKED = "plan:locked"
_NEEDS_PLAN = "needs-plan"
_OWNER_QUEUE = "status:owner-queue"


def build_pick_queries(repo: str) -> tuple[str, str]:
    """GitHub search queries for the two-query pick construction (AC1/AC2).

    Query A: sandcastle issues that are not class:2 (no plan needed).
    Query B: sandcastle class:2 issues that are already plan:locked.
    Both exclude status:owner-queue. Union of A and B is exactly the
    pickable set — an unlocked class:2 issue satisfies neither query, so
    it is unpickable by construction, not by a runtime check.
    """
    common = f"repo:{repo} is:open label:{_SANDCASTLE} -label:{_OWNER_QUEUE}"
    query_a = f"{common} -label:{_CLASS_2}"
    query_b = f"{common} label:{_CLASS_2} label:{_PLAN_LOCKED}"
    return query_a, query_b


def is_pickable(label_names: set[str]) -> bool:
    """Pure re-implementation of the two-query union, for a single issue's labels."""
    if _SANDCASTLE not in label_names or _OWNER_QUEUE in label_names:
        return False
    if _CLASS_2 not in label_names:
        return True
    return _PLAN_LOCKED in label_names


def pick_pass_outcome(label_names: set[str]) -> str:
    """Classify one issue's labels during a pick pass.

    Returns "pick" (eligible now), "needs_plan" (unlocked class:2, flag
    and move on — AC3, never a block/wait), or "skip" (not sandcastle,
    owner-queue parked, or already flagged and awaiting drain).
    """
    if is_pickable(label_names):
        return "pick"
    if _SANDCASTLE not in label_names or _OWNER_QUEUE in label_names:
        return "skip"
    if _CLASS_2 in label_names and _NEEDS_PLAN not in label_names:
        return "needs_plan"
    return "skip"


def service_needs_plan(
    github: GitHubClient,
    config: PlanReviewConfig,
    planner: PlannerPort,
    candidates: list[dict[str, Any]],
) -> list[int]:
    """Service ``needs-plan``-flagged candidates via the shared planner path (AC4).

    Reuses :func:`agents.plan_review_drain.write_plan_section` — the same
    synchronous planner path #1689 built for the queue lane — so a plan
    written here and a plan written by the queue drain look identical on
    the issue. On a resolved plan: writes the ``## Plan`` section, swaps
    ``needs-plan`` for ``plan:locked`` (AC5's only other writer besides
    :func:`release_lock`). An unresolved plan leaves ``needs-plan`` in
    place — untouched, to be retried on a later drain tick.

    Returns the issue numbers actually serviced (resolved plan written).
    """
    serviced: list[int] = []
    for candidate in candidates:
        label_names = {label["name"] for label in candidate.get("labels", [])}
        if _NEEDS_PLAN not in label_names:
            continue

        issue_number = int(candidate["number"])
        row = {
            "issue_number": issue_number,
            "issue_title": candidate.get("title", ""),
            "issue_body": candidate.get("body", ""),
        }
        result = planner.run_planner(row, config)
        if not result.resolved:
            continue

        write_plan_section(github, issue_number, result.plan_text)
        github.remove_label(issue_number, _NEEDS_PLAN)
        github.add_label(issue_number, _PLAN_LOCKED)
        serviced.append(issue_number)

    return serviced


def release_lock(github: GitHubClient, issue_number: int, reason: str) -> None:
    """Remove ``plan:locked`` from an issue (AC6: park / staleness / replan).

    ``reason`` is accepted for caller-side logging/observability only — the
    removal itself is identical regardless of which of the three triggers
    fired.
    """
    github.remove_label(issue_number, _PLAN_LOCKED)


def classify_lock_release(label_names: set[str], pick_ok: bool, pick_reason: str) -> str | None:
    """Pure classification of *why* a locked issue's label should come off (AC6).

    Owner-queue parking takes priority over the pick-time verdict — a
    principal pulling an issue into owner-queue while it's locked always
    parks it, regardless of whether the lock itself still verifies.
    Otherwise, a failed :func:`verify_pick_time` re-check is "stale" when
    the failure reason names an age violation, else "replanned" (digest
    mismatch or malformed plan — the body changed under the lock).
    Returns ``None`` when no release is warranted.
    """
    if _PLAN_LOCKED not in label_names:
        return None
    if _OWNER_QUEUE in label_names:
        return "parked"
    if not pick_ok:
        return "stale" if "age" in pick_reason.lower() else "replanned"
    return None


def service_lock_releases(
    github: GitHubClient,
    config: PlanReviewConfig,
    candidates: list[dict[str, Any]],
    now: datetime,
) -> list[tuple[int, str]]:
    """Sweep ``plan:locked`` candidates and release any that no longer hold (AC6).

    Reuses :func:`verify_pick_time` (AC7/AC8) for the digest/age re-check
    and delegates the actual write to :func:`release_lock` — this function
    never calls ``add_label``/``remove_label`` directly, preserving AC5's
    single-writer discipline without widening the meta-test's allow-list.
    """
    released: list[tuple[int, str]] = []
    for candidate in candidates:
        label_names = {label["name"] for label in candidate.get("labels", [])}
        if _PLAN_LOCKED not in label_names:
            continue

        body = candidate.get("body", "")
        locked_at = candidate.get("plan_locked_at")
        pick_ok, pick_reason = verify_pick_time(body, locked_at, config.lock_max_age_days, now)

        reason = classify_lock_release(label_names, pick_ok, pick_reason)
        if reason is None:
            continue

        issue_number = int(candidate["number"])
        release_lock(github, issue_number, reason=reason)
        released.append((issue_number, reason))

    return released


def verify_pick_time(
    body: str,
    locked_at: datetime | None,
    max_age_days: int,
    now: datetime,
) -> tuple[bool, str]:
    """Pick-time re-check of a ``plan:locked`` issue (AC7/AC8).

    Fail-closed on a digest mismatch or a malformed plan section — a
    ``plan:locked`` label alone is never trusted; the lock is recomputed
    from the current body every time. Age is checked only when
    ``locked_at`` is known — a caller unable to resolve it (e.g. a failed
    label-timeline lookup) still gets a digest-only verdict rather than a
    hard refuse (age-checking degrades gracefully; it is not itself a hard
    dependency). The age boundary is inclusive: exactly ``max_age_days``
    old is still ok.
    """
    try:
        parsed = parse_plan(body)
    except MalformedPlanError as exc:
        return False, f"malformed plan: {exc}"

    steps_text = "\n".join(f"- {step}" for step in parsed.steps)
    if _hash_plan(steps_text) != parsed.lock:
        return False, "lock digest does not match the current plan steps"

    if locked_at is not None:
        age_days = (now - locked_at).total_seconds() / 86400
        if age_days > max_age_days:
            return False, f"lock age {age_days:.1f}d exceeds max_age_days={max_age_days}"

    return True, "ok"
