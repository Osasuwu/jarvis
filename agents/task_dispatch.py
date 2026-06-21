"""task_dispatch — close the reactive forward path (#909).

The reactive forward path is now closed end-to-end (#741/#744 → #909 → #921)::

    event → wake_driver → orchestrator.handle_event
          → task_queue.enqueue(row) → drain_tasks → executor.spawn
          → poll_completions → running → done | failed

:func:`drain_tasks` claims pending ``sandcastle`` rows, transitions each to
``running``, and fires ``executor.spawn(goal)`` — symmetric to how
:func:`wake_driver.drain_pending` drains *events*. The spawned processes are
handed back as :attr:`DrainResult.procs`; :func:`poll_completions` (#921)
closes each row when its process exits — exit 0 → ``done``, non-zero →
``failed``. **Model P semantics: ``done`` means the spawned process exited
cleanly, nothing more** — not task success, not PR-merged. Outcome truth
re-enters externally via GitHub Path-A workflows as fresh *events*.

**Restart limitation (#921):** the proc map lives only in the driver process.
A restart forgets every live process — those rows age out and the orphan
reaper (:func:`reclaim_stale_tasks`) fails them as a backstop, which Path A
then self-heals. A PID sidecar that survives restarts is #952.

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
import subprocess
import sys
import time
from collections.abc import Callable, Collection
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from agents import task_queue
from agents.pid_sidecar import Sidecar

logger = logging.getLogger(__name__)

# Only sandcastle rows are auto-spawned; assignee='owner' escalation rows are
# never claimed by the drain (AC2).
DEFAULT_ASSIGNEE = "sandcastle"

# Max concurrent running sandcastle tasks (AC3). Measures compute concurrency:
# slots free as soon as poll_completions observes the process exit (#921).
DEFAULT_CONCURRENCY_CAP = 5

# A row stuck in ``claimed`` past this long means the drainer died between the
# claim and the running transition — no process exists, so it is safe to return
# to ``pending`` (AC5). Matches the wake_driver event watchdog default.
DEFAULT_CLAIMED_STALE_SECONDS = 300

# One 6h knob, two consumers (#921): rows whose process the driver no longer
# tracks (orphans — e.g. after a restart) are reaped to ``failed`` past this
# age, and *tracked* processes still alive past it are tree-killed as runaways.
# Deliberately generous (≫ normal task runtime); live tracked rows under the
# threshold are never time-reaped (AC5).
DEFAULT_RUNNING_REAP_SECONDS = 6 * 60 * 60

# Spawn a task's goal, fire-and-forget. Raises on a hard launch failure (AC7b).
Spawn = Callable[[str], Any]
# Resolve the claude binary; raises FileNotFoundError when unresolved (AC7a).
ResolveBinary = Callable[[], str]
# Quota probe — returns a UsageReading-shaped object with .near_exhaustion
# (#921 AC4). The production default is false-safe: it never raises, a probe
# error reads as near-exhaustion, so a broken probe pauses dispatch.
ReadUsage = Callable[[], Any]


@runtime_checkable
class TaskQueuePort(Protocol):
    """The slice of the task FSM the dispatch loop depends on (AC10).

    Implemented for real by :class:`SupabaseTaskQueue` over
    :mod:`agents.task_queue`, and by an in-memory fake in the tests.

    ``runtime_checkable`` makes ``isinstance(x, TaskQueuePort)`` check only that
    the six method *names* are present — not their signatures — so the
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

    def requeue_running(self, task_id: str) -> bool:
        """Return one process-less ``running`` row to ``pending`` (direct UPDATE, #921 AC4)."""


@dataclass(frozen=True)
class DrainResult:
    """What one :func:`drain_tasks` did."""

    spawned: int = 0
    failed: int = 0
    # True iff the whole drain was skipped because the claude binary did not
    # resolve (AC7a) — distinct from "ran, claimed nothing".
    skipped_no_binary: bool = False
    # True iff the drain skipped/stopped on quota near-exhaustion — either the
    # AC4 pre-flight (nothing claimed) or a mid-drain throttled spawn (the one
    # in-flight row is requeued to ``pending``; on requeue failure the AC6
    # reaper is the backstop). Remaining rows stay ``pending`` and self-heal.
    throttled: bool = False
    # (task_id, proc) per *successful* spawn that yielded a pollable process
    # handle (#921 AC1). A raising spawn never reaches the append; a throttled
    # spawn returns early (the whole drain stops) before it; a result without
    # a ``proc`` attribute counts as spawned but is skipped here. The
    # wake_driver folds these pairs into its {task_id: TrackedProc} liveness
    # map to close running→done on process exit.
    procs: tuple[tuple[str, Any], ...] = ()


@dataclass(frozen=True)
class ReclaimResult:
    """What one :func:`reclaim_stale_tasks` did."""

    reclaimed_claimed: int = 0
    reaped_running: int = 0


@dataclass(frozen=True)
class TrackedProc:
    """A live spawn under liveness tracking (#921 AC2).

    ``proc`` is the ``Popen``-shaped handle from :class:`executor.SpawnResult`;
    ``started_at`` is a monotonic-clock stamp taken when the wake_driver folded
    the pair into its map (the runaway check measures age against it, AC6).
    """

    proc: Any
    started_at: float


@dataclass(frozen=True)
class CompletionResult:
    """What one :func:`poll_completions` did (#921 AC2)."""

    done: int = 0
    failed_exit: int = 0


def poll_completions(
    port: TaskQueuePort,
    procs: dict[str, TrackedProc],
    *,
    sidecar: Sidecar | None = None,
) -> CompletionResult:
    """Close ``running`` rows whose process has exited (#921 AC2, Model P).

    For each tracked pair: ``poll() is None`` → still running, kept;
    ``poll() == 0`` → ``transition(done)``; ``poll() != 0`` →
    ``transition(failed, reason="exit <rc>")``. The DB transition is what frees
    the cap slot (``count_running`` drops) for the same tick's drain; dropping
    the closed entry from ``procs`` (mutated in place) just stops it from being
    re-polled and shields the row from the watchdogs.

    **``done`` means the process exited 0 — nothing more.** Not task success,
    not PR merged; the child may have produced garbage and exited cleanly.
    Outcome truth re-enters externally via Path-A GitHub events.

    Per-row isolation: a ``transition`` raising logs, drops the entry, and
    continues — the row stays ``running`` in the store with no live handle, so
    the AC5/AC6 orphan reaper is the backstop. No counter is incremented for it.
    """
    done = 0
    failed_exit = 0
    for task_id, tracked in list(procs.items()):
        rc = tracked.proc.poll()
        if rc is None:
            continue
        try:
            if rc == 0:
                port.transition(task_id, "done")
                done += 1
            else:
                port.transition(task_id, "failed", reason=f"exit {rc}")
                failed_exit += 1
        except Exception:  # noqa: BLE001 — isolate one bad row, reaper backstops it
            logger.exception(
                "[task_dispatch] completion transition for task %s failed; "
                "dropped from tracking (reaper backstop)",
                task_id,
            )
        finally:
            # AC6 (#952) — delete sidecar on terminal transition.
            if sidecar is not None:
                try:
                    sidecar.delete_sidecar_file(task_id)
                except Exception:  # noqa: BLE001 — sidecar delete is best-effort
                    logger.exception(
                        "[task_dispatch] sidecar delete failed for task %s",
                        task_id,
                    )
            procs.pop(task_id, None)
    return CompletionResult(done=done, failed_exit=failed_exit)


def kill_process_tree(proc: Any, *, platform: str = sys.platform) -> None:
    """Kill a spawned process AND its children (#921 AC6).

    On Windows ``Popen.kill()`` is an alias for ``terminate()`` — it kills only
    the direct process, and a ``claude -p`` child's own subprocesses (git, gh,
    tools) survive as orphans. ``taskkill /PID <pid> /T /F`` walks the tree; if
    taskkill itself can't launch (stripped PATH), degrade to ``proc.kill()`` —
    direct child only, better than leaving the runaway alive.

    POSIX gets plain ``proc.kill()`` — direct child only. ``os.killpg`` would
    be WRONG here: :func:`executor.spawn` does not pass
    ``start_new_session=True``, so the child shares the driver's process group
    and ``killpg`` would kill the driver itself. A POSIX tree-kill needs the
    spawn-side change first; production runs on Windows, so this is deferred.

    Best-effort ``wait`` afterwards reaps the handle so ``poll()`` reflects the
    death immediately; a hung wait is swallowed (the next tick's poll re-checks).
    """
    if platform == "win32":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                capture_output=True,
                check=False,
            )
        except OSError:  # taskkill missing/unlaunchable — degrade to direct kill
            logger.exception(
                "[task_dispatch] taskkill unavailable for pid %s; "
                "falling back to Popen.kill() (children may survive)",
                proc.pid,
            )
            proc.kill()
    else:
        proc.kill()
    try:
        proc.wait(timeout=10)
    except Exception:  # noqa: BLE001 — reap is best-effort; poll re-checks next tick
        pass


def kill_runaways(
    port: TaskQueuePort,
    procs: dict[str, TrackedProc],
    *,
    max_runtime_seconds: float = DEFAULT_RUNNING_REAP_SECONDS,
    now: Callable[[], float] = time.monotonic,
    kill: Callable[[Any], None] = kill_process_tree,
    sidecar: Sidecar | None = None,
) -> int:
    """Tree-kill live processes that exceeded the max runtime (#921 AC6).

    The orphan reaper (:func:`reclaim_stale_tasks`) deliberately skips rows
    with a live tracked process — this is the counterpart that bounds those:
    a process still alive past ``max_runtime_seconds`` (same one 6h knob as
    the reaper) is killed with its whole tree, its row transitioned
    ``running → failed`` (``reason="killed: exceeded max runtime"``), and the
    entry dropped. Killed runaways fold into the tick's failed-exit counter.

    Already-exited processes are skipped — :func:`poll_completions` owns those
    (their real exit code decides done vs failed). Per-row isolation: a *kill*
    raising keeps the entry (the process may still be alive; failing the row
    would lie — retried next tick); a *transition* raising after a successful
    kill drops the entry to the reaper backstop, like ``poll_completions``.
    """
    killed = 0
    for task_id, tracked in list(procs.items()):
        if tracked.proc.poll() is not None:
            continue  # exited — poll_completions closes it with the real rc
        if now() - tracked.started_at <= max_runtime_seconds:
            continue
        try:
            kill(tracked.proc)
        except Exception:  # noqa: BLE001 — possibly still alive; retry next tick
            logger.exception(
                "[task_dispatch] tree-kill of runaway task %s failed; will retry",
                task_id,
            )
            continue
        try:
            port.transition(task_id, "failed", reason="killed: exceeded max runtime")
            killed += 1
        except Exception:  # noqa: BLE001 — killed but row not closed; reaper backstops
            logger.exception(
                "[task_dispatch] runaway task %s killed but transition failed; "
                "dropped from tracking (reaper backstop)",
                task_id,
            )
        finally:
            # AC4 (#952) — delete sidecar when tree-killing orphan.
            if sidecar is not None:
                try:
                    sidecar.delete_sidecar_file(task_id)
                except Exception:  # noqa: BLE001 — sidecar delete is best-effort
                    logger.exception(
                        "[task_dispatch] sidecar delete failed for runaway task %s",
                        task_id,
                    )
            procs.pop(task_id, None)
    return killed


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


def default_read_usage() -> Any:
    """Production quota-probe adapter (lazy import; see :func:`default_spawn`).

    :func:`agents.usage_probe.read_usage` is false-safe — it never raises, a
    probe failure returns ``near_exhaustion=True`` — so the AC4 pre-flight
    pauses dispatch rather than flooding it when the probe is broken.
    """
    from agents.usage_probe import read_usage

    return read_usage()


def drain_tasks(
    port: TaskQueuePort,
    spawn: Spawn = default_spawn,
    *,
    assignee: str = DEFAULT_ASSIGNEE,
    cap: int = DEFAULT_CONCURRENCY_CAP,
    resolve_binary: ResolveBinary = default_resolve_binary,
    read_usage: ReadUsage = default_read_usage,
    sidecar: Sidecar | None = None,
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
    launched) stops the drain — the one in-flight row is requeued to
    ``pending`` (#921 AC4; reaper backstop if the requeue fails), the rest stay
    ``pending``; quota will not recover mid-drain.
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

    # AC4 (#921) — quota pre-flight, once per drain. Near-exhaustion skips the
    # *entire* drain: zero claims, zero churn, rows stay visibly ``pending``
    # until quota recovers. The default probe is false-safe (a probe error
    # reads as near-exhaustion), so a broken probe pauses dispatch too.
    # executor.spawn re-checks per spawn — that per-spawn gate remains the
    # backstop for a quota flip mid-drain.
    reading = read_usage()
    if getattr(reading, "near_exhaustion", False):
        logger.warning(
            "[task_dispatch] quota near-exhaustion at drain start; skipping drain "
            "(no claims, rows stay pending until quota recovers)"
        )
        return DrainResult(throttled=True)

    # AC3 — budget sampled once at drain start.
    budget = cap - port.count_running(assignee=assignee)
    if budget <= 0:
        return DrainResult()

    spawned = 0
    failed = 0
    procs: list[tuple[str, Any]] = []
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
            try:
                port.transition(task_id, "failed", reason=f"spawn raised: {exc}")
            except Exception:  # noqa: BLE001 — the failed-mark itself can raise; an
                # escape here would discard the already-spawned handles in ``procs``
                # (orphans for the 6h reaper). Row stays running; reaper backstops.
                logger.exception(
                    "[task_dispatch] could not mark task %s failed after spawn raise; "
                    "row left running for the reaper",
                    task_id,
                )
            failed += 1
            continue

        # The executor declined to launch (quota near-exhaustion): no process
        # exists, but the row is already ``running`` (Ordering B). Requeue it to
        # ``pending`` so the next drain retries as soon as quota recovers
        # (#921 AC4) — without this it would strand 6h until the reaper failed
        # a task that never ran. Quota won't recover mid-drain, so stop
        # claiming. Not a spawn failure → not counted.
        if getattr(result, "throttled", False):
            try:
                requeued = port.requeue_running(task_id)
            except Exception:  # noqa: BLE001 — requeue is best-effort
                requeued = False
                logger.exception("[task_dispatch] requeue of throttled task %s raised", task_id)
            logger.warning(
                "[task_dispatch] spawn throttled (quota near-exhaustion); "
                "stopping drain — task %s %s",
                task_id,
                "requeued to pending" if requeued else "left running for the reaper",
            )
            return DrainResult(spawned=spawned, failed=failed, throttled=True, procs=tuple(procs))

        spawned += 1
        # AC1 (#921) — retain the process handle so the wake_driver can poll
        # completion. Spawns without a handle (test fakes, defensive None)
        # still count as spawned but cannot be liveness-tracked.
        proc = getattr(result, "proc", None)
        if proc is not None:
            procs.append((task_id, proc))
            # AC2 (#952) — record spawn to sidecar for restart liveness recovery.
            if sidecar is not None:
                try:
                    pid = proc.pid if hasattr(proc, "pid") else proc.pid
                    create_time = proc.create_time() if hasattr(proc, "create_time") else time.time()
                    sidecar.record_spawn(task_id, pid, create_time)
                except Exception:  # noqa: BLE001 — sidecar write is best-effort
                    logger.exception(
                        "[task_dispatch] sidecar record_spawn failed for task %s; "
                        "liveness tracking degraded but task continues",
                        task_id,
                    )

    return DrainResult(spawned=spawned, failed=failed, procs=tuple(procs))


def reclaim_stale_tasks(
    port: TaskQueuePort,
    *,
    assignee: str = DEFAULT_ASSIGNEE,
    claimed_stale_after_seconds: float = DEFAULT_CLAIMED_STALE_SECONDS,
    running_reap_after_seconds: float = DEFAULT_RUNNING_REAP_SECONDS,
    live_task_ids: Collection[str] = (),
) -> ReclaimResult:
    """Sweep stranded tasks before a drain (#909 AC5/AC6, #921 AC5 orphan-only).

    - **Stale claimed** rows return to ``pending`` via a direct UPDATE that
      bypasses the FSM (``claimed → pending`` is not a legal transition; this
      mirrors :meth:`wake_driver.PsycopgEventQueue.reclaim_stale`). Never
      touches ``running``.
    - **Orphaned running** rows — stale AND not in ``live_task_ids`` — are
      transitioned ``running → failed`` so rows with no process behind them (a
      child that died without a completion, a crash in the running↔spawn
      window, a pre-restart spawn) stop ratcheting the cap toward 0.

    ``live_task_ids`` is the wake_driver's tracked-process map keyset (#921
    AC5): a row with a live handle is *not* an orphan however old — legitimate
    long tasks are never time-reaped; genuinely stuck live processes are
    :func:`kill_runaways`' job, which kills the tree and closes the row
    explicitly. Restart semantics: a fresh driver has an empty map, so every
    stale running row is an orphan again (AC7 — the map does not survive
    restart; the backstop self-heals via Path-A).

    Invoked by :func:`wake_driver.tick` *before* :func:`drain_tasks`, so a row
    reclaimed this pass is eligible to be re-claimed and spawned in the same
    tick — symmetric to the event watchdog running before ``drain_pending``.
    """
    # Stale claimed → pending (FSM-bypassing direct UPDATE).
    reclaimed = port.reclaim_stale_claimed(
        assignee=assignee, older_than_seconds=claimed_stale_after_seconds
    )

    # Orphaned running → failed (stale + no tracked live process).
    reaped = 0
    for row in port.list_stale_running(
        assignee=assignee, older_than_seconds=running_reap_after_seconds
    ):
        task_id = str(row["id"])
        if task_id in live_task_ids:
            continue
        try:
            port.transition(
                task_id,
                "failed",
                reason=(
                    f"reaped: orphaned running row (no tracked process) "
                    f"after {running_reap_after_seconds:.0f}s"
                ),
            )
            reaped += 1
        except Exception:  # noqa: BLE001 — isolate one bad row; the rest still reap
            logger.exception(
                "[task_dispatch] orphan reap of task %s failed; retried next sweep",
                task_id,
            )

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

    def requeue_running(self, task_id: str) -> bool:
        return task_queue.requeue_running(task_id)
