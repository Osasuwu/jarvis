"""Tests for TriageEngine parsing and integration."""

from jarvis.triage.engine import TriageEngine

# -- _extract_parent ---------------------------------------------------------


def test_extract_parent_standard() -> None:
    body = "Parent: #5\n\n## Description\nSome text."
    assert TriageEngine._extract_parent(body) == 5


def test_extract_parent_no_parent() -> None:
    body = "## Description\nNo parent here."
    assert TriageEngine._extract_parent(body) is None


def test_extract_parent_with_spaces() -> None:
    body = "Parent:  #  42 \n"
    assert TriageEngine._extract_parent(body) == 42


# -- _extract_children -------------------------------------------------------


def test_extract_children_standard() -> None:
    body = (
        "## Children\n"
        "- [ ] #11 Daily Triage\n"
        "- [x] #12 Planning Standards\n"
        "- [ ] #22 Weekly Reporting\n"
    )
    children = TriageEngine._extract_children(body)
    assert children == [11, 12, 22]


def test_extract_children_empty() -> None:
    body = "## Summary\nNo children."
    assert TriageEngine._extract_children(body) == []


def test_extract_children_mixed_content() -> None:
    body = "- [ ] #7 Epic\n- Regular bullet without issue\n- [ ] #8 Another"
    children = TriageEngine._extract_children(body)
    assert 7 in children
    assert 8 in children
