"""Tests for the `waiting-human-review` check (#1892) and its bot-release control (#1999 AP5).

`.github/scripts/waiting_human_review.py` decides the check; the workflow runs it from the
base ref. The check is red exactly when a human look is owed:

  - A pending reviewer or team request     -> red
  - The `waiting-human-review` label,      -> red (solo-developer path: a
    with no request pending                   review cannot be requested from
                                               oneself, so the label carries
                                               the same hold)
  - Neither present, but the bot (or any   -> red, and the label goes back on
    non-human actor) released the hold
  - Neither present, released by a human   -> green

Convention from docs/reference/ci-guard-meta-tests.md: the logic dimension runs the real
`decide`/`main` from the script; the config dimension asserts against the parsed workflow.
"""

from __future__ import annotations

import importlib.util
import json
import urllib.error
from pathlib import Path

import pytest
import yaml

_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = _ROOT / ".github" / "workflows" / "waiting-human-review.yml"

_spec = importlib.util.spec_from_file_location(
    "waiting_human_review", _ROOT / ".github" / "scripts" / "waiting_human_review.py"
)
whr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(whr)

LABEL_NAME = "waiting-human-review"
BOT = "osasuwu-bot"


def _pr(reviewers=(), teams=(), labels=()):
    return {
        "requested_reviewers": [{"login": login} for login in reviewers],
        "requested_teams": [{"slug": slug} for slug in teams],
        "labels": [{"name": name} for name in labels],
    }


def _event(action="synchronize", sender="Osasuwu", label=None):
    event = {"action": action, "sender": {"login": sender}}
    if label:
        event["label"] = {"name": label}
    return event


def _released(actor, what="unlabeled", label=LABEL_NAME):
    item = {"event": what, "actor": {"login": actor}}
    if what == "unlabeled":
        item["label"] = {"name": label}
    return item


def test_pending_reviewer_request_is_red():
    assert whr.decide(_pr(reviewers=["alice"]), [], _event()) == (True, "review-requested", False)


def test_pending_team_request_is_red():
    assert whr.decide(_pr(teams=["core-team"]), [], _event()) == (True, "review-requested", False)


def test_no_request_no_label_is_green():
    assert whr.decide(_pr(), [], _event()) == (False, "clear", False)


def test_label_with_no_request_is_red():
    """#1892 AC4: the solo-developer path — a label of the same name."""
    assert whr.decide(_pr(labels=[LABEL_NAME]), [], _event()) == (True, "label", False)


def test_other_labels_do_not_trigger():
    assert whr.decide(_pr(labels=["priority:high", "area:infrastructure"]), [], _event()) == (
        False,
        "clear",
        False,
    )


def test_label_and_request_both_present_still_names_the_request():
    assert whr.decide(_pr(reviewers=["bob"], labels=[LABEL_NAME]), [], _event()) == (
        True,
        "review-requested",
        False,
    )


def test_bot_removing_the_label_is_red_and_reapplies_it():
    event = _event("unlabeled", sender=BOT, label=LABEL_NAME)
    assert whr.decide(_pr(), [], event, BOT) == (True, "bot-released", True)


def test_human_removing_the_label_is_green():
    event = _event("unlabeled", sender="Osasuwu", label=LABEL_NAME)
    assert whr.decide(_pr(), [_released("Osasuwu")], event, BOT) == (False, "clear", False)


def test_bot_removing_a_review_request_is_red_and_reapplies_the_label():
    event = _event("review_request_removed", sender=BOT)
    assert whr.decide(_pr(), [], event, BOT) == (True, "bot-released", True)


def test_a_bot_app_login_removing_the_label_is_red():
    event = _event("unlabeled", sender="claude[bot]", label=LABEL_NAME)
    assert whr.decide(_pr(), [], event, BOT) == (True, "bot-released", True)


def test_a_release_by_an_unnamed_sender_is_red():
    event = _event("unlabeled", sender="", label=LABEL_NAME)
    assert whr.decide(_pr(), [], event, BOT) == (True, "bot-released", True)


def test_bot_removing_an_unrelated_label_changes_nothing():
    event = _event("unlabeled", sender=BOT, label="priority:high")
    assert whr.decide(_pr(), [], event, BOT) == (False, "clear", False)


def test_a_later_event_does_not_forget_the_bots_release():
    events = [_released("Osasuwu", "unlabeled"), _released(BOT, "unlabeled")]
    assert whr.decide(_pr(), events, _event("synchronize"), BOT) == (True, "bot-released", True)


def test_a_bot_review_request_removal_in_history_stays_red_on_a_later_event():
    events = [_released(BOT, "review_request_removed")]
    assert whr.decide(_pr(), events, _event("synchronize"), BOT) == (True, "bot-released", True)


def test_a_human_release_after_the_bots_clears_it():
    events = [_released(BOT, "unlabeled"), _released("Osasuwu", "unlabeled")]
    assert whr.decide(_pr(), events, _event("synchronize"), BOT) == (False, "clear", False)


def test_is_non_human_names_the_bot_apps_and_the_unknown():
    assert [whr.is_non_human(login, BOT) for login in (BOT, "x[bot]", "", None, "Osasuwu")] == [
        True,
        True,
        True,
        True,
        False,
    ]


# --- main(): the API calls around decide.


def _run_main(monkeypatch, tmp_path, pr, events, event, post_error=None, bot_login=None):
    """Drive `main()` with a fake API; return (exit code, recorded POSTs)."""
    posts = []

    def fake_request(method, path, body=None):
        if method == "POST":
            posts.append((path, body))
            if post_error:
                raise post_error
            return None
        if path == "repos/owner/repo/pulls/7":
            return pr
        if path.startswith("repos/owner/repo/issues/7/events"):
            if isinstance(events, Exception):
                raise events
            return events
        raise AssertionError(f"unexpected {method} {path}")

    path = tmp_path / "event.json"
    path.write_text(json.dumps(event), encoding="utf-8")
    monkeypatch.setattr(whr, "_request", fake_request)
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("PR_NUMBER", "7")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(path))
    monkeypatch.delenv("LANE_BOT_LOGIN", raising=False)
    if bot_login:
        monkeypatch.setenv("LANE_BOT_LOGIN", bot_login)
    return whr.main(), posts


def test_main_reapplies_the_label_after_a_bot_release_and_stays_red(monkeypatch, tmp_path):
    code, posts = _run_main(
        monkeypatch, tmp_path, _pr(), [], _event("unlabeled", sender=BOT, label=LABEL_NAME)
    )
    assert code == 1
    assert posts == [("repos/owner/repo/issues/7/labels", {"labels": [LABEL_NAME]})]


def test_main_stays_red_when_the_label_cannot_be_reapplied(monkeypatch, tmp_path):
    code, posts = _run_main(
        monkeypatch,
        tmp_path,
        _pr(),
        [],
        _event("unlabeled", sender=BOT, label=LABEL_NAME),
        post_error=urllib.error.URLError("denied"),
    )
    assert code == 1
    assert len(posts) == 1


def test_main_is_red_when_the_events_cannot_be_read(monkeypatch, tmp_path):
    code, posts = _run_main(
        monkeypatch, tmp_path, _pr(), urllib.error.URLError("down"), _event("synchronize")
    )
    assert code == 1
    assert posts == []


def test_main_is_red_when_the_release_history_exceeds_the_page_cap(monkeypatch, tmp_path):
    full_page = [{"event": "labeled", "label": {"name": "x"}, "actor": {"login": "Osasuwu"}}] * 100
    code, posts = _run_main(monkeypatch, tmp_path, _pr(), full_page, _event("synchronize"))
    assert code == 1
    assert posts == []


def test_main_takes_the_bot_login_from_the_environment(monkeypatch, tmp_path):
    event = _event("unlabeled", sender="custom-agent", label=LABEL_NAME)
    code, posts = _run_main(monkeypatch, tmp_path, _pr(), [], event, bot_login="custom-agent")
    assert code == 1
    assert posts == [("repos/owner/repo/issues/7/labels", {"labels": [LABEL_NAME]})]


def test_main_is_green_for_a_clear_pr_and_writes_nothing(monkeypatch, tmp_path):
    code, posts = _run_main(monkeypatch, tmp_path, _pr(), [], _event("synchronize"))
    assert code == 0
    assert posts == []


def test_main_is_green_when_a_human_released_the_label(monkeypatch, tmp_path):
    event = _event("unlabeled", sender="Osasuwu", label=LABEL_NAME)
    code, posts = _run_main(monkeypatch, tmp_path, _pr(), [_released("Osasuwu")], event)
    assert code == 0
    assert posts == []


def test_main_is_red_for_a_label_without_touching_it(monkeypatch, tmp_path):
    code, posts = _run_main(monkeypatch, tmp_path, _pr(labels=[LABEL_NAME]), [], _event())
    assert code == 1
    assert posts == []


# --- Config dimension: assert against the parsed workflow, not raw file text.
# The file's comments, step script and log lines all repeat the event and label
# names, so a raw-text search stays green after the trigger itself is removed.


def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))


def _triggers() -> dict:
    doc = _workflow()
    # PyYAML (YAML 1.1) parses the bare key `on` as boolean True.
    return doc["on"] if "on" in doc else doc[True]


def _steps() -> list[dict]:
    return _workflow()["jobs"]["waiting-human-review"]["steps"]


def test_workflow_runs_the_script_from_the_base_ref():
    """#1999 AP5: the bot PAT can push `.github/scripts/**` on its branch, so a PR must not run
    its own copy of the gate; the script is checked out from the base ref."""
    checkout = next(step for step in _steps() if "checkout" in step.get("uses", ""))
    assert checkout["with"]["ref"] == "${{ github.event.pull_request.base.ref }}"
    assert checkout["with"]["sparse-checkout"].split() == [".github/scripts"]
    assert checkout["with"]["persist-credentials"] is False
    run = next(step for step in _steps() if "python3" in step.get("run", ""))
    assert "python3 .github/scripts/waiting_human_review.py" in run["run"]
    assert run["env"]["GITHUB_TOKEN"] == "${{ secrets.GITHUB_TOKEN }}"
    assert run["env"]["PR_NUMBER"] == "${{ github.event.pull_request.number }}"


def test_workflow_token_can_reapply_the_label():
    job = _workflow()["jobs"]["waiting-human-review"]
    assert job["permissions"] == {"contents": "read", "pull-requests": "write"}


def test_workflow_yaml_triggers_on_required_events():
    """#1892 AC2: settles without a re-run needed by hand."""
    triggers = _triggers()
    pr_types = triggers["pull_request"]["types"]
    missing = [
        event
        for event in (
            "opened",
            "synchronize",
            "ready_for_review",
            "review_requested",
            "review_request_removed",
        )
        if event not in pr_types
    ]
    assert not missing, f"missing pull_request trigger type(s): {missing}"
    assert "submitted" in triggers["pull_request_review"]["types"], (
        "missing pull_request_review 'submitted' trigger (review submitted)"
    )


def test_workflow_yaml_triggers_on_label_toggle():
    """#1892 AC2/AC4: the solo-developer path is carried by the label alone, so
    toggling it must itself re-run the check — otherwise a label add/remove
    with no other PR event leaves a stale status until an unrelated re-run,
    breaking AC2's "settles without a re-run needed by hand" promise for that
    path (plan-review tiebreak finding, planner run 1892-planrun-20260924)."""
    pr_types = _triggers()["pull_request"]["types"]
    missing = [event for event in ("labeled", "unlabeled") if event not in pr_types]
    assert not missing, f"missing pull_request trigger type(s): {missing}"


def test_workflow_job_id_matches_check_name():
    """#1892 AC5: the check name must match what #1893's branch-protection ruleset
    will reference, exactly — the job id IS the check name (no jobs.<id>.name
    override), same pattern as require-linked-issue in pr-body-check.yml."""
    jobs = _workflow()["jobs"]
    assert "waiting-human-review" in jobs, "job id must be 'waiting-human-review'"
    assert "name" not in jobs["waiting-human-review"], (
        "a jobs.<id>.name override renames the check the ruleset requires"
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
