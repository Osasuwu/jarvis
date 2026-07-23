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

Second root cause (#1229): this guard originally asserted that the SDK's
`query()` loop is broken on the first `result`-type message by explicit
contract, so EXEC_FILE could never hold more than one `result` and
`[.[] | select(.type == "result")] | last` was merely defensive. Field
evidence on the SAME shared plugin contradicts that source-contract claim:
in redrobot (redrobot#1371, PR #1362, run 28666054188) the action's own
summary reported 11 permission denials while a `last`-selecting guard read 0
and passed the gate green. A trailing `result` reporting zero SHADOWS the
real aggregate. Both repos now aggregate across the WHOLE log — the max of a
recursive `permission_denials_count` scan and the size of the unioned
`permission_denials[]` arrays — so neither a zeroed trailing result nor a
relocated field can mask a denial.

Two halves, per the #326 guard-test convention:
  - Config: the workflow's step reads the correct field/shape and aggregates
    across the whole log, never the nonexistent-alone
    `.permission_denials_count` (#1210) and never `| last` (#1229).
  - Logic: reimplement the extraction rule in Python and assert it against
    synthetic EXEC_FILE fixtures — a clean result, a denied-in-subagent
    result, and a multi-result log whose trailing entry reports zero.
"""

from __future__ import annotations

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
# aggregates across the whole document rather than selecting a single result.


def _walk(node) -> "list[dict]":
    """Every dict reachable from node — mirror of jq's recursive `..`."""
    found: list[dict] = []
    if isinstance(node, dict):
        found.append(node)
        for value in node.values():
            found.extend(_walk(value))
    elif isinstance(node, list):
        for value in node:
            found.extend(_walk(value))
    return found


def select_result(exec_file: list[dict]) -> dict:
    """Legacy `| last` selector — retained ONLY to prove the #1229 shadowing.

    Mirror of the REMOVED line:
        jq -c '[.[] | select(.type == "result")] | last // {}'
    Not used by `gate_passes`; see TestLastSelectorRegression.
    """
    results = [m for m in exec_file if m.get("type") == "result"]
    return results[-1] if results else {}


def compute_is_error(exec_file: list[dict]) -> bool:
    """Mirror of: jq -r 'any(.[] | select(.type == "result"); .is_error == true)'"""
    return any(
        m.get("is_error") is True
        for m in exec_file
        if isinstance(m, dict) and m.get("type") == "result"
    )


def compute_count_field(exec_file: list[dict]) -> int:
    """Mirror of: jq -r '[.. | .permission_denials_count? // empty] | max // 0'

    jq's `// empty` drops only null/false, so a legitimate 0 is kept.
    """
    values = [
        d["permission_denials_count"]
        for d in _walk(exec_file)
        if d.get("permission_denials_count") not in (None, False)
    ]
    return max(values) if values else 0


def compute_count_array(exec_file: list[dict]) -> int:
    """Mirror of: jq -r '[.. | .permission_denials? // empty] | add // [] | length'"""
    total = 0
    for d in _walk(exec_file):
        arr = d.get("permission_denials")
        if arr not in (None, False):
            total += len(arr)
    return total


def compute_denials(exec_file: list[dict]) -> int:
    """Mirror of: denials=$(( count_field > count_array ? count_field : count_array ))"""
    return max(compute_count_field(exec_file), compute_count_array(exec_file))


def compute_denials_buggy(result: dict) -> int:
    """Mirror of the ORIGINAL BUGGY line: jq -r '.permission_denials_count // 0'

    Kept only so the regression tests below can demonstrate the buggy
    extraction silently returns 0 against the real (raw) object shape, even
    when the aggregate on the same log returns a nonzero count.
    """
    return int(result.get("permission_denials_count") or 0)


def gate_passes(exec_file: list[dict]) -> bool:
    """True if the step would exit 0 (no is_error, no denials).

    Encodes the STRICT tripwire (jarvis policy, #1229): any denial fails.
    redrobot runs the blinded-only policy by declared exception — see the
    policy note in scripts/repo_baseline/canon/code-review.yml.
    """
    if compute_is_error(exec_file):
        return False
    if compute_denials(exec_file) > 0:
        return False
    return True


# -- Fixtures mirroring the real raw SDKMessage[] shape ---------------------


def make_denial(tool_name: str = "Bash", tool_input: str = "git blame foo.py") -> dict:
    return {
        "tool_name": tool_name,
        "tool_use_id": "toolu_01example",
        "tool_input": tool_input,
    }


def make_exec_file(
    *, is_error: bool = False, permission_denials: list[dict] | None = None
) -> list[dict]:
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
        assert compute_denials(exec_file) == 0
        assert compute_is_error(exec_file) is False
        assert gate_passes(exec_file) is True

    def test_subagent_denials_are_detected(self):
        # Mirrors the CI incidents (#1176, #1206): subagent Task-tool calls
        # got denied tools, rolling up into the top-level result's
        # permission_denials array with a nonzero count.
        denials = [make_denial("Bash(git blame:*)"), make_denial("Bash(wc:*)")]
        exec_file = make_exec_file(is_error=False, permission_denials=denials)
        assert compute_denials(exec_file) == 2
        assert gate_passes(exec_file) is False

    def test_is_error_alone_fails_the_gate(self):
        exec_file = make_exec_file(is_error=True, permission_denials=[])
        assert gate_passes(exec_file) is False

    def test_is_error_on_any_result_not_just_the_last(self):
        # `any(...)` semantics: an early failing result is not forgiven by a
        # later clean one.
        exec_file = [
            {"type": "result", "is_error": True, "permission_denials": []},
            {"type": "result", "is_error": False, "permission_denials": []},
        ]
        assert compute_is_error(exec_file) is True
        assert gate_passes(exec_file) is False

    def test_missing_permission_denials_key_defaults_to_zero(self):
        # A result object with no permission_denials key at all (rather than
        # an empty array) must still resolve to 0, not error.
        exec_file = [
            {"type": "result", "subtype": "success", "is_error": False},
        ]
        assert compute_denials(exec_file) == 0

    def test_no_result_event_defaults_to_zero(self):
        exec_file = [{"type": "system", "subtype": "init"}]
        assert compute_denials(exec_file) == 0
        assert compute_is_error(exec_file) is False
        assert gate_passes(exec_file) is True

    def test_count_field_is_honored_when_larger_than_array(self):
        # Defends the relocated/absent-array case: if only the synthesized
        # count survives into the log, it must still fail the gate.
        exec_file = [
            {"type": "result", "is_error": False, "permission_denials_count": 7},
        ]
        assert compute_count_array(exec_file) == 0
        assert compute_denials(exec_file) == 7
        assert gate_passes(exec_file) is False

    def test_zero_count_field_is_kept_not_dropped(self):
        # jq's `// empty` drops null/false but NOT 0 — pin that the mirror
        # agrees, so a genuine 0 does not fall through to the `// 0` default
        # by a different route.
        exec_file = [
            {"type": "result", "is_error": False, "permission_denials_count": 0},
        ]
        assert compute_count_field(exec_file) == 0
        assert gate_passes(exec_file) is True


class TestLastSelectorRegression:
    """#1229: a trailing zeroed `result` must not shadow the real aggregate.

    Field evidence: redrobot#1371 / PR #1362 run 28666054188 — the action's
    own summary reported 11 denials while a `| last`-selecting guard read 0
    and passed the gate green.
    """

    def test_trailing_zeroed_result_shadows_the_last_selector(self):
        exec_file = [
            {"type": "system", "subtype": "init"},
            {
                "type": "result",
                "is_error": False,
                "permission_denials": [make_denial(), make_denial(), make_denial()],
            },
            # Trailing result reports a clean run — this is what `| last` sees.
            {"type": "result", "is_error": False, "permission_denials": []},
        ]
        # The removed selector would have read zero and passed the gate...
        assert len(select_result(exec_file).get("permission_denials") or []) == 0
        # ...while the aggregate sees all three and fails closed.
        assert compute_denials(exec_file) == 3
        assert gate_passes(exec_file) is False

    def test_denials_nested_below_top_level_are_still_counted(self):
        # Guards the "relocated field" half: `..` reaches denials that are not
        # hanging directly off a top-level result object.
        exec_file = [
            {"type": "result", "is_error": False, "permission_denials": []},
            {"type": "assistant", "payload": {"nested": {"permission_denials": [make_denial()]}}},
        ]
        assert compute_denials(exec_file) == 1
        assert gate_passes(exec_file) is False


class TestBuggyExtractionRegression:
    """Demonstrates the #1210 bug directly: the old field name silently read
    0 against the real raw object shape, independent of actual denials."""

    def test_buggy_field_name_always_reads_zero_on_raw_shape(self):
        denials = [make_denial(), make_denial(), make_denial()]
        exec_file = make_exec_file(is_error=False, permission_denials=denials)
        result = select_result(exec_file)
        # The real field (aggregate logic) sees the denials...
        assert compute_denials(exec_file) == 3
        # ...but the old buggy field name does not exist on the raw object,
        # so it always silently resolved to 0 regardless of actual denials.
        assert compute_denials_buggy(result) == 0


# -- Workflow wiring ----------------------------------------------------------


def _code_only(run: str) -> str:
    """Drop shell comment lines — antipattern checks target executed code."""
    return "\n".join(line for line in run.splitlines() if not line.lstrip().startswith("#"))


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
        assert (
            "count_array=$(jq -r '[.. | .permission_denials? // empty] | add // [] | length'" in run
        ), (
            "the denials extraction must union the real `.permission_denials` "
            "arrays found anywhere in the log — pins the #1210 fix and the "
            "#1229 whole-log aggregation"
        )

    def test_denials_line_also_reads_the_synthesized_count(self, ran_cleanly_step):
        # #1229: the display-only `permission_denials_count` is not a
        # substitute for the array, but it IS a valid second signal — if the
        # array is relocated or absent, the count still trips the gate. The
        # step takes whichever is larger, so neither field alone can mask.
        run = ran_cleanly_step["run"]
        assert "count_field=$(jq -r '[.. | .permission_denials_count? // empty] | max // 0'" in run
        assert "denials=$(( count_field > count_array ? count_field : count_array ))" in run

    def test_last_selector_is_absent(self, ran_cleanly_step):
        # The regression this file's TestLastSelectorRegression proves: a
        # trailing zeroed `result` shadows the real aggregate (redrobot#1371).
        # Comments are stripped — the step deliberately quotes the buggy
        # selector to explain why it is not used.
        run = _code_only(ran_cleanly_step["run"])
        assert "| last" not in run, (
            "selecting a single `result` object with `| last` is the #1229 "
            "shadowing bug — aggregate across the whole log instead"
        )

    def test_is_error_covers_every_result_object(self, ran_cleanly_step):
        # is_error reads a field that DOES exist on the raw object, but must
        # be evaluated over ALL result objects — an early failure is not
        # forgiven by a later clean one (#1229).
        run = ran_cleanly_step["run"]
        assert "is_error=$(jq -r 'any(.[] | select(.type == \"result\"); .is_error == true)'" in run

    def test_step_gated_on_exec_file_env(self, ran_cleanly_step):
        env = ran_cleanly_step.get("env", {})
        assert "EXEC_FILE" in env
        assert "steps.review.outputs.execution_file" in str(env["EXEC_FILE"])

    def test_denied_tool_calls_listing_matches_the_fixed_field(self, ran_cleanly_step):
        # The "Denied tool calls" listing must enumerate from the same unioned
        # arrays the count is computed from — otherwise the gate can fail with
        # an empty diagnostic listing.
        run = ran_cleanly_step["run"]
        assert "[.. | .permission_denials? // empty] | add // [] | .[]" in run

    def test_strict_tripwire_is_the_jarvis_policy(self, ran_cleanly_step):
        # AC3 (#1229): jarvis's gate is no weaker than the strict tripwire —
        # ANY denial fails, with no "was a fresh verdict posted" escape hatch
        # (that is redrobot's declared exception, decision f96089ee).
        run = ran_cleanly_step["run"]
        assert 'if [ "$denials" -gt 0 ]; then' in run
        assert "STRICT TRIPWIRE" in run
        assert "created_at" not in _code_only(run), (
            "a freshness/blinded-only carve-out would soften jarvis below the "
            "strict tripwire — mandate faaf6671 forbids moving downward"
        )
