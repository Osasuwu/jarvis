"""Tests for agents/task_sweeper.py — the result-file-first sweeper (#1122 S5).

decide() is pure (no docker, no network) — its tests drive AC1/AC3/AC4/AC5/
AC7/AC8/AC13 directly. sweep() tests cover AC6 (daemon-failure threshold),
AC7 (late-result container correlation) and AC12 (adapter isolation).
"""

from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from agents.sandcastle_config import SweeperConfig
from agents.task_sweeper import (
    INVALID_RESULT,
    ContainerInfo,
    DockerCallError,
    FakeDocker,
    SubprocessDocker,
    SweeperState,
    _apply_action,
    decide,
    sweep,
)

NOW = datetime(2026, 9, 2, 12, 0, 0, tzinfo=timezone.utc)

# 4h timeout, 10min min-age, ceiling irrelevant unless stated (slots length 3).
CONFIG = SweeperConfig(
    run_timeout_hours=4,
    destructive_min_age_minutes=10,
    daemon_failure_threshold=3,
    docker_call_timeout_seconds=30,
    runtime_root=".sandcastle/runtime",
)


def _row(
    task_id: str = "t1",
    *,
    status: str = "running",
    claimed_at: datetime | None = None,
    idempotency_key: str = "t1",
) -> dict[str, Any]:
    return {
        "id": task_id,
        "status": status,
        "claimed_at": claimed_at.isoformat() if claimed_at else None,
        "idempotency_key": idempotency_key,
        "goal": "do the thing",
        "target_repo": "Osasuwu/jarvis",
        "target_type": "issue",
        "target_number": 1122,
        "origin": "sandcastle",
    }


def _result(outcome: str = "success", **overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "schemaVersion": 2,
        "runId": "run-1",
        "taskId": "t1",
        "lineageKey": "t1",
        "attempt": 1,
        "tier": "sonnet",
        "goal": "do the thing",
        "outcome": outcome,
        "failureClass": None,
        "exit": 0 if outcome == "success" else 1,
        "branch": "task/run-1",
        "commits": ["abc123"],
        "pr": False,
        "prEvidence": None,
        "failureReason": "" if outcome == "success" else "boom",
        "completionSignal": "exit",
        "logFilePath": "/tmp/log",
        "preservedWorktreePath": None,
        "iterations": 1,
    }
    data.update(overrides)
    return data


def _container(
    task_id: str | None = "t1", *, running: bool = False, container_id: str = "c1"
) -> ContainerInfo:
    return ContainerInfo(
        container_id=container_id, task_id=task_id, run_id="run-1", running=running
    )


class TestDecideNoop:
    def test_healthy_running_row_no_result_no_container_is_noop(self) -> None:
        row = _row(claimed_at=NOW - timedelta(minutes=5))

        action = decide(row, None, None, NOW, CONFIG, 5)

        assert action.kind == "noop"

    def test_terminal_row_no_result_is_noop(self) -> None:
        row = _row(status="done", claimed_at=NOW - timedelta(hours=10))

        action = decide(row, None, None, NOW, CONFIG, 5)

        assert action.kind == "noop"

    def test_timeout_expired_but_container_running_blocks_destructive(self) -> None:
        row = _row(claimed_at=NOW - timedelta(hours=5))
        container = _container(running=True)

        action = decide(row, None, container, NOW, CONFIG, 5)

        assert action.kind == "noop"

    def test_min_age_not_elapsed_blocks_destructive_even_if_timeout_expired(self) -> None:
        # run_timeout tiny (3.6s), destructive_min_age huge (60min) — timeout
        # fires almost immediately but the min-age leg of the conjunction
        # still blocks it for a fresh-ish row.
        config = SweeperConfig(
            run_timeout_hours=0.001,
            destructive_min_age_minutes=60,
            daemon_failure_threshold=3,
            docker_call_timeout_seconds=30,
            runtime_root=".sandcastle/runtime",
        )
        row = _row(claimed_at=NOW - timedelta(seconds=10))

        action = decide(row, None, None, NOW, config, 5)

        assert action.kind == "noop"

    def test_invalid_result_file_does_not_satisfy_no_result_file_leg(self) -> None:
        # AC4: an INVALID_RESULT (malformed file present) is NOT "no result
        # file" — it must not trigger destructive_fail even past timeout.
        row = _row(claimed_at=NOW - timedelta(hours=5))

        action = decide(row, INVALID_RESULT, None, NOW, CONFIG, 5)

        assert action.kind == "noop"


class TestDecideHarvest:
    def test_success_result_closes_row_done(self) -> None:
        row = _row(claimed_at=NOW - timedelta(minutes=5))
        result = _result(outcome="success")

        action = decide(row, result, None, NOW, CONFIG, 5)

        assert action.kind == "harvest"
        assert action.transition_status == "done"
        assert action.event_type == "task_done"
        assert action.event_payload["task_id"] == "t1"

    def test_failure_result_closes_row_failed(self) -> None:
        row = _row(claimed_at=NOW - timedelta(minutes=5))
        result = _result(outcome="agent_fault")

        action = decide(row, result, None, NOW, CONFIG, 5)

        assert action.kind == "harvest"
        assert action.transition_status == "failed"
        assert action.event_type == "task_failed"

    def test_harvest_removes_running_container_force(self) -> None:
        row = _row(claimed_at=NOW - timedelta(minutes=5))
        result = _result(outcome="success")
        container = _container(running=True)

        action = decide(row, result, container, NOW, CONFIG, 5)

        assert action.remove_container is True
        assert action.remove_force is True
        assert action.container_id == "c1"

    def test_harvest_removes_exited_container_without_force(self) -> None:
        row = _row(claimed_at=NOW - timedelta(minutes=5))
        result = _result(outcome="success")
        container = _container(running=False)

        action = decide(row, result, container, NOW, CONFIG, 5)

        assert action.remove_container is True
        assert action.remove_force is False

    def test_harvest_takes_priority_even_past_timeout(self) -> None:
        row = _row(claimed_at=NOW - timedelta(hours=10))
        result = _result(outcome="success")

        action = decide(row, result, None, NOW, CONFIG, 5)

        assert action.kind == "harvest"

    def test_dedup_key_matches_build_dedup_key_shape(self) -> None:
        row = _row(claimed_at=NOW - timedelta(minutes=5), idempotency_key="t1:r2")
        result = _result(outcome="success", attempt=2)

        action = decide(row, result, None, NOW, CONFIG, 5)

        assert action.event_dedup_key == "task_done:t1:a2"


class TestDecideDestructive:
    def test_timeout_no_result_no_container_fails_row(self) -> None:
        row = _row(claimed_at=NOW - timedelta(hours=5))

        action = decide(row, None, None, NOW, CONFIG, 5)

        assert action.kind == "destructive_fail"
        assert action.transition_status == "failed"
        assert action.event_type == "task_failed"
        assert action.event_payload["exit_confirmed"] is False

    def test_timeout_no_result_container_absent_removal_not_requested(self) -> None:
        row = _row(claimed_at=NOW - timedelta(hours=5))

        action = decide(row, None, None, NOW, CONFIG, 5)

        assert action.remove_container is False

    def test_timeout_no_result_container_exited_removed_without_force(self) -> None:
        row = _row(claimed_at=NOW - timedelta(hours=5))
        container = _container(running=False)

        action = decide(row, None, container, NOW, CONFIG, 5)

        assert action.kind == "destructive_fail"
        assert action.remove_container is True
        assert action.remove_force is False


class TestDecidePoisonPill:
    def test_attempt_at_ceiling_parks_instead_of_fails(self) -> None:
        row = _row(claimed_at=NOW - timedelta(hours=5), idempotency_key="t1:r2")

        action = decide(row, None, None, NOW, CONFIG, 2)

        assert action.kind == "poison_park"
        assert action.transition_status == "parked"
        assert action.event_type == "task_poisoned"

    def test_attempt_below_ceiling_still_fails(self) -> None:
        row = _row(claimed_at=NOW - timedelta(hours=5), idempotency_key="t1:r2")

        action = decide(row, None, None, NOW, CONFIG, 5)

        assert action.kind == "destructive_fail"


class TestDecideLateResult:
    def test_valid_result_on_terminal_row_emits_info_event_no_transition(self) -> None:
        row = _row(status="done", claimed_at=NOW - timedelta(hours=10))
        result = _result(outcome="success")

        action = decide(row, result, None, NOW, CONFIG, 5)

        assert action.kind == "late_result"
        assert action.transition_status is None
        assert action.event_type == "sweeper_late_result"
        assert action.event_severity == "info"

    def test_late_result_removes_running_container_force(self) -> None:
        row = _row(status="failed", claimed_at=NOW - timedelta(hours=10))
        result = _result(outcome="success")
        container = _container(running=True)

        action = decide(row, result, container, NOW, CONFIG, 5)

        assert action.remove_container is True
        assert action.remove_force is True


class TestParseTimestampEdgeCases:
    def test_missing_claimed_at_never_times_out(self) -> None:
        row = _row(claimed_at=None)

        action = decide(row, None, None, NOW, CONFIG, 5)

        assert action.kind == "noop"


# -- sweep() orchestrator -----------------------------------------------------


class FakePort:
    def __init__(
        self,
        *,
        running_rows: list[dict[str, Any]] | None = None,
        rows_by_id: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self._running_rows = list(running_rows or [])
        self._rows_by_id = dict(rows_by_id or {})
        self.transitions: list[tuple[str, str, str | None]] = []

    def list_running(self) -> list[dict[str, Any]]:
        return list(self._running_rows)

    def get_row(self, task_id: str) -> dict[str, Any] | None:
        return self._rows_by_id.get(task_id)

    def transition(
        self, task_id: str, to_status: str, *, reason: str | None = None
    ) -> dict[str, Any]:
        self.transitions.append((task_id, to_status, reason))
        return {"id": task_id, "status": to_status}


def _events_recorder() -> tuple[list[tuple[Any, ...]], Any]:
    calls: list[tuple[Any, ...]] = []

    def emit(
        event_type: str, severity: str, payload: dict[str, Any], *, dedup_key: str | None = None
    ) -> None:
        calls.append((event_type, severity, payload, dedup_key))

    return calls, emit


class TestSweepDockerFailure:
    def test_adapter_failure_aborts_pass_untouched(self) -> None:
        port = FakePort(running_rows=[_row(claimed_at=NOW - timedelta(hours=10))])
        docker = FakeDocker(fail=True)
        events, emit = _events_recorder()

        result = sweep(port, docker, config=CONFIG, event_emit=emit, now=lambda: NOW)

        assert result.aborted is True
        assert port.transitions == []

    def test_daemon_unreachable_event_fires_at_threshold(self) -> None:
        port = FakePort(running_rows=[])
        docker = FakeDocker(fail=True)
        events, emit = _events_recorder()
        state = SweeperState()

        for _ in range(3):
            sweep(port, docker, config=CONFIG, event_emit=emit, now=lambda: NOW, state=state)

        daemon_events = [c for c in events if c[0] == "sweeper_daemon_unreachable"]
        assert len(daemon_events) == 1

    def test_counter_resets_after_success(self) -> None:
        port = FakePort(running_rows=[])
        events, emit = _events_recorder()
        state = SweeperState()
        failing_docker = FakeDocker(fail=True)
        sweep(port, failing_docker, config=CONFIG, event_emit=emit, now=lambda: NOW, state=state)
        assert state.consecutive_docker_failures == 1

        healthy_docker = FakeDocker()
        sweep(port, healthy_docker, config=CONFIG, event_emit=emit, now=lambda: NOW, state=state)

        assert state.consecutive_docker_failures == 0


class TestSweepHarvest:
    def test_harvests_running_row_with_valid_result_file(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        row = _row(claimed_at=NOW - timedelta(minutes=5))
        port = FakePort(running_rows=[row])
        docker = FakeDocker()
        events, emit = _events_recorder()
        config = SweeperConfig(
            run_timeout_hours=4,
            destructive_min_age_minutes=10,
            daemon_failure_threshold=3,
            docker_call_timeout_seconds=30,
            runtime_root=str(tmp_path),
        )
        result_dir = tmp_path / "t1-a1"
        result_dir.mkdir()
        (result_dir / "result.json").write_text(
            __import__("json").dumps(_result(outcome="success")), encoding="utf-8"
        )

        outcome = sweep(port, docker, config=config, event_emit=emit, now=lambda: NOW)

        assert outcome.harvest == 1
        assert port.transitions == [("t1", "done", None)]
        assert any(c[0] == "task_done" for c in events)


class TestSweepLateResultCorrelation:
    def test_container_for_terminal_row_triggers_late_result_check(self, tmp_path: Any) -> None:
        terminal_row = _row(status="done", claimed_at=NOW - timedelta(hours=10))
        port = FakePort(running_rows=[], rows_by_id={"t1": terminal_row})
        container = _container(task_id="t1", running=False, container_id="sandcastle-c1")
        docker = FakeDocker(containers=[container])
        events, emit = _events_recorder()
        config = SweeperConfig(
            run_timeout_hours=4,
            destructive_min_age_minutes=10,
            daemon_failure_threshold=3,
            docker_call_timeout_seconds=30,
            runtime_root=str(tmp_path),
        )
        result_dir = tmp_path / "t1-a1"
        result_dir.mkdir()
        (result_dir / "result.json").write_text(
            __import__("json").dumps(_result(outcome="success")), encoding="utf-8"
        )

        outcome = sweep(port, docker, config=config, event_emit=emit, now=lambda: NOW)

        assert outcome.late_result == 1
        assert port.transitions == []
        assert any(c[0] == "sweeper_late_result" for c in events)

    def test_container_for_unknown_task_id_is_skipped(self) -> None:
        port = FakePort(running_rows=[], rows_by_id={})
        container = _container(task_id="ghost", running=False, container_id="sandcastle-c2")
        docker = FakeDocker(containers=[container])
        events, emit = _events_recorder()

        outcome = sweep(port, docker, config=CONFIG, event_emit=emit, now=lambda: NOW)

        assert outcome.noop == 0
        assert outcome.late_result == 0
        assert port.transitions == []


class TestApplyActionIsolation:
    def test_emit_failure_does_not_block_transition(self) -> None:
        port = FakePort()
        docker = FakeDocker()

        def failing_emit(*args: Any, **kwargs: Any) -> None:
            raise RuntimeError("emit boom")

        from agents.task_sweeper import SweepAction

        action = SweepAction(
            kind="destructive_fail",
            transition_status="failed",
            transition_reason="timeout",
            event_type="task_failed",
            event_payload={},
            event_dedup_key="task_failed:t1:a1",
        )

        _apply_action("t1", action, port=port, docker=docker, event_emit=failing_emit)

        assert port.transitions == [("t1", "failed", "timeout")]

    def test_transition_failure_does_not_raise(self) -> None:
        docker = FakeDocker()

        class RaisingPort(FakePort):
            def transition(
                self, task_id: str, to_status: str, *, reason: str | None = None
            ) -> dict[str, Any]:
                raise RuntimeError("db boom")

        from agents.task_sweeper import SweepAction

        action = SweepAction(kind="destructive_fail", transition_status="failed")

        _apply_action(
            "t1", action, port=RaisingPort(), docker=docker, event_emit=None
        )  # must not raise


class TestDockerAdapterIsolation:
    def test_no_subprocess_or_docker_calls_outside_adapter(self) -> None:
        for fn in (decide, sweep, _apply_action):
            source = inspect.getsource(fn)
            assert "subprocess" not in source
            assert "docker.run" not in source

    def test_subprocess_docker_constructs(self) -> None:
        adapter = SubprocessDocker(timeout_seconds=30)
        assert adapter._timeout == 30

    def test_inspect_carries_no_env_key_other_than_task_and_run_id(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """AC12: ``--format`` narrows docker's raw env to the two identity vars;
        ``ContainerInfo`` must never surface anything else even when the real
        container env carries extra, unrelated keys (PATH, HOME, secrets, ...).
        """
        import dataclasses
        import subprocess as subprocess_module

        raw_env = [
            "PATH=/usr/bin",
            "SANDCASTLE_TASK_ID=t1",
            "SOME_SECRET=shh",
            "SANDCASTLE_RUN_ID=r1",
            "HOME=/root",
        ]
        stdout = "true\t" + __import__("json").dumps(raw_env)

        def fake_run(cmd: list[str], **kwargs: Any) -> Any:
            return subprocess_module.CompletedProcess(cmd, 0, stdout=stdout, stderr="")

        monkeypatch.setattr(subprocess_module, "run", fake_run)

        adapter = SubprocessDocker(timeout_seconds=30)
        info = adapter.inspect("c1")

        assert info.task_id == "t1"
        assert info.run_id == "r1"
        assert {f.name for f in dataclasses.fields(info)} == {
            "container_id",
            "task_id",
            "run_id",
            "running",
        }
        for stray in ("PATH", "SOME_SECRET", "HOME", "/usr/bin", "shh", "/root"):
            assert stray not in vars(info).values()

    def test_docker_call_error_is_exception(self) -> None:
        assert issubclass(DockerCallError, RuntimeError)
