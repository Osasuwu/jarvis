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

# #1498: a WHERE-qualified ON CONFLICT target only matches a *partial* index —
# never the FULL constraint dedup_key now carries (#1491) — so any RPC still
# restating `where dedup_key is not null` here 42P10s on every call.
STALE_ONCONFLICT_WHERE_PATTERN = re.compile(
    r"on\s+conflict\s*\(\s*dedup_key\s*\)\s+where\s+dedup_key\s+is\s+not\s+null",
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


def test_schema_sql_scrubber_rpcs_have_no_stale_onconflict_where() -> None:
    """scrubber_block_event_upsert / scrubber_disabled_event_upsert must use a
    plain `on conflict (dedup_key)` matching the FULL constraint (#1491) —
    not the WHERE-qualified target that only matches a partial index and
    42P10s against a full one (#1498)."""
    assert not STALE_ONCONFLICT_WHERE_PATTERN.search(SCHEMA), (
        "mcp-memory/schema.sql still declares a WHERE-qualified "
        "`on conflict (dedup_key) where dedup_key is not null` — this cannot "
        "match events.dedup_key's FULL unique constraint (events_dedup_key_key, "
        "#1491) and 42P10s on every call (#1498)"
    )


def test_repo_migrations_effective_scrubber_rpcs_have_no_stale_onconflict_where() -> None:
    """The LATEST migration defining each scrubber RPC (by filename order,
    matching Supabase's chronological apply order) must not retain the stale
    WHERE-qualified conflict target. Earlier migrations are allowed to keep
    it — they're superseded history, not live schema."""
    migrations_dir = REPO_ROOT / "supabase" / "migrations"
    for rpc_name in ("scrubber_block_event_upsert", "scrubber_disabled_event_upsert"):
        defining = sorted(
            p
            for p in migrations_dir.glob("*.sql")
            if re.search(
                rf"create\s+or\s+replace\s+function\s+{rpc_name}\b",
                p.read_text(encoding="utf-8"),
                flags=re.IGNORECASE,
            )
        )
        assert defining, f"no migration defines {rpc_name}"
        latest = defining[-1]
        body = latest.read_text(encoding="utf-8")
        assert not STALE_ONCONFLICT_WHERE_PATTERN.search(body), (
            f"{latest.name} is the latest migration defining {rpc_name} but "
            "still restates the WHERE-qualified conflict target — it 42P10s "
            "against the FULL dedup_key constraint (#1491, #1498)"
        )
