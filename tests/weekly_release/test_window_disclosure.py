"""#1668 - format_window_disclosure(): a cap-truncated window must disclose
its covered period in the release body; an untruncated window needs no
disclosure at all.
"""

from __future__ import annotations

from scripts.weekly_release_engine import format_window_disclosure


def test_untruncated_window_yields_no_disclosure():
    assert format_window_disclosure("2026-08-01", "2026-08-20", truncated=False) == ""


def test_truncated_window_discloses_the_covered_period():
    text = format_window_disclosure("2026-07-21", "2026-08-20", truncated=True)
    assert "2026-07-21" in text
    assert "2026-08-20" in text


def test_disclosure_renders_dates_not_full_timestamps():
    # #1761: compute_window() hands over full ISO-8601 bounds.
    text = format_window_disclosure(
        "2026-07-21T13:15:09.775515+00:00", "2026-08-20T06:00:00+00:00", truncated=True
    )
    assert text == "_Покрывает период с 2026-07-21 по 2026-08-20._"
