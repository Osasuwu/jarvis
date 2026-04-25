"""Scheduler primitive for Pillar 7 persistent agents (issue #300, S2-5).

Run-loop engine. Registers agent tick functions as APScheduler jobs backed
by a Postgres jobstore (same database as LangGraph's PostgresSaver) so
jobs persist across process restarts.

Why APScheduler and not Claude Code Routines: Routines run Claude Code;
these agents are Python/LangGraph talking to Ollama and Supabase. Routines
can't drive them. APScheduler is in-process, Postgres-backed, crash-safe.

Usage::

    from agents import scheduler

    handle = scheduler.build_scheduler()
    scheduler.register_agent(
        handle,
        agent_id="task-dispatcher",
        fn=dispatcher_tick,
        interval_seconds=60,
        jitter_seconds=10,
    )
    handle.scheduler.start()

CLI (runs the task-dispatcher on a persistent schedule)::

    python -m agents.scheduler                              # tick every 60s + 10s jitter
    python -m agents.scheduler --interval 30                # override interval
    python -m agents.scheduler --once                       # fire one tick and exit
    python -m agents.scheduler --once --dry-run             # graph only, no 'claude -p'
    python -m agents.scheduler --interval 60 --jitter 5     # production CLI
    python -m agents.scheduler --interval 60 --placeholder  # (dev) + canary tick

Restart semantics: each agent's job is identified by ``agent_id`` and
registered with ``replace_existing=True`` / ``max_instances=1`` /
``coalesce=True``. A restarted process rebuilds the same job; the
persisted row in ``apscheduler_jobs`` is reused, no duplicate tick is
fired, and missed ticks collapse to a single catch-up run.

Co-existence with LangGraph: APScheduler writes to ``apscheduler_jobs``
/ ``apscheduler_jobs_history``; LangGraph's PostgresSaver writes to
``checkpoints`` / ``checkpoint_writes`` / ``checkpoint_blobs``. Disjoint
table sets — they share the database, not the schema namespace.
"""

from __future__ import annotations

import argparse
import logging
import signal
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from dotenv import load_dotenv

from agents.config import load_config

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_SECONDS = 60
DEFAULT_JITTER_SECONDS = 10


@dataclass(frozen=True)
class SchedulerHandle:
    """Wraps a live scheduler and the jobstore alias used for registration.

    Held by callers so they can add further jobs or shut the scheduler down.
    Frozen — treat as a value object.
    """

    scheduler: Any  # apscheduler.schedulers.base.BaseScheduler
    jobstore_alias: str = "default"


def _resolve_jobstore_url(postgres_url: str) -> str:
    """Adapt a psycopg-style URL to the SQLAlchemy driver form APScheduler wants.

    LangGraph's ``PostgresSaver`` accepts plain ``postgresql://`` because psycopg
    registers itself as the default driver. APScheduler's ``SQLAlchemyJobStore``
    builds a SQLAlchemy engine, which in modern SA (2.x) prefers an explicit
    driver tag. Use psycopg v3 unless the caller already specified one.
    """
    if postgres_url.startswith("postgresql+"):
        return postgres_url
    if postgres_url.startswith("postgresql://"):
        return "postgresql+psycopg://" + postgres_url[len("postgresql://") :]
    return postgres_url


def build_scheduler(
    postgres_url: str | None = None,
    *,
    jobstore: Any | None = None,
) -> SchedulerHandle:
    """Construct a ``BackgroundScheduler`` with a Postgres-backed jobstore.

    Passing ``jobstore`` overrides the default SQLAlchemy one — tests inject
    ``MemoryJobStore`` so they can run without a live Postgres.
    """
    from apscheduler.schedulers.background import BackgroundScheduler

    if jobstore is None:
        from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

        if postgres_url is None:
            postgres_url = load_config().postgres_url
        jobstore = SQLAlchemyJobStore(url=_resolve_jobstore_url(postgres_url))

    scheduler = BackgroundScheduler(jobstores={"default": jobstore}, timezone="UTC")
    return SchedulerHandle(scheduler=scheduler)


def register_agent(
    handle: SchedulerHandle,
    *,
    agent_id: str,
    fn: Callable[..., Any],
    interval_seconds: int = DEFAULT_INTERVAL_SECONDS,
    jitter_seconds: int = DEFAULT_JITTER_SECONDS,
) -> Any:
    """Register ``fn`` as a recurring job keyed by ``agent_id``.

    Key invariants:

    - ``replace_existing=True`` — restarts reuse the persisted row, config
      drift updates the trigger in place, no duplicate registrations.
    - ``max_instances=1`` — no two ticks of the same agent overlap.
    - ``coalesce=True`` — if the scheduler was asleep and 5 ticks are due,
      run once, not five times.
    - ``jitter`` on the trigger — two devices running the same agent don't
      fall into lockstep with the DB.

    Returns the APScheduler ``Job`` object (opaque — tests inspect it for
    trigger shape).
    """
    from apscheduler.triggers.interval import IntervalTrigger

    if interval_seconds <= 0:
        raise ValueError(f"interval_seconds must be positive, got {interval_seconds}")
    if jitter_seconds < 0:
        raise ValueError(f"jitter_seconds must be non-negative, got {jitter_seconds}")

    return handle.scheduler.add_job(
        fn,
        trigger=IntervalTrigger(seconds=interval_seconds, jitter=jitter_seconds or None),
        id=agent_id,
        name=f"agent:{agent_id}",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        jobstore=handle.jobstore_alias,
    )


def _pickle_canary_tick() -> None:
    """Proof-of-life tick for testing jobstore pickle round-trips.

    Lives at module scope (not a closure) so APScheduler's jobstore can
    pickle the job reference and restore it across restarts. Used by
    ``--placeholder`` dev flag to verify the persistence contract.
    """
    logger.info("[scheduler] canary tick at %s", int(time.time()))


def _install_signal_handlers(handle: SchedulerHandle) -> None:
    """Drain the scheduler on SIGTERM / SIGINT where the platform supports it.

    Windows: ``SIGTERM`` is exposed as a constant but ``signal.signal`` raises
    ValueError when you try to install a handler — there's no Unix-style term
    signal on the OS. Swallow silently; KeyboardInterrupt handling in ``run``
    still covers Ctrl-C on both platforms.
    """

    def _handler(signum: int, frame: Any) -> None:  # noqa: ARG001
        logger.info("[scheduler] signal %s received -- draining", signum)
        handle.scheduler.shutdown(wait=True)

    for sig_name in ("SIGTERM", "SIGINT"):
        sig = getattr(signal, sig_name, None)
        if sig is None:
            continue
        try:
            signal.signal(sig, _handler)
        except (ValueError, OSError):
            # Platform doesn't allow this signal (SIGTERM on Windows).
            logger.debug("[scheduler] signal %s not installable on this platform", sig_name)


def run(
    interval_seconds: int,
    jitter_seconds: int,
    *,
    once: bool = False,
    dry_run: bool = False,
    placeholder: bool = False,
) -> int:
    """CLI entry-point: start scheduler, register the dispatcher, block.

    ``--once`` forces one immediate run of every registered agent and exits.
    Useful for smoke tests that don't want to wait a full interval.

    ``--dry-run`` makes the dispatcher tick traverse the full graph without
    spawning ``claude -p``; audit rows are still written.

    ``--placeholder`` dev flag registers the canary tick alongside the
    dispatcher (useful for testing the jobstore pickle contract).
    """
    from agents import dispatcher

    cfg = load_config()
    handle = build_scheduler(cfg.postgres_url)
    dispatcher.register(
        handle,
        dry_run=dry_run,
        interval_seconds=interval_seconds,
        jitter_seconds=jitter_seconds,
    )
    if placeholder:
        register_agent(
            handle,
            agent_id="scheduler-canary",
            fn=_pickle_canary_tick,
            interval_seconds=interval_seconds,
            jitter_seconds=jitter_seconds,
        )
    _install_signal_handlers(handle)
    handle.scheduler.start()

    # Startup reaper: delete orphan jobstore rows from agent_ids that
    # no longer exist in code. This guards against rename/removal drift.
    registered_ids = {job.id for job in handle.scheduler.get_jobs()}
    jobstore = handle.scheduler._lookup_jobstore(handle.jobstore_alias)
    for job in jobstore.get_all_jobs():
        if job.id not in registered_ids:
            logger.info("[scheduler] reaping orphan job id=%s", job.id)
            jobstore.remove_job(job.id)

    if once:
        # Wake every registered job immediately, drain, exit.
        import datetime as _dt

        now = _dt.datetime.now(_dt.UTC)
        for job in handle.scheduler.get_jobs():
            job.modify(next_run_time=now)
        # Give the worker thread a chance to pick up and run.
        time.sleep(2)
        handle.scheduler.shutdown(wait=True)
        return 0

    logger.info(
        "[scheduler] running. interval=%ss jitter=%ss (Ctrl-C to stop)",
        interval_seconds,
        jitter_seconds,
    )
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        logger.info("[scheduler] KeyboardInterrupt -- draining")
        handle.scheduler.shutdown(wait=True)
    return 0


def main() -> int:
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--interval",
        type=int,
        default=DEFAULT_INTERVAL_SECONDS,
        help=f"Seconds between ticks (default: {DEFAULT_INTERVAL_SECONDS})",
    )
    parser.add_argument(
        "--jitter",
        type=int,
        default=DEFAULT_JITTER_SECONDS,
        help=f"Max random seconds added per tick (default: {DEFAULT_JITTER_SECONDS})",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run registered jobs once and exit (useful for smoke tests).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dispatcher traverses full graph but does not spawn 'claude -p'.",
    )
    parser.add_argument(
        "--placeholder",
        action="store_true",
        help="(Dev only) Register the canary tick alongside the dispatcher.",
    )
    args = parser.parse_args()
    return run(
        args.interval,
        args.jitter,
        once=args.once,
        dry_run=args.dry_run,
        placeholder=args.placeholder,
    )


if __name__ == "__main__":
    raise SystemExit(main())
