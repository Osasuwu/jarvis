"""Tests for _normalize_for_embed helper and underscore symmetry (#766)."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'mcp-memory'))

import pytest
from embeddings import _normalize_for_embed, _canonical_embed_text


class TestNormalizeForEmbed:
    """Unit tests for _normalize_for_embed helper function."""

    def test_single_underscore(self):
        """Replace single underscore with space."""
        assert _normalize_for_embed("hello_world") == "hello world"

    def test_multiple_underscores(self):
        """Replace multiple underscores with spaces."""
        assert _normalize_for_embed("autonomous_chain_synthesis_template") == "autonomous chain synthesis template"

    def test_preserves_spaces(self):
        """Preserve existing spaces."""
        assert _normalize_for_embed("hello world") == "hello world"

    def test_mixed_underscores_and_spaces(self):
        """Handle mixed underscores and spaces."""
        assert _normalize_for_embed("hello_world test_case") == "hello world test case"

    def test_empty_string(self):
        """Handle empty string."""
        assert _normalize_for_embed("") == ""

    def test_no_underscores(self):
        """Return unchanged text when no underscores."""
        assert _normalize_for_embed("hello world") == "hello world"


class TestCanonicalEmbedTextNormalization:
    """Integration tests for _canonical_embed_text using _normalize_for_embed."""

    def test_normalizes_name_field(self):
        """Verify name field gets normalized for embedding."""
        result = _canonical_embed_text(
            name="autonomous_chain_synthesis_template",
            description="test",
            tags=[],
            content=""
        )
        # Name should have underscores replaced with spaces
        assert "autonomous chain synthesis template" in result
        assert "autonomous_chain_synthesis_template" not in result

    def test_normalizes_name_only(self):
        """Name normalization appears first in result."""
        result = _canonical_embed_text(
            name="test_name",
            description="",
            tags=[],
            content=""
        )
        assert result == "test name"

    def test_preserves_tag_structure(self):
        """Tags are not normalized (they're metadata, not content)."""
        result = _canonical_embed_text(
            name="",
            description="",
            tags=["memory", "recall"],
            content=""
        )
        # Tag line should be present
        assert "tags: memory, recall" in result

    def test_full_canonical_structure(self):
        """Full structure with name, tags, description, content."""
        result = _canonical_embed_text(
            name="memory_template",
            description="A test memory",
            tags=["test"],
            content="Some content here"
        )
        # Name normalized, tags added, then description and content
        lines = result.split("\n")
        assert len(lines) >= 3
        assert lines[0] == "memory template"  # name, normalized
        assert "tags: test" in result
        assert "A test memory" in result
        assert "Some content here" in result
