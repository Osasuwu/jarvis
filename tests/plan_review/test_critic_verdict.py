"""Tests for agents.critic_verdict — critic verdict schema, fail-closed
resolution, and consensus (issue #1686 AC3, AC6, AC7, AC8).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agents.critic_verdict import (
    InvalidVerdictError,
    consensus_reached,
    planner_actor,
    resolve_verdict,
    validate_objection,
    validate_verdict,
)


# AC6: verdict schema — objection carries either resolution or blocking+rationale


def test_validate_objection_with_resolution() -> None:
    obj = validate_objection({"description": "misses edge case", "resolution": "added a check"})
    assert obj.description == "misses edge case"
    assert obj.resolution == "added a check"
    assert obj.blocking is False
    assert obj.is_unresolved() is False


def test_validate_objection_blocking_requires_rationale() -> None:
    obj = validate_objection(
        {"description": "unsafe default", "blocking": True, "rationale": "could delete data"}
    )
    assert obj.blocking is True
    assert obj.rationale == "could delete data"
    assert obj.is_unresolved() is True


def test_validate_objection_blocking_without_rationale_raises() -> None:
    with pytest.raises(InvalidVerdictError):
        validate_objection({"description": "unsafe default", "blocking": True})


def test_validate_objection_neither_resolution_nor_blocking_raises() -> None:
    with pytest.raises(InvalidVerdictError):
        validate_objection({"description": "vague concern"})


def test_validate_verdict_builds_objections() -> None:
    verdict = validate_verdict(
        {
            "critic": "goal-fit",
            "objections": [
                {"description": "ok", "resolution": "fixed"},
                {"description": "bad", "blocking": True, "rationale": "why"},
            ],
        }
    )
    assert verdict.critic == "goal-fit"
    assert len(verdict.objections) == 2
    assert verdict.has_unresolved_blocking() is True


def test_validate_verdict_no_objections_has_no_unresolved_blocking() -> None:
    verdict = validate_verdict({"critic": "state-fit", "objections": []})
    assert verdict.has_unresolved_blocking() is False


def test_validate_verdict_missing_critic_raises() -> None:
    with pytest.raises(InvalidVerdictError):
        validate_verdict({"objections": []})


# #1984: an objection citing a locked/rejected decision carries source_path +
# a verbatim source_quote; a quote that is not in that file rejects it. The
# fixture mirrors the #1982 incident: the record says extending the file set
# was *rejected*, the critic claimed the record forbade including the files.

_DECISIONS = (
    "## 2026-10-06 code-gate redesign\n"
    "- Lock 4: the always-red file set is the workflow plus its script.\n"
    "  Rejected alternative: narrowing the set to drop code-gate-verdict.yml.\n"
)


def _cited(path: Path, quote: str | None) -> dict:
    return {
        "description": "plan contradicts Lock 4",
        "blocking": True,
        "rationale": "the record says so",
        "source_path": str(path),
        "source_quote": quote,
    }


def test_decision_citation_with_verbatim_quote_passes(tmp_path: Path) -> None:
    record = tmp_path / "decisions.md"
    record.write_text(_DECISIONS, encoding="utf-8")
    quote = "Rejected alternative: narrowing the set to drop code-gate-verdict.yml."

    obj = validate_objection(_cited(record, quote))

    assert obj.source_path == str(record)
    assert obj.source_quote == quote
    assert obj.is_unresolved() is True


def test_decision_citation_with_non_verbatim_quote_is_rejected(tmp_path: Path) -> None:
    record = tmp_path / "decisions.md"
    record.write_text(_DECISIONS, encoding="utf-8")
    paraphrase = "Lock 4: the always-red set must not include code-gate-verdict.yml."

    with pytest.raises(InvalidVerdictError, match="not a verbatim substring"):
        validate_objection(_cited(record, paraphrase))


@pytest.mark.parametrize("quote", [None, "", "   "])
def test_decision_citation_without_a_quote_is_rejected(tmp_path: Path, quote: str | None) -> None:
    record = tmp_path / "decisions.md"
    record.write_text(_DECISIONS, encoding="utf-8")

    with pytest.raises(InvalidVerdictError, match="missing 'source_quote'"):
        validate_objection(_cited(record, quote))


# AC7: absent or schema-invalid verdict, after exactly one re-run, is treated
# as an unresolved blocking objection — fail-closed, never fail-open.


def test_resolve_verdict_valid_passthrough() -> None:
    raw = {"critic": "goal-fit", "objections": []}
    verdict = resolve_verdict(raw, retried=False)
    assert verdict is not None
    assert verdict.has_unresolved_blocking() is False


def test_resolve_verdict_none_before_retry_returns_none() -> None:
    # Not yet retried — caller is expected to re-run once before we force-fail.
    assert resolve_verdict(None, retried=False) is None


def test_resolve_verdict_none_after_retry_forces_unresolved_blocking() -> None:
    verdict = resolve_verdict(None, retried=True)
    assert verdict is not None
    assert verdict.has_unresolved_blocking() is True


def test_resolve_verdict_invalid_after_retry_forces_unresolved_blocking() -> None:
    verdict = resolve_verdict({"objections": []}, retried=True)  # missing "critic"
    assert verdict is not None
    assert verdict.has_unresolved_blocking() is True


def test_resolve_verdict_invalid_before_retry_returns_none() -> None:
    assert resolve_verdict({"objections": []}, retried=False) is None


# AC8: consensus requires zero unresolved objections after <=1 revision cycle


def test_consensus_reached_when_no_unresolved_objections() -> None:
    verdicts = [
        validate_verdict({"critic": "goal-fit", "objections": []}),
        validate_verdict({"critic": "state-fit", "objections": []}),
    ]
    assert consensus_reached(verdicts, revisions=0) is True


def test_consensus_not_reached_with_unresolved_blocking() -> None:
    verdicts = [
        validate_verdict(
            {
                "critic": "goal-fit",
                "objections": [{"description": "x", "blocking": True, "rationale": "y"}],
            }
        ),
    ]
    assert consensus_reached(verdicts, revisions=0) is False


def test_consensus_not_reached_past_revision_cap() -> None:
    verdicts = [validate_verdict({"critic": "goal-fit", "objections": []})]
    assert consensus_reached(verdicts, revisions=2) is False


# AC3: planner actor stamping


def test_planner_actor_format() -> None:
    assert planner_actor("run-123") == "planner:run-123"
