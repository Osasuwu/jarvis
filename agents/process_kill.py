"""process_kill — tree-kill a spawned process and its children.

Extracted from ``agents/task_dispatch.py`` (#1609, milestone #66 —
task_dispatch decomposition 5/7) and de-duplicated against the equivalent
kill logic that used to live inline in ``agents/pid_sidecar.py``
(``kill_orphan_process``). Both call sites now import :func:`kill_process_tree`
from here rather than each maintaining their own copy (AC3/AC4).

``proc`` is duck-typed: only ``.pid``, ``.kill()``, and ``.wait(timeout=...)``
are required, so both a tracked ``subprocess.Popen``-style handle
(``task_dispatch.py``) and a ``psutil.Process`` orphan lookup
(``pid_sidecar.py``) satisfy the interface.
"""

from __future__ import annotations

import logging
import subprocess
import sys
from typing import Any

logger = logging.getLogger(__name__)


def kill_process_tree(
    proc: Any, *, platform: str = sys.platform, wait_timeout: float = 10.0
) -> None:
    """Kill a spawned process AND its children (#921 AC6).

    On Windows, a bare ``Popen.kill()`` is ``TerminateProcess`` on the direct
    child only — grandchildren survive. ``taskkill /T /F`` tree-kills the
    whole process tree; if ``taskkill`` itself is unavailable (stripped PATH,
    minimal container), fall back to plain ``proc.kill()`` so the direct
    child is at least taken down. POSIX goes straight to ``proc.kill()``.

    ``wait_timeout`` lets callers with different reap-latency needs (a 10s
    runaway-kill tick vs. pid_sidecar's faster 1s orphan-kill path) share
    this implementation without either forcing the other's timing.
    """
    if platform == "win32":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                capture_output=True,
                check=False,
            )
        except OSError:
            logger.exception(
                "[process_kill] taskkill unavailable for pid %s; "
                "falling back to Popen.kill() (children may survive)",
                proc.pid,
            )
            proc.kill()
    else:
        proc.kill()
    try:
        proc.wait(timeout=wait_timeout)
    except Exception:  # noqa: BLE001
        pass
