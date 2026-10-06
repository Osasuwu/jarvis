"""#1572 AC10 / #1761 - trust ramp: first 3 releases per repo are drafts; 3
consecutive published-without-edits -> auto-publish. State is derived
entirely from the release history handed in (the caller reads it live
from the GitHub releases API - no local state is stored by this function).
"""

from __future__ import annotations

from scripts.weekly_release_engine import trust_ramp_state

CLEAN = {"published": True, "edited_after_publish": False}


def test_no_prior_releases_is_draft():
    assert trust_ramp_state([]) == "draft"


def test_fewer_than_three_prior_releases_is_draft():
    assert trust_ramp_state([CLEAN] * 2) == "draft"


def test_three_consecutive_clean_publishes_graduates_to_auto():
    assert trust_ramp_state([CLEAN] * 3) == "auto"


def test_a_post_publish_edit_in_the_last_three_keeps_it_on_draft():
    releases = [CLEAN, {"published": True, "edited_after_publish": True}, CLEAN]
    assert trust_ramp_state(releases) == "draft"


def test_an_unpublished_draft_in_the_last_three_keeps_it_on_draft():
    releases = [{"published": False, "edited_after_publish": False}, CLEAN, CLEAN, CLEAN]
    assert trust_ramp_state(releases) == "draft"


def test_only_the_three_most_recent_releases_matter():
    # An old bad release beyond the last-3 window must not hold the ramp
    # back forever once 3 clean releases have happened since.
    releases = [CLEAN] * 3 + [{"published": True, "edited_after_publish": True}]
    assert trust_ramp_state(releases) == "auto"
