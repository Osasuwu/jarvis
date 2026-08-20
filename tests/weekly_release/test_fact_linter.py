"""#1572 AC6 - fact-anchoring linter: every note line must cite >=1 PR/issue
number pulled from the collected window; a quantitative claim with no such
citation is rejected. Language-independent (checks citation presence, not
banned words), so the same rule covers the skill's ru and en <details> body.
"""

from __future__ import annotations

from scripts.weekly_release_engine import lint_release_notes

WINDOW_REFS = {"1597", "1600", "1601", "1602", "1604", "1612"}


def test_line_with_valid_window_citation_passes():
    lines = ["- Daily digest gained a schema v2 (#1597)."]
    assert lint_release_notes(lines, WINDOW_REFS) == []


def test_line_with_no_citation_at_all_is_rejected():
    lines = ["- Assorted cleanup and polish."]
    violations = lint_release_notes(lines, WINDOW_REFS)
    assert len(violations) == 1
    assert "missing PR/issue citation" in violations[0]


def test_line_citing_a_number_outside_the_window_is_rejected():
    # #9999 is not in this window's ref set - a stale/foreign citation must
    # not pass just because it looks like a citation.
    lines = ["- Fixed a bug (#9999)."]
    violations = lint_release_notes(lines, WINDOW_REFS)
    assert len(violations) == 1
    assert "missing PR/issue citation" in violations[0]


def test_quantitative_claim_without_citation_gets_specific_message():
    lines = ["- Retries went from 3 attempts to 5."]
    violations = lint_release_notes(lines, WINDOW_REFS)
    assert len(violations) == 1
    assert "quantitative claim without a source citation" in violations[0]


def test_quantitative_claim_with_valid_citation_passes():
    lines = ["- Retries went from 3 attempts to 5 (#1602)."]
    assert lint_release_notes(lines, WINDOW_REFS) == []


def test_language_independent_ru_line_same_rule():
    lines_pass = ["- Добавлена схема v2 для дайджеста (#1597)."]
    lines_fail = ["- Добавлена схема v2 для дайджеста."]
    assert lint_release_notes(lines_pass, WINDOW_REFS) == []
    assert len(lint_release_notes(lines_fail, WINDOW_REFS)) == 1


def test_multiple_lines_report_one_violation_each():
    lines = [
        "- Cited fix (#1600).",
        "- Uncited claim.",
        "- Another cited fix (#1601).",
    ]
    violations = lint_release_notes(lines, WINDOW_REFS)
    assert len(violations) == 1
    assert "line 1" in violations[0]
