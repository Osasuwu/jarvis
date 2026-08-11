"""Cross-device liveness read for reactive-core drivers (#1085 S2-6).

The WRITE side (``wake_driver`` stamping its own tick into ``driver_heartbeat``)
ships in Slice 3 (S3-1). This module is the READ side, shipped in Slice 2 so
`/dispatch` can warn "driver stale — rows enqueued but may not run" right
after enqueue: a row with no writer yet is legitimately "stale" too, so the
classifier treats a missing row the same as an old one.

Split into a pure classifier (:func:`classify`) and a thin Supabase adapter
(:class:`SupabaseHeartbeat`) behind :class:`HeartbeatPort`, mirroring the
``TaskQueuePort`` pattern in ``agents/task_dispatch.py`` — tests exercise
``classify`` directly or swap in an in-memory fake, never a live DB.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from supabase import Client

from agents.supabase_client import get_client

# 3x wake_driver's own idle-wait constant (agents/wake_driver.py,
# DEFAULT_STALE_AFTER_SECONDS = 300) — one missed tick is noise, three in a
# row is a driver that has stopped.
DEFAULT_STALE_AFTER_SECONDS = 900

DRIVER_NAME = "wake_driver"

WARN_MESSAGE = "driver stale — rows enqueued but may not run"


@dataclass(frozen=True)
class HeartbeatStatus:
    """Result of classifying a driver_heartbeat row against a staleness threshold."""

    state: str  # "fresh" | "stale" | "missing"
    last_tick: datetime | None = None
    age_seconds: float | None = None

    @property
    def is_stale(self) -> bool:
        """True for both "stale" and "missing" — both warn-worthy to a reader."""
        return self.state != "fresh"


@runtime_checkable
class HeartbeatPort(Protocol):
    def read_heartbeat(self, driver_name: str) -> dict[str, Any] | None:
        """Return the raw ``driver_heartbeat`` row for ``driver_name``, or ``None``."""


class SupabaseHeartbeat:
    """Real adapter — one-row lookup on ``driver_heartbeat``."""

    def __init__(self, client: Client | None = None) -> None:
        self._client = client

    def read_heartbeat(self, driver_name: str) -> dict[str, Any] | None:
        cli = self._client or get_client()
        rows = (
            cli.table("driver_heartbeat")
            .select("driver_name,last_tick")
            .eq("driver_name", driver_name)
            .limit(1)
            .execute()
        ).data or []
        return rows[0] if rows else None


def classify(
    row: dict[str, Any] | None,
    *,
    now: datetime | None = None,
    stale_after_seconds: float = DEFAULT_STALE_AFTER_SECONDS,
) -> HeartbeatStatus:
    """Pure classification of a ``driver_heartbeat`` row — no I/O.

    ``row`` is whatever :meth:`HeartbeatPort.read_heartbeat` returned:
    ``None`` (no writer has ever ticked, or the table is pre-Slice-3-empty)
    classifies as ``"missing"``, same warn-worthy bucket as an old tick.
    """
    if row is None or not row.get("last_tick"):
        return HeartbeatStatus(state="missing")

    last_tick = row["last_tick"]
    if isinstance(last_tick, str):
        last_tick = datetime.fromisoformat(last_tick.replace("Z", "+00:00"))

    moment = now or datetime.now(timezone.utc)
    age = (moment - last_tick).total_seconds()
    if age > stale_after_seconds:
        return HeartbeatStatus(state="stale", last_tick=last_tick, age_seconds=age)
    return HeartbeatStatus(state="fresh", last_tick=last_tick, age_seconds=age)


def check_heartbeat(
    port: HeartbeatPort | None = None,
    *,
    driver_name: str = DRIVER_NAME,
    now: datetime | None = None,
    stale_after_seconds: float = DEFAULT_STALE_AFTER_SECONDS,
) -> HeartbeatStatus:
    """Read (via ``port``, default: live Supabase) then classify in one call."""
    p = port or SupabaseHeartbeat()
    row = p.read_heartbeat(driver_name)
    return classify(row, now=now, stale_after_seconds=stale_after_seconds)
