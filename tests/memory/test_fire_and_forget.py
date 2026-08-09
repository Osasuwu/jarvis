"""Shared fire-and-forget task pinning + swallowed-exception logging (#1082).

Deduplicates the _PENDING_TASKS/_pin_task pattern previously copy-pasted
across handlers/memory.py and handlers/decision.py, and gives every
genuinely-silent ``except Exception: pass`` site a shared, non-silent home
via ``log_swallowed``.
"""

from __future__ import annotations

import asyncio
import gc
import logging

import pytest

import fire_and_forget as faf


@pytest.mark.asyncio
async def test_pin_task_holds_until_completion_then_discards():
    gate = asyncio.Event()
    completed = asyncio.Event()

    async def _gated():
        await gate.wait()
        completed.set()

    faf._PENDING_TASKS.clear()
    faf._pin_task(asyncio.create_task(_gated()))
    del _gated
    gc.collect()

    assert len(faf._PENDING_TASKS) == 1, "task must be strong-reffed while in flight"

    gate.set()
    await asyncio.wait_for(completed.wait(), timeout=1.0)
    await asyncio.sleep(0)

    assert faf._PENDING_TASKS == set(), "completed task must be unpinned by the done-callback"


def test_logger_mirrors_events_canonical_setup():
    """log_swallowed's logger must own a StreamHandler(sys.stderr) + formatter
    + explicit level, guarded by `if not logger.handlers` — not just a bare
    getLogger() + .warning() call (decision ee0f5567)."""
    assert faf.logger.handlers, "logger must own at least one handler"
    handler = faf.logger.handlers[0]
    assert isinstance(handler, logging.StreamHandler)
    assert handler.formatter is not None
    assert faf.logger.level == logging.WARNING


def test_log_swallowed_logs_site_and_exception(caplog):
    exc = ValueError("boom")
    with caplog.at_level(logging.WARNING, logger=faf.logger.name):
        faf.log_swallowed("memory._touch_memories", exc)

    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.levelno == logging.WARNING
    assert "memory._touch_memories" in record.message
    assert "ValueError" in record.message
    assert "boom" in record.message
