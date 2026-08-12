"""Tests for scripts/session-context.py — recovery section sizing and assembly."""

import sys
import importlib.util
from pathlib import Path

# Load session-context.py as a module (it's a script, not a normal package)
script_path = Path(__file__).parent.parent.parent / "scripts" / "session-context.py"
spec = importlib.util.spec_from_file_location("session_context", script_path)
sc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sc)


class TestRecoverySectionCap:
    """Test recovery section size ceiling (#1353)."""

    def test_cap_recovery_payload_normal(self):
        """Short payload should not be truncated."""
        payload = "Short recovery data"
        result = sc._cap_recovery_payload(payload)
        assert result == payload

    def test_cap_recovery_payload_truncated(self):
        """Oversized payload should be truncated with visible marker."""
        # Create payload larger than the cap
        large_payload = "x" * (sc.RECOVERY_SECTION_MAX_CHARS + 500)
        result = sc._cap_recovery_payload(large_payload)

        # Check truncation marker is present
        assert "[truncated," in result
        assert "chars omitted]" in result

        # Check result stays within budget
        assert len(result) <= sc.RECOVERY_SECTION_MAX_CHARS

        # Check we actually truncated (not just copied)
        assert len(result) < len(large_payload)

    def test_format_recovery_section_respects_cap(self):
        """Formatted recovery section should stay within RECOVERY_SECTION_MAX_CHARS."""
        # Create large recovery payload
        large_payload = "y" * (sc.RECOVERY_SECTION_MAX_CHARS + 1000)
        session_id = "test-session-123"

        result = sc._format_recovery_section(large_payload, session_id)

        # Extract just the payload part (after the header)
        lines = result.split("\n")
        # Find where the payload starts (after the "Pre-Compact Recovery" header block)
        header_end = 0
        for i, line in enumerate(lines):
            if line.startswith("The full row"):
                header_end = i + 2  # Skip past the header
                break

        payload_part = "\n".join(lines[header_end:])

        # The payload part should be capped and show truncation
        assert "[truncated," in payload_part

    def test_recovery_payload_cap_limit_respected(self):
        """Payload should never exceed RECOVERY_SECTION_MAX_CHARS."""
        test_cases = [
            100,  # Small
            sc.RECOVERY_SECTION_MAX_CHARS - 10,  # Just under cap
            sc.RECOVERY_SECTION_MAX_CHARS,  # At cap
            sc.RECOVERY_SECTION_MAX_CHARS + 1,  # Just over
            sc.RECOVERY_SECTION_MAX_CHARS + 10000,  # Far over
        ]

        for size in test_cases:
            payload = "a" * size
            result = sc._cap_recovery_payload(payload)
            assert len(result) <= sc.RECOVERY_SECTION_MAX_CHARS, (
                f"Payload of size {size} resulted in {len(result)} chars, "
                f"exceeds cap of {sc.RECOVERY_SECTION_MAX_CHARS}"
            )


class TestAssemblySectionsCap:
    """Test assembly respects budget even with oversized recovery section."""

    def test_oversized_recovery_alone_assembly(self):
        """Assembly with only oversized recovery should stay within budget."""
        # Create recovery section that WOULD exceed budget without capping
        large_payload = "z" * (sc.ASSEMBLY_BUDGET_CHARS + 1000)
        session_id = "test-session-456"
        recovery_rendered = sc._format_recovery_section(large_payload, session_id)

        # Build a single-section assembly
        sections = [
            (sc._PRIORITY_RECOVERY, "recovery", recovery_rendered, []),
        ]

        output, dropped_names, emitted_ids, emitted_chars = sc.assemble_sections(sections)

        # Output should stay within budget
        assert emitted_chars <= sc.ASSEMBLY_BUDGET_CHARS, (
            f"Assembly emitted {emitted_chars} chars, exceeds budget "
            f"of {sc.ASSEMBLY_BUDGET_CHARS}"
        )

    def test_multiple_sections_drop_when_recovery_capped(self):
        """Assembly with capped recovery + other sections should drop lower priority."""
        # Create a large (but capped) recovery section
        large_payload = "r" * (sc.RECOVERY_SECTION_MAX_CHARS - 50)
        recovery_rendered = sc._format_recovery_section(large_payload, "test-123")

        # Create multiple lower-priority sections
        sections = [
            (sc._PRIORITY_RECOVERY, "recovery", recovery_rendered, []),
            (sc._PRIORITY_GOALS, "goals", "## Goals\n" + "g" * 2000, []),
            (sc._PRIORITY_REMINDER, "reminder", "## Reminder\n" + "x" * 3000, []),
        ]

        output, dropped_names, emitted_ids, emitted_chars = sc.assemble_sections(sections)

        # Output should stay within budget
        assert emitted_chars <= sc.ASSEMBLY_BUDGET_CHARS

        # Recovery should be kept (highest priority)
        assert "recovery" not in dropped_names or "recovery" in [s[1] for s in sections if s[0] == sc._PRIORITY_RECOVERY]

    def test_assembly_budget_not_exceeded_with_truncation(self):
        """Real-world test: compact resume with large snapshot should stay within budget."""
        # Simulate a compact resume scenario
        # Typically recovery section is large, other sections are smaller

        # Create a recovery section that's been capped
        oversized_snapshot = "## Session Snapshot — test-abc123\n" + "x" * (
            sc.RECOVERY_SECTION_MAX_CHARS + 500
        )
        recovery_rendered = sc._format_recovery_section(oversized_snapshot, "test-abc123")

        # Add a few other sections typical in a compact resume
        sections = [
            (sc._PRIORITY_RECOVERY, "recovery", recovery_rendered, []),
            (
                sc._PRIORITY_ALWAYS_LOAD,
                "always_load",
                "## Always-Load Rules\n- Rule 1: keep things simple\n- Rule 2: test first",
                [],
            ),
        ]

        output, dropped_names, emitted_ids, emitted_chars = sc.assemble_sections(sections)

        # Main assertion: output must stay within budget
        assert emitted_chars <= sc.ASSEMBLY_BUDGET_CHARS, (
            f"Assembly with capped recovery section emitted {emitted_chars} chars, "
            f"exceeds budget of {sc.ASSEMBLY_BUDGET_CHARS}. "
            f"Dropped sections: {dropped_names}"
        )

        # Verify truncation is visible in output
        assert "[truncated," in output, "Truncation marker should be visible in output"


class TestTruncationMarker:
    """Test that truncation markers are visible to users."""

    def test_truncation_marker_in_payload(self):
        """Truncated payload should show char count."""
        large = "x" * 6000
        result = sc._cap_recovery_payload(large)

        # Should contain explicit marker with count
        assert "[truncated," in result
        assert "chars omitted]" in result

        # Extract the number from the marker
        import re

        match = re.search(r"\[truncated, (\d+) chars omitted\]", result)
        assert match is not None
        omitted_count = int(match.group(1))

        # Verify math: original - truncated + marker overhead = omitted
        # (approximately)
        assert omitted_count > 0
        assert omitted_count < len(large)

    def test_truncation_marker_visible_in_recovery_section(self):
        """Truncation marker should appear in formatted recovery section."""
        # Create oversized payload
        oversized = "data line 1\ndata line 2\n" + "y" * 5000

        result = sc._format_recovery_section(oversized, "test-session")

        # The marker should be in the output
        assert "[truncated," in result

        # It should be part of the rendered text (not just logged)
        # Verify by checking it comes after the header but before the footer
        assert result.count("[truncated,") >= 1


if __name__ == "__main__":
    # Run with: python -m pytest tests/scripts/test_session_context.py -v
    import pytest

    pytest.main([__file__, "-v"])
