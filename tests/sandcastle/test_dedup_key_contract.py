"""Dedup-key contract: Python side of a shared fixture also read by the TS
side (#1121 step 11, decision 17736ef0-01d2-492a-b490-ef5d0b46cb11).

The supervisor's completion-event emission and the (future) S4 sweeper's
re-emission must produce byte-identical dedup keys for the same
``(event_type, task_id, attempt)`` triple — the issue's motivating bug was a
1-based/0-based ``a1``/``a0`` drift between the two sides. This fixture and
its TS mirror (``.sandcastle/check-dedup-key-contract.mts``) pin the format
so a future change to either side's string interpolation is caught here
instead of silently breaking dedup between the two event sources.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agents.task_dispatch import build_dedup_key

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "sandcastle-dedup-key.json"


def _load_cases() -> list[dict[str, Any]]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"]


def test_fixture_has_cases() -> None:
    cases = _load_cases()
    assert len(cases) >= 1


def test_build_dedup_key_matches_fixture() -> None:
    for case in _load_cases():
        actual = build_dedup_key(case["eventType"], case["taskId"], case["attempt"])
        assert actual == case["dedupKey"], case
