"""task_dispatch — close the reactive forward path (#909).

The reactive forward path was left open after #741/#744::

    event → wake_driver → orchestrator.handle_event
          → task_queue.enqueue(row) → ❌ MISSING → executor.spawn

Nothing claimed a pending ``task_queue`` row and called :func:`executor.spawn`.
This module is the missing link: :func:`drain_tasks` claims pending
``sandcastle`` rows, transitions each to ``running``, and fires
``executor.spawn(goal)`` — symmetric to how :func:`wake_driver.drain_pending`
drains *events*. Completion (``running → done``) re-enters **externally** via
GitHub Path-A workflows as a fresh ``event`` (no internal polling; closure
deferred to #921).

Design mirrors :mod:`agents.wake_driver`: the pure logic
(:func:`drain_tasks` / :func:`reclaim_stale_tasks`) runs over a
:class:`TaskQueuePort` Protocol, so it is unit-testable with an in-memory fake
(fake queue + fake spawn + fake running-count) — no live DB, no real
``claude -p``. :class:`SupabaseTaskQueue` is the thin real adapter over
:mod:`agents.task_queue` (supabase-py / PostgREST). Events ride raw psycopg
(they need ``LISTEN``); tasks ride supabase-py — the split is deliberate (AC10).

Crash-safety follows **Ordering B** (grill decision ``2489782f``): per task,
``claim → transition(running) → spawn``. Transitioning to ``running`` *before*
the spawn means a crash in the window leaves the row ``running`` (swept by the
generous reaper, AC6) rather than ``claimed`` with a live process — the latter
would let the claimed-reclaimer (AC5) hand the same task to a second spawn.
``claimed`` therefore strictly means *claimed-but-not-yet-spawned*.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from agents import task_queue

logger = logging.getLogger(__name__)

# Only sandcastle rows are auto-spawned; assignee='owner' escalation rows are
# never claimed by the drain (AC2).
DEFAULT_ASSIGNEE = "sandcastle"

# Max concurrent running sandcastle tasks (AC3). Until #921 wires real
# completion closure, the loop self-throttles to this cap.
DEFAULT_CONCURRENCY_CAP = 5

# A row stuck in ``claimed`` past this long means the drainer died between the
# claim and the running transition — no process exists, so it is safe to return
# to ``pending`` (AC5). Matches the wake_driver event watchdog default.
DEFAULT_CLAIMED_STALE_SECONDS = 300

# A ``running`` row older than this is reaped to ``failed`` (AC6). Deliberately
# generous (≫ normal task runtime) — a crude time-based stopgap until #921 adds
# a liveness-aware reaper. Its only job is to stop orphaned rows ratcheting the
# cap toward 0.
DEFAULT_RUNNING_REAP_SECONDS = 6 * 60 * 60

# Spawn a task's goal, fire-and-forget. Raises on a hard launch failure (AC7b).
Spawn = Callable[[str], Any]
# Resolve the claude binary; raises FileNotFoundError when unresolved (AC7a).
ResolveBinary = Callable[[], str]


@runtime_checkable
class TaskQueuePort(Protocol):
    """The slice of the task FSM the dispatch loop depends on (AC10).

    Implemented for real by :class:`SupabaseTaskQueue` over
    :mod:`agents.task_queue`, and by an in-memory fake in the tests.

    ``runtime_checkable`` makes ``isinstance(x, TaskQueuePort)`` check only that
    the five method *names* are present — not their signatures — so the
    ``isinstance`` assertion in the tests is a structural smoke check, not a
    full conformance proof.
    """

    def claim_next(self, *, assignee: str) -> dict[str, Any] | None:
        """Claim the highest-priority pending row for ``assignee`` (pending→claimed)."""

    def count_running(self, *, assignee: str) -> int:
        """Count rows currently ``running`` for ``assignee`` (concurrency cap)."""

    def transition(
        self, task_id: str, to_status: str, *, reason: str | None = None
    ) -> dict[str, Any]:
        """Advance a task through the FSM (validated in the real adapter)."""

    def reclaim_stale_claimed(self, *, assignee: str, older_than_seconds: float) -> int:
        """Return stale ``claimed`` rows to ``pending`` (direct UPDATE, FSM-bypassing)."""

    def list_stale_running(
        self, *, assignee: str, older_than_seconds: float
    ) -> list[dict[str, Any]]:
        """List ``running`` rows older than the reaper threshold for ``assignee``."""


@dataclass(frozen=True)
class DrainResult:
    """What one :func:`drain_tasks` did."""

    spawned: int = 0
    failed: int = 0
    # True iff the whole drain was skipped because the claude binary did not
    # resolve (AC7a) — distinct from "ran, claimed nothing".
    skipped_no_binary: bool = False
    # True iff the drain stopped early because a spawn was throttled (quota
    # near-exhaustion). The one in-flight row is left ``running`` for the AC6
    # reaper; remaining rows stay ``pending`` and self-heal next drain.
    throttled: bool = False


@dataclass(frozen=True)
class ReclaimResult:
    """What one :func:`reclaim_stale_tasks` did."""

    reclaimed_claimed: int = 0
    reaped_running: int = 0


def default_spawn(goal: str) -> Any:
    """Production spawn adapter — fire-and-forget ``claude -p`` via the executor.

    Returns the :class:`executor.SpawnResult`. A throttled result (quota
    near-exhaustion) means no process launched; :func:`drain_tasks` inspects the
    ``throttled`` flag and stops the drain rather than counting a phantom spawn.
    Imported lazily so the tested drain logic (which injects its own spawn) need
    not pull executor's subprocess/usage-probe dependencies.
    """
    from agents.executor import spawn as executor_spawn

    return executor_spawn(goal)


def default_resolve_binary() -> str:
    """Production binary-resolution adapter (lazy import; see :func:`default_spawn`)."""
    from agents.executor import _resolve_claude_binary

    return _resolve_claude_binary()


def drain_tasks(
    port: TaskQueuePort,
    spawn: Spawn = default_spawn,
    *,
    assignee: str = DEFAULT_ASSIGNEE,
    cap: int = DEFAULT_CONCURRENCY_CAP,
    resolve_binary: ResolveBinary = default_resolve_binary,
) -> DrainResult:
    """Claim pending ``assignee`` tasks up to the cap and spawn each (AC2–AC4, AC7–AC9).

    Order of operations:

    1. **Pre-flight binary resolution, once (AC7a).** If the claude binary does
       not resolve — missing, not executable, or the executor import is broken —
       skip the *entire* drain: zero claims, nothing marked ``failed``, every
       row stays ``pending`` so the next drain self-heals once the env is fixed.
       No internal retry.
    2. **Budget, sampled once (AC3).** ``budget = cap − count_running(assignee)``.
       Nothing exits ``running`` mid-drain, so the snapshot is exact; the loop
       spawns at most ``budget`` tasks and leaves the rest ``pending``.
    3. **Per task, Ordering B (AC4).** ``claim_next`` (pending→claimed) →
       ``transition(running)`` → ``spawn(goal)``. The running transition
       precedes the spawn so a crash in the window can only strand a ``running``
       row (reaped, AC6), never a ``claimed`` row with a live process (which
       would double-spawn under the AC5 reclaimer).

    A ``claim_next`` returning ``None`` (empty queue or lost race, AC9) breaks
    the loop cleanly. A ``transition(running)`` raising leaves the row
    ``claimed`` (no process launched) for the AC5 reclaimer and skips to the
    next slot. A ``spawn`` raising (AC7b) marks *that* task ``running→failed``
    (terminal — the external event loop re-drives) and the drain continues. A
    ``spawn`` returning a *throttled* result (quota near-exhaustion: no process
    launched) stops the drain — the one in-flight row is left ``running`` for
    the AC6 reaper, the rest stay ``pending``; quota will not recover mid-drain.
    """
    # AC7a — pre-flight once; an unusable binary skips the whole drain. Widened
    # past FileNotFoundError to the other no-usable-binary failures (not
    # executable → PermissionError; broken executor import → ImportError): all
    # mean "cannot spawn", so skip-and-self-heal beats claim-and-strand.
    try:
        resolve_binary()
    except (FileNotFoundError, PermissionError, ImportError):
        logger.warning(
            "[task_dispatch] claude binary unresolved; skipping drain "
            "(no claims, rows stay pending, self-heals when env is fixed)"
        )
        return DrainResult(skipped_no_binary=True)

    # AC3 — budget sampled once at drain start.
    budget = cap - port.count_running(assignee=assignee)
    if budget <= 0:
        return DrainResult()

    spawned = 0
    failed = 0
    for _ in range(budget):
        row = port.claim_next(assignee=assignee)  # AC2 routing; AC9 lost-race → None
        if row is None:
            break
        task_id = str(row["id"])

        # AC4 Ordering B — running BEFORE spawn. Guard it: a transient store
        # error here leaves the row ``claimed`` with no process, so the AC5
        # reclaimer returns it to ``pending``. Skip to the next slot rather than
        # spawn against a row we failed to mark running.
        try:
            port.transition(task_id, "running")
        except Exception:  # noqa: BLE001 — isolate a transient transition error
            logger.exception(
                "[task_dispatch] could not mark task %s running; left claimed for the reclaimer",
                task_id,
            )
            continue

        try:
            result = spawn(row["goal"])  # AC8 billing-trap rides executor._sanitize_env
        except Exception as exc:  # noqa: BLE001 — AC7b: isolate one bad spawn
            # AC7b — terminal failure; no internal retry, external loop re-drives.
            port.transition(task_id, "failed", reason=f"spawn raised: {exc}")
            failed += 1
            continue

        # The executor declined to launch (quota near-exhaustion): no process
        # exists, but the row is already ``running`` (reaped by AC6 — bounded to
        # this one row). Quota won't recover mid-drain, so stop claiming rather
        # than strand the whole budget. Not a spawn failure → not counted.
        if getattr(result, "throttled", False):
            logger.warning(
                "[task_dispatch] spawn throttled (quota near-exhaustion); "
                "stopping drain — task %s left running for the reaper",
                task_id,
            )
            return DrainResult(spawned=spawned, failed=failed, throttled=True)

        spawned += 1

    return DrainResult(spawned=spawned, failed=failed)


def reclaim_stale_tasks(
    port: TaskQueuePort,
    *,
    assignee: str = DEFAULT_ASSIGNEE,
    claimed_stale_after_seconds: float = DEFAULT_CLAIMED_STALE_SECONDS,
    running_reap_after_seconds: float = DEFAULT_RUNNING_REAP_SECONDS,
) -> ReclaimResult:
    """Sweep stranded tasks before a drain (AC5 + AC6).

    - **AC5** — stale ``claimed`` rows return to ``pending`` via a direct UPDATE
      that bypasses the FSM (``claimed → pending`` is not a legal transition;
      this mirrors :meth:`wake_driver.PsycopgEventQueue.reclaim_stale`). Never
      touches ``running``.
    - **AC6** — stale ``running`` rows (older than the generous reaper
      threshold) are transitioned ``running → failed`` so orphaned rows (a
      child that died without opening a PR, or a crash in the running↔spawn
      window) stop ratcheting the cap toward 0. A fresh ``running`` row is left
      untouched because the port's staleness query excludes it.

    Invoked by :func:`wake_driver.tick` *before* :func:`drain_tasks`, so a row
    reclaimed this pass is eligible to be re-claimed and spawned in the same
    tick — symmetric to the event watchdog running before ``drain_pending``.
    """
    # AC5 — stale claimed → pending (FSM-bypassing direct UPDATE).
    reclaimed = port.reclaim_stale_claimed(
        assignee=assignee, older_than_seconds=claimed_stale_after_seconds
    )

    # AC6 — stale running → failed (time-based stopgap; #921 = liveness-aware).
    reaped = 0
    for row in port.list_stale_running(
        assignee=assignee, older_than_seconds=running_reap_after_seconds
    ):
        port.transition(
            str(row["id"]),
            "failed",
            reason=f"reaped: no completion within {running_reap_after_seconds:.0f}s",
        )
        reaped += 1

    return ReclaimResult(reclaimed_claimed=reclaimed, reaped_running=reaped)


class SupabaseTaskQueue:
    """Real :class:`TaskQueuePort` over :mod:`agents.task_queue` (AC10).

    Thin delegation — the FSM and SQL live in :mod:`agents.task_queue`. Tasks
    stay on supabase-py (PostgREST); only events need raw psycopg (``LISTEN``),
    so this is the task-side analogue of
    :class:`wake_driver.PsycopgEventQueue`. Constructible without touching the
    network (each call resolves the Supabase client lazily inside
    ``task_queue``). Not unit-tested (needs live Supabase); the tested logic
    lives in :func:`drain_tasks` / :func:`reclaim_stale_tasks` above.
    """

    def claim_next(self, *, assignee: str) -> dict[str, Any] | None:
        return task_queue.claim_next(assignee=assignee)

    def count_running(self, *, assignee: str) -> int:
        return task_queue.count_running(assignee=assignee)

    def transition(
        self, task_id: str, to_status: str, *, reason: str | None = None
    ) -> dict[str, Any]:
        return task_queue.transition(task_id, to_status, reason=reason)

    def reclaim_stale_claimed(self, *, assignee: str, older_than_seconds: float) -> int:
        return task_queue.reclaim_stale_claimed(
            assignee=assignee, older_than_seconds=older_than_seconds
        )

    def list_stale_running(
        self, *, assignee: str, older_than_seconds: float
    ) -> list[dict[str, Any]]:
        return task_queue.list_stale_running(
            assignee=assignee, older_than_seconds=older_than_seconds
        )
