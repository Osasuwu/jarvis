"""Tests for agents.critic_verdict — critic verdict schema, fail-closed
resolution, and consensus (issue #1686 AC3, AC6, AC7, AC8).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from agents import critic_verdict
from agents.critic_verdict import (
    InvalidVerdictError,
    consensus_reached,
    planner_actor,
    resolve_verdict,
    validate_objection,
    validate_verdict,
)

_ROOT = Path(__file__).resolve().parents[2]


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


# #2018: the quote check guards only an objection that can still block. The planner answers a
# critic's unconfirmed quote with a `resolution` (planner.md); that objection must not turn the
# verdict blocking through the fail-closed path.


def test_resolved_objection_with_unverifiable_quote_does_not_block(tmp_path: Path) -> None:
    record = tmp_path / "decisions.md"
    record.write_text(_DECISIONS, encoding="utf-8")
    paraphrase = "Lock 4: the always-red set must not include code-gate-verdict.yml."
    raw = {
        "critic": "state-fit",
        "objections": [
            {**_cited(record, paraphrase), "resolution": "quote not in the record; step kept"}
        ],
    }

    verdict = resolve_verdict(raw, retried=True)

    assert verdict is not None
    assert verdict.critic == "state-fit"
    assert verdict.objections[0].resolution == "quote not in the record; step kept"
    assert verdict.has_unresolved_blocking() is False


def test_unresolved_objection_with_unverifiable_quote_still_blocks(tmp_path: Path) -> None:
    record = tmp_path / "decisions.md"
    record.write_text(_DECISIONS, encoding="utf-8")
    paraphrase = "Lock 4: the always-red set must not include code-gate-verdict.yml."
    raw = {"critic": "state-fit", "objections": [_cited(record, paraphrase)]}

    verdict = resolve_verdict(raw, retried=True)

    assert verdict is not None
    assert verdict.critic == "unknown"
    assert verdict.objections[0].description == (
        "verdict resolution failed: schema-invalid verdict: source_quote is not a verbatim "
        f"substring of source_path {str(record)!r}"
    )
    assert verdict.has_unresolved_blocking() is True


# #2018: `python -m agents.critic_verdict check <file>...` — the runtime check /implement §2a.2
# runs on each critic verdict file. Fail-closed like resolve_verdict(retried=True).

_CLEAN = {"critic": "goal-fit", "objections": [{"description": "x", "resolution": "fixed"}]}


def test_check_exits_zero_when_every_verdict_is_clear(tmp_path: Path, capsys) -> None:
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    a.write_text(json.dumps(_CLEAN), encoding="utf-8")
    b.write_text(json.dumps({"critic": "state-fit", "objections": []}), encoding="utf-8")

    assert critic_verdict.main(["check", str(a), str(b)]) == 0
    assert capsys.readouterr().err == ""


@pytest.mark.parametrize(
    ("content", "reason"),
    [
        (None, "missing verdict file"),
        ("{not json", "not valid JSON: Expecting property name enclosed in double quotes: "
                      "line 1 column 2 (char 1)"),
        ("[]", "verdict is not a JSON object"),
        ('{"objections": []}', "schema-invalid verdict: verdict missing 'critic'"),
        (
            '{"critic": "goal-fit", "objections": '
            '[{"description": "unsafe default", "blocking": true, "rationale": "deletes data"}]}',
            "unresolved blocking objection (goal-fit): unsafe default: deletes data",
        ),
    ],
    ids=["missing", "bad-json", "not-object", "schema-invalid", "unresolved-blocking"],
)  # fmt: skip
def test_check_exits_nonzero_and_names_the_bad_file(
    tmp_path: Path, capsys, content: str | None, reason: str
) -> None:
    good, bad = tmp_path / "good.json", tmp_path / "bad.json"
    good.write_text(json.dumps(_CLEAN), encoding="utf-8")
    if content is not None:
        bad.write_text(content, encoding="utf-8")

    assert critic_verdict.main(["check", str(good), str(bad)]) == 1
    assert capsys.readouterr().err == f"{bad}: {reason}\n"


def test_check_reads_verdicts_as_utf8_whatever_the_locale(tmp_path: Path) -> None:
    """A quote with `—` passes with UTF-8 mode off: cp125x on Windows, ASCII under C on Linux."""
    record = tmp_path / "decisions.md"
    record.write_text("- Lock 5: the gate stays red — no bypass.\n", encoding="utf-8")
    verdict = tmp_path / "verdict.json"
    objection = _cited(record, "the gate stays red — no bypass.")
    verdict.write_text(
        json.dumps({"critic": "goal-fit", "objections": [objection]}, ensure_ascii=False),
        encoding="utf-8",
    )
    env = {**os.environ, "PYTHONUTF8": "0", "PYTHONCOERCECLOCALE": "0", "LC_ALL": "C"}

    proc = subprocess.run(
        [sys.executable, "-m", "agents.critic_verdict", "check", str(verdict)],
        cwd=_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="backslashreplace",
        check=False,
    )

    # The quote is verbatim, so the only finding is the blocking objection itself — not a
    # schema failure from a mis-decoded quote.
    assert (proc.returncode, proc.stderr) == (
        1,
        f"{verdict}: unresolved blocking objection (goal-fit): plan contradicts Lock 4: "
        "the record says so\n",
    )


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
