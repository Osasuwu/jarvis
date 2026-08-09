"""Canon↔live drift guard for the code-review verdict logic.

The repo-baseline canon (`scripts/repo_baseline/canon/code-review.yml`) is the
PROPAGATION template pushed to every owned repo. Its `verify-verdict` job must
encode the SAME merge-gate decision logic as the live reference workflow
(`.github/workflows/code-review.yml`), or propagated repos silently get an
outdated gate that mis-merges PRs.

This is exactly what happened pre-this-test: the canon verdict step lagged a
full generation behind live —

  - still `grep -qiE` (case-INsensitive) on the block check vs live `-qE` (#976);
  - still blocked on MINOR (pre-two-gate) vs live's CRITICAL/MAJOR/BLOCKING
    alternation (#988);
  - lacked `export LC_ALL=C` so an emoji severity heading escaped the block
    check (#996);
  - lacked the #993 freshness anchor.

Nothing compared the two, so the drift was invisible. This guard pins parity on
the load-bearing verdict patterns. When the live workflow's verdict logic
evolves, re-snapshot the canon (`scripts/repo_baseline/canon/code-review.yml`)
and this test goes green again — that's the guard working.

Structural note: the canon and live workflows are intentionally NOT byte-equal —
canon is a 3-job retry-wrapper (attempt-1 → attempt-2 → verify-verdict) with
`{{ axis }}` placeholders, live is a single `review` job. So this test compares
the *verdict-decision patterns*, not the whole file.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from scripts.repo_baseline import Manifest, Renderer
from scripts.repo_baseline.canon import load_canon_template

REPO_ROOT = Path(__file__).resolve().parents[2]
LIVE_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "code-review.yml"

# Patterns that carry the merge-gate decision. Each must appear, verbatim, in
# BOTH the live verdict step and the rendered canon verdict step. Drift on any
# one is the class of bug this guard exists to catch.
VERDICT_INVARIANTS = [
    # case-SENSITIVE all-caps block, MINOR dropped (#976/#988), MEDIUM
    # promoted into the blocking set (#1385 follow-up)
    r"grep -qE '^#{1,6}[^[:alnum:]]*(CRITICAL|MAJOR|BLOCKING|MEDIUM)",
    # locale fix so emoji headings are consumed byte-wise (#996)
    "export LC_ALL=C",
    # non-blocking severity pass branch (two-gate, #963)
    r"^#{1,6}[^[:alnum:]]*(MINOR|NITPICK|LOW|INFO|MEDIUM)\b",
    # "Found N issues:" recognized (non-blocking pass under two-gate, #956)
    "Found [0-9]+ issues?:",
    # "Blocking issues — None" APPROVE pass (#962)
    "blocking issues",
    # clean signal, not end-anchored
    r"^No issues found\.",
    # freshness anchor (#993)
    "headRefOid",
    ".commit.committer.date",
    ".created_at >= $head",
    # head-lineage probe (#1228) — "no verdict comment" is NOT an automatic
    # pass. PR #1226 auto-merged un-reviewed because every review run died
    # before posting and the gate read the silence as "plugin skipped".
    "actions/workflows/code-review.yml/runs",
    'conclusion == "failure"',
    "LINEAGE_FAILED",
    "GITHUB_RUN_ID",
    # post-factum carve-out (#1228): a merged/closed PR has nothing left to gate
    'PR_STATE" != "OPEN"',
    # in-flight fail-closed (#1434): a review still running over this PR's
    # commits is NOT "no review needed" — keyed on the status complement so a
    # status GitHub adds later fails closed instead of reading as done
    'select(.status != "completed")',
    "LINEAGE_INFLIGHT",
    "Failing closed (#1434)",
    # structured findings block (#1456): the authoritative machine-readable
    # severity source, checked before the prose ladder — PR #1452 auto-merged
    # MEDIUM findings whose prose took the bare Found-N pass path
    "<!-- *code-review-findings",
    "Failing closed (#1456)",
    'ascii_upcase',
    'select(. == "CRITICAL" or . == "MAJOR" or . == "BLOCKING" or . == "MEDIUM")',
    # explicit LGTM/APPROVE pass branch (#1050), only reachable after the
    # block + findings checks
    r"\bLGTM\b|Verdict:[^\n]*\bAPPROVED?\b",
]

# Anti-patterns: the OLD/buggy shapes. Must appear in NEITHER verdict step.
VERDICT_ANTIPATTERNS = [
    # case-INsensitive block — the #962 false-block bug
    r"grep -qiE '^#{1,6}[^[:alnum:]]*(CRITICAL",
    # MINOR in the block alternation — pre-two-gate (#988)
    "(CRITICAL|MAJOR|MINOR|BLOCKING)",
]


def _verdict_run(run_steps: list[dict]) -> str:
    step = next(s for s in run_steps if s.get("name") == "Verify review verdict")
    return step["run"]


@pytest.fixture(scope="module")
def live_verdict_run() -> str:
    doc = yaml.safe_load(LIVE_WORKFLOW.read_text(encoding="utf-8"))
    return _verdict_run(doc["jobs"]["review"]["steps"])


@pytest.fixture(scope="module")
def live_review_job() -> dict:
    doc = yaml.safe_load(LIVE_WORKFLOW.read_text(encoding="utf-8"))
    return doc["jobs"]["review"]


@pytest.fixture(scope="module")
def canon_verdict_job() -> dict:
    return yaml.safe_load(_rendered_canon())["jobs"]["verify-verdict"]


def _rendered_canon() -> str:
    template = load_canon_template(".github/workflows/code-review.yml")
    assert template is not None, "canon code-review.yml template must exist"
    manifest = Manifest.from_dict(
        {
            "repo": "Osasuwu/jarvis",
            "profile": "full",
            "required_check_contexts": ["verify-verdict"],
        }
    )
    return Renderer().render(template, manifest)


@pytest.fixture(scope="module")
def canon_verdict_run(canon_verdict_job) -> str:
    return _verdict_run(canon_verdict_job["steps"])


@pytest.fixture(scope="module")
def canon_doc() -> dict:
    return yaml.safe_load(_rendered_canon())


class TestCanonExecRanFailClosed:
    """Canon-only structural guard (#1300 rework) for the "ran but silent"
    branch (#1239/#1182/#1195). This is deliberately NOT a VERDICT_INVARIANTS
    literal-text entry: canon's implementation is structurally different from
    live's `[ -n "${EXEC_FILE:-}" ] && [ -f "$EXEC_FILE" ]` file check, because
    EXEC_FILE is a path on the attempt job's own runner and cannot cross into
    the separate verify-verdict job. Canon instead surfaces a boolean job
    output (`execution_ran`) from each attempt job and reads it via `needs.*`.
    """

    @pytest.mark.parametrize("job_id", ["attempt-1", "attempt-2"])
    def test_attempt_job_declares_execution_ran_output(self, canon_doc, job_id):
        outputs = canon_doc["jobs"][job_id].get("outputs") or {}
        assert "execution_ran" in outputs, (
            f"{job_id} must declare an `execution_ran` job output so "
            f"verify-verdict can detect a silent no-review run across the "
            f"job boundary."
        )
        assert "steps.review.outputs.execution_file" in outputs["execution_ran"], (
            f"{job_id}'s execution_ran output must derive from the review "
            f"step's execution_file output."
        )

    def test_verdict_reads_both_attempt_outputs(self, canon_verdict_job):
        env = canon_verdict_job["steps"]
        step = next(s for s in env if s.get("name") == "Verify review verdict")
        step_env = step.get("env") or {}
        assert "needs.attempt-1.outputs.execution_ran" in step_env.get("EXEC_RAN_1", ""), (
            "verify-verdict's env must wire EXEC_RAN_1 from needs.attempt-1.outputs.execution_ran."
        )
        assert "needs.attempt-2.outputs.execution_ran" in step_env.get("EXEC_RAN_2", ""), (
            "verify-verdict's env must wire EXEC_RAN_2 from needs.attempt-2.outputs.execution_ran."
        )

    def test_exec_ran_branch_present_and_fails_closed(self, canon_verdict_run):
        assert '[ "$EXEC_RAN_1" = "true" ] || [ "$EXEC_RAN_2" = "true" ]' in canon_verdict_run, (
            "Missing the ran-but-silent fail-closed check, or it regressed to "
            'a `:-` "prefer the latest" fallback. A job output is always '
            "defined once its job runs, so if attempt-2 fails before its own "
            "review step executes, EXEC_RAN_2 resolves to the literal "
            '"false" (not empty) — a `:-` fallback would never reach '
            'attempt-1\'s real "true" in that case (#1309). Must '
            "OR-aggregate across both attempts instead, matching live's "
            "EXEC_FILE check (#1239/#1182/#1195)."
        )

    def test_exec_ran_branch_is_correctly_ordered(self, canon_verdict_run):
        run = canon_verdict_run
        lineage_exit = run.index("LINEAGE_FAILED", run.index('if [ "$LINEAGE_FAILED" -gt 0 ]'))
        inflight_check = run.index('if [ "$LINEAGE_INFLIGHT" -gt 0 ]')
        exec_ran_check = run.index('[ "$EXEC_RAN_1" = "true" ] || [ "$EXEC_RAN_2" = "true" ]')
        legitimate_skip = run.index("legitimately skipped")
        assert lineage_exit < inflight_check < exec_ran_check < legitimate_skip, (
            "The total==0 disambiguation must run in order: LINEAGE_FAILED "
            "fail-closed exit → LINEAGE_INFLIGHT fail-closed exit (#1434) → "
            "ran-but-silent check → final 'legitimately skipped' pass. Each "
            "later check is only meaningful once the earlier ones ruled out "
            "their state."
        )


class TestCanonVerdictParity:
    @pytest.mark.parametrize("pattern", VERDICT_INVARIANTS)
    def test_invariant_present_in_canon(self, canon_verdict_run, pattern):
        assert pattern in canon_verdict_run, (
            f"Canon verdict step is missing the load-bearing pattern {pattern!r}. "
            f"Re-snapshot scripts/repo_baseline/canon/code-review.yml from the live "
            f".github/workflows/code-review.yml verdict step."
        )

    @pytest.mark.parametrize("pattern", VERDICT_INVARIANTS)
    def test_invariant_present_in_live(self, live_verdict_run, pattern):
        # If live drops a pattern, the invariant list is stale — update both.
        assert pattern in live_verdict_run, (
            f"Live verdict step no longer contains {pattern!r}. If the live "
            f"verdict logic changed intentionally, update VERDICT_INVARIANTS and "
            f"re-snapshot the canon to match."
        )

    @pytest.mark.parametrize("pattern", VERDICT_ANTIPATTERNS)
    def test_antipattern_absent_from_canon(self, canon_verdict_run, pattern):
        assert pattern not in canon_verdict_run, (
            f"Canon verdict step contains the buggy/outdated shape {pattern!r}."
        )

    @pytest.mark.parametrize("pattern", VERDICT_ANTIPATTERNS)
    def test_antipattern_absent_from_live(self, live_verdict_run, pattern):
        assert pattern not in live_verdict_run, (
            f"Live verdict step contains the buggy/outdated shape {pattern!r}."
        )

    def test_canon_block_check_runs_before_pass_checks(self, canon_verdict_run):
        run = canon_verdict_run
        block_at = run.index("(CRITICAL|MAJOR|BLOCKING|MEDIUM)")
        for later in (
            r"^No issues found\.",
            "Found [0-9]+ issues?:",
            "(MINOR|NITPICK|LOW|INFO|MEDIUM)",
            r"\bLGTM\b",
        ):
            assert block_at < run.index(later), (
                f"Block check must precede pass signal {later!r} so no pass can "
                f"shadow a CRITICAL/MAJOR/BLOCKING/MEDIUM heading."
            )

    def test_canon_locale_exported_before_block(self, canon_verdict_run):
        run = canon_verdict_run
        assert run.index("export LC_ALL=C") < run.index("(CRITICAL|MAJOR|BLOCKING|MEDIUM)"), (
            "LC_ALL=C must be exported before the first severity grep (#996)."
        )

    @pytest.mark.parametrize(
        "run_fixture", ["canon_verdict_run", "live_verdict_run"]
    )
    def test_findings_block_precedes_prose_ladder(self, run_fixture, request):
        # #1456: the structured JSON block is the authoritative severity source
        # and must be evaluated before `export LC_ALL=C` (jq needs a UTF-8
        # aware read of the body) and before every prose check that follows it.
        run = request.getfixturevalue(run_fixture)
        # "\nexport ..." anchors to the executed line — both steps *mention*
        # `export LC_ALL=C` in a comment above the findings block, which a bare
        # index() would match first.
        assert run.index("<!-- *code-review-findings") < run.index("\nexport LC_ALL=C"), (
            f"{run_fixture}: the code-review-findings JSON block must run "
            f"before `export LC_ALL=C` (and hence before the whole prose "
            f"ladder) — it is the authoritative severity source (#1456)."
        )

    def test_both_jobs_grant_actions_read(self, canon_verdict_job, live_review_job):
        # The #1228 lineage probe reads the Actions API. Propagating the bash
        # without the permission gives owned repos a step that dies under
        # `set -euo pipefail` on every PR.
        for label, job in (
            ("canon verify-verdict", canon_verdict_job),
            ("live review", live_review_job),
        ):
            assert (job.get("permissions") or {}).get("actions") == "read", (
                f"{label} job must grant `actions: read` for the head-lineage probe (#1228)."
            )

    def test_canon_verdict_fails_closed(self, canon_verdict_run):
        assert canon_verdict_run.strip().endswith("exit 1"), (
            "Unrecognized verdict format must fail closed (exit 1), not fall "
            "through to success (cf. #957)."
        )
