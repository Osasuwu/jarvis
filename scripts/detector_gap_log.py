"""Detector gap journal — memory-first, promote on second occurrence (#1595).

Thin module. Three-step loop:
  1. First occurrence  → stored in the injected GapStore; returns None.
  2. Second occurrence → returns PromoteSuggestion for digest output.
  3. Promote to a real detector is a human decision — this module never
     creates one, never opens an issue.

Repeat recognition uses Jaccard similarity over normalised word tokens so
that paraphrased descriptions of the same gap still match. The real
GapStore implementation wraps mcp__memory__*; tests inject _InMemoryStore.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

# Jaccard threshold for "same gap".
# ceiling: word-level Jaccard with simple suffix stripping; works well for
# natural-language paraphrases sharing 3-5 content words (40 % overlap).
# If false positives appear for short (1-2 word) descriptions, raise to 0.5.
_SIMILARITY_THRESHOLD = 0.4

_STOP_WORDS = frozenset(
    {
        "a", "an", "the",
        "is", "are", "was", "were", "be", "been",
        "do", "does", "did",
        "has", "have", "had",
        "not", "no", "nor",
        "by", "for", "from", "in", "of", "on", "at", "to",
        "and", "or", "but",
        "it", "its",
        "any", "some", "all",
    }
)


# ============================================================================
# Public data types
# ============================================================================


@dataclass
class GapRecord:
    """One stored detector-gap entry."""

    key: str          # sorted-token canonical key (used for update look-up)
    description: str  # original description text
    count: int        # times this gap has been logged


@dataclass
class PromoteSuggestion:
    """A proposal to promote a repeated gap into a proper detector.

    Returned by log_gap() on the second (or later) occurrence.
    Carries no issue reference, no detector config — human decides.
    """

    description: str
    count: int

    def render(self) -> str:
        """Human-readable line for digest output."""
        return (
            f"Detector gap seen {self.count}× — consider promoting to a detector:\n"
            f"  {self.description}"
        )


# ============================================================================
# GapStore protocol (injectable)
# ============================================================================


class GapStore(Protocol):
    """Storage contract — implement with mcp__memory__* for production,
    _InMemoryStore for tests."""

    def load_all(self) -> list[GapRecord]: ...

    def save(self, record: GapRecord) -> None: ...

    def update(self, record: GapRecord) -> None: ...


# ============================================================================
# Public API
# ============================================================================


def log_gap(description: str, store: GapStore) -> PromoteSuggestion | None:
    """Log a detector gap.

    Returns None on first occurrence (gap stored).
    Returns PromoteSuggestion on second or later occurrence.
    Never creates an issue. Never creates a detector.
    """
    records = store.load_all()
    match = _find_match(description, records)
    if match is None:
        store.save(GapRecord(key=_key(description), description=description, count=1))
        return None
    match.count += 1
    store.update(match)
    return PromoteSuggestion(description=match.description, count=match.count)


# ============================================================================
# Internals
# ============================================================================


def _tokens(text: str) -> set[str]:
    """Normalised content-word set for similarity comparison.

    Steps: lowercase → split on non-word chars → drop stop-words and
    very-short words → simple suffix stripping (plurals, -ed, -ing).
    """
    words: set[str] = set()
    for raw in re.split(r"\W+", text.lower()):
        if len(raw) <= 2 or raw in _STOP_WORDS:
            continue
        words.add(_stem(raw))
    return words


def _stem(word: str) -> str:
    """Strip common English suffixes to reduce inflection noise."""
    if word.endswith("ing") and len(word) > 5:
        return word[:-3]
    if word.endswith("ers") and len(word) > 5:
        return word[:-3]
    if word.endswith("ed") and len(word) > 4:
        return word[:-2]
    if word.endswith("er") and len(word) > 4:
        return word[:-2]
    if word.endswith("es") and len(word) > 4:
        return word[:-2]
    if word.endswith("s") and len(word) > 3:
        return word[:-1]
    return word


def _similarity(a: str, b: str) -> float:
    """Jaccard similarity between the token sets of two descriptions."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _key(text: str) -> str:
    """Sorted-token canonical key — stable across minor rephrasing."""
    return " ".join(sorted(_tokens(text)))


def _find_match(description: str, records: list[GapRecord]) -> GapRecord | None:
    """Return the first record whose description is similar enough."""
    for record in records:
        if _similarity(description, record.description) >= _SIMILARITY_THRESHOLD:
            return record
    return None
