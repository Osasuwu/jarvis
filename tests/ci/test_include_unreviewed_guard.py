"""CI guard test for include_unreviewed recall flag (issue #685, Slice 5).

Validates the migration file and schema.sql are in sync: each of the 4
recall-path RPCs must accept an `include_unreviewed boolean default false`
parameter and apply the conditional filter.
"""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_DIR = REPO_ROOT / "supabase" / "migrations"
SCHEMA_PATH = REPO_ROOT / "mcp-memory" / "schema.sql"

# The canonical migration filename for this slice.
EXPECTED_MIGRATION = "20260520000001_add_include_unreviewed_recall_flag.sql"

# RPCs that must accept include_unreviewed.
RECALL_RPCS = [
    "match_memories_v2",
    "match_memories",
    "keyword_search_memories",
    "get_linked_memories",
]


class TestMigrationFile:
    """The migration file exists and has the expected RPC signatures."""

    def test_migration_file_exists(self):
        migration = MIGRATION_DIR / EXPECTED_MIGRATION
        assert migration.exists(), (
            f"Expected migration {EXPECTED_MIGRATION} not found in {MIGRATION_DIR}"
        )

    def test_migration_has_include_unreviewed_on_match_memories_v2(self):
        text = (MIGRATION_DIR / EXPECTED_MIGRATION).read_text(encoding="utf-8")
        assert "include_unreviewed boolean default false" in text
        assert "create or replace function match_memories_v2" in text

    def test_migration_has_include_unreviewed_on_match_memories(self):
        text = (MIGRATION_DIR / EXPECTED_MIGRATION).read_text(encoding="utf-8")
        assert "include_unreviewed boolean default false" in text
        assert "create or replace function match_memories(" in text

    def test_migration_has_include_unreviewed_on_keyword_search(self):
        text = (MIGRATION_DIR / EXPECTED_MIGRATION).read_text(encoding="utf-8")
        assert "include_unreviewed boolean default false" in text
        assert "create or replace function keyword_search_memories" in text

    def test_migration_has_include_unreviewed_on_get_linked(self):
        text = (MIGRATION_DIR / EXPECTED_MIGRATION).read_text(encoding="utf-8")
        assert "include_unreviewed boolean default false" in text
        assert "create or replace function get_linked_memories" in text

    def test_migration_merge_targets_always_filtered(self):
        """merge_targets IS NULL check must remain — never include proposals."""
        text = (MIGRATION_DIR / EXPECTED_MIGRATION).read_text(encoding="utf-8")
        count = text.count("merge_targets is null or array_length")
        # Appears in every subquery: match_memories_v2 (1), match_memories (1),
        # keyword_search_memories (1), get_linked_memories (2 = each union branch).
        assert count >= 5, (
            f"Expected >=5 merge_targets filter occurrences, found {count}. "
            "The filter must remain unconditional."
        )


class TestSchemaFileInSync:
    """schema.sql must reflect the same RPC signatures as the migration."""

    def test_schema_has_include_unreviewed_default(self):
        text = SCHEMA_PATH.read_text(encoding="utf-8")
        assert "include_unreviewed boolean default false" in text, (
            "schema.sql must declare `include_unreviewed boolean default false` "
            "on recall-path RPCs."
        )

    def test_schema_conditions_on_flag(self):
        """The requires_review filter must be gated by include_unreviewed."""
        text = SCHEMA_PATH.read_text(encoding="utf-8")
        count = text.count("include_unreviewed or m.requires_review = false")
        # match_memories_v2 (1), match_memories (1), keyword_search (1),
        # get_linked_memories (2 = each union branch)
        assert count >= 5, (
            f"Expected >=5 conditional filter occurrences, found {count}. "
            "The `include_unreviewed or` guard must wrap every requires_review "
            "filter."
        )

    def test_merge_targets_still_absolute(self):
        """merge_targets filter must NOT be gated by include_unreviewed."""
        text = SCHEMA_PATH.read_text(encoding="utf-8")
        gated = text.count("include_unreviewed or m.merge_targets")
        assert gated == 0, (
            f"Found {gated} instances where merge_targets filter is gated by "
            "include_unreviewed. merge_targets must ALWAYS be filtered."
        )
