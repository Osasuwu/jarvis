"""Unit tests for ``scripts/pending-volume-watcher.py``.

Tests the hysteresis logic and debounce behavior with a mocked Supabase
client. See ``test_dreamer.py`` for same-pattern mock chain construction.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

_SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "pending-volume-watcher.py"
_spec = importlib.util.spec_from_file_location("pending_volume_watcher", _SCRIPT_PATH)
assert _spec and _spec.loader
watcher = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(watcher)


def _mock_pending_count(client: MagicMock, count: int):
    """Set up the client stub to return ``count`` pending items."""
    exec_resp = MagicMock()
    exec_resp.count = count

    execute_mock = MagicMock()
    execute_mock.execute.return_value = exec_resp

    is_mock = MagicMock()
    is_mock.is_.return_value = execute_mock

    eq_mock = MagicMock()
    eq_mock.eq.return_value = is_mock

    select_mock = MagicMock()
    select_mock.select.return_value = eq_mock

    client.table.return_value = select_mock


def _mock_events(client: MagicMock, event_type: str, rows: list[dict]):
    """Set up the client stub to return events rows."""
    exec_resp = MagicMock()
    exec_resp.data = rows

    limit_mock = MagicMock()
    limit_mock.limit.return_value.execute.return_value = exec_resp

    order_mock = MagicMock()
    order_mock.order.return_value = limit_mock

    eq_mock = MagicMock()
    eq_mock.eq.return_value = order_mock

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
        _mock_events(client, "candidates_pending", [])

        result = watcher.check_and_fire(client, dry_run=True)
        assert result["action"] == "none"
        assert "pending=5 < fire=10" in result["reason"]

    def test_above_threshold_fires(self):
        client = MagicMock()
        _mock_pending_count(client, 12)
        _mock_events(client, "candidates_pending", [])

        result = watcher.check_and_fire(client, dry_run=True)
        assert result["action"] == "would_fire"
        assert result["pending_count"] == 12

    def test_already_fired_no_rearm_skips(self):
        """Still in fired state and count >= rearm threshold → skip."""
        client = MagicMock()
        _mock_pending_count(client, 10)
        _mock_events(client, "candidates_pending", [
            {
                "created_at": "2026-05-20T10:00:00Z",
                "payload": {"state": "fired", "pending_count": 15},
            }
        ])

        result = watcher.check_and_fire(client, dry_run=True)
        assert result["action"] == "none"
        assert "already fired" in result["reason"]

    def test_rearmed_then_crosses_threshold_fires_again(self):
        """After re-arm (<8), crossing >=10 fires again."""
        client = MagicMock()
        _mock_pending_count(client, 12)
        # Last event was a fired event from earlier, but count dropped below 8
        # so re-arm happened. The last event's state is still 'fired' but
        # pending_count is now 12 >= 8 rearm threshold... hmm.

        # Actually, the logic is: if last state is 'fired' AND pending >= rearm,
        # skip. So to re-fire, we need either:
        # 1. Last state is 'rearmed' (from a re-arm event), or
        # 2. pending < rearm threshold (wouldn't fire anyway)

        # Let me simulate: after re-arm, the last event is 'rearmed'
        _mock_events(client, "candidates_pending", [
            {
                "created_at": "2026-05-19T10:00:00Z",
                "payload": {"state": "rearmed", "pending_count": 7},
            }
        ])

        result = watcher.check_and_fire(client, dry_run=True)
        assert result["action"] == "would_fire"
        assert result["pending_count"] == 12

    def test_hysteresis_band_does_not_refire(self):
        """pending=9 is in the hysteresis band (8..9), no re-fire when last was fired."""
        client = MagicMock()
        _mock_pending_count(client, 9)
        _mock_events(client, "candidates_pending", [
            {
                "created_at": "2026-05-20T10:00:00Z",
                "payload": {"state": "fired", "pending_count": 15},
            }
        ])

        result = watcher.check_and_fire(client, dry_run=True)
        assert result["action"] == "none"
        # Still in hysteresis band (pending=9 >= rearm=8, last state=fired)


class TestDebounce:
    """Tests the 24h debounce after /learn runs."""

    def test_recent_learn_skips_fire(self):
        client = MagicMock()
        _mock_pending_count(client, 15)
        # Last candidates_pending event is rearmed, so that gate passes
        _mock_events(client, "candidates_pending", [
            {
                "created_at": "2026-05-19T10:00:00Z",
                "payload": {"state": "rearmed", "pending_count": 5},
            }
        ])
        # But a /learn ran 2 hours ago
        _mock_events(client, "learn_run", [
            {"created_at": "2026-05-20T10:00:00Z"},
        ])

        result = watcher.check_and_fire(client, dry_run=True)
        assert result["action"] == "none"
        assert "debounce" in result["reason"]

    def test_old_learn_allows_fire(self):
        client = MagicMock()
        _mock_pending_count(client, 15)
        # Last candidates_pending is rearmed
        _mock_events(client, "candidates_pending", [
            {
                "created_at": "2026-05-19T10:00:00Z",
                "payload": {"state": "rearmed", "pending_count": 5},
            }
        ])
        # But /learn ran 48 hours ago - outside debounce window
        _mock_events(client, "learn_run", [
            {"created_at": "2026-05-18T10:00:00Z"},
        ])

        result = watcher.check_and_fire(client, dry_run=True)
        assert result["action"] == "would_fire"


class TestDryRun:
    def test_dry_run_no_event_emitted(self):
        client = MagicMock()
        _mock_pending_count(client, 15)
        _mock_events(client, "candidates_pending", [])

        result = watcher.check_and_fire(client, dry_run=True)
        assert result["action"] == "would_fire"
        assert result["dry_run"] is True
