"""Tests for status_engine pure-function module (#1013).

Verifies four deterministic detectors, ranking, provenance contract, and
the contradiction-detector prefilter. Follows the fixture pattern from
test_rework_policy.py: in-memory fixtures, no I/O.
"""

from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone

from status_engine import (
    DECISION_PREFILTER_DAYS,
    FRESHNESS_AGE_SECONDS,
    MEMORY_GIT_CONTRADICTION,
    STALE_INPROGRESS_DAYS,
    TOP_N_CAP,
    Baseline,
    ContradictionVerdict,
    DecisionInfo,
    Delta,
    DetectorHit,
    Digest,
    HealthVerdict,
    IssueInfo,
    Provenance,
    RepoState,
    analyze,
    build_contradiction_prefilter,
    compute_health_verdict,
    deserialize_contradiction_cache,
    detect_blocker_cascade,
    detect_decision_without_followthrough,
    detect_priority_inversion,
    detect_stale_in_progress,
    fold_contradiction_verdicts,
    rank_detector_hits,
    serialize_contradiction_cache,
)

# ============================================================================
# Fixture helpers
# ============================================================================


def _days_ago(days: float) -> str:
    """Return ISO 8601 string for `days` ago in UTC."""
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def make_issue(
    number: int,
    title: str = "",
    state: str = "open",
    labels: list[str] | None = None,
    updated_days_ago: float = 0,
    is_blocked: bool = False,
    blocks: list[int] | None = None,
) -> IssueInfo:
    """Helper to construct an IssueInfo fixture."""
    return IssueInfo(
        number=number,
        title=title or f"Issue #{number}",
        state=state,
        labels=labels or [],
        updated_at=_days_ago(updated_days_ago),
        is_blocked=is_blocked,
        blocks=blocks or [],
    )


def make_state(
    repo: str,
    issues: list[IssueInfo] | None = None,
    provenance: Provenance | None = None,
) -> RepoState:
    """Helper to construct a RepoState fixture."""
    return RepoState(
        repo=repo,
        open_issues=issues or [],
        provenance=provenance or Provenance(ran=True, ok=True, age=0),
    )


def make_baseline(
    repos: dict[str, RepoState] | None = None,
    provenance: dict[str, Provenance] | None = None,
) -> Baseline:
    """Helper to construct a Baseline fixture."""
    return Baseline(
        repos=repos or {},
        provenance=provenance or {},
    )


def make_delta(
    repos: dict[str, RepoState] | None = None,
) -> Delta:
    """Helper to construct a Delta fixture."""
    return Delta(repos=repos or {})


def make_decision(
    decision_id: str = "dec-1",
    decision: str = "",
    created_days_ago: float = 0,
) -> DecisionInfo:
    """Helper to construct a DecisionInfo fixture."""
    return DecisionInfo(
        decision_id=decision_id,
        decision=decision,
        created_at=_days_ago(created_days_ago),
    )


_NOW = datetime.now(timezone.utc)


# ============================================================================
# AC: Pure function — module-level smoke
# ============================================================================


class TestPureFunctionContract:
    """analyze() is a pure function — no I/O, deterministic with same inputs."""

    def test_analyze_returns_digest(self):
        """analyze with empty inputs returns a green Digest."""
        baseline = make_baseline()
        delta = make_delta()
        result = analyze(baseline, delta, [])
        assert isinstance(result, Digest)
        assert isinstance(result.health, HealthVerdict)
        assert isinstance(result.detector_hits, list)
        assert isinstance(result.ranking, list)
        assert isinstance(result.provenance, dict)

    def test_digest_has_required_fields(self):
        """Digest carries health, detector_hits, ranking, provenance."""
        result = analyze(make_baseline(), make_delta(), [])
        assert hasattr(result, "health")
        assert hasattr(result, "detector_hits")
        assert hasattr(result, "ranking")
        assert hasattr(result, "provenance")


# ============================================================================
# AC: Stale-in-progress detector
# ============================================================================


class TestStaleInProgressDetector:
    """stale-in-progress: issues with status:in-progress past threshold."""

    def test_stale_issue_detected(self):
        """AC: issue in-progress >3 days without update → hit."""
        baseline = make_baseline(
            {
                "jarvis": make_state(
                    "jarvis",
                    issues=[
                        make_issue(
                            1,
                            labels=["status:in-progress"],
                            updated_days_ago=STALE_INPROGRESS_DAYS + 1,
                        ),
                    ],
                ),
            }
        )
        hits = detect_stale_in_progress(baseline, make_delta(), [])
        assert len(hits) == 1
        assert hits[0].detector == "stale-in-progress"
        assert hits[0].issue_number == 1
        assert hits[0].severity == "major"

    def test_recent_in_progress_not_stale(self):
        """AC: in-progress issue updated today → no hit."""
        baseline = make_baseline(
            {
                "jarvis": make_state(
                    "jarvis",
                    issues=[
                        make_issue(1, labels=["status:in-progress"], updated_days_ago=0.1),
                    ],
                ),
            }
        )
        hits = detect_stale_in_progress(baseline, make_delta(), [])
        assert len(hits) == 0

    def test_no_label_not_stale(self):
        """Issue without status:in-progress label → no hit regardless of age."""
        baseline = make_baseline(
            {
                "jarvis": make_state(
                    "jarvis",
                    issues=[
                        make_issue(1, labels=["bug"], updated_days_ago=10),
                    ],
                ),
            }
        )
        hits = detect_stale_in_progress(baseline, make_delta(), [])
        assert len(hits) == 0

    def test_delta_overrides_baseline(self):
        """Delta repo state takes priority over baseline."""
        baseline = make_baseline(
            {
                "jarvis": make_state(
                    "jarvis",
                    issues=[
                        make_issue(
                            1, labels=["status:in-progress"], updated_days_ago=10
                        ),  # stale in baseline
                    ],
                ),
            }
        )
        delta = make_delta(
            {
                "jarvis": make_state(
                    "jarvis",
                    issues=[
                        make_issue(
                            1, labels=["status:in-progress"], updated_days_ago=0.1
                        ),  # fresh in delta
                    ],
                ),
            }
        )
        hits = detect_stale_in_progress(baseline, delta, [])
        assert len(hits) == 0

    def test_boundary_below_threshold_not_stale(self):
        """Edge: just below STALE_INPROGRESS_DAYS → not stale (> not >=)."""
        baseline = make_baseline(
            {
                "jarvis": make_state(
                    "jarvis",
                    issues=[
                        make_issue(
                            1,
                            labels=["status:in-progress"],
                            updated_days_ago=STALE_INPROGRESS_DAYS - 0.01,
                        ),
                    ],
                ),
            }
        )
        hits = detect_stale_in_progress(baseline, make_delta(), [])
        assert len(hits) == 0


# ============================================================================
# AC: Priority-inversion detector
# ============================================================================


class TestPriorityInversionDetector:
    """priority-inversion: high-priority stalled while low-priority active."""

    def test_priority_inversion_detected(self):
        """AC: P0 issue stale, P2 issue active → hit."""
        baseline = make_baseline(
            {
                "jarvis": make_state(
                    "jarvis",
                    issues=[
                        make_issue(
                            1, labels=["priority:P0"], updated_days_ago=STALE_INPROGRESS_DAYS + 2
                        ),
                        make_issue(2, labels=["priority:P2"], updated_days_ago=0.1),
                    ],
                ),
            }
        )
        hits = detect_priority_inversion(baseline, make_delta(), [])
        assert len(hits) == 1
        assert hits[0].detector == "priority-inversion"
        assert hits[0].issue_number == 1
        assert hits[0].severity == "critical"

    def test_no_inversion_when_all_active(self):
        """All priorities active → no inversion."""
        baseline = make_baseline(
            {
                "jarvis": make_state(
                    "jarvis",
                    issues=[
                        make_issue(1, labels=["priority:P0"], updated_days_ago=0.1),
                        make_issue(2, labels=["priority:P2"], updated_days_ago=0.1),
                    ],
                ),
            }
        )
        hits = detect_priority_inversion(baseline, make_delta(), [])
        assert len(hits) == 0

    def test_no_inversion_when_low_priority_inactive(self):
        """All issues stale → no inversion (no active low-pri work)."""
        baseline = make_baseline(
            {
                "jarvis": make_state(
                    "jarvis",
                    issues=[
                        make_issue(
                            1, labels=["priority:P0"], updated_days_ago=STALE_INPROGRESS_DAYS + 5
                        ),
                        make_issue(
                            2, labels=["priority:P2"], updated_days_ago=STALE_INPROGRESS_DAYS + 5
                        ),
                    ],
                ),
            }
        )
        hits = detect_priority_inversion(baseline, make_delta(), [])
        assert len(hits) == 0

    def test_no_inversion_without_priority_labels(self):
        """Issues without priority labels → no inversion hits."""
        baseline = make_baseline(
            {
                "jarvis": make_state(
                    "jarvis",
                    issues=[
                        make_issue(
                            1,
                            labels=["status:in-progress"],
                            updated_days_ago=STALE_INPROGRESS_DAYS + 2,
                        ),
                        make_issue(2, labels=["bug"], updated_days_ago=0.1),
                    ],
                ),
            }
        )
        hits = detect_priority_inversion(baseline, make_delta(), [])
        assert len(hits) == 0

    def test_priority_critical_treated_as_P0(self):
        """priority:critical label treated same as P0."""
        baseline = make_baseline(
            {
                "jarvis": make_state(
                    "jarvis",
                    issues=[
                        make_issue(
                            1,
                            labels=["priority:critical"],
                            updated_days_ago=STALE_INPROGRESS_DAYS + 2,
                        ),
                        make_issue(2, labels=["priority:P2"], updated_days_ago=0.1),
                    ],
                ),
            }
        )
        hits = detect_priority_inversion(baseline, make_delta(), [])
        assert len(hits) == 1


# ============================================================================
# AC: Decision-without-followthrough detector
# ============================================================================


class TestDecisionWithoutFollowthrough:
    """decision-without-followthrough: decisions referencing open issues."""

    def test_decision_referencing_open_issue_detected(self):
        """AC: decision with #NNN referencing an open issue → hit."""
        baseline = make_baseline(
            {
                "jarvis": make_state(
                    "jarvis",
                    issues=[
                        make_issue(42, labels=[]),
                    ],
                ),
            }
        )
        decisions = [
            make_decision("dec-1", decision="We should fix #42 via a new PR"),
        ]
        hits = detect_decision_without_followthrough(baseline, make_delta(), decisions)
        assert len(hits) == 1
        assert hits[0].detector == "decision-without-followthrough"
        assert hits[0].issue_number == 42
        assert hits[0].severity == "major"

    def test_decision_no_refs_no_hit(self):
        """Decision without #NNN ref → no hit."""
        baseline = make_baseline(
            {
                "jarvis": make_state(
                    "jarvis",
                    issues=[
                        make_issue(42),
                    ],
                ),
            }
        )
        decisions = [
            make_decision("dec-1", decision="Refactor the auth module"),
        ]
        hits = detect_decision_without_followthrough(baseline, make_delta(), decisions)
        assert len(hits) == 0

    def test_decision_refers_to_closed_issue(self):
        """Decision referencing issue NOT in open_issues → no hit."""
        baseline = make_baseline(
            {
                "jarvis": make_state(
                    "jarvis",
                    issues=[
                        make_issue(1, state="closed"),
                    ],
                ),
            }
        )
        decisions = [
            make_decision("dec-1", decision="See #999"),
        ]
        hits = detect_decision_without_followthrough(baseline, make_delta(), decisions)
        assert len(hits) == 0


# ============================================================================
# AC: Blocker-cascade detector
# ============================================================================


class TestBlockerCascadeDetector:
    """blocker-cascade: surface root blockers."""

    def test_root_blocker_surfaced(self):
        """AC: issue blocking others but not blocked → root blocker hit."""
        baseline = make_baseline(
            {
                "jarvis": make_state(
                    "jarvis",
                    issues=[
                        make_issue(1, blocks=[2, 3]),  # root blocker
                        make_issue(2, is_blocked=True),  # transitively blocked
                        make_issue(3, is_blocked=True),  # transitively blocked
                    ],
                ),
            }
        )
        hits = detect_blocker_cascade(baseline, make_delta(), [])
        assert len(hits) == 1
        assert hits[0].detector == "blocker-cascade"
        assert hits[0].issue_number == 1
        assert hits[0].severity == "critical"

    def test_no_blockers_no_hits(self):
        """No blocking relationships → no hits."""
        baseline = make_baseline(
            {
                "jarvis": make_state(
                    "jarvis",
                    issues=[
                        make_issue(1),
                        make_issue(2),
                    ],
                ),
            }
        )
        hits = detect_blocker_cascade(baseline, make_delta(), [])
        assert len(hits) == 0

    def test_transitive_chain_surfaces_root(self):
        """AC: A→B→C chain surfaces A (root), not B or C."""
        baseline = make_baseline(
            {
                "jarvis": make_state(
                    "jarvis",
                    issues=[
                        make_issue(1, blocks=[2]),
                        make_issue(2, is_blocked=True, blocks=[3]),
                        make_issue(3, is_blocked=True),
                    ],
                ),
            }
        )
        hits = detect_blocker_cascade(baseline, make_delta(), [])
        assert len(hits) == 1
        assert hits[0].issue_number == 1


# ============================================================================
# AC: Contradiction-detector prefilter
# ============================================================================


class TestContradictionPrefilter:
    """build_contradiction_prefilter returns ≤14-day decision↔issue pairs."""

    def test_recent_decision_with_ref_included(self):
        """Recent decision (<14d) with #NNN → included in prefilter."""
        decisions = [
            make_decision(
                "dec-1", decision="Fix #42", created_days_ago=DECISION_PREFILTER_DAYS - 1
            ),
        ]
        result = build_contradiction_prefilter(decisions, make_baseline())
        assert len(result) == 1
        assert result[0][1] == 42

    def test_old_decision_excluded(self):
        """Old decision (>14d) → excluded from prefilter."""
        decisions = [
            make_decision(
                "dec-1", decision="Fix #42", created_days_ago=DECISION_PREFILTER_DAYS + 1
            ),
        ]
        result = build_contradiction_prefilter(decisions, make_baseline())
        assert len(result) == 0

    def test_decision_without_ref_excluded(self):
        """Decision without #NNN ref → excluded."""
        decisions = [
            make_decision("dec-1", decision="Refactor auth", created_days_ago=1),
        ]
        result = build_contradiction_prefilter(decisions, make_baseline())
        assert len(result) == 0

    def test_multiple_refs_in_one_decision(self):
        """One decision referencing multiple issues → multiple pairs."""
        decisions = [
            make_decision("dec-1", decision="Fix #42 and #99", created_days_ago=1),
        ]
        result = build_contradiction_prefilter(decisions, make_baseline())
        assert len(result) == 2
        refs = {r[1] for r in result}
        assert refs == {42, 99}


# ============================================================================
# AC: memory↔git contradiction — verdict folding (#1016)
# ============================================================================


def make_verdict(
    decision_id: str = "dec-1",
    issue_number: int = 42,
    repo: str = "Osasuwu/jarvis",
    verdict: str = "contradiction",
    rationale: str = "memory says shipped; issue still open",
) -> ContradictionVerdict:
    """Helper to construct a ContradictionVerdict fixture."""
    return ContradictionVerdict(
        decision_id=decision_id,
        issue_number=issue_number,
        repo=repo,
        verdict=verdict,
        rationale=rationale,
    )


class TestContradictionFolding:
    """fold_contradiction_verdicts maps verdicts → DetectorHits (AC1, AC6).

    The LLM judgment itself is the native status-record cron session — not
    tested here. This covers only the deterministic fold of its output.
    """

    def test_contradiction_verdict_becomes_hit(self):
        """A 'contradiction' verdict folds into one DetectorHit."""
        hits = fold_contradiction_verdicts([make_verdict()])
        assert len(hits) == 1
        assert hits[0].detector == MEMORY_GIT_CONTRADICTION
        assert hits[0].issue_number == 42
        assert hits[0].repo == "Osasuwu/jarvis"

    def test_rationale_carried_into_hit(self):
        """Per-candidate rationale is preserved into the hit (AC1)."""
        hits = fold_contradiction_verdicts(
            [make_verdict(rationale="decision 6f11 claims merged; PR never opened")]
        )
        assert "6f11" in hits[0].description

    def test_uncertain_verdict_dropped(self):
        """An 'uncertain' candidate is dropped, not surfaced (AC6)."""
        hits = fold_contradiction_verdicts([make_verdict(verdict="uncertain")])
        assert hits == []

    def test_no_contradiction_verdict_dropped(self):
        """A 'no_contradiction' candidate produces no hit."""
        hits = fold_contradiction_verdicts([make_verdict(verdict="no_contradiction")])
        assert hits == []

    def test_mixed_batch_only_contradictions_surface(self):
        """Only the 'contradiction' verdicts in a mixed batch fold to hits."""
        verdicts = [
            make_verdict("d1", 1, verdict="contradiction"),
            make_verdict("d2", 2, verdict="uncertain"),
            make_verdict("d3", 3, verdict="no_contradiction"),
            make_verdict("d4", 4, verdict="contradiction"),
        ]
        hits = fold_contradiction_verdicts(verdicts)
        assert {h.issue_number for h in hits} == {1, 4}

    def test_empty_verdicts_returns_empty(self):
        assert fold_contradiction_verdicts([]) == []

    def test_unknown_verdict_string_dropped(self):
        """An unrecognized verdict value is treated as uncertain → dropped."""
        hits = fold_contradiction_verdicts([make_verdict(verdict="maybe?")])
        assert hits == []


class TestContradictionCache:
    """Cached contradiction result round-trips without re-running the LLM (AC4)."""

    def test_serialize_produces_jsonable_dict(self):
        data = serialize_contradiction_cache([make_verdict()])
        # round-trips through JSON unchanged
        import json

        assert json.loads(json.dumps(data)) == data

    def test_roundtrip_preserves_verdicts(self):
        verdicts = [
            make_verdict("d1", 1, verdict="contradiction"),
            make_verdict("d2", 2, verdict="uncertain"),
        ]
        restored = deserialize_contradiction_cache(serialize_contradiction_cache(verdicts))
        assert restored == verdicts

    def test_renderer_folds_from_cache_without_llm(self):
        """Deserialized cache folds to the same hits as the live verdicts (AC4)."""
        verdicts = [
            make_verdict("d1", 1, verdict="contradiction"),
            make_verdict("d2", 2, verdict="uncertain"),
        ]
        cached = serialize_contradiction_cache(verdicts)
        from_cache = fold_contradiction_verdicts(deserialize_contradiction_cache(cached))
        from_live = fold_contradiction_verdicts(verdicts)
        assert from_cache == from_live
        assert len(from_cache) == 1  # only the contradiction survives

    def test_empty_cache_deserializes_to_empty(self):
        assert deserialize_contradiction_cache({"verdicts": []}) == []

    def test_missing_verdicts_key_tolerated(self):
        """A malformed cache (no verdicts key) deserializes to empty, not raises."""
        assert deserialize_contradiction_cache({}) == []


class TestL1OnlyGuard:
    """The contradiction detector runs L1-only; analyze() never invokes it (AC2)."""

    def test_analyze_does_not_call_fold(self):
        """The intraday-capable analyze() path must not invoke the LLM fold."""
        src = inspect.getsource(analyze)
        assert "fold_contradiction_verdicts" not in src
        assert "contradiction" not in src.lower()

    def test_analyze_emits_no_contradiction_hits(self):
        """Even with referenced decisions present, analyze() emits no
        memory-git-contradiction hits — that detector is L1-only and lives
        outside the engine path."""
        baseline = make_baseline(
            repos={
                "jarvis": make_state("jarvis", issues=[make_issue(42)]),
            },
            provenance={"gh:jarvis": Provenance(ran=True, ok=True, age=0)},
        )
        decisions = [make_decision("d1", decision="Shipped #42", created_days_ago=1)]
        result = analyze(baseline, make_delta(), decisions)
        assert all(h.detector != MEMORY_GIT_CONTRADICTION for h in result.detector_hits)


# ============================================================================
# AC: Top-N ranking
# ============================================================================


class TestRanking:
    """rank_detector_hits returns at most TOP_N_CAP items, sorted by severity."""

    def test_at_most_top_n_returned(self):
        """AC: ranking caps at TOP_N_CAP items."""
        hits = [
            DetectorHit(detector=f"test-{i}", severity="minor", repo="jarvis")
            for i in range(TOP_N_CAP + 5)
        ]
        ranked = rank_detector_hits(hits)
        assert len(ranked) <= TOP_N_CAP

    def test_critical_before_major_before_minor(self):
        """AC: critical items ranked before major before minor."""
        hits = [
            DetectorHit(detector="minor-hit", severity="minor", repo="jarvis"),
            DetectorHit(detector="critical-hit", severity="critical", repo="jarvis"),
            DetectorHit(detector="major-hit", severity="major", repo="jarvis"),
        ]
        ranked = rank_detector_hits(hits)
        assert ranked[0].detector_hit.detector == "critical-hit"
        assert ranked[1].detector_hit.detector == "major-hit"
        assert ranked[2].detector_hit.detector == "minor-hit"

    def test_rank_numbers_are_one_indexed(self):
        """Rank starts at 1 and increments."""
        hits = [
            DetectorHit(detector="a", severity="critical", repo="jarvis"),
            DetectorHit(detector="b", severity="major", repo="jarvis"),
        ]
        ranked = rank_detector_hits(hits)
        assert ranked[0].rank == 1
        assert ranked[1].rank == 2

    def test_empty_hits_returns_empty(self):
        """No hits → empty ranking."""
        assert rank_detector_hits([]) == []

    def test_top_n_is_documented_constant(self):
        """AC: TOP_N_CAP is a module-level documented constant."""
        assert isinstance(TOP_N_CAP, int)
        assert TOP_N_CAP > 0


# ============================================================================
# AC: Health verdict — provenance contract
# ============================================================================


class TestHealthVerdict:
    """Health is GREEN only if all sources fresh/ok AND no detector hits."""

    def test_green_when_all_sources_fresh_no_hits(self):
        """AC: all sources ok + fresh, no hits → health ok=True."""
        health = compute_health_verdict(
            make_baseline(
                provenance={"gh:jarvis": Provenance(ran=True, ok=True, age=0)},
            ),
            [],
        )
        assert health.ok is True

    def test_not_green_when_source_did_not_run(self):
        """AC: source with ran=False → health not green."""
        health = compute_health_verdict(
            make_baseline(
                provenance={"gh:jarvis": Provenance(ran=False, ok=False, age=0)},
            ),
            [],
        )
        assert health.ok is False
        assert "did not run" in health.reason

    def test_not_green_when_source_failed(self):
        """AC: source with ok=False → health not green."""
        health = compute_health_verdict(
            make_baseline(
                provenance={"gh:jarvis": Provenance(ran=True, ok=False, age=0)},
            ),
            [],
        )
        assert health.ok is False
        assert "ok=False" in health.reason

    def test_not_green_when_source_stale(self):
        """AC: source with age > FRESHNESS_AGE_SECONDS → health not green."""
        health = compute_health_verdict(
            make_baseline(
                provenance={
                    "gh:jarvis": Provenance(
                        ran=True,
                        ok=True,
                        age=FRESHNESS_AGE_SECONDS + 1,
                    )
                },
            ),
            [],
        )
        assert health.ok is False
        assert "stale" in health.reason

    def test_not_green_with_detector_hits(self):
        """AC: fresh sources but with detector hits → health not green."""
        health = compute_health_verdict(
            make_baseline(
                provenance={"gh:jarvis": Provenance(ran=True, ok=True, age=0)},
            ),
            [
                DetectorHit(detector="test", severity="major", repo="jarvis"),
            ],
        )
        assert health.ok is False
        assert "detector hit" in health.reason

    def test_green_requires_all_sources_fresh(self):
        """Multiple sources: one stale → not green."""
        health = compute_health_verdict(
            make_baseline(
                provenance={
                    "gh:jarvis": Provenance(ran=True, ok=True, age=0),
                    "gh:redrobot": Provenance(
                        ran=True,
                        ok=True,
                        age=FRESHNESS_AGE_SECONDS + 100,
                    ),
                },
            ),
            [],
        )
        assert health.ok is False


# ============================================================================
# AC: Constants are module-level
# ============================================================================


class TestModuleConstants:
    """AC: Thresholds are module-level constants with documented defaults."""

    def test_stale_inprogress_days_constant(self):
        assert isinstance(STALE_INPROGRESS_DAYS, int)
        assert STALE_INPROGRESS_DAYS > 0

    def test_freshness_age_seconds_constant(self):
        assert isinstance(FRESHNESS_AGE_SECONDS, (int, float))
        assert FRESHNESS_AGE_SECONDS > 0

    def test_decision_prefilter_days_constant(self):
        assert isinstance(DECISION_PREFILTER_DAYS, int)
        assert DECISION_PREFILTER_DAYS > 0


# ============================================================================
# Integration tests
# ============================================================================


class TestIntegration:
    """End-to-end analyze() scenarios."""

    def test_empty_state_returns_green(self):
        """No repos, no decisions → green health, empty lists."""
        result = analyze(make_baseline(), make_delta(), [])
        assert result.health.ok is True
        assert result.detector_hits == []
        assert result.ranking == []

    def test_stale_issue_makes_health_red(self):
        """Single stale in-progress issue → hits + non-green health."""
        baseline = make_baseline(
            repos={
                "jarvis": make_state(
                    "jarvis",
                    issues=[
                        make_issue(
                            1,
                            labels=["status:in-progress"],
                            updated_days_ago=STALE_INPROGRESS_DAYS + 5,
                        ),
                    ],
                ),
            },
            provenance={"gh:jarvis": Provenance(ran=True, ok=True, age=0)},
        )
        result = analyze(baseline, make_delta(), [])
        assert len(result.detector_hits) >= 1
        assert result.health.ok is False

    def test_provenance_in_digest(self):
        """Baseline provenance is carried through to digest."""
        baseline = make_baseline(
            repos={},
            provenance={
                "gh:jarvis": Provenance(ran=True, ok=True, age=0, input_rows=10),
            },
        )
        result = analyze(baseline, make_delta(), [])
        assert "gh:jarvis" in result.provenance
        assert result.provenance["gh:jarvis"].input_rows == 10

    def test_delta_provenance_merged(self):
        """Delta repo provenance is added to digest."""
        baseline = make_baseline(
            provenance={"gh:jarvis": Provenance(ran=True, ok=True, age=0)},
        )
        delta = make_delta(
            {
                "redrobot": make_state(
                    "redrobot",
                    provenance=Provenance(ran=True, ok=True, age=100),
                ),
            }
        )
        result = analyze(baseline, delta, [])
        assert "delta:redrobot" in result.provenance
