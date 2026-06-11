"""wake_driver — crash-safe LISTEN/NOTIFY cold-boot loop (#743).

The wake_driver replaces the retired APScheduler resident scheduler. It is a
**program, not an agent**: it owns no decisions, only the wake mechanics —
"persistent BEHAVIOR, not a persistent PROCESS" (milestone #44, decisions
``efa255cc`` / ``2c5384d0``).

Behavior:

- ``LISTEN`` on the events NOTIFY channel (``'events'``, the
  ``notify_events_insert`` trigger from the #739 substrate). Each wake signal
  cold-boots the orchestrator for the next single ``pending`` event; the loop
  advances to the next as soon as the prior tick finishes — no cron, no fixed
  interval, no resident sleep-poll loop.
- **At-least-once.** An event stays ``claimed`` until the orchestrator commits
  ``processed``. A crash mid-tick leaves the row ``claimed``; a **watchdog**
  re-claims rows older than a threshold so a dead orchestrator never strands
  work. The watchdog also fires on the wait timeout, so it runs even when no
  NOTIFY arrives.
- The orchestrator is **injected** (a ``Callable[[dict], None]``). The default
  is a trivial no-op stub (this slice tests wake mechanics without the real
  model). wake_driver deliberately does **not** import
  :func:`agents.orchestrator.handle_event` — the driver is a decisionless
  program and the router is a separate concern.

The pure loop (:func:`drain_pending` / :func:`run_watchdog` / :func:`tick` /
:func:`run`) operates over an :class:`EventQueuePort`, so it is unit-testable
with an FSM-faithful fake. :class:`PsycopgEventQueue` is the real adapter over
the #739 Postgres RPCs and the LISTEN socket.

CLI::

    python -m agents.wake_driver                      # block on NOTIFY, drain forever
    python -m agents.wake_driver --watchdog-seconds 120
    python -m agents.wake_driver --once               # one tick (drain + watchdog) then exit
"""

from __future__ import annotations

import argparse
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from dotenv import load_dotenv

from agents.config import load_config
from agents.task_dispatch import (
    DEFAULT_CLAIMED_STALE_SECONDS,
    DEFAULT_RUNNING_REAP_SECONDS,
    ResolveBinary,
    Spawn,
    SupabaseTaskQueue,
    TaskQueuePort,
    _default_resolve_binary,
    _default_spawn,
    drain_tasks,
    reclaim_stale_tasks,
)

if TYPE_CHECKING:
    import psycopg

logger = logging.getLogger(__name__)

# Re-claim a ``claimed`` row after this long with no ``processed`` commit. Also
# the wait-for-wake timeout, so the watchdog runs on an idle queue.
DEFAULT_STALE_AFTER_SECONDS = 300

# Identifies this driver in events.claimed_by for traceability.
CLAIMER = "wake_driver"

# The NOTIFY channel from the #739 substrate (notify_events_insert).
EVENTS_CHANNEL = "events"

# Orchestrator stub returns whatever it likes; the driver only cares that it
# returned without raising before committing ``processed``.
Orchestrator = Callable[[dict[str, Any]], Any]


class EventQueuePort(Protocol):
    """The slice of the events FSM the loop depends on.

    Implemented for real by :class:`PsycopgEventQueue` over the #739 RPCs,
    and by an in-memory fake in the tests.
    """

    def claim_next(self) -> dict[str, Any] | None:
        """Claim the highest-severity ``pending`` event (pending→claimed)."""

    def mark_processed(self, event_id: str, *, action: str = "") -> bool:
        """Commit a ``claimed`` event to ``processed``."""

    def reclaim_stale(self, *, older_than_seconds: float) -> int:
        """Return ``claimed`` rows older than the threshold to ``pending``."""

    def wait_for_wake(self, *, timeout_seconds: float | None) -> bool:
        """Block until a NOTIFY arrives or the timeout elapses.

        Returns ``True`` on a wake signal, ``False`` on timeout.
        """


@dataclass(frozen=True)
class TickResult:
    """What one :func:`tick` did — event watchdog + drain, then task sweep + drain.

    The ``tasks_*`` fields default to 0 so an event-only tick (no ``task_port``)
    constructs unchanged.
    """

    reclaimed: int
    processed: int
    tasks_reclaimed: int = 0
    tasks_reaped: int = 0
    tasks_spawned: int = 0
    tasks_failed: int = 0


def default_orchestrator(event: dict[str, Any]) -> None:
    """Trivial stub orchestrator for this slice — log and return.

    The driver commits ``processed`` after this returns. The real
    local-model router (qwen3 on Workshop) is wired in a later slice and is
    injected, never imported here.
    """
    logger.info(
        "[wake_driver] stub-processing event id=%s type=%s severity=%s",
        event.get("id"),
        event.get("event_type"),
        event.get("severity"),
    )


def drain_pending(port: EventQueuePort, orchestrator: Orchestrator) -> int:
    """Drain every ``pending`` event, one at a time, until the queue is empty.

    Claims, hands the event to ``orchestrator``, then commits ``processed`` —
    advancing to the next event as soon as the prior finishes (no interval).

    Crash-safety: if ``orchestrator`` raises, ``mark_processed`` is **not**
    reached, so the event is left ``claimed`` (recoverable by the watchdog)
    rather than lost or marked done. The exception propagates — a mid-tick
    failure aborts the drain, exactly as a process kill would.
    """
    processed = 0
    while (event := port.claim_next()) is not None:
        orchestrator(event)
        port.mark_processed(str(event["id"]))
        processed += 1
    return processed


def run_watchdog(port: EventQueuePort, *, stale_after_seconds: float) -> int:
    """Re-claim events stranded in ``claimed`` past the threshold.

    Returns the number of rows returned to ``pending``.
    """
    reclaimed = port.reclaim_stale(older_than_seconds=stale_after_seconds)
    if reclaimed:
        logger.info("[wake_driver] watchdog re-claimed %d stale event(s)", reclaimed)
    return reclaimed


def tick(
    port: EventQueuePort,
    orchestrator: Orchestrator,
    *,
    stale_after_seconds: float,
    task_port: TaskQueuePort | None = None,
    task_spawn: Spawn = _default_spawn,
    task_resolve_binary: ResolveBinary = _default_resolve_binary,
    task_claimed_stale_after_seconds: float = DEFAULT_CLAIMED_STALE_SECONDS,
    task_running_reap_after_seconds: float = DEFAULT_RUNNING_REAP_SECONDS,
) -> TickResult:
    """One unit of work — four ordered steps (#909 AC1)::

        reclaim_stale(events) → reclaim_stale_tasks() → drain_pending(events) → drain_tasks()

    Both watchdogs run **before** both drains, so a row stranded by a previous
    crash (event *or* task) is returned to ``pending`` and re-driven within the
    same tick. Tasks are swept and drained only when ``task_port`` is supplied;
    omitting it preserves the original event-only behavior. There is no task
    NOTIFY — a task is born from an event that already woke the driver, or is
    swept by the idle-timeout watchdog (AC1; task-NOTIFY latency deferred to
    #922).
    """
    # Step 1 — event watchdog.
    reclaimed = run_watchdog(port, stale_after_seconds=stale_after_seconds)

    # Step 2 — task watchdog (stale claimed → pending, stale running → failed).
    task_reclaim = None
    if task_port is not None:
        task_reclaim = reclaim_stale_tasks(
            task_port,
            claimed_stale_after_seconds=task_claimed_stale_after_seconds,
            running_reap_after_seconds=task_running_reap_after_seconds,
        )

    # Step 3 — event drain.
    processed = drain_pending(port, orchestrator)

    # Step 4 — task drain (claim → running → spawn, capped, Ordering B).
    task_drain = None
    if task_port is not None:
        task_drain = drain_tasks(task_port, task_spawn, resolve_binary=task_resolve_binary)

    return TickResult(
        reclaimed=reclaimed,
        processed=processed,
        tasks_reclaimed=task_reclaim.reclaimed_claimed if task_reclaim else 0,
        tasks_reaped=task_reclaim.reaped_running if task_reclaim else 0,
        tasks_spawned=task_drain.spawned if task_drain else 0,
        tasks_failed=task_drain.failed if task_drain else 0,
    )


def run(
    port: EventQueuePort,
    orchestrator: Orchestrator = default_orchestrator,
    *,
    stale_after_seconds: float = DEFAULT_STALE_AFTER_SECONDS,
    should_continue: Callable[[], bool] | None = None,
    task_port: TaskQueuePort | None = None,
) -> None:
    """The event-driven loop: block on a wake signal, then run one tick.

    The loop blocks on :meth:`EventQueuePort.wait_for_wake` (the NOTIFY
    socket in the real adapter) with the watchdog interval as its timeout —
    so a NOTIFY *or* an idle timeout both drive a :func:`tick`. There is no
    busy sleep-poll; ``should_continue`` (default: forever) lets tests bound
    the loop.

    When ``task_port`` is supplied, each tick also sweeps and drains the
    ``task_queue`` (#909). The same idle-timeout that runs the event watchdog
    runs the task watchdog, so tasks left ``claimed``/``running`` by a crash
    are swept even on an idle queue.

    A tick that raises is logged and swallowed so a transient failure does
    not tear down the driver — the offending event stays ``claimed`` and the
    watchdog re-claims it next pass (at-least-once, never silently lost).
    """
    keep_going = should_continue or (lambda: True)
    while keep_going():
        port.wait_for_wake(timeout_seconds=stale_after_seconds)
        try:
            tick(port, orchestrator, stale_after_seconds=stale_after_seconds, task_port=task_port)
        except Exception:  # noqa: BLE001 — daemon must survive a bad tick
            logger.exception("[wake_driver] tick failed; event left claimed for watchdog re-claim")


class PsycopgEventQueue:
    """Real :class:`EventQueuePort` over the #739 Postgres substrate.

    Uses the migration RPCs (``claim_next`` / ``mark_processed``) and a
    direct ``UPDATE`` for the watchdog reclaim, and ``LISTEN`` on the
    ``events`` channel for the wake signal. Requires a psycopg connection —
    PostgREST (supabase-py) cannot ``LISTEN``, so this is the one place the
    agents reach Postgres directly.

    Not unit-tested (needs a live DB); kept thin so the tested loop above
    carries the logic.
    """

    def __init__(self, conn: psycopg.Connection, *, claimer: str = CLAIMER) -> None:
        self._conn = conn
        self._claimer = claimer
        self._conn.execute(f"LISTEN {EVENTS_CHANNEL}")
        self._conn.commit()

    def claim_next(self) -> dict[str, Any] | None:
        with self._conn.cursor() as cur:
            cur.execute("SELECT * FROM claim_next(%s)", (self._claimer,))
            row = cur.fetchone()
            if row is None:
                return None
            cols = [d.name for d in cur.description]
        self._conn.commit()
        return dict(zip(cols, row, strict=True))

    def mark_processed(self, event_id: str, *, action: str = "") -> bool:
        with self._conn.cursor() as cur:
            cur.execute("SELECT mark_processed(%s, %s, %s)", (event_id, self._claimer, action))
            ok = bool(cur.fetchone()[0])
        self._conn.commit()
        return ok

    def reclaim_stale(self, *, older_than_seconds: float) -> int:
        with self._conn.cursor() as cur:
            cur.execute(
                "UPDATE events SET state = 'pending', claimed_at = NULL, claimed_by = NULL "
                "WHERE state = 'claimed' "
                "AND claimed_at < now() - make_interval(secs => %s) "
                "RETURNING id",
                (older_than_seconds,),
            )
            count = len(cur.fetchall())
        self._conn.commit()
        return count

    def wait_for_wake(self, *, timeout_seconds: float | None) -> bool:
        for _notify in self._conn.notifies(timeout=timeout_seconds, stop_after=1):
            return True
        return False


def _build_psycopg_queue() -> PsycopgEventQueue:
    import psycopg

    cfg = load_config()
    conn = psycopg.connect(cfg.postgres_url, autocommit=False)
    return PsycopgEventQueue(conn)


def main() -> int:
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--watchdog-seconds",
        type=int,
        default=DEFAULT_STALE_AFTER_SECONDS,
        help=(
            "Re-claim claimed rows older than this many seconds; also the "
            f"wait-for-wake timeout (default: {DEFAULT_STALE_AFTER_SECONDS})"
        ),
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single tick (watchdog + drain) and exit (smoke test).",
    )
    args = parser.parse_args()

    queue = _build_psycopg_queue()
    task_port = SupabaseTaskQueue()  # tasks ride supabase-py; events ride psycopg
    if args.once:
        result = tick(
            queue,
            default_orchestrator,
            stale_after_seconds=args.watchdog_seconds,
            task_port=task_port,
        )
        logger.info(
            "[wake_driver] one-shot tick: reclaimed=%d processed=%d "
            "tasks_reclaimed=%d tasks_reaped=%d tasks_spawned=%d tasks_failed=%d",
            result.reclaimed,
            result.processed,
            result.tasks_reclaimed,
            result.tasks_reaped,
            result.tasks_spawned,
            result.tasks_failed,
        )
        return 0

    logger.info(
        "[wake_driver] listening on '%s' channel (watchdog=%ss, Ctrl-C to stop)",
        EVENTS_CHANNEL,
        args.watchdog_seconds,
    )
    try:
        run(
            queue,
            default_orchestrator,
            stale_after_seconds=args.watchdog_seconds,
            task_port=task_port,
        )
    except KeyboardInterrupt:
        logger.info("[wake_driver] KeyboardInterrupt — stopping")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
