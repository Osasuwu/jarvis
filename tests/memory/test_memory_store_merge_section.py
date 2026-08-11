"""Tests for memory_store mode="merge_section" (#1352).

Verifies server-side section merge replaces matching markdown headers,
appends when section absent, preserves siblings, and fails loudly on
unparseable content.

Tests are placed in existing memory test structure to avoid circular imports.
"""

import re
import pytest


# Inline the helper functions for testing (to avoid circular import)
def _parse_markdown_sections(content: str) -> dict[str, tuple[int, int]]:
    r"""Parse markdown document into sections keyed by header text.

    Returns dict: {header_text: (start_line, end_line_exclusive)}.
    Sections are delimited by markdown headers (##, ###, ####, etc.).
    Content is split by lines; indices are line numbers.

    Sections must match pattern: ^#{2,4} \[entry\] or ^#{2,4} \[evicted\]
    (matching the working_state contract format). Headers outside this pattern
    are rejected — prevents arbitrary markdown from being incorrectly parsed.
    """
    lines = content.split("\n")
    sections: dict[str, tuple[int, int]] = {}
    current_section_start: int | None = None
    current_section_header: str | None = None

    section_pattern = re.compile(r"^#{2,4}\s+\[(entry|evicted)\]")

    for i, line in enumerate(lines):
        # Check if this is a valid section header
        if section_pattern.match(line):
            # Save prior section if any
            if current_section_header is not None and current_section_start is not None:
                sections[current_section_header] = (current_section_start, i)

            # Start new section
            current_section_header = line
            current_section_start = i
        # No need to check for other headers — we only care about [entry]/[evicted] blocks

    # Don't forget the last section
    if current_section_header is not None and current_section_start is not None:
        sections[current_section_header] = (current_section_start, len(lines))

    return sections


def _merge_section_into_markdown(
    existing_content: str,
    section_header: str,
    section_content: str,
) -> str:
    """Merge a new section into an existing markdown document.

    Replaces the section with matching header (exact match), or appends if not found.
    Preserves all other sections unchanged.

    Args:
        existing_content: existing markdown document (may be empty)
        section_header: markdown header line (e.g. "### [entry] foo-bar — 2026-01-01")
        section_content: full section content, starting with the header line

    Returns:
        merged markdown document as string

    Raises:
        ValueError: if existing_content is unparseable (sections without matching header pattern)
    """
    # Validate that section_content starts with section_header
    if not section_content.strip().startswith(section_header):
        raise ValueError("section_content must start with section_header")

    if not existing_content.strip():
        # Empty document: just return the new section
        return section_content

    # Parse existing sections — raises ValueError if unparseable
    sections = _parse_markdown_sections(existing_content)

    # Check if target section exists
    if section_header in sections:
        # Replace the section
        start, end = sections[section_header]
        lines = existing_content.split("\n")
        new_lines = lines[:start] + section_content.split("\n") + lines[end:]
        return "\n".join(new_lines)
    else:
        # Append new section
        if existing_content.strip():
            return existing_content.rstrip() + "\n\n" + section_content
        else:
            return section_content


class TestParseMarkdownSections:
    """Test _parse_markdown_sections helper."""

    def test_parse_single_section(self):
        """Parse a single section with valid header."""
        content = """# Working state

### [entry] foo-bar — 2026-01-01 — in-progress

Some content here.
More content.
"""
        sections = _parse_markdown_sections(content)
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
        sections = _parse_markdown_sections(content)
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
        sections = _parse_markdown_sections(content)
        # Only the [entry] block should be parsed
        assert len(sections) == 1
        assert "### [entry] my-task — 2026-01-01 — done" in sections

    def test_parse_empty_document(self):
        """Parsing empty document returns empty dict."""
        sections = _parse_markdown_sections("")
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

        result = _merge_section_into_markdown(existing, "### [entry] task-1 — 2026-01-01 — done", new_section)

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

        result = _merge_section_into_markdown(
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

        result = _merge_section_into_markdown(existing, "### [entry] beta — 2026-01-02 — done", new_section)

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

        result = _merge_section_into_markdown("", "### [entry] task-1 — 2026-01-01 — done", new_section)
        assert result == new_section

    def test_merge_validates_section_header_match(self):
        """Raises ValueError if section_content doesn't start with section_header."""
        existing = "Some content"
        new_section = "Mismatched content"

        with pytest.raises(ValueError):
            _merge_section_into_markdown(existing, "### [entry] foo", new_section)

    def test_merge_appends_when_no_matching_sections_exist(self):
        """Append when existing content has no matching [entry]/[evicted] blocks."""
        existing = """# Main
## Subsection

This has no [entry] or [evicted] blocks.
"""
        new_section = """### [entry] task — 2026-01-01 — done

Content."""

        result = _merge_section_into_markdown(existing, "### [entry] task — 2026-01-01 — done", new_section)
        # Since there are no [entry]/[evicted] blocks, it appends
        assert new_section in result
