"""#1572 AC9 - release body assembly: no issue links added by the engine
itself, **Full Changelog** line always present, footer always present.
notes_body/remaining_section are already agent-authored prose (facts sourced
from the collected window / milestone per the fact-anchoring linter) - this
function only appends the mechanical Full-Changelog line and footer.
"""

from __future__ import annotations

from scripts.weekly_release_engine import assemble_release_body


def test_full_changelog_line_is_present():
    body = assemble_release_body(
        notes_body="- Added schema v2 for the daily digest (#1597).",
        remaining_section="",
        full_changelog_url="https://github.com/Osasuwu/jarvis/compare/v0.4.2...v0.5.0",
    )
    assert "**Full Changelog**: https://github.com/Osasuwu/jarvis/compare/v0.4.2...v0.5.0" in body


def test_footer_is_present_on_every_release():
    body = assemble_release_body(
        notes_body="- Added schema v2 (#1597).",
        remaining_section="",
        full_changelog_url="https://github.com/x/y/compare/a...b",
    )
    assert "Опубликовано ботом" in body


def test_engine_adds_no_issue_links_of_its_own():
    body = assemble_release_body(
        notes_body="- Added schema v2 (#1597).",
        remaining_section="- Migration cleanup still pending (#1601).",
        full_changelog_url="https://github.com/x/y/compare/a...b",
    )
    assert "github.com/x/y/issues/" not in body


def test_remaining_section_included_when_non_empty():
    body = assemble_release_body(
        notes_body="- Added schema v2 (#1597).",
        remaining_section="## Осталось\n- Migration cleanup pending (#1601).",
        full_changelog_url="https://github.com/x/y/compare/a...b",
    )
    assert "## Осталось" in body
    assert "Migration cleanup pending (#1601)" in body


def test_remaining_section_omitted_when_empty():
    body = assemble_release_body(
        notes_body="- Added schema v2 (#1597).",
        remaining_section="",
        full_changelog_url="https://github.com/x/y/compare/a...b",
    )
    assert "## Осталось" not in body
