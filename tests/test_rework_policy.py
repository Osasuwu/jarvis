"""Tests for rework loop-stop policy decision module (#634).

Verifies that the pure-function policy module correctly decides whether
a PR rework loop should continue, has converged, or has terminated due to
one of four guard conditions:
  - max_attempts: ≥3 attempts
  - scope_creep: LOC delta >50% OR files outside initial PR diff
  - no_convergence: critical+major finding counts not strictly decreasing
  - conflict: same file:line touched in multiple attempts
"""

from __future__ import annotations

import pytest

from rework_policy import (
    LoopDecision,
    decide,
)


# -- Test data helpers -------------------------------------------------------


def make_attempt(
    attempt_num: int,
    n_critical: int,
    n_major: int,
    files_touched: set[str] | None = None,
    loc_delta: int | None = None,
    conflicts: dict[str, set[int]] | None = None,
) -> dict:
    """Helper to construct an attempt record."""
    return {
        "attempt": attempt_num,
        "n_critical": n_critical,
        "n_major": n_major,
        "files_touched": files_touched or set(),
        "loc_delta": loc_delta or 0,
        "conflicts": conflicts or {},  # {file: {line_nums}}
    }


# ============================================================================
# AC Tests: Max Attempts Guard
# ============================================================================


class TestMaxAttemptsGuard:
    """max_attempts: ≥3 attempts → stuck_attempts."""

    def test_attempt_3_no_convergence_returns_stuck_attempts(self):
        """AC: attempt 3, no convergence → stuck_attempts."""
        history = [
            make_attempt(1, n_critical=5, n_major=6),
            make_attempt(2, n_critical=3, n_major=4),
            make_attempt(3, n_critical=2, n_major=3),
        ]
        result = decide(
            attempts=3,
            history=history,
            initial_files={"a.py", "b.py"},
        )
        assert result.decision == LoopDecision.STUCK_ATTEMPTS

    def test_attempt_2_within_attempts_continues(self):
        """AC: history [(5,6),(3,4)] at attempt 2 within scope → continue."""
        history = [
            make_attempt(1, n_critical=5, n_major=6),
            make_attempt(2, n_critical=3, n_major=4),
        ]
        result = decide(
            attempts=2,
            history=history,
            initial_files={"a.py", "b.py"},
        )
        assert result.decision == LoopDecision.CONTINUE


# ============================================================================
# AC Tests: Scope Creep Guard
# ============================================================================


class TestScopeCreepGuard:
    """scope_creep: LOC delta >50% OR files outside initial diff → stuck_scope."""

    def test_loc_delta_51_percent_triggers_scope_creep(self):
        """AC: attempt 2, LOC delta = 51% of original → stuck_scope."""
        history = [
            make_attempt(1, n_critical=5, n_major=6, loc_delta=100),
            make_attempt(2, n_critical=3, n_major=4, loc_delta=151),
        ]
        result = decide(
            attempts=2,
            history=history,
            initial_files={"a.py", "b.py"},
        )
        assert result.decision == LoopDecision.STUCK_SCOPE

    def test_loc_delta_exactly_50_percent_is_safe(self):
        """Edge: LOC delta exactly 50% should NOT trigger scope_creep."""
        history = [
            make_attempt(1, n_critical=5, n_major=6, loc_delta=100),
            make_attempt(2, n_critical=3, n_major=4, loc_delta=150),
        ]
        result = decide(
            attempts=2,
            history=history,
            initial_files={"a.py", "b.py"},
        )
        assert result.decision == LoopDecision.CONTINUE

    def test_file_outside_initial_diff_triggers_scope_creep(self):
        """AC: attempt 2, files touched include one outside initial diff → stuck_scope."""
        history = [
            make_attempt(1, n_critical=5, n_major=6, files_touched={"a.py", "b.py"}),
            make_attempt(2, n_critical=3, n_major=4, files_touched={"a.py", "c.py"}),
        ]
        result = decide(
            attempts=2,
            history=history,
            initial_files={"a.py", "b.py"},
        )
        assert result.decision == LoopDecision.STUCK_SCOPE

    def test_all_files_within_initial_diff_is_safe(self):
        """All files in attempt stay within initial diff → scope OK."""
        history = [
            make_attempt(1, n_critical=5, n_major=6, files_touched={"a.py", "b.py"}),
            make_attempt(2, n_critical=3, n_major=4, files_touched={"a.py"}),
        ]
        result = decide(
            attempts=2,
            history=history,
            initial_files={"a.py", "b.py"},
        )
        assert result.decision == LoopDecision.CONTINUE


# ============================================================================
# AC Tests: No Convergence Guard
# ============================================================================


class TestNoConvergenceGuard:
    """no_convergence: n_critical + n_major not strictly decreasing → stuck_no_convergence."""

    def test_flat_finding_counts_triggers_no_convergence(self):
        """AC: [(5,6),(3,4),(3,4)] attempt 3==2 → stuck_no_convergence."""
        history = [
            make_attempt(1, n_critical=5, n_major=6),
            make_attempt(2, n_critical=3, n_major=4),
            make_attempt(3, n_critical=3, n_major=4),
        ]
        result = decide(
            attempts=3,
            history=history,
            initial_files={"a.py"},
        )
        assert result.decision == LoopDecision.STUCK_NO_CONVERGENCE

    def test_strictly_decreasing_allows_continue(self):
        """AC: history [(5,6),(3,4),(0,2)] → converged."""
        history = [
            make_attempt(1, n_critical=5, n_major=6),
            make_attempt(2, n_critical=3, n_major=4),
            make_attempt(3, n_critical=0, n_major=2),
        ]
        result = decide(
            attempts=3,
            history=history,
            initial_files={"a.py"},
        )
        assert result.decision == LoopDecision.CONVERGED

    def test_increase_in_findings_triggers_no_convergence(self):
        """If findings go up (not strictly decreasing), guard fires."""
        history = [
            make_attempt(1, n_critical=2, n_major=3),
            make_attempt(2, n_critical=3, n_major=2),  # critical went up
        ]
        result = decide(
            attempts=2,
            history=history,
            initial_files={"a.py"},
        )
        # Violation of strictly decreasing — both components must decrease
        assert result.decision == LoopDecision.STUCK_NO_CONVERGENCE


# ============================================================================
# AC Tests: Conflict Guard
# ============================================================================


class TestConflictGuard:
    """conflict: same file:line touched in 2 different attempts → stuck_conflict."""

    def test_same_file_line_in_two_attempts_triggers_conflict(self):
        """AC: file.py:42 touched in attempts 1 and 2 → stuck_conflict."""
        history = [
            make_attempt(
                1,
                n_critical=5,
                n_major=6,
                conflicts={"file.py": {42}},
            ),
            make_attempt(
                2,
                n_critical=3,
                n_major=4,
                conflicts={"file.py": {42}},
            ),
        ]
        result = decide(
            attempts=2,
            history=history,
            initial_files={"file.py"},
        )
        assert result.decision == LoopDecision.STUCK_CONFLICT

    def test_different_lines_in_same_file_is_safe(self):
        """Same file, different lines → no conflict."""
        history = [
            make_attempt(
                1,
                n_critical=5,
                n_major=6,
                conflicts={"file.py": {42}},
            ),
            make_attempt(
                2,
                n_critical=3,
                n_major=4,
                conflicts={"file.py": {43}},
            ),
        ]
        result = decide(
            attempts=2,
            history=history,
            initial_files={"file.py"},
        )
        assert result.decision == LoopDecision.CONTINUE

    def test_different_files_is_safe(self):
        """Different files → no conflict."""
        history = [
            make_attempt(
                1,
                n_critical=5,
                n_major=6,
                conflicts={"a.py": {42}},
            ),
            make_attempt(
                2,
                n_critical=3,
                n_major=4,
                conflicts={"b.py": {42}},
            ),
        ]
        result = decide(
            attempts=2,
            history=history,
            initial_files={"a.py", "b.py"},
        )
        assert result.decision == LoopDecision.CONTINUE


# ============================================================================
# AC Tests: Convergence
# ============================================================================


class TestConvergence:
    """Convergence target: n_critical == 0 AND n_major <= 2 → converged."""

    def test_convergence_at_attempt_3(self):
        """AC: history [(5,6),(2,3),(0,2)] → converged."""
        history = [
            make_attempt(1, n_critical=5, n_major=6),
            make_attempt(2, n_critical=2, n_major=3),
            make_attempt(3, n_critical=0, n_major=2),
        ]
        result = decide(
            attempts=3,
            history=history,
            initial_files={"a.py"},
        )
        assert result.decision == LoopDecision.CONVERGED

    def test_convergence_at_attempt_2(self):
        """Hitting the convergence target at attempt 2."""
        history = [
            make_attempt(1, n_critical=3, n_major=4),
            make_attempt(2, n_critical=0, n_major=2),
        ]
        result = decide(
            attempts=2,
            history=history,
            initial_files={"a.py"},
        )
        assert result.decision == LoopDecision.CONVERGED

    def test_not_converged_with_critical_remaining(self):
        """n_critical > 0 means not converged."""
        history = [
            make_attempt(1, n_critical=3, n_major=4),
            make_attempt(2, n_critical=1, n_major=2),
        ]
        result = decide(
            attempts=2,
            history=history,
            initial_files={"a.py"},
        )
        assert result.decision == LoopDecision.CONTINUE

    def test_not_converged_with_too_many_majors(self):
        """n_major > 2 means not converged."""
        history = [
            make_attempt(1, n_critical=3, n_major=4),
            make_attempt(2, n_critical=0, n_major=3),
        ]
        result = decide(
            attempts=2,
            history=history,
            initial_files={"a.py"},
        )
        assert result.decision == LoopDecision.CONTINUE

    def test_convergence_with_exactly_2_majors(self):
        """Edge: n_major exactly = 2 with n_critical = 0 → converged."""
        history = [
            make_attempt(1, n_critical=3, n_major=4),
            make_attempt(2, n_critical=0, n_major=2),
        ]
        result = decide(
            attempts=2,
            history=history,
            initial_files={"a.py"},
        )
        assert result.decision == LoopDecision.CONVERGED


# ============================================================================
# Edge Tests: Boundaries
# ============================================================================


class TestBoundaryConditions:
    """Edge cases: exact boundaries for guards."""

    def test_attempt_exactly_3_is_stuck(self):
        """Edge: attempt exactly = 3 → stuck (not ≥ 4)."""
        history = [
            make_attempt(1, n_critical=5, n_major=6),
            make_attempt(2, n_critical=3, n_major=4),
            make_attempt(3, n_critical=2, n_major=3),
        ]
        result = decide(
            attempts=3,
            history=history,
            initial_files={"a.py"},
        )
        assert result.decision == LoopDecision.STUCK_ATTEMPTS

    def test_attempt_2_is_allowed(self):
        """Edge: attempt exactly = 2 → still allowed (not yet stuck)."""
        history = [
            make_attempt(1, n_critical=5, n_major=6),
            make_attempt(2, n_critical=3, n_major=4),
        ]
        result = decide(
            attempts=2,
            history=history,
            initial_files={"a.py"},
        )
        # Will continue unless another guard fires
        assert result.decision in (LoopDecision.CONTINUE, LoopDecision.CONVERGED)

    def test_loc_delta_exactly_50_is_boundary(self):
        """Edge: LOC delta exactly 50% → allowed (> not >=)."""
        history = [
            make_attempt(1, n_critical=5, n_major=6, loc_delta=100),
            make_attempt(2, n_critical=3, n_major=4, loc_delta=150),
        ]
        result = decide(
            attempts=2,
            history=history,
            initial_files={"a.py"},
        )
        assert result.decision != LoopDecision.STUCK_SCOPE

    def test_n_major_exactly_2_converges(self):
        """Edge: n_major exactly = 2 with n_critical = 0 → converged."""
        history = [
            make_attempt(1, n_critical=3, n_major=5),
            make_attempt(2, n_critical=0, n_major=2),
        ]
        result = decide(
            attempts=2,
            history=history,
            initial_files={"a.py"},
        )
        assert result.decision == LoopDecision.CONVERGED


# ============================================================================
# Integration Tests
# ============================================================================


class TestIntegration:
    """Multi-guard scenarios."""

    def test_multiple_guards_could_fire_first_one_wins(self):
        """If multiple guards would fire, which takes precedence?

        Current design: guards are independent, any one firing terminates.
        We assert the actual result, not a precedence order.
        """
        # Scope creep + no convergence both present
        history = [
            make_attempt(1, n_critical=5, n_major=6, loc_delta=100),
            make_attempt(2, n_critical=5, n_major=6, loc_delta=151),  # scope + no conv
        ]
        result = decide(
            attempts=2,
            history=history,
            initial_files={"a.py"},
        )
        # Should hit one of the stuck guards
        assert result.decision in (
            LoopDecision.STUCK_SCOPE,
            LoopDecision.STUCK_NO_CONVERGENCE,
        )

    def test_happy_path_attempt_2_converging(self):
        """Happy path: attempt 2, converging towards target."""
        history = [
            make_attempt(1, n_critical=5, n_major=6),
            make_attempt(2, n_critical=0, n_major=2),
        ]
        result = decide(
            attempts=2,
            history=history,
            initial_files={"a.py", "b.py"},
        )
        assert result.decision == LoopDecision.CONVERGED

    def test_happy_path_attempt_2_still_improving(self):
        """Happy path: attempt 2, still making progress."""
        history = [
            make_attempt(1, n_critical=5, n_major=6),
            make_attempt(2, n_critical=2, n_major=3),
        ]
        result = decide(
            attempts=2,
            history=history,
            initial_files={"a.py", "b.py"},
        )
        assert result.decision == LoopDecision.CONTINUE


# ============================================================================
# Return Value Structure
# ============================================================================


class TestReturnStructure:
    """Verify the return value has all required fields."""

    def test_result_has_decision_field(self):
        """Result object must have .decision field."""
        history = [
            make_attempt(1, n_critical=5, n_major=6),
        ]
        result = decide(
            attempts=1,
            history=history,
            initial_files={"a.py"},
        )
        assert hasattr(result, "decision")
        assert isinstance(result.decision, LoopDecision)

    def test_result_has_reason_field(self):
        """Result object must have .reason field for debugging."""
        history = [
            make_attempt(1, n_critical=5, n_major=6),
            make_attempt(2, n_critical=3, n_major=4),
            make_attempt(3, n_critical=2, n_major=3),
        ]
        result = decide(
            attempts=3,
            history=history,
            initial_files={"a.py"},
        )
        assert hasattr(result, "reason")
        assert isinstance(result.reason, str)
        assert len(result.reason) > 0
