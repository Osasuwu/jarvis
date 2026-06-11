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
from datetime import UTC, datetime, timedelta
from typing import Any

from agents.task_dispatch import (
    DEFAULT_ASSIGNEE,
    DEFAULT_CONCURRENCY_CAP,
    SupabaseTaskQueue,
    TaskQueuePort,
    drain_tasks,
    reclaim_stale_tasks,
)


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
        self, *, pending: list[dict[str, Any]] | None = None, running_count: int = 0
    ) -> None:
        self._pending = list(pending or [])
        self._running_count = running_count
        self.claimed: list[str] = []
        self.transitions: list[tuple[str, str, str | None]] = []
        self.reclaimed_count = 0
        self.stale_running: list[dict[str, Any]] = []

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


def _always_resolve() -> str:
    return "claude"


# ---------------------------------------------------------------------------
# AC3 — concurrency cap: budget = cap − count_running, sampled once
# ---------------------------------------------------------------------------


class TestConcurrencyCap:
    def test_budget_limits_spawns(self) -> None:
        # 3 already running, cap 5 -> budget 2 -> only 2 of 4 pending spawned.
        q = FakeTaskQueue(pending=[_row(f"t{i}") for i in range(4)], running_count=3)
        spawns: list[str] = []
        res = drain_tasks(q, lambda g: spawns.append(g), cap=5, resolve_binary=_always_resolve)
        assert len(spawns) == 2
        assert len(q.claimed) == 2
        assert res.spawned == 2

    def test_no_spawn_when_at_cap(self) -> None:
        q = FakeTaskQueue(pending=[_row("t0")], running_count=5)
        spawns: list[str] = []
        res = drain_tasks(q, lambda g: spawns.append(g), cap=5, resolve_binary=_always_resolve)
        assert spawns == []
        assert q.claimed == []
        assert res.spawned == 0

    def test_default_cap_is_five(self) -> None:
        assert DEFAULT_CONCURRENCY_CAP == 5


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
        drain_tasks(q, lambda g: spawns.append(g), resolve_binary=_always_resolve)
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

        drain_tasks(q, lambda g: events.append(("spawn", g)), resolve_binary=_always_resolve)

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
        res = drain_tasks(q, lambda g: spawns.append(g), resolve_binary=_always_resolve)
        assert spawns == []
        assert res.spawned == 0

    def test_none_claim_stops_drain_no_phantom_spawn(self) -> None:
        # Budget allows 5 but a competing drainer left only one claimable row;
        # subsequent claims return None and the loop stops cleanly without
        # spawning for an unclaimed row (the optimistic-lock atomicity that
        # makes the lost race safe is unit-tested in test_agents_task_queue).
        q = FakeTaskQueue(pending=[_row("only")], running_count=0)
        spawns: list[str] = []
        res = drain_tasks(q, lambda g: spawns.append(g), cap=5, resolve_binary=_always_resolve)
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

        res = drain_tasks(q, lambda g: spawns.append(g), resolve_binary=resolve_missing)

        assert q.claimed == []  # zero claims — no row touched
        assert spawns == []
        assert res.skipped_no_binary is True
        assert res.spawned == 0
        assert len(q._pending) == 2  # rows stay pending -> next drain self-heals


# ---------------------------------------------------------------------------
# AC7b — spawn raises: mark that task failed (terminal), continue the drain
# ---------------------------------------------------------------------------


class TestSpawnFailureIsTerminal:
    def test_spawn_raise_marks_failed_and_continues(self) -> None:
        q = FakeTaskQueue(pending=[_row("boom"), _row("ok")], running_count=0)
        spawns: list[str] = []

        def spawn(goal: str) -> None:
            if goal == "do boom":
                raise RuntimeError("spawn blew up")
            spawns.append(goal)

        res = drain_tasks(q, spawn, cap=5, resolve_binary=_always_resolve)

        failed = [t for t in q.transitions if t[1] == "failed"]
        assert len(failed) == 1
        assert failed[0][0] == "boom"
        assert failed[0][2] and "spawn" in failed[0][2]  # reason documents the cause
        # 'boom' was transitioned running THEN failed (no retry); 'ok' spawned.
        assert ("boom", "running", None) in q.transitions
        assert spawns == ["do ok"]
        assert res.spawned == 1
        assert res.failed == 1


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


class TestBillingTrapThroughDrain:
    def test_api_keys_stripped_from_spawned_env(self, monkeypatch: Any, tmp_path: Any) -> None:
        from agents import executor

        fake_bin = tmp_path / "claude.exe"
        fake_bin.write_text("")

        captured = _CapturedPopen()
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-must-be-stripped")
        monkeypatch.setenv("CLAUDE_API_KEY", "sk-also-stripped")
        monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "tok-stripped")
        monkeypatch.setenv("JARVIS_CLAUDE_BIN", str(fake_bin))
        monkeypatch.setenv("PATH_FROM_PARENT", "keep-me")

        q = FakeTaskQueue(pending=[_row("t0")], running_count=0)

        def spawn(goal: str) -> Any:
            return executor.spawn(
                goal,
                popen=captured,
                probe=_FixedProbe(_healthy_reading()),
                stderr_log_dir=str(tmp_path),
            )

        drain_tasks(q, spawn, resolve_binary=lambda: str(fake_bin))

        assert len(captured.calls) == 1
        env = captured.calls[0]["env"]
        assert "ANTHROPIC_API_KEY" not in env, "billing-trap leak through drain path"
        assert "CLAUDE_API_KEY" not in env
        assert "ANTHROPIC_AUTH_TOKEN" not in env
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
        drain_tasks(q, lambda g: spawns.append(g), resolve_binary=_always_resolve)
        assert spawns == ["do t0"]
        assert os.environ is not None  # sanity — no monkeypatch leaked
