"""Guard: events.dedup_key uniqueness must be a FULL constraint, not partial (#1491).

supabase-py upsert generates a bare ``ON CONFLICT (dedup_key)``, which Postgres
cannot infer from a partial unique index (``WHERE dedup_key IS NOT NULL``) —
every #953 terminal-transition emission died with 42P10 while the original
partial index was live, and the swallow-by-design emit path hid it. Prod was
fixed by migration ``events_dedup_key_full_unique_constraint``; this guard pins
the canon so it cannot drift back to a shape PostgREST cannot use.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
SCHEMA = (REPO_ROOT / "mcp-memory" / "schema.sql").read_text(encoding="utf-8")
CI_BOOTSTRAP = (REPO_ROOT / "tests" / "ci" / "global_task_schema_bootstrap.sql").read_text(
    encoding="utf-8"
)

PARTIAL_INDEX_PATTERN = re.compile(
    r"create\s+unique\s+index[^;]*\bevents\s*\(\s*dedup_key\s*\)[^;]*\bwhere\b",
    flags=re.IGNORECASE,
)


def _events_table_block() -> str:
    """The `create table ... events` block, up to its closing `);`."""
    match = re.search(
        r"create table if not exists events\s*\(.*?^\);",
        SCHEMA,
        flags=re.DOTALL | re.MULTILINE | re.IGNORECASE,
    )
    assert match, "events table definition not found in schema.sql"
    return match.group(0)


def test_no_partial_unique_index_on_dedup_key() -> None:
    """A partial index on events(dedup_key) is the #1491 bug shape — banned."""
    assert not PARTIAL_INDEX_PATTERN.search(SCHEMA), (
        "schema.sql declares a PARTIAL unique index on events(dedup_key); "
        "PostgREST's bare ON CONFLICT (dedup_key) cannot infer it (42P10, #1491) "
        "— use a full UNIQUE constraint on the column instead"
    )


def test_ci_bootstrap_matches_prod_shape() -> None:
    """The CI bootstrap DB must carry the same full constraint as prod —
    otherwise integration tests upserting on dedup_key hit 42P10 only in CI."""
    assert not PARTIAL_INDEX_PATTERN.search(CI_BOOTSTRAP), (
        "tests/ci/global_task_schema_bootstrap.sql still creates the partial "
        "unique index on events(dedup_key) — converge to the full UNIQUE "
        "constraint (#1491) so CI matches prod"
    )
    assert re.search(
        r"^\s*dedup_key\s+text\s+unique\b", CI_BOOTSTRAP, flags=re.IGNORECASE | re.MULTILINE
    ), "CI bootstrap events.dedup_key must be declared UNIQUE inline (#1491)"


def test_dedup_key_column_declares_full_unique() -> None:
    """The column itself carries `unique` → constraint events_dedup_key_key,
    matching the live migration events_dedup_key_full_unique_constraint."""
    block = _events_table_block()
    column_line = next(
        (line for line in block.splitlines() if re.match(r"\s*dedup_key\s+text\b", line)),
        None,
    )
    assert column_line is not None, "dedup_key column not found in events table"
    code = column_line.split("--", 1)[0]  # the old comment said "unique when set"
    assert re.search(r"\bunique\b", code, flags=re.IGNORECASE), (
        "events.dedup_key must be declared UNIQUE inline so a fresh DB gets the "
        "same full constraint (events_dedup_key_key) that prod carries (#1491)"
    )


def test_repo_migration_mirrors_live_fix() -> None:
    """The applied prod migration has a matching file in supabase/migrations/."""
    migrations = REPO_ROOT / "supabase" / "migrations"
    hits = list(migrations.glob("*events_dedup_key_full_unique_constraint.sql"))
    assert hits, (
        "supabase/migrations/ must mirror the live migration "
        "events_dedup_key_full_unique_constraint (#1491)"
    )
    body = hits[0].read_text(encoding="utf-8").lower()
    assert "unique (dedup_key)" in body
    assert "drop index if exists idx_events_dedup_key" in body
