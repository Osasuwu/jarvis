"""Meta-test for the `Verify review ran cleanly` step in code-review.yml (#1210).

Root cause: `claude-code-action`'s `writeExecutionFile()` serializes the RAW
`SDKMessage[]` array. The `result`-type object in that raw array has a field
`permission_denials` (an array) — NOT `permission_denials_count`. The latter
name only exists in a separate, display-only console-log sanitizer
(`sanitizeSdkOutput()` in claude-code-action's `run-claude-sdk.ts`) and is
never written to the execution file. The step was reading the nonexistent
`.permission_denials_count` field, which jq's `// 0` silently resolved to 0
regardless of the actual denial count — so the gate always reported "0
permission denials" even when the raw log showed real ones (CI: 14/15/17 raw
vs. 0 parsed on PRs #1176/#1206).

The SDK's `query()` loop is broken on the first `result`-type message by
explicit contract (see run-claude-sdk.ts), so EXEC_FILE never contains more
than one `result` event — the `last` in the workflow's jq is defensive, not
the bug, and multi-result aggregation is not needed.

Two halves, per the #326 guard-test convention:
  - Config: the workflow's step reads the correct field/shape
    (`.permission_denials // [] | length`), not the nonexistent
    `.permission_denials_count`.
  - Logic: reimplement the extraction rule in Python and assert it against
    synthetic EXEC_FILE fixtures — a clean result and a denied-in-subagent
    result — per the issue's acceptance criteria.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
REVIEW_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "code-review.yml"


# -- Decision logic (mirror of the bash/jq in the "Verify review ran cleanly"
# step) --------------------------------------------------------------------
#
# EXEC_FILE is a JSON array of raw SDKMessage objects (claude-code-action's
# writeExecutionFile() does `JSON.stringify(messages, null, 2)`). The step
# selects the last `type == "result"` object (there is structurally only
# ever one) and reads `is_error` and `permission_denials` directly off it.


def select_result(exec_file: list[dict]) -> dict:
    """Mirror of: jq -c '[.[] | select(.type == "result")] | last // {}'"""
    results = [m for m in exec_file if m.get("type") == "result"]
    return results[-1] if results else {}


def compute_is_error(result: dict) -> bool:
    """Mirror of: jq -r '.is_error // false'"""
    return bool(result.get("is_error", False))


def compute_denials(result: dict) -> int:
    """Mirror of the FIXED line: jq -r '(.permission_denials // []) | length'"""
    return len(result.get("permission_denials") or [])


def compute_denials_buggy(result: dict) -> int:
    """Mirror of the ORIGINAL BUGGY line: jq -r '.permission_denials_count // 0'

    Kept only so the regression tests below can demonstrate the buggy
    extraction silently returns 0 against the real (raw) object shape, even
    when `compute_denials` on the same object returns a nonzero count.
    """
    return int(result.get("permission_denials_count") or 0)


def gate_passes(exec_file: list[dict]) -> bool:
    """True if the step would exit 0 (no is_error, no denials)."""
    result = select_result(exec_file)
    if compute_is_error(result):
        return False
    if compute_denials(result) > 0:
        return False
    return True


# -- Fixtures mirroring the real raw SDKMessage[] shape ---------------------


def make_denial(tool_name: str = "Bash", tool_input: str = "git blame foo.py") -> dict:
    return {
        "tool_name": tool_name,
        "tool_use_id": "toolu_01example",
        "tool_input": tool_input,
    }


def make_exec_file(*, is_error: bool = False, permission_denials: list[dict] | None = None) -> list[dict]:
    """A minimal but realistic raw EXEC_FILE: init + assistant turns + one result.

    Denials incurred by subagent (Task-tool) calls are not separately typed
    `result` events — they roll up into this single top-level result's
    `permission_denials` array (the SDK enforces tool permissions centrally
    across the whole session, including nested Task-tool calls).
    """
    return [
        {"type": "system", "subtype": "init", "session_id": "sess-1"},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "reviewing..."}]}},
        {
            "type": "result",
            "subtype": "success",
            "is_error": is_error,
            "duration_ms": 12345,
            "num_turns": 4,
            "permission_denials": permission_denials or [],
        },
    ]


class TestDenialExtractionLogic:
    def test_clean_result_has_zero_denials(self):
        exec_file = make_exec_file(is_error=False, permission_denials=[])
        result = select_result(exec_file)
        assert compute_denials(result) == 0
        assert compute_is_error(result) is False
        assert gate_passes(exec_file) is True

    def test_subagent_denials_are_detected(self):
        # Mirrors the CI incidents (#1176, #1206): subagent Task-tool calls
        # got denied tools, rolling up into the top-level result's
        # permission_denials array with a nonzero count.
        denials = [make_denial("Bash(git blame:*)"), make_denial("Bash(wc:*)")]
        exec_file = make_exec_file(is_error=False, permission_denials=denials)
        result = select_result(exec_file)
        assert compute_denials(result) == 2
        assert gate_passes(exec_file) is False

    def test_is_error_alone_fails_the_gate(self):
        exec_file = make_exec_file(is_error=True, permission_denials=[])
        assert gate_passes(exec_file) is False

    def test_missing_permission_denials_key_defaults_to_zero(self):
        # A result object with no permission_denials key at all (rather than
        # an empty array) must still resolve to 0, not error.
        exec_file = [
            {"type": "result", "subtype": "success", "is_error": False},
        ]
        result = select_result(exec_file)
        assert compute_denials(result) == 0

    def test_no_result_event_defaults_to_empty_object(self):
        exec_file = [{"type": "system", "subtype": "init"}]
        result = select_result(exec_file)
        assert result == {}
        assert compute_denials(result) == 0
        assert compute_is_error(result) is False


class TestBuggyExtractionRegression:
    """Demonstrates the #1210 bug directly: the old field name silently read
    0 against the real raw object shape, independent of actual denials."""

    def test_buggy_field_name_always_reads_zero_on_raw_shape(self):
        denials = [make_denial(), make_denial(), make_denial()]
        exec_file = make_exec_file(is_error=False, permission_denials=denials)
        result = select_result(exec_file)
        # The real field (fixed logic) sees the denials...
        assert compute_denials(result) == 3
        # ...but the old buggy field name does not exist on the raw object,
        # so it always silently resolved to 0 regardless of actual denials.
        assert compute_denials_buggy(result) == 0


# -- Workflow wiring ----------------------------------------------------------


@pytest.fixture(scope="module")
def workflow_text() -> str:
    return REVIEW_WORKFLOW.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def ran_cleanly_step(workflow_text) -> dict:
    workflow = yaml.safe_load(workflow_text)
    steps = workflow["jobs"]["review"]["steps"]
    return next(s for s in steps if s.get("name") == "Verify review ran cleanly")


class TestRanCleanlyStepWiring:
    def test_denials_line_reads_permission_denials_array(self, ran_cleanly_step):
        run = ran_cleanly_step["run"]
        assert re.search(
            r"denials=\$\(jq -r '\(\.permission_denials // \[\]\) \| length'",
            run,
        ), (
            "the denials extraction must read the real `.permission_denials` "
            "array field (via `length`) off the raw execution-file result "
            "object — pins the #1210 fix"
        )

    def test_denials_line_no_longer_reads_nonexistent_count_field(self, ran_cleanly_step):
        run = ran_cleanly_step["run"]
        denials_line = next(
            line for line in run.splitlines() if line.strip().startswith("denials=")
        )
        assert "permission_denials_count" not in denials_line, (
            "`.permission_denials_count` does not exist on the raw "
            "SDKResultMessage written to EXEC_FILE — it is a display-only "
            "field synthesized solely for the action's console log (#1210). "
            "Reading it here always silently resolves to 0 via `// 0`."
        )

    def test_is_error_line_unchanged_and_correct(self, ran_cleanly_step):
        # is_error reads a field that DOES exist on the raw object — grounded
        # confirmation this half of the step was never blind (#1210 scope
        # note: fix does not widen to touch is_error).
        run = ran_cleanly_step["run"]
        assert "is_error=$(jq -r '.is_error // false' <<<\"$result\")" in run

    def test_step_gated_on_exec_file_env(self, ran_cleanly_step):
        env = ran_cleanly_step.get("env", {})
        assert "EXEC_FILE" in env
        assert "steps.review.outputs.execution_file" in str(env["EXEC_FILE"])

    def test_denied_tool_calls_listing_matches_the_fixed_field(self, ran_cleanly_step):
        # The pre-existing "Denied tool calls" listing a few lines below
        # already used the correct field name — confirms the fix aligns the
        # count computation with logic that was already correct elsewhere in
        # the same step.
        run = ran_cleanly_step["run"]
        assert "(.permission_denials // [])[]" in run
