"""CI guard test for include_unreviewed recall flag (issue #685, Slice 5).

Validates the migration file and schema.sql are in sync: each of the 4
recall-path RPCs must accept an `include_unreviewed boolean default false`
parameter and apply the conditional filter.
"""

from __future__ import annotations

import re
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


def _extract_param_list(text: str, func_name: str) -> str | None:
    """Return the parameter list of the **last** definition of *func_name* in SQL text.

    Finds ``CREATE OR REPLACE FUNCTION <func_name>(`` (case-insensitive) and
    returns the substring between the opening ``(`` and its matching ``)``.
    The last match is used because schema.sql is cumulative — each migration
    appends a new ``CREATE OR REPLACE FUNCTION`` that supersedes earlier ones,
    so only the last definition is authoritative (mirrors Postgres semantics).
    Returns None if the function is not found.
    """
    pattern = re.compile(
        r"create\s+or\s+replace\s+function\s+" + re.escape(func_name) + r"\s*\(",
        re.IGNORECASE,
    )
    matches = list(pattern.finditer(text))
    if not matches:
        return None
    m = matches[-1]
    start = m.end()
    depth, pos = 1, start
    while pos < len(text) and depth > 0:
        if text[pos] == "(":
            depth += 1
        elif text[pos] == ")":
            depth -= 1
        pos += 1
    return text[start : pos - 1]


class TestMigrationFile:
    """The migration file exists and has the expected RPC signatures."""

    def test_migration_file_exists(self):
        migration = MIGRATION_DIR / EXPECTED_MIGRATION
        assert migration.exists(), (
            f"Expected migration {EXPECTED_MIGRATION} not found in {MIGRATION_DIR}"
        )

    def test_migration_has_include_unreviewed_on_match_memories_v2(self):
        text = (MIGRATION_DIR / EXPECTED_MIGRATION).read_text(encoding="utf-8")
        params = _extract_param_list(text, "match_memories_v2")
        assert params is not None, "match_memories_v2 not found in migration"
        assert "include_unreviewed boolean default false" in params.lower(), (
            "match_memories_v2 parameter list missing include_unreviewed"
        )

    def test_migration_has_include_unreviewed_on_match_memories(self):
        text = (MIGRATION_DIR / EXPECTED_MIGRATION).read_text(encoding="utf-8")
        params = _extract_param_list(text, "match_memories")
        assert params is not None, "match_memories not found in migration"
        assert "include_unreviewed boolean default false" in params.lower(), (
            "match_memories parameter list missing include_unreviewed"
        )

    def test_migration_has_include_unreviewed_on_keyword_search(self):
        text = (MIGRATION_DIR / EXPECTED_MIGRATION).read_text(encoding="utf-8")
        params = _extract_param_list(text, "keyword_search_memories")
        assert params is not None, "keyword_search_memories not found in migration"
        assert "include_unreviewed boolean default false" in params.lower(), (
            "keyword_search_memories parameter list missing include_unreviewed"
        )

    def test_migration_has_include_unreviewed_on_get_linked(self):
        text = (MIGRATION_DIR / EXPECTED_MIGRATION).read_text(encoding="utf-8")
        params = _extract_param_list(text, "get_linked_memories")
        assert params is not None, "get_linked_memories not found in migration"
        assert "include_unreviewed boolean default false" in params.lower(), (
            "get_linked_memories parameter list missing include_unreviewed"
        )

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
        for rpc in RECALL_RPCS:
            params = _extract_param_list(text, rpc)
            assert params is not None, f"schema.sql: {rpc} function not found"
            assert "include_unreviewed boolean default false" in params.lower(), (
                f"schema.sql: {rpc} parameter list missing include_unreviewed"
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
