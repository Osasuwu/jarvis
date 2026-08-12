#!/usr/bin/env python
"""Simple test runner for session_context tests without conftest interference."""

import sys
import importlib.util
from pathlib import Path

# Load session-context.py as a module
script_path = Path(__file__).parent.parent.parent / "scripts" / "session-context.py"
spec = importlib.util.spec_from_file_location("session_context", script_path)
sc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sc)


def test_cap_recovery_payload_normal():
    """Short payload should not be truncated."""
    payload = "Short recovery data"
    result = sc._cap_recovery_payload(payload)
    assert result == payload, f"Expected unchanged payload, got: {result}"
    print("✓ test_cap_recovery_payload_normal")


def test_cap_recovery_payload_truncated():
    """Oversized payload should be truncated with visible marker."""
    large_payload = "x" * (sc.RECOVERY_SECTION_MAX_CHARS + 500)
    result = sc._cap_recovery_payload(large_payload)

    # Check truncation marker is present
    assert "[truncated," in result, f"Truncation marker missing in: {result}"
    assert "chars omitted]" in result, f"Truncation marker incomplete in: {result}"

    # Check result stays within budget
    assert len(result) <= sc.RECOVERY_SECTION_MAX_CHARS, (
        f"Result {len(result)} exceeds max {sc.RECOVERY_SECTION_MAX_CHARS}"
    )

    # Check we actually truncated (not just copied)
    assert len(result) < len(large_payload), "Payload should be truncated"
    print("✓ test_cap_recovery_payload_truncated")


def test_format_recovery_section_respects_cap():
    """Formatted recovery section should stay within RECOVERY_SECTION_MAX_CHARS."""
    large_payload = "y" * (sc.RECOVERY_SECTION_MAX_CHARS + 1000)
    session_id = "test-session-123"

    result = sc._format_recovery_section(large_payload, session_id)

    # The payload part should be capped and show truncation
    assert "[truncated," in result, f"Truncation marker missing in recovery section"
    print("✓ test_format_recovery_section_respects_cap")


def test_recovery_payload_cap_limit_respected():
    """Payload should never exceed RECOVERY_SECTION_MAX_CHARS."""
    test_cases = [
        100,
        sc.RECOVERY_SECTION_MAX_CHARS - 10,
        sc.RECOVERY_SECTION_MAX_CHARS,
        sc.RECOVERY_SECTION_MAX_CHARS + 1,
        sc.RECOVERY_SECTION_MAX_CHARS + 10000,
    ]

    for size in test_cases:
        payload = "a" * size
        result = sc._cap_recovery_payload(payload)
        assert len(result) <= sc.RECOVERY_SECTION_MAX_CHARS, (
            f"Payload of size {size} resulted in {len(result)} chars, "
            f"exceeds cap of {sc.RECOVERY_SECTION_MAX_CHARS}"
        )
    print("✓ test_recovery_payload_cap_limit_respected")


def test_oversized_recovery_alone_assembly():
    """Assembly with only oversized recovery should stay within budget."""
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
    print("✓ test_oversized_recovery_alone_assembly")


def test_truncation_marker_in_payload():
    """Truncated payload should show char count."""
    import re

    large = "x" * 6000
    result = sc._cap_recovery_payload(large)

    # Should contain explicit marker with count
    assert "[truncated," in result
    assert "chars omitted]" in result

    # Extract the number from the marker
    match = re.search(r"\[truncated, (\d+) chars omitted\]", result)
    assert match is not None, f"Could not parse truncation marker: {result}"
    omitted_count = int(match.group(1))

    # Verify math
    assert omitted_count > 0, "Omitted count should be > 0"
    assert omitted_count < len(large), "Omitted count should be < original size"
    print("✓ test_truncation_marker_in_payload")


def test_assembly_budget_not_exceeded_with_truncation():
    """Real-world test: compact resume with large snapshot should stay within budget."""
    oversized_snapshot = "## Session Snapshot — test-abc123\n" + "x" * (
        sc.RECOVERY_SECTION_MAX_CHARS + 500
    )
    recovery_rendered = sc._format_recovery_section(oversized_snapshot, "test-abc123")

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
    print("✓ test_assembly_budget_not_exceeded_with_truncation")


if __name__ == "__main__":
    try:
        test_cap_recovery_payload_normal()
        test_cap_recovery_payload_truncated()
        test_format_recovery_section_respects_cap()
        test_recovery_payload_cap_limit_respected()
        test_oversized_recovery_alone_assembly()
        test_truncation_marker_in_payload()
        test_assembly_budget_not_exceeded_with_truncation()

        print("\n✅ All tests passed!")
        sys.exit(0)
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
