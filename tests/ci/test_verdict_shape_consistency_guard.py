"""Cross-consumer meta-test: every `{blocking, findings}` verdict consumer
agrees on the same decision (#1816 code-gate rebuild, plan step 16).

Three independent implementations parse the Layer B structured verdict:

  * `code-review.yml`'s "Verify review verdict" step, pinned by
    `structured_verdict()` in test_code_review_verdict_guard.py.
  * `scripts/review_debt_collector.py`'s `has_blocking_finding()` (real
    shipped module, not a mirror).
  * `event-dispatch.yml`'s `review-negative-claude-bot` job, pinned by
    `parse_verdict()` in test_event_dispatch_review_parser.py.

Each was hardened independently against the same failure modes (malformed
JSON, missing/wrong-typed fields, blocking/findings-emptiness mismatch) and
each fails closed in its own words. This test does not re-derive those rules;
it feeds one shared fixture set through all three and asserts they land on
the same `blocking` verdict — the drift this guards against is one consumer
silently diverging (e.g. failing open where the other two fail closed) after
an independent edit to just one of the three files.

It also cross-checks the two `fingerprint()` implementations
(`scripts/rework_policy.py`, a frozenset; the event-dispatch parser mirror in
test_event_dispatch_review_parser.py, a sorted list) resolve to the same set
of "<class>|<file>" strings for the same findings array.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from review_debt_collector import has_blocking_finding  # noqa: E402
from rework_policy import fingerprint as rework_fingerprint  # noqa: E402

from tests.ci.test_code_review_verdict_guard import structured_verdict  # noqa: E402
from tests.ci.test_event_dispatch_review_parser import (  # noqa: E402
    fingerprint as dispatch_fingerprint,
    parse_verdict,
)


def _marker(blocking: bool, findings: list) -> str:
    import json

    payload = json.dumps({"blocking": blocking, "findings": findings})
    return f"## Claude Code Review — PR #1\n\n<!-- code-review-findings\n{payload}\n-->\n"


FINDINGS = [{"class": "regression", "file": "a.py"}]

STRUCTURED_BLOCKING = _marker(True, FINDINGS)
STRUCTURED_PASS = _marker(False, [])
MALFORMED_JSON = (
    "## Claude Code Review — PR #1\n\n<!-- code-review-findings\n{not json\n-->\n"
)
MISSING_FIELD = (
    "## Claude Code Review — PR #1\n\n"
    '<!-- code-review-findings\n{"findings": []}\n-->\n'
)
LEGACY_PROSE_BLOCKING = "## Claude Code Review — PR #1\n\n### MAJOR findings\n\n1. Regex too broad\n"
LEGACY_PROSE_CLEAN = "## Claude Code Review — PR #1\n\nNo issues found. Checked for bugs.\n"


def _structured_to_bool(verdict: str | None) -> bool | None:
    if verdict is None:
        return None
    return verdict == "fail"


MARKER_PRESENT_CASES = [
    ("structured_blocking", STRUCTURED_BLOCKING, True),
    ("structured_pass", STRUCTURED_PASS, False),
    ("malformed_json", MALFORMED_JSON, True),  # fail closed
    ("missing_field", MISSING_FIELD, True),  # fail closed
]

MARKER_ABSENT_CASES = [
    ("legacy_prose_blocking", LEGACY_PROSE_BLOCKING),
    ("legacy_prose_clean", LEGACY_PROSE_CLEAN),
]


class TestMarkerPresentConsumersAgree:
    def test_all_three_consumers_agree_on_blocking(self):
        for name, body, expected_blocking in MARKER_PRESENT_CASES:
            sv_blocking = _structured_to_bool(structured_verdict(body))
            debt_blocking = has_blocking_finding(body)
            dispatch_blocking, _ = parse_verdict(body)

            assert sv_blocking == expected_blocking, name
            assert debt_blocking == expected_blocking, name
            assert dispatch_blocking == expected_blocking, name


class TestMarkerAbsentFallsThroughConsistently:
    def test_structured_verdict_defers_to_prose_ladder(self):
        for name, body in MARKER_ABSENT_CASES:
            assert structured_verdict(body) is None, name

    def test_prose_fallback_consumers_agree(self):
        for name, body in MARKER_ABSENT_CASES:
            debt_blocking = has_blocking_finding(body)
            dispatch_blocking, _ = parse_verdict(body)
            assert debt_blocking == dispatch_blocking, name


class TestFingerprintImplementationsAgree:
    def test_same_findings_yield_same_fingerprint_set(self):
        findings = [
            {"class": "regression", "file": "a.py"},
            {"class": "concurrency", "file": "b.py"},
            {"class": "regression", "file": "a.py"},  # dup
        ]
        assert rework_fingerprint(findings) == frozenset(dispatch_fingerprint(findings))

    def test_empty_findings_yield_empty_set_both_sides(self):
        assert rework_fingerprint([]) == frozenset(dispatch_fingerprint([]))
