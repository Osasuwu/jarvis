"""Guard for the token boundary of .github/workflows/agent-dispatch.yml (#2007, D4).

The worker reads an attacker-reachable issue body, so it must not hold a token that
can write to the repo, its issues or its PRs: a prompt-injected worker then fails at
GitHub rather than at a prompt rule. The bot PAT lives only in the `publish` job, which
pushes the worker's bundle and runs repo code from a fresh default-branch checkout.

None of this errors when it drifts: a worker given `contents: write` or the PAT still
produces a green run and a merged PR. These tests read the workflow file and pin the
properties the boundary is made of.

Convention: same one-workflow-many-narrow-guards shape as
test_agent_dispatch_automerge_guard.py.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "agent-dispatch.yml"

PAT = "AGENT_DISPATCH_PAT"


@pytest.fixture(scope="module")
def workflow() -> dict:
    return yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))


def _step(job: dict, name: str) -> dict:
    for step in job["steps"]:
        if step.get("name") == name:
            return step
    pytest.fail(f"no step named {name!r}")


@pytest.fixture(scope="module")
def worker_action(workflow: dict) -> dict:
    return _step(workflow["jobs"]["worker"], "Run unattended worker")


class TestWorkerHoldsNoWriteToken:
    def test_worker_permissions_are_read_only(self, workflow):
        permissions = workflow["jobs"]["worker"]["permissions"]
        assert permissions, "an absent `permissions` block inherits the repo's default scopes"
        assert "write" not in set(permissions.values())

    def test_workflow_level_permissions_grant_no_write(self, workflow):
        # A workflow-level grant would reach a job that forgot its own block.
        assert "write" not in set((workflow.get("permissions") or {}).values())

    def test_pat_never_appears_in_the_worker_job(self, workflow):
        assert PAT not in json.dumps(workflow["jobs"]["worker"])

    def test_action_runs_on_the_default_token(self, worker_action):
        assert worker_action["with"]["github_token"] == "${{ secrets.GITHUB_TOKEN }}"

    def test_push_and_pr_creation_are_not_handed_to_the_agent(self, worker_action):
        claude_args = worker_action["with"]["claude_args"]
        allowed = next(line for line in claude_args.splitlines() if "--allowed-tools" in line)
        for verb in (
            "git push",
            "gh pr create",
            "gh issue edit",
            "gh issue comment",
            "gh pr merge",
        ):
            assert verb not in allowed, f"the worker's allowlist grants `{verb}`"
        assert "Bash(git push:*)" in claude_args.split("--disallowed-tools", 1)[1]


class TestPublishJobHoldsThePat:
    @pytest.fixture(scope="class")
    def publish(self, workflow) -> dict:
        return workflow["jobs"]["publish"]

    def test_publish_waits_for_the_worker_and_intake(self, publish):
        assert set(publish["needs"]) == {"intake", "worker"}
        assert "needs.intake.outputs.pass == 'true'" in publish["if"]

    def test_publish_step_runs_the_script_with_the_pat(self, publish):
        step = _step(publish, "Publish the worker's branch")
        assert step["env"]["GH_TOKEN"] == "${{ secrets.AGENT_DISPATCH_PAT }}"
        assert step["run"] == "python3 .github/scripts/lane_publish.py"
        assert (REPO_ROOT / ".github" / "scripts" / "lane_publish.py").is_file()

    def test_publish_job_token_cannot_write(self, publish):
        assert "write" not in set(publish["permissions"].values())

    def test_checkout_is_the_default_branch_without_persisted_credentials(self, publish):
        checkout = next(
            s for s in publish["steps"] if str(s.get("uses", "")).startswith("actions/checkout@")
        )
        assert "ref" not in checkout["with"], "publish must not check out anything the worker chose"
        # A persisted GITHUB_TOKEN would shadow the PAT's credential helper at push time.
        assert checkout["with"]["persist-credentials"] is False

    def test_no_agent_runs_in_the_publish_job(self, publish):
        uses = [str(s.get("uses", "")) for s in publish["steps"]]
        assert not any(u.startswith("anthropics/") for u in uses)


class TestWorkerModelIsPinned:
    def test_claude_args_carries_an_explicit_model(self, worker_action):
        claude_args = worker_action["with"]["claude_args"]
        flags = [line.split() for line in claude_args.splitlines() if line.startswith("--model")]
        assert len(flags) == 1 and len(flags[0]) == 2, "exactly one `--model <id>` line"
        assert flags[0][1].startswith("claude-")


class TestCommentsDescribeTheCurrentToken:
    def test_retired_fine_grained_pat_is_not_described(self):
        text = WORKFLOW_PATH.read_text(encoding="utf-8").lower()
        assert "fine-grained" not in text

    def test_current_token_is_named(self):
        text = WORKFLOW_PATH.read_text(encoding="utf-8")
        assert "osasuwu-bot" in text
        assert "classic `repo` PAT" in text
        assert "#1810" in text
