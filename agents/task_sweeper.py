"""``agents/task_sweeper.py`` — the primary closer of ``running`` rows (#1122 S5).

Two independent clocks, decided per-row by the pure :func:`decide`:

- **Harvest** — a valid schema-v2 result file closes the row immediately,
  no grace period.
- **Destructive** — failing a row with no result file (or removing its
  container) needs the conjunction *timeout expired ∧ no result file ∧
  correlated container absent or not running*, gated further by
  ``destructive_min_age_minutes``.

Identity: rows are correlated to containers purely via the
``SANDCASTLE_TASK_ID`` env var the container carries (see
``agents.sandcastle_supervisor.build_supervisor_env`` for the writer side) —
deterministic container *names* are unbuildable on the
``@ai-hero/sandcastle`` pin (library-assigned ``sandcastle-<uuid>``).

All docker access goes through the :class:`DockerAdapter` Protocol
(:class:`SubprocessDocker` for real, :class:`FakeDocker` for tests) — no
``subprocess``/docker call exists anywhere else in this module.
"""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Protocol, runtime_checkable

from agents.sandcastle_config import SweeperConfig, default_attempt_ceiling, default_sweeper_config
from agents.sandcastle_result import (
    SandcastleResultError,
    build_completion_payload,
    completion_severity,
    read_result_file,
)
from agents.task_dispatch import EventEmit, TaskQueuePort, build_dedup_key, parse_lineage

logger = logging.getLogger(__name__)

# Library-assigned container names are always "sandcastle-<uuid>" — the only
# stable prefix we can filter on (decision 2adaa6a7: name-based double-spawn
# guard dropped, but the prefix itself is still how we find OUR containers
# among whatever else docker is running).
_CONTAINER_NAME_PREFIX = "sandcastle-"

# Sentinel: a result file is present on disk but failed schema-v2 validation.
# Distinct from ``None`` (no file at all) — AC4 treats the two differently:
# both count as "not harvestable", but only ``None`` satisfies the
# destructive branch's "no result file" leg.
INVALID_RESULT: object = object()


# -- Docker adapter (AC12) ----------------------------------------------------


@dataclass(frozen=True)
class ContainerInfo:
    """Only the two identity env vars + running state — never the full env."""

    container_id: str
    task_id: str | None
    run_id: str | None
    running: bool


class DockerCallError(RuntimeError):
    """A docker adapter call failed (timeout or non-zero exit) — AC6."""


@runtime_checkable
class DockerAdapter(Protocol):
    def list_by_name_prefix(self, prefix: str) -> list[str]:
        """List container IDs whose name starts with ``prefix`` (``-a``, includes exited)."""

    def inspect(self, container_id: str) -> ContainerInfo:
        """Correlation + liveness for one container. Raises :class:`DockerCallError` on failure."""

    def remove(self, container_id: str, *, force: bool) -> None:
        """``docker rm`` (``force`` → ``-f``). Raises :class:`DockerCallError` on failure."""


class SubprocessDocker:
    """Real adapter — shells out to the docker CLI with a bounded timeout (AC6/AC12)."""

    def __init__(self, *, timeout_seconds: float) -> None:
        self._timeout = timeout_seconds

    def list_by_name_prefix(self, prefix: str) -> list[str]:
        out = self._run(
            ["docker", "ps", "-a", "--filter", f"name=^{prefix}", "--format", "{{.ID}}"]
        )
        return [line for line in out.splitlines() if line.strip()]

    def inspect(self, container_id: str) -> ContainerInfo:
        # --format scoped to exactly what we need: running state + the raw
        # env (parsed and discarded below — it never leaves this function,
        # so ContainerInfo can never carry a stray env key).
        out = self._run(
            [
                "docker",
                "inspect",
                "--format",
                "{{.State.Running}}\t{{json .Config.Env}}",
                container_id,
            ]
        )
        running_field, _, env_json = out.partition("\t")
        raw_env = json.loads(env_json) if env_json.strip() else []
        task_id: str | None = None
        run_id: str | None = None
        for entry in raw_env:
            key, _, value = str(entry).partition("=")
            if key == "SANDCASTLE_TASK_ID":
                task_id = value
            elif key == "SANDCASTLE_RUN_ID":
                run_id = value
        return ContainerInfo(
            container_id=container_id,
            task_id=task_id,
            run_id=run_id,
            running=running_field.strip() == "true",
        )

    def remove(self, container_id: str, *, force: bool) -> None:
        cmd = ["docker", "rm"]
        if force:
            cmd.append("-f")
        cmd.append(container_id)
        self._run(cmd)

    def _run(self, cmd: list[str]) -> str:
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=self._timeout, check=False
            )
        except subprocess.TimeoutExpired as exc:
            raise DockerCallError(f"docker call timed out: {' '.join(cmd)}") from exc
        if proc.returncode != 0:
            raise DockerCallError(
                f"docker call failed (rc={proc.returncode}): {' '.join(cmd)}: {proc.stderr.strip()}"
            )
        return proc.stdout


@dataclass
class FakeDocker:
    """Test double — pre-seeded containers + a call journal for assertions."""

    containers: list[ContainerInfo] = field(default_factory=list)
    fail: bool = False
    calls: list[tuple[Any, ...]] = field(default_factory=list)

    def list_by_name_prefix(self, prefix: str) -> list[str]:
        self.calls.append(("list_by_name_prefix", prefix))
        if self.fail:
            raise DockerCallError("FakeDocker: forced failure")
        return [c.container_id for c in self.containers if c.container_id.startswith(prefix)]

    def inspect(self, container_id: str) -> ContainerInfo:
        self.calls.append(("inspect", container_id))
        if self.fail:
            raise DockerCallError("FakeDocker: forced failure")
        for c in self.containers:
            if c.container_id == container_id:
                return c
        raise DockerCallError(f"FakeDocker: no such container {container_id!r}")

    def remove(self, container_id: str, *, force: bool) -> None:
        self.calls.append(("remove", container_id, force))
        if self.fail:
            raise DockerCallError("FakeDocker: forced failure")
        self.containers = [c for c in self.containers if c.container_id != container_id]


# -- Pure decision (AC1) ------------------------------------------------------


@dataclass(frozen=True)
class SweepAction:
    """What :func:`decide` wants done for one row — applied by :func:`sweep`."""

    kind: str  # "noop" | "harvest" | "destructive_fail" | "poison_park" | "late_result"
    transition_status: str | None = None
    transition_reason: str | None = None
    event_type: str | None = None
    event_severity: str | None = None
    event_payload: dict[str, Any] | None = None
    event_dedup_key: str | None = None
    remove_container: bool = False
    remove_force: bool = False
    container_id: str | None = None


def _parse_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def decide(
    row: dict[str, Any],
    result: dict[str, Any] | None | object,
    container: ContainerInfo | None,
    now: datetime,
    config: SweeperConfig,
    ceiling: int,
) -> SweepAction:
    """Pure per-row decision — no docker, no network, no I/O.

    ``result`` is one of: a validated result-file dict (harvestable), ``None``
    (no file at all), or :data:`INVALID_RESULT` (a malformed file is present
    — counts as "not harvestable" but NOT as "no result file" for AC4).

    ``ceiling`` is ``attempt_ceiling()`` over the *full* slot-ladder config
    (``agents.sandcastle_config.attempt_ceiling`` takes a ``SandcastleConfig``
    with a ``slots`` tuple — ``SweeperConfig`` alone carries no slot info, so
    the caller resolves the ceiling once and passes the int in, per decision
    9f357110 (ceiling derived from ladder length, not hardcoded).
    """
    task_id = row["id"]
    status = row.get("status")
    lineage_key, attempt = parse_lineage(row.get("idempotency_key") or "")
    is_valid_result = isinstance(result, dict)

    # AC7/AC13 — terminal row: idempotent no-op, except a straggling valid
    # result file surfaces as an info event (never a transition, never a
    # completion event — the row already closed through some other path).
    if status != "running":
        if is_valid_result:
            return SweepAction(
                kind="late_result",
                event_type="sweeper_late_result",
                event_severity="info",
                event_payload={
                    "task_id": task_id,
                    "lineage_key": lineage_key,
                    "attempt": attempt,
                    "row_status": status,
                },
                event_dedup_key=build_dedup_key("sweeper_late_result", task_id, attempt),
                remove_container=container is not None,
                remove_force=container is not None and container.running,
                container_id=container.container_id if container is not None else None,
            )
        return SweepAction(kind="noop")

    # AC3 — harvest: valid result file closes the row immediately, no grace.
    if is_valid_result:
        payload = build_completion_payload(result)
        event_type = "task_done" if result["outcome"] == "success" else "task_failed"
        return SweepAction(
            kind="harvest",
            transition_status="done" if event_type == "task_done" else "failed",
            transition_reason=None
            if event_type == "task_done"
            else (payload.get("failure_reason") or "sweeper harvest"),
            event_type=event_type,
            event_severity=completion_severity(event_type, payload.get("pr_evidence")),
            event_payload=payload,
            event_dedup_key=build_dedup_key(event_type, task_id, attempt),
            remove_container=container is not None,
            remove_force=container is not None and container.running,
            container_id=container.container_id if container is not None else None,
        )

    # AC4 — destructive conjunction: timeout expired ∧ no result file (an
    # INVALID_RESULT file does NOT satisfy "no result file") ∧ correlated
    # container absent or not running. A running container blocks this
    # branch unconditionally, regardless of age.
    claimed_at = _parse_timestamp(row.get("claimed_at"))
    timeout_expired = (
        claimed_at is not None
        and (now - claimed_at).total_seconds() >= config.run_timeout_hours * 3600
    )
    min_age_elapsed = (
        claimed_at is not None
        and (now - claimed_at).total_seconds() >= config.destructive_min_age_minutes * 60
    )
    container_running = container is not None and container.running
    no_result_file = result is None

    if timeout_expired and min_age_elapsed and no_result_file and not container_running:
        container_id = container.container_id if container is not None else None
        # AC8 — poison-pill: same conjunction that would otherwise fail the
        # row, but attempt >= ceiling parks it instead (no new column).
        if attempt >= ceiling:
            return SweepAction(
                kind="poison_park",
                transition_status="parked",
                transition_reason="sweeper: attempt ceiling reached",
                event_type="task_poisoned",
                event_severity="medium",
                event_payload={
                    "task_id": task_id,
                    "lineage_key": lineage_key,
                    "attempt": attempt,
                    "goal": row.get("goal"),
                },
                event_dedup_key=build_dedup_key("task_poisoned", task_id, attempt),
                remove_container=container is not None,
                remove_force=False,  # container_running is False here (guard above)
                container_id=container_id,
            )
        return SweepAction(
            kind="destructive_fail",
            transition_status="failed",
            transition_reason="sweeper: timeout expired, no result file, container absent",
            event_type="task_failed",
            event_severity="medium",
            event_payload={
                "task_id": task_id,
                "lineage_key": lineage_key,
                "attempt": attempt,
                "exit_confirmed": False,
                "pr_evidence": None,
                "failure_reason": "sweeper: timeout expired, no result file, container absent",
                "goal": row.get("goal"),
                "target_repo": row.get("target_repo"),
                "target_type": row.get("target_type"),
                "target_number": row.get("target_number"),
                "origin": row.get("origin"),
            },
            event_dedup_key=build_dedup_key("task_failed", task_id, attempt),
            remove_container=container is not None,
            remove_force=False,  # container_running is False here (guard above)
            container_id=container_id,
        )

    return SweepAction(kind="noop")


# -- Orchestrator (AC1, AC6, AC10, AC13) --------------------------------------


@dataclass
class SweeperState:
    """Cross-tick in-memory state — just the AC6 consecutive-failure counter.

    ceiling: in-process only, resets on driver restart. A restart itself
    proves the daemon reachable again on next boot, so this is acceptable;
    if cross-restart persistence is ever needed, derive the count from
    recent ``sweeper_daemon_unreachable`` events instead of adding a column.
    """

    consecutive_docker_failures: int = 0

    # AC7 — consecutive sweep passes containing at least one late-result
    # occurrence (a straggling result on an already-terminal row); mirrors
    # the AC6 shape above: an owner event fires once this crosses
    # ``late_result_drift_threshold``, and it resets on the next clean pass.
    consecutive_late_result_passes: int = 0


@dataclass(frozen=True)
class SweepResult:
    aborted: bool = False
    startup: bool = False
    harvest: int = 0
    destructive_fail: int = 0
    poison_park: int = 0
    late_result: int = 0
    noop: int = 0


def _read_result_for_row(
    row: dict[str, Any], config: SweeperConfig
) -> dict[str, Any] | object | None:
    task_id = row["id"]
    _, attempt = parse_lineage(row.get("idempotency_key") or "")
    path = Path(config.runtime_root) / f"{task_id}-a{attempt}" / "result.json"
    try:
        return read_result_file(path)
    except FileNotFoundError:
        return None
    except SandcastleResultError:
        logger.warning("[task_sweeper] invalid result file for task %s at %s", task_id, path)
        return INVALID_RESULT


def _apply_action(
    task_id: str,
    action: SweepAction,
    *,
    port: TaskQueuePort,
    docker: DockerAdapter,
    event_emit: EventEmit | None,
) -> None:
    if action.kind == "noop":
        return

    # Event-first ordering (mirrors task_dispatch.poll_completions): emit
    # before the transition so a crash in the window self-heals on
    # re-observation via the dedup_key.
    if event_emit and action.event_type:
        try:
            event_emit(
                action.event_type,
                action.event_severity or "medium",
                action.event_payload or {},
                dedup_key=action.event_dedup_key,
            )
        except Exception:  # noqa: BLE001 — emit failure must not block the transition
            logger.exception("[task_sweeper] event emit for task %s failed", task_id)

    if action.transition_status:
        try:
            port.transition(task_id, action.transition_status, reason=action.transition_reason)
        except Exception:  # noqa: BLE001 — isolate one bad row
            logger.exception(
                "[task_sweeper] transition to %s for task %s failed",
                action.transition_status,
                task_id,
            )

    # AC5 — removal happens AFTER the harvest/destructive attempt above,
    # never before. force only when the container was seen running on what
    # is now a terminal row (decide() only ever sets remove_force in that
    # exact case).
    if action.remove_container and action.container_id:
        try:
            docker.remove(action.container_id, force=action.remove_force)
        except Exception:  # noqa: BLE001 — cleanup is best-effort; row already terminal
            logger.exception(
                "[task_sweeper] container remove failed for task %s (container %s)",
                task_id,
                action.container_id,
            )


def sweep(
    port: TaskQueuePort,
    docker: DockerAdapter,
    *,
    config: SweeperConfig | None = None,
    event_emit: EventEmit | None = None,
    now: Callable[[], datetime] | None = None,
    state: SweeperState | None = None,
    startup: bool = False,
    ceiling: int | None = None,
) -> SweepResult:
    """Run one sweep pass — harvest, destructive-fail, poison-pill, late-result.

    AC6: the docker listing/inspection phase runs BEFORE any row is touched;
    any adapter failure aborts the whole pass untouched, bumps the
    consecutive-failure counter (owner event past ``daemon_failure_threshold``),
    and resets on the next successful pass.

    ``ceiling`` defaults to ``default_attempt_ceiling()`` (reads the repo's
    slot ladder) — pass explicitly in tests to avoid coupling to the repo's
    live ``config/sandcastle.yaml`` slot count.
    """
    cfg = config or default_sweeper_config()
    resolved_ceiling = ceiling if ceiling is not None else default_attempt_ceiling()
    clock = now or (lambda: datetime.now(timezone.utc))
    st = state if state is not None else SweeperState()
    moment = clock()

    try:
        container_ids = docker.list_by_name_prefix(_CONTAINER_NAME_PREFIX)
        containers = [docker.inspect(cid) for cid in container_ids]
    except Exception:  # noqa: BLE001 — any adapter failure aborts the pass, untouched
        logger.exception("[task_sweeper] docker adapter failed; aborting pass untouched")
        st.consecutive_docker_failures += 1
        if event_emit and st.consecutive_docker_failures >= cfg.daemon_failure_threshold:
            try:
                event_emit(
                    "sweeper_daemon_unreachable",
                    "high",
                    {"consecutive_failures": st.consecutive_docker_failures},
                    dedup_key=f"sweeper_daemon_unreachable:{moment.date().isoformat()}",
                )
            except Exception:  # noqa: BLE001 — emit failure must not raise
                logger.exception("[task_sweeper] daemon-unreachable event emit failed")
        return SweepResult(aborted=True, startup=startup)
    st.consecutive_docker_failures = 0

    by_task_id: dict[str, ContainerInfo] = {c.task_id: c for c in containers if c.task_id}

    running_rows = port.list_running()
    running_ids = {row["id"] for row in running_rows}

    rows_to_check: list[dict[str, Any]] = list(running_rows)
    # AC7 — a container correlated to a task_id NOT among the running rows is
    # either unrelated (task_id absent in our queue — get_row returns None,
    # skip) or a straggler on an already-terminal row; either way decide()
    # needs the row to know which.
    for task_id, container in by_task_id.items():
        if task_id in running_ids:
            continue
        row = port.get_row(task_id)
        if row is not None and row.get("status") != "running":
            rows_to_check.append(row)

    counts = {"harvest": 0, "destructive_fail": 0, "poison_park": 0, "late_result": 0, "noop": 0}
    for row in rows_to_check:
        task_id = row["id"]
        container = by_task_id.get(task_id)
        result = _read_result_for_row(row, cfg)
        action = decide(row, result, container, moment, cfg, resolved_ceiling)
        _apply_action(task_id, action, port=port, docker=docker, event_emit=event_emit)
        counts[action.kind] = counts.get(action.kind, 0) + 1

    # AC7 — drift counter: a late-result occurrence is expected occasionally
    # (a straggling completion racing the sweeper), but repeated occurrences
    # across consecutive passes indicate a correlation/timing problem an
    # owner should look at, mirroring the AC6 daemon-failure pattern above.
    if counts["late_result"] > 0:
        st.consecutive_late_result_passes += 1
        if event_emit and st.consecutive_late_result_passes >= cfg.late_result_drift_threshold:
            try:
                event_emit(
                    "sweeper_late_result_drift",
                    "medium",
                    {"consecutive_passes": st.consecutive_late_result_passes},
                    dedup_key=f"sweeper_late_result_drift:{moment.date().isoformat()}",
                )
            except Exception:  # noqa: BLE001 — emit failure must not raise
                logger.exception("[task_sweeper] late-result-drift event emit failed")
    else:
        st.consecutive_late_result_passes = 0

    return SweepResult(aborted=False, startup=startup, **counts)
