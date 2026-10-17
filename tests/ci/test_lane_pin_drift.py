"""Tests for the advisory lane-pin drift signal (#2087): .github/scripts/lane_pin_drift.py."""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "lane-pin-drift.yml"

_spec = importlib.util.spec_from_file_location(
    "lane_pin_drift", REPO_ROOT / ".github" / "scripts" / "lane_pin_drift.py"
)
drift = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(drift)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def _commit(repo: Path, path: str, subject: str) -> str:
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(subject, encoding="utf-8")
    _git(repo, "add", path)
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", subject)
    return _git(repo, "rev-parse", "HEAD")


def test_lists_only_later_commits_that_touch_the_pinned_code(tmp_path):
    _git(tmp_path, "init", "-q")
    pin = _commit(tmp_path, ".github/scripts/risk_tier.py", "pinned")
    _commit(tmp_path, "docs/readme.md", "docs only")
    _commit(tmp_path, ".github/scripts/lane_publish.py", "fix lane publish")
    _commit(tmp_path, ".github/scripts/code_gate_verdict.py", "gate script, not pinned")
    _commit(tmp_path, ".github/actions/risk-tier/action.yml", "fix action")
    _commit(tmp_path, ".github/workflows/agent-dispatch.yml", "bump caller")
    found = [line.split(" ", 1)[1] for line in drift.missing_commits(tmp_path, pin)]
    assert found == ["fix action", "fix lane publish"]


def test_a_current_pin_reports_nothing_missing(tmp_path):
    _git(tmp_path, "init", "-q")
    _commit(tmp_path, ".github/scripts/risk_tier.py", "one")
    pin = _commit(tmp_path, ".github/workflows/lane.yml", "two")
    _commit(tmp_path, "README.md", "unrelated")
    assert drift.missing_commits(tmp_path, pin) == []


def test_a_stale_pin_is_a_warning_naming_pin_and_commits():
    pin = "88cee2a53a3a7afe0315e0052ddb4eba66210abb"
    line = drift.report(pin, ["abc1234 fix lane publish"])
    assert line.startswith(
        "::warning title=Lane pin is stale::lane pin 88cee2a53a3a is 1 commit(s)"
    )
    assert "abc1234 fix lane publish" in line
    assert not drift.report(pin, []).startswith("::")


def test_reads_the_pin_from_the_risk_tier_job():
    text = (REPO_ROOT / drift.PIN_SOURCE).read_text(encoding="utf-8")
    assert len(drift.pin_from(text)) == 40


def test_workflow_paths_filter_equals_the_scripts_pinned_paths():
    on = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))[True]
    assert tuple(on["push"]["paths"]) == drift.PINNED_PATHS


def test_workflow_stays_advisory():
    # Never a PR check (so it cannot be required or hold a merge), read-only token.
    doc = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    assert set(doc[True]) == {"push", "workflow_dispatch"}
    assert doc["permissions"] == {"contents": "read"}
