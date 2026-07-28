"""Canon↔live drift guard for the "Upload review execution log" step (#1300).

The step was added to the live workflow (commit 692d4f7) as a diagnostic
escape hatch for silent no-review runs (#1239): when the action reports
success but posts nothing, the runner-local execution log is the only
evidence of what happened, and without an upload step that evidence dies
with the runner. The canon propagation template
(`scripts/repo_baseline/canon/code-review.yml`) never got the step, so every
repo synced from canon since #1239 shipped without the diagnostic (#1300).

This guard pins the step's presence and load-bearing fields in canon's
attempt-1 and attempt-2 jobs, matching live's `review` job, and pins that the
two canon copies stay byte-identical (same convention as the cleanliness-gate
parity guard).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from scripts.repo_baseline import Manifest, Renderer
from scripts.repo_baseline.canon import load_canon_template

REPO_ROOT = Path(__file__).resolve().parents[2]
LIVE_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "code-review.yml"

STEP_NAME = "Upload review execution log"


def _upload_step(steps: list[dict]) -> dict:
    return next(s for s in steps if s.get("name") == STEP_NAME)


@pytest.fixture(scope="module")
def canon_doc() -> dict:
    template = load_canon_template(".github/workflows/code-review.yml")
    assert template is not None, "canon code-review.yml template must exist"
    manifest = Manifest.from_dict(
        {
            "repo": "Osasuwu/jarvis",
            "profile": "full",
            "required_check_contexts": ["verify-verdict"],
        }
    )
    return yaml.safe_load(Renderer().render(template, manifest))


@pytest.fixture(scope="module")
def live_step() -> dict:
    doc = yaml.safe_load(LIVE_WORKFLOW.read_text(encoding="utf-8"))
    return _upload_step(doc["jobs"]["review"]["steps"])


@pytest.fixture(scope="module")
def canon_attempt1_step(canon_doc) -> dict:
    return _upload_step(canon_doc["jobs"]["attempt-1"]["steps"])


@pytest.fixture(scope="module")
def canon_attempt2_step(canon_doc) -> dict:
    return _upload_step(canon_doc["jobs"]["attempt-2"]["steps"])


class TestArtifactUploadStepParity:
    @pytest.mark.parametrize("job_label", ["canon_attempt1_step", "canon_attempt2_step"])
    def test_step_present_with_live_action_version(self, request, live_step, job_label):
        step = request.getfixturevalue(job_label)
        assert step["uses"] == live_step["uses"], (
            f"{job_label} uses {step['uses']!r}, live uses {live_step['uses']!r} — "
            f"re-snapshot canon from live (#1300)."
        )

    @pytest.mark.parametrize("job_label", ["canon_attempt1_step", "canon_attempt2_step"])
    def test_step_condition_matches_live(self, request, live_step, job_label):
        step = request.getfixturevalue(job_label)
        assert step["if"] == live_step["if"]

    @pytest.mark.parametrize("job_label", ["canon_attempt1_step", "canon_attempt2_step"])
    def test_step_uploads_the_execution_file(self, request, live_step, job_label):
        step = request.getfixturevalue(job_label)
        assert step["with"]["path"] == live_step["with"]["path"]
        assert step["with"]["retention-days"] == live_step["with"]["retention-days"]
        assert step["with"]["if-no-files-found"] == live_step["with"]["if-no-files-found"]

    def test_canon_attempts_are_identical(self, canon_attempt1_step, canon_attempt2_step):
        assert canon_attempt1_step == canon_attempt2_step, (
            "The artifact-upload step must be identical between canon "
            "attempt-1 and attempt-2 — a retry that diagnoses differently is "
            "a hole in the diagnostic."
        )

    def test_step_precedes_cleanliness_gate(self, canon_doc):
        for job_id in ("attempt-1", "attempt-2"):
            steps = canon_doc["jobs"][job_id]["steps"]
            names = [s.get("name") for s in steps]
            assert names.index(STEP_NAME) < names.index("Verify review ran cleanly"), (
                f"{job_id}: upload step must run before the cleanliness gate "
                f"consumes EXEC_FILE, so the artifact captures the same log."
            )
