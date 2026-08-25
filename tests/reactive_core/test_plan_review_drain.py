"""Tests for the ex-post plan-review drain gate (#1689).

Covers agents/plan_review_drain.py: unconditional classification (AC1, no
priority:critical carve-out — contrast with test_implement_plan_gate.py's
carve-out tests, which must NOT apply here), plan requirement derivation
(AC1), and the PlannerPort/PlanResult contract shapes (AC2).
"""

from __future__ import annotations

import hashlib

import pytest

from agents.plan_lock import hash_plan
from agents.plan_review_config import (
    Class2Thresholds,
    Class3Criteria,
    ExemptCriteria,
    ModelFloors,
    PlanReviewConfig,
)
from agents.plan_review_drain import (
    PlanResult,
    PlannerPort,
    _PLANNER_ALLOWED_TOOLS,
    class_gate,
    default_run_planner,
    needs_plan,
    pre_spawn_digest_mismatch,
    write_plan_section,
)
from agents.plan_section import replace_plan_section

_CFG = PlanReviewConfig(
    class_2=Class2Thresholds(
        shared_surface_globs=("mcp-memory/*", ".mcp.json"),
        churn_threshold=400,
        min_prod_areas=2,
    ),
    exempt=ExemptCriteria(mechanical_criteria=("docs-only", "typo-fix")),
    class_3=Class3Criteria(mechanical_criteria=("admin-rights-required",)),
    models=ModelFloors(planner="claude-opus-5", critic="claude-sonnet-5"),
)


class _FakeGitHub:
    def __init__(self, issues: dict[int, dict]) -> None:
        self._issues = issues
        self.comments: list[tuple[int, str]] = []

    def get_issue(self, issue_number: int):
        return self._issues.get(issue_number)

    def update_issue(self, issue_number: int, *, body: str):
        issue = dict(self._issues.get(issue_number) or {})
        issue["body"] = body
        self._issues[issue_number] = issue
        return issue

    def create_issue_comment(self, issue_number: int, *, body: str):
        self.comments.append((issue_number, body))
        return {"body": body}


def _plan_body(steps: tuple[str, ...]) -> str:
    steps_text = "\n".join(f"- {s}" for s in steps)
    digest = hashlib.sha256(steps_text.encode("utf-8")).hexdigest()
    return f"## Plan\n{steps_text}\nlock: {digest}\n"


# ── AC1: unconditional classification — no priority:critical carve-out ─────


class TestClassGate:
    def test_class_1_change_does_not_require_a_plan(self):
        row = {"scope_files": ("docs/foo.md",), "churn_lines": 5, "prod_areas": 1}
        assert class_gate(_CFG, row) == 1

    def test_shared_surface_path_trips_class_2(self):
        row = {"scope_files": ("mcp-memory/server.py",), "churn_lines": 5, "prod_areas": 1}
        assert class_gate(_CFG, row) == 2

    def test_priority_critical_label_does_not_skip_classification(self):
        """Contrast with implement_plan_gate.evaluate_trigger: this ex-post
        gate has no carve-out — a class-2 row with a priority:critical-shaped
        label is still class 2, and needs_plan still requires a plan."""
        row = {
            "scope_files": ("mcp-memory/server.py",),
            "churn_lines": 5,
            "prod_areas": 1,
            "labels": ("priority:critical",),
        }
        assert class_gate(_CFG, row) == 2
        github = _FakeGitHub({})
        assert needs_plan(_CFG, row, github) is True


# ── AC1: needs_plan derivation ──────────────────────────────────────────────


class TestNeedsPlan:
    def test_class_1_row_never_needs_a_plan(self):
        row = {"scope_files": ("docs/foo.md",), "churn_lines": 5, "prod_areas": 1}
        github = _FakeGitHub({})
        assert needs_plan(_CFG, row, github) is False

    def test_class_2_row_with_no_digest_needs_a_plan(self):
        row = {
            "scope_files": ("mcp-memory/server.py",),
            "churn_lines": 5,
            "prod_areas": 1,
            "issue_number": 1689,
        }
        github = _FakeGitHub({})
        assert needs_plan(_CFG, row, github) is True

    def test_class_2_row_with_verified_locked_plan_does_not_need_a_plan(self):
        body = _plan_body(("Step one", "Step two"))
        row = {
            "scope_files": ("mcp-memory/server.py",),
            "churn_lines": 5,
            "prod_areas": 1,
            "issue_number": 1689,
            "plan_digest": hash_plan("- Step one\n- Step two"),
        }
        github = _FakeGitHub({1689: {"body": body}})
        assert needs_plan(_CFG, row, github) is False

    # Stored-vs-fresh digest *mismatch* (post-approval issue-body edit) is
    # the pre-spawn fail-closed recheck's job (AC6, plan step 11/12), not
    # needs_plan's (AC1, plan step 3) — needs_plan only asks whether a
    # verified plan exists at all, not whether row["plan_digest"] still
    # matches it byte-for-byte. See TestPreSpawnDigestCheck below.

    def test_class_2_row_with_malformed_plan_section_needs_a_plan(self):
        row = {
            "scope_files": ("mcp-memory/server.py",),
            "churn_lines": 5,
            "prod_areas": 1,
            "issue_number": 1689,
            "plan_digest": "deadbeef",
        }
        github = _FakeGitHub({1689: {"body": "no plan heading here"}})
        assert needs_plan(_CFG, row, github) is True


# ── AC6: pre-spawn fail-closed digest recheck ───────────────────────────────


class TestPreSpawnDigestCheck:
    def test_no_mismatch_when_fresh_body_still_verifies_the_stored_digest(self):
        body = _plan_body(("Step one", "Step two"))
        row = {
            "issue_number": 1689,
            "plan_digest": hash_plan("- Step one\n- Step two"),
        }
        github = _FakeGitHub({1689: {"body": body}})
        assert pre_spawn_digest_mismatch(github, row) is False

    def test_mismatch_when_issue_body_edited_after_the_digest_was_recorded(self):
        original_body = _plan_body(("Step one", "Step two"))
        row = {
            "issue_number": 1689,
            "plan_digest": hash_plan("- Step one\n- Step two"),
        }
        github = _FakeGitHub({1689: {"body": original_body}})
        # Simulate a post-approval edit: a still-locked plan, but different
        # steps than what row["plan_digest"] was recorded against.
        github.update_issue(1689, body=_plan_body(("Step one", "Step two", "Step three")))
        assert pre_spawn_digest_mismatch(github, row) is True

    def test_mismatch_when_fresh_body_lock_line_no_longer_verifies(self):
        row = {"issue_number": 1689, "plan_digest": "deadbeef"}
        github = _FakeGitHub({1689: {"body": "## Plan\n- Step one\nlock: deadbeef\n"}})
        assert pre_spawn_digest_mismatch(github, row) is True

    def test_mismatch_when_fresh_body_has_no_plan_section_at_all(self):
        row = {"issue_number": 1689, "plan_digest": "deadbeef"}
        github = _FakeGitHub({1689: {"body": "## Acceptance Criteria\n- AC one\n"}})
        assert pre_spawn_digest_mismatch(github, row) is True


# ── default_run_planner: argv shape, not runtime behavior ──────────────────


class TestDefaultRunPlannerArgvShape:
    def test_argv_uses_planner_model_floor_and_allowed_tools(self, monkeypatch):
        captured = {}

        def _fake_run(argv, **kwargs):
            captured["argv"] = argv
            captured["kwargs"] = kwargs

            class _Result:
                returncode = 0
                stdout = '{"result": "{\\"plan_text\\": \\"## Plan\\\\n- x\\\\nlock: abc\\\\n\\", \\"resolved\\": true}"}'
                stderr = ""

            return _Result()

        monkeypatch.setattr("agents.plan_review_drain.subprocess.run", _fake_run)
        monkeypatch.setattr("agents.plan_review_drain.default_resolve_binary", lambda: "claude")

        row = {"issue_number": 1689, "issue_title": "Test issue", "issue_body": "body text"}
        result = default_run_planner(row, _CFG)

        argv = captured["argv"]
        assert argv[0] == "claude"
        assert "-p" in argv
        assert "--permission-mode" in argv
        assert argv[argv.index("--permission-mode") + 1] == "acceptEdits"
        assert "--allowedTools" in argv
        tools_start = argv.index("--allowedTools") + 1
        assert tuple(argv[tools_start : tools_start + len(_PLANNER_ALLOWED_TOOLS)]) == (
            _PLANNER_ALLOWED_TOOLS
        )
        assert "--model" in argv
        assert argv[argv.index("--model") + 1] == _CFG.models.planner
        assert isinstance(result, PlanResult)
        assert result.resolved is True
        assert "## Plan" in result.plan_text


# ── replace_plan_section: unrelated-sections preservation ──────────────────


class TestReplacePlanSection:
    def test_replaces_only_the_plan_section_between_headings(self):
        body = (
            "## Acceptance Criteria\n- AC one\n\n"
            "## Plan\n- old step\nlock: oldhash\n\n"
            "## Decisions\n- decided X\n"
        )
        result = replace_plan_section(body, "- new step\nlock: newhash\n")
        assert "## Acceptance Criteria\n- AC one" in result
        assert "## Decisions\n- decided X" in result
        assert "- old step" not in result
        assert "- new step\nlock: newhash" in result

    def test_appends_a_plan_section_when_none_exists(self):
        body = "## Acceptance Criteria\n- AC one\n"
        result = replace_plan_section(body, "- new step\nlock: newhash\n")
        assert "## Acceptance Criteria\n- AC one" in result
        assert "## Plan\n- new step\nlock: newhash\n" in result


# ── write_plan_section: fetch, comment-supersede, replace, write back ──────


class TestWritePlanSection:
    def test_posts_superseded_plan_as_comment_before_overwriting(self):
        body = "## Plan\n- old step\nlock: oldhash\n"
        github = _FakeGitHub({1689: {"body": body}})
        new_plan_text = "- new step\nlock: newhash\n"

        result = write_plan_section(github, 1689, new_plan_text)

        assert github.comments == [(1689, body)]
        assert result == github._issues[1689]["body"]
        assert "- new step\nlock: newhash" in result
        assert "- old step" not in result

    def test_does_not_post_a_comment_when_issue_has_no_prior_plan(self):
        body = "## Acceptance Criteria\n- AC one\n"
        github = _FakeGitHub({1689: {"body": body}})
        new_plan_text = "- new step\nlock: newhash\n"

        write_plan_section(github, 1689, new_plan_text)

        assert github.comments == []


# ── AC2: PlannerPort / PlanResult contract shapes ───────────────────────────


class TestPlannerPortContract:
    def test_plan_result_is_a_frozen_dataclass_with_expected_fields(self):
        result = PlanResult(plan_text="## Plan\n- x\nlock: abc\n", resolved=True, reason=None)
        assert result.plan_text.startswith("## Plan")
        assert result.resolved is True
        with pytest.raises(Exception):
            result.resolved = False  # frozen

    def test_fake_planner_satisfies_the_port_structurally(self):
        class _FakePlanner:
            def run_planner(self, row, config):
                return PlanResult(plan_text="## Plan\n- x\nlock: abc\n", resolved=True)

        assert isinstance(_FakePlanner(), PlannerPort)
