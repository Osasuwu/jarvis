"""Unit tests for the scheduler primitive (issue #300, S2-5).

These tests use APScheduler's in-memory jobstore so they don't need a
live Postgres. The Postgres restart-recovery path is covered by a
manual smoke test documented in docs/agents/scheduler.md — can't
reliably fork/kill a process from within pytest on Windows.
"""

from __future__ import annotations

import pickle

import pytest

apscheduler = pytest.importorskip("apscheduler")


@pytest.fixture()
def memory_handle():
    """A ``SchedulerHandle`` backed by ``MemoryJobStore`` — no Postgres required."""
    from apscheduler.jobstores.memory import MemoryJobStore

    from agents import scheduler

    return scheduler.build_scheduler(jobstore=MemoryJobStore())


# ---------------------------------------------------------------------------
# URL resolution for the SQLAlchemy jobstore.
# ---------------------------------------------------------------------------


def test_resolve_jobstore_url_adds_driver_tag_when_missing() -> None:
    from agents import scheduler

    got = scheduler._resolve_jobstore_url(
        "postgresql://jarvis:jarvis@localhost:5433/agents?sslmode=disable"
    )
    assert got == "postgresql+psycopg://jarvis:jarvis@localhost:5433/agents?sslmode=disable"


def test_resolve_jobstore_url_preserves_explicit_driver() -> None:
    from agents import scheduler

    url = "postgresql+psycopg2://u:p@host/db"
    assert scheduler._resolve_jobstore_url(url) == url


def test_resolve_jobstore_url_passthrough_non_postgres() -> None:
    """Sqlite URLs or anything else get returned unchanged — no surprises."""
    from agents import scheduler

    url = "sqlite:///tmp/jarvis.sqlite"
    assert scheduler._resolve_jobstore_url(url) == url


# ---------------------------------------------------------------------------
# build_scheduler + SchedulerHandle basics.
# ---------------------------------------------------------------------------


def test_build_scheduler_returns_handle_with_injected_jobstore() -> None:
    from apscheduler.jobstores.memory import MemoryJobStore

    from agents import scheduler

    store = MemoryJobStore()
    handle = scheduler.build_scheduler(jobstore=store)

    assert handle.scheduler is not None
    assert handle.jobstore_alias == "default"
    # The handle's scheduler should be using our injected store under the alias.
    assert handle.scheduler._lookup_jobstore("default") is store


def test_scheduler_handle_is_frozen_dataclass() -> None:
    """Handle should be immutable — tests accidental mutation."""
    from agents import scheduler

    handle = scheduler.build_scheduler(jobstore=_memory_jobstore())
    with pytest.raises(Exception):  # FrozenInstanceError is a dataclasses-specific subclass
        handle.jobstore_alias = "other"  # type: ignore[misc]


def _memory_jobstore():
    from apscheduler.jobstores.memory import MemoryJobStore

    return MemoryJobStore()


# ---------------------------------------------------------------------------
# register_agent — the core public API.
# ---------------------------------------------------------------------------


def test_register_agent_creates_interval_job(memory_handle) -> None:
    from agents import scheduler

    job = scheduler.register_agent(
        memory_handle,
        agent_id="test-agent",
        fn=scheduler._placeholder_tick,
        interval_seconds=30,
        jitter_seconds=5,
    )

    assert job.id == "test-agent"
    assert job.name == "agent:test-agent"
    # Single-instance, coalesce, matches the restart-safe contract.
    assert job.max_instances == 1
    assert job.coalesce is True


def test_register_agent_trigger_has_interval_and_jitter(memory_handle) -> None:
    """Interval and jitter are what the trigger actually exposes."""
    from agents import scheduler

    job = scheduler.register_agent(
        memory_handle,
        agent_id="jitter-agent",
        fn=scheduler._placeholder_tick,
        interval_seconds=45,
        jitter_seconds=7,
    )

    trigger = job.trigger
    # IntervalTrigger stores the interval as a timedelta.
    assert int(trigger.interval_length) == 45
    assert trigger.jitter == 7


def test_register_agent_jitter_zero_passed_as_none(memory_handle) -> None:
    """jitter_seconds=0 must not register a jitter=0 (it rejects the job).

    APScheduler's IntervalTrigger treats jitter=0 as 'no jitter' — we pass
    None to make intent explicit. Verifies the `jitter_seconds or None` path.
    """
    from agents import scheduler

    job = scheduler.register_agent(
        memory_handle,
        agent_id="no-jitter",
        fn=scheduler._placeholder_tick,
        interval_seconds=60,
        jitter_seconds=0,
    )
    assert job.trigger.jitter is None


def test_register_agent_replace_existing_is_idempotent(memory_handle) -> None:
    """Re-registering the same ``agent_id`` replaces the previous job.

    Uses ``start(paused=True)`` so the jobstore actually holds the jobs
    (otherwise they queue into ``_pending_jobs`` and the test can't see
    the real dedup behaviour).
    """
    from agents import scheduler

    memory_handle.scheduler.start(paused=True)
    try:
        scheduler.register_agent(
            memory_handle,
            agent_id="dup-agent",
            fn=scheduler._placeholder_tick,
            interval_seconds=30,
        )
        # Second registration with a different interval — must succeed and
        # update the existing job, not throw ConflictingIdError.
        job = scheduler.register_agent(
            memory_handle,
            agent_id="dup-agent",
            fn=scheduler._placeholder_tick,
            interval_seconds=120,
        )

        assert job.id == "dup-agent"
        assert int(job.trigger.interval_length) == 120
        # And there is only ONE job with that id in the jobstore.
        all_jobs = memory_handle.scheduler.get_jobs()
        assert sum(1 for j in all_jobs if j.id == "dup-agent") == 1
    finally:
        memory_handle.scheduler.shutdown(wait=False)


def test_register_agent_rejects_zero_interval(memory_handle) -> None:
    from agents import scheduler

    with pytest.raises(ValueError, match="interval_seconds must be positive"):
        scheduler.register_agent(
            memory_handle,
            agent_id="zero",
            fn=scheduler._placeholder_tick,
            interval_seconds=0,
        )


def test_register_agent_rejects_negative_interval(memory_handle) -> None:
    from agents import scheduler

    with pytest.raises(ValueError, match="interval_seconds must be positive"):
        scheduler.register_agent(
            memory_handle,
            agent_id="neg",
            fn=scheduler._placeholder_tick,
            interval_seconds=-5,
        )


def test_register_agent_rejects_negative_jitter(memory_handle) -> None:
    from agents import scheduler

    with pytest.raises(ValueError, match="jitter_seconds must be non-negative"):
        scheduler.register_agent(
            memory_handle,
            agent_id="neg-jitter",
            fn=scheduler._placeholder_tick,
            interval_seconds=60,
            jitter_seconds=-1,
        )


# ---------------------------------------------------------------------------
# Job persistence contract: the registered callable must be picklable.
# ---------------------------------------------------------------------------


def test_placeholder_tick_is_picklable() -> None:
    """Persistent jobstore serialises the callable. A closure here would
    silently fail on restart — keep _placeholder_tick at module scope.
    """
    from agents import scheduler

    blob = pickle.dumps(scheduler._placeholder_tick)
    restored = pickle.loads(blob)
    # Round-trip yields the same callable reference, not a copy.
    assert restored is scheduler._placeholder_tick


# ---------------------------------------------------------------------------
# Signal-handler installation — must not raise on any platform.
# ---------------------------------------------------------------------------


def test_install_signal_handlers_is_safe_on_current_platform(memory_handle) -> None:
    """On Windows SIGTERM install raises ValueError; on Unix it works.
    Either way, ``_install_signal_handlers`` must not propagate the error.
    """
    from agents import scheduler

    # Must not raise, regardless of platform.
    scheduler._install_signal_handlers(memory_handle)


# ---------------------------------------------------------------------------
# CLI argparse surface — cheap sanity that --once / --interval / --jitter exist.
# ---------------------------------------------------------------------------


def test_main_cli_exposes_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    """The CLI should accept --interval, --jitter, --once without error,
    and forward them to ``run``. We don't actually start the scheduler.
    """
    from agents import scheduler

    called: dict[str, object] = {}

    def fake_run(interval: int, jitter: int, *, once: bool = False) -> int:
        called["interval"] = interval
        called["jitter"] = jitter
        called["once"] = once
        return 0

    monkeypatch.setattr(scheduler, "run", fake_run)
    monkeypatch.setattr("sys.argv", ["agents.scheduler", "--interval", "42", "--jitter", "3"])

    rc = scheduler.main()
    assert rc == 0
    assert called == {"interval": 42, "jitter": 3, "once": False}


def test_main_cli_once_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    from agents import scheduler

    captured: dict[str, object] = {}

    def fake_run(interval: int, jitter: int, *, once: bool = False) -> int:
        captured["once"] = once
        return 0

    monkeypatch.setattr(scheduler, "run", fake_run)
    monkeypatch.setattr("sys.argv", ["agents.scheduler", "--once"])

    assert scheduler.main() == 0
    assert captured["once"] is True
