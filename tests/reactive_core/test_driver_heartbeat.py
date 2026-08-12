"""Tests for the driver_heartbeat read side (#1085 S2-6).

``classify`` is pure (no I/O) — exercised directly with fixed ``now`` values
so the 900s threshold is deterministic. ``check_heartbeat`` is exercised
through a ``HeartbeatPort`` fake, mirroring how ``/dispatch``'s pipeline
will call it: no live Supabase in this suite.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from agents.driver_heartbeat import (
    DEFAULT_STALE_AFTER_SECONDS,
    DRIVER_NAME,
    HeartbeatPort,
    HeartbeatStatus,
    check_heartbeat,
    classify,
)

_NOW = datetime(2026, 8, 12, 12, 0, 0, tzinfo=timezone.utc)


class FakeHeartbeat:
    """In-memory HeartbeatPort fake — one optional row, keyed by driver_name."""

    def __init__(self, rows: dict[str, dict] | None = None) -> None:
        self.rows = rows or {}
        self.tick_calls: list[str] = []

    def read_heartbeat(self, driver_name: str) -> dict | None:
        return self.rows.get(driver_name)

    def record_tick(self, driver_name: str) -> None:
        self.tick_calls.append(driver_name)


def test_classify_missing_row_is_missing() -> None:
    status = classify(None, now=_NOW)
    assert status.state == "missing"
    assert status.is_stale is True
    assert status.last_tick is None


def test_classify_row_with_null_last_tick_is_missing() -> None:
    status = classify({"driver_name": DRIVER_NAME, "last_tick": None}, now=_NOW)
    assert status.state == "missing"
    assert status.is_stale is True


def test_classify_fresh_row_is_fresh() -> None:
    row = {"driver_name": DRIVER_NAME, "last_tick": (_NOW - timedelta(seconds=60)).isoformat()}
    status = classify(row, now=_NOW)
    assert status.state == "fresh"
    assert status.is_stale is False
    assert status.age_seconds == pytest.approx(60.0)


def test_classify_row_at_exact_threshold_is_fresh() -> None:
    row = {
        "driver_name": DRIVER_NAME,
        "last_tick": (_NOW - timedelta(seconds=DEFAULT_STALE_AFTER_SECONDS)).isoformat(),
    }
    status = classify(row, now=_NOW)
    assert status.state == "fresh"


def test_classify_stale_row_is_stale() -> None:
    row = {
        "driver_name": DRIVER_NAME,
        "last_tick": (_NOW - timedelta(seconds=DEFAULT_STALE_AFTER_SECONDS + 1)).isoformat(),
    }
    status = classify(row, now=_NOW)
    assert status.state == "stale"
    assert status.is_stale is True
    assert status.age_seconds == pytest.approx(DEFAULT_STALE_AFTER_SECONDS + 1)


def test_classify_accepts_datetime_last_tick_not_only_string() -> None:
    row = {"driver_name": DRIVER_NAME, "last_tick": _NOW - timedelta(seconds=10)}
    status = classify(row, now=_NOW)
    assert status.state == "fresh"


def test_classify_custom_threshold_overrides_default() -> None:
    row = {"driver_name": DRIVER_NAME, "last_tick": (_NOW - timedelta(seconds=100)).isoformat()}
    assert classify(row, now=_NOW, stale_after_seconds=50).state == "stale"
    assert classify(row, now=_NOW, stale_after_seconds=200).state == "fresh"


def test_check_heartbeat_missing_via_port() -> None:
    port = FakeHeartbeat(rows={})
    status = check_heartbeat(port, now=_NOW)
    assert status.state == "missing"


def test_check_heartbeat_fresh_via_port() -> None:
    port = FakeHeartbeat(
        rows={DRIVER_NAME: {"last_tick": (_NOW - timedelta(seconds=5)).isoformat()}}
    )
    status = check_heartbeat(port, now=_NOW)
    assert status.state == "fresh"


def test_check_heartbeat_stale_via_port() -> None:
    port = FakeHeartbeat(
        rows={
            DRIVER_NAME: {
                "last_tick": (_NOW - timedelta(seconds=DEFAULT_STALE_AFTER_SECONDS * 2)).isoformat()
            }
        }
    )
    status = check_heartbeat(port, now=_NOW)
    assert status.state == "stale"


def test_check_heartbeat_only_reads_named_driver() -> None:
    port = FakeHeartbeat(
        rows={"some_other_driver": {"last_tick": (_NOW - timedelta(seconds=5)).isoformat()}}
    )
    status = check_heartbeat(port, driver_name=DRIVER_NAME, now=_NOW)
    assert status.state == "missing"


def test_heartbeat_port_is_runtime_checkable_against_fake() -> None:
    assert isinstance(FakeHeartbeat(), HeartbeatPort)


def test_heartbeat_status_is_frozen_dataclass() -> None:
    status = HeartbeatStatus(state="fresh")
    with pytest.raises(AttributeError):
        status.state = "stale"  # type: ignore[misc]


def test_fake_heartbeat_record_tick_tracks_calls() -> None:
    port = FakeHeartbeat()
    port.record_tick(DRIVER_NAME)
    assert port.tick_calls == [DRIVER_NAME]


def test_supabase_heartbeat_record_tick_calls_rpc() -> None:
    from unittest.mock import MagicMock

    from agents.driver_heartbeat import SupabaseHeartbeat

    client = MagicMock()
    rpc_builder = MagicMock()
    rpc_builder.execute.return_value = MagicMock(data=None)
    client.rpc.return_value = rpc_builder

    heartbeat = SupabaseHeartbeat(client=client)
    heartbeat.record_tick(DRIVER_NAME)

    client.rpc.assert_called_once_with("driver_heartbeat_tick", {"p_driver_name": DRIVER_NAME})
    rpc_builder.execute.assert_called_once()
