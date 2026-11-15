"""Heartbeat for the required checks of open PRs (#2142, failure-class matrix row 8).

A required check that never posts leaves its PR pending forever, and pending reads as "not
failed yet". .github/scripts/required_check_heartbeat.py goes red on a schedule when a required
check has had no result on a PR head for longer than the limit; these tests pin what it calls
stale, against fake API answers and the real workflow file.
"""

import importlib.util
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

from ._github_fake import FakeApi

_root = next(p for p in Path(__file__).resolve().parents if (p / ".github" / "scripts").is_dir())
_spec = importlib.util.spec_from_file_location(
    "required_check_heartbeat", _root / ".github" / "scripts" / "required_check_heartbeat.py"
)
hb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hb)

WORKFLOW_PATH = _root / ".github" / "workflows" / "required-check-heartbeat.yml"

NOW = datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc)
ACTIONS = 15368
CI_APP = 3969106


def _ago(minutes):
    return (
        datetime.fromtimestamp(NOW.timestamp() - minutes * 60, tz=timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _run(name, app=ACTIONS, status="completed", started=90, run_id=1):
    return {
        "id": run_id,
        "name": name,
        "app": {"id": app},
        "status": status,
        "started_at": _ago(started),
    }


def _stale(required, runs=(), statuses=(), committed=90):
    return hb.stale_checks(
        required, list(runs), list(statuses), _ago(committed), NOW, stale_after_min=60
    )


# --- stale_checks: what counts as a result, and since when it is due ------------------------


def test_a_required_check_with_no_run_is_stale_only_once_the_head_is_older_than_the_limit():
    assert _stale({"pytest": ACTIONS}, committed=90) == [("pytest", "no result", 90)]
    assert _stale({"pytest": ACTIONS}, committed=60) == [("pytest", "no result", 60)]
    assert _stale({"pytest": ACTIONS}, committed=59) == []


def test_a_completed_run_from_the_bound_app_is_a_result_whatever_its_conclusion():
    assert _stale({"code-gate": CI_APP}, [_run("code-gate", app=CI_APP)]) == []


def test_a_same_named_run_from_another_app_is_not_a_result():
    # Branch protection bound to an app ignores another app's run of that name.
    assert _stale({"code-gate": CI_APP}, [_run("code-gate", app=ACTIONS)]) == [
        ("code-gate", "no result", 90)
    ]


def test_an_unfinished_run_is_due_from_its_start_not_from_the_commit():
    stuck = _run("pytest", status="in_progress", started=75)
    assert _stale({"pytest": ACTIONS}, [stuck], committed=600) == [("pytest", "in_progress", 75)]
    rerun = _run("pytest", status="queued", started=10)
    assert _stale({"pytest": ACTIONS}, [rerun], committed=600) == []


def test_the_newest_run_decides_so_an_old_result_does_not_hide_a_stuck_rerun():
    old_done = _run("pytest", status="completed", started=300, run_id=1)
    stuck_rerun = _run("pytest", status="queued", started=120, run_id=2)
    assert _stale({"pytest": ACTIONS}, [stuck_rerun, old_done], committed=600) == [
        ("pytest", "queued", 120)
    ]


def test_an_unbound_check_also_accepts_a_commit_status_and_its_newest_state_decides():
    done = {"id": 5, "context": "legacy", "state": "success", "created_at": _ago(80)}
    assert _stale({"legacy": None}, statuses=[done]) == []
    pending = {"id": 6, "context": "legacy", "state": "pending", "created_at": _ago(70)}
    assert _stale({"legacy": None}, statuses=[pending, done]) == [("legacy", "pending", 70)]


def test_a_commit_status_does_not_satisfy_a_check_bound_to_an_app():
    status = {"id": 5, "context": "pytest", "state": "success", "created_at": _ago(80)}
    assert _stale({"pytest": ACTIONS}, statuses=[status]) == [("pytest", "no result", 90)]


# --- scan / main: which PRs, and absence of input is an error -------------------------------


def _branch(**required):
    return {
        "protected": True,
        "protection": {
            "enabled": True,
            "required_status_checks": {
                "contexts": list(required),
                "checks": [{"context": n, "app_id": a} for n, a in required.items()],
            },
        },
    }


def _api(prs, runs_by_sha, *, required=None, mergeable_state="clean", statuses_by_sha=None):
    responses = {
        "repos/o/r/branches/main": _branch(**(required or {"pytest": ACTIONS})),
        "repos/o/r/pulls?state=open&base=main": prs,
    }
    for pr in prs:
        sha = pr["head"]["sha"]
        responses[f"repos/o/r/pulls/{pr['number']}"] = {
            "number": pr["number"],
            "mergeable_state": mergeable_state,
        }
        responses[f"repos/o/r/commits/{sha}/check-runs"] = {"check_runs": runs_by_sha.get(sha, [])}
        responses[f"repos/o/r/commits/{sha}/statuses"] = (statuses_by_sha or {}).get(sha, [])
        responses[f"repos/o/r/commits/{sha}"] = {"commit": {"committer": {"date": _ago(90)}}}
    return FakeApi(responses)


def _pr(number, sha, opened=120):
    return {"number": number, "draft": False, "head": {"sha": sha}, "created_at": _ago(opened)}


def _main(api, monkeypatch):
    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
    monkeypatch.setenv("DEFAULT_BRANCH", "main")
    monkeypatch.setenv("GH_TOKEN", "t")
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    return hb.main(make_client=lambda _token: api, now=lambda: NOW)


def test_main_goes_red_naming_the_pr_and_the_check_that_never_reported(monkeypatch, capsys):
    api = _api([_pr(7, "aaa"), _pr(8, "bbb")], {"bbb": [_run("pytest")]})
    assert _main(api, monkeypatch) == 1
    out = capsys.readouterr().out
    assert "#7 aaa: pytest — no result for 90 min" in out
    assert "#8" not in out


def test_main_is_green_when_every_required_check_reported(monkeypatch, capsys):
    api = _api([_pr(7, "aaa")], {"aaa": [_run("pytest")]})
    assert _main(api, monkeypatch) == 0


def test_a_check_with_no_run_is_due_from_the_pr_opening_when_the_commit_is_older(
    monkeypatch, capsys
):
    # The head commit is 90 min old; a PR opened on it 20 min ago is not yet late.
    assert _main(_api([_pr(7, "aaa", opened=20)], {}), monkeypatch) == 0
    assert _main(_api([_pr(7, "aaa", opened=70)], {}), monkeypatch) == 1
    assert "#7 aaa: pytest — no result for 70 min" in capsys.readouterr().out


def test_an_unbound_required_check_is_satisfied_by_a_commit_status_on_the_head(monkeypatch):
    status = {"id": 5, "context": "legacy", "state": "failure", "created_at": _ago(80)}
    api = _api(
        [_pr(7, "aaa")],
        {"aaa": [_run("pytest")]},
        required={"pytest": ACTIONS, "legacy": None},
        statuses_by_sha={"aaa": [status]},
    )
    assert _main(api, monkeypatch) == 0


def test_a_pr_with_merge_conflicts_is_listed_but_does_not_turn_the_run_red(monkeypatch, capsys):
    # GitHub runs no pull_request workflow on a conflicting PR; the conflict is its own signal.
    api = _api([_pr(7, "aaa")], {}, mergeable_state="dirty")
    assert _main(api, monkeypatch) == 0
    assert "#7 aaa: merge conflict, checks cannot run" in capsys.readouterr().out


@pytest.mark.parametrize(
    "branch",
    [{"protected": False}, {"protected": True, "protection": {"enabled": True}}],
)
def test_no_required_checks_to_read_is_an_error_not_a_green_heartbeat(branch, monkeypatch, capsys):
    api = _api([_pr(7, "aaa")], {})
    api.responses["repos/o/r/branches/main"] = branch
    assert _main(api, monkeypatch) == 2
    assert "no required checks" in capsys.readouterr().err


def test_the_workflow_runs_the_script_on_a_schedule_with_a_read_only_token():
    workflow = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    triggers = workflow[True]  # PyYAML reads the bare `on:` key as True
    assert triggers["schedule"] and "workflow_dispatch" in triggers
    assert set(workflow["permissions"].values()) == {"read"}
    (job,) = workflow["jobs"].values()
    runs = [s["run"] for s in job["steps"] if "run" in s]
    assert runs == ["python3 .github/scripts/required_check_heartbeat.py"]
