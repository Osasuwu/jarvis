"""Issue #1645 — write-amplification fixes on the memories recall-touch path.

Every assertion here is source-text over SQL artifacts rather than a live
query: the DDL is the deliverable, and `schema_sql_requires_paired_migration`
means a change is only real when it exists in BOTH `mcp-memory/schema.sql`
(aspirational documentation) and a `supabase/migrations/*` file (what actually
executes). Asserting on one alone reproduces the #284 failure mode, where a
schema.sql-only edit left prod silently diverged.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCHEMA = REPO / "mcp-memory" / "schema.sql"
MIGRATIONS = REPO / "supabase" / "migrations"


def _schema_text() -> str:
    return SCHEMA.read_text(encoding="utf-8")


def _migration_texts() -> dict[str, str]:
    return {p.name: p.read_text(encoding="utf-8") for p in sorted(MIGRATIONS.glob("*.sql"))}


def _touch_memories_body(sql: str) -> str:
    """Extract the body of the last `create ... function touch_memories` in `sql`."""
    matches = list(
        re.finditer(
            r"create\s+(or\s+replace\s+)?function\s+touch_memories\b.*?\$\$?(.*?)\$\$?\s*;",
            sql,
            re.IGNORECASE | re.DOTALL,
        )
    )
    assert matches, "no touch_memories function definition found"
    return matches[-1].group(2)


# --- AC1: touch_memories no longer UPDATEs on every recall -------------------


def test_ac1_schema_touch_memories_debounces_on_last_accessed_at():
    body = _touch_memories_body(_schema_text())
    assert "last_accessed_at" in body and "interval" in body.lower(), (
        "touch_memories in schema.sql still bumps last_accessed_at unconditionally — "
        "expected a debounce predicate skipping rows touched within the last hour"
    )


def test_ac1_paired_migration_redefines_touch_memories_with_debounce():
    hits = [
        name
        for name, text in _migration_texts().items()
        if re.search(r"function\s+touch_memories\b", text, re.IGNORECASE)
        and "interval" in _touch_memories_body(text).lower()
    ]
    assert hits, (
        "no migration redefines touch_memories with a debounce — schema.sql alone "
        "does not execute against the live DB (see #284)"
    )


# --- AC3: drop the two low-scan trigram indexes, keep the load-bearing one ----


def test_ac3_migration_drops_low_scan_trigram_indexes():
    joined = "\n".join(_migration_texts().values()).lower()
    for idx in ("idx_memories_content_trgm", "idx_memories_description_trgm"):
        assert re.search(rf"drop\s+index\s+(concurrently\s+)?(if\s+exists\s+)?{idx}\b", joined), (
            f"{idx} is never dropped by a migration"
        )


def test_ac3_name_trgm_index_is_never_dropped():
    """idx_memories_name_trgm has 3161 lifetime scans — the issue text does not
    mention it, and dropping it alongside its two idle siblings would kill the
    only trigram index the planner actually chooses."""
    joined = "\n".join(_migration_texts().values()).lower()
    assert not re.search(r"drop\s+index\s+.*idx_memories_name_trgm\b", joined), (
        "idx_memories_name_trgm must be preserved — it is heavily used"
    )


def test_ac3_kept_trigram_index_is_documented_in_schema():
    """It exists in prod but was never in schema.sql — closing that drift is
    the other half of AC3, otherwise a fresh instance silently loses it."""
    assert "idx_memories_name_trgm" in _schema_text(), (
        "idx_memories_name_trgm exists in prod but not in schema.sql (drift)"
    )


# --- AC5: live cron state must be encoded in migration history ---------------


def test_ac5_migration_encodes_current_cron_state():
    texts = _migration_texts()
    cadence = [
        n for n, t in texts.items() if "*/30 * * * *" in t and "events_last_run_by_actor_mv" in t
    ]
    purge = [n for n, t in texts.items() if "cron_job_run_details_purge" in t]
    assert cadence, "no migration encodes the */30 refresh cadence for events_last_run_by_actor_mv"
    assert purge, "no migration encodes the cron_job_run_details_purge retention job"


# --- AC4: archive_timeout finding + RPO trade-off recorded -------------------


def test_ac4_archive_timeout_tradeoff_documented():
    doc = (REPO / "docs" / "reference" / "memory-subsystem.md").read_text(encoding="utf-8")
    assert "archive_timeout" in doc, "archive_timeout finding not recorded"
    assert "RPO" in doc, "RPO consequence of raising archive_timeout not stated"
