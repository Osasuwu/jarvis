"""#1572 AC11 - draft-aware anchor window: last release OR an existing
pending draft's anchor -> now, capped at 1 month; cap-truncation must be
disclosed by the caller (release body says "covers the period from X to
Y") whenever `truncated` is True.
"""

from __future__ import annotations

from scripts.weekly_release_engine import compute_window


def test_window_anchors_to_last_release_when_no_pending_draft():
    r = compute_window(
        last_release_at="2026-08-01T00:00:00Z",
        pending_draft_at=None,
        now="2026-08-20T00:00:00Z",
    )
    assert r.start.startswith("2026-08-01")
    assert r.truncated is False


def test_window_prefers_pending_draft_anchor_over_last_release():
    # A pending draft's own original anchor wins so re-running the skill
    # updates the existing draft in place instead of restarting the clock.
    r = compute_window(
        last_release_at="2026-07-01T00:00:00Z",
        pending_draft_at="2026-08-10T00:00:00Z",
        now="2026-08-20T00:00:00Z",
    )
    assert r.start.startswith("2026-08-10")
    assert r.truncated is False


def test_window_caps_at_one_month_and_flags_truncation():
    r = compute_window(
        last_release_at="2026-01-01T00:00:00Z",
        pending_draft_at=None,
        now="2026-08-20T00:00:00Z",
        cap_days=30,
    )
    assert r.truncated is True
    # capped start is (now - 30d), not the real last-release date
    assert not r.start.startswith("2026-01-01")


def test_no_prior_anchor_at_all_falls_back_to_cap_and_flags_truncation():
    r = compute_window(last_release_at=None, pending_draft_at=None, now="2026-08-20T00:00:00Z")
    assert r.truncated is True
