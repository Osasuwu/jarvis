"""Guard for the escalation marker wiring in the AFK lane workflows (#2011).

``lane_escalation.py`` decides what to write; these workflows decide when it runs and what
it holds. None of this errors when it drifts: an ``escalate`` job that loses its ``always()``
silently stops reporting failed runs, a stale ``WORKER_MAX_TURNS`` misnames a turn-limit as
a crash, a watcher bound to a renamed workflow never fires. The tests read the real YAML.

Convention: same one-workflow-many-narrow-guards shape as
test_agent_dispatch_token_boundary_guard.py.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
DISPATCH_PATH = WORKFLOWS / "agent-dispatch.yml"
WATCHER_PATH = WORKFLOWS / "lane-red-check-watcher.yml"
SCRIPT_PATH = REPO_ROOT / ".github" / "scripts" / "lane_escalation.py"
SETUP_DOC = REPO_ROOT / "docs" / "reference" / "github-repo-setup.md"

PAT = "AGENT_DISPATCH_PAT"
RUN_STEP = "Label and comment on an issue that ended without a PR"
ENDING_STEP = "Record how the worker ended"


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def dispatch() -> dict:
    return _load(DISPATCH_PATH)


@pytest.fixture(scope="module")
def watcher() -> dict:
    return _load(WATCHER_PATH)


def _step(job: dict, name: str) -> dict:
    for step in job["steps"]:
        if step.get("name") == name:
            return step
    pytest.fail(f"no step named {name!r}")


def _checkout(job: dict) -> dict:
    return next(s for s in job["steps"] if str(s.get("uses", "")).startswith("actions/checkout@"))


class TestEscalateJob:
    @pytest.fixture(scope="class")
    def escalate(self, dispatch) -> dict:
        return dispatch["jobs"]["escalate"]

    def test_runs_after_every_job_even_when_they_fail_but_not_for_refused_runs(self, escalate):
        assert set(escalate["needs"]) == {"intake", "worker", "publish"}
        assert escalate["if"] == "always() && needs.intake.outputs.pass == 'true'"

    def test_token_cannot_write(self, escalate):
        assert escalate["permissions"] == {"contents": "read"}

    def test_checkout_is_the_default_branch_without_persisted_credentials(self, escalate):
        checkout = _checkout(escalate)
        assert "ref" not in checkout["with"], (
            "escalate must not check out anything the worker chose"
        )
        assert checkout["with"]["persist-credentials"] is False

    def test_no_agent_runs_in_the_job(self, escalate):
        uses = [str(s.get("uses", "")) for s in escalate["steps"]]
        assert not any(u.startswith("anthropics/") for u in uses)

    def test_pat_is_in_the_script_step_only(self, escalate):
        step = _step(escalate, RUN_STEP)
        assert step["env"]["GH_TOKEN"] == "${{ secrets.AGENT_DISPATCH_PAT }}"
        assert step["run"] == "python3 .github/scripts/lane_escalation.py run"
        others = [s for s in escalate["steps"] if s is not step]
        assert PAT not in json.dumps(others)

    def test_the_hand_off_download_may_fail_without_failing_the_job(self, escalate):
        download = next(
            s
            for s in escalate["steps"]
            if str(s.get("uses", "")).startswith("actions/download-artifact@")
        )
        assert download["continue-on-error"] is True
        assert download["with"] == {"name": "lane-out", "path": "lane-out"}

    def test_operator_handle_comes_from_a_repository_variable(self, escalate):
        env = _step(escalate, RUN_STEP)["env"]
        assert env["LANE_OPERATOR"] == "${{ vars.LANE_OPERATOR }}"

    def test_worker_facts_come_from_the_worker_job(self, escalate):
        env = _step(escalate, RUN_STEP)["env"]
        assert env["WORKER_RESULT"] == "${{ needs.worker.result }}"
        assert env["WORKER_RESULT_SUBTYPE"] == "${{ needs.worker.outputs.result_subtype }}"
        assert env["WORKER_NUM_TURNS"] == "${{ needs.worker.outputs.num_turns }}"

    def test_timeout_and_turn_limit_mirror_the_worker_job(self, dispatch):
        env = _step(dispatch["jobs"]["escalate"], RUN_STEP)["env"]
        worker = dispatch["jobs"]["worker"]
        assert env["WORKER_TIMEOUT_MINUTES"] == str(worker["timeout-minutes"])
        claude_args = _step(worker, "Run unattended worker")["with"]["claude_args"]
        (limit,) = re.findall(r"^--max-turns (\d+)$", claude_args, flags=re.MULTILINE)
        assert env["WORKER_MAX_TURNS"] == limit

    def test_the_uncovered_runner_crash_is_stated_in_the_workflow(self):
        text = DISPATCH_PATH.read_text(encoding="utf-8")
        assert "NOT covered: a runner crash or Actions outage" in text
        assert "`no-artifact`" in text

    def test_no_job_but_escalate_and_the_script_steps_name_the_script(self, dispatch):
        users = [
            name
            for name, job in dispatch["jobs"].items()
            if "lane_escalation.py" in json.dumps(job)
        ]
        assert users == ["escalate"]


class TestWorkerEndingRecord:
    @pytest.fixture(scope="class")
    def worker(self, dispatch) -> dict:
        return dispatch["jobs"]["worker"]

    def test_the_agent_step_has_the_id_the_record_reads(self, worker):
        assert _step(worker, "Run unattended worker")["id"] == "claude"

    def test_the_record_runs_even_when_the_worker_failed_and_reads_the_execution_log(self, worker):
        step = _step(worker, ENDING_STEP)
        assert step["if"] == "always()"
        assert step["env"] == {"EXECUTION_FILE": "${{ steps.claude.outputs.execution_file }}"}

    def test_the_record_holds_no_pat_and_runs_no_repo_script(self, worker):
        step = _step(worker, ENDING_STEP)
        assert PAT not in json.dumps(step)
        assert ".github/scripts" not in step["run"] and "python" not in step["run"]
        assert "jq " in step["run"]

    def test_job_outputs_are_the_record_steps_outputs(self, worker):
        assert worker["outputs"] == {
            "result_subtype": "${{ steps.ending.outputs.result_subtype }}",
            "num_turns": "${{ steps.ending.outputs.num_turns }}",
        }
        assert _step(worker, ENDING_STEP)["id"] == "ending"


class TestRedCheckWatcher:
    def test_triggers_on_completed_runs_of_the_workflows_behind_the_watched_checks(self, watcher):
        trigger = watcher[True]["workflow_run"]  # PyYAML reads the key `on` as True
        assert trigger["types"] == ["completed"]
        owners = {
            "pytest": "pytest.yml",
            "gitleaks": "gitleaks.yml",
            "require-linked-issue": "pr-body-check.yml",
            "code-gate": "code-gate-verdict.yml",
        }
        names = [_load(WORKFLOWS / file)["name"] for file in owners.values()]
        assert sorted(trigger["workflows"]) == sorted(names)

    def test_watched_checks_are_the_required_checks_less_the_deliberate_hold(self):
        text = SETUP_DOC.read_text(encoding="utf-8")
        block = text.split("<!-- required-checks-binding -->", 1)[1]
        required = set(json.loads(re.search(r"```json\n(.*?)\n```", block, re.S).group(1)))
        source = SCRIPT_PATH.read_text(encoding="utf-8")
        watched = set(
            re.findall(
                r'"([^"]+)"', re.search(r"^WATCHED_CHECKS = \((.*?)\)$", source, re.M).group(1)
            )
        )
        assert watched == required - {"waiting-human-review", "risk-tier"}

    def test_pushes_to_the_default_branch_are_skipped(self, watcher):
        assert watcher["jobs"]["watch"]["if"] == "github.event.workflow_run.event != 'push'"

    def test_passes_are_queued_not_cancelled(self, watcher):
        concurrency = watcher["concurrency"]
        assert concurrency["cancel-in-progress"] is False
        assert "github.repository" in concurrency["group"]
        assert "github.run_id" not in concurrency["group"]

    def test_job_token_cannot_write(self, watcher):
        assert watcher["jobs"]["watch"]["permissions"] == {"contents": "read"}

    def test_checkout_is_the_default_branch_without_persisted_credentials(self, watcher):
        checkout = _checkout(watcher["jobs"]["watch"])
        assert "ref" not in checkout["with"]
        assert checkout["with"]["persist-credentials"] is False

    def test_pat_and_operator_wiring(self, watcher):
        (run_step,) = [s for s in watcher["jobs"]["watch"]["steps"] if "run" in s]
        assert run_step["run"] == "python3 .github/scripts/lane_escalation.py watch"
        assert run_step["env"] == {
            "GH_TOKEN": "${{ secrets.AGENT_DISPATCH_PAT }}",
            "GH_REPO": "${{ github.repository }}",
            "LANE_OPERATOR": "${{ vars.LANE_OPERATOR }}",
        }

    def test_the_waiting_human_review_exclusion_is_explained_in_the_workflow(self):
        text = WATCHER_PATH.read_text(encoding="utf-8")
        assert "`waiting-human-review` is\n# left out on purpose" in text
