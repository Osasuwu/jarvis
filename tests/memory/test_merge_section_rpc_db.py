"""DB-gated tests for merge_section_into_memory_upsert's soft-delete revival
fix (#1714, decision 84c5b737-1887-4c78-9d8b-e58dedac2b04).

The bug and the mocked-client-level pin of the Python-side half of the fix
live in tests/memory/test_memory_store_merge_section.py — this file exercises
the plpgsql half against real Postgres, which is the only way to prove:

  - a soft-deleted (project, name) row is found and revived via UPDATE,
    instead of falling into the INSERT branch and raising 23505 against the
    still-present unique(project, name) constraint (AC1-AC3)
  - the revived row's prior description/tags are NOT preserved, even though
    p_preserve_existing_description/p_preserve_existing_tags default true
    (AC1, "revive-fresh" not "revive+preserve")
  - a live (non-deleted) row's preserve semantics are unaffected (regression
    guard for the fix's scope)
  - the OCC compare-and-swap on updated_at still rejects a stale caller

Run by the `pytest-db-pgvector` job in .github/workflows/pytest.yml, which
bootstraps tests/ci/pgvector_schema_bootstrap.sql and applies both the base
and fix migrations on top. Skips cleanly with no DATABASE_URL (local/non-DB
runs); REQUIRE_DB=1 (set by that job) turns a missing DATABASE_URL into a
hard failure instead of a silent skip, mirroring
tests/memory/test_find_consolidation_clusters_db.py (#1187).
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest


BASE_TIME = datetime(2026, 1, 1, tzinfo=timezone.utc)


@pytest.fixture
def db_connection() -> Any:
    """Postgres connection, rolled back (never committed) after each test.

    Mirrors test_find_consolidation_clusters_db.py::db_connection.
    """
    db_url = os.environ.get("DATABASE_URL")
    require_db = os.environ.get("REQUIRE_DB", "").strip() not in ("", "0")
    if not db_url:
        if require_db:
            pytest.fail(
                "REQUIRE_DB is set but DATABASE_URL is missing — the DB-gated "
                "merge_section_into_memory_upsert tests must run against real "
                "Postgres in this job, not silently skip (#1714)."
            )
        pytest.skip("DATABASE_URL not set (no Postgres connection available)")

    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError:
        pytest.skip("psycopg not installed")

    try:
        conn = psycopg.connect(db_url, row_factory=dict_row, autocommit=False)
    except Exception as e:  # noqa: BLE001 — connection failure must fail loudly, not skip
        pytest.fail(f"could not connect to DATABASE_URL: {type(e).__name__}")

    try:
        yield conn
    finally:
        conn.rollback()
        conn.close()


def _insert_memory(
    conn: Any,
    *,
    name: str,
    project: str = "test-proj",
    mtype: str = "project",
    content: str = "original content",
    description: str | None = "original description",
    tags: list[str] | None = None,
    updated_at: datetime = BASE_TIME,
    deleted_at: datetime | None = None,
    source_provenance: str | None = "rpc:merge_section",
) -> tuple[str, datetime]:
    with conn.cursor() as cur:
        cur.execute(
            """
            insert into memories
              (type, project, name, content, description, tags, updated_at,
               deleted_at, source_provenance)
            values
              (%(type)s, %(project)s, %(name)s, %(content)s, %(description)s,
               %(tags)s, %(updated_at)s, %(deleted_at)s, %(source_provenance)s)
            returning id, updated_at
            """,
            {
                "type": mtype,
                "project": project,
                "name": name,
                "content": content,
                "description": description,
                "tags": tags or ["original-tag"],
                "updated_at": updated_at,
                "deleted_at": deleted_at,
                "source_provenance": source_provenance,
            },
        )
        row = cur.fetchone()
        return str(row["id"]), row["updated_at"]


def _call_rpc(
    conn: Any,
    *,
    project: str,
    name: str,
    merged_content: str,
    expected_updated_at: datetime,
    description: str = "new description",
    tags: list[str] | None = None,
    preserve_description: bool = True,
    preserve_tags: bool = True,
) -> dict:
    with conn.cursor() as cur:
        cur.execute(
            """
            select * from merge_section_into_memory_upsert(
              p_project => %(project)s,
              p_name => %(name)s,
              p_merged_content => %(merged_content)s,
              p_expected_updated_at => %(expected_updated_at)s,
              p_description => %(description)s,
              p_tags => %(tags)s,
              p_preserve_existing_description => %(preserve_description)s,
              p_preserve_existing_tags => %(preserve_tags)s
            )
            """,
            {
                "project": project,
                "name": name,
                "merged_content": merged_content,
                "expected_updated_at": expected_updated_at,
                "description": description,
                "tags": tags or ["new-tag"],
                "preserve_description": preserve_description,
                "preserve_tags": preserve_tags,
            },
        )
        return cur.fetchone()


def _fetch_row(conn: Any, *, project: str, name: str) -> dict:
    with conn.cursor() as cur:
        cur.execute(
            "select * from memories where project = %s and name = %s",
            (project, name),
        )
        return cur.fetchone()


class TestSoftDeletedRowRevival:
    def test_soft_deleted_row_is_revived_without_unique_violation(self, db_connection: Any) -> None:
        _id, updated_at = _insert_memory(
            db_connection,
            name="tombstoned",
            deleted_at=BASE_TIME + timedelta(days=1),
        )

        result = _call_rpc(
            db_connection,
            project="test-proj",
            name="tombstoned",
            merged_content="revived content",
            expected_updated_at=updated_at,
        )

        assert result["success"] is True, result["conflict_reason"]
        assert str(result["memory_id"]) == _id
        assert result["revived"] is True

        row = _fetch_row(db_connection, project="test-proj", name="tombstoned")
        assert row["deleted_at"] is None
        assert row["content"] == "revived content"

    def test_soft_deleted_row_does_not_preserve_prior_description_or_tags(
        self, db_connection: Any
    ) -> None:
        _id, updated_at = _insert_memory(
            db_connection,
            name="tombstoned-2",
            description="stale description",
            tags=["stale-tag"],
            deleted_at=BASE_TIME + timedelta(days=1),
        )

        _call_rpc(
            db_connection,
            project="test-proj",
            name="tombstoned-2",
            merged_content="revived content",
            expected_updated_at=updated_at,
            description="fresh description",
            tags=["fresh-tag"],
            preserve_description=True,
            preserve_tags=True,
        )

        row = _fetch_row(db_connection, project="test-proj", name="tombstoned-2")
        assert row["description"] == "fresh description"
        assert row["tags"] == ["fresh-tag"]

    def test_live_row_still_preserves_description_and_tags(self, db_connection: Any) -> None:
        _id, updated_at = _insert_memory(
            db_connection,
            name="live-row",
            description="kept description",
            tags=["kept-tag"],
            deleted_at=None,
        )

        result = _call_rpc(
            db_connection,
            project="test-proj",
            name="live-row",
            merged_content="merged content",
            expected_updated_at=updated_at,
            description="ignored description",
            tags=["ignored-tag"],
            preserve_description=True,
            preserve_tags=True,
        )

        assert result["success"] is True, result["conflict_reason"]
        assert result["revived"] is False

        row = _fetch_row(db_connection, project="test-proj", name="live-row")
        assert row["description"] == "kept description"
        assert row["tags"] == ["kept-tag"]

    def test_stale_expected_updated_at_is_rejected(self, db_connection: Any) -> None:
        _insert_memory(
            db_connection,
            name="tombstoned-3",
            deleted_at=BASE_TIME + timedelta(days=1),
        )

        result = _call_rpc(
            db_connection,
            project="test-proj",
            name="tombstoned-3",
            merged_content="should not apply",
            expected_updated_at=BASE_TIME - timedelta(days=100),
        )

        assert result["success"] is False
        assert result["conflict_reason"] == "merge_conflict: concurrent modification"

        row = _fetch_row(db_connection, project="test-proj", name="tombstoned-3")
        assert row["deleted_at"] is not None, "rejected call must not revive the row"
