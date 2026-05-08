"""Meta-test for sandcastle anon-INSERT RLS gate (slice 3, #542).

Same pattern as test_schema_drift_guard.py (#326): parse the migration SQL,
reimplement the policy decision rule in Python, assert positive + negative
cases. CI does not require a live DB — parsing alone catches drift between
schema.sql and the migration file, plus any regression in policy shape.

Two layers:

1. **Migration shape** — the migration must (a) drop the legacy broad
   "Allow all for anon" policy on each of the four tables, and (b) install
   a "FOR INSERT TO anon" policy whose WITH CHECK clause references the
   per-table provenance column with a 'sandcastle:%' LIKE prefix.

2. **Policy logic** — given a candidate row payload, a pure-Python
   reimplementation of the WITH CHECK predicate must accept rows whose
   per-table provenance column starts with 'sandcastle:' and reject all
   others. Service-role writes bypass RLS, modeled here as `role='service'`.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_PATH = (
    REPO_ROOT
    / "supabase"
    / "migrations"
    / "20260508120000_sandcastle_anon_rls_provenance_gate.sql"
)
SCHEMA_PATH = REPO_ROOT / "mcp-memory" / "schema.sql"

# Per-table provenance column. memories + task_outcomes use source_provenance;
# episodes + events_canonical use the existing `actor` column (semantic match —
# `actor` is already the provenance field per their schema comments).
PROVENANCE_COLUMN = {
    "memories": "source_provenance",
    "task_outcomes": "source_provenance",
    "episodes": "actor",
    "events_canonical": "actor",
}


# -- Migration shape --------------------------------------------------------


def _migration_sql() -> str:
    assert MIGRATION_PATH.exists(), f"Missing migration: {MIGRATION_PATH}"
    return MIGRATION_PATH.read_text(encoding="utf-8")


def _schema_sql() -> str:
    return SCHEMA_PATH.read_text(encoding="utf-8")


class TestMigrationShape:
    def test_migration_file_exists(self):
        assert MIGRATION_PATH.exists()

    def test_task_outcomes_gets_source_provenance_column(self):
        sql = _migration_sql()
        assert re.search(
            r"ALTER\s+TABLE\s+task_outcomes\s+ADD\s+COLUMN\s+IF\s+NOT\s+EXISTS\s+source_provenance",
            sql,
            re.IGNORECASE,
        ), "Migration must add source_provenance column to task_outcomes"

    @pytest.mark.parametrize("table", list(PROVENANCE_COLUMN.keys()))
    def test_drops_legacy_anon_policy(self, table: str):
        sql = _migration_sql()
        pattern = rf'DROP\s+POLICY\s+IF\s+EXISTS\s+"Allow all for anon"\s+ON\s+{table}\b'
        assert re.search(pattern, sql, re.IGNORECASE), (
            f"Migration must drop legacy 'Allow all for anon' policy on {table}"
        )

    @pytest.mark.parametrize("table,column", list(PROVENANCE_COLUMN.items()))
    def test_installs_sandcastle_insert_policy(self, table: str, column: str):
        sql = _migration_sql()
        # Match: CREATE POLICY ... ON <table> FOR INSERT TO anon WITH CHECK (<col> LIKE 'sandcastle:%')
        pattern = (
            rf"CREATE\s+POLICY\s+\"[^\"]+\"\s+ON\s+{table}\s+"
            rf"FOR\s+INSERT\s+TO\s+anon\s+"
            rf"WITH\s+CHECK\s*\(\s*{column}\s+LIKE\s+'sandcastle:%'\s*\)"
        )
        assert re.search(pattern, sql, re.IGNORECASE), (
            f"Missing or malformed sandcastle INSERT policy on {table} "
            f"(expected WITH CHECK ({column} LIKE 'sandcastle:%'))"
        )

    @pytest.mark.parametrize("table", list(PROVENANCE_COLUMN.keys()))
    def test_anon_select_preserved(self, table: str):
        """SELECT for anon must remain wide-open — only INSERT is gated."""
        sql = _migration_sql()
        pattern = (
            rf"CREATE\s+POLICY\s+\"[^\"]+\"\s+ON\s+{table}\s+"
            rf"FOR\s+SELECT\s+TO\s+anon\s+USING\s*\(\s*true\s*\)"
        )
        assert re.search(pattern, sql, re.IGNORECASE), (
            f"Anon SELECT policy missing or restrictive on {table}"
        )


class TestSchemaMirror:
    """schema.sql is the canonical doc; migration is the apply unit. Both
    must agree on the new policy shape (per #326 schema-drift CI gate)."""

    @pytest.mark.parametrize("table,column", list(PROVENANCE_COLUMN.items()))
    def test_schema_has_sandcastle_insert_policy(self, table: str, column: str):
        sql = _schema_sql()
        pattern = (
            rf"CREATE\s+POLICY\s+\"[^\"]+\"\s+ON\s+{table}\s+"
            rf"FOR\s+INSERT\s+TO\s+anon\s+"
            rf"WITH\s+CHECK\s*\(\s*{column}\s+LIKE\s+'sandcastle:%'\s*\)"
        )
        assert re.search(pattern, sql, re.IGNORECASE), (
            f"schema.sql is missing the sandcastle INSERT policy for {table}; "
            f"it has drifted from the migration."
        )

    def test_schema_has_no_legacy_broad_anon_policy(self):
        """The phrase 'Allow all for anon' is the legacy broad policy we
        replaced. If it survives in schema.sql for any of the four tables,
        the schema has drifted from the migration."""
        sql = _schema_sql()
        for table in PROVENANCE_COLUMN:
            pattern = rf'"Allow all for anon"\s+(?:on|ON)\s+{table}\b'
            assert not re.search(pattern, sql), (
                f"Legacy 'Allow all for anon' policy still present on {table} "
                f"in schema.sql — drift from migration."
            )


# -- Policy logic -----------------------------------------------------------


def _anon_insert_allowed(table: str, row: dict) -> bool:
    """Pure-Python reimplementation of the anon INSERT WITH CHECK predicate.

    Mirrors the migration's per-table policy. Keep in sync with
    `20260508120000_sandcastle_anon_rls_provenance_gate.sql`. The shape tests
    above lock down the SQL; this function locks down the decision logic.
    """
    column = PROVENANCE_COLUMN[table]
    value = row.get(column)
    if value is None:
        return False
    return value.startswith("sandcastle:")


class TestPolicyLogic:
    @pytest.mark.parametrize("table", list(PROVENANCE_COLUMN.keys()))
    def test_sandcastle_prefix_accepted(self, table: str):
        col = PROVENANCE_COLUMN[table]
        assert _anon_insert_allowed(table, {col: "sandcastle:agent"})
        assert _anon_insert_allowed(table, {col: "sandcastle:agent:run-42"})

    @pytest.mark.parametrize("table", list(PROVENANCE_COLUMN.keys()))
    def test_other_prefix_rejected(self, table: str):
        col = PROVENANCE_COLUMN[table]
        for bad in [
            "session:abc",
            "skill:implement",
            "user:explicit",
            "Sandcastle:agent",  # case-sensitive — LIKE in PG is case-sensitive
            "sandcastles:agent",  # close but no colon
            "",
            "sandcastle",  # no colon
        ]:
            assert not _anon_insert_allowed(table, {col: bad}), (
                f"{table}: value {bad!r} should have been rejected"
            )

    @pytest.mark.parametrize("table", list(PROVENANCE_COLUMN.keys()))
    def test_null_provenance_rejected(self, table: str):
        col = PROVENANCE_COLUMN[table]
        assert not _anon_insert_allowed(table, {col: None})
        assert not _anon_insert_allowed(table, {})  # missing key

    def test_service_role_bypasses_rls(self):
        """Service-role bypasses RLS at the Postgres level — modeled here as
        a documentation assertion rather than a code path. The migration does
        not touch service-role behavior; the test exists to flag any future
        change that would (e.g. adding TO service_role to the new policies)."""
        sql = _migration_sql()
        # No new policy should mention service_role explicitly — service-role
        # bypasses RLS and should not need a policy.
        assert "service_role" not in sql.lower(), (
            "Migration should not reference service_role — it bypasses RLS. "
            "If you intentionally added a service_role policy, update this test."
        )
