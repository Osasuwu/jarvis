"""Shape of the two code-gate workflows (#1964).

code-gate-verdict.yml is the trusted half: it runs from the default branch and
decides `code-gate`. Its safety is structural — it must never run PR code, never
hold more than read permissions, and never let a PR-controlled string reach a
shell. code-review.yml produces the evidence; its retry and upload settings are
what make a missing or stale review fail closed. Each test walks the parsed YAML,
not the file text.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest
import yaml

WORKFLOWS = Path(__file__).resolve().parents[2] / ".github" / "workflows"
REVIEW = yaml.safe_load((WORKFLOWS / "code-review.yml").read_text(encoding="utf-8"))
VERDICT = yaml.safe_load((WORKFLOWS / "code-gate-verdict.yml").read_text(encoding="utf-8"))

# PyYAML parses the bare key `on` as the boolean True.
ON = True


def _steps(spec: dict) -> list[dict]:
    return [step for job in spec["jobs"].values() for step in job["steps"]]


def _run_bodies(spec: dict) -> list[str]:
    return [step["run"] for step in _steps(spec) if "run" in step]


# --- verdict workflow -----------------------------------------------------


def test_verdict_permissions_are_exactly_three_reads():
    assert VERDICT["permissions"] == {
        "contents": "read",
        "actions": "read",
        "pull-requests": "read",
    }
    for name, job in VERDICT["jobs"].items():
        assert "permissions" not in job, f"job {name} must not widen the workflow permissions"


def test_verdict_never_checks_out_the_pr_head():
    checkouts = [
        s for s in _steps(VERDICT) if str(s.get("uses", "")).startswith("actions/checkout@")
    ]
    assert len(checkouts) == 2  # resolve + verdict, both base-pinned
    for step in checkouts:
        # A schedule's own ref is the default branch; every other trigger names it
        # through the event's repository (#2079).
        assert step["with"]["ref"] == (
            "${{ github.event_name == 'schedule' && github.ref"
            " || github.event.repository.default_branch }}"
        )
        assert step["with"]["persist-credentials"] is False
    sparse = {
        name: step["with"]["sparse-checkout"].split()
        for name, job in VERDICT["jobs"].items()
        for step in job["steps"]
        if str(step.get("uses", "")).startswith("actions/checkout@")
    }
    # verdict reads the gate set from the base's protected list through path_policy (#2067)
    assert sparse == {
        "resolve": [".github/scripts"],
        "verdict": [".github/scripts", "agents", "config"],
    }


def test_verdict_triggers_pull_request_target_review_workflow_run_and_a_daily_schedule():
    triggers = VERDICT[ON]
    assert set(triggers) == {"pull_request_target", "workflow_run", "schedule"}
    # Evidence expires with no event, so a daily sweep re-decides every open PR (#2079).
    ((cron,),) = [tuple(entry.values()) for entry in triggers["schedule"]]
    minute, hour, day_of_month, month, day_of_week = cron.split()
    assert (minute.isdigit(), hour.isdigit()) == (True, True)
    assert (day_of_month, month, day_of_week) == ("*", "*", "*")
    assert triggers["workflow_run"] == {"workflows": ["Code Review"], "types": ["completed"]}
    assert triggers["pull_request_target"]["types"] == [
        "opened",
        "synchronize",
        "reopened",
        "ready_for_review",
        "edited",
    ]


def test_verdict_concurrency_is_per_pr_and_sha_without_cancel():
    assert VERDICT["jobs"]["verdict"]["concurrency"] == {
        "group": "code-gate-${{ matrix.target.pr_number }}-${{ matrix.target.head_sha }}",
        "cancel-in-progress": False,
    }


def test_verdict_runs_once_per_resolved_target():
    """resolve emits one JSON list; the verdict job is a matrix over it, so a
    sweep decides every open PR and an event decides its one (#2079)."""
    resolve, verdict = VERDICT["jobs"]["resolve"], VERDICT["jobs"]["verdict"]
    assert resolve["outputs"] == {"targets": "${{ steps.resolve.outputs.targets }}"}
    assert verdict["if"] == "needs.resolve.outputs.targets != '[]'"
    assert verdict["strategy"] == {
        "fail-fast": False,
        "matrix": {"target": "${{ fromJSON(needs.resolve.outputs.targets) }}"},
    }
    (step,) = [s for s in verdict["steps"] if s.get("name") == "Decide and post code-gate"]
    assert (step["env"]["PR_NUMBER"], step["env"]["HEAD_SHA"]) == (
        "${{ matrix.target.pr_number }}",
        "${{ matrix.target.head_sha }}",
    )


def test_edited_proceeds_only_on_a_base_change_in_both_workflows():
    guard = "github.event.action != 'edited' || github.event.changes.base"
    assert guard in VERDICT["jobs"]["resolve"]["if"]
    assert guard in REVIEW["jobs"]["review"]["if"]


def test_no_run_body_interpolates_pr_controlled_context():
    # PR title, branch names, head repo and dispatch inputs are attacker-chosen;
    # they reach shell only through `env:`.
    pattern = re.compile(
        r"\$\{\{[^}]*(github\.event\.pull_request\.|github\.event\.workflow_run\.|inputs\.|github\.head_ref)"
    )
    for spec in (VERDICT, REVIEW):
        bodies = _run_bodies(spec)
        assert bodies, "expected run bodies to scan"
        for body in bodies:
            assert pattern.search(body) is None, body


def test_only_the_verdict_step_holds_the_app_token():
    holders = [
        s["name"]
        for s in _steps(VERDICT)
        if "GATE_TOKEN" in (s.get("env") or {})
        or "secrets.GATE_APP_PRIVATE_KEY" in str(s.get("with") or {})
    ]
    assert holders == ["Mint osasuwu-ci installation token", "Decide and post code-gate"]
    assert VERDICT["jobs"]["verdict"]["environment"] == "code-gate-verdict"


# --- review workflow ------------------------------------------------------


# Concurrency (a superseded review is cancelled, a body edit is not):
# test_code_review_concurrency_guard.py.


def test_review_run_name_embeds_pr_and_head_sha_for_dispatch_provenance():
    run_name = REVIEW["run-name"]
    assert "format('Code review PR #{0} @ {1}', inputs.pr_number, inputs.head_sha)" in run_name


def test_dispatch_requires_pr_number_and_head_sha():
    inputs = REVIEW[ON]["workflow_dispatch"]["inputs"]
    assert set(inputs) == {"pr_number", "head_sha"}
    assert all(spec["required"] is True for spec in inputs.values())


def test_review_checks_out_base_only_with_no_history():
    (checkout,) = [
        s for s in _steps(REVIEW) if str(s.get("uses", "")).startswith("actions/checkout@")
    ]
    assert checkout["with"] == {
        "ref": "${{ github.event.pull_request.base.sha || github.event.repository.default_branch }}"
    }


def _upload_steps() -> list[dict]:
    return [
        s for s in _steps(REVIEW) if str(s.get("uses", "")).startswith("actions/upload-artifact@")
    ]


EVIDENCE_UPLOAD_NAME = "review-evidence-${{ github.run_attempt }}"


def test_evidence_artifact_is_retained_90_days_one_per_attempt():
    """A re-run attempt uploads its own artifact and cannot overwrite an earlier
    attempt's, so blocking evidence survives a re-run (#2024)."""
    (evidence,) = [s for s in _upload_steps() if s["with"]["name"] == EVIDENCE_UPLOAD_NAME]
    assert evidence["with"]["retention-days"] == 90
    assert evidence["with"]["overwrite"] is False
    assert evidence["with"]["if-no-files-found"] == "error"
    assert "if" not in evidence, "every run uploads evidence, including skipped ones"


def test_evidence_upload_is_the_review_jobs_last_step():
    """The verdict reads an attempt that succeeded but left no listed artifact as
    one whose evidence was deleted, sticky `evidence-unobserved` (#2062). That holds
    only while a successful attempt is one that reached the upload: a step after it
    could fail an attempt that did upload, one before it could not skip it."""
    (job,) = [j for j in REVIEW["jobs"].values() if any(s in _upload_steps() for s in j["steps"])]
    last = job["steps"][-1]
    assert last["with"]["name"] == EVIDENCE_UPLOAD_NAME
    assert "if" not in last


@pytest.mark.parametrize("attempt", ["1", "2", "17"])
def test_uploaded_evidence_name_is_what_the_verdict_reads(attempt):
    """The verdict only reads artifacts whose name fullmatches its pattern; an
    upload name it does not match would read as "missing" for every run. The step
    is found by what it uploads, not by the name under test."""
    (evidence,) = [s for s in _upload_steps() if s["with"]["path"] == "review-evidence.json"]
    name = evidence["with"]["name"].replace("${{ github.run_attempt }}", attempt)
    assert _gate().EVIDENCE_ARTIFACT_NAME.fullmatch(name)


def _gate():
    spec = importlib.util.spec_from_file_location(
        "code_gate_verdict", WORKFLOWS.parent / "scripts" / "code_gate_verdict.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_second_reviewer_attempt_runs_only_when_the_first_findings_are_invalid():
    by_name = {s["name"]: s for s in _steps(REVIEW) if "name" in s}
    first = by_name["Run code review (attempt 1)"]
    second = by_name["Run code review (attempt 2)"]
    assert first["continue-on-error"] is True
    assert by_name["Validate findings (attempt 1)"]["continue-on-error"] is True
    assert second["if"] == "steps.v1.outcome == 'failure'"
    # The retry starts from the sentinel again, not from attempt 1's invalid file.
    names = [s.get("name") for s in _steps(REVIEW)]
    reseed = by_name["Reseed findings file for the retry"]
    assert reseed["if"] == "steps.v1.outcome == 'failure'"
    assert names.index(reseed["name"]) < names.index(second["name"])
    assert "unreviewed" in reseed["run"]


def test_resolve_step_gets_the_default_branch():
    """resolve_run_target picks the listed PR into the default branch (#2024); the
    step reads DEFAULT_BRANCH, so without it every workflow_run resolve fails."""
    (step,) = [s for s in VERDICT["jobs"]["resolve"]["steps"] if s.get("id") == "resolve"]
    assert step["env"]["DEFAULT_BRANCH"] == "${{ github.event.repository.default_branch }}"


def test_resolve_lists_open_prs_with_the_read_only_token_and_no_other_secret():
    """The schedule sweep lists open PRs with the workflow's read-only token, which
    resolve holds on the schedule only; the resolve job holds no environment and no
    other secret, so the App key stays in the verdict job (#2079)."""
    resolve = VERDICT["jobs"]["resolve"]
    (step,) = [s for s in resolve["steps"] if s.get("id") == "resolve"]
    assert step["env"]["GH_TOKEN"] == (
        "${{ github.event_name == 'schedule' && secrets.GITHUB_TOKEN || '' }}"
    )
    assert "environment" not in resolve
    assert set(re.findall(r"secrets\.\w+", str(resolve))) == {"secrets.GITHUB_TOKEN"}


def test_decision_rests_on_the_findings_file_not_on_reviewer_outcome():
    # A run with permission denials but valid findings must pass; a clean run with
    # no findings file must fail. So no step may read the reviewer's outcome or its
    # denial count after validation (#1210, #1229 counted denials — retired).
    steps = _steps(REVIEW)
    final_names = {"Check workspace is clean", "Validate findings", "Stamp review evidence"}
    final = [s for s in steps if s.get("name") in final_names]
    assert [s["name"] for s in final] == [
        "Check workspace is clean",
        "Validate findings",
        "Stamp review evidence",
    ]
    for step in final:
        assert "continue-on-error" not in step
        assert "steps.review1" not in step.get("if", "") and "steps.review2" not in step.get(
            "if", ""
        )
    assert "permission_denials" not in yaml.safe_dump(REVIEW)


SCRUB = "CLAUDE_CODE_SUBPROCESS_ENV_SCRUB"


def test_bubblewrap_is_installed_before_the_reviewer_with_the_scrub_on():
    """#2024: the scrub needs bwrap, which the runner lacks. The install is a plain
    step before the first reviewer attempt — a failure is a named red step, never
    swallowed — and the scrub stays on rather than being switched off to pass."""
    steps = REVIEW["jobs"]["review"]["steps"]
    ids = [s.get("id") for s in steps]
    (bwrap,) = [s for s in steps if s.get("name") == "Install subprocess isolation (bubblewrap)"]
    at = steps.index(bwrap)
    assert ids.index("prepare") < at < ids.index("review1")
    assert bwrap["if"] == "steps.prepare.outputs.skip_reason == ''"
    assert "continue-on-error" not in bwrap
    lines = [line.strip() for line in bwrap["run"].splitlines()]
    assert lines[0] == "set -euo pipefail"
    (install,) = [line for line in lines if "apt-get install" in line]
    assert "bubblewrap" in install.split()
    assert "sudo sysctl -w kernel.apparmor_restrict_unprivileged_userns=0" in lines
    assert lines[-1] == "bwrap --ro-bind / / --unshare-all true"
    assert REVIEW["jobs"]["review"]["env"][SCRUB] == "1"
    overrides = [s.get("name") for s in steps if SCRUB in (s.get("env") or {})]
    assert overrides == []


_GATE_SCRIPT = re.compile(r"(\S+(?:\s+-\S+)*)\s+\.github/scripts/code_gate_verdict\.py\b")


@pytest.mark.parametrize("spec", [REVIEW, VERDICT], ids=["code-review", "code-gate-verdict"])
def test_every_gate_script_call_runs_isolated(spec):
    """`python -I` keeps the script's directory and PYTHON* variables off the import
    path, so a module the reviewer manages to write next to the script is never
    imported by the steps that decide the evidence and the verdict (#2024)."""
    calls = [m for body in _run_bodies(spec) for m in _GATE_SCRIPT.findall(body)]
    assert calls, "no code_gate_verdict.py call found"
    assert calls == ["python -I"] * len(calls)
