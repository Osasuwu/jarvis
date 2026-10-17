"""Tests for the advisory lane-pin drift signal (#2087): .github/scripts/lane_pin_drift.py."""

from __future__ import annotations

import ast
import importlib.util
import re
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
WORKFLOW = WORKFLOWS / "lane-pin-drift.yml"
RISK_TIER_ACTION = REPO_ROOT / ".github" / "actions" / "risk-tier" / "action.yml"

_spec = importlib.util.spec_from_file_location(
    "lane_pin_drift", REPO_ROOT / ".github" / "scripts" / "lane_pin_drift.py"
)
drift = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(drift)

# The code the pin runs (#2087), as a closed list: dropping an entry must go red. The drift
# script itself and its workflow are deliberately absent: the lane never runs them, so an edit
# to them must not read as the pin falling behind.
EXPECTED_PINNED_PATHS = (
    ".github/workflows/lane.yml",
    ".github/workflows/lane-watch.yml",
    ".github/workflows/lane-close.yml",
    ".github/actions/risk-tier/**",
    ".github/scripts/lane_intake.py",
    ".github/scripts/lane_publish.py",
    ".github/scripts/lane_escalation.py",
    ".github/scripts/lane_ledger.py",
    ".github/scripts/risk_tier.py",
    ".github/scripts/github_client.py",
    "agents/__init__.py",
    "agents/plan_lock.py",
    "agents/plan_classifier.py",
    "agents/plan_review_config.py",
    "agents/path_policy.py",
    "config/plan_review.yaml",
)

PIN = "88cee2a53a3a7afe0315e0052ddb4eba66210abb"


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def _commit(repo: Path, path: str, subject: str, content: str | None = None) -> str:
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(subject if content is None else content, encoding="utf-8")
    _git(repo, "add", path)
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", subject)
    return _git(repo, "rev-parse", "HEAD")


def _pin_source(pin: str) -> str:
    return f"      - uses: Osasuwu/jarvis/.github/actions/risk-tier@{pin}\n"


def test_lists_only_later_commits_that_touch_the_pinned_code(tmp_path):
    _git(tmp_path, "init", "-q")
    pin = _commit(tmp_path, ".github/scripts/risk_tier.py", "pinned")
    _commit(tmp_path, "docs/readme.md", "docs only")
    _commit(tmp_path, ".github/scripts/lane_publish.py", "fix lane publish")
    _commit(tmp_path, ".github/scripts/code_gate_verdict.py", "gate script, not pinned")
    _commit(tmp_path, ".github/actions/risk-tier/action.yml", "fix action")
    _commit(tmp_path, ".github/workflows/agent-dispatch.yml", "bump caller")
    _commit(tmp_path, ".github/scripts/lane_pin_drift.py", "drift script, not run by the lane")
    _commit(tmp_path, ".github/workflows/lane-pin-drift.yml", "drift workflow, not run by the lane")
    found = [line.split(" ", 1)[1] for line in drift.missing_commits(tmp_path, pin)]
    assert found == ["fix action", "fix lane publish"]


def test_a_current_pin_reports_nothing_missing(tmp_path):
    _git(tmp_path, "init", "-q")
    _commit(tmp_path, ".github/scripts/risk_tier.py", "one")
    pin = _commit(tmp_path, ".github/workflows/lane.yml", "two")
    _commit(tmp_path, "README.md", "unrelated")
    assert drift.missing_commits(tmp_path, pin) == []


def test_a_stale_pin_is_a_warning_naming_pin_and_commits():
    line = drift.report(PIN, ["abc1234 fix lane publish"])
    assert line.startswith(
        "::warning title=Lane pin is stale::lane pin 88cee2a53a3a is 1 commit(s)"
    )
    assert "abc1234 fix lane publish" in line
    assert not drift.report(PIN, []).startswith("::")


def test_commit_subjects_are_escaped_in_the_annotation():
    # Workflow-command data: `%`, CR and LF must be percent-encoded or the runner decodes them.
    line = drift.report(PIN, ["abc1234 100% done %0A\rx\ny"])
    assert "abc1234 100%25 done %250A%0Dx%0Ay" in line
    assert "\r" not in line and "\n" not in line


def test_reads_the_pin_from_the_risk_tier_job():
    text = (REPO_ROOT / drift.PIN_SOURCE).read_text(encoding="utf-8")
    assert len(drift.pin_from(text)) == 40


def test_main_on_a_stale_pin_warns_writes_the_summary_and_succeeds(tmp_path, capsys, monkeypatch):
    _git(tmp_path, "init", "-q")
    pin = _commit(tmp_path, ".github/scripts/risk_tier.py", "pinned")
    _commit(tmp_path, drift.PIN_SOURCE, "pin it", _pin_source(pin))
    _commit(tmp_path, ".github/scripts/lane_publish.py", "fix lane publish")
    short = _git(tmp_path, "log", "-1", "--format=%h")
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    assert drift.main(tmp_path) == 0
    assert capsys.readouterr().out.startswith(
        f"::warning title=Lane pin is stale::lane pin {pin[:12]} is 1 commit(s) behind main"
    )
    assert summary.read_text(encoding="utf-8") == (
        f"### Lane pin `{pin[:12]}` is stale\n\n- {short} fix lane publish\n"
    )


def test_main_on_a_current_pin_says_so_in_the_summary(tmp_path, capsys, monkeypatch):
    # The latest run must describe the pin as it is now, so a re-pin run reads "current".
    _git(tmp_path, "init", "-q")
    pin = _commit(tmp_path, ".github/scripts/risk_tier.py", "pinned")
    _commit(tmp_path, drift.PIN_SOURCE, "pin it", _pin_source(pin))
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    assert drift.main(tmp_path) == 0
    assert not capsys.readouterr().out.startswith("::")
    assert summary.read_text(encoding="utf-8") == (
        f"### Lane pin `{pin[:12]}` is current\n\nNo later main commit touches the pinned code.\n"
    )


@pytest.mark.parametrize(
    "pin_text",
    [_pin_source("1" * 40), "      - uses: actions/checkout@v7\n"],
    ids=["pin-not-in-history", "no-pin"],
)
def test_main_warns_and_succeeds_when_the_pin_cannot_be_resolved(
    tmp_path, capsys, monkeypatch, pin_text
):
    _git(tmp_path, "init", "-q")
    _commit(tmp_path, drift.PIN_SOURCE, "pin it", pin_text)
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    assert drift.main(tmp_path) == 0
    assert capsys.readouterr().out.startswith(
        "::warning title=Lane pin drift check could not run::"
    )
    assert summary.read_text(encoding="utf-8").startswith(
        "### Lane pin drift check could not run\n\n"
    )


def test_pinned_paths_are_the_code_the_lane_runs():
    assert drift.PINNED_PATHS == EXPECTED_PINNED_PATHS


# --- The pinned code, derived from what the lane workflows and the action execute ----------

_LANE_RUN = re.compile(r"python3 \.lane-src/(\.github/scripts/\w+\.py)")
_ACTION_RUN = re.compile(r"\$GITHUB_ACTION_PATH/\.\./\.\./scripts/(\w+\.py)")
_SIBLING = re.compile(r"\w+\.py")
_JARVIS_PIN = re.compile(r"Osasuwu/jarvis/\.github/[^@\s]+@[0-9a-f]{40}")


def _rel(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _local_imports(path: Path) -> set[str]:
    """Repo files `path` loads: `agents.*` imports, sibling-module imports, and sibling
    `*.py` files named by a string literal (the importlib loads of `github_client.py`)."""
    found = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == "agents":
            found.add("agents/__init__.py")
            if node.module == "agents":
                found |= {f"agents/{alias.name}.py" for alias in node.names}
            else:
                found.add(node.module.replace(".", "/") + ".py")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if path.with_name(alias.name + ".py").is_file():
                    found.add(_rel(path.with_name(alias.name + ".py")))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if _SIBLING.fullmatch(node.value) and path.with_name(node.value).is_file():
                found.add(_rel(path.with_name(node.value)))
    return found


def test_every_file_the_lane_executes_is_pinned_code():
    lane_workflows = {
        _rel(wf) for wf in WORKFLOWS.glob("*.yml") if _LANE_RUN.search(wf.read_text("utf-8"))
    }
    entries = {
        s for wf in lane_workflows for s in _LANE_RUN.findall((REPO_ROOT / wf).read_text("utf-8"))
    }
    entries |= {
        f".github/scripts/{name}"
        for name in _ACTION_RUN.findall(RISK_TIER_ACTION.read_text("utf-8"))
    }
    assert lane_workflows and entries
    executed, todo = set(), list(entries)
    while todo:
        current = todo.pop()
        if current not in executed:
            executed.add(current)
            todo.extend(_local_imports(REPO_ROOT / current))
    missing = sorted((lane_workflows | executed) - set(drift.PINNED_PATHS))
    assert missing == []


def test_workflow_triggers_on_the_pinned_code_and_on_the_pin_itself():
    # A push that only moves the pin (a bump or a rollback) must run the check too, or the
    # latest run keeps describing the old pin. The pin carriers are triggers only: they change
    # in every re-pin commit, so in the pathspec they would read as the pin falling behind.
    carriers = {
        _rel(wf) for wf in WORKFLOWS.glob("*.yml") if _JARVIS_PIN.search(wf.read_text("utf-8"))
    }
    assert drift.PIN_SOURCE in carriers
    assert carriers.isdisjoint(drift.PINNED_PATHS)
    trigger = set(yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))[True]["push"]["paths"])
    assert sorted((set(drift.PINNED_PATHS) | carriers) - trigger) == []


def test_workflow_stays_advisory():
    # Never a PR check (so it cannot be required or hold a merge), read-only token.
    doc = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    assert set(doc[True]) == {"push", "workflow_dispatch"}
    assert doc["permissions"] == {"contents": "read"}


def test_workflow_checks_out_full_history():
    # pin..HEAD needs the pin in the clone; a depth-1 checkout makes every run unresolvable.
    steps = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]["drift"]["steps"]
    checkout = next(s for s in steps if str(s.get("uses", "")).startswith("actions/checkout@"))
    assert checkout["with"]["fetch-depth"] == 0
