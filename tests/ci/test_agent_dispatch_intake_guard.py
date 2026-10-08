"""Meta-test for the `intake` job's wiring in .github/workflows/lane.yml (#2008).

The intake script imports `agents/plan_lock.py` and reads `LANE_CLASS2_AFK`. Both
are wiring that fails quietly when it drifts:

1. The job checks out only `.github/scripts` and `agents`. Drop `agents` and the
   script dies on its import, so no label ever dispatches; the Actions page shows
   a red intake job and no refusal comment.
2. The step passes the label's applier as `LABEL_SENDER`. Drop it and intake sees an unknown
   labeller and refuses every dispatch as `labeller-unknown`, human or bot.
3. The jarvis caller passes `class2-afk: true` and the step maps it to `LANE_CLASS2_AFK`. Drop it and every `afk:2-plan` issue in
   this repo is refused as `class2-host`, which reads like a plan problem.

Convention: docs/reference/ci-guard-meta-tests.md (#326).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

WORKFLOWS = Path(__file__).resolve().parents[2] / ".github" / "workflows"
WORKFLOW_PATH = WORKFLOWS / "lane.yml"
CALLER_PATH = WORKFLOWS / "agent-dispatch.yml"


@pytest.fixture(scope="module")
def intake_job() -> dict:
    return yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))["jobs"]["intake"]


def _step(job: dict, step_id: str) -> dict:
    return next(step for step in job["steps"] if step.get("id") == step_id)


def test_intake_checks_out_the_script_and_the_plan_lock_module(intake_job):
    checkout = next(step for step in intake_job["steps"] if "checkout" in step.get("uses", ""))
    assert checkout["with"]["sparse-checkout"].split() == [".github/scripts", "agents"]


def test_intake_step_reads_the_class2_flag_from_the_callers_input(intake_job):
    assert _step(intake_job, "intake")["env"]["LANE_CLASS2_AFK"] == "${{ inputs.class2-afk }}"


def test_the_jarvis_caller_sets_the_class2_flag_for_this_repo():
    caller = yaml.safe_load(CALLER_PATH.read_text(encoding="utf-8"))
    assert caller["jobs"]["lane"]["with"]["class2-afk"] is True


def test_intake_step_passes_the_label_applier(intake_job):
    assert _step(intake_job, "intake")["env"]["LABEL_SENDER"] == "${{ github.event.sender.login }}"
