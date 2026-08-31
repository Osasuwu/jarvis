"""DB-gated tests for task_queue.enqueue()'s target-pin CAS (#1085 S1-3, #1119).

Unit tests in tests/reactive_core/test_agents_task_queue.py cover enqueue()'s
collision-handling code path against a hand-rolled stub that mimics Postgres's
unique-violation behavior. That proves the Python is correct, not that the
partial unique index actually enforces the CAS. This file runs the same
enqueue() call against real Postgres, applying the REAL migrations
(supabase/migrations/20260811163000_add_task_queue_issue_number.sql, then
supabase/migrations/20260831120000_task_queue_pins_tier_substrate_parked_fsm.sql)
on top of the pre-#1085 table shape, so the constraint itself is under test.

#1119 replaced idx_task_queue_issue_number_active with
idx_task_queue_target_active on (target_repo, target_type, target_number),
scoped to pending/claimed/running/parked (parked added because #1119 made it
non-terminal — decision f24ad617). enqueue() still derives those pin columns
from issue_number when the caller doesn't pass them explicitly, so most tests
below keep using issue_number as the ergonomic entry point; the CAS itself now
keys on the derived columns, which the new test cases assert directly.

enqueue() is written against the supabase-py/postgrest client interface, but
the DB-gated CI convention (pytest-db, pytest-db-pgvector) only stands up raw
Postgres — no PostgREST layer. _FakeClient below is a thin adapter
implementing just the ``.table(x).upsert(row, on_conflict=, ignore_
duplicates=).execute()`` surface enqueue() calls, via raw SQL, translating a
real ``psycopg.errors.UniqueViolation`` into a real
``postgrest.exceptions.APIError`` — so enqueue()'s production code runs
completely unmodified while the constraint enforcement underneath it is 100%
real Postgres DDL.

Run by the `pytest-db-task-queue` job in .github/workflows/pytest.yml.
"""

from __future__ import annotations

import os
import uuid
from typing import Any

import pytest

from agents.task_queue import enqueue


@pytest.fixture
def db_connection() -> Any:
    """Real Postgres connection, autocommit, dict rows; truncates task_queue.

    Gating logic mirrors tests/reactive_core/test_global_task_advancer.py::db_connection
    (#975): REQUIRE_DB set but DATABASE_URL missing is a hard failure, not a
    skip, so this job can't quietly revert to never running.

    autocommit=True (unlike the advancer fixture) because a UniqueViolation
    from the issue_number CAS must not poison the connection for the next
    enqueue() call in the same test — under an explicit transaction, Postgres
    aborts the whole transaction on the first error and every statement after
    it raises "current transaction is aborted" until a rollback.
    """
    db_url = os.environ.get("DATABASE_URL")
    require_db = os.environ.get("REQUIRE_DB", "").strip() not in ("", "0")
    if not db_url:
        if require_db:
            pytest.fail(
                "REQUIRE_DB is set but DATABASE_URL is missing — the DB-gated "
                "task_queue issue_number tests must run against real Postgres "
                "in this job, not silently skip (#1085 S1-3)."
            )
        pytest.skip("DATABASE_URL not set (no Postgres connection available)")

    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError:
        pytest.skip("psycopg not installed")

    try:
        conn = psycopg.connect(db_url, row_factory=dict_row, autocommit=True)
    except Exception as e:  # noqa: BLE001 — must fail loudly, never echo db_url (carries the password)
        pytest.fail(f"could not connect to DATABASE_URL: {type(e).__name__}")

    try:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE task_queue")
        yield conn
    finally:
        conn.close()


class _PostgrestLikeUpsert:
    """Just enough of postgrest's query-builder surface for enqueue()'s upsert."""

    def __init__(self, conn: Any, table_name: str) -> None:
        self._conn = conn
        self._table = table_name
        self._row: dict[str, Any] = {}
        self._on_conflict = ""

    def upsert(
        self, row: dict[str, Any], *, on_conflict: str, ignore_duplicates: bool
    ) -> "_PostgrestLikeUpsert":
        assert ignore_duplicates, "enqueue() always passes ignore_duplicates=True (#1455 AC5)"
        self._row = row
        self._on_conflict = on_conflict
        return self

    def execute(self) -> "_Result":
        from postgrest.exceptions import APIError
        from psycopg.errors import UniqueViolation

        columns = list(self._row.keys())
        col_list = ", ".join(columns)
        placeholders = ", ".join(f"%({c})s" for c in columns)
        # ON CONFLICT names only the idempotency_key arbiter, matching
        # production's on_conflict="idempotency_key" — a violation on any
        # OTHER unique index (idx_task_queue_issue_number_active) is not
        # suppressed and raises normally, exactly like real PostgREST.
        sql = (
            f"INSERT INTO {self._table} ({col_list}) VALUES ({placeholders}) "
            f"ON CONFLICT ({self._on_conflict}) DO NOTHING RETURNING *"
        )
        try:
            with self._conn.cursor() as cur:
                cur.execute(sql, self._row)
                data = cur.fetchall()
        except UniqueViolation as e:
            raise APIError(
                {"code": "23505", "message": str(e), "details": None, "hint": None}
            ) from e
        return _Result([dict(r) for r in data])


class _Result:
    def __init__(self, data: list[dict[str, Any]]) -> None:
        self.data = data


class _FakeClient:
    """Just enough of the supabase Client surface for enqueue()'s upsert call."""

    def __init__(self, conn: Any) -> None:
        self._conn = conn

    def table(self, name: str) -> _PostgrestLikeUpsert:
        return _PostgrestLikeUpsert(self._conn, name)


def _key() -> str:
    return uuid.uuid4().hex


class TestTargetActiveCAS:
    """Real-constraint proof for idx_task_queue_target_active (#1119).

    #1119 replaced idx_task_queue_issue_number_active with a structured-pin
    index on (target_repo, target_type, target_number), scoped to
    pending/claimed/running/parked. issue_number is still the ergonomic
    kwarg callers pass, but enqueue() now derives the pin columns from it
    (agents/task_queue.py) and the CAS actually keys on those. parked is
    new to the scoped set here — decision f24ad617 made parked non-terminal,
    so a parked row must still occupy the CAS slot instead of freeing it.
    """

    def test_same_idempotency_key_collision_returns_none(self, db_connection: Any) -> None:
        client = _FakeClient(db_connection)
        key = _key()

        first = enqueue(goal="g1", idempotency_key=key, issue_number=101, client=client)
        assert first is not None

        second = enqueue(goal="g1 retry", idempotency_key=key, issue_number=101, client=client)
        assert second is None

    def test_different_key_same_issue_number_active_row_collides(self, db_connection: Any) -> None:
        client = _FakeClient(db_connection)

        first = enqueue(goal="g1", idempotency_key=_key(), issue_number=202, client=client)
        assert first is not None
        assert first["status"] == "pending"  # non-terminal — covered by the partial index

        second = enqueue(goal="g2", idempotency_key=_key(), issue_number=202, client=client)
        assert second is None

    def test_different_key_same_issue_number_terminal_row_does_not_block(
        self, db_connection: Any
    ) -> None:
        client = _FakeClient(db_connection)

        first = enqueue(goal="g1", idempotency_key=_key(), issue_number=303, client=client)
        assert first is not None

        with db_connection.cursor() as cur:
            cur.execute(
                "UPDATE task_queue SET status = 'done' WHERE id = %(id)s", {"id": first["id"]}
            )

        second = enqueue(goal="g2", idempotency_key=_key(), issue_number=303, client=client)
        assert second is not None
        assert second["issue_number"] == 303

    def test_issue_number_derived_pin_is_what_cas_keys_on(self, db_connection: Any) -> None:
        """#1119: the index is on (target_repo, target_type, target_number),
        not issue_number directly — prove the derived pin is what fires."""
        client = _FakeClient(db_connection)

        first = enqueue(goal="g1", idempotency_key=_key(), issue_number=404, client=client)
        assert first is not None
        assert first["target_type"] == "issue"
        assert first["target_number"] == 404
        assert first["target_repo"]

        second = enqueue(goal="g2", idempotency_key=_key(), issue_number=404, client=client)
        assert second is None

    def test_parked_row_still_blocks_new_enqueue(self, db_connection: Any) -> None:
        """#1119: parked is non-terminal now and included in the index's
        where clause, so a parked row's pin must keep blocking a re-enqueue
        (unlike the pre-#1119 world where parked was terminal and freed the
        slot)."""
        client = _FakeClient(db_connection)

        first = enqueue(goal="g1", idempotency_key=_key(), issue_number=505, client=client)
        assert first is not None

        with db_connection.cursor() as cur:
            cur.execute(
                "UPDATE task_queue SET status = 'parked' WHERE id = %(id)s", {"id": first["id"]}
            )

        second = enqueue(goal="g2", idempotency_key=_key(), issue_number=505, client=client)
        assert second is None


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
