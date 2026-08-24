"""Unit tests for agents/task_dispatch.py — the #909 task-dispatch loop.

The whole point of AC10 is that the dispatch logic is a pure function over a
``TaskQueuePort`` Protocol plus an injected ``spawn`` callable, so every test
here runs against an in-memory fake — no Supabase client, no real ``claude``
binary. The one exception is the AC8 billing-trap test, which drives the *real*
``executor.spawn`` through the drain path (with an injected ``Popen``) to prove
the env-sanitization safety property survives integration.

Each test names the acceptance criterion it covers (see issue #909, grilled
2026-06-01, decision 2489782f).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from datetime import UTC, datetime, timedelta
from typing import Any

from agents.driver_heartbeat import HeartbeatStatus
from agents.task_dispatch import (
    DEFAULT_ASSIGNEE,
    LOCAL_DRAIN_DRIVER_NAME,
    DrainResult,
    SupabaseTaskQueue,
    TaskQueuePort,
    TrackedProc,
    _resolve_concurrency_cap,
    default_get_task_statuses,
    default_local_drain_heartbeat_check,
    default_local_drain_once,
    default_spawn,
    drain_tasks,
    kill_runaways,
    local_drain_until_terminal,
    poll_completions,
    reclaim_stale_tasks,
)
from agents.task_worktree import sweep_task_worktrees


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


def _row(task_id: str, *, assignee: str = "sandcastle", goal: str | None = None) -> dict[str, Any]:
    return {
        "id": task_id,
        "goal": goal or f"do {task_id}",
        "assignee": assignee,
        "status": "pending",
    }


class FakeTaskQueue:
    """In-memory ``TaskQueuePort`` for driving ``drain_tasks`` deterministically.

    ``claim_next`` hands out seeded pending rows FIFO, filtered by assignee —
    mirroring the real SELECT filter so a non-matching row is never claimed.
    """

    def __init__(
        self,
        *,
        pending: list[dict[str, Any]] | None = None,
        running_count: int = 0,
        statuses: dict[str, str] | None = None,
    ) -> None:
        self._pending = list(pending or [])
        self._running_count = running_count
        self.claimed: list[str] = []
        self.transitions: list[tuple[str, str, str | None]] = []
        self.reclaimed_count = 0
        self.stale_running: list[dict[str, Any]] = []
        self.requeued: list[str] = []
        self.statuses: dict[str, str] = dict(statuses or {})
        self.plan_digests: dict[str, str] = {}

    def claim_next(self, *, assignee: str) -> dict[str, Any] | None:
        for i, row in enumerate(self._pending):
            if row.get("assignee") == assignee:
                claimed = self._pending.pop(i)
                self.claimed.append(claimed["id"])
                return claimed
        return None

    def count_running(self, *, assignee: str) -> int:
        return self._running_count

    def transition(
        self, task_id: str, to_status: str, *, reason: str | None = None
    ) -> dict[str, Any]:
        self.transitions.append((task_id, to_status, reason))
        return {"id": task_id, "status": to_status}

    def reclaim_stale_claimed(self, *, assignee: str, older_than_seconds: float) -> int:
        return self.reclaimed_count

    def list_stale_running(
        self, *, assignee: str, older_than_seconds: float
    ) -> list[dict[str, Any]]:
        return list(self.stale_running)

    def requeue_running(self, task_id: str) -> bool:
        self.requeued.append(task_id)
        return True

    def get_status(self, task_id: str) -> str | None:
        return self.statuses.get(task_id)

    def set_plan_digest(self, task_id: str, digest: str) -> dict[str, Any]:
        self.plan_digests[task_id] = digest
        return {"id": task_id, "plan_digest": digest}


def _always_resolve() -> str:
    return "claude"


class _FakeProc:
    """Minimal ``Popen``-shaped handle: ``poll()`` returns the scripted rc."""

    def __init__(self, rc: int | None = None, pid: int = 4242) -> None:
        self._rc = rc
        self.pid = pid
        self.killed = False
        self.waited = False

    def poll(self) -> int | None:
        return self._rc

    def kill(self) -> None:
        self.killed = True
        self._rc = -9

    def wait(self, timeout: float | None = None) -> int | None:
        self.waited = True
        return self._rc


class _AdoptedProc:
    """``psutil.Process``-shaped handle as folded in by boot adoption (#952).

    Deliberately exposes ONLY ``is_running()`` — NO ``poll()``, NO
    ``returncode`` — exactly like a real ``psutil.Process``. This is the handle
    kind that wedged ``running`` rows before the poll_exit fix: a bare
    ``.poll()`` in poll_completions/kill_runaways AttributeErrors on it.
    """

    def __init__(self, *, running: bool, pid: int = 4242) -> None:
        self._running = running
        self.pid = pid

    def is_running(self) -> bool:
        return self._running


class _ThrottledResult:
    """Stand-in for ``executor.SpawnResult`` when quota is near-exhaustion.

    No process was launched (``proc=None``); the ``throttled`` flag is the
    signal :func:`drain_tasks` must honor instead of counting a spawn.
    """

    proc = None
    throttled = True
    reason = "quota near-exhaustion"


class _FixedProbe:
    def __init__(self, reading: Any) -> None:
        self._reading = reading

    def read(self) -> Any:
        return self._reading


def _healthy_reading() -> Any:
    from agents.usage_probe import UsageReading

    return UsageReading(
        limit_window=timedelta(hours=5),
        used=10,
        total=100,
        reset_at=datetime.now(UTC),
        near_exhaustion=False,
    )


def _exhausted_reading() -> Any:
    from agents.usage_probe import UsageReading

    return UsageReading(
        limit_window=timedelta(hours=5),
        used=100,
        total=100,
        reset_at=datetime.now(UTC),
        near_exhaustion=True,
    )


def _healthy_usage() -> Any:
    """Injectable stand-in for ``read_usage`` — plenty of headroom."""
    return _healthy_reading()


# ---------------------------------------------------------------------------
# AC3 — concurrency cap: budget = cap − count_running, sampled once
# ---------------------------------------------------------------------------


class TestConcurrencyCap:
    def test_budget_limits_spawns(self) -> None:
        # 3 already running, cap 5 -> budget 2 -> only 2 of 4 pending spawned.
        q = FakeTaskQueue(pending=[_row(f"t{i}") for i in range(4)], running_count=3)
        spawns: list[str] = []
        res = drain_tasks(
            q,
            lambda g, task_id=None: spawns.append(g),  # AC3 #953 — spawn now accepts task_id
            cap=5,
            resolve_binary=_always_resolve,
            read_usage=_healthy_usage,
        )
        assert len(spawns) == 2
        assert len(q.claimed) == 2
        assert res.spawned == 2

    def test_no_spawn_when_at_cap(self) -> None:
        q = FakeTaskQueue(pending=[_row("t0")], running_count=5)
        spawns: list[str] = []
        res = drain_tasks(
            q,
            lambda g, task_id=None: spawns.append(g),
            cap=5,
            resolve_binary=_always_resolve,
            read_usage=_healthy_usage,
        )
        assert spawns == []
        assert q.claimed == []
        assert res.spawned == 0

    def test_resolve_concurrency_cap_reads_env_var(self, monkeypatch: Any) -> None:
        """AC8 (#1390): REACTIVE_CONCURRENCY_CAP overrides the module default so
        register-wake-driver.ps1 can pin autonomous runs to a lower cap (2)."""
        monkeypatch.setenv("REACTIVE_CONCURRENCY_CAP", "2")
        assert _resolve_concurrency_cap() == 2

    def test_resolve_concurrency_cap_defaults_to_five_when_unset(self, monkeypatch: Any) -> None:
        monkeypatch.delenv("REACTIVE_CONCURRENCY_CAP", raising=False)
        assert _resolve_concurrency_cap() == 5


# ---------------------------------------------------------------------------
# AC2 — assignee routing: only 'sandcastle' claimed; 'owner' never spawned
# ---------------------------------------------------------------------------


class TestAssigneeRouting:
    def test_owner_rows_never_claimed(self) -> None:
        q = FakeTaskQueue(
            pending=[_row("own", assignee="owner"), _row("sand", assignee="sandcastle")],
            running_count=0,
        )
        spawns: list[str] = []
        drain_tasks(
            q,
            lambda g, task_id=None: spawns.append(g),
            resolve_binary=_always_resolve,
            read_usage=_healthy_usage,
        )
        assert q.claimed == ["sand"]
        assert spawns == ["do sand"]

    def test_default_assignee_is_sandcastle(self) -> None:
        assert DEFAULT_ASSIGNEE == "sandcastle"


# ---------------------------------------------------------------------------
# AC4 — Ordering B: claim → transition(running) → spawn
# ---------------------------------------------------------------------------


class TestOrderingB:
    def test_transition_running_before_spawn(self) -> None:
        events: list[tuple[str, ...]] = []
        q = FakeTaskQueue(pending=[_row("t0")], running_count=0)

        original = q.transition

        def recording_transition(task_id: str, to_status: str, *, reason: str | None = None) -> Any:
            events.append(("transition", task_id, to_status))
            return original(task_id, to_status, reason=reason)

        q.transition = recording_transition  # type: ignore[method-assign]

        drain_tasks(
            q,
            lambda g, task_id=None: events.append(("spawn", g)),
            resolve_binary=_always_resolve,
            read_usage=_healthy_usage,
        )

        # The running transition must be recorded BEFORE the spawn — a row is
        # never left 'claimed' once we have committed to spawning it, and spawn
        # is never invoked for a row still 'pending'/'claimed'.
        assert events == [("transition", "t0", "running"), ("spawn", "do t0")]


# ---------------------------------------------------------------------------
# AC9 — atomic claim: lost race returns None -> no spawn, no phantom work
# ---------------------------------------------------------------------------


class TestAtomicClaim:
    def test_empty_queue_no_spawn(self) -> None:
        q = FakeTaskQueue(pending=[], running_count=0)
        spawns: list[str] = []
        res = drain_tasks(
            q,
            lambda g, task_id=None: spawns.append(g),
            resolve_binary=_always_resolve,
            read_usage=_healthy_usage,
        )
        assert spawns == []
        assert res.spawned == 0

    def test_none_claim_stops_drain_no_phantom_spawn(self) -> None:
        # Budget allows 5 but a competing drainer left only one claimable row;
        # subsequent claims return None and the loop stops cleanly without
        # spawning for an unclaimed row (the optimistic-lock atomicity that
        # makes the lost race safe is unit-tested in test_agents_task_queue).
        q = FakeTaskQueue(pending=[_row("only")], running_count=0)
        spawns: list[str] = []
        res = drain_tasks(
            q,
            lambda g, task_id=None: spawns.append(g),
            cap=5,
            resolve_binary=_always_resolve,
            read_usage=_healthy_usage,
        )
        assert spawns == ["do only"]
        assert res.spawned == 1


# ---------------------------------------------------------------------------
# AC7a — binary unresolved: skip whole drain, zero claims, self-heals
# ---------------------------------------------------------------------------


class TestBinaryPreflight:
    def test_unresolved_binary_skips_entire_drain(self) -> None:
        q = FakeTaskQueue(pending=[_row("t0"), _row("t1")], running_count=0)
        spawns: list[str] = []

        def resolve_missing() -> str:
            raise FileNotFoundError("claude binary not found")

        res = drain_tasks(
            q, lambda g, task_id=None: spawns.append(g), resolve_binary=resolve_missing
        )

        assert q.claimed == []  # zero claims — no row touched
        assert spawns == []
        assert res.skipped_no_binary is True
        assert res.spawned == 0
        assert len(q._pending) == 2  # rows stay pending -> next drain self-heals

    def test_permissionerror_in_resolve_also_skips_drain(self) -> None:
        # A binary that exists but is not executable means "cannot spawn" just
        # as much as a missing one — skip the whole drain, claim nothing.
        q = FakeTaskQueue(pending=[_row("t0")], running_count=0)
        spawns: list[str] = []

        def resolve_denied() -> str:
            raise PermissionError("claude is not executable")

        res = drain_tasks(
            q, lambda g, task_id=None: spawns.append(g), resolve_binary=resolve_denied
        )

        assert res.skipped_no_binary is True
        assert q.claimed == []
        assert spawns == []

    def test_importerror_in_resolve_also_skips_drain(self) -> None:
        # A broken executor import surfaces as ImportError from the lazy
        # default resolver — still "cannot spawn", so skip not strand.
        q = FakeTaskQueue(pending=[_row("t0")], running_count=0)

        def resolve_broken() -> str:
            raise ImportError("executor dependency missing")

        res = drain_tasks(q, lambda g, task_id=None: None, resolve_binary=resolve_broken)

        assert res.skipped_no_binary is True
        assert q.claimed == []


# ---------------------------------------------------------------------------
# #921 AC4 — quota pre-flight: near-exhaustion skips the entire drain
# ---------------------------------------------------------------------------


class TestQuotaPreflight:
    def test_near_exhaustion_skips_entire_drain(self) -> None:
        # Zero claims, zero churn — rows stay visibly pending. The false-safe
        # probe contract means a broken probe also lands here.
        q = FakeTaskQueue(pending=[_row("t0"), _row("t1")], running_count=0)
        spawns: list[str] = []
        res = drain_tasks(
            q,
            lambda g, task_id=None: spawns.append(g),
            resolve_binary=_always_resolve,
            read_usage=_exhausted_reading,
        )
        assert q.claimed == []
        assert spawns == []
        assert res.throttled is True
        assert res.spawned == 0
        assert len(q._pending) == 2

    def test_consulted_once_at_drain_start(self) -> None:
        # One probe per drain, not one per task — mirrors the binary pre-flight.
        calls = {"n": 0}

        def usage() -> Any:
            calls["n"] += 1
            return _healthy_reading()

        q = FakeTaskQueue(pending=[_row(f"t{i}") for i in range(3)], running_count=0)
        res = drain_tasks(
            q, lambda g, task_id=None: None, cap=5, resolve_binary=_always_resolve, read_usage=usage
        )
        assert calls["n"] == 1
        assert res.spawned == 3


# ---------------------------------------------------------------------------
# AC7b — spawn raises: mark that task failed (terminal), continue the drain
# ---------------------------------------------------------------------------


class TestSpawnFailureIsTerminal:
    def test_spawn_raise_marks_failed_and_continues(self) -> None:
        q = FakeTaskQueue(pending=[_row("boom"), _row("ok")], running_count=0)
        spawns: list[str] = []

        def spawn(goal: str, task_id: str | None = None) -> None:
            if goal == "do boom":
                raise RuntimeError("spawn blew up")
            spawns.append(goal)

        res = drain_tasks(
            q, spawn, cap=5, resolve_binary=_always_resolve, read_usage=_healthy_usage
        )

        failed = [t for t in q.transitions if t[1] == "failed"]
        assert len(failed) == 1
        assert failed[0][0] == "boom"
        assert failed[0][2] and "spawn" in failed[0][2]  # reason documents the cause
        # 'boom' was transitioned running THEN failed (no retry); 'ok' spawned.
        assert ("boom", "running", None) in q.transitions
        assert spawns == ["do ok"]
        assert res.spawned == 1
        assert res.failed == 1

    def test_failed_mark_raise_does_not_abort_drain(self) -> None:
        # review #957-1 (MAJOR): the AC7b failure-marking itself can raise
        # (store outage). That must not escape drain_tasks — an escape discards
        # DrainResult.procs for already-spawned tasks, orphaning live children
        # onto the 6h reaper instead of next-tick completion polling.
        class Q(FakeTaskQueue):
            def transition(
                self, task_id: str, to_status: str, *, reason: str | None = None
            ) -> dict[str, Any]:
                if to_status == "failed":
                    raise RuntimeError("store outage")
                return super().transition(task_id, to_status, reason=reason)

        handle = object()
        q = Q(pending=[_row("boom"), _row("ok")], running_count=0)

        def spawn(goal: str, task_id: str | None = None) -> Any:
            if goal == "do boom":
                raise RuntimeError("spawn blew up")
            return _HealthySpawnResult(handle)

        res = drain_tasks(
            q, spawn, cap=5, resolve_binary=_always_resolve, read_usage=_healthy_usage
        )

        assert res.failed == 1  # still counted despite the failed-mark raising
        assert res.spawned == 1  # the drain continued past the bad row
        assert res.procs == (("ok", handle),)  # spawned handle survives for tracking


# ---------------------------------------------------------------------------
# review #2 — throttled spawn (quota near-exhaustion) is not a spawn
# ---------------------------------------------------------------------------


class TestThrottledSpawn:
    def test_throttle_stops_drain_without_miscounting(self) -> None:
        # Quota near-exhaustion: executor.spawn returns throttled=True, proc=None
        # — no process launched. The pre-fix bug counted this as `spawned` and
        # drained the WHOLE budget into 'running' rows, orphaning every one for
        # the 6h reaper. The drain must instead bail after a single row.
        q = FakeTaskQueue(pending=[_row(f"t{i}") for i in range(4)], running_count=0)
        res = drain_tasks(
            q,
            lambda g, task_id=None: _ThrottledResult(),
            cap=5,
            resolve_binary=_always_resolve,
            read_usage=_healthy_usage,
        )

        assert res.spawned == 0
        assert res.failed == 0
        assert res.throttled is True
        # Exactly one row was claimed+transitioned-running before the drain
        # bailed — bounded blast radius (that row is requeued, #921), not the cap.
        assert len(q.claimed) == 1
        assert ("t0", "running", None) in q.transitions
        # A throttle is NOT a spawn failure — the row must not be marked failed.
        assert [t for t in q.transitions if t[1] == "failed"] == []

    def test_throttle_midway_spawns_healthy_then_stops(self) -> None:
        # First task spawns healthily, the second hits the quota wall. The
        # healthy spawn still counts; the drain then stops on the throttle.
        calls = {"n": 0}

        def spawn(goal: str, task_id: str | None = None) -> Any:
            calls["n"] += 1
            return None if calls["n"] == 1 else _ThrottledResult()

        q = FakeTaskQueue(pending=[_row("t0"), _row("t1"), _row("t2")], running_count=0)
        res = drain_tasks(
            q, spawn, cap=5, resolve_binary=_always_resolve, read_usage=_healthy_usage
        )

        assert res.spawned == 1
        assert res.throttled is True
        assert len(q.claimed) == 2  # t0 (spawned) + t1 (throttled, requeued)

    def test_drain_result_has_throttled_field_default_false(self) -> None:
        assert DrainResult().throttled is False


# ---------------------------------------------------------------------------
# #921 AC4 — mid-drain throttle requeues the in-flight running row to pending
# ---------------------------------------------------------------------------


class TestThrottleRequeue:
    def test_midthrottle_requeues_running_row(self) -> None:
        # The throttled row is already `running` (Ordering B) but no process
        # exists — requeue it to `pending` instead of stranding it 6h for the
        # reaper to fail a task that never ran.
        q = FakeTaskQueue(pending=[_row("t0"), _row("t1")], running_count=0)
        res = drain_tasks(
            q,
            lambda g, task_id=None: _ThrottledResult(),
            cap=5,
            resolve_binary=_always_resolve,
            read_usage=_healthy_usage,
        )

        assert res.throttled is True
        assert q.requeued == ["t0"]
        # Requeued ≠ failed — the row must not get a terminal transition.
        assert [t for t in q.transitions if t[1] == "failed"] == []

    def test_requeue_raise_leaves_row_for_reaper(self) -> None:
        # If the requeue UPDATE itself fails, the row stays `running` and the
        # AC5/AC6 reaper is the backstop — the drain must not crash.
        class Q(FakeTaskQueue):
            def requeue_running(self, task_id: str) -> bool:
                raise RuntimeError("supabase transient error")

        q = Q(pending=[_row("t0")], running_count=0)
        res = drain_tasks(
            q,
            lambda g, task_id=None: _ThrottledResult(),
            cap=5,
            resolve_binary=_always_resolve,
            read_usage=_healthy_usage,
        )

        assert res.throttled is True
        assert [t for t in q.transitions if t[1] == "failed"] == []

    def test_requeue_false_is_tolerated(self) -> None:
        # Optimistic-lock miss (row changed under us) → False; same backstop.
        class Q(FakeTaskQueue):
            def requeue_running(self, task_id: str) -> bool:
                return False

        q = Q(pending=[_row("t0")], running_count=0)
        res = drain_tasks(
            q,
            lambda g, task_id=None: _ThrottledResult(),
            cap=5,
            resolve_binary=_always_resolve,
            read_usage=_healthy_usage,
        )

        assert res.throttled is True

    def test_healthy_drain_never_requeues(self) -> None:
        q = FakeTaskQueue(pending=[_row("t0")], running_count=0)
        drain_tasks(
            q,
            lambda g, task_id=None: _HealthySpawnResult(object()),
            resolve_binary=_always_resolve,
            read_usage=_healthy_usage,
        )
        assert q.requeued == []


# ---------------------------------------------------------------------------
# review #5 — a failed running-transition leaves the row claimed (AC5 reclaims)
# ---------------------------------------------------------------------------


class TestRunningTransitionFailureIsSafe:
    def test_transition_running_raise_skips_row_no_spawn(self) -> None:
        spawns: list[str] = []

        class Q(FakeTaskQueue):
            def transition(self, task_id: str, to_status: str, *, reason: str | None = None) -> Any:
                if to_status == "running":
                    raise RuntimeError("supabase transient error")
                return super().transition(task_id, to_status, reason=reason)

        q = Q(pending=[_row("t0")], running_count=0)
        res = drain_tasks(
            q,
            lambda g, task_id=None: spawns.append(g),
            cap=5,
            resolve_binary=_always_resolve,
            read_usage=_healthy_usage,
        )

        # The row was claimed but the running transition failed: never spawned,
        # never marked failed — left 'claimed' for the AC5 reclaimer.
        assert spawns == []
        assert res.spawned == 0
        assert res.failed == 0
        assert [t for t in q.transitions if t[1] == "failed"] == []

    def test_transition_running_raise_continues_to_next_row(self) -> None:
        # A transient transition error on one row must not abort the drain —
        # it skips that row (left claimed) and continues with the next.
        spawns: list[str] = []

        class Q(FakeTaskQueue):
            def transition(self, task_id: str, to_status: str, *, reason: str | None = None) -> Any:
                if to_status == "running" and task_id == "bad":
                    raise RuntimeError("transient")
                return super().transition(task_id, to_status, reason=reason)

        q = Q(pending=[_row("bad"), _row("good")], running_count=0)
        res = drain_tasks(
            q,
            lambda g, task_id=None: spawns.append(g),
            cap=5,
            resolve_binary=_always_resolve,
            read_usage=_healthy_usage,
        )

        assert spawns == ["do good"]
        assert res.spawned == 1


# ---------------------------------------------------------------------------
# AC8 — billing-trap holds through the integrated drain path
# ---------------------------------------------------------------------------


class _CapturedPopen:
    """Records argv + env passed to each Popen instantiation (no real process)."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def __call__(self, argv: list[str], **kwargs: Any) -> Any:
        self.calls.append({"argv": list(argv), "env": dict(kwargs.get("env") or {})})

        class _Handle:
            pid = 4242

            def poll(self) -> None:
                return None

        return _Handle()


class TestBillingTrapThroughDrain:
    def test_api_keys_stripped_from_spawned_env(self, monkeypatch: Any, tmp_path: Any) -> None:
        from agents import executor

        fake_bin = tmp_path / "claude.exe"
        fake_bin.write_text("")

        captured = _CapturedPopen()
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-must-be-stripped")
        monkeypatch.setenv("CLAUDE_API_KEY", "sk-also-stripped")
        monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "tok-stripped")
        monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://metered.example/v1")
        monkeypatch.setenv("CLAUDE_BASE_URL", "https://metered.example/v1")
        monkeypatch.setenv("JARVIS_CLAUDE_BIN", str(fake_bin))
        monkeypatch.setenv("PATH_FROM_PARENT", "keep-me")

        q = FakeTaskQueue(pending=[_row("t0")], running_count=0)

        def spawn(goal: str, task_id: str | None = None) -> Any:
            return executor.spawn(
                goal,
                popen=captured,
                probe=_FixedProbe(_healthy_reading()),
                stderr_log_dir=str(tmp_path),
            )

        drain_tasks(q, spawn, resolve_binary=lambda: str(fake_bin), read_usage=_healthy_usage)

        assert len(captured.calls) == 1
        env = captured.calls[0]["env"]
        assert "ANTHROPIC_API_KEY" not in env, "billing-trap leak through drain path"
        assert "CLAUDE_API_KEY" not in env
        assert "ANTHROPIC_AUTH_TOKEN" not in env
        assert "ANTHROPIC_BASE_URL" not in env, "base-url redirect leak through drain path"
        assert "CLAUDE_BASE_URL" not in env
        assert env.get("PATH_FROM_PARENT") == "keep-me", "non-sensitive env must survive"


# ---------------------------------------------------------------------------
# AC5 — reclaim_stale_tasks: stale claimed -> pending (assignee+threshold scoped)
# ---------------------------------------------------------------------------


class TestReclaimStaleClaimed:
    def test_reclaims_with_assignee_and_threshold(self) -> None:
        calls: dict[str, Any] = {}

        class Q(FakeTaskQueue):
            def reclaim_stale_claimed(self, *, assignee: str, older_than_seconds: float) -> int:
                calls["claimed"] = (assignee, older_than_seconds)
                return 1

            def list_stale_running(self, *, assignee: str, older_than_seconds: float) -> list:
                calls["running"] = (assignee, older_than_seconds)
                return []

        res = reclaim_stale_tasks(
            Q(),
            assignee="sandcastle",
            claimed_stale_after_seconds=300,
            running_reap_after_seconds=21600,
        )
        assert calls["claimed"] == ("sandcastle", 300)
        assert calls["running"] == ("sandcastle", 21600)
        assert res.reclaimed_claimed == 1

    def test_reclaimed_count_propagates(self) -> None:
        q = FakeTaskQueue()
        q.reclaimed_count = 3
        res = reclaim_stale_tasks(q)
        assert res.reclaimed_claimed == 3


# ---------------------------------------------------------------------------
# AC6 — running reaper: stale running -> failed; nothing stale -> no-op
# ---------------------------------------------------------------------------


class TestRunningReaper:
    def test_stale_running_marked_failed(self) -> None:
        q = FakeTaskQueue()
        q.stale_running = [{"id": "stuck1"}, {"id": "stuck2"}]
        res = reclaim_stale_tasks(q, running_reap_after_seconds=21600)
        failed = [t for t in q.transitions if t[1] == "failed"]
        assert {t[0] for t in failed} == {"stuck1", "stuck2"}
        assert all(t[2] and "reaped" in t[2] for t in failed)
        assert res.reaped_running == 2

    def test_noop_when_nothing_stale(self) -> None:
        q = FakeTaskQueue()
        q.stale_running = []
        res = reclaim_stale_tasks(q)
        assert res.reaped_running == 0
        assert q.transitions == []


# ---------------------------------------------------------------------------
# #921 AC5 — reaper is orphan-only: live-tracked rows are never time-reaped
# ---------------------------------------------------------------------------


class TestOrphanOnlyReaper:
    def test_live_rows_not_reaped(self) -> None:
        # A row with a live tracked process is NOT an orphan, however old —
        # long-running tasks are legitimate; runaways are AC6's job (tree-kill),
        # not the time-reaper's.
        q = FakeTaskQueue()
        q.stale_running = [{"id": "live"}, {"id": "orphan"}]
        res = reclaim_stale_tasks(q, live_task_ids={"live"})
        failed = [t for t in q.transitions if t[1] == "failed"]
        assert {t[0] for t in failed} == {"orphan"}
        assert res.reaped_running == 1

    def test_orphan_reason_names_orphan(self) -> None:
        q = FakeTaskQueue()
        q.stale_running = [{"id": "orphan"}]
        reclaim_stale_tasks(q, live_task_ids=set())
        failed = [t for t in q.transitions if t[1] == "failed"]
        assert failed[0][2] and "orphan" in failed[0][2]

    def test_default_live_set_empty_reaps_all_stale(self) -> None:
        # Restart semantics: a fresh driver has no map, so every stale running
        # row is an orphan (AC7 — the in-memory map does not survive restart).
        q = FakeTaskQueue()
        q.stale_running = [{"id": "a"}, {"id": "b"}]
        res = reclaim_stale_tasks(q)
        assert res.reaped_running == 2

    def test_orphan_transition_raise_isolated(self) -> None:
        # review #957-5 (MINOR): one orphan's failed-mark raising must not
        # abort the sweep — the remaining orphans are still reaped this pass
        # (per-row isolation, mirroring poll_completions).
        class Q(FakeTaskQueue):
            def transition(
                self, task_id: str, to_status: str, *, reason: str | None = None
            ) -> dict[str, Any]:
                if task_id == "bad":
                    raise RuntimeError("transient store error")
                return super().transition(task_id, to_status, reason=reason)

        q = Q()
        q.stale_running = [{"id": "bad"}, {"id": "ok"}]
        res = reclaim_stale_tasks(q)
        assert res.reaped_running == 1  # 'bad' raised → not counted
        failed = [t[0] for t in q.transitions if t[1] == "failed"]
        assert failed == ["ok"]  # the sweep continued past the bad row


# ---------------------------------------------------------------------------
# #921 AC1 — DrainResult exposes spawned (task_id, proc) pairs
# ---------------------------------------------------------------------------


class _HealthySpawnResult:
    """Stand-in for ``executor.SpawnResult`` on the healthy path: proc launched."""

    def __init__(self, proc: Any) -> None:
        self.proc = proc
        self.throttled = False
        self.reason = None


class TestSpawnedProcPairs:
    def test_healthy_spawn_contributes_pair(self) -> None:
        handle = object()
        q = FakeTaskQueue(pending=[_row("t0")], running_count=0)
        res = drain_tasks(
            q,
            lambda g, task_id=None: _HealthySpawnResult(handle),
            resolve_binary=_always_resolve,
            read_usage=_healthy_usage,
        )
        assert res.procs == (("t0", handle),)
        assert res.spawned == 1

    def test_multiple_healthy_spawns_pair_in_claim_order(self) -> None:
        handles = {"do t0": object(), "do t1": object()}
        q = FakeTaskQueue(pending=[_row("t0"), _row("t1")], running_count=0)
        res = drain_tasks(
            q,
            lambda g, task_id=None: _HealthySpawnResult(handles[g]),
            cap=5,
            resolve_binary=_always_resolve,
            read_usage=_healthy_usage,
        )
        assert res.procs == (("t0", handles["do t0"]), ("t1", handles["do t1"]))

    def test_throttled_spawn_contributes_no_pair(self) -> None:
        # No process launched — nothing for the driver to poll.
        q = FakeTaskQueue(pending=[_row("t0")], running_count=0)
        res = drain_tasks(
            q,
            lambda g, task_id=None: _ThrottledResult(),
            resolve_binary=_always_resolve,
            read_usage=_healthy_usage,
        )
        assert res.procs == ()

    def test_raising_spawn_contributes_no_pair(self) -> None:
        def spawn(goal: str, task_id: str | None = None) -> Any:
            raise RuntimeError("spawn blew up")

        q = FakeTaskQueue(pending=[_row("t0")], running_count=0)
        res = drain_tasks(q, spawn, resolve_binary=_always_resolve, read_usage=_healthy_usage)
        assert res.procs == ()
        assert res.failed == 1

    def test_procless_spawn_result_contributes_no_pair(self) -> None:
        # A spawn returning None (or result.proc=None) launched nothing the
        # driver can poll — counted as spawned, but no pair.
        q = FakeTaskQueue(pending=[_row("t0")], running_count=0)
        res = drain_tasks(
            q,
            lambda g, task_id=None: None,
            resolve_binary=_always_resolve,
            read_usage=_healthy_usage,
        )
        assert res.procs == ()
        assert res.spawned == 1

    def test_procs_default_empty_tuple(self) -> None:
        assert DrainResult().procs == ()


# ---------------------------------------------------------------------------
# #921 AC2 — poll_completions closes running→done/failed on process exit
# ---------------------------------------------------------------------------


class TestPollCompletions:
    def test_still_running_kept_no_transition(self) -> None:
        q = FakeTaskQueue()
        procs = {"t0": TrackedProc(_FakeProc(rc=None), started_at=0.0)}
        res = poll_completions(q, procs)
        assert res.done == 0
        assert res.failed_exit == 0
        assert "t0" in procs
        assert q.transitions == []

    def test_exit_zero_closes_done_and_drops(self) -> None:
        # Model P: done = the spawned process exited 0 — NOT task success,
        # NOT PR merged. Path-A events carry the actual outcome.
        q = FakeTaskQueue()
        procs = {"t0": TrackedProc(_FakeProc(rc=0), started_at=0.0)}
        res = poll_completions(q, procs)
        assert res.done == 1
        assert ("t0", "done", None) in q.transitions
        assert procs == {}

    def test_nonzero_exit_closes_failed_with_rc_in_reason(self) -> None:
        q = FakeTaskQueue()
        procs = {"t0": TrackedProc(_FakeProc(rc=3), started_at=0.0)}
        res = poll_completions(q, procs)
        assert res.failed_exit == 1
        failed = [t for t in q.transitions if t[1] == "failed"]
        assert len(failed) == 1
        assert failed[0][0] == "t0"
        assert failed[0][2] and "exit 3" in failed[0][2]
        assert procs == {}

    def test_mixed_batch(self) -> None:
        q = FakeTaskQueue()
        procs = {
            "live": TrackedProc(_FakeProc(rc=None), started_at=0.0),
            "ok": TrackedProc(_FakeProc(rc=0), started_at=0.0),
            "boom": TrackedProc(_FakeProc(rc=1), started_at=0.0),
        }
        res = poll_completions(q, procs)
        assert res.done == 1
        assert res.failed_exit == 1
        assert set(procs) == {"live"}

    def test_transition_raise_isolated_drops_entry(self) -> None:
        # One bad row must not block the others. The bad entry is dropped —
        # its row stays `running` and the reaper backstop fails it later.
        class Q(FakeTaskQueue):
            def transition(self, task_id: str, to_status: str, *, reason: str | None = None) -> Any:
                if task_id == "bad":
                    raise RuntimeError("supabase transient error")
                return super().transition(task_id, to_status, reason=reason)

        q = Q()
        procs = {
            "bad": TrackedProc(_FakeProc(rc=0), started_at=0.0),
            "ok": TrackedProc(_FakeProc(rc=0), started_at=0.0),
        }
        res = poll_completions(q, procs)
        assert res.done == 1  # only 'ok' counted
        assert ("ok", "done", None) in q.transitions
        assert procs == {}  # both dropped — 'bad' falls to the reaper backstop


class TestPollCompletionsOutcomeRecord:
    """PR #1539 review finding 2: ``/task-implement`` runs headless with no
    MCP tools, so it can never call ``outcome_record`` itself — without this
    wiring a subagent-dispatched task never gets a ``task_outcomes`` row and
    ``/verify`` Step 2b's divergence audit never sees it.
    """

    def test_done_task_invokes_outcome_record(self) -> None:
        q = FakeTaskQueue()
        procs = {"t0": TrackedProc(_FakeProc(rc=0), started_at=0.0, goal="do t0", issue_number=42)}
        recorded: list[dict[str, Any]] = []
        poll_completions(q, procs, outcome_record=recorded.append)
        assert len(recorded) == 1
        assert recorded[0]["task_id"] == "t0"
        assert recorded[0]["goal"] == "do t0"
        assert recorded[0]["issue_number"] == 42

    def test_failed_task_does_not_invoke_outcome_record(self) -> None:
        q = FakeTaskQueue()
        procs = {"t0": TrackedProc(_FakeProc(rc=1), started_at=0.0, goal="do t0")}
        recorded: list[dict[str, Any]] = []
        poll_completions(q, procs, outcome_record=recorded.append)
        assert recorded == []

    def test_outcome_record_failure_does_not_block_transition(self) -> None:
        # Mirrors event_emit's decoupling (MAJOR, PR #1011): a raise inside
        # outcome_record must never wedge the row out of the ``done`` transition.
        q = FakeTaskQueue()
        procs = {"t0": TrackedProc(_FakeProc(rc=0), started_at=0.0, goal="do t0")}

        def _boom(_payload: dict[str, Any]) -> None:
            raise RuntimeError("supabase transient error")

        res = poll_completions(q, procs, outcome_record=_boom)
        assert res.done == 1
        assert ("t0", "done", None) in q.transitions

    def test_no_outcome_record_wired_is_a_noop(self) -> None:
        # Default (no callback injected) must behave exactly like pre-#1539
        # behavior — no AttributeError, no transition change.
        q = FakeTaskQueue()
        procs = {"t0": TrackedProc(_FakeProc(rc=0), started_at=0.0, goal="do t0")}
        res = poll_completions(q, procs)
        assert res.done == 1


class TestPollCompletionsAdoptedProcess:
    """#952 regression — adopted psutil.Process handles (no poll()) must flow
    through poll_completions, not AttributeError-wedge the row in ``running``.

    Before the poll_exit fix, boot adoption folded raw psutil.Process handles
    into ``procs``; ``tracked.proc.poll()`` raised AttributeError (swallowed by
    the driver's tick guard), so adopted rows NEVER completed, were NEVER
    orphan-reaped (still in live_task_ids), and leaked a cap slot forever —
    strictly worse than the pre-sidecar empty-map self-heal.
    """

    def test_exited_adopted_proc_closes_failed_unknown_exit(self) -> None:
        # AC5: the true exit code of a process we did not spawn is unknowable,
        # so an exited adopted process closes ``failed`` (never ``done``).
        q = FakeTaskQueue()
        procs = {"t0": TrackedProc(_AdoptedProc(running=False), started_at=0.0)}
        res = poll_completions(q, procs)
        assert res.done == 0
        assert res.failed_exit == 1
        failed = [t for t in q.transitions if t[1] == "failed"]
        assert len(failed) == 1 and failed[0][0] == "t0"
        assert procs == {}

    def test_running_adopted_proc_kept_no_transition(self) -> None:
        q = FakeTaskQueue()
        procs = {"t0": TrackedProc(_AdoptedProc(running=True), started_at=0.0)}
        res = poll_completions(q, procs)
        assert res.done == 0 and res.failed_exit == 0
        assert "t0" in procs
        assert q.transitions == []

    def test_runaway_adopted_proc_is_tree_killed(self) -> None:
        # kill_runaways must also tolerate the adopted handle — a still-running
        # adopted process past max runtime is killed, not skipped on a raise.
        q = FakeTaskQueue()
        kills: list[Any] = []
        procs = {"t0": TrackedProc(_AdoptedProc(running=True), started_at=0.0)}
        n = kill_runaways(q, procs, max_runtime_seconds=100, now=lambda: 200.0, kill=kills.append)
        assert n == 1
        assert len(kills) == 1
        failed = [t for t in q.transitions if t[1] == "failed"]
        assert failed and failed[0][0] == "t0"
        assert procs == {}


# ---------------------------------------------------------------------------
# #921 AC6 — runaway live processes are tree-killed and failed
# ---------------------------------------------------------------------------


class TestKillRunaways:
    def test_runaway_killed_failed_and_dropped(self) -> None:
        q = FakeTaskQueue()
        proc = _FakeProc(rc=None)
        kills: list[Any] = []
        procs = {"t0": TrackedProc(proc, started_at=0.0)}
        n = kill_runaways(q, procs, max_runtime_seconds=100, now=lambda: 200.0, kill=kills.append)
        assert n == 1
        assert kills == [proc]
        failed = [t for t in q.transitions if t[1] == "failed"]
        assert failed[0][0] == "t0"
        assert failed[0][2] and "killed" in failed[0][2] and "max runtime" in failed[0][2]
        assert procs == {}

    def test_young_live_proc_untouched(self) -> None:
        q = FakeTaskQueue()
        kills: list[Any] = []
        procs = {"t0": TrackedProc(_FakeProc(rc=None), started_at=0.0)}
        n = kill_runaways(q, procs, max_runtime_seconds=100, now=lambda: 50.0, kill=kills.append)
        assert n == 0
        assert kills == []
        assert "t0" in procs
        assert q.transitions == []

    def test_exited_proc_skipped_for_poll(self) -> None:
        # An already-exited proc is poll_completions' job (rc decides
        # done/failed); killing it would be a no-op and failing it could lie.
        q = FakeTaskQueue()
        kills: list[Any] = []
        procs = {"t0": TrackedProc(_FakeProc(rc=0), started_at=0.0)}
        n = kill_runaways(q, procs, max_runtime_seconds=100, now=lambda: 200.0, kill=kills.append)
        assert n == 0
        assert kills == []
        assert "t0" in procs

    def test_runaway_kill_emits_task_failed(self) -> None:
        # AC1 (#953): a runaway-reaped task is the worst-case stuck class the
        # reconciliation exists to catch — it MUST emit task_failed so the
        # orchestrator can re-drive/escalate. poll_completions emits at its
        # terminal boundary but kill_runaways did not (MAJOR, PR #1011 round-4).
        q = FakeTaskQueue()
        emitted: list[dict[str, Any]] = []

        def emit(
            event_type: str, severity: str, payload: dict[str, Any], *, dedup_key: str | None = None
        ) -> None:
            emitted.append(
                {
                    "event_type": event_type,
                    "severity": severity,
                    "payload": payload,
                    "dedup_key": dedup_key,
                }
            )

        procs = {
            "t0": TrackedProc(
                _FakeProc(rc=None),
                started_at=0.0,
                goal="implement #5",
                idempotency_key="task_done:lin5:r2",
            )
        }
        n = kill_runaways(
            q,
            procs,
            max_runtime_seconds=100,
            now=lambda: 200.0,
            kill=lambda _p: None,
            event_emit=emit,
        )
        assert n == 1
        assert len(emitted) == 1
        ev = emitted[0]
        assert ev["event_type"] == "task_failed"
        assert ev["payload"]["exit_confirmed"] is True
        assert ev["payload"]["pr_evidence"] is None
        assert "killed" in ev["payload"]["failure_reason"]
        # lineage/attempt parsed from the idempotency key (re-drive keying).
        assert ev["payload"]["lineage_key"] == "task_done:lin5"
        assert ev["payload"]["attempt"] == 2
        assert ev["dedup_key"] == "task_failed:t0:a2"

    def test_runaway_kill_emit_failure_does_not_block_transition(self) -> None:
        # Decoupled emit (MAJOR, PR #1011): a raising event_emit must NOT stop
        # the FSM transition — else the killed row wedges in `running` until the
        # 6h reaper, exactly the stall poll_completions' decoupling avoids.
        q = FakeTaskQueue()

        def boom(*_a: Any, **_k: Any) -> None:
            raise RuntimeError("supabase down")

        procs = {"t0": TrackedProc(_FakeProc(rc=None), started_at=0.0)}
        n = kill_runaways(
            q,
            procs,
            max_runtime_seconds=100,
            now=lambda: 200.0,
            kill=lambda _p: None,
            event_emit=boom,
        )
        assert n == 1
        assert {t[0] for t in q.transitions if t[1] == "failed"} == {"t0"}
        assert procs == {}

    def test_runaway_kill_no_emit_when_emitter_absent(self) -> None:
        # With no event_emit wired the #921 behavior is unchanged: kill + fail,
        # no events (the dispatch loop runs eventless until wake_driver wires it).
        q = FakeTaskQueue()
        procs = {"t0": TrackedProc(_FakeProc(rc=None), started_at=0.0)}
        n = kill_runaways(
            q, procs, max_runtime_seconds=100, now=lambda: 200.0, kill=lambda _p: None
        )
        assert n == 1
        assert procs == {}

    def test_kill_raise_isolated_keeps_entry(self) -> None:
        # A failed kill leaves a possibly-alive process — do NOT fail the row
        # (that would lie); keep the entry and retry next tick.
        q = FakeTaskQueue()
        live = _FakeProc(rc=None)
        procs = {
            "bad": TrackedProc(live, started_at=0.0),
            "ok": TrackedProc(_FakeProc(rc=None), started_at=0.0),
        }

        calls = {"n": 0}

        def kill(proc: Any) -> None:
            calls["n"] += 1
            if proc is live:
                raise OSError("taskkill unavailable")

        n = kill_runaways(q, procs, max_runtime_seconds=100, now=lambda: 200.0, kill=kill)
        assert n == 1  # only 'ok' was killed+failed
        assert "bad" in procs and "ok" not in procs
        assert {t[0] for t in q.transitions if t[1] == "failed"} == {"ok"}
        assert calls["n"] == 2  # both attempted — isolation, not abort


# kill_process_tree itself moved to tests/reactive_core/test_agents_process_kill.py
# (#1609, milestone #66 — extracted to agents/process_kill.py, de-duplicated
# against agents/pid_sidecar.py's kill logic).


# ---------------------------------------------------------------------------
# AC10 — injectable-port architecture
# ---------------------------------------------------------------------------


class TestInjectablePortArchitecture:
    def test_port_protocol_and_real_adapter_exist(self) -> None:
        # The Protocol is the seam; SupabaseTaskQueue is the prod adapter.
        adapter = SupabaseTaskQueue()  # constructible without touching the network
        assert isinstance(adapter, TaskQueuePort)  # runtime_checkable Protocol

    def test_drain_runs_against_a_fake_no_live_client(self) -> None:
        # If drain_tasks required a live client this whole module would not run.
        q = FakeTaskQueue(pending=[_row("t0")], running_count=0)
        spawns: list[str] = []
        drain_tasks(
            q,
            lambda g, task_id=None: spawns.append(g),
            resolve_binary=_always_resolve,
            read_usage=_healthy_usage,
        )
        assert spawns == ["do t0"]


# ---------------------------------------------------------------------------
# AC3 (#1390) — per-task git worktree creation in default_spawn
# ---------------------------------------------------------------------------


def _init_git_repo(path: Any) -> None:
    """A minimal real git repo with one commit on main, so a later
    ``git worktree add -b`` has something to branch from."""
    subprocess.run(["git", "init", "-q", "--initial-branch=main"], cwd=path, check=True)
    (path / "README.md").write_text("stub\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=path, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=t@t",
            "-c",
            "user.name=t",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-qm",
            "init",
        ],
        cwd=path,
        check=True,
    )


class TestDefaultSpawnWorktree:
    """AC3 (#1390): default_spawn creates .reactive/worktrees/<task_id> on
    branch task/<task_id> before spawn, and passes it as the worker's cwd."""

    def test_creates_worktree_and_passes_cwd(self, tmp_path: Any, monkeypatch: Any) -> None:
        import agents.executor as executor
        import agents.task_worktree as tw

        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)
        monkeypatch.setattr(tw, "_REPO_ROOT", str(repo))

        captured: dict[str, Any] = {}

        def fake_executor_spawn(
            goal: str, *, task_id: str | None = None, cwd: str | None = None
        ) -> Any:
            captured["task_id"] = task_id
            captured["cwd"] = cwd
            return "spawned"

        monkeypatch.setattr(executor, "spawn", fake_executor_spawn)

        default_spawn("do the thing", task_id="t1")

        expected_path = os.path.join(str(repo), ".reactive", "worktrees", "t1")
        assert captured["cwd"] == expected_path
        assert os.path.isdir(expected_path)

        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=expected_path,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        assert branch == "task/t1"
        assert os.environ is not None  # sanity — no monkeypatch leaked


# ---------------------------------------------------------------------------
# AC4 (#1390) — isolation proven against real git, not string inequality
# ---------------------------------------------------------------------------


class TestWorktreeIsolationRealGit:
    """AC4 (#1390): two worktrees off one repo never see each other's writes,
    and neither write reaches the root checkout — proven with real git, not a
    string-inequality assertion on two path values."""

    def test_conflicting_writes_stay_isolated(self, tmp_path: Any, monkeypatch: Any) -> None:
        import agents.task_worktree as tw

        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)
        monkeypatch.setattr(tw, "_REPO_ROOT", str(repo))

        path_a = tw.create_task_worktree("task-a")
        path_b = tw.create_task_worktree("task-b")

        # Same relative filename, conflicting content, one write per worktree.
        conflict_a = os.path.join(path_a, "conflict.txt")
        conflict_b = os.path.join(path_b, "conflict.txt")
        with open(conflict_a, "w", encoding="utf-8") as f:
            f.write("written by task-a\n")
        with open(conflict_b, "w", encoding="utf-8") as f:
            f.write("written by task-b\n")

        # Each worktree sees only its own write, at the content level.
        with open(conflict_a, encoding="utf-8") as f:
            assert f.read() == "written by task-a\n"
        with open(conflict_b, encoding="utf-8") as f:
            assert f.read() == "written by task-b\n"

        # Neither write reaches the root checkout — worktrees have distinct
        # working trees, not shared ones.
        assert not os.path.exists(os.path.join(str(repo), "conflict.txt"))


# ---------------------------------------------------------------------------
# AC5 (#1390) — terminal-boundary worktree finalize: remove on success,
# detach HEAD (freeing the branch ref) on failure
# ---------------------------------------------------------------------------


class TestFinalizeTaskWorktreeOnTerminal:
    """AC5 (#1390): poll_completions removes the worktree on a `done`
    transition. On `failed` it detaches HEAD instead, so the branch ref is
    free for `_redrive_goal`'s retry — proven by a subsequent real
    `git worktree add <path> task/<id>` (attach, not -b) succeeding."""

    def test_success_removes_worktree(self, tmp_path: Any, monkeypatch: Any) -> None:
        import agents.task_worktree as tw

        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)
        monkeypatch.setattr(tw, "_REPO_ROOT", str(repo))

        worktree_path = tw.create_task_worktree("t0")
        assert os.path.isdir(worktree_path)

        q = FakeTaskQueue()
        procs = {"t0": TrackedProc(_FakeProc(rc=0), started_at=0.0)}
        res = poll_completions(q, procs)

        assert res.done == 1
        assert not os.path.exists(worktree_path)

    def test_failure_detaches_head_and_frees_branch_for_retry(
        self, tmp_path: Any, monkeypatch: Any
    ) -> None:
        import agents.task_worktree as tw

        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)
        monkeypatch.setattr(tw, "_REPO_ROOT", str(repo))

        worktree_path = tw.create_task_worktree("t0")

        q = FakeTaskQueue()
        procs = {"t0": TrackedProc(_FakeProc(rc=1), started_at=0.0)}
        res = poll_completions(q, procs)

        assert res.failed_exit == 1
        # Retained on disk for post-mortem — AC6's sweep TTL/count-caps it later.
        assert os.path.isdir(worktree_path)

        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=worktree_path,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        assert branch == "HEAD"  # detached, not still on task/t0

        # The branch ref is free — a retry can attach it in a fresh worktree.
        retry_path = str(tmp_path / "retry")
        subprocess.run(
            ["git", "worktree", "add", retry_path, "task/t0"],
            cwd=str(repo),
            check=True,
            capture_output=True,
            text=True,
        )
        assert os.path.isdir(retry_path)


# ---------------------------------------------------------------------------
# PR #1450 review (MEDIUM) — _create_task_worktree must honor an explicit
# (branch=...) directive by attaching to that branch instead of always
# creating task/<task_id>, so a fresh-shape redrive lands back on the root
# attempt's branch per _redrive_goal's pin.
# ---------------------------------------------------------------------------


class TestCreateTaskWorktreeBranchDirective:
    def test_no_directive_creates_own_task_branch(self, tmp_path: Any, monkeypatch: Any) -> None:
        import agents.task_worktree as tw

        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)
        monkeypatch.setattr(tw, "_REPO_ROOT", str(repo))

        worktree_path = tw.create_task_worktree("t0", "do the thing")

        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=worktree_path,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        assert branch == "task/t0"

    def test_directive_naming_own_branch_still_creates(
        self, tmp_path: Any, monkeypatch: Any
    ) -> None:
        import agents.task_worktree as tw

        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)
        monkeypatch.setattr(tw, "_REPO_ROOT", str(repo))

        worktree_path = tw.create_task_worktree("t0", "do the thing\n\n(branch=task/t0)")

        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=worktree_path,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        assert branch == "task/t0"

    def test_directive_naming_other_branch_attaches_not_creates(
        self, tmp_path: Any, monkeypatch: Any
    ) -> None:
        """A fresh-shape redrive's goal carries (branch=task/<root_task_id>)
        (per orchestrator._redrive_goal) naming a branch that already exists
        (freed by a prior failure's detach, per TestFinalizeTaskWorktreeOnTerminal
        above) — _create_task_worktree must attach to it, not create
        task/<new_task_id>, or the redrive's evidence check looks at a branch
        that was never populated (PR #1450 review, MEDIUM)."""
        import agents.task_worktree as tw

        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)
        monkeypatch.setattr(tw, "_REPO_ROOT", str(repo))

        # Simulate the root attempt: create + fail + detach, freeing task/root.
        root_path = tw.create_task_worktree("root")
        q = FakeTaskQueue()
        procs = {"root": TrackedProc(_FakeProc(rc=1), started_at=0.0)}
        poll_completions(q, procs)
        assert os.path.isdir(root_path)

        redrive_goal = "Re-drive (attempt 2): do the thing\n\n(branch=task/root)"
        redrive_path = tw.create_task_worktree("root-r2", redrive_goal)

        assert os.path.isdir(redrive_path)
        assert redrive_path != root_path
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=redrive_path,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        assert branch == "task/root"  # attached to the root branch, not task/root-r2

        # task/root-r2 must never have been created.
        branches = subprocess.run(
            ["git", "branch", "--list", "task/root-r2"],
            cwd=str(repo),
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        assert branches == ""


# ---------------------------------------------------------------------------
# AC6 (#1390) — tick-start worktree-reaping sweep
# ---------------------------------------------------------------------------


def _write_failed_marker(worktree_path: str, timestamp: float) -> None:
    """Directly write the AC5 marker file with a chosen timestamp — lets the
    AC6 TTL/cap tests control "how old" a retained failure is without
    depending on wall-clock timing."""
    import agents.task_worktree as tw

    with open(
        os.path.join(worktree_path, tw._WORKTREE_FAILED_AT_MARKER), "w", encoding="utf-8"
    ) as fh:
        fh.write(str(timestamp))


class TestSweepTaskWorktrees:
    """AC6 (#1390): tick-start sweep prunes worktrees whose task row is absent
    or terminal-non-failure, TTLs and count-caps retained failures, and
    reconciles git's own registration via `git worktree prune`."""

    def test_prunes_absent_and_terminal_non_failure_rows(
        self, tmp_path: Any, monkeypatch: Any
    ) -> None:
        import agents.task_worktree as tw

        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)
        monkeypatch.setattr(tw, "_REPO_ROOT", str(repo))

        gone_path = tw.create_task_worktree("gone")  # no status row at all
        done_path = tw.create_task_worktree("ok-done")
        parked_path = tw.create_task_worktree("ok-parked")
        dup_path = tw.create_task_worktree("ok-dup")

        queue = FakeTaskQueue(
            statuses={
                "ok-done": "done",
                "ok-parked": "parked",
                "ok-dup": "skipped_duplicate",
            }
        )

        result = sweep_task_worktrees(queue)

        assert not os.path.exists(gone_path)
        assert not os.path.exists(done_path)
        assert not os.path.exists(parked_path)
        assert not os.path.exists(dup_path)
        assert result.pruned == 4
        assert result.retained == 0
        assert result.ttl_pruned == 0
        assert result.cap_evicted == 0

    def test_active_states_all_untouched(self, tmp_path: Any, monkeypatch: Any) -> None:
        import agents.task_worktree as tw

        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)
        monkeypatch.setattr(tw, "_REPO_ROOT", str(repo))

        pending_path = tw.create_task_worktree("t-pending")
        claimed_path = tw.create_task_worktree("t-claimed")
        running_path = tw.create_task_worktree("t-running")

        queue = FakeTaskQueue(
            statuses={
                "t-pending": "pending",
                "t-claimed": "claimed",
                "t-running": "running",
            }
        )

        result = sweep_task_worktrees(queue)

        assert os.path.isdir(pending_path)
        assert os.path.isdir(claimed_path)
        assert os.path.isdir(running_path)
        assert result.pruned == 0
        assert result.retained == 0

    def test_retains_failed_within_ttl_and_cap(self, tmp_path: Any, monkeypatch: Any) -> None:
        import agents.task_worktree as tw

        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)
        monkeypatch.setattr(tw, "_REPO_ROOT", str(repo))

        worktree_path = tw.create_task_worktree("f1")
        tw.finalize_task_worktree("f1", success=False)

        queue = FakeTaskQueue(statuses={"f1": "failed"})
        result = sweep_task_worktrees(queue)

        assert os.path.isdir(worktree_path)
        assert result.pruned == 0
        assert result.retained == 1
        assert result.ttl_pruned == 0
        assert result.cap_evicted == 0

    def test_ttl_prunes_retained_failure_past_window(self, tmp_path: Any, monkeypatch: Any) -> None:
        import agents.task_worktree as tw

        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)
        monkeypatch.setattr(tw, "_REPO_ROOT", str(repo))

        worktree_path = tw.create_task_worktree("f2")
        tw.finalize_task_worktree("f2", success=False)
        _write_failed_marker(worktree_path, 1000.0)

        queue = FakeTaskQueue(statuses={"f2": "failed"})
        result = sweep_task_worktrees(queue, retention_seconds=100, now=lambda: 1000.0 + 10_000)

        assert not os.path.exists(worktree_path)
        assert result.ttl_pruned == 1
        assert result.retained == 0
        assert result.cap_evicted == 0

    def test_cap_evicts_oldest_first_independent_of_ttl(
        self, tmp_path: Any, monkeypatch: Any
    ) -> None:
        import agents.task_worktree as tw

        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)
        monkeypatch.setattr(tw, "_REPO_ROOT", str(repo))

        path_a = tw.create_task_worktree("f-a")
        tw.finalize_task_worktree("f-a", success=False)
        _write_failed_marker(path_a, 100.0)

        path_b = tw.create_task_worktree("f-b")
        tw.finalize_task_worktree("f-b", success=False)
        _write_failed_marker(path_b, 200.0)

        path_c = tw.create_task_worktree("f-c")
        tw.finalize_task_worktree("f-c", success=False)
        _write_failed_marker(path_c, 300.0)

        queue = FakeTaskQueue(statuses={"f-a": "failed", "f-b": "failed", "f-c": "failed"})
        # Huge retention_seconds keeps the TTL from firing regardless of `now`;
        # the cap is the only thing under test here.
        result = sweep_task_worktrees(
            queue, retention_seconds=10**9, retention_cap=2, now=lambda: 1000.0
        )

        assert not os.path.exists(path_a)  # oldest — evicted
        assert os.path.isdir(path_b)
        assert os.path.isdir(path_c)
        assert result.cap_evicted == 1
        assert result.retained == 2
        assert result.ttl_pruned == 0
        assert result.pruned == 0

    def test_git_worktree_prune_reconciles_externally_deleted_dir(
        self, tmp_path: Any, monkeypatch: Any
    ) -> None:
        import agents.task_worktree as tw

        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)
        monkeypatch.setattr(tw, "_REPO_ROOT", str(repo))

        worktree_path = tw.create_task_worktree("stale")
        # Simulate an out-of-band deletion (e.g. a Windows handle-lock that
        # cleared on its own, or a manual cleanup) — the directory is gone,
        # but git's own worktree registration doesn't know that yet.
        shutil.rmtree(worktree_path)

        before = subprocess.run(
            ["git", "worktree", "list"],
            cwd=str(repo),
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        assert "stale" in before

        sweep_task_worktrees(FakeTaskQueue())

        after = subprocess.run(
            ["git", "worktree", "list"],
            cwd=str(repo),
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        assert "stale" not in after

    def test_removal_failure_logs_and_continues(self, tmp_path: Any, monkeypatch: Any) -> None:
        import agents.task_worktree as tw

        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)
        monkeypatch.setattr(tw, "_REPO_ROOT", str(repo))

        good_path = tw.create_task_worktree("good")
        bad_path = tw.create_task_worktree("bad")

        real_remove = tw.remove_worktree

        def flaky_remove(worktree_path: str) -> bool:
            if worktree_path == bad_path:
                return False
            return real_remove(worktree_path)

        monkeypatch.setattr(tw, "remove_worktree", flaky_remove)

        queue = FakeTaskQueue(statuses={"good": "done", "bad": "done"})
        result = sweep_task_worktrees(queue)  # must not raise

        assert not os.path.exists(good_path)
        assert os.path.isdir(bad_path)  # removal "failed" — retried next tick
        assert result.pruned == 1


# ---------------------------------------------------------------------------
# #1085 S3-2 — local-drain fallback
# ---------------------------------------------------------------------------


class TestLocalDrainUntilTerminal:
    """local_drain_until_terminal — heartbeat-gated wake_driver --once loop."""

    def test_stops_when_rows_reach_terminal_state(self) -> None:
        status_sequence = [
            {"t1": "pending", "t2": "running"},
            {"t1": "done", "t2": "failed"},
        ]
        get_statuses_calls: list[list[str]] = []

        def fake_get_statuses(task_ids: list[str]) -> dict[str, str]:
            get_statuses_calls.append(list(task_ids))
            return status_sequence[len(get_statuses_calls) - 1]

        run_once_calls = 0

        def fake_run_once() -> None:
            nonlocal run_once_calls
            run_once_calls += 1

        result = local_drain_until_terminal(
            ["t1", "t2"],
            heartbeat_check=lambda: HeartbeatStatus(state="stale"),
            run_once=fake_run_once,
            get_statuses=fake_get_statuses,
            sleep=lambda _seconds: None,
        )

        assert result == {"t1": "done", "t2": "failed"}
        assert run_once_calls == 1
        assert get_statuses_calls == [["t1", "t2"], ["t1", "t2"]]

    def test_rechecks_heartbeat_before_each_spawn(self) -> None:
        heartbeat_calls = 0

        def fake_heartbeat_check() -> HeartbeatStatus:
            nonlocal heartbeat_calls
            heartbeat_calls += 1
            return HeartbeatStatus(state="stale")

        run_once_calls = 0
        statuses_by_call = [
            {"t1": "pending"},
            {"t1": "pending"},
            {"t1": "done"},
        ]

        def fake_run_once() -> None:
            nonlocal run_once_calls
            run_once_calls += 1

        def fake_get_statuses(task_ids: list[str]) -> dict[str, str]:
            return statuses_by_call[min(run_once_calls, len(statuses_by_call) - 1)]

        result = local_drain_until_terminal(
            ["t1"],
            heartbeat_check=fake_heartbeat_check,
            run_once=fake_run_once,
            get_statuses=fake_get_statuses,
            sleep=lambda _seconds: None,
        )

        assert result == {"t1": "done"}
        assert run_once_calls == 2
        # Heartbeat re-checked immediately before each of the 2 spawns.
        assert heartbeat_calls == 2

    def test_stops_early_when_heartbeat_becomes_fresh(self) -> None:
        heartbeat_states = iter(["stale", "fresh"])
        run_once_calls = 0

        def fake_run_once() -> None:
            nonlocal run_once_calls
            run_once_calls += 1

        result = local_drain_until_terminal(
            ["t1"],
            heartbeat_check=lambda: HeartbeatStatus(state=next(heartbeat_states)),
            run_once=fake_run_once,
            get_statuses=lambda _ids: {"t1": "pending"},
            sleep=lambda _seconds: None,
        )

        # Resident driver recovered (heartbeat fresh again) — stop without a
        # second local spawn, even though "t1" never reached a terminal state.
        assert result == {"t1": "pending"}
        assert run_once_calls == 1

    def test_empty_task_ids_is_noop(self) -> None:
        calls = {"heartbeat": 0, "run_once": 0, "get_statuses": 0}

        def fake_heartbeat_check() -> HeartbeatStatus:
            calls["heartbeat"] += 1
            return HeartbeatStatus(state="stale")

        def fake_run_once() -> None:
            calls["run_once"] += 1

        def fake_get_statuses(_ids: list[str]) -> dict[str, str]:
            calls["get_statuses"] += 1
            return {}

        result = local_drain_until_terminal(
            [],
            heartbeat_check=fake_heartbeat_check,
            run_once=fake_run_once,
            get_statuses=fake_get_statuses,
            sleep=lambda _seconds: None,
        )

        assert result == {}
        assert calls == {"heartbeat": 0, "run_once": 0, "get_statuses": 0}


class TestLocalDrainProductionAdapters:
    """default_* adapters for local_drain_until_terminal (#1085 S3-2)."""

    def test_default_local_drain_once_shells_out_to_wake_driver_once(
        self, monkeypatch: Any
    ) -> None:
        import sys

        import agents.task_dispatch as td

        captured: dict[str, Any] = {}

        def fake_run(argv: list[str], **kwargs: Any) -> Any:
            captured["argv"] = argv
            captured["kwargs"] = kwargs
            return subprocess.CompletedProcess(argv, 0)

        monkeypatch.setattr(td.subprocess, "run", fake_run)

        default_local_drain_once()

        assert captured["argv"] == [
            sys.executable,
            "-m",
            "agents.wake_driver",
            "--once",
            "--driver-name",
            td.LOCAL_DRAIN_DRIVER_NAME,
        ]
        # No cap-override flag/env — DEFAULT_CONCURRENCY_CAP (read inside the
        # child process's own drain_tasks call) is the only concurrency limit.
        assert "--concurrency" not in captured["argv"]
        assert "env" not in captured["kwargs"]

    def test_local_drain_driver_name_distinct_from_resident(self) -> None:
        """Regression guard for the review-flagged self-collision bug.

        If ``default_local_drain_once``'s subprocess ever stamps its ticks
        under the resident driver's own heartbeat identity again,
        ``local_drain_until_terminal``'s heartbeat re-check would read back
        its own just-written tick and conclude the resident had recovered —
        exiting after exactly one iteration regardless of pending rows.
        """
        from agents.driver_heartbeat import DRIVER_NAME

        assert LOCAL_DRAIN_DRIVER_NAME != DRIVER_NAME

    def test_default_get_task_statuses_delegates_to_task_queue(self, monkeypatch: Any) -> None:
        import agents.task_dispatch as td

        captured: dict[str, Any] = {}

        def fake_get_statuses(task_ids: list[str], *, client: Any = None) -> dict[str, str]:
            captured["task_ids"] = task_ids
            return {tid: "done" for tid in task_ids}

        monkeypatch.setattr(td.task_queue, "get_statuses", fake_get_statuses)

        result = default_get_task_statuses(["t1", "t2"])

        assert result == {"t1": "done", "t2": "done"}
        assert captured["task_ids"] == ["t1", "t2"]

    def test_default_local_drain_heartbeat_check_delegates_to_driver_heartbeat(
        self, monkeypatch: Any
    ) -> None:
        import agents.driver_heartbeat as dh

        expected = HeartbeatStatus(state="stale")
        monkeypatch.setattr(dh, "check_heartbeat", lambda: expected)

        assert default_local_drain_heartbeat_check() is expected


# ---------------------------------------------------------------------------
# #1689 — ex-post plan-review drain gate wiring
# ---------------------------------------------------------------------------


def _class2_row(
    task_id: str, *, issue_number: int = 1689, plan_digest: str | None = None
) -> dict[str, Any]:
    row = _row(task_id)
    row.update(
        {
            "issue_number": issue_number,
            "scope_files": ("mcp-memory/server.py",),
            "churn_lines": 5,
            "prod_areas": 1,
        }
    )
    if plan_digest is not None:
        row["plan_digest"] = plan_digest
    return row


class _FakePlanReviewGithub:
    """Fake ``GitHubClient`` for the plan-review gate — tracks call order."""

    def __init__(self, issues: dict[int, dict[str, Any]], events: list[tuple[str, ...]]) -> None:
        self._issues = issues
        self._events = events

    def get_issue(self, issue_number: int) -> dict[str, Any] | None:
        self._events.append(("get_issue", str(issue_number)))
        return self._issues.get(issue_number)

    def update_issue(self, issue_number: int, *, body: str) -> dict[str, Any]:
        issue = dict(self._issues.get(issue_number) or {})
        issue["body"] = body
        self._issues[issue_number] = issue
        self._events.append(("update_issue", str(issue_number)))
        return issue

    def create_issue_comment(self, issue_number: int, *, body: str) -> dict[str, Any]:
        self._events.append(("create_issue_comment", str(issue_number)))
        return {"body": body}


def _plan_config_with_shared_surface() -> Any:
    from agents.plan_review_config import (
        Class2Thresholds,
        Class3Criteria,
        ModelFloors,
        PlanReviewConfig,
    )

    return PlanReviewConfig(
        class_2=Class2Thresholds(
            shared_surface_globs=("mcp-memory/*",),
            churn_threshold=400,
            min_prod_areas=99,
        ),
        class_3=Class3Criteria(mechanical_criteria=()),
        models=ModelFloors(planner="claude-opus-5", critic="claude-sonnet-5"),
    )


class TestPlanReviewGateWiring:
    def test_planner_runs_and_digest_lands_before_spawn_for_class2_row(self) -> None:
        """AC2/AC7 — synchronous in-tick ordering.

        A class:2 row with no locked plan must go through the planner before
        ``spawn`` is ever called, ``set_plan_digest`` must land on the row
        before spawn, and the gate must not create a second ``task_queue``
        row (the fake port's ``claimed`` list stays length 1).
        """
        from agents.plan_lock import hash_plan
        from agents.plan_review_drain import PlanResult

        events: list[tuple[str, ...]] = []
        row = _class2_row("t0")
        q = FakeTaskQueue(pending=[row], running_count=0)

        original_set_digest = q.set_plan_digest

        def recording_set_plan_digest(task_id: str, digest: str) -> dict[str, Any]:
            events.append(("set_plan_digest", task_id))
            return original_set_digest(task_id, digest)

        q.set_plan_digest = recording_set_plan_digest  # type: ignore[method-assign]

        # No "## Plan\n" heading here — write_plan_section/replace_plan_section
        # adds the heading itself; embedding it in plan_text would double it up
        # and fail verify_lock's re-parse.
        plan_text = "- Step one\nlock: " + hash_plan("- Step one") + "\n"

        class _FakePlanner:
            def run_planner(self, row: dict[str, Any], config: Any) -> PlanResult:
                events.append(("run_planner", str(row["issue_number"])))
                return PlanResult(plan_text=plan_text, resolved=True)

        github = _FakePlanReviewGithub(
            {1689: {"body": "## Acceptance Criteria\n- AC one\n"}}, events
        )

        res = drain_tasks(
            q,
            lambda g, task_id=None: events.append(("spawn", g)),
            cap=5,
            resolve_binary=_always_resolve,
            read_usage=_healthy_usage,
            planner=_FakePlanner(),
            plan_config_loader=_plan_config_with_shared_surface,
            github_factory=lambda: github,
        )

        kinds = [e[0] for e in events]
        assert "run_planner" in kinds
        assert "set_plan_digest" in kinds
        assert "spawn" in kinds
        assert kinds.index("run_planner") < kinds.index("spawn")
        assert kinds.index("set_plan_digest") < kinds.index("spawn")
        assert q.claimed == ["t0"]  # no second row created
        assert res.spawned == 1
        assert res.parked == 0
        assert res.failed == 0

    def test_class2_row_parked_when_planner_does_not_resolve(self) -> None:
        from agents.plan_review_drain import PlanResult

        class _UnresolvedPlanner:
            def run_planner(self, row: dict[str, Any], config: Any) -> PlanResult:
                return PlanResult(plan_text="", resolved=False, reason="critics disagreed")

        row = _class2_row("t0")
        q = FakeTaskQueue(pending=[row], running_count=0)
        events: list[tuple[str, ...]] = []
        github = _FakePlanReviewGithub({1689: {"body": "no plan yet"}}, events)
        spawns: list[str] = []

        res = drain_tasks(
            q,
            lambda g, task_id=None: spawns.append(g),
            cap=5,
            resolve_binary=_always_resolve,
            read_usage=_healthy_usage,
            planner=_UnresolvedPlanner(),
            plan_config_loader=_plan_config_with_shared_surface,
            github_factory=lambda: github,
        )

        assert spawns == []
        assert res.spawned == 0
        assert res.parked == 1
        assert ("t0", "parked", "critics disagreed") in q.transitions

    def test_class1_row_skips_the_plan_gate_entirely(self) -> None:
        """A row that classifies class:1 never touches the planner or GitHub."""
        row = _row("t0")  # bare row -> no scope_files/churn/prod_areas -> class:1

        class _ExplodingPlanner:
            def run_planner(self, row: dict[str, Any], config: Any) -> Any:
                raise AssertionError("planner must not run for a class:1 row")

        def _exploding_github_factory() -> Any:
            raise AssertionError("github must not be fetched for a class:1 row")

        q = FakeTaskQueue(pending=[row], running_count=0)
        spawns: list[str] = []

        res = drain_tasks(
            q,
            lambda g, task_id=None: spawns.append(g),
            cap=5,
            resolve_binary=_always_resolve,
            read_usage=_healthy_usage,
            planner=_ExplodingPlanner(),
            plan_config_loader=_plan_config_with_shared_surface,
            github_factory=_exploding_github_factory,
        )

        assert spawns == ["do t0"]
        assert res.spawned == 1

    def test_drain_skips_entirely_when_plan_config_fails_to_load(self) -> None:
        def _broken_loader() -> Any:
            raise RuntimeError("config missing")

        q = FakeTaskQueue(pending=[_class2_row("t0")], running_count=0)
        spawns: list[str] = []

        res = drain_tasks(
            q,
            lambda g, task_id=None: spawns.append(g),
            cap=5,
            resolve_binary=_always_resolve,
            read_usage=_healthy_usage,
            plan_config_loader=_broken_loader,
        )

        assert spawns == []
        assert q.claimed == []
        assert res.skipped_no_plan_config is True
        assert res.spawned == 0
