"""Tests for memory_store mode="merge_section" (#1352).

Verifies server-side section merge replaces matching markdown headers,
appends when section absent, preserves siblings, and fails loudly on
unparseable content.

conftest.py stubs MCP SDK + Supabase before any imports, so this file
can import from server and handlers.memory without external dependencies.
"""

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

        result = mem._merge_section_into_markdown(existing, "### [entry] task-1 — 2026-01-01 — done", new_section)

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

        result = mem._merge_section_into_markdown(existing, "### [entry] beta — 2026-01-02 — done", new_section)

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

        result = mem._merge_section_into_markdown("", "### [entry] task-1 — 2026-01-01 — done", new_section)
        assert result == new_section

    def test_merge_validates_section_header_match(self):
        """Raises ValueError if section_content doesn't start with section_header."""
        existing = "Some content"
        new_section = "Mismatched content"

        with pytest.raises(ValueError):
            mem._merge_section_into_markdown(existing, "### [entry] foo", new_section)

    def test_merge_appends_when_no_matching_sections_exist(self):
        """Append when existing content has no matching [entry]/[evicted] blocks."""
        existing = """# Main
## Subsection

This has no [entry] or [evicted] blocks.
"""
        new_section = """### [entry] task — 2026-01-01 — done

Content."""

        result = mem._merge_section_into_markdown(existing, "### [entry] task — 2026-01-01 — done", new_section)
        # Since there are no [entry]/[evicted] blocks, it appends
        assert new_section in result


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
        first_merged = mem._merge_section_into_markdown(existing_v1, "## [entry] task-2 — 2026-01-01", new_section)
        assert "## [entry] task-1" in first_merged
        assert "## [entry] task-2" in first_merged

        # Simulate concurrent update: existing content now has a new task
        existing_v2 = "## [entry] task-1 — 2026-01-01\n\nTask 1 content\n\n## [entry] task-3 — 2026-01-01\n\nTask 3 content\n"

        # CORRECT behavior on retry: merge new_section into existing_v2
        correct_retry_merge = mem._merge_section_into_markdown(existing_v2, "## [entry] task-2 — 2026-01-01", new_section)
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
            mem._merge_section_into_markdown(existing_v2, "## [entry] task-2 — 2026-01-01", first_merged)
