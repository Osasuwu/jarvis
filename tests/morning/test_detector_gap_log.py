"""Tests for detector_gap_log (#1595).

All tests use an injectable in-memory store — no network, no memory MCP.
"""

from __future__ import annotations

from detector_gap_log import GapRecord, PromoteSuggestion, log_gap


# ============================================================================
# Injectable in-memory store (test double)
# ============================================================================


class _InMemoryStore:
    def __init__(self):
        self._records: list[GapRecord] = []

    def load_all(self) -> list[GapRecord]:
        return list(self._records)

    def save(self, record: GapRecord) -> None:
        self._records.append(record)

    def update(self, record: GapRecord) -> None:
        for i, r in enumerate(self._records):
            if r.key == record.key:
                self._records[i] = record
                return


# ============================================================================
# AC: first occurrence writes to memory, nothing else
# ============================================================================


def test_first_occurrence_writes_to_store_returns_none():
    store = _InMemoryStore()
    result = log_gap("GitHub open PRs not tracked by status digest", store)
    assert result is None
    assert len(store._records) == 1


def test_first_occurrence_stores_description():
    store = _InMemoryStore()
    log_gap("GitHub open PRs not tracked by status digest", store)
    assert store._records[0].description == "GitHub open PRs not tracked by status digest"
    assert store._records[0].count == 1


# ============================================================================
# AC: second occurrence produces a promote suggestion
# ============================================================================


def test_second_occurrence_returns_promote_suggestion():
    store = _InMemoryStore()
    log_gap("GitHub open PRs not tracked by status digest", store)
    result = log_gap("GitHub open PRs not tracked by status digest", store)
    assert isinstance(result, PromoteSuggestion)
    assert result.count == 2


def test_third_occurrence_increments_count():
    store = _InMemoryStore()
    log_gap("some uncovered data gap", store)
    log_gap("some uncovered data gap", store)
    result = log_gap("some uncovered data gap", store)
    assert isinstance(result, PromoteSuggestion)
    assert result.count == 3


# ============================================================================
# AC: repeat recognition does not rely on literal text match
# ============================================================================


def test_paraphrased_gap_recognized_as_same():
    """Fuzzy match: rephrased version of the same gap triggers promote."""
    store = _InMemoryStore()
    log_gap("GitHub open PRs not tracked by status digest", store)
    # Paraphrase — different word order + "pull requests" instead of "PRs"
    result = log_gap("Status digest does not track open GitHub pull requests", store)
    assert isinstance(result, PromoteSuggestion), (
        "Paraphrased gap should be recognized as the same gap, not stored as new"
    )


def test_literal_match_still_works():
    """Literal match (identity) must also trigger promote."""
    store = _InMemoryStore()
    log_gap("calendar events not covered", store)
    result = log_gap("calendar events not covered", store)
    assert isinstance(result, PromoteSuggestion)


# ============================================================================
# AC: no issue created automatically
# ============================================================================


def test_no_issue_created_automatically():
    """No code path in log_gap triggers issue creation."""
    store = _InMemoryStore()
    log_gap("some uncovered gap", store)
    suggestion = log_gap("some uncovered gap", store)
    # The result carries no issue reference
    assert not hasattr(suggestion, "issue_number")
    assert not hasattr(suggestion, "issue_url")
    # Stored records have no issue reference either
    for record in store.load_all():
        assert not hasattr(record, "issue_number")
        assert not hasattr(record, "issue_url")


# ============================================================================
# AC: no detector created automatically
# ============================================================================


def test_no_detector_created_automatically():
    """No code path in log_gap creates a detector object."""
    store = _InMemoryStore()
    log_gap("some uncovered gap", store)
    suggestion = log_gap("some uncovered gap", store)
    assert not hasattr(suggestion, "detector")
    assert not hasattr(suggestion, "detector_name")
    assert not hasattr(suggestion, "detector_config")


# ============================================================================
# AC: promote suggestion visible in digest output
# ============================================================================


def test_promote_suggestion_render_contains_description():
    """render() produces human-readable text for digest output."""
    store = _InMemoryStore()
    desc = "GitHub open PRs not tracked by status digest"
    log_gap(desc, store)
    suggestion = log_gap(desc, store)
    assert isinstance(suggestion, PromoteSuggestion)
    rendered = suggestion.render()
    assert desc in rendered


def test_promote_suggestion_render_mentions_detector():
    """render() names the action: promote to a detector."""
    store = _InMemoryStore()
    log_gap("some gap", store)
    suggestion = log_gap("some gap", store)
    rendered = suggestion.render()
    assert "detector" in rendered.lower()


def test_promote_suggestion_render_includes_count():
    """render() includes the occurrence count so human knows the weight."""
    store = _InMemoryStore()
    log_gap("some gap", store)
    log_gap("some gap", store)
    suggestion = log_gap("some gap", store)
    rendered = suggestion.render()
    assert "3" in rendered


# ============================================================================
# AC: module testable with injectable store, no network
# (validated implicitly: _InMemoryStore is the only store used above,
#  and the module has no network imports — verified by separate grep)
# ============================================================================


def test_distinct_gaps_are_stored_separately():
    """Two unrelated gaps do not trigger each other's promote path."""
    store = _InMemoryStore()
    log_gap("GitHub open PRs not tracked", store)
    # Completely different topic — should be first occurrence → None
    result = log_gap("Calendar events missing from digest", store)
    assert result is None
    assert len(store._records) == 2


def test_first_of_each_gap_is_none_second_triggers_promote():
    """Multiple distinct gaps tracked independently."""
    store = _InMemoryStore()
    # First occurrences
    assert log_gap("GitHub PRs not covered", store) is None
    assert log_gap("Calendar events missing", store) is None
    # Second occurrences
    assert isinstance(log_gap("GitHub PRs not covered", store), PromoteSuggestion)
    assert isinstance(log_gap("Calendar events missing", store), PromoteSuggestion)
    # Only two records (not four)
    assert len(store._records) == 2
