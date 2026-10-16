"""Tests for agents.plan_lock — canonicalization/hashing + strict parser
for the ``## Plan`` section (issue #1685).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from agents import plan_lock
from agents.plan_lock import (
    MalformedPlanError,
    canonicalize_plan,
    compute_lock,
    hash_plan,
    parse_plan,
    verify_lock,
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


def test_parse_plan_ignores_step_and_lock_lines_outside_the_section() -> None:
    """A stray '- ...' or 'lock: ...' line in another section of a full
    issue body must not leak into the parsed plan (#1685 review finding:
    parse_plan scanned the whole document instead of scoping to the
    content between '## Plan' and the next heading)."""
    body = (
        "## Acceptance Criteria\n\n"
        "- not a plan step\n"
        "lock: not-the-real-lock\n\n"
        "## Plan\n\n"
        "- step one\n"
        "- step two\n\n"
        "lock: abc123\n\n"
        "## Decisions\n\n"
        "- also not a plan step\n"
        "lock: also-not-the-real-lock\n"
    )
    parsed = parse_plan(body)
    assert parsed.steps == ("step one", "step two")
    assert parsed.lock == "abc123"


# ── strict grammar (D5, #2008) ───────────────────────────────────────────────


def _reason(plan: str) -> str:
    with pytest.raises(MalformedPlanError) as exc_info:
        compute_lock(plan)
    return exc_info.value.reason


def test_sub_heading_inside_plan_is_malformed() -> None:
    assert _reason("## Plan\n\n- step one\n### Detail\n- step two\n") == "sub_heading"


def test_prose_line_inside_plan_is_malformed() -> None:
    assert _reason("## Plan\n\n- step one\nA note between steps.\n- step two\n") == "prose_line"


def test_indented_continuation_line_inside_plan_is_malformed() -> None:
    assert _reason("## Plan\n\n- step one\n  wrapped onto a second line\n") == "prose_line"


def test_second_plan_heading_is_malformed() -> None:
    plan = "## Plan\n\n- step one\n\n## Other\n\n## Plan\n\n- step two\n"
    assert _reason(plan) == "duplicate_heading"


def test_second_lock_line_is_malformed() -> None:
    with pytest.raises(MalformedPlanError) as exc_info:
        parse_plan("## Plan\n\n- step one\n\nlock: abc\nlock: def\n")
    assert exc_info.value.reason == "duplicate_lock_line"


def test_next_top_level_heading_ends_the_plan_section() -> None:
    body = _locked_plan(("step one",)) + "\n# Appendix\n\nfree prose is fine out here\n"
    assert verify_lock(body) is True


def test_prose_in_a_later_section_is_not_part_of_the_plan() -> None:
    body = _locked_plan(("step one",)) + "\n## Decisions\n\nfree prose is fine out here\n"
    assert verify_lock(body) is True


# ── verify_lock (#1687) ──────────────────────────────────────────────────────


def _locked_plan(steps: tuple[str, ...]) -> str:
    """Build a `## Plan` body whose lock value actually matches its steps."""
    steps_text = "\n".join(f"- {s}" for s in steps)
    lock = hash_plan(steps_text)
    return f"## Plan\n\n{steps_text}\n\nlock: {lock}\n"


def test_verify_lock_true_for_matching_hash() -> None:
    body = _locked_plan(("step one", "step two"))
    assert verify_lock(body) is True


def test_verify_lock_false_for_stale_lock_after_step_edit() -> None:
    body = _locked_plan(("step one", "step two"))
    tampered = body.replace("step two", "step THREE")
    assert verify_lock(tampered) is False


def test_verify_lock_false_for_placeholder_lock() -> None:
    assert verify_lock(_LF_PLAN) is False


def test_verify_lock_stable_across_crlf_lf() -> None:
    body = _locked_plan(("step one", "step two"))
    crlf_body = body.replace("\n", "\r\n")
    assert verify_lock(crlf_body) is True


def test_verify_lock_raises_malformed_plan_error_on_bad_plan() -> None:
    with pytest.raises(MalformedPlanError, match="absent_lock_line"):
        verify_lock("## Plan\n\n- step one\n")


# ── publish: python -m agents.plan_lock publish <issue> (#2008) ──────────────

_REPO_ROOT = Path(__file__).resolve().parents[2]

# sha256 of the canonical steps "- new step one\n- шаг два", worked out
# independently of agents.plan_lock.
_NEW_PLAN_LOCK = "ca1eb383e104dd3c13839804897bcf1af23e88a3fea7163901a78afb76e23f55"
_NEW_PLAN = "## Plan\n\n- new step one\n- шаг два\n\nlock: PENDING\n"


class _FakeGh:
    """In-memory stand-in for ``agents.plan_lock._run_gh`` holding one issue body."""

    def __init__(
        self,
        body: str,
        *,
        corrupt_stored_body: bool = False,
        store_instead: str | None = None,
    ) -> None:
        self.body = body
        self.corrupt_stored_body = corrupt_stored_body
        self.store_instead = store_instead
        self.calls: list[list[str]] = []

    def __call__(self, args: list[str]) -> str:
        self.calls.append(list(args))
        if args[:2] == ["issue", "view"]:
            return json.dumps({"body": self.body})
        if args[:2] == ["issue", "edit"]:
            written = Path(args[args.index("--body-file") + 1]).read_bytes().decode("utf-8")
            if self.corrupt_stored_body:
                written = written.replace("- new step one", "- new step ONE")
            self.body = self.store_instead if self.store_instead is not None else written
            return ""
        raise AssertionError(f"unexpected gh call: {args}")

    @property
    def edits(self) -> list[list[str]]:
        return [c for c in self.calls if c[:2] == ["issue", "edit"]]


def _publish(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    fake: _FakeGh,
    plan: str = _NEW_PLAN,
    extra: tuple[str, ...] = (),
) -> int:
    monkeypatch.setattr(plan_lock, "_run_gh", fake)
    plan_file = tmp_path / "plan.md"
    plan_file.write_text(plan, encoding="utf-8")
    return plan_lock.main(["publish", "7", "--plan-file", str(plan_file), *extra])


def test_publish_replaces_the_plan_and_keeps_every_other_byte(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    head = "## Acceptance Criteria\r\n\r\n- AC one — ключ\r\n\r\n"
    tail = "## Decisions\r\n\r\nkept prose\r\n"
    fake = _FakeGh(f"{head}## Plan\r\n\r\n- old step\r\n\r\nlock: deadbeef\r\n\r\n{tail}")

    rc = _publish(monkeypatch, tmp_path, fake)

    assert rc == 0
    new_section = (
        f"## Plan\r\n\r\n- new step one\r\n- шаг два\r\n\r\nlock: {_NEW_PLAN_LOCK}\r\n\r\n"
    )
    assert fake.body == head + new_section + tail
    assert verify_lock(fake.body) is True
    assert capsys.readouterr().out.strip() == _NEW_PLAN_LOCK
    assert len(fake.edits) == 1


def test_publish_appends_a_plan_section_when_the_body_has_none(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = _FakeGh("## Acceptance Criteria\n\n- AC one\n")

    rc = _publish(monkeypatch, tmp_path, fake)

    assert rc == 0
    assert fake.body.startswith("## Acceptance Criteria\n\n- AC one\n\n## Plan\n")
    assert parse_plan(fake.body).steps == ("new step one", "шаг два")
    assert verify_lock(fake.body) is True


def test_publish_refuses_a_body_with_two_plan_headings_and_edits_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = _FakeGh("## Plan\n\n- a\n\nlock: x\n\n## Notes\n\n## Plan\n\n- b\n\nlock: y\n")

    rc = _publish(monkeypatch, tmp_path, fake)

    assert rc == 1
    assert fake.edits == []
    assert "duplicate_heading" in capsys.readouterr().err


def test_publish_with_a_malformed_plan_file_makes_no_gh_call(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = _FakeGh("irrelevant")

    rc = _publish(monkeypatch, tmp_path, fake, plan="## Plan\n\n- one\nA note.\n")

    assert rc == 1
    assert fake.calls == []
    assert "prose_line" in capsys.readouterr().err


def test_publish_fails_when_the_stored_body_does_not_verify(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = _FakeGh("## Acceptance Criteria\n\n- AC one\n", corrupt_stored_body=True)

    rc = _publish(monkeypatch, tmp_path, fake)

    assert rc == 1
    assert "round-trip failed" in capsys.readouterr().err


def test_publish_fails_when_the_stored_body_holds_a_different_valid_plan(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A concurrent edit can leave a plan that verifies yet is not the published one."""
    fake = _FakeGh(
        "## Acceptance Criteria\n\n- AC one\n",
        store_instead=_locked_plan(("someone else's step",)),
    )

    rc = _publish(monkeypatch, tmp_path, fake)

    assert rc == 1
    assert "round-trip failed" in capsys.readouterr().err


def test_publish_reports_a_gh_failure_and_edits_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def failing_gh(args: list[str]) -> str:
        raise plan_lock.GhError("HTTP 404: issue not found")

    monkeypatch.setattr(plan_lock, "_run_gh", failing_gh)
    plan_file = tmp_path / "plan.md"
    plan_file.write_text(_NEW_PLAN, encoding="utf-8")

    rc = plan_lock.main(["publish", "7", "--plan-file", str(plan_file)])

    assert rc == 1
    assert "HTTP 404: issue not found" in capsys.readouterr().err


def test_publish_passes_repo_to_every_gh_call(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = _FakeGh("## Acceptance Criteria\n")

    rc = _publish(monkeypatch, tmp_path, fake, extra=("--repo", "owner/name"))

    assert rc == 0
    assert len(fake.calls) == 3  # view, edit, re-fetch
    assert all(c[c.index("--repo") + 1] == "owner/name" for c in fake.calls)


def test_publish_entry_point_rejects_a_malformed_plan_file(tmp_path: Path) -> None:
    plan_file = tmp_path / "plan.md"
    plan_file.write_text("## Plan\n\n- one\n### Detail\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "-m", "agents.plan_lock", "publish", "7", "--plan-file", str(plan_file)],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "sub_heading" in result.stderr
