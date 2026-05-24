"""Unit tests for ``scripts/pending-volume-watcher.py``.

Tests the hysteresis logic and debounce behavior with a mocked Supabase
client. See ``test_dreamer.py`` for same-pattern mock chain construction.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

_SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "pending-volume-watcher.py"
_spec = importlib.util.spec_from_file_location("pending_volume_watcher", _SCRIPT_PATH)
assert _spec and _spec.loader
watcher = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(watcher)

FROZEN_NOW = datetime(2026, 5, 24, 12, 0, 0, tzinfo=timezone.utc)


def _mock_pending_count(client: MagicMock, count: int):
    """Set up the client stub to return ``count`` pending items."""
    exec_resp = MagicMock()
    exec_resp.count = count

    execute_mock = MagicMock()
    execute_mock.execute.return_value = exec_resp

    is_superseded_mock = MagicMock()
    is_superseded_mock.is_.return_value = execute_mock

    is_deleted_mock = MagicMock()
    is_deleted_mock.is_.return_value = is_superseded_mock

    eq_mock = MagicMock()
    eq_mock.eq.return_value = is_deleted_mock

    select_mock = MagicMock()
    select_mock.select.return_value = eq_mock

    client.table.return_value = select_mock


def _mock_events(client: MagicMock, events_by_type: dict[str, list[dict]]):
    """Set up the client stub to return event rows keyed by event_type.

    Each key maps to the rows that queries with
    ``.eq("event_type", key)`` should return.  Unknown event_types get an
    empty result.  Call this *after* ``_mock_pending_count`` so the memories
    mock (stored in ``client.table.return_value``) is already in place.
    """
    def _make_chain(rows: list[dict]) -> MagicMock:
        exec_resp = MagicMock()
        exec_resp.data = rows
        limit_mock = MagicMock()
        limit_mock.limit.return_value.execute.return_value = exec_resp
        order_mock = MagicMock()
        order_mock.order.return_value = limit_mock
        return order_mock

    def _eq_side_effect(field: str, value):
        if field == "event_type" and value in events_by_type:
            return _make_chain(events_by_type[value])
        return _make_chain([])

    eq_mock = MagicMock()
    eq_mock.eq.side_effect = _eq_side_effect

    select_mock = MagicMock()
    select_mock.select.return_value = eq_mock

    def _table_side_effect(name: str):
        if name == "memories":
            return client.table.return_value
        elif name == "events":
            return select_mock
        return MagicMock()

    client.table.side_effect = _table_side_effect


class TestHysteresis:
    """Tests the fire/re-arm hysteresis logic."""

    def test_below_threshold_no_action(self):
        client = MagicMock()
        _mock_pending_count(client, 5)
        _mock_events(client, {"candidates_pending": []})

        result = watcher.check_and_fire(client, dry_run=True)
        assert result["action"] == "none"
        assert "pending=5 < fire=10" in result["reason"]

    def test_above_threshold_fires(self):
        client = MagicMock()
        _mock_pending_count(client, 12)
        _mock_events(client, {"candidates_pending": []})

        result = watcher.check_and_fire(client, dry_run=True)
        assert result["action"] == "would_fire"
        assert result["pending_count"] == 12

    def test_already_fired_no_rearm_skips(self):
        """Still in fired state and count >= rearm threshold → skip."""
        client = MagicMock()
        _mock_pending_count(client, 10)
        _mock_events(client, {"candidates_pending": [
            {
                "created_at": "2026-05-20T10:00:00Z",
                "payload": {"state": "fired", "pending_count": 15},
            }
        ]})

        result = watcher.check_and_fire(client, dry_run=True)
        assert result["action"] == "none"
        assert "already fired" in result["reason"]

    def test_rearmed_then_crosses_threshold_fires_again(self):
        """After re-arm (<8), crossing >=10 fires again."""
        client = MagicMock()
        _mock_pending_count(client, 12)
        _mock_events(client, {"candidates_pending": [
            {
                "created_at": "2026-05-19T10:00:00Z",
                "payload": {"state": "rearmed", "pending_count": 7},
            }
        ]})

        result = watcher.check_and_fire(client, dry_run=True)
        assert result["action"] == "would_fire"
        assert result["pending_count"] == 12

    def test_hysteresis_band_does_not_refire(self):
        """pending=9 is in the hysteresis band (8..9), no re-fire when last was fired."""
        client = MagicMock()
        _mock_pending_count(client, 9)
        _mock_events(client, {"candidates_pending": [
            {
                "created_at": "2026-05-20T10:00:00Z",
                "payload": {"state": "fired", "pending_count": 15},
            }
        ]})

        result = watcher.check_and_fire(client, dry_run=True)
        assert result["action"] == "none"

    def test_fire_drop_rerise_refires(self):
        """fire → drop below REARM_THRESHOLD → rise above FIRE_THRESHOLD → re-fires."""
        # Phase 1: no prior event, pending=12 → fires
        c1 = MagicMock()
        _mock_pending_count(c1, 12)
        _mock_events(c1, {"candidates_pending": [], "learn_run": []})
        r1 = watcher.check_and_fire(c1, dry_run=True, _now=lambda: FROZEN_NOW)
        assert r1["action"] == "would_fire"

        # Phase 2: pending=6, last state=fired → re-arms, returns none (below FIRE)
        c2 = MagicMock()
        _mock_pending_count(c2, 6)
        _mock_events(c2, {"candidates_pending": [
            {"created_at": "2026-05-24T10:00:00Z", "payload": {"state": "fired", "pending_count": 12}}
        ], "learn_run": []})
        r2 = watcher.check_and_fire(c2, dry_run=True, _now=lambda: FROZEN_NOW)
        assert r2["action"] == "none"
        assert r2.get("rearmed") is True

        # Phase 3: pending=11, last state=rearmed → fires again
        c3 = MagicMock()
        _mock_pending_count(c3, 11)
        _mock_events(c3, {"candidates_pending": [
            {"created_at": "2026-05-24T11:00:00Z", "payload": {"state": "rearmed", "pending_count": 6}}
        ], "learn_run": []})
        r3 = watcher.check_and_fire(c3, dry_run=True, _now=lambda: FROZEN_NOW)
        assert r3["action"] == "would_fire"


class TestDebounce:
    """Tests the 24h debounce after /learn runs."""

    def test_recent_learn_skips_fire(self):
        client = MagicMock()
        _mock_pending_count(client, 15)
        _mock_events(client, {
            "candidates_pending": [
                {
                    "created_at": "2026-05-23T12:00:00Z",
                    "payload": {"state": "rearmed", "pending_count": 5},
                }
            ],
            "learn_run": [
                {"created_at": "2026-05-24T11:00:00Z"},  # 1h before FROZEN_NOW
            ],
        })

        result = watcher.check_and_fire(client, dry_run=True, _now=lambda: FROZEN_NOW)
        assert result["action"] == "none"
        assert "debounce" in result["reason"]

    def test_old_learn_allows_fire(self):
        client = MagicMock()
        _mock_pending_count(client, 15)
        _mock_events(client, {
            "candidates_pending": [
                {
                    "created_at": "2026-05-22T12:00:00Z",
                    "payload": {"state": "rearmed", "pending_count": 5},
                }
            ],
            "learn_run": [
                {"created_at": "2026-05-22T12:00:00Z"},  # 48h before FROZEN_NOW
            ],
        })

        result = watcher.check_and_fire(client, dry_run=True, _now=lambda: FROZEN_NOW)
        assert result["action"] == "would_fire"

    def test_second_invocation_within_debounce_suppressed(self):
        """After watcher fires, re-invocation within 24h is suppressed via learn_run marker."""
        client = MagicMock()
        _mock_pending_count(client, 15)
        _mock_events(client, {
            "candidates_pending": [
                {"created_at": "2026-05-24T11:55:00Z", "payload": {"state": "rearmed"}}
            ],
            "learn_run": [
                {"created_at": "2026-05-24T11:59:00Z"},  # 1 min before FROZEN_NOW
            ],
        })

        result = watcher.check_and_fire(client, dry_run=True, _now=lambda: FROZEN_NOW)
        assert result["action"] == "none"
        assert "debounce" in result["reason"]


class TestDryRun:
    def test_dry_run_no_event_emitted(self):
        client = MagicMock()
        _mock_pending_count(client, 15)
        _mock_events(client, {"candidates_pending": []})

        result = watcher.check_and_fire(client, dry_run=True)
        assert result["action"] == "would_fire"
        assert result["dry_run"] is True
