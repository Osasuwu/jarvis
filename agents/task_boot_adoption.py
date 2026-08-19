"""task_boot_adoption — re-adopt live processes from the sidecar directory at driver boot.

Extracted from ``agents/wake_driver.py``'s ``run()`` (#1608, milestone #66 —
task_dispatch decomposition 4/7). Pure extraction, no behavior change:
``wake_driver.run()`` calls :func:`maybe_adopt_at_boot` directly (shape (b) —
no event bus, no plugin registry) in place of the inline AC3 (#952) block.

Note on the issue's file reference: despite the issue title ("extract...from
agents/task_dispatch.py"), the code being extracted here never lived in
``task_dispatch.py`` — it lived inline in ``wake_driver.run()``. The title is
inherited template phrasing shared across all 7 milestone #66 slices; each
slice's actual code location was confirmed independently (#1608 PR body).

The extraction is also what makes this logic unit-testable at all:
``run()``'s gate for this block requires ``should_continue=None``, which
makes ``run()``'s own ``while keep_going():`` loop unbounded (no existing
test exercises that combination for that reason). Pulling the gate condition
and body into a standalone, directly-callable function sidesteps that
entirely — every case here is exercised by calling the function directly,
never by invoking ``run()``'s loop.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from agents.pid_sidecar import Sidecar
from agents.task_dispatch import TrackedProc

if TYPE_CHECKING:
    from agents.task_dispatch import TaskQueuePort

logger = logging.getLogger(__name__)


def maybe_adopt_at_boot(
    *,
    task_port: TaskQueuePort | None,
    procs: dict[str, TrackedProc] | None,
    should_continue: Callable[[], bool] | None,
    task_clock: Callable[[], float],
    sidecar_factory: Callable[[], Sidecar] = Sidecar,
) -> Sidecar | None:
    """Re-adopt live processes from the sidecar directory (AC3, #952).

    Only fires in resident mode: ``task_port`` supplied, ``procs`` map
    exists, and ``should_continue`` is ``None`` — the same three-way gate
    the inline block in ``wake_driver.run()`` used before extraction (a
    test-bounded loop, i.e. any explicit ``should_continue``, is never
    boot). Any other shape is a no-op returning ``None``.

    Adoption failure is non-fatal: logged and swallowed, leaving every row
    to be treated as an orphan by the reaper backstop, rather than tearing
    down the driver at boot.
    """
    if task_port is None or procs is None or should_continue is not None:
        return None
    try:
        sidecar = sidecar_factory()
        for task_id, proc in sidecar.adopt_live_processes():
            procs[task_id] = TrackedProc(proc=proc, started_at=task_clock())
        return sidecar
    except Exception:  # noqa: BLE001 — boot adoption failure is non-fatal
        logger.exception(
            "[task_boot_adoption] boot adoption failed; will treat all rows as orphans"
        )
        return None
