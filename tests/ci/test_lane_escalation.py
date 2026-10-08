"""The escalation marker of the AFK lane (.github/scripts/lane_escalation.py, #2011).

A run that passes intake and ends without a PR must leave `needs-human` and one comment
that @-mentions the operator; a red required check on an open lane PR does the same on the
PR. What must hold: no write when a PR exists, exactly one comment per run (and per check
and head SHA), nothing the worker wrote becomes live markdown, and no assignee or body
edit ever. `gh` is recorded, not run.
"""

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

_root = next(p for p in Path(__file__).resolve().parents if (p / ".github" / "scripts").is_dir())


def _load(name):
    spec = importlib.util.spec_from_file_location(
        name, _root / ".github" / "scripts" / f"{name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


lane_escalation = _load("lane_escalation")
lane_intake = _load("lane_intake")

REPO = "Osasuwu/jarvis"
SHA = "a" * 40
WRITES = (("issue", "edit"), ("issue", "comment"), ("pr", "edit"), ("pr", "comment"))


class FakeGh:
    """Serves the reads a test configures and records every write; an unknown call fails."""

    def __init__(self):
        self.branch_prs = []
        self.issue_labels = ["afk:1-auto", "status:in-progress"]
        self.comments = {}
        self.jobs = None
        self.open_prs = []
        self.check_runs = {}
        self.review_runs = []
        self.dispatched_runs = []
        self.reads = []
        self.writes = []

    def __call__(self, *args):
        if args[:2] in WRITES:
            self.writes.append(args)
            return ""
        self.reads.append(args)
        if args[:2] == ("pr", "list") and "--head" in args:
            return json.dumps(self.branch_prs)
        if args[:2] == ("pr", "list"):
            return json.dumps(self.open_prs)
        if args[:2] == ("issue", "view"):
            return json.dumps([{"name": n} for n in self.issue_labels])
        path = next((a for a in args if a.startswith("repos/")), "")
        if "/comments" in path:
            number = int(path.split("/issues/")[1].split("/")[0])
            return "\n".join(json.dumps(c) for c in self.comments.get(number, []))
        if "/actions/runs/" in path and path.endswith("/jobs"):
            if self.jobs is None:
                raise subprocess.CalledProcessError(1, "gh")
            return self.jobs
        if "/check-runs" in path:
            sha = path.split("/commits/")[1].split("/")[0]
            return "\n".join(json.dumps(c) for c in self.check_runs.get(sha, []))
        if "code-review.yml/runs" in path:
            runs = self.dispatched_runs if "event=workflow_dispatch" in path else self.review_runs
            return "\n".join(json.dumps(r) for r in runs)
        raise AssertionError(f"unexpected gh call: {args}")


@pytest.fixture
def gh(monkeypatch):
    fake = FakeGh()
    monkeypatch.setattr(lane_escalation, "gh", fake)
    return fake


def _env(**over):
    env = {
        "GH_REPO": REPO,
        "ISSUE_NUMBER": "2011",
        "RUN_ID": "9001",
        "LANE_OPERATOR": "Osasuwu",
        "LANE_BOT_LOGIN": "osasuwu-bot",
        "WORKER_RESULT": "success",
        "WORKER_RESULT_SUBTYPE": "",
        "WORKER_NUM_TURNS": "",
        "WORKER_TIMEOUT_MINUTES": "45",
        "WORKER_MAX_TURNS": "100",
    }
    env.update(over)
    return env


def _out(tmp_path, escalation=None, bundle=False):
    out = tmp_path / "lane-out"
    out.mkdir(exist_ok=True)
    if escalation is not None:
        (out / "escalation.md").write_text(escalation, encoding="utf-8")
    if bundle:
        (out / "work.bundle").write_bytes(b"x")
    return out


def _comment_body(gh):
    (call,) = [w for w in gh.writes if w[:2] == ("issue", "comment")]
    return call[call.index("--body") + 1]


# --- cause classification -------------------------------------------------------------

_BASE = {
    "escalation": None,
    "worker_result": "success",
    "subtype": None,
    "num_turns": None,
    "worker_minutes": None,
    "timeout_minutes": 45,
    "max_turns": 100,
    "has_bundle": False,
}


@pytest.mark.parametrize(
    ("over", "cause"),
    [
        ({"escalation": "blocked", "worker_result": "success"}, "escalated"),
        (
            {"escalation": "blocked", "worker_minutes": 45.0, "worker_result": "failure"},
            "escalated",
        ),
        ({"worker_result": "cancelled", "worker_minutes": 45.1}, "timeout"),
        ({"worker_result": "cancelled", "worker_minutes": 44.9}, "cancelled"),
        ({"worker_result": "failure", "subtype": "error_max_turns"}, "max-turns"),
        ({"worker_result": "failure", "num_turns": 101}, "max-turns"),
        ({"worker_result": "failure", "num_turns": 100}, "crash"),
        ({"worker_result": "failure", "subtype": "error_during_execution"}, "crash"),
        ({"worker_result": "skipped"}, "crash"),
        ({"worker_result": "success", "has_bundle": True}, "publish-failed"),
        ({"worker_result": "success"}, "no-output"),
    ],
)
def test_cause_of_a_run_that_ended_without_a_pr(over, cause):
    assert lane_escalation.classify(**{**_BASE, **over}) == cause


def test_worker_outputs_outside_the_expected_shape_read_as_absent():
    assert lane_escalation.worker_outputs("error_max_turns", "101") == ("error_max_turns", 101)
    assert lane_escalation.worker_outputs("x; rm -rf", "1e9") == (None, None)
    assert lane_escalation.worker_outputs("", "") == (None, None)


# --- the operator handle --------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "handle"),
    [
        ("Osasuwu", "Osasuwu"),
        ("@Osasuwu", "Osasuwu"),
        (" a-b ", "a-b"),
        ("", None),
        (None, None),
        ("two words", None),
        ("-leading", None),
        ("double--dash", None),
        ("a" * 40, None),
        ("name\n@other", None),
    ],
)
def test_operator_handle_is_a_github_login_or_nothing(raw, handle):
    assert lane_escalation.operator_handle(raw) == handle


# --- quoting the worker's text --------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "ticks"),
    [("no backticks", 3), ("a `b` c", 3), ("```py\ncode\n```", 4), ("x `````` y", 7)],
)
def test_fence_is_longer_than_any_backtick_run_inside(text, ticks):
    fenced = lane_escalation.fence(text)
    assert fenced == f"{'`' * ticks}\n{text}\n{'`' * ticks}"


# --- run: the issue side --------------------------------------------------------------


def test_run_with_a_pr_on_the_run_branch_writes_nothing(gh, tmp_path):
    gh.branch_prs = [{"number": 77}]
    assert lane_escalation.escalate(_env(), _out(tmp_path, escalation="blocked")) is None
    assert gh.writes == []
    assert ("pr", "list", "--repo", REPO, "--head", "claude/issue-2011-9001") == gh.reads[0][:6]


def test_escalation_labels_the_issue_and_posts_one_comment(gh, tmp_path):
    cause = lane_escalation.escalate(_env(), _out(tmp_path, escalation="Scope is ambiguous.\n"))
    assert cause == "escalated"
    assert gh.writes[0] == (
        "issue",
        "edit",
        "2011",
        "--repo",
        REPO,
        "--add-label",
        "needs-human",
        "--remove-label",
        "status:in-progress",
    )
    assert len(gh.writes) == 2
    assert _comment_body(gh) == (
        "<!-- lane-escalation run=9001 -->\n"
        "@Osasuwu run [9001](https://github.com/Osasuwu/jarvis/actions/runs/9001) ended without"
        " a PR: the worker stopped and escalated; its note is quoted below.\n"
        "\n"
        "The worker's `escalation.md`, quoted (untrusted):\n"
        "\n"
        "```\n"
        "Scope is ambiguous.\n"
        "```\n"
        "\n"
        "Decide, then re-dispatch: remove `needs-human` and re-apply `agent:dispatch`."
        " Cause: `escalated`.\n"
    )


def test_status_in_progress_is_dropped_only_when_present(gh, tmp_path):
    gh.issue_labels = ["afk:1-auto"]
    lane_escalation.escalate(_env(), _out(tmp_path, escalation="x"))
    assert gh.writes[0] == (
        "issue",
        "edit",
        "2011",
        "--repo",
        REPO,
        "--add-label",
        "needs-human",
    )


def test_a_crash_without_a_note_names_the_cause(gh, tmp_path):
    cause = lane_escalation.escalate(_env(WORKER_RESULT="failure"), _out(tmp_path))
    assert cause == "crash"
    body = _comment_body(gh)
    assert "ended without a PR: the worker job ended `failure` before it finished." in body
    assert "quoted" not in body


def test_a_job_that_ran_its_full_timeout_is_reported_as_a_timeout(gh, tmp_path):
    gh.jobs = "2026-10-08T10:00:00Z\t2026-10-08T10:45:03Z"
    cause = lane_escalation.escalate(_env(WORKER_RESULT="cancelled"), _out(tmp_path))
    assert cause == "timeout"
    assert "the worker hit its 45-minute job timeout." in _comment_body(gh)


def test_an_unreadable_jobs_api_falls_back_to_the_worker_result(gh, tmp_path):
    gh.jobs = None
    assert lane_escalation.escalate(_env(WORKER_RESULT="cancelled"), _out(tmp_path)) == "cancelled"


def test_turn_limit_is_reported_from_the_workers_ending_record(gh, tmp_path):
    env = _env(WORKER_RESULT="failure", WORKER_RESULT_SUBTYPE="error_max_turns")
    assert lane_escalation.escalate(env, _out(tmp_path)) == "max-turns"
    assert "the worker ran out of turns (limit 100)." in _comment_body(gh)


def test_a_rerun_of_the_job_posts_no_second_comment(gh, tmp_path):
    marker = "<!-- lane-escalation run=9001 -->\nearlier body"
    gh.comments = {2011: [{"user": "osasuwu-bot", "body": marker}]}
    lane_escalation.escalate(_env(), _out(tmp_path, escalation="x"))
    assert [w[:2] for w in gh.writes] == [("issue", "edit")]


@pytest.mark.parametrize(
    "forged",
    [
        {"user": "someone-else", "body": "<!-- lane-escalation run=9001 -->\nhi"},
        {"user": "osasuwu-bot", "body": "quoting\n<!-- lane-escalation run=9001 -->"},
        {"user": "osasuwu-bot", "body": "<!-- lane-escalation run=9002 -->\nother run"},
    ],
)
def test_only_the_bots_own_marker_for_this_run_suppresses_the_comment(gh, tmp_path, forged):
    gh.comments = {2011: [forged]}
    lane_escalation.escalate(_env(), _out(tmp_path, escalation="x"))
    assert [w[:2] for w in gh.writes] == [("issue", "edit"), ("issue", "comment")]


def test_hostile_escalation_text_stays_inside_one_code_fence(gh, tmp_path):
    hostile = "done\n```\n@everyone ping <!-- lane-escalation run=1 -->\n````\n@Osasuwu"
    lane_escalation.escalate(_env(), _out(tmp_path, escalation=hostile))
    lines = _comment_body(gh).splitlines()
    opening = lines.index("`````")
    closing = lines.index("`````", opening + 1)
    assert lines[opening + 1 : closing] == hostile.splitlines()
    live = lines[:opening] + lines[closing + 1 :]
    assert not any("@everyone" in line or "run=1" in line for line in live)


def test_an_overlong_note_is_truncated_with_a_pointer_to_the_artifact(gh, tmp_path):
    lane_escalation.escalate(_env(), _out(tmp_path, escalation="y" * 20000))
    body = _comment_body(gh)
    quoted = body.split("```\n")[1]
    assert quoted.count("y") == 8000
    assert "[truncated; the full text is in the run's `lane-out` artifact]" in body


def test_a_note_that_is_not_utf8_is_read_with_replacement(gh, tmp_path):
    out = _out(tmp_path)
    (out / "escalation.md").write_bytes(b"bad \xff byte")
    lane_escalation.escalate(_env(), out)
    assert "bad � byte" in _comment_body(gh)


def test_nothing_in_a_run_touches_an_assignee_or_the_issue_body(gh, tmp_path):
    for result in ("success", "failure", "cancelled"):
        gh.writes.clear()
        lane_escalation.escalate(_env(WORKER_RESULT=result), _out(tmp_path, escalation="x"))
        flat = [part for call in gh.writes for part in call]
        assert not [p for p in flat if "assignee" in p]
        assert {"--body", "--body-file", "--title", "--add-assignee", "--remove-assignee"} & set(
            flat
        ) <= {"--body"}
        edits = [w for w in gh.writes if w[:2] == ("issue", "edit")]
        assert all(
            set(w[3:])
            <= {
                "--repo",
                REPO,
                "--add-label",
                "--remove-label",
                "needs-human",
                "status:in-progress",
            }
            for w in edits
        )


def test_without_an_operator_the_label_and_comment_still_land_and_the_command_fails(
    gh, tmp_path, monkeypatch, capsys
):
    out = _out(tmp_path, escalation="x")
    for key, value in _env(LANE_OPERATOR="").items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("LANE_OUT", str(out))
    with pytest.raises(SystemExit) as exit_info:
        lane_escalation.main(["lane_escalation.py", "run"])
    assert exit_info.value.code == 1
    assert [w[:2] for w in gh.writes] == [("issue", "edit"), ("issue", "comment")]
    assert " @" not in _comment_body(gh) and not _comment_body(gh).splitlines()[1].startswith("@")
    assert "::warning::LANE_OPERATOR" in capsys.readouterr().out


def test_a_configured_operator_exits_clean(gh, tmp_path, monkeypatch):
    out = _out(tmp_path, escalation="x")
    for key, value in _env().items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("LANE_OUT", str(out))
    assert lane_escalation.main(["lane_escalation.py", "run"]) is None


def test_redispatch_after_an_escalation_needs_the_human_to_clear_the_marker(gh, tmp_path):
    labels = ["afk:1-auto", "agent:dispatch", "status:in-progress"]
    gh.issue_labels = list(labels)
    lane_escalation.escalate(_env(), _out(tmp_path, escalation="x"))
    edit = gh.writes[0]
    after = [n for n in labels if n not in edit[edit.index("--remove-label") + 1 :]]
    after.append(edit[edit.index("--add-label") + 1])
    facts = {
        "body": "Do the thing.",
        "state": "open",
        "labels": after,
        "editors": ["Osasuwu"],
        "closing_prs": [],
        "blocked_by": 0,
    }
    assert lane_intake.check(facts, "Do the thing.", "osasuwu-bot")[0] == "needs-human"
    facts["labels"] = [n for n in after if n != "needs-human"]
    assert lane_intake.check(facts, "Do the thing.", "osasuwu-bot") is None


# --- watch: the PR side ---------------------------------------------------------------


def _pr(number=40, head="claude/issue-2011-9001", sha=SHA, cross=False, labels=()):
    return {
        "number": number,
        "headRefName": head,
        "headRefOid": sha,
        "isCrossRepository": cross,
        "labels": [{"name": n} for n in labels],
    }


def _check(name, conclusion, id_=1, status="completed", at="2026-10-08T10:00:00Z"):
    return {
        "id": id_,
        "name": name,
        "status": status,
        "conclusion": conclusion,
        "completed_at": at,
        "details_url": f"https://github.com/{REPO}/actions/runs/{id_}/job/1",
    }


WATCHED = "require-linked-issue,pytest,code-gate,gitleaks"


def _watch(gh, watched=WATCHED):
    return lane_escalation.watch(
        {
            "GH_REPO": REPO,
            "LANE_OPERATOR": "Osasuwu",
            "LANE_BOT_LOGIN": "osasuwu-bot",
            "LANE_WATCHED_CHECKS": watched,
        }
    )


def test_a_red_required_check_on_a_lane_pr_labels_it_and_comments_once(gh):
    gh.open_prs = [_pr()]
    gh.check_runs = {SHA: [_check("pytest", "failure", id_=7), _check("gitleaks", "success", 8)]}
    flagged, handle = _watch(gh)
    assert flagged == [(40, "pytest")] and handle == "Osasuwu"
    assert gh.writes == [
        ("pr", "edit", "40", "--repo", REPO, "--add-label", "needs-human"),
        (
            "pr",
            "comment",
            "40",
            "--repo",
            REPO,
            "--body",
            f"<!-- lane-red-check pytest {SHA} -->\n"
            "@Osasuwu required check `pytest` is red on `aaaaaaa`"
            f" (https://github.com/{REPO}/actions/runs/7/job/1).\n"
            "\n"
            "Fix it and push, or close the PR. Remove `needs-human` once you have decided.\n",
        ),
    ]


@pytest.mark.parametrize(
    "runs",
    [
        [_check("pytest", "success", 1), _check("gitleaks", "success", 2)],
        [_check("pytest", "failure", 1, status="in_progress")],
        [_check("pytest", "failure", 1), _check("pytest", "success", 2)],
        [_check("waiting-human-review", "failure", 3)],
        [_check("some-other-check", "failure", 4)],
        [],
    ],
)
def test_green_pending_superseded_and_unwatched_checks_get_nothing(gh, runs):
    gh.open_prs = [_pr()]
    gh.check_runs = {SHA: runs}
    assert _watch(gh)[0] == []
    assert gh.writes == []


def test_a_red_rerun_after_a_green_one_is_the_latest(gh):
    gh.open_prs = [_pr()]
    gh.check_runs = {SHA: [_check("pytest", "success", 1), _check("pytest", "timed_out", 2)]}
    assert _watch(gh)[0] == [(40, "pytest")]


@pytest.mark.parametrize(
    "pr",
    [_pr(head="feat/2011-thing"), _pr(head="claude/issue-2011-9001", cross=True)],
)
def test_non_lane_and_cross_repo_prs_are_not_read_at_all(gh, pr):
    gh.open_prs = [pr]
    gh.check_runs = {SHA: [_check("pytest", "failure")]}
    assert _watch(gh)[0] == []
    assert gh.writes == [] and len(gh.reads) == 1


def test_one_comment_per_check_and_head_sha(gh):
    gh.open_prs = [_pr(labels=["needs-human"])]
    gh.check_runs = {SHA: [_check("pytest", "failure", 1), _check("gitleaks", "failure", 2)]}
    gh.comments = {
        40: [{"user": "osasuwu-bot", "body": f"<!-- lane-red-check pytest {SHA} -->\nold"}]
    }
    _watch(gh)
    assert [w[:2] for w in gh.writes] == [("pr", "comment")]
    assert "required check `gitleaks` is red" in gh.writes[0][-1]


def test_a_second_event_for_the_same_red_head_writes_nothing(gh):
    gh.open_prs = [_pr(labels=["needs-human"])]
    gh.check_runs = {SHA: [_check("pytest", "failure", 1)]}
    gh.comments = {
        40: [{"user": "osasuwu-bot", "body": f"<!-- lane-red-check pytest {SHA} -->\nold"}]
    }
    _watch(gh)
    assert gh.writes == []


def test_a_new_head_sha_is_reported_again(gh):
    new = "b" * 40
    gh.open_prs = [_pr(sha=new, labels=["needs-human"])]
    gh.check_runs = {new: [_check("pytest", "failure", 1)]}
    gh.comments = {
        40: [{"user": "osasuwu-bot", "body": f"<!-- lane-red-check pytest {SHA} -->\nold"}]
    }
    _watch(gh)
    assert [w[:2] for w in gh.writes] == [("pr", "comment")]


_GATE_AT = "2026-10-08T10:10:00Z"


def _review(status="completed", at="2026-10-08T10:05:00Z", title="Code Review"):
    return {"status": status, "updated_at": at, "title": title}


@pytest.mark.parametrize(
    "reviews",
    [
        [],
        [_review(status="in_progress")],
        [_review(), _review(status="queued", at="2026-10-08T10:09:00Z")],
        [_review(at="2026-10-08T10:11:00Z")],
    ],
    ids=["no-review-run", "review-running", "second-review-queued", "gate-older-than-review"],
)
def test_a_red_code_gate_before_the_review_settles_is_not_reported(gh, reviews):
    gh.open_prs = [_pr()]
    gh.check_runs = {SHA: [_check("code-gate", "failure", 5, at=_GATE_AT)]}
    gh.review_runs = reviews
    assert _watch(gh)[0] == []
    assert gh.writes == []


def test_a_red_code_gate_after_the_review_settled_is_reported(gh):
    gh.open_prs = [_pr()]
    gh.check_runs = {SHA: [_check("code-gate", "failure", 5, at=_GATE_AT)]}
    gh.review_runs = [_review()]
    assert _watch(gh)[0] == [(40, "code-gate")]


def test_a_dispatched_review_counts_by_its_run_title(gh):
    gh.open_prs = [_pr()]
    gh.check_runs = {SHA: [_check("code-gate", "failure", 5, at=_GATE_AT)]}
    gh.dispatched_runs = [
        _review(title=f"Code review PR #40 @ {SHA}"),
        _review(status="in_progress", title=f"Code review PR #41 @ {SHA}"),
    ]
    assert _watch(gh)[0] == [(40, "code-gate")]


def test_watch_without_an_operator_exits_cleanly_when_nothing_is_red(gh, monkeypatch, capsys):
    gh.open_prs = [_pr()]
    gh.check_runs = {SHA: [_check("pytest", "success", 1)]}
    monkeypatch.setenv("GH_REPO", REPO)
    monkeypatch.setenv("LANE_BOT_LOGIN", "osasuwu-bot")
    monkeypatch.setenv("LANE_WATCHED_CHECKS", WATCHED)
    monkeypatch.delenv("LANE_OPERATOR", raising=False)
    lane_escalation.main(["lane_escalation.py", "watch"])  # must not raise SystemExit
    assert gh.writes == []
    assert "::warning::" not in capsys.readouterr().out


def test_watch_without_an_operator_still_flags_and_exits_failing(gh, monkeypatch, capsys):
    gh.open_prs = [_pr()]
    gh.check_runs = {SHA: [_check("pytest", "failure", 1)]}
    monkeypatch.setenv("GH_REPO", REPO)
    monkeypatch.setenv("LANE_BOT_LOGIN", "osasuwu-bot")
    monkeypatch.setenv("LANE_WATCHED_CHECKS", WATCHED)
    monkeypatch.delenv("LANE_OPERATOR", raising=False)
    with pytest.raises(SystemExit) as exit_info:
        lane_escalation.main(["lane_escalation.py", "watch"])
    assert exit_info.value.code == 1
    assert [w[:2] for w in gh.writes] == [("pr", "edit"), ("pr", "comment")]
    assert gh.writes[1][-1].splitlines()[1].startswith("required check")
    assert "::warning::LANE_OPERATOR" in capsys.readouterr().out


def test_the_watched_checks_come_from_the_caller_not_from_the_script(gh):
    gh.open_prs = [_pr()]
    gh.check_runs = {SHA: [_check("pytest", "failure", 1), _check("lint", "failure", 2)]}
    assert _watch(gh, "lint")[0] == [(40, "lint")]


def test_the_code_review_runs_are_read_only_when_code_gate_is_watched(gh):
    gh.open_prs = [_pr()]
    gh.check_runs = {SHA: [_check("pytest", "failure", 1)]}
    _watch(gh, "pytest")
    assert not [r for r in gh.reads if any("code-review.yml" in a for a in r)]


@pytest.mark.parametrize("value", [None, "", " , "])
def test_watch_with_no_watched_checks_fails_naming_the_variable(gh, monkeypatch, capsys, value):
    gh.open_prs = [_pr()]
    monkeypatch.setenv("GH_REPO", REPO)
    monkeypatch.setenv("LANE_BOT_LOGIN", "osasuwu-bot")
    monkeypatch.delenv("LANE_WATCHED_CHECKS", raising=False)
    if value is not None:
        monkeypatch.setenv("LANE_WATCHED_CHECKS", value)
    with pytest.raises(SystemExit) as exit_info:
        lane_escalation.main(["lane_escalation.py", "watch"])
    assert exit_info.value.code == 1
    assert "::error::LANE_WATCHED_CHECKS" in capsys.readouterr().out
    assert gh.writes == []


@pytest.mark.parametrize("command", ["run", "watch"])
def test_escalation_without_a_bot_login_fails_naming_the_variable(gh, monkeypatch, capsys, command):
    monkeypatch.setenv("GH_REPO", REPO)
    monkeypatch.setenv("LANE_WATCHED_CHECKS", WATCHED)
    monkeypatch.delenv("LANE_BOT_LOGIN", raising=False)
    with pytest.raises(SystemExit) as exit_info:
        lane_escalation.main(["lane_escalation.py", command])
    assert exit_info.value.code == 1
    assert "::error::lane_escalation: LANE_BOT_LOGIN" in capsys.readouterr().out
    assert gh.writes == []
