"""Unit tests for event emission at task completion (#953).

Tests cover:
- AC1: Event emission on terminal transitions (task_done, task_failed)
- AC2: PR-evidence check for fresh-shape and rework-shape goals
- AC3: Secondary evidence channel from executor stdout JSON
- AC4: Evidence checks via github_client (no gh CLI)
- AC5: Branch contract in task_dispatch
- AC6: Orchestrator routing table for all (event_type, pr_evidence, exit_confirmed) combos
- AC7: Re-drive mechanics with idempotency keys and MAX_ATTEMPTS
- AC8: No cron, no periodic scan — event-driven only
- AC10: Event-first ordering and dedup on re-observation
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from unittest import mock

import pytest

from agents.github_client import (
    check_pr_evidence_fresh_shape,
    check_pr_evidence_rework_shape,
    parse_executor_stdout,
)
from agents.orchestrator import Route, handle_event
from agents.task_dispatch import (
    TrackedProc,
    _augment_branch_directive,
    poll_completions,
)


# =============================================================================
# Fakes and Mocks
# =============================================================================


class FakeEventQueue:
    """In-memory event queue for testing event emission."""

    def __init__(self) -> None:
        self.emitted: list[dict[str, Any]] = []

    def emit_event(
        self,
        event_type: str,
        severity: str,
        payload: dict[str, Any],
        *,
        dedup_key: str | None = None,
    ) -> dict[str, Any]:
        """Emit an event, returning the inserted row."""
        row = {
            "id": len(self.emitted),
            "event_type": event_type,
            "severity": severity,
            "payload": payload,
            "dedup_key": dedup_key or f"{event_type}:{len(self.emitted)}",
            "created_at": datetime.now(UTC),
        }
        self.emitted.append(row)
        return row


class _FakeProc:
    """A process handle whose ``poll()`` reports a fixed exit code (exited)."""

    def __init__(self, rc: int) -> None:
        self._rc = rc

    def poll(self) -> int:
        return self._rc


class _RecordingPort:
    """Minimal task-queue port stand-in that records transition order.

    ``poll_completions`` only ever calls ``transition`` on the port; the other
    Protocol methods are unused here, so they raise to catch accidental use.
    """

    def __init__(self, order_log: list[tuple[str, ...]]) -> None:
        self._order = order_log
        self.transitions: list[tuple[str, str, str | None]] = []

    def transition(
        self, task_id: str, to_status: str, *, reason: str | None = None
    ) -> dict[str, Any]:
        self._order.append(("transition", task_id, to_status))
        self.transitions.append((task_id, to_status, reason))
        return {"id": task_id, "status": to_status}


def _recording_emit(
    order_log: list[tuple[str, ...]], sink: list[dict[str, Any]]
) -> Any:
    """Build an ``event_emit`` callback that records emit order and payloads."""

    def emit(
        event_type: str,
        severity: str,
        payload: dict[str, Any],
        *,
        dedup_key: str | None = None,
    ) -> dict[str, Any]:
        order_log.append(("event", event_type, dedup_key))
        row = {
            "event_type": event_type,
            "severity": severity,
            "payload": payload,
            "dedup_key": dedup_key,
        }
        sink.append(row)
        return row

    return emit


# =============================================================================
# AC2: PR-Evidence Check — Fresh Shape
# =============================================================================


class TestPREvidenceFreshShape:
    """Test PR-evidence check for fresh-shape goals (create your working branch as `task/<task_id>`)."""

    def test_pr_exists_with_task_branch_convention(self) -> None:
        """Fresh shape: PR exists with head branch `task/abc123`."""
        mock_client = mock.MagicMock()
        mock_client.get_pull_by_head_branch.return_value = {"id": 1, "number": 42}

        evidence = check_pr_evidence_fresh_shape(
            task_id="abc123",
            goal="implement feature X",
            spawned_at=datetime.now(UTC),
            client=mock_client,
        )
        assert evidence is True

    def test_pr_missing_task_branch_convention(self) -> None:
        """Fresh shape: no PR with head branch `task/abc123`."""
        mock_client = mock.MagicMock()
        mock_client.get_pull_by_head_branch.return_value = None

        evidence = check_pr_evidence_fresh_shape(
            task_id="abc123",
            goal="implement feature X",
            spawned_at=datetime.now(UTC),
            client=mock_client,
        )
        assert evidence is False

    def test_goal_with_explicit_branch_directive(self) -> None:
        """Fresh shape: goal carries explicit branch directive (non-convention)."""
        mock_client = mock.MagicMock()
        mock_client.get_pull_by_head_branch.return_value = {"id": 1, "number": 42}

        # Goal has explicit "branch=feature-xyz" directive
        evidence = check_pr_evidence_fresh_shape(
            task_id="abc123",
            goal="implement feature X (branch=feature-xyz)",
            spawned_at=datetime.now(UTC),
            client=mock_client,
        )
        # Should look up the explicit branch, not the convention
        mock_client.get_pull_by_head_branch.assert_called_with("feature-xyz")
        assert evidence is True


# =============================================================================
# AC2: PR-Evidence Check — Rework Shape
# =============================================================================


class TestPREvidenceReworkShape:
    """Test PR-evidence check for rework-shape goals (continue on PR #N)."""

    def test_pr_has_activity_after_spawned_at(self) -> None:
        """Rework shape: PR #42 has activity (commits/updatedAt) after spawned_at."""
        mock_client = mock.MagicMock()
        spawned_at = datetime(2026, 6, 21, 10, 0, 0, tzinfo=UTC)
        # PR updated after spawn
        mock_client.get_pull_by_number.return_value = {
            "number": 42,
            "updated_at": "2026-06-21T11:00:00Z",  # 1 hour after spawn
            "head": {"sha": "abc123"},
        }
        mock_client.list_commits_for_pull.return_value = [
            {"sha": "abc123", "commit": {"author": {"date": "2026-06-21T10:30:00Z"}}}
        ]

        evidence = check_pr_evidence_rework_shape(
            task_id="abc123",
            goal="/rework #42",
            pr_number=42,
            spawned_at=spawned_at,
            client=mock_client,
        )
        assert evidence is True

    def test_pr_no_activity_after_spawned_at(self) -> None:
        """Rework shape: PR #42 unchanged since spawned_at."""
        mock_client = mock.MagicMock()
        spawned_at = datetime(2026, 6, 21, 10, 0, 0, tzinfo=UTC)
        # PR updated BEFORE spawn — no new activity
        mock_client.get_pull_by_number.return_value = {
            "number": 42,
            "updated_at": "2026-06-21T09:00:00Z",
        }
        mock_client.list_commits_for_pull.return_value = []

        evidence = check_pr_evidence_rework_shape(
            task_id="abc123",
            goal="/rework #42",
            pr_number=42,
            spawned_at=spawned_at,
            client=mock_client,
        )
        assert evidence is False

    def test_pr_not_found(self) -> None:
        """Rework shape: PR #42 does not exist."""
        mock_client = mock.MagicMock()
        mock_client.get_pull_by_number.return_value = None

        evidence = check_pr_evidence_rework_shape(
            task_id="abc123",
            goal="/rework #42",
            pr_number=42,
            spawned_at=datetime.now(UTC),
            client=mock_client,
        )
        assert evidence is False


# =============================================================================
# AC3: Secondary Evidence Channel — Executor Stdout Parsing
# =============================================================================


class TestExecutorStdoutParsing:
    """Test parsing executor stdout JSON for PR-evidence fallback."""

    def test_parse_executor_stdout_with_pr_url(self) -> None:
        """Executor stdout contains PR URL — extract and verify."""
        stdout_json = {
            "status": "completed",
            "pr_url": "https://github.com/Osasuwu/jarvis/pull/999",
            "message": "Opened PR #999",
        }
        pr_info = parse_executor_stdout(json.dumps(stdout_json))
        assert pr_info is not None
        assert pr_info["number"] == 999

    def test_parse_executor_stdout_missing_pr_url(self) -> None:
        """Executor stdout has no PR URL."""
        stdout_json = {
            "status": "completed",
            "message": "No PR was opened",
        }
        pr_info = parse_executor_stdout(json.dumps(stdout_json))
        assert pr_info is None

    def test_parse_executor_stdout_malformed(self) -> None:
        """Executor stdout is not valid JSON."""
        pr_info = parse_executor_stdout("garbage data")
        assert pr_info is None


# =============================================================================
# AC6: Orchestrator Routing Table — task_done / task_failed Combinations
# =============================================================================


class TestOrchestratorRoutingTable:
    """Test routing table for all (event_type, pr_evidence, exit_confirmed) combos."""

    def test_task_done_pr_evidence_true(self) -> None:
        """task_done + pr_evidence=true → inline no-op (never re-drive, never escalate)."""
        event = {
            "event_type": "task_done",
            "severity": "info",
            "payload": {
                "task_id": "t123",
                "pr_evidence": True,
                "goal": "implement feature",
            },
        }
        decision = handle_event(event)
        assert decision.route == Route.HANDLE_INLINE
        assert decision.noop is True

    def test_task_failed_pr_evidence_true(self) -> None:
        """task_failed + pr_evidence=true → inline no-op (work landed; exit code lost)."""
        event = {
            "event_type": "task_failed",
            "severity": "info",
            "payload": {
                "task_id": "t123",
                "pr_evidence": True,
                "exit_confirmed": True,
                "goal": "implement feature",
            },
        }
        decision = handle_event(event)
        assert decision.route == Route.HANDLE_INLINE
        assert decision.noop is True

    def test_task_done_pr_evidence_false_attempt_1(self) -> None:
        """task_done + pr_evidence=false + attempt=1 → EMIT_TASK re-drive."""
        event = {
            "event_type": "task_done",
            "severity": "medium",
            "payload": {
                "task_id": "t123",
                "attempt": 1,
                "pr_evidence": False,
                "goal": "implement feature",
            },
        }
        decision = handle_event(event)
        assert decision.route == Route.EMIT_TASK
        assert "re-drive" in decision.goal.lower() or "retry" in decision.goal.lower()

    def test_task_failed_pr_evidence_false_confirmed_attempt_1(self) -> None:
        """task_failed + exit_confirmed=true + pr_evidence=false + attempt=1 → EMIT_TASK."""
        event = {
            "event_type": "task_failed",
            "severity": "medium",
            "payload": {
                "task_id": "t123",
                "attempt": 1,
                "exit_confirmed": True,
                "pr_evidence": False,
                "failure_reason": "exit 1",
                "goal": "implement feature",
            },
        }
        decision = handle_event(event)
        assert decision.route == Route.EMIT_TASK

    def test_task_done_pr_evidence_false_attempt_2_escalate(self) -> None:
        """task_done + pr_evidence=false + attempt≥2 → ESCALATE."""
        event = {
            "event_type": "task_done",
            "severity": "medium",
            "payload": {
                "task_id": "t123",
                "attempt": 2,
                "pr_evidence": False,
                "goal": "implement feature",
            },
        }
        decision = handle_event(event)
        assert decision.route == Route.ESCALATE
        assert decision.assignee == "owner"

    def test_task_failed_unconfirmed_exit_escalate(self) -> None:
        """task_failed + exit_confirmed=false → ESCALATE (never re-drive unconfirmed death)."""
        event = {
            "event_type": "task_failed",
            "severity": "medium",
            "payload": {
                "task_id": "t123",
                "exit_confirmed": False,
                "failure_reason": "reaped",
                "goal": "implement feature",
            },
        }
        decision = handle_event(event)
        assert decision.route == Route.ESCALATE
        assert decision.assignee == "owner"

    def test_task_failed_pr_evidence_null_escalate(self) -> None:
        """task_failed + pr_evidence=null (unparseable goal) → ESCALATE, never re-drive."""
        event = {
            "event_type": "task_failed",
            "severity": "medium",
            "payload": {
                "task_id": "t123",
                "pr_evidence": None,  # unparseable goal
                "failure_reason": "exit 1",
                "goal": "some unparseable text",
            },
        }
        decision = handle_event(event)
        assert decision.route == Route.ESCALATE


# =============================================================================
# AC7: Re-drive Mechanics — Idempotency Keys and MAX_ATTEMPTS
# =============================================================================


class TestRedriveIdempotency:
    """Test re-drive key structure and idempotency collision handling."""

    def test_redrive_key_structure(self) -> None:
        """Re-drive Decision carries idempotency key ``<lineage_key>:r<next_attempt>``.

        Drives the real ``handle_event`` re-drive branch (task_done + no PR
        evidence + attempt < MAX_ATTEMPTS) and asserts on the product key, not a
        re-derived string. ``lineage_key`` on the payload is what the key keys
        off — incrementing the attempt by one each re-drive.
        """
        event = {
            "event_type": "task_done",
            "severity": "medium",
            "payload": {
                "task_id": "t123",
                "lineage_key": "t123",
                "attempt": 1,
                "pr_evidence": False,
                "goal": "implement feature",
            },
        }
        decision = handle_event(event)
        assert decision.route == Route.EMIT_TASK
        # attempt 1 → next attempt 2 → key suffix :r2
        assert decision.idempotency_key == "t123:r2"

    def test_redrive_key_falls_back_to_task_id_without_lineage_key(self) -> None:
        """Older emitters omit ``lineage_key`` → re-drive keys off ``task_id``."""
        event = {
            "event_type": "task_failed",
            "severity": "medium",
            "payload": {
                "task_id": "t999",
                "attempt": 1,
                "exit_confirmed": True,
                "pr_evidence": False,
                "goal": "implement feature",
            },
        }
        decision = handle_event(event)
        assert decision.route == Route.EMIT_TASK
        assert decision.idempotency_key == "t999:r2"

    def test_max_attempts_exhausted(self) -> None:
        """Attempt ≥ 2 (MAX_ATTEMPTS=2) and pr_evidence=false → escalate, no re-drive."""
        event = {
            "event_type": "task_done",
            "severity": "medium",
            "payload": {
                "task_id": "t123",
                "attempt": 2,
                "pr_evidence": False,
                "goal": "implement feature",
            },
        }
        decision = handle_event(event)
        # Should escalate, not re-drive (attempt >= MAX_ATTEMPTS)
        assert decision.route == Route.ESCALATE


# =============================================================================
# AC10: Event Emission — Event-First Ordering and Dedup
# =============================================================================


class TestEventEmission:
    """Test event-first emission with dedup on re-observation."""

    def test_event_emitted_before_transition(self) -> None:
        """``poll_completions`` emits the terminal event BEFORE the FSM transition.

        Event-first ordering is the crash-safety contract: if the driver dies in
        the window, re-observation re-emits and the ``dedup_key`` absorbs the
        duplicate. Verified on a real ``poll_completions`` call by recording the
        interleaving of emit vs transition into one ordered log.
        """
        order: list[tuple[str, ...]] = []
        emitted: list[dict[str, Any]] = []
        port = _RecordingPort(order)
        procs = {
            "t123": TrackedProc(
                proc=_FakeProc(0),
                started_at=0.0,
                goal="implement feature X",
                idempotency_key="t123",
                spawned_at=datetime.now(UTC),
            )
        }
        client = mock.MagicMock()
        client.get_pull_by_head_branch.return_value = {"id": 1, "number": 42}

        result = poll_completions(
            port,
            procs,
            event_emit=_recording_emit(order, emitted),
            evidence_client=client,
        )

        assert result.done == 1
        # exactly one event then one transition, event first
        assert order == [
            ("event", "task_done", "task_done:t123:a1"),
            ("transition", "t123", "done"),
        ]

    def test_dedup_key_collision_idempotent(self) -> None:
        """Re-observation of the same terminal task emits an identical dedup_key.

        The key is ``<event_type>:<task_id>:a<attempt>`` — derived from the
        task's identity and attempt, not from observation time — so two
        independent ``poll_completions`` passes over the same exited task produce
        byte-identical keys. The DB unique index then collapses the duplicate.
        """
        client = mock.MagicMock()
        client.get_pull_by_head_branch.return_value = None  # no PR → pr_evidence False

        def observe() -> str | None:
            emitted: list[dict[str, Any]] = []
            procs = {
                "t123": TrackedProc(
                    proc=_FakeProc(0),
                    started_at=0.0,
                    goal="implement feature X",
                    idempotency_key="t123",  # root → attempt 1
                    spawned_at=datetime.now(UTC),
                )
            }
            poll_completions(
                _RecordingPort([]),
                procs,
                event_emit=_recording_emit([], emitted),
                evidence_client=client,
            )
            return emitted[0]["dedup_key"]

        first = observe()
        second = observe()
        assert first == "task_done:t123:a1"
        assert first == second


# =============================================================================
# AC5: Branch Contract — Goal Augmentation in task_dispatch
# =============================================================================


class TestBranchContract:
    """Test branch directive in goal for fresh-shape tasks."""

    def test_fresh_shape_augmented_goal_convention(self) -> None:
        """Real ``_augment_branch_directive`` pins a fresh-shape goal to ``task/<task_id>``."""
        augmented = _augment_branch_directive("implement feature X", "abc123")
        assert augmented != "implement feature X"  # it WAS augmented
        assert "(branch=task/abc123)" in augmented

    def test_fresh_shape_with_explicit_branch_not_re_augmented(self) -> None:
        """A goal already naming a branch is left exactly as the author wrote it (AC5)."""
        goal = "implement feature X (branch=feature-xyz)"
        assert _augment_branch_directive(goal, "abc123") == goal

    def test_rework_shape_no_augmentation(self) -> None:
        """Real ``_augment_branch_directive`` never touches a rework-shape goal (AC5)."""
        goal = "/rework #42"
        # Rework targets an existing PR's branch — augmenting it would be wrong.
        assert _augment_branch_directive(goal, "abc123") == goal


# =============================================================================
# Integration: Event Emission in wake_driver.tick()
# =============================================================================


class TestEventEmissionInTick:
    """Integration test: events are emitted during completion polling in tick()."""

    def test_completion_poll_emits_task_done_event(self) -> None:
        """A clean exit emits ``task_done`` carrying the COMPUTED pr_evidence.

        Full integration through real ``poll_completions``: a fresh-shape goal
        whose injected evidence client finds the PR yields ``pr_evidence=True``
        (computed at the boundary, not handed in), plus the lineage/attempt
        parsed from the idempotency key and the AC1 dedup_key.
        """
        emitted: list[dict[str, Any]] = []
        procs = {
            "abc123": TrackedProc(
                proc=_FakeProc(0),
                started_at=0.0,
                goal="implement feature X",
                idempotency_key="abc123:r2",  # lineage abc123, attempt 2
                spawned_at=datetime.now(UTC),
            )
        }
        client = mock.MagicMock()
        client.get_pull_by_head_branch.return_value = {"id": 1, "number": 7}

        result = poll_completions(
            _RecordingPort([]),
            procs,
            event_emit=_recording_emit([], emitted),
            evidence_client=client,
        )

        assert result.done == 1
        assert len(emitted) == 1
        event = emitted[0]
        assert event["event_type"] == "task_done"
        # PR evidence was COMPUTED from the injected client, not passed in.
        assert event["payload"]["pr_evidence"] is True
        assert event["payload"]["lineage_key"] == "abc123"
        assert event["payload"]["attempt"] == 2
        assert event["dedup_key"] == "task_done:abc123:a2"
        # The evidence check used the task/<task_id> convention branch.
        client.get_pull_by_head_branch.assert_called_with("task/abc123")

    def test_completion_poll_emits_task_failed_on_nonzero_exit(self) -> None:
        """A non-zero exit emits ``task_failed`` with exit_confirmed + exit_code."""
        emitted: list[dict[str, Any]] = []
        procs = {
            "abc123": TrackedProc(
                proc=_FakeProc(1),
                started_at=0.0,
                goal="implement feature X",
                idempotency_key="abc123",
                spawned_at=datetime.now(UTC),
            )
        }
        client = mock.MagicMock()
        client.get_pull_by_head_branch.return_value = None  # no PR → pr_evidence False

        result = poll_completions(
            _RecordingPort([]),
            procs,
            event_emit=_recording_emit([], emitted),
            evidence_client=client,
        )

        assert result.failed_exit == 1
        event = emitted[0]
        assert event["event_type"] == "task_failed"
        assert event["payload"]["exit_confirmed"] is True
        assert event["payload"]["exit_code"] == 1
        assert event["payload"]["pr_evidence"] is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
