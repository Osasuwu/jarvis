"""Shared fire-and-forget task pinning + swallowed-exception logging.

Deduplicates the _PENDING_TASKS/_pin_task pattern previously copy-pasted
across handlers/memory.py and handlers/decision.py (#1082), and gives every
genuinely-silent ``except Exception: pass`` site a shared, non-silent home:
``log_swallowed`` logs at WARNING via its own stderr handler, mirroring
events_canonical.py's logger setup exactly.
"""

from __future__ import annotations

import asyncio
import logging
import sys

# Strong references to fire-and-forget tasks. CPython holds only a weak ref to
# a bare ``asyncio.create_task`` result, so without an external strong ref the
# task can be GC-collected mid-flight before it completes (same pattern as
# write_scrubber._PENDING_BLOCK_LOGS). Shared across memory.py and
# decision.py — both modules pin into this one set. Discard via the
# done-callback below.
_PENDING_TASKS: set[asyncio.Task] = set()


def _pin_task(task: asyncio.Task) -> None:
    """Strong-ref *task* until completion so it can't be GC-collected mid-flight."""
    _PENDING_TASKS.add(task)
    task.add_done_callback(_PENDING_TASKS.discard)


logger = logging.getLogger(__name__)
# Default to stderr so MCP server logs surface the warnings — the host
# may layer additional handlers, those compose on top.
if not logger.handlers:
    _h = logging.StreamHandler(sys.stderr)
    _h.setFormatter(logging.Formatter("[fire_and_forget] %(levelname)s: %(message)s"))
    logger.addHandler(_h)
    logger.setLevel(logging.WARNING)


def log_swallowed(site: str, exc: BaseException) -> None:
    """Log an otherwise-silently-swallowed exception at WARNING.

    ``site`` identifies the call site (e.g. "memory._touch_memories") so
    degraded-mode log lines are greppable back to source.
    """
    logger.warning("swallowed exception at %s: %s: %s", site, type(exc).__name__, exc)
