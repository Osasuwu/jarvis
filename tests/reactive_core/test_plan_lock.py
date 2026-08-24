"""Tests for agents.plan_lock — canonicalization/hashing + strict parser
for the ``## Plan`` section (issue #1685).

Sibling module to agents.scope_hash (issue #773's consolidation pattern),
but over plan *text*, not a file list.
"""

from __future__ import annotations

import pytest

from agents.plan_lock import (
    MalformedPlanError,
    canonicalize_plan,
    hash_plan,
    parse_plan,
)

_LF_PLAN = "## Plan\n\n- step one\n- step two\n\nlock: abc123\n"
_CRLF_PLAN = "## Plan\r\n\r\n- step one\r\n- step two\r\n\r\nlock: abc123\r\n"
_TRAILING_WS_PLAN = "## Plan   \n\n- step one   \n- step two\t\n\nlock: abc123\n"


def test_canonicalize_is_idempotent() -> None:
    once = canonicalize_plan(_LF_PLAN)
    twice = canonicalize_plan(once)
    assert once == twice


def test_hash_stable_across_crlf_lf() -> None:
    """Golden test: CRLF and LF variants of the same plan hash identically."""
    assert hash_plan(_LF_PLAN) == hash_plan(_CRLF_PLAN)


def test_hash_stable_across_trailing_whitespace() -> None:
    """Golden test: trailing whitespace differences don't change the digest."""
    assert hash_plan(_LF_PLAN) == hash_plan(_TRAILING_WS_PLAN)


def test_hash_sensitive_to_actual_content_change() -> None:
    other = "## Plan\n\n- step one\n- step THREE\n\nlock: abc123\n"
    assert hash_plan(_LF_PLAN) != hash_plan(other)


def test_hash_is_sha256_hex() -> None:
    digest = hash_plan(_LF_PLAN)
    assert len(digest) == 64
    int(digest, 16)  # raises ValueError if not valid hex


def test_parse_plan_extracts_steps_and_lock() -> None:
    parsed = parse_plan(_LF_PLAN)
    assert parsed.steps == ("step one", "step two")
    assert parsed.lock == "abc123"


def test_parse_plan_rejects_missing_heading() -> None:
    with pytest.raises(MalformedPlanError, match="missing_heading"):
        parse_plan("- step one\n\nlock: abc123\n")


def test_parse_plan_rejects_empty_step_list() -> None:
    with pytest.raises(MalformedPlanError, match="empty_step_list"):
        parse_plan("## Plan\n\nlock: abc123\n")


def test_parse_plan_rejects_absent_lock_line() -> None:
    with pytest.raises(MalformedPlanError, match="absent_lock_line"):
        parse_plan("## Plan\n\n- step one\n")


def test_malformed_plan_error_reasons_are_distinct() -> None:
    reasons = set()
    for bad in (
        "- step one\n\nlock: x\n",
        "## Plan\n\nlock: x\n",
        "## Plan\n\n- step one\n",
    ):
        with pytest.raises(MalformedPlanError) as exc_info:
            parse_plan(bad)
        reasons.add(exc_info.value.reason)
    assert len(reasons) == 3
