"""task_worktree — per-task git worktree lifecycle for the reactive dispatch loop.

Extracted from ``agents/task_dispatch.py`` (#1607, milestone #66 — task_dispatch
decomposition 3/7). Pure extraction, no behavior change: ``task_dispatch.py``
calls into this module directly (shape (b) — no event bus, no plugin registry).

Covers the full worktree lifecycle (#1390): creation at spawn time (AC3),
finalization at the terminal boundary (AC5), and the tick-start reaping sweep
that TTL/cap-evicts retained-failure trees (AC6).
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agents.task_dispatch import TaskQueuePort

logger = logging.getLogger(__name__)

# Repo root, mirroring executor._REPO_ROOT — anchors per-task worktree creation
# (#1390 AC3) to the main checkout regardless of the daemon's CWD. Tests
# monkeypatch this attribute to point at a temporary repo.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# A task_id is interpolated into a worktree filesystem path, so it must be
# confined to a charset that cannot escape the directory — no ``/``, ``\``,
# ``.`` (hence no ``..``), or other path-significant characters. UUIDs and the
# alnum ids used elsewhere both satisfy this; a crafted ``../../etc/passwd``
# does not (LOW, PR #1011 — path-traversal hardening, mirrored here from the
# original ``default_stdout_reader`` guard in ``task_dispatch.py``).
_SAFE_TASK_ID_RE = re.compile(r"\A[A-Za-z0-9_-]+\Z")

# A retained-failure worktree (#1390 AC6) is kept this long, measured from its
# ``_WORKTREE_FAILED_AT_MARKER`` timestamp, before the sweep TTL-prunes it —
# generous enough to cover a same-day post-mortem without accumulating stale
# trees indefinitely.
DEFAULT_WORKTREE_RETENTION_TTL_SECONDS = 24 * 60 * 60

# Beyond this many retained-failure worktrees, the sweep evicts the oldest
# (by ``_WORKTREE_FAILED_AT_MARKER``) first — a backstop against disk growth
# when failures outpace the TTL, independent of it (#1390 AC6).
DEFAULT_WORKTREE_RETENTION_CAP = 20

# Marker file written into a retained-failure worktree at detach time, holding
# the epoch timestamp of finalization. The AC6 sweep TTLs retained failures
# against this file's content rather than git-internal mtimes — ``git
# checkout --detach`` gives no reliable "when did this fail" signal on its
# own (LOW, #1390 AC6 design).
_WORKTREE_FAILED_AT_MARKER = ".reactive-failed-at"


@dataclass(frozen=True)
class WorktreeSweepResult:
    """What one :func:`sweep_task_worktrees` did (#1390 AC6)."""

    # Worktrees removed immediately: task row absent, or terminal-non-failure
    # (``done``, ``parked``, ``skipped_duplicate``).
    pruned: int = 0
    # Retained-failure worktrees still on disk after TTL + cap eviction.
    retained: int = 0
    # Retained-failure worktrees removed for exceeding the TTL.
    ttl_pruned: int = 0
    # Retained-failure worktrees removed for exceeding the count cap
    # (oldest-first), independent of TTL.
    cap_evicted: int = 0


def create_task_worktree(task_id: str, goal: str = "") -> str:
    """Create a per-task git worktree at ``.reactive/worktrees/<task_id>``
    (#1390 AC3) — isolates concurrent spawned workers from each other and
    from the main checkout's working tree.

    By default the worktree is created on a fresh branch ``task/<task_id>``
    (``git worktree add -b``). If ``goal`` carries an explicit
    ``(branch=<name>)`` directive naming a *different* branch, the worktree
    instead **attaches** to that existing branch (``git worktree add`` with
    no ``-b``) rather than creating ``task/<task_id>``.

    This distinction matters for a fresh-shape re-drive: :func:`orchestrator._redrive_goal`
    pins the retry to ``(branch=task/<root_task_id>)`` specifically *because*
    the re-driven task's own ``task/<task_id>`` branch is never meant to be
    created — the retry needs to land back on the root attempt's branch,
    which :func:`finalize_task_worktree` leaves detached-but-intact after a
    failure precisely so a later attach can succeed. Creating a new branch
    unconditionally here would silently violate that pin (MEDIUM, PR #1450
    review) and leave the retry's evidence check looking at a branch that was
    never populated.

    ``task_id`` is validated via ``_SAFE_TASK_ID_RE`` before interpolation into
    a filesystem path — same path-traversal guard as
    ``task_dispatch.default_stdout_reader``.
    """
    if not _SAFE_TASK_ID_RE.match(task_id):
        raise ValueError(f"unsafe task_id for worktree path: {task_id!r}")
    worktree_path = os.path.join(_REPO_ROOT, ".reactive", "worktrees", task_id)
    own_branch = f"task/{task_id}"
    branch_match = re.search(r"\(branch=([^)]+)\)", goal)
    target_branch = branch_match.group(1).strip() if branch_match else own_branch
    if target_branch == own_branch:
        cmd = ["git", "worktree", "add", "-b", own_branch, worktree_path]
    else:
        cmd = ["git", "worktree", "add", worktree_path, target_branch]
    subprocess.run(cmd, cwd=_REPO_ROOT, check=True, capture_output=True, text=True)
    return worktree_path


def finalize_task_worktree(task_id: str, *, success: bool) -> None:
    """Finalize the per-task worktree at the terminal boundary (#1390 AC5).

    Success removes the worktree outright. Failure detaches HEAD first so the
    branch ``task/<task_id>`` is free for ``_redrive_goal``'s retry to attach
    in a fresh worktree, writes the ``_WORKTREE_FAILED_AT_MARKER`` timestamp
    file, then leaves the tree on disk for post-mortem — the AC6 sweep
    TTL/count-caps genuinely retained failures later, keyed on that marker.

    No-op (not an error) when the worktree was never created — e.g. an
    adopted-after-restart proc, or a task spawned before #1390 shipped.
    """
    if not _SAFE_TASK_ID_RE.match(task_id):
        return
    worktree_path = os.path.join(_REPO_ROOT, ".reactive", "worktrees", task_id)
    if not os.path.isdir(worktree_path):
        return
    if success:
        subprocess.run(
            ["git", "worktree", "remove", "--force", worktree_path],
            cwd=_REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    else:
        subprocess.run(
            ["git", "checkout", "--detach"],
            cwd=worktree_path,
            check=True,
            capture_output=True,
            text=True,
        )
        with open(
            os.path.join(worktree_path, _WORKTREE_FAILED_AT_MARKER), "w", encoding="utf-8"
        ) as fh:
            fh.write(str(time.time()))


def remove_worktree(worktree_path: str) -> bool:
    """Best-effort ``git worktree remove --force`` — log-and-continue, never raise.

    Windows handle-locks make an un-removable tree a normal outcome (the
    existing ``.claude/worktrees/`` lane already drifts — 9 dirs on disk vs 5
    registered), not an exotic one; the AC6 sweep must not let one stuck tree
    abort the rest of the tick (#1390 AC6).
    """
    try:
        subprocess.run(
            ["git", "worktree", "remove", "--force", worktree_path],
            cwd=_REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        return True
    except (subprocess.CalledProcessError, OSError):
        logger.exception(
            "[task_worktree] failed to remove worktree %s; retried next sweep",
            worktree_path,
        )
        return False


def read_worktree_failed_at(worktree_path: str, *, default: float) -> float:
    """Read the ``_WORKTREE_FAILED_AT_MARKER`` epoch timestamp, or ``default``
    if the marker is missing/unreadable — e.g. a worktree that failed before
    #1390 AC6 shipped the marker write. Defaulting to "now" rather than "very
    old" means an unreadable marker errs toward retaining the tree, not
    losing it to an eager TTL prune.
    """
    marker_path = os.path.join(worktree_path, _WORKTREE_FAILED_AT_MARKER)
    try:
        with open(marker_path, encoding="utf-8") as fh:
            return float(fh.read().strip())
    except (OSError, ValueError):
        return default


def sweep_task_worktrees(
    port: TaskQueuePort,
    *,
    retention_seconds: float = DEFAULT_WORKTREE_RETENTION_TTL_SECONDS,
    retention_cap: int = DEFAULT_WORKTREE_RETENTION_CAP,
    now: Callable[[], float] = time.time,
) -> WorktreeSweepResult:
    """Tick-start reaping sweep over ``.reactive/worktrees/*`` (#1390 AC6).

    Keyed on the owning task's queue-row status, looked up via
    :meth:`TaskQueuePort.get_status`:

    - **Absent row, or terminal-non-failure** (``done``, ``parked``,
      ``skipped_duplicate``) → removed immediately. Nothing needs the tree
      any more.
    - **``failed``** → retained for post-mortem, subject to TTL
      (``retention_seconds``, measured from the tree's
      ``_WORKTREE_FAILED_AT_MARKER``) and a count cap (``retention_cap``,
      oldest-first eviction) so failures don't accumulate unbounded.
    - **Any active state** (``pending``, ``claimed``, ``running``) → left
      untouched. A live spawn's worktree is never touched by this sweep;
      :func:`agents.task_dispatch.reclaim_stale_tasks` (run immediately
      before this in ``wake_driver.tick``) is what turns an orphaned
      ``running`` row into ``failed`` so it becomes eligible here.

    Finishes with a best-effort ``git worktree prune`` so git's own
    registration bookkeeping stays in sync with what's actually on disk.
    Removal failures (Windows handle-locks are a normal, not exotic, outcome)
    are logged and retried next tick rather than raised — one stuck tree must
    not abort the sweep.
    """
    worktrees_root = os.path.join(_REPO_ROOT, ".reactive", "worktrees")
    pruned = 0
    retained_failures: list[tuple[str, float]] = []

    if os.path.isdir(worktrees_root):
        for name in sorted(os.listdir(worktrees_root)):
            if not _SAFE_TASK_ID_RE.match(name):
                continue
            worktree_path = os.path.join(worktrees_root, name)
            if not os.path.isdir(worktree_path):
                continue

            status = port.get_status(name)
            if status == "failed":
                failed_at = read_worktree_failed_at(worktree_path, default=now())
                retained_failures.append((worktree_path, failed_at))
            elif status in (None, "done", "parked", "skipped_duplicate"):
                if remove_worktree(worktree_path):
                    pruned += 1
            # else: active (pending/claimed/running) — untouched this sweep.

    # TTL-prune retained failures past their retention window.
    ttl_pruned = 0
    cutoff = now() - retention_seconds
    survivors: list[tuple[str, float]] = []
    for worktree_path, failed_at in retained_failures:
        if failed_at < cutoff:
            if remove_worktree(worktree_path):
                ttl_pruned += 1
            continue
        survivors.append((worktree_path, failed_at))

    # Count-cap survivors, oldest-first, independent of TTL.
    cap_evicted = 0
    if len(survivors) > retention_cap:
        survivors.sort(key=lambda item: item[1])
        overflow = len(survivors) - retention_cap
        for worktree_path, _failed_at in survivors[:overflow]:
            if remove_worktree(worktree_path):
                cap_evicted += 1

    try:
        subprocess.run(
            ["git", "worktree", "prune"],
            cwd=_REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (subprocess.CalledProcessError, OSError):
        logger.exception("[task_worktree] git worktree prune failed; retried next sweep")

    return WorktreeSweepResult(
        pruned=pruned,
        retained=len(survivors) - cap_evicted,
        ttl_pruned=ttl_pruned,
        cap_evicted=cap_evicted,
    )
