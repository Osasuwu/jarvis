"""Meta-test for .github/workflows/pr-body-check.yml.

Reimplements the workflow's decision rule in Python and asserts the
escape hatches behave as the workflow promises:

  - Closes #NNN in body                → allowed
  - priority:critical label             → allowed (hotfix bypass)
  - neither                             → blocked

Convention from CLAUDE.md §326 (path-filtered guards need meta-tests).
PR Body Check isn't path-filtered, but the escape logic is non-trivial
enough that a sibling test is worth keeping in lockstep with the YAML.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


WORKFLOW_PATH = (
    Path(__file__).resolve().parents[2]
    / ".github"
    / "workflows"
    / "pr-body-check.yml"
)


def evaluate(body: str, labels: list[str]) -> tuple[bool, str]:
    """Mirror the workflow's decision rule. Returns (allowed, reason)."""
    if "priority:critical" in labels:
        return True, "hotfix"

    matches = re.findall(r"(?:closes|fixes|resolves)\s+#(\d+)", body, re.IGNORECASE)
    if matches:
        return True, "linked"

    return False, "no-link"


def test_closes_marker_allows():
    allowed, reason = evaluate("Closes #123\n\nSome body", [])
    assert allowed
    assert reason == "linked"


def test_alt_markers_allow():
    for marker in ("Closes", "Fixes", "Resolves", "closes", "FIXES"):
        body = f"{marker} #42"
        allowed, _ = evaluate(body, [])
        assert allowed, f"{marker} should be accepted"


def test_hotfix_label_bypasses():
    allowed, reason = evaluate("urgent prod fix, no time to file", ["priority:critical"])
    assert allowed
    assert reason == "hotfix"


def test_other_labels_do_not_bypass():
    allowed, _ = evaluate("trivial change", ["priority:medium", "documentation"])
    assert not allowed


def test_empty_body_no_label_blocked():
    allowed, _ = evaluate("", [])
    assert not allowed


def test_partial_keyword_blocked():
    # "close to" should not match "closes"
    allowed, _ = evaluate("This is close to done.", [])
    assert not allowed


def test_workflow_yaml_references_priority_critical():
    """Config dimension: workflow file must mention the label name we test against."""
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "priority:critical" in text, (
        "PR Body Check workflow no longer references the priority:critical "
        "escape; this test (and CLAUDE.md hotfix rule) is now stale."
    )


def test_workflow_yaml_keeps_closes_regex():
    """Config dimension: the regex used in the YAML must still recognize Closes/Fixes/Resolves."""
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "closes|fixes|resolves" in text.lower(), (
        "PR Body Check regex changed shape — update this test to match."
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
