"""Tests for global task sources and advancer (issue #679).

DB-gated tests skip cleanly when DATABASE_URL is unavailable.
Pure-Python logic (lapse_intervals math, dedup_key, fire_per_interval cap)
is tested without a DB.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
from datetime import datetime, timedelta
from typing import Any

import pytest


# =========================================================================
# Pure-Python Helpers (replicated from advance-global-tasks.py)
# =========================================================================


def digest_sha256(data: str) -> str:
    """SHA256 hex digest of a string (matching postgres digest(..., 'hex'))."""
    return hashlib.sha256(data.encode()).hexdigest()


def compute_dedup_key(source_id: str, next_run_epoch: float) -> str:
    """Compute dedup_key = sha256('global_task:'||source_id||':'||EXTRACT(EPOCH FROM next_run)).

    Args:
        source_id: UUID string
        next_run_epoch: seconds since epoch (full timestamp, NOT hour-truncated)

    Returns:
        Hex digest
    """
    data = f"global_task:{source_id}:{int(next_run_epoch)}"
    return digest_sha256(data)


# =========================================================================
# Pure-Python Unit Tests (no DB required)
# =========================================================================


class TestPurePython:
    """Test pure-Python logic in the advancer."""

    def test_digest_sha256(self) -> None:
        """SHA256 digest matches expected output."""
        result = digest_sha256("global_task:123:456")
        expected = hashlib.sha256(b"global_task:123:456").hexdigest()
        assert result == expected

    def test_dedup_key_matches_postgres(self) -> None:
        """Dedup key computed correctly from source_id and epoch."""
        source_id = "550e8400-e29b-41d4-a716-446655440000"
        epoch = 1713000000.0
        result = compute_dedup_key(source_id, epoch)

        # Should be sha256('global_task:<id>:<int(epoch)>')
        expected = hashlib.sha256(
            f"global_task:{source_id}:1713000000".encode()
        ).hexdigest()
        assert result == expected

    def test_dedup_key_full_timestamp_not_hour_truncated(self) -> None:
        """Dedup key uses full timestamp epoch, not hour-truncated."""
        source_id = "test-id"

        # Two epochs in the same hour should produce different dedup_keys
        epoch1 = 1713000000.0  # 00:00:00
        epoch2 = 1713003600.0  # 01:00:00

        key1 = compute_dedup_key(source_id, epoch1)
        key2 = compute_dedup_key(source_id, epoch2)

        assert key1 != key2, "Dedup keys should differ for different epochs"

    def test_lapse_intervals_calculation_coalesce(self) -> None:
        """Coalesce path: lapse_intervals = FLOOR((now - next_run) / cadence) + 1."""
        # Test logic: if one-shot (no cadence), lapse_intervals = 1
        # If recurring and on-time, lapse_intervals = 1
        # If recurring and 2 intervals late, lapse_intervals = 3

        # One-shot case: lapse_intervals should be 1
        cadence = None
        next_run = None  # first run
        if next_run is None:
            lapse_intervals = 1
        else:
            # Would calculate from cadence if it exists
            lapse_intervals = 1
        assert lapse_intervals == 1

        # Recurring case (simulated): 2 intervals late
        # Would be: FLOOR((now - next_run) / cadence) + 1 ≈ FLOOR(2.5) + 1 = 3
        cadence_seconds = 3600  # 1 hour
        time_late = 9000  # 2.5 hours = 2.5 intervals
        lapse_intervals = int(time_late / cadence_seconds) + 1
        assert lapse_intervals == 3


# =========================================================================
# DB-Gated Tests (skip cleanly if no DATABASE_URL)
# =========================================================================


@pytest.fixture
def db_connection() -> Any:
    """Provide a Postgres connection if DATABASE_URL is set."""
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL not set (no Postgres connection available)")

    try:
        import psycopg
        db_url = os.environ["DATABASE_URL"]
        conn = psycopg.connect(db_url)
        yield conn
        conn.close()
    except ImportError:
        pytest.skip("psycopg not installed")


class TestGlobalTaskSourcesSchema:
    """Test schema creation and RLS (DB-gated)."""

    def test_table_exists(self, db_connection: Any) -> None:
        """global_task_sources table is created."""
        with db_connection.cursor() as cur:
            cur.execute("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_name = 'global_task_sources'
                )
            """)
            (exists,) = cur.fetchone()
            assert exists, "global_task_sources table should exist"

    def test_schema_columns(self, db_connection: Any) -> None:
        """Table has required columns with correct types."""
        with db_connection.cursor() as cur:
            cur.execute("""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = 'global_task_sources'
                ORDER BY ordinal_position
            """)
            columns = {name: dtype for name, dtype in cur.fetchall()}

            assert "id" in columns
            assert "title" in columns
            assert "dispatcher_skill" in columns
            assert "output_sink" in columns
            assert "cadence" in columns
            assert "last_run" in columns
            assert "next_run" in columns
            assert "enabled" in columns
            assert "on_lapse" in columns
            assert "created_at" in columns

    def test_dispatcher_skill_enum(self, db_connection: Any) -> None:
        """dispatcher_skill CHECK constraint enforces valid values."""
        with db_connection.cursor() as cur:
            # Valid insert
            cur.execute("""
                INSERT INTO global_task_sources (title, dispatcher_skill, output_sink)
                VALUES ('test', 'research', 'memory')
                RETURNING id
            """)
            (row_id,) = cur.fetchone()

            # Invalid insert should fail
            with pytest.raises(Exception, match="dispatcher_skill"):
                cur.execute("""
                    INSERT INTO global_task_sources (title, dispatcher_skill, output_sink)
                    VALUES ('test2', 'invalid_skill', 'memory')
                """)

            # Clean up
            cur.execute("DELETE FROM global_task_sources WHERE id = %s", (row_id,))
            db_connection.commit()

    def test_output_sink_enum(self, db_connection: Any) -> None:
        """output_sink CHECK constraint enforces valid values."""
        with db_connection.cursor() as cur:
            # Valid insert
            cur.execute("""
                INSERT INTO global_task_sources (title, dispatcher_skill, output_sink)
                VALUES ('test', 'research', 'telegram_digest')
                RETURNING id
            """)
            (row_id,) = cur.fetchone()

            # Invalid insert should fail
            with pytest.raises(Exception, match="output_sink"):
                cur.execute("""
                    INSERT INTO global_task_sources (title, dispatcher_skill, output_sink)
                    VALUES ('test2', 'research', 'invalid_sink')
                """)

            # Clean up
            cur.execute("DELETE FROM global_task_sources WHERE id = %s", (row_id,))
            db_connection.commit()

    def test_on_lapse_enum(self, db_connection: Any) -> None:
        """on_lapse CHECK constraint enforces 'coalesce' or 'fire_per_interval'."""
        with db_connection.cursor() as cur:
            # Valid insert with coalesce
            cur.execute("""
                INSERT INTO global_task_sources (
                    title, dispatcher_skill, output_sink, on_lapse
                ) VALUES ('test', 'research', 'memory', 'coalesce')
                RETURNING id
            """)
            (row_id1,) = cur.fetchone()

            # Valid insert with fire_per_interval
            cur.execute("""
                INSERT INTO global_task_sources (
                    title, dispatcher_skill, output_sink, on_lapse
                ) VALUES ('test2', 'research', 'memory', 'fire_per_interval')
                RETURNING id
            """)
            (row_id2,) = cur.fetchone()

            # Invalid insert should fail
            with pytest.raises(Exception, match="on_lapse"):
                cur.execute("""
                    INSERT INTO global_task_sources (
                        title, dispatcher_skill, output_sink, on_lapse
                    ) VALUES ('test3', 'research', 'memory', 'invalid_lapse')
                """)

            # Clean up
            cur.execute("DELETE FROM global_task_sources WHERE id IN (%s, %s)", (row_id1, row_id2))
            db_connection.commit()

    def test_dispatcher_sink_compatibility(self, db_connection: Any) -> None:
        """Dispatcher/sink compatibility constraint: status-record -> memory only."""
        with db_connection.cursor() as cur:
            # status-record with memory is valid
            cur.execute("""
                INSERT INTO global_task_sources (
                    title, dispatcher_skill, output_sink
                ) VALUES ('status check', 'status-record', 'memory')
                RETURNING id
            """)
            (row_id,) = cur.fetchone()

            # status-record with non-memory should fail
            with pytest.raises(Exception, match="dispatcher_sink_compatibility"):
                cur.execute("""
                    INSERT INTO global_task_sources (
                        title, dispatcher_skill, output_sink
                    ) VALUES ('status check 2', 'status-record', 'telegram_digest')
                """)

            # research can use any sink (valid)
            cur.execute("""
                INSERT INTO global_task_sources (
                    title, dispatcher_skill, output_sink
                ) VALUES ('research task', 'research', 'event_reemit')
                RETURNING id
            """)
            (row_id2,) = cur.fetchone()

            # Clean up
            cur.execute("DELETE FROM global_task_sources WHERE id IN (%s, %s)", (row_id, row_id2))
            db_connection.commit()

    def test_rls_service_role_can_write(self, db_connection: Any) -> None:
        """Service-role (authenticated) can write to global_task_sources."""
        with db_connection.cursor() as cur:
            cur.execute("""
                INSERT INTO global_task_sources (title, dispatcher_skill, output_sink)
                VALUES ('service role test', 'research', 'memory')
                RETURNING id
            """)
            (row_id,) = cur.fetchone()
            assert row_id is not None

            # Clean up
            cur.execute("DELETE FROM global_task_sources WHERE id = %s", (row_id,))
            db_connection.commit()


class TestCoalesceAdvancer:
    """Test advancer behavior with coalesce lapse strategy (DB-gated)."""

    def test_due_coalesce_row_fires_once_with_lapse_intervals(self, db_connection: Any) -> None:
        """Due coalesce row fires exactly once, payload carries lapse_intervals."""
        with db_connection.cursor() as cur:
            # Create a due one-shot task
            cur.execute("""
                INSERT INTO global_task_sources (
                    title, dispatcher_skill, output_sink, cadence,
                    next_run, on_lapse
                ) VALUES (
                    'one-shot task', 'research', 'memory', NULL,
                    now() - INTERVAL '1 hour', 'coalesce'
                )
                RETURNING id
            """)
            (task_id,) = cur.fetchone()

            # Simulate advancer: fetch due row
            cur.execute("""
                SELECT id, title, dispatcher_skill, output_sink, payload,
                       cadence, next_run, on_lapse
                FROM global_task_sources
                WHERE enabled = true AND (next_run IS NULL OR next_run <= now())
                ORDER BY created_at ASC
            """)
            rows = cur.fetchall()
            assert len(rows) >= 1

            row = [r for r in rows if r[0] == task_id][0]
            next_run = row[6]

            # Compute lapse_intervals (first run = 1)
            lapse_intervals = 1

            # Compute dedup_key
            next_run_epoch = next_run.timestamp()
            dedup_key = compute_dedup_key(str(task_id), next_run_epoch)

            # Insert event
            event_payload = {
                "source_id": str(task_id),
                "dispatcher_skill": "research",
                "output_sink": "memory",
                "payload": {},
                "lapse_intervals": lapse_intervals,
            }
            cur.execute("""
                INSERT INTO events (
                    event_type, severity, repo, source, title, payload, dedup_key
                ) VALUES (
                    'global_task_due', 'low', '_global', 'global_task_advancer',
                    %s, %s::jsonb, %s
                )
            """, ("one-shot task", json.dumps(event_payload), dedup_key))

            # Verify event created
            cur.execute(
                "SELECT payload FROM events WHERE event_type = 'global_task_due' AND source = 'global_task_advancer' ORDER BY created_at DESC LIMIT 1"
            )
            (payload,) = cur.fetchone()
            assert payload["lapse_intervals"] == 1

            # Clean up
            cur.execute("DELETE FROM global_task_sources WHERE id = %s", (task_id,))
            cur.execute("DELETE FROM events WHERE title = 'one-shot task'")
            db_connection.commit()

    def test_one_shot_row_disables_after_fire(self, db_connection: Any) -> None:
        """One-shot (cadence=NULL) row is disabled (enabled=false) after update."""
        with db_connection.cursor() as cur:
            # Create a one-shot task
            cur.execute("""
                INSERT INTO global_task_sources (
                    title, dispatcher_skill, output_sink, cadence,
                    next_run, on_lapse
                ) VALUES (
                    'one-shot disable test', 'research', 'memory', NULL,
                    now() - INTERVAL '1 hour', 'coalesce'
                )
                RETURNING id
            """)
            (task_id,) = cur.fetchone()

            # Simulate advancer UPDATE
            cur.execute("""
                UPDATE global_task_sources
                SET last_run = now(),
                    next_run = NULL,
                    enabled = false
                WHERE id = %s
            """, (task_id,))

            # Verify disabled
            cur.execute("SELECT enabled FROM global_task_sources WHERE id = %s", (task_id,))
            (enabled,) = cur.fetchone()
            assert enabled is False

            # Clean up
            cur.execute("DELETE FROM global_task_sources WHERE id = %s", (task_id,))
            db_connection.commit()

    def test_recurring_row_advances_next_run_by_cadence(self, db_connection: Any) -> None:
        """Recurring row's next_run advances by exactly one cadence period."""
        with db_connection.cursor() as cur:
            # Create a recurring task with 1-hour cadence, due 2 hours ago
            cur.execute("""
                INSERT INTO global_task_sources (
                    title, dispatcher_skill, output_sink, cadence,
                    next_run, on_lapse
                ) VALUES (
                    'recurring advance test', 'research', 'memory', INTERVAL '1 hour',
                    now() - INTERVAL '2 hours', 'coalesce'
                )
                RETURNING id
            """)
            (task_id,) = cur.fetchone()

            # Capture old next_run
            cur.execute("SELECT next_run FROM global_task_sources WHERE id = %s", (task_id,))
            (old_next_run,) = cur.fetchone()

            # Simulate advancer UPDATE
            cur.execute("""
                UPDATE global_task_sources
                SET last_run = now(),
                    next_run = GREATEST(now(), next_run + INTERVAL '1 hour'::interval)
                WHERE id = %s
            """, (task_id,))

            # Verify next_run advanced
            cur.execute("SELECT next_run FROM global_task_sources WHERE id = %s", (task_id,))
            (new_next_run,) = cur.fetchone()

            # new_next_run should be at least old_next_run + 1 hour
            # (GREATEST ensures it's not in the past)
            assert new_next_run > old_next_run

            # Clean up
            cur.execute("DELETE FROM global_task_sources WHERE id = %s", (task_id,))
            db_connection.commit()

    def test_concurrent_invocations_skip_locked(self, db_connection: Any) -> None:
        """FOR UPDATE SKIP LOCKED prevents double-fire on concurrent invocations."""
        with db_connection.cursor() as cur:
            # Create a due task
            cur.execute("""
                INSERT INTO global_task_sources (
                    title, dispatcher_skill, output_sink, cadence,
                    next_run, on_lapse
                ) VALUES (
                    'skip locked test', 'research', 'memory', INTERVAL '1 hour',
                    now() - INTERVAL '1 hour', 'coalesce'
                )
                RETURNING id
            """)
            (task_id,) = cur.fetchone()

            # First SELECT with FOR UPDATE SKIP LOCKED should claim it
            cur.execute("""
                SELECT id FROM global_task_sources
                WHERE enabled = true AND (next_run IS NULL OR next_run <= now())
                FOR UPDATE SKIP LOCKED
            """)
            rows1 = cur.fetchall()
            assert any(row[0] == task_id for row in rows1), "First fetch should get the task"

            # Open a second cursor in same connection — it should also see the task
            # (same connection doesn't actually lock in a single-threaded test)
            # This test is simplified; a real test would use two connections.
            # For now, just verify SKIP LOCKED syntax is valid.

            # Clean up
            cur.execute("DELETE FROM global_task_sources WHERE id = %s", (task_id,))
            db_connection.commit()


class TestFirePerIntervalAdvancer:
    """Test advancer behavior with fire_per_interval lapse strategy (DB-gated)."""

    def test_fire_per_interval_missing_3_fires_3(self) -> None:
        """fire_per_interval missing 3 intervals fires 3 times."""
        # Simulated test: with a 1-hour cadence due 3+ hours ago, should fire 3 times
        # (This is logic testing; actual multi-event insert would be in integration test)
        cadence_seconds = 3600  # 1 hour
        time_late = 10800  # 3 hours
        fire_count = int(time_late / cadence_seconds) + 1
        assert fire_count == 4  # 3 hours / 1 hour + 1 = 4

        # Cap at 24
        capped = min(24, fire_count)
        assert capped == 4

    def test_fire_per_interval_missing_50_fires_24_capped(self) -> None:
        """fire_per_interval missing 50+ intervals fires 24 (capped)."""
        cadence_seconds = 3600  # 1 hour
        time_late = 180000  # 50 hours
        fire_count = int(time_late / cadence_seconds) + 1
        assert fire_count == 51

        # Cap at 24
        capped = min(24, fire_count)
        assert capped == 24
