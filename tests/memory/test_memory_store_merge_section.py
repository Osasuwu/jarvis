"""Tests for memory_store mode="merge_section" (#1352).

Verifies server-side section merge replaces matching markdown headers,
appends when section absent, preserves siblings, and fails loudly on
unparseable content.

conftest.py stubs MCP SDK + Supabase before any imports, so this file
can import from server and handlers.memory without external dependencies.
"""

from unittest.mock import MagicMock

import pytest
import server  # noqa: F401 (needed to break circular import with handlers.memory)
import handlers.memory as mem


class TestParseMarkdownSections:
    """Test _parse_markdown_sections helper."""

    def test_parse_single_section(self):
        """Parse a single section with valid header."""
        content = """# Working state

### [entry] foo-bar — 2026-01-01 — in-progress

Some content here.
More content.
"""
        sections = mem._parse_markdown_sections(content)
        assert "### [entry] foo-bar — 2026-01-01 — in-progress" in sections
        start, end = sections["### [entry] foo-bar — 2026-01-01 — in-progress"]
        lines = content.split("\n")
        assert lines[start].startswith("### [entry]")
        assert end <= len(lines)

    def test_parse_multiple_sections(self):
        """Parse multiple sections correctly."""
        content = """# Working state

### [entry] task-1 — 2026-01-01 — done

Done.

### [entry] task-2 — 2026-01-02 — in-progress

In progress.

### [evicted] task-3 — 2026-01-03 — GC: age >14 days
"""
        sections = mem._parse_markdown_sections(content)
        assert len(sections) == 3
        assert "### [entry] task-1 — 2026-01-01 — done" in sections
        assert "### [entry] task-2 — 2026-01-02 — in-progress" in sections
        assert "### [evicted] task-3 — 2026-01-03 — GC: age >14 days" in sections

    def test_parse_ignores_non_entry_headers(self):
        """Non-entry headers are ignored; only [entry] and [evicted] count."""
        content = """# Main Title

## Other section

Some text

### [entry] my-task — 2026-01-01 — done

Task content.

## Another thing

### Not an entry header

This should be ignored.
"""
        sections = mem._parse_markdown_sections(content)
        # Only the [entry] block should be parsed
        assert len(sections) == 1
        assert "### [entry] my-task — 2026-01-01 — done" in sections

    def test_parse_empty_document(self):
        """Parsing empty document returns empty dict."""
        sections = mem._parse_markdown_sections("")
        assert sections == {}


class TestMergeSectionIntoMarkdown:
    """Test _merge_section_into_markdown helper."""

    def test_replace_existing_section(self):
        """Replace an existing section header."""
        existing = """# Working state

### [entry] task-1 — 2026-01-01 — done

Old content here.

### [entry] task-2 — 2026-01-02 — in-progress

Different task.
"""
        new_section = """### [entry] task-1 — 2026-01-01 — done

New content for task 1."""

        result = mem._merge_section_into_markdown(
            existing, "### [entry] task-1 — 2026-01-01 — done", new_section
        )

        # Check that task-1 was replaced
        assert "New content for task 1" in result
        assert "Old content here" not in result
        # Check that task-2 is preserved
        assert "### [entry] task-2 — 2026-01-02 — in-progress" in result
        assert "Different task" in result

    def test_append_new_section(self):
        """Append a new section when header doesn't exist."""
        existing = """# Working state

### [entry] task-1 — 2026-01-01 — done

Task 1 content.
"""
        new_section = """### [entry] task-2 — 2026-01-02 — in-progress

Task 2 content."""

        result = mem._merge_section_into_markdown(
            existing, "### [entry] task-2 — 2026-01-02 — in-progress", new_section
        )

        # Both tasks should be present
        assert "### [entry] task-1 — 2026-01-01 — done" in result
        assert "### [entry] task-2 — 2026-01-02 — in-progress" in result
        assert "Task 1 content" in result
        assert "Task 2 content" in result

    def test_merge_preserves_all_siblings(self):
        """Verify all sibling sections are preserved when merging."""
        existing = """# Working state

### [entry] alpha — 2026-01-01 — done

Alpha content.

### [entry] beta — 2026-01-02 — done

Beta content.

### [evicted] gamma — 2026-01-03 — GC

Gamma marker.

### [entry] delta — 2026-01-04 — in-progress

Delta content.
"""
        # Replace beta with new content
        new_section = """### [entry] beta — 2026-01-02 — done

Beta updated."""

        result = mem._merge_section_into_markdown(
            existing, "### [entry] beta — 2026-01-02 — done", new_section
        )

        # All other sections intact
        assert "### [entry] alpha — 2026-01-01 — done" in result
        assert "Alpha content" in result
        assert "### [evicted] gamma — 2026-01-03 — GC" in result
        assert "Gamma marker" in result
        assert "### [entry] delta — 2026-01-04 — in-progress" in result
        assert "Delta content" in result
        # Beta updated
        assert "Beta updated" in result
        assert "Beta content" not in result

    def test_merge_empty_existing_returns_new_section(self):
        """Merging into empty document returns just the new section."""
        new_section = """### [entry] task-1 — 2026-01-01 — done

First task."""

        result = mem._merge_section_into_markdown(
            "", "### [entry] task-1 — 2026-01-01 — done", new_section
        )
        assert result == new_section

    def test_merge_validates_section_header_match(self):
        """Raises ValueError if section_content doesn't start with section_header."""
        existing = "Some content"
        new_section = "Mismatched content"

        with pytest.raises(ValueError):
            mem._merge_section_into_markdown(existing, "### [entry] foo", new_section)

    def test_merge_raises_when_existing_content_unparseable(self):
        """Fails loudly (per the tools_schema.py contract) when existing content
        has zero recognized '## [marker] ...' headers — a foreign-format doc,
        not a legitimate empty section list. Silently appending under it would
        guess at structure the merge can't verify.
        """
        existing = """# Main
## Subsection

This has no bracketed-marker headers at all.
"""
        new_section = """### [entry] task — 2026-01-01 — done

Content."""

        with pytest.raises(ValueError, match="not parseable as markdown sections"):
            mem._merge_section_into_markdown(
                existing, "### [entry] task — 2026-01-01 — done", new_section
            )

    def test_merge_appends_new_marker_section_alongside_existing_ones(self):
        """A doc that DOES use the '[marker]' convention, just not for the
        target header yet, is a legitimate append — not unparseable.
        """
        existing = """# Working state

### [entry] other-task — 2026-01-01 — done

Other content.
"""
        new_section = """### [entry] task — 2026-01-02 — done

Content."""

        result = mem._merge_section_into_markdown(
            existing, "### [entry] task — 2026-01-02 — done", new_section
        )
        assert new_section in result
        assert "### [entry] other-task — 2026-01-01 — done" in result

    def test_merge_generic_bracket_marker_not_hardcoded_to_entry_evicted(self):
        """The [marker] convention is generic (tools_schema.py: 'e.g. [entry]'),
        not hardcoded to literally 'entry'/'evicted' — a caller-defined marker
        must parse and merge too.
        """
        existing = """# Doc

### [custom] alpha — note

Alpha body.
"""
        new_section = """### [custom] beta — note

Beta body."""

        result = mem._merge_section_into_markdown(existing, "### [custom] beta — note", new_section)
        assert "### [custom] alpha — note" in result
        assert "Beta body" in result


class TestMergeSectionRetryLogic:
    """Test that merge_section retry uses original new section, not previous merged result.

    This tests the critical bug fix for #1352 finding #1: when an RPC conflict
    is detected and Python retries, it must re-merge using the *original new
    section* passed by the caller, not the previous merged result.

    The test uses direct helper function calls to verify the merge logic, ensuring
    that if we were to (incorrectly) pass a previous merged result as the new
    section, we'd get duplication or errors.
    """

    def test_merge_retry_detects_bug_with_previous_merged_result(self):
        """Verify that using previous merged result as new section causes ValueError.

        This test documents the bug that existed before the fix: if code incorrectly
        passed the previous merged result as the new section on retry, it would fail.

        The fix ensures we always use the original new section (stored separately)
        for each merge attempt, including retries.
        """
        # Original existing content
        existing_v1 = "## [entry] task-1 — 2026-01-01\n\nTask 1 content\n"

        # New section to merge (this never changes across retries)
        new_section = "## [entry] task-2 — 2026-01-01\n\nTask 2 content\n"

        # First merge: existing_v1 + new_section
        first_merged = mem._merge_section_into_markdown(
            existing_v1, "## [entry] task-2 — 2026-01-01", new_section
        )
        assert "## [entry] task-1" in first_merged
        assert "## [entry] task-2" in first_merged

        # Simulate concurrent update: existing content now has a new task
        existing_v2 = "## [entry] task-1 — 2026-01-01\n\nTask 1 content\n\n## [entry] task-3 — 2026-01-01\n\nTask 3 content\n"

        # CORRECT behavior on retry: merge new_section into existing_v2
        correct_retry_merge = mem._merge_section_into_markdown(
            existing_v2, "## [entry] task-2 — 2026-01-01", new_section
        )
        assert "## [entry] task-1" in correct_retry_merge
        assert "## [entry] task-2" in correct_retry_merge
        assert "## [entry] task-3" in correct_retry_merge
        # Verify no duplicates
        assert correct_retry_merge.count("## [entry] task-1") == 1
        assert correct_retry_merge.count("## [entry] task-2") == 1
        assert correct_retry_merge.count("## [entry] task-3") == 1

        # BUG: if code passed first_merged (previous result) as new section on retry:
        # The section validation fails because first_merged doesn't start with task-2's header
        with pytest.raises(ValueError, match="section_content must start with section_header"):
            mem._merge_section_into_markdown(
                existing_v2, "## [entry] task-2 — 2026-01-01", first_merged
            )


class TestFetchAndRemergeSectionSoftDeleteRevival:
    """#1714: a soft-deleted row at (project, name) must be treated as an
    empty base — revive-fresh semantics (decision
    84c5b737-1887-4c78-9d8b-e58dedac2b04), not revive+preserve. Before the
    fix, the SELECT filtered `deleted_at is null`, so a soft-deleted row was
    invisible here and `existing_content` defaulted to "" only because no row
    was found at all — the RPC then hit its own `deleted_at is null` filter
    and fell into the INSERT branch, colliding with the still-present
    unique(project, name) constraint (Postgres 23505). This test pins the
    fix at the Python layer: a soft-deleted row IS found (so its
    updated_at threads through as the OCC value for the RPC's revival
    UPDATE), but its content/description/tags are discarded as if the row
    were empty.
    """

    def _mock_client_with_row(self, row: dict) -> MagicMock:
        client = MagicMock()
        found = client.table.return_value.select.return_value.eq.return_value
        found.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[row])
        found.is_.return_value.limit.return_value.execute.return_value = MagicMock(data=[row])
        return client

    def test_soft_deleted_row_is_treated_as_empty_base(self):
        client = self._mock_client_with_row(
            {
                "content": "### [entry] old — 2026-01-01 — done\n\nOld content.",
                "updated_at": "2026-01-01T00:00:00Z",
                "description": "old description",
                "tags": ["old-tag"],
                "deleted_at": "2026-01-02T00:00:00Z",
            }
        )
        new_section = "### [entry] new — 2026-01-03 — in-progress\n\nNew content."

        result = mem._fetch_and_remerge_section(
            client,
            mem_name="working_state_test",
            project="test-proj",
            section_header="### [entry] new — 2026-01-03 — in-progress",
            new_section_content=new_section,
            description="",
            tags=[],
        )

        # Old content must NOT survive into the merge — empty base, not
        # revive+preserve.
        assert "Old content" not in result["merged_content"]
        assert result["merged_content"] == new_section
        # updated_at still threads through so the RPC's OCC check compares
        # against the tombstone row's real value (needed to find/lock it).
        assert result["expected_updated_at"] == "2026-01-01T00:00:00Z"
        # Revive-fresh: never preserve a tombstoned row's description/tags,
        # even though the caller passed the merge_section defaults ("", [])
        # that would normally signal "preserve existing".
        assert result["preserve_description"] is False
        assert result["preserve_tags"] is False

    def test_live_row_still_preserves_content_and_metadata(self):
        """Regression guard: the fix must not touch the live-row path — a
        non-deleted row's content/description/tags are still read and
        preserve_description/preserve_tags still compute True when the
        caller passed the "preserve" sentinel values.
        """
        client = self._mock_client_with_row(
            {
                "content": "### [entry] old — 2026-01-01 — done\n\nOld content.",
                "updated_at": "2026-01-01T00:00:00Z",
                "description": "kept description",
                "tags": ["kept-tag"],
                "deleted_at": None,
            }
        )
        new_section = "### [entry] new — 2026-01-03 — in-progress\n\nNew content."

        result = mem._fetch_and_remerge_section(
            client,
            mem_name="working_state_test",
            project="test-proj",
            section_header="### [entry] new — 2026-01-03 — in-progress",
            new_section_content=new_section,
            description="",
            tags=[],
        )

        assert "Old content" in result["merged_content"]
        assert "New content" in result["merged_content"]
        assert result["expected_updated_at"] == "2026-01-01T00:00:00Z"
        assert result["preserve_description"] is True
        assert result["preserve_tags"] is True
