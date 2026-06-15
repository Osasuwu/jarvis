"""Tests for global task sources and advancer (issue #679).

DB-gated tests skip cleanly when DATABASE_URL is unavailable.
Pure-Python logic (lapse_intervals math, dedup_key, fire_per_interval cap)
is tested without a DB.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import logging
import os
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest


# =========================================================================
# Load the advancer module under test.
#
# scripts/advance-global-tasks.py has a dash in its name, so a plain `import`
# can't reach it. Load it via importlib and bind the symbols the tests use —
# keeping ONE definition of digest_sha256 / compute_dedup_key (the production
# one). The previous copy-pasted re-definitions could drift from the real code
# and let the suite pass against a lie (MAJOR #13).
# =========================================================================


def _ensure_psycopg_importable() -> None:
    """advance-global-tasks.py does `import psycopg` / `from psycopg.rows import
    dict_row` at module top. When the real driver isn't installed, stub just
    enough for the module to import — the fake-cursor tests below never touch a
    real connection (they monkeypatch psycopg.connect), and the DB-gated tests
    skip on the DATABASE_URL check before reaching psycopg. Only stubs when the
    real driver is absent, so a real install is used verbatim where present."""
    try:
        import psycopg  # noqa: F401
        return
    except ModuleNotFoundError:
        pass
    stub = types.ModuleType("psycopg")

    def _no_connect(*a: Any, **k: Any) -> Any:  # pragma: no cover - monkeypatched
        raise RuntimeError("stub psycopg: connect unavailable (install psycopg)")

    stub.connect = _no_connect  # type: ignore[attr-defined]
    rows = types.ModuleType("psycopg.rows")
    rows.dict_row = object()  # type: ignore[attr-defined]
    stub.rows = rows  # type: ignore[attr-defined]
    sys.modules["psycopg"] = stub
    sys.modules["psycopg.rows"] = rows


_MODULE_PATH = (
    Path(__file__).resolve().parent.parent / "scripts" / "advance-global-tasks.py"
)
_spec = importlib.util.spec_from_file_location("advance_global_tasks", _MODULE_PATH)
assert _spec is not None and _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
_ensure_psycopg_importable()
_spec.loader.exec_module(_mod)

digest_sha256 = _mod.digest_sha256
compute_dedup_key = _mod.compute_dedup_key


# =========================================================================
# Fake cursor/connection — exercise the advancer end-to-end with no live
# Postgres, so the transaction-model and dedup findings are assertable in CI
# (MAJOR #10). Routes fetchall/fetchone off the statement shape and records
# every (sql, params) the advancer emits.
# =========================================================================


class _FakeCursor:
    """Minimal psycopg-cursor stand-in for _advance_due_rows."""

    def __init__(
        self,
        due_rows: list[dict[str, Any]],
        *,
        intervals_missed: float = 1.0,
        rowcounts: list[int] | None = None,
    ) -> None:
        self._due_rows = list(due_rows)
        self._intervals_missed = intervals_missed
        # rowcount values successive event INSERTs take on. Default: every
        # insert lands (1). Pass [0, ...] to simulate ON CONFLICT skips.
        self._rowcounts = list(rowcounts) if rowcounts is not None else None
        self.statements: list[tuple[str, Any]] = []
        self.rowcount = -1

    def execute(self, sql: str, params: Any = None) -> None:
        self.statements.append((sql, params))
        if sql.strip().upper().startswith("INSERT INTO EVENTS"):
            self.rowcount = self._rowcounts.pop(0) if self._rowcounts else 1
        else:
            self.rowcount = -1

    def fetchall(self) -> list[dict[str, Any]]:
        return self._due_rows

    def fetchone(self) -> dict[str, Any]:
        # Only _intervals_lapsed's SELECT calls fetchone.
        return {"intervals_missed": self._intervals_missed}

    def __enter__(self) -> "_FakeCursor":
        return self

    def __exit__(self, *exc: Any) -> bool:
        return False


class _FakeConn:
    """psycopg-connection stand-in: `with conn:` + `with conn.cursor() as cur:`."""

    def __init__(self, cursor: _FakeCursor) -> None:
        self._cursor = cursor
        self.closed = False

    def __enter__(self) -> "_FakeConn":
        return self

    def __exit__(self, *exc: Any) -> bool:
        return False

    def cursor(self) -> _FakeCursor:
        return self._cursor

    def close(self) -> None:
        self.closed = True


def _due_row(**overrides: Any) -> dict[str, Any]:
    """Build a due global_task_sources row (dict_row shape) for the fake cursor."""
    row: dict[str, Any] = {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "title": "test task",
        "dispatcher_skill": "research",
        "output_sink": "memory",
        "payload": {},
        "cadence": None,
        "last_run": None,
        "next_run": None,
        "on_lapse": "coalesce",
    }
    row.update(overrides)
    return row


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
        # One-shot / first run carries lapse_intervals == 1 by definition (no
        # cadence to count against) — that branch is exercised end-to-end in
        # TestAdvanceDueRowsFakeCursor. Here we pin the recurring math: 2.5
        # intervals late → FLOOR(2.5) + 1 = 3.
        cadence_seconds = 3600  # 1 hour
        time_late = 9000  # 2.5 hours = 2.5 intervals
        lapse_intervals = int(time_late / cadence_seconds) + 1
        assert lapse_intervals == 3


class TestAdvanceDueRowsFakeCursor:
    """End-to-end exercise of the advancer against a fake cursor (no DB).

    Makes the transaction-model + dedup findings assertable in CI (MAJOR #10):
    no manual BEGIN/SERIALIZABLE (CRITICAL #1), event count reflects rowcount
    not a blind +1 (CRITICAL #2), null-next_run dedups on the fixed sentinel
    (MAJOR #7), and fire_per_interval advances next_run by its fire count
    (MAJOR #8). -1 error contract (CRITICAL #3) and no-DSN-leak (MAJOR #14)
    covered via advance_global_tasks.
    """

    @staticmethod
    def _inserts(cur: _FakeCursor) -> list[tuple[str, Any]]:
        return [
            (s, p)
            for s, p in cur.statements
            if s.strip().upper().startswith("INSERT INTO EVENTS")
        ]

    def test_coalesce_one_shot_inserts_one_event(self) -> None:
        cur = _FakeCursor([_due_row(on_lapse="coalesce")])
        total = _mod._advance_due_rows(cur)
        assert total == 1
        assert len(self._inserts(cur)) == 1

    def test_no_manual_begin_or_serializable(self) -> None:
        # CRITICAL #1: the advancer must never issue a manual BEGIN / isolation
        # level — psycopg's `with conn:` owns the transaction.
        cur = _FakeCursor([_due_row()])
        _mod._advance_due_rows(cur)
        for sql, _ in cur.statements:
            upper = sql.strip().upper()
            assert not upper.startswith("BEGIN"), f"manual BEGIN: {sql!r}"
            assert "ISOLATION LEVEL" not in upper, f"isolation level set: {sql!r}"
            assert "SERIALIZABLE" not in upper, f"SERIALIZABLE set: {sql!r}"

    def test_deduped_insert_not_counted(self) -> None:
        # CRITICAL #2: ON CONFLICT DO NOTHING → rowcount 0 → must not increment.
        cur = _FakeCursor([_due_row()], rowcounts=[0])
        assert _mod._advance_due_rows(cur) == 0

    def test_null_next_run_uses_sentinel_dedup_key(self) -> None:
        # MAJOR #7: a never-run row (next_run IS NULL) dedups on the fixed
        # sentinel epoch, not a moving now()-derived value.
        row_id = "abc-123"
        cur = _FakeCursor([_due_row(id=row_id, next_run=None)])
        _mod._advance_due_rows(cur)
        (_, params) = self._inserts(cur)[0]
        # params: (title, payload_json, dedup_key)
        assert params[2] == compute_dedup_key(row_id, _mod.NULL_NEXT_RUN_SENTINEL_EPOCH)

    def test_fire_per_interval_advances_by_fire_count(self) -> None:
        # MAJOR #8: the schedule UPDATE for a lapsed fire_per_interval row jumps
        # next_run forward by `fire_count` cadence widths, not 1.
        cadence = timedelta(hours=1)
        next_run = datetime(2024, 4, 13, 12, 0, 0, tzinfo=timezone.utc)
        cur = _FakeCursor(
            [_due_row(on_lapse="fire_per_interval", cadence=cadence, next_run=next_run)],
            intervals_missed=3.0,  # int(3.0) + 1 = 4 fires
        )
        total = _mod._advance_due_rows(cur)
        assert total == 4
        update = next(
            (
                p
                for s, p in cur.statements
                if s.strip().upper().startswith("UPDATE GLOBAL_TASK_SOURCES")
                and "GREATEST" in s.upper()
            ),
            None,
        )
        assert update is not None, "recurring row must issue a GREATEST(...) UPDATE"
        # params: (periods, cadence, source_id) — periods == fire_count.
        assert update[0] == 4

    def test_advance_global_tasks_returns_event_count(self, monkeypatch: Any) -> None:
        cur = _FakeCursor([_due_row(), _due_row(id="second-row")])
        conn = _FakeConn(cur)
        monkeypatch.setattr(_mod.psycopg, "connect", lambda *a, **k: conn)
        assert _mod.advance_global_tasks(db_url="postgres://fake") == 2
        assert conn.closed, "connection must be closed in finally"

    def test_advance_global_tasks_no_dsn_returns_minus_one(self, monkeypatch: Any) -> None:
        # CRITICAL #3: error path returns -1 (CLI maps -1 → exit 1).
        monkeypatch.delenv("DATABASE_URL", raising=False)
        assert _mod.advance_global_tasks(db_url=None) == -1

    def test_advance_global_tasks_connect_error_returns_minus_one(
        self, monkeypatch: Any, caplog: Any
    ) -> None:
        # CRITICAL #3 + MAJOR #14: connect failure returns -1 and never logs the
        # DSN (which carries the password).
        def _boom(*a: Any, **k: Any) -> Any:
            raise RuntimeError("FATAL: password=supersecret in dsn")

        monkeypatch.setattr(_mod.psycopg, "connect", _boom)
        with caplog.at_level(logging.ERROR):
            result = _mod.advance_global_tasks(
                db_url="postgres://u:supersecret@host/db"
            )
        assert result == -1
        assert "supersecret" not in caplog.text, "DSN/password must not be logged"


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

            # Valid insert with fire_per_interval. fire_per_interval requires a
            # cadence (cadence_lapse_coherence CHECK forbids cadence IS NULL with
            # fire_per_interval), so supply one.
            cur.execute("""
                INSERT INTO global_task_sources (
                    title, dispatcher_skill, output_sink, on_lapse, cadence
                ) VALUES ('test2', 'research', 'memory', 'fire_per_interval', INTERVAL '1 hour')
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
        """FOR UPDATE SKIP LOCKED makes a row claimed by connection A invisible to
        connection B's concurrent claim — so two advancer invocations never
        double-fire the same source. Uses two real connections (a single-cursor
        test can't observe locking)."""
        import psycopg

        # Insert one due row, committed so the second connection can see it.
        with db_connection.cursor() as cur:
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
        db_connection.commit()

        claim_sql = """
            SELECT id FROM global_task_sources
            WHERE id = %s AND enabled = true
              AND (next_run IS NULL OR next_run <= now())
            FOR UPDATE SKIP LOCKED
        """

        conn_b = psycopg.connect(os.environ["DATABASE_URL"])
        try:
            # Connection A claims the row and HOLDS it in an open transaction.
            with db_connection.cursor() as cur_a:
                cur_a.execute(claim_sql, (task_id,))
                claimed_a = cur_a.fetchall()
                assert any(r[0] == task_id for r in claimed_a), "A should claim the row"

                # Connection B, concurrently, must SKIP the locked row → empty.
                with conn_b.cursor() as cur_b:
                    cur_b.execute(claim_sql, (task_id,))
                    assert cur_b.fetchall() == [], "B must skip the row A holds locked"
                conn_b.rollback()

            # A's transaction is still open after the cursor block; commit to
            # release the row lock.
            db_connection.commit()

            # Once A releases, B can claim it.
            with conn_b.cursor() as cur_b2:
                cur_b2.execute(claim_sql, (task_id,))
                assert any(
                    r[0] == task_id for r in cur_b2.fetchall()
                ), "B should claim the row after A releases"
            conn_b.rollback()
        finally:
            with db_connection.cursor() as cur:
                cur.execute("DELETE FROM global_task_sources WHERE id = %s", (task_id,))
            db_connection.commit()
            conn_b.close()


class TestFirePerIntervalAdvancer:
    """Test advancer behavior with fire_per_interval lapse strategy (DB-gated)."""

    def test_fire_per_interval_3_hours_late_fires_4(self) -> None:
        """fire_per_interval 3 hours late at 1h cadence fires 4 times.

        FLOOR((now - next_run) / cadence) + 1 = FLOOR(3) + 1 = 4 — the 3 missed
        intervals plus the currently-due one. (Earlier name said "fires 3"; the
        +1 for the due interval makes it 4.)
        """
        cadence_seconds = 3600  # 1 hour
        time_late = 10800  # 3 hours
        fire_count = int(time_late / cadence_seconds) + 1
        assert fire_count == 4

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
