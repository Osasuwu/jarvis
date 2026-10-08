"""Guard for the lane's distribution shape (#2013, D2, D7, F7).

The AFK lane is shared: its logic lives in reusable workflows that other repos call from a
thin caller pinned to a jarvis commit. Nothing errors when that drifts. A literal jarvis
login in a shared file runs fine in jarvis and hands another host the wrong bot; a caller
that forgets a secret fails at run time in the host, not in jarvis's CI; a `secrets: inherit`
hands a host's whole secret store to a pinned callee; a shared job that runs `.lane-src`
code without verifying the pin runs the lane repository's default branch instead.

The shared files are the ones the callers reference, read from the callers rather than
listed here; the callers themselves are a closed set whose membership is the contract.

Convention: docs/reference/ci-guard-meta-tests.md (#326).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
ACTION = REPO_ROOT / ".github" / "actions" / "risk-tier" / "action.yml"

# The jarvis callers of the shared lane; adding a lane trigger means adding it here.
CALLERS = {"agent-dispatch.yml", "lane-red-check-watcher.yml", "lane-ledger-close.yml"}

# A local ref (same commit) or `owner/repo/.github/...@<40-hex sha>` once pinned.
USES = re.compile(
    r"(?P<local>\./|(?P<repo>[\w.-]+/[\w.-]+)/)"
    r"(?P<path>\.github/(?:workflows|actions)/[\w./-]+?)"
    r"(?:@(?P<sha>[0-9a-f]{40}))?"
)


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _all_workflows() -> dict[str, dict]:
    return {p.name: _load(p) for p in sorted(WORKFLOWS.glob("*.yml"))}


def _trigger(workflow: dict) -> dict:
    return workflow.get("on", workflow.get(True))  # PyYAML reads the bare key `on` as True


def _lane_calls() -> list[tuple[str, str, dict]]:
    """Every (caller file, job id, job) whose `uses` names a shared lane workflow."""
    calls = []
    for name, workflow in _all_workflows().items():
        for job_id, job in workflow["jobs"].items():
            match = USES.fullmatch(job.get("uses", ""))
            if match and Path(match["path"]).parent.name == "workflows":
                if Path(match["path"]).name.startswith("lane"):
                    calls.append((name, job_id, job))
    return calls


def _shared_files() -> list[Path]:
    return sorted(
        {WORKFLOWS / Path(USES.fullmatch(j["uses"])["path"]).name for _, _, j in _lane_calls()}
    )


def test_the_callers_found_are_the_closed_set_and_reach_three_shared_workflows():
    calls = _lane_calls()
    assert {name for name, _, _ in calls} == CALLERS
    assert [path.name for path in _shared_files()] == [
        "lane-close.yml",
        "lane-watch.yml",
        "lane.yml",
    ]


def test_no_workflow_hands_a_caller_the_whole_secret_store():
    # `secrets: inherit` passes every secret the host has to the pinned callee; D2 passes by name.
    offenders = [
        f"{name}:{job_id}"
        for name, workflow in _all_workflows().items()
        for job_id, job in workflow["jobs"].items()
        if job.get("secrets") == "inherit"
    ]
    assert offenders == []


def test_shared_files_carry_no_operator_or_host_literal():
    # Comments are not in the parsed tree, so this reads what the runner reads.
    files = [*_shared_files(), ACTION]
    assert len(files) == 4
    offenders = []
    for path in files:
        parsed = json.dumps(_load(path), default=str)
        for what, pattern in (
            ("operator handle", r"osasuwu"),
            ("repository variable", r"\bvars\."),
            ("owner/repo#N reference", r"[\w.-]+/[\w.-]+#\d+"),
        ):
            if re.search(pattern, parsed, re.IGNORECASE):
                offenders.append(f"{path.name}: {what}")
    assert offenders == []


def test_shared_workflows_are_triggered_only_as_callees():
    for path in _shared_files():
        assert list(_trigger(_load(path))) == ["workflow_call"], path.name


def test_no_caller_declares_concurrency():
    # The group is the callee's (F7); a caller group equal to it deadlocks the run.
    offenders = []
    for name, job_id, _ in _lane_calls():
        workflow = _all_workflows()[name]
        if "concurrency" in workflow:
            offenders.append(f"{name}: workflow")
        if "concurrency" in workflow["jobs"][job_id]:
            offenders.append(f"{name}:{job_id}")
    assert offenders == []


def test_each_caller_passes_exactly_the_callees_secrets_and_inputs():
    problems = []
    for name, job_id, job in _lane_calls():
        callee = _trigger(_load(WORKFLOWS / Path(USES.fullmatch(job["uses"])["path"]).name))[
            "workflow_call"
        ]
        declared_secrets = set(callee.get("secrets", {}))
        declared_inputs = callee.get("inputs", {})
        required_inputs = {k for k, v in declared_inputs.items() if v.get("required")}
        passed_secrets = set(job.get("secrets", {}))
        passed_inputs = set(job.get("with", {}))
        if passed_secrets != declared_secrets:
            problems.append(
                f"{name}:{job_id} secrets {sorted(passed_secrets)} != {sorted(declared_secrets)}"
            )
        if not required_inputs <= passed_inputs:
            problems.append(
                f"{name}:{job_id} lacks required inputs {sorted(required_inputs - passed_inputs)}"
            )
        if not passed_inputs <= set(declared_inputs):
            problems.append(
                f"{name}:{job_id} passes unknown inputs {sorted(passed_inputs - set(declared_inputs))}"
            )
    assert problems == []


def test_shared_workflows_reference_only_declared_inputs_and_secrets():
    problems = []
    for path in _shared_files():
        text = path.read_text(encoding="utf-8")
        declared = _trigger(_load(path))["workflow_call"]
        for kind, declared_names in (
            ("inputs", set(declared.get("inputs", {}))),
            ("secrets", set(declared.get("secrets", {})) | {"GITHUB_TOKEN"}),
        ):
            used = set(re.findall(rf"\b{kind}\.([\w-]+)", text))
            if not used <= declared_names:
                problems.append(f"{path.name}: {kind} {sorted(used - declared_names)} undeclared")
    assert problems == []


def test_every_shared_job_that_runs_lane_code_pins_it_before_the_first_use():
    checked = 0
    for path in _shared_files():
        for job_id, job in _load(path)["jobs"].items():
            steps = job["steps"]
            first_use = next(
                (i for i, s in enumerate(steps) if ".lane-src/" in s.get("run", "")), None
            )
            if first_use is None:
                continue
            checked += 1
            where = f"{path.name}:{job_id}"
            checkout = next(
                (
                    s
                    for s in steps[:first_use]
                    if str(s.get("uses", "")).startswith("actions/checkout@")
                    and s.get("with", {}).get("path") == ".lane-src"
                ),
                None,
            )
            assert checkout is not None, f"{where}: no `.lane-src` checkout before its first use"
            assert checkout["with"]["repository"] == "${{ job.workflow_repository }}", where
            assert checkout["with"]["ref"] == "${{ job.workflow_sha }}", where
            assert checkout["with"]["persist-credentials"] is False, where
            verify = [
                s
                for s in steps[:first_use]
                if s.get("env", {}).get("LANE_SHA") == "${{ job.workflow_sha }}"
                and "rev-parse HEAD" in s.get("run", "")
            ]
            assert len(verify) == 1, f"{where}: the pin is not verified before the first use"
            assert steps.index(verify[0]) > steps.index(checkout), where
    # intake, publish, escalate, ledger (lane.yml), watch (lane-watch.yml), finalise (lane-close.yml)
    assert checked == 6


def test_every_jarvis_reference_is_one_pinned_commit_or_a_local_ref():
    shas = set()
    for name, workflow in _all_workflows().items():
        for job_id, job in workflow["jobs"].items():
            refs = [job["uses"]] if "uses" in job else []
            refs += [
                s["uses"]
                for s in job.get("steps", [])
                if str(s.get("uses", "")).startswith(("./", "Osasuwu/jarvis/"))
            ]
            for ref in refs:
                match = USES.fullmatch(ref)
                assert match, (
                    f"{name}:{job_id}: {ref!r} is neither a local ref nor `owner/repo/path@sha`"
                )
                if match["repo"]:
                    assert match["sha"], f"{name}:{job_id}: {ref!r} is not pinned to a commit"
                    shas.add(match["sha"])
    assert len(shas) <= 1, f"jarvis references pin different commits: {sorted(shas)}"


def test_callers_hold_no_job_steps():
    # A caller is `uses:` + `with:` + `secrets:`; steps of its own would be lane logic in the host.
    offenders = [
        f"{name}:{job_id}"
        for name in sorted(CALLERS)
        for job_id, job in _load(WORKFLOWS / name)["jobs"].items()
        if "steps" in job or "runs-on" in job
    ]
    assert offenders == []
