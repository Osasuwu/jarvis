"""Tests for sandcastle pick admission (#1691).

Covers agents/sandcastle_admission.py: the two-query pick construction
(AC1/AC2/AC3 — a afk:2-plan issue lacking plan:locked is unpickable by
construction, never blocks/waits), the needs-plan servicing drain wires
into plan_review_drain's existing synchronous planner path (AC4), the
single-writer discipline over plan:locked/needs-plan (AC5), lock release on
park/staleness/replan (AC6), and pick-time lock verification incl. age
(AC7/AC8).
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from agents.plan_review_config import (
    Class2Thresholds,
    Class3Criteria,
    ExemptCriteria,
    ModelFloors,
    PlanReviewConfig,
)
from agents.plan_review_drain import PlanResult
from agents.sandcastle_admission import (
    build_pick_queries,
    classify_lock_release,
    is_pickable,
    pick_pass_outcome,
    release_lock,
    service_lock_releases,
    service_needs_plan,
    verify_pick_time,
)

_CFG = PlanReviewConfig(
    class_2=Class2Thresholds(
        shared_surface_globs=("mcp-memory/*", ".mcp.json"),
        churn_threshold=400,
        min_prod_areas=2,
    ),
    exempt=ExemptCriteria(mechanical_criteria=("docs-only", "typo-fix")),
    class_3=Class3Criteria(mechanical_criteria=("admin-rights-required",)),
    models=ModelFloors(planner="claude-opus-5", critic="claude-sonnet-5"),
    lock_max_age_days=14,
)


class _FakeGitHub:
    def __init__(self, issues: dict[int, dict] | None = None) -> None:
        self._issues = issues or {}
        self.comments: list[tuple[int, str]] = []
        self.added_labels: list[tuple[int, str]] = []
        self.removed_labels: list[tuple[int, str]] = []

    def get_issue(self, issue_number: int):
        return self._issues.get(issue_number)

    def update_issue(self, issue_number: int, *, body: str):
        issue = dict(self._issues.get(issue_number) or {})
        issue["body"] = body
        self._issues[issue_number] = issue
        return issue

    def create_issue_comment(self, issue_number: int, *, body: str):
        self.comments.append((issue_number, body))
        return {"body": body}

    def add_label(self, issue_number: int, label: str) -> None:
        self.added_labels.append((issue_number, label))

    def remove_label(self, issue_number: int, label: str) -> None:
        self.removed_labels.append((issue_number, label))


def _plan_body(steps: tuple[str, ...]) -> str:
    steps_text = "\n".join(f"- {s}" for s in steps)
    digest = hashlib.sha256(steps_text.encode("utf-8")).hexdigest()
    return f"## Plan\n{steps_text}\nlock: {digest}\n"


# ── AC1/AC2: two-query pick construction ────────────────────────────────────


class TestBuildPickQueries:
    def test_returns_two_distinct_queries_for_repo(self):
        query_a, query_b = build_pick_queries("Osasuwu/jarvis")
        assert query_a != query_b
        for q in (query_a, query_b):
            assert "repo:Osasuwu/jarvis" in q
            assert "is:open" in q
            assert "label:sandcastle" in q
            assert "-label:status:owner-queue" in q

    def test_query_a_excludes_class_2(self):
        query_a, _ = build_pick_queries("Osasuwu/jarvis")
        assert "-label:afk:2-plan" in query_a

    def test_query_b_requires_class_2_and_plan_locked(self):
        _, query_b = build_pick_queries("Osasuwu/jarvis")
        assert "label:afk:2-plan" in query_b
        assert "label:plan:locked" in query_b


class TestIsPickable:
    def test_non_class_2_sandcastle_issue_is_pickable(self):
        assert is_pickable({"sandcastle"}) is True

    def test_class_2_without_lock_is_not_pickable(self):
        assert is_pickable({"sandcastle", "afk:2-plan"}) is False

    def test_class_2_with_lock_is_pickable(self):
        assert is_pickable({"sandcastle", "afk:2-plan", "plan:locked"}) is True

    def test_owner_queue_is_never_pickable_regardless_of_class(self):
        assert is_pickable({"sandcastle", "status:owner-queue"}) is False
        assert is_pickable({"sandcastle", "afk:2-plan", "plan:locked", "status:owner-queue"}) is False

    def test_missing_sandcastle_label_is_not_pickable(self):
        assert is_pickable({"afk:2-plan", "plan:locked"}) is False


class TestPickPassOutcome:
    def test_pickable_issue_yields_pick(self):
        assert pick_pass_outcome({"sandcastle"}) == "pick"
        assert pick_pass_outcome({"sandcastle", "afk:2-plan", "plan:locked"}) == "pick"

    def test_unlocked_class_2_yields_needs_plan_not_a_block(self):
        """AC3: an unlocked afk:2-plan candidate hit during a pick pass is
        flagged and skipped — never blocks or waits on the plan."""
        assert pick_pass_outcome({"sandcastle", "afk:2-plan"}) == "needs_plan"

    def test_already_flagged_unlocked_class_2_is_skipped_not_reflagged(self):
        assert pick_pass_outcome({"sandcastle", "afk:2-plan", "needs-plan"}) == "skip"

    def test_non_sandcastle_issue_is_skipped(self):
        assert pick_pass_outcome({"afk:2-plan"}) == "skip"

    def test_owner_queue_parked_issue_is_skipped(self):
        assert pick_pass_outcome({"sandcastle", "status:owner-queue"}) == "skip"


# ── AC4: drain services needs-plan issues via the shared planner path ──────


class TestServiceNeedsPlan:
    class _FakePlanner:
        def __init__(self, result: PlanResult) -> None:
            self._result = result
            self.calls: list[dict] = []

        def run_planner(self, row, config):
            self.calls.append(row)
            return self._result

    def test_resolved_plan_swaps_needs_plan_for_plan_locked(self):
        github = _FakeGitHub({42: {"body": "## Acceptance Criteria\n- AC one\n"}})
        plan_text = "- Step one\nlock: " + hashlib.sha256(b"- Step one").hexdigest() + "\n"
        planner = self._FakePlanner(PlanResult(plan_text=plan_text, resolved=True))
        candidates = [
            {
                "number": 42,
                "title": "Some issue",
                "body": "## Acceptance Criteria\n- AC one\n",
                "labels": [{"name": "sandcastle"}, {"name": "afk:2-plan"}, {"name": "needs-plan"}],
            }
        ]

        serviced = service_needs_plan(github, _CFG, planner, candidates)

        assert serviced == [42]
        assert (42, "needs-plan") in github.removed_labels
        assert (42, "plan:locked") in github.added_labels
        assert "## Plan" in github._issues[42]["body"]

    def test_unresolved_plan_leaves_needs_plan_in_place(self):
        github = _FakeGitHub({42: {"body": "## Acceptance Criteria\n- AC one\n"}})
        planner = self._FakePlanner(PlanResult(plan_text="", resolved=False, reason="stuck"))
        candidates = [
            {
                "number": 42,
                "title": "Some issue",
                "body": "## Acceptance Criteria\n- AC one\n",
                "labels": [{"name": "sandcastle"}, {"name": "afk:2-plan"}, {"name": "needs-plan"}],
            }
        ]

        serviced = service_needs_plan(github, _CFG, planner, candidates)

        assert serviced == []
        assert github.removed_labels == []
        assert github.added_labels == []

    def test_candidates_without_needs_plan_label_are_ignored(self):
        github = _FakeGitHub()
        planner = self._FakePlanner(PlanResult(plan_text="x", resolved=True))
        candidates = [{"number": 7, "title": "t", "body": "b", "labels": [{"name": "sandcastle"}]}]

        serviced = service_needs_plan(github, _CFG, planner, candidates)

        assert serviced == []
        assert planner.calls == []


# ── AC5: single-writer discipline over plan:locked / needs-plan ────────────


class TestSingleWriterDiscipline:
    """Only service_needs_plan / release_lock may call add_label/remove_label
    for the plan:locked / needs-plan pair — no other module writes these
    labels directly (AC5)."""

    def test_only_sandcastle_admission_writes_the_lifecycle_labels(self):
        # github_client.py defines add_label/remove_label (the interface,
        # not a call site) — excluded alongside the one module allowed to
        # call them.
        _EXCLUDED = {"sandcastle_admission.py", "github_client.py"}
        repo_root = Path(__file__).resolve().parents[2]
        agents_dir = repo_root / "agents"
        call_re = re.compile(r"\.(add_label|remove_label)\(")

        offenders = []
        for path in agents_dir.rglob("*.py"):
            if path.name in _EXCLUDED:
                continue
            text = path.read_text(encoding="utf-8")
            if call_re.search(text):
                offenders.append(str(path.relative_to(repo_root)))

        assert offenders == []

    def test_writer_calls_are_confined_to_the_two_named_functions(self):
        repo_root = Path(__file__).resolve().parents[2]
        module_path = repo_root / "agents" / "sandcastle_admission.py"
        source = module_path.read_text(encoding="utf-8")

        allowed_functions = {"service_needs_plan", "release_lock"}
        current_function = None
        for line in source.splitlines():
            def_match = re.match(r"def (\w+)\(", line)
            if def_match:
                current_function = def_match.group(1)
            if re.search(r"\b(add_label|remove_label)\(", line):
                assert current_function in allowed_functions, (
                    f"unexpected label write outside {allowed_functions}: "
                    f"found in {current_function!r}"
                )


# ── AC6: plan:locked removed on park / staleness / replan ──────────────────


class TestReleaseLock:
    def test_removes_plan_locked_label(self):
        github = _FakeGitHub()
        release_lock(github, 42, reason="parked")
        assert github.removed_labels == [(42, "plan:locked")]

    @pytest.mark.parametrize("reason", ["parked", "stale", "replanned"])
    def test_accepts_any_of_the_three_release_reasons(self, reason):
        github = _FakeGitHub()
        release_lock(github, 1, reason=reason)
        assert github.removed_labels == [(1, "plan:locked")]


class TestClassifyLockRelease:
    """Pure classification of *why* a locked issue's label should come off —
    mirrors pick_pass_outcome's shape (AC6)."""

    def test_not_locked_is_none(self):
        assert classify_lock_release({"sandcastle", "afk:2-plan"}, True, "ok") is None

    def test_owner_queue_parks_regardless_of_pick_verdict(self):
        assert classify_lock_release({"plan:locked", "status:owner-queue"}, True, "ok") == "parked"

    def test_age_refusal_is_stale(self):
        labels = {"plan:locked"}
        assert (
            classify_lock_release(labels, False, "lock age 20.0d exceeds max_age_days=14")
            == "stale"
        )

    def test_digest_or_malformed_refusal_is_replanned(self):
        labels = {"plan:locked"}
        assert (
            classify_lock_release(
                labels, False, "lock digest does not match the current plan steps"
            )
            == "replanned"
        )
        assert (
            classify_lock_release(labels, False, "malformed plan: absent_lock_line") == "replanned"
        )

    def test_locked_and_verified_ok_is_none(self):
        assert classify_lock_release({"plan:locked"}, True, "ok") is None


class TestServiceLockReleases:
    def test_owner_queue_labeled_locked_issue_is_released_as_parked(self):
        github = _FakeGitHub()
        body = _plan_body(("Step one",))
        candidates = [
            {
                "number": 9,
                "body": body,
                "labels": [{"name": "plan:locked"}, {"name": "status:owner-queue"}],
            }
        ]
        now = datetime(2026, 8, 25, tzinfo=timezone.utc)

        released = service_lock_releases(github, _CFG, candidates, now)

        assert released == [(9, "parked")]
        assert github.removed_labels == [(9, "plan:locked")]

    def test_stale_lock_is_released_as_stale(self):
        github = _FakeGitHub()
        body = _plan_body(("Step one",))
        now = datetime(2026, 8, 25, tzinfo=timezone.utc)
        locked_at = now - timedelta(days=20)
        candidates = [
            {
                "number": 10,
                "body": body,
                "labels": [{"name": "plan:locked"}],
                "plan_locked_at": locked_at,
            }
        ]

        released = service_lock_releases(github, _CFG, candidates, now)

        assert released == [(10, "stale")]

    def test_edited_body_after_lock_is_released_as_replanned(self):
        github = _FakeGitHub()
        now = datetime(2026, 8, 25, tzinfo=timezone.utc)
        candidates = [
            {
                "number": 11,
                "body": "## Plan\n- Step one\nlock: deadbeef\n",
                "labels": [{"name": "plan:locked"}],
            }
        ]

        released = service_lock_releases(github, _CFG, candidates, now)

        assert released == [(11, "replanned")]

    def test_valid_fresh_lock_is_left_alone(self):
        github = _FakeGitHub()
        body = _plan_body(("Step one",))
        now = datetime(2026, 8, 25, tzinfo=timezone.utc)
        candidates = [
            {
                "number": 12,
                "body": body,
                "labels": [{"name": "plan:locked"}],
                "plan_locked_at": now - timedelta(days=1),
            }
        ]

        released = service_lock_releases(github, _CFG, candidates, now)

        assert released == []
        assert github.removed_labels == []

    def test_candidates_without_plan_locked_are_ignored(self):
        github = _FakeGitHub()
        now = datetime(2026, 8, 25, tzinfo=timezone.utc)
        candidates = [{"number": 13, "body": "no plan here", "labels": [{"name": "sandcastle"}]}]

        released = service_lock_releases(github, _CFG, candidates, now)

        assert released == []
        assert github.removed_labels == []


# ── AC7/AC8: pick-time lock verification (digest + age) ────────────────────


class TestVerifyPickTime:
    def test_valid_fresh_lock_is_ok(self):
        body = _plan_body(("Step one",))
        now = datetime(2026, 8, 25, tzinfo=timezone.utc)
        locked_at = now - timedelta(days=1)
        ok, _reason = verify_pick_time(body, locked_at, max_age_days=14, now=now)
        assert ok is True

    def test_digest_mismatch_refuses(self):
        now = datetime(2026, 8, 25, tzinfo=timezone.utc)
        ok, reason = verify_pick_time(
            "## Plan\n- Step one\nlock: deadbeef\n", now, max_age_days=14, now=now
        )
        assert ok is False
        assert "lock" in reason.lower()

    def test_malformed_plan_refuses(self):
        now = datetime(2026, 8, 25, tzinfo=timezone.utc)
        ok, reason = verify_pick_time("no plan heading here", now, max_age_days=14, now=now)
        assert ok is False

    def test_lock_older_than_threshold_refuses(self):
        body = _plan_body(("Step one",))
        now = datetime(2026, 8, 25, tzinfo=timezone.utc)
        locked_at = now - timedelta(days=15)
        ok, reason = verify_pick_time(body, locked_at, max_age_days=14, now=now)
        assert ok is False
        assert "age" in reason.lower()

    def test_lock_exactly_at_threshold_is_still_ok(self):
        body = _plan_body(("Step one",))
        now = datetime(2026, 8, 25, tzinfo=timezone.utc)
        locked_at = now - timedelta(days=14)
        ok, _reason = verify_pick_time(body, locked_at, max_age_days=14, now=now)
        assert ok is True

    def test_no_locked_at_skips_age_check(self):
        """A caller that cannot resolve locked_at (e.g. label-timeline lookup
        failed) still gets a digest-only verdict rather than a hard refuse —
        age-checking degrades gracefully, it is not itself a hard dependency."""
        body = _plan_body(("Step one",))
        now = datetime(2026, 8, 25, tzinfo=timezone.utc)
        ok, _reason = verify_pick_time(body, None, max_age_days=14, now=now)
        assert ok is True
