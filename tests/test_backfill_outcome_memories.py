"""Tests for scripts/backfill-outcome-memories.py (#288).

Covers the pure-function helpers. DB-interaction paths
(_build_hash_to_memory_index, _resolve_memory_name, backfill) are exercised
manually via `python scripts/backfill-outcome-memories.py` against the
live Supabase project — see the PR description for the dry-run output.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path


# Script has a hyphen in the filename so import it via importlib.
_spec = importlib.util.spec_from_file_location(
    "backfill_outcome_memories",
    Path(__file__).parent.parent / "scripts" / "backfill-outcome-memories.py",
)
backfill = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(backfill)


class TestParseIssueNumber:
    def test_github_issue_url(self):
        assert backfill._parse_issue_number("https://github.com/Osasuwu/jarvis/issues/286") == 286

    def test_github_pr_url_returns_none(self):
        """PR URLs must not be treated as issue URLs."""
        assert backfill._parse_issue_number("https://github.com/Osasuwu/jarvis/pull/290") is None

    def test_none_input(self):
        assert backfill._parse_issue_number(None) is None

    def test_empty_string(self):
        assert backfill._parse_issue_number("") is None

    def test_malformed_url(self):
        assert backfill._parse_issue_number("not a url") is None


class TestParsePrNumber:
    def test_github_pr_url(self):
        assert backfill._parse_pr_number("https://github.com/Osasuwu/jarvis/pull/290") == 290

    def test_github_issue_url_returns_none(self):
        assert backfill._parse_pr_number("https://github.com/Osasuwu/jarvis/issues/286") is None

    def test_none_input(self):
        assert backfill._parse_pr_number(None) is None


class TestExtractSingleHash:
    """Only decisions mentioning exactly ONE #N qualify for attribution.
    Multi-issue decisions (sprint planners, batch triages) are too ambiguous."""

    def test_single_hash_returns_int(self):
        assert backfill._extract_single_hash("Implement #286: add memory_id") == 286

    def test_pr_hash_style_also_matches(self):
        """Decision might reference #N as PR number, not just issue."""
        assert (
            backfill._extract_single_hash(
                "Address Copilot review on PR #285 with client-side filter"
            )
            == 285
        )

    def test_zero_hashes_returns_none(self):
        assert backfill._extract_single_hash("Refactor memory server for clarity") is None

    def test_multiple_hashes_returns_none(self):
        """Sprint-opening decisions with 5 issues must NOT attribute to any one."""
        text = (
            "Open Pillar 4 Sprint 'Metacognition Loop-Closure' with 5 issues: "
            "#286, #287, #288, #237, #289."
        )
        assert backfill._extract_single_hash(text) is None

    def test_two_hashes_returns_none(self):
        """Even two #N references are too ambiguous — pick neither."""
        assert backfill._extract_single_hash("Fix #42 then revisit #43") is None

    def test_none_input(self):
        assert backfill._extract_single_hash(None) is None

    def test_empty_string(self):
        assert backfill._extract_single_hash("") is None

    def test_hash_inside_word_still_matches(self):
        """Regex is `#(\\d+)` — will catch `foo#286bar` too. Accept that as
        a known false-positive edge case; real decision text doesn't do this."""
        assert backfill._extract_single_hash("foo#286bar") == 286
