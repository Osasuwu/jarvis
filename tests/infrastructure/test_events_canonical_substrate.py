"""Contract tests for the C17 events_canonical substrate (#476, Sprint #35).

Verifies the migration file and the schema.sql mirror declare the same
shape that the design 1-pager (docs/design/c17-events-substrate.md) and
the first writer (#477) depend on. Does NOT hit a live database — live
verification was performed via the Supabase MCP `apply_migration` tool
during the implementing session and is reproducible by anyone with the
project ID.

When a future change moves a column or renames an index, these assertions
break loudly so the cascading damage to writers / consumers is caught at
PR time, not in production.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION = REPO_ROOT / "supabase" / "migrations" / "20260429145000_create_events_canonical.sql"
SCHEMA_MIRROR = REPO_ROOT / "supabase" / "schema.sql"

REQUIRED_COLUMNS = (
    "event_id",
    "trace_id",
    "parent_event_id",
    "ts",
    "actor",
    "action",
    "payload",
    "outcome",
    "cost_tokens",
    "cost_usd",
    "redacted",
    "degraded",
)

REQUIRED_INDEXES = (
    "idx_events_canonical_trace_ts",
    "idx_events_canonical_actor_ts",
    "idx_events_canonical_action_ts",
    "idx_events_canonical_cost",
)

REQUIRED_MATVIEWS = (
    "events_cost_by_day_mv",
    "events_last_run_by_actor_mv",
)

OTEL_KEYS_IN_VIEW = ("gen_ai.request.model",)


@pytest.fixture(scope="module")
def migration_sql() -> str:
    assert MIGRATION.exists(), f"missing migration file: {MIGRATION}"
    return MIGRATION.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def schema_sql() -> str:
    assert SCHEMA_MIRROR.exists(), f"missing schema mirror: {SCHEMA_MIRROR}"
    return SCHEMA_MIRROR.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Table shape
# ---------------------------------------------------------------------------


def _undeclared_columns(sql: str) -> list[str]:
    return [
        column
        for column in REQUIRED_COLUMNS
        if not re.search(rf"^\s*{column}\s+", sql, re.MULTILINE)
    ]


def test_migration_declares_columns(migration_sql: str) -> None:
    missing = _undeclared_columns(migration_sql)
    assert not missing, f"column(s) {missing} missing from CREATE TABLE events_canonical"


def test_schema_mirror_declares_columns(schema_sql: str) -> None:
    missing = _undeclared_columns(_extract_events_canonical_block(schema_sql))
    assert not missing, f"column(s) {missing} missing from schema.sql events_canonical block"


def test_event_outcome_enum_present(migration_sql: str, schema_sql: str) -> None:
    """outcome column references an event_outcome enum with the four values."""
    for source, label in ((migration_sql, "migration"), (schema_sql, "schema")):
        assert "CREATE TYPE event_outcome AS ENUM" in source, (
            f"event_outcome enum missing from {label}"
        )
        for value in ("success", "failure", "timeout", "partial"):
            assert f"'{value}'" in source, f"enum value {value!r} missing from {label}"


def test_trace_id_is_not_null(migration_sql: str) -> None:
    """trace_id must be NOT NULL — orphaned events break trace replay."""
    line = _line_for_column(migration_sql, "trace_id")
    assert "NOT NULL" in line, f"trace_id must be NOT NULL: {line!r}"


def test_degraded_defaults_false(migration_sql: str) -> None:
    """degraded MUST default to false — only buffer-replay paths set it."""
    line = _line_for_column(migration_sql, "degraded")
    assert "DEFAULT false" in line, f"degraded must DEFAULT false: {line!r}"


# ---------------------------------------------------------------------------
# Indexes
# ---------------------------------------------------------------------------


def test_migration_declares_indexes(migration_sql: str) -> None:
    missing = [index for index in REQUIRED_INDEXES if index not in migration_sql]
    assert not missing, f"index(es) {missing} missing from migration"


def test_cost_index_is_partial(migration_sql: str) -> None:
    """The cost index must be partial on cost_usd IS NOT NULL — full index
    on a nullable column would bloat with cost-free events."""
    match = re.search(
        r"CREATE INDEX[^;]*idx_events_canonical_cost[^;]*;",
        migration_sql,
        re.IGNORECASE | re.DOTALL,
    )
    assert match, "idx_events_canonical_cost not found"
    assert "WHERE cost_usd IS NOT NULL" in match.group(0), (
        "idx_events_canonical_cost must be partial on cost_usd IS NOT NULL"
    )


# ---------------------------------------------------------------------------
# pg_notify trigger
# ---------------------------------------------------------------------------


def test_pg_notify_trigger_present(migration_sql: str) -> None:
    """Trigger must fire per inserted row into the notify function, and the
    function must notify on channel 'events_canonical' so LISTEN clients can
    subscribe by name."""
    trigger = _statement(migration_sql, r"CREATE TRIGGER events_canonical_notify\b")
    assert trigger == (
        "CREATE TRIGGER events_canonical_notify AFTER INSERT ON events_canonical "
        "FOR EACH ROW EXECUTE FUNCTION notify_events_canonical()"
    )
    fn_block = _extract_function_body(migration_sql, "notify_events_canonical")
    channel = re.search(r"pg_notify\(\s*'([^']*)'", fn_block)
    assert channel, f"notify_events_canonical() makes no pg_notify call: {fn_block}"
    assert channel.group(1) == "events_canonical"


def test_notify_payload_includes_trace_id(migration_sql: str) -> None:
    """Payload must include trace_id so subscribers can route by trace."""
    fn_block = _extract_function_body(migration_sql, "notify_events_canonical")
    for key in ("event_id", "trace_id", "action", "actor"):
        assert f"'{key}'" in fn_block, f"notify payload missing key {key!r}: {fn_block}"


# ---------------------------------------------------------------------------
# Materialized views + cron schedules
# ---------------------------------------------------------------------------


def test_migration_declares_matviews(migration_sql: str) -> None:
    missing = [
        matview
        for matview in REQUIRED_MATVIEWS
        if f"CREATE MATERIALIZED VIEW IF NOT EXISTS {matview}" not in migration_sql
    ]
    assert not missing, f"matview(s) {missing} missing"


def test_matviews_have_unique_index_for_concurrent_refresh(migration_sql: str) -> None:
    """REFRESH MATERIALIZED VIEW CONCURRENTLY requires a unique index."""
    missing = [
        matview
        for matview in REQUIRED_MATVIEWS
        if not re.search(rf"CREATE UNIQUE INDEX[^;]*ON {matview}", migration_sql, re.IGNORECASE)
    ]
    assert not missing, f"matview(s) {missing} need a unique index for CONCURRENTLY refresh"


def test_cost_view_uses_otel_model_key(migration_sql: str) -> None:
    """Cost rollup must read OTel-shaped model key, not a bespoke alias."""
    cost_view = _extract_matview_body(migration_sql, "events_cost_by_day_mv")
    for key in OTEL_KEYS_IN_VIEW:
        assert f"'{key}'" in cost_view, f"cost view must read OTel key {key!r}: {cost_view}"


def test_cost_view_excludes_degraded(migration_sql: str) -> None:
    """Replayed (degraded=true) events must not contribute to cost truth."""
    cost_view = _extract_matview_body(migration_sql, "events_cost_by_day_mv")
    assert "degraded = false" in cost_view, "cost view must filter out degraded=true rows"


def test_pg_cron_schedules_present(migration_sql: str) -> None:
    """Both materialized views need scheduled refreshes."""
    assert "events_cost_by_day_mv_refresh" in migration_sql, "cost view cron job missing"
    assert "events_last_run_by_actor_mv_refresh" in migration_sql, "last_run view cron job missing"


def test_pg_cron_extension_enabled(migration_sql: str) -> None:
    """Migration must enable pg_cron — Supabase ships it but doesn't
    install by default."""
    assert "CREATE EXTENSION IF NOT EXISTS pg_cron" in migration_sql, (
        "migration must enable pg_cron"
    )


# ---------------------------------------------------------------------------
# RLS
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("source_attr", ["migration_sql", "schema_sql"])
def test_rls_enabled_with_allow_all_policies(
    request: pytest.FixtureRequest, source_attr: str
) -> None:
    """Match existing convention (fok_judgments, task_queue, etc.).

    schema_sql carries the post-#542 split-anon shape (SELECT/UPDATE/DELETE
    open, INSERT gated on actor LIKE 'sandcastle:%'); migration_sql is the
    original create migration which still has the broad `Allow all for anon`.
    """
    source = request.getfixturevalue(source_attr)
    assert (
        _statement(source, r"ALTER TABLE events_canonical ENABLE ROW LEVEL SECURITY")
        == "ALTER TABLE events_canonical ENABLE ROW LEVEL SECURITY"
    )
    assert (
        _policy(source, "Allow all for authenticated") == "FOR ALL USING (true) WITH CHECK (true)"
    )
    if source_attr == "migration_sql":
        assert _policy(source, "Allow all for anon") == (
            "FOR ALL TO anon USING (true) WITH CHECK (true)"
        )
    else:
        # post-#542 split-anon shape in schema.sql; each policy is read from its
        # own statement, so the sandcastle gate on UPDATE/DELETE cannot stand in
        # for a missing gate on INSERT.
        assert _policy(source, "Anon select") == "FOR SELECT TO anon USING (true)"
        assert _policy(source, "Anon sandcastle insert") == (
            "FOR INSERT TO anon WITH CHECK (actor LIKE 'sandcastle:%')"
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _line_for_column(sql: str, column: str) -> str:
    for line in sql.splitlines():
        if re.match(rf"\s*{column}\s+", line):
            return line.strip()
    raise AssertionError(f"column {column!r} not found")


def _raw_statement(sql: str, head: str) -> str:
    """The one SQL statement starting at regex `head`, up to (not including)
    its `;`, line structure intact. Only for statements with no `;` inside them
    (tables, triggers, policies) — function bodies go through
    `_extract_function_body`."""
    matches = list(re.finditer(head, sql))
    assert len(matches) == 1, (
        f"expected exactly one statement matching {head!r}, got {len(matches)}"
    )
    start = matches[0].start()
    end = sql.find(";", start)
    assert end != -1, f"statement {head!r} has no closing ;"
    return sql[start:end]


def _statement(sql: str, head: str) -> str:
    """`_raw_statement` with whitespace collapsed to single spaces."""
    return " ".join(_raw_statement(sql, head).split())


def _policy(sql: str, name: str) -> str:
    """The clauses after `CREATE POLICY "<name>" ON events_canonical`."""
    prefix = f'CREATE POLICY "{name}" ON events_canonical'
    statement = _statement(sql, re.escape(prefix) + r"\s")
    return statement[len(prefix) :].strip()


def _extract_events_canonical_block(schema_sql: str) -> str:
    """The events_canonical CREATE TABLE statement alone, so column lookups
    match neither the legacy `events` table nor any later table in the file."""
    return _raw_statement(schema_sql, r"CREATE TABLE IF NOT EXISTS events_canonical\s*\(")


def _extract_function_body(sql: str, fn_name: str) -> str:
    pattern = rf"CREATE OR REPLACE FUNCTION {fn_name}\(\)\s+RETURNS trigger.*?\$\$"
    match = re.search(pattern, sql, re.DOTALL)
    assert match, f"function {fn_name!r} not found"
    start = match.end()
    end = sql.find("$$", start)
    assert end != -1, f"function {fn_name!r} body unterminated"
    return sql[start:end]


def _extract_matview_body(sql: str, matview: str) -> str:
    pattern = rf"CREATE MATERIALIZED VIEW IF NOT EXISTS {matview} AS"
    start = sql.find(pattern)
    if start == -1:
        # Fall back to a less strict prefix for the schema mirror style.
        start = sql.find(f"MATERIALIZED VIEW IF NOT EXISTS {matview}")
    assert start != -1, f"matview {matview!r} not found"
    end = sql.find("WITH NO DATA", start)
    if end == -1:
        end = sql.find(";", start)
    assert end != -1, f"matview {matview!r} body unterminated"
    return sql[start:end]
