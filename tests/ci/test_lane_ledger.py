"""The N-run gate ledger of the AFK lane (.github/scripts/lane_ledger.py, #2012, D13).

What must hold: every run past intake leaves one bot-authored row, a closed lane PR
finalises that row, and the rows alone give the gate's verdict. `gh` is replaced by an
in-memory ledger issue; the row format, the tally and the workflow wiring run for real.
"""

import importlib.util
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

_root = next(p for p in Path(__file__).resolve().parents if (p / ".github" / "scripts").is_dir())
_spec = importlib.util.spec_from_file_location(
    "lane_ledger", _root / ".github" / "scripts" / "lane_ledger.py"
)
lane_ledger = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lane_ledger)

WORKFLOWS = _root / ".github" / "workflows"
NOW = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)
BOT = "osasuwu-bot"


def _row(n, **over):
    row = {
        "run_id": str(n),
        "repo": "Osasuwu/jarvis",
        "issue": f"#{n}",
        "pr": n,
        "lane_sha": "abc123def456",
        "class": "afk:1-auto",
        "tier": "LOW",
        "diff": 10,
        "outcome": "pr-opened",
        "final": "merged-unedited",
        "window": "counted",
        "at": "2026-10-15T09:00:00+00:00",
    }
    row.update(over)
    return row


def _comment(row, user=BOT):
    return {"user": user, "body": lane_ledger.render(row)}


# --- row format ---------------------------------------------------------------------


def test_a_row_is_read_back_from_its_comment_body():
    row = _row(7, diff="—", tier="—", pr="—", outcome="escalated", final="pending")
    assert lane_ledger.parse(lane_ledger.render(row)) == row


def test_the_comment_shows_the_row_as_a_table_and_records_it_as_json():
    body = lane_ledger.render(_row(7))
    assert body.splitlines()[0].startswith(
        '<!-- lane-ledger {"run_id": "7", "repo": "Osasuwu/jarvis"'
    )
    assert body.splitlines()[3] == (
        "| 7 | Osasuwu/jarvis | #7 | 7 | abc123def456 | afk:1-auto | LOW | 10 |"
        " pr-opened | merged-unedited | counted | 2026-10-15T09:00:00+00:00 |"
    )


def test_a_value_cannot_close_the_html_comment_early():
    body = lane_ledger.render(_row(7, **{"class": "x --> <b>y"}))
    record = body.splitlines()[0]
    assert record.count("-->") == 1 and record.endswith("-->")
    assert lane_ledger.parse(body)["class"] == "x --> <b>y"


@pytest.mark.parametrize(
    "body",
    ["", "no row here", "<!-- lane-ledger {not json} -->", '<!-- lane-ledger {"x": 1} -->', None],
)
def test_a_comment_without_a_valid_row_parses_to_none(body):
    assert lane_ledger.parse(body) is None


# --- the tally ----------------------------------------------------------------------


def _tally(comments, now=NOW):
    return lane_ledger.tally(comments, now, BOT)


def test_six_merged_unedited_of_ten_pass_the_gate():
    rows = [_row(n) for n in range(6)] + [_row(n, final="merged-edited") for n in range(6, 10)]
    assert _tally([_comment(r) for r in rows]) == {
        "counted": 10,
        "smoke": 0,
        "successes": 6,
        "failures": 4,
        "pending": 0,
        "verdict": "pass",
    }


def test_six_successes_of_six_counted_runs_are_not_a_pass_yet():
    rows = [_row(n) for n in range(6)]
    assert _tally([_comment(r) for r in rows])["verdict"] == "open"
    # D13: fewer than ten counted runs by the deadline is a fail, however clean they are.
    after = datetime(2026, 11, 19, 12, 0, tzinfo=timezone.utc)
    assert _tally([_comment(r) for r in rows], now=after)["verdict"] == "fail"


def test_five_successes_do_not_pass_the_gate_yet():
    rows = [_row(n) for n in range(5)] + [_row(n, final="merged-edited") for n in range(5, 9)]
    rows.append(_row(9, final="pending", tier="LOW"))
    result = _tally([_comment(r) for r in rows])
    assert (result["successes"], result["failures"], result["pending"]) == (5, 4, 1)
    assert result["verdict"] == "open"


def test_five_failures_fail_the_gate_before_the_tenth_run():
    rows = [_row(n) for n in range(3)]
    rows += [_row(3, final="closed-unmerged"), _row(4, final="merged-edited")]
    rows += [_row(5, outcome="escalated", final="pending", tier="—", pr="—", diff="—")]
    rows += [_row(6, outcome="no-artifact", final="pending", tier="—", pr="—", diff="—")]
    rows += [_row(7, final="closed-unmerged")]
    result = _tally([_comment(r) for r in rows])
    assert (result["counted"], result["successes"], result["failures"]) == (8, 3, 5)
    assert result["verdict"] == "fail"


def test_smoke_rows_and_rows_past_the_tenth_are_never_counted():
    smoke = [_row(n, window="smoke", final="closed-unmerged") for n in range(3)]
    counted = [_row(n) for n in range(3, 14)]
    result = _tally([_comment(r) for r in smoke + counted])
    assert (result["smoke"], result["counted"], result["successes"]) == (3, 10, 10)


def test_a_high_pr_without_a_decision_for_seven_days_counts_as_not_merged():
    held = _row(1, tier="HIGH", final="pending", at="2026-10-13T12:00:00+00:00")
    assert _tally([_comment(held)])["failures"] == 1
    fresh = _row(1, tier="HIGH", final="pending", at="2026-10-13T12:00:01+00:00")
    assert _tally([_comment(fresh)]) == {
        "counted": 1,
        "smoke": 0,
        "successes": 0,
        "failures": 0,
        "pending": 1,
        "verdict": "open",
    }


def test_a_critical_pr_without_a_decision_for_seven_days_counts_as_not_merged():
    held = _row(1, tier="CRITICAL", final="pending", at="2026-10-13T12:00:00+00:00")
    assert _tally([_comment(held)])["failures"] == 1


def test_a_pending_low_pr_stays_open_however_old():
    old = _row(1, tier="LOW", final="pending", at="2026-09-01T00:00:00+00:00")
    assert _tally([_comment(old)])["pending"] == 1


def test_fewer_than_ten_counted_runs_after_the_deadline_fail():
    comments = [_comment(_row(n)) for n in range(4)]
    assert _tally(comments, datetime(2026, 11, 18, 23, 0, tzinfo=timezone.utc))["verdict"] == "open"
    assert _tally(comments, datetime(2026, 11, 19, 0, 1, tzinfo=timezone.utc))["verdict"] == "fail"


def test_ten_counted_runs_still_waiting_stay_open_after_the_deadline():
    comments = [_comment(_row(n, final="pending")) for n in range(10)]
    assert _tally(comments, datetime(2026, 12, 1, tzinfo=timezone.utc))["verdict"] == "open"


def test_a_row_posted_by_anyone_but_the_bot_is_ignored():
    comments = [_comment(_row(1)), _comment(_row(2), user="someone-else")]
    assert _tally(comments)["counted"] == 1


# --- final outcome ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("merged", "authors", "expected"),
    [
        (True, [BOT, BOT], "merged-unedited"),
        (True, [BOT, "Osasuwu"], "merged-edited"),
        (True, [BOT, ""], "merged-edited"),
        (True, [], "merged-edited"),
        (False, [BOT], "closed-unmerged"),
    ],
)
def test_final_outcome(merged, authors, expected):
    assert lane_ledger.final_outcome(merged, authors, BOT) == expected


# --- add / close against an in-memory ledger issue -----------------------------------


class FakeGitHub:
    """Answers the `gh` calls the script makes; keeps the ledger issue's comments."""

    def __init__(self):
        self.comments = []  # {"id", "user", "body"}
        self.prs = []
        self.labels = ["afk:1-auto", "status:in-progress"]
        self.smoke_state = "CLOSED"
        self.authors = []
        self.calls = []

    def __call__(self, *args):
        self.calls.append(args)
        if args[:2] == ("issue", "view") and args[2] == "2014":
            return self.smoke_state
        if args[:2] == ("issue", "view"):
            return json.dumps([{"name": n} for n in self.labels])
        if args[:2] == ("pr", "list"):
            return json.dumps(self.prs)
        if args[0] == "api" and "/pulls/" in args[2]:
            return "\n".join(self.authors)
        if args[0] == "api" and "--paginate" in args:
            return "\n".join(json.dumps(c) for c in self.comments)
        if args[0] == "api" and "-X" in args:
            comment_id = int(args[3].rsplit("/", 1)[1])
            next(c for c in self.comments if c["id"] == comment_id)["body"] = args[5][
                len("body=") :
            ]
            return ""
        if args[0] == "api":
            self.comments.append(
                {"id": 100 + len(self.comments), "user": BOT, "body": args[3][len("body=") :]}
            )
            return ""
        raise AssertionError(f"unexpected gh call {args}")

    def rows(self):
        return [lane_ledger.parse(c["body"]) for c in self.comments]


@pytest.fixture
def github(monkeypatch):
    fake = FakeGitHub()
    monkeypatch.setattr(lane_ledger, "gh", fake)
    return fake


def _add_env(**over):
    env = {
        "LANE_LEDGER_ISSUE": "Osasuwu/jarvis#3000",
        "GH_REPO": "Osasuwu/jarvis",
        "ISSUE_NUMBER": "55",
        "RUN_ID": "9001",
        "LANE_SHA": "0123456789abcdef0123",
    }
    env.update(over)
    return env


def test_a_run_with_a_pr_gets_a_row_with_its_diff_size_and_tier(github, tmp_path):
    github.prs = [{"number": 77, "additions": 30, "deletions": 12, "body": "Risk: MEDIUM — helper"}]
    lane_ledger.add_row(_add_env(), tmp_path, NOW)
    assert github.rows() == [
        {
            "run_id": "9001",
            "repo": "Osasuwu/jarvis",
            "issue": "#55",
            "pr": 77,
            "lane_sha": "0123456789ab",
            "class": "afk:1-auto",
            "tier": "MEDIUM",
            "diff": 42,
            "outcome": "pr-opened",
            "final": "pending",
            "window": "counted",
            "at": "2026-10-20T12:00:00+00:00",
        }
    ]


def test_a_pr_with_no_risk_line_is_recorded_as_high(github, tmp_path):
    github.prs = [{"number": 77, "additions": 1, "deletions": 0, "body": "no risk line"}]
    lane_ledger.add_row(_add_env(), tmp_path, NOW)
    assert github.rows()[0]["tier"] == "HIGH"


def test_a_run_that_escalated_has_no_pr_and_a_dash_for_diff_and_tier(github, tmp_path):
    (tmp_path / "escalation.md").write_text("blocked on X\n", encoding="utf-8")
    lane_ledger.add_row(_add_env(), tmp_path, NOW)
    row = github.rows()[0]
    assert (row["outcome"], row["pr"], row["diff"], row["tier"]) == ("escalated", "—", "—", "—")


def test_a_run_with_no_pr_and_no_escalation_is_no_artifact(github, tmp_path):
    lane_ledger.add_row(_add_env(), tmp_path, NOW)
    assert github.rows()[0]["outcome"] == "no-artifact"


def test_an_afk_2_plan_issue_is_recorded_with_that_class(github, tmp_path):
    github.labels = ["afk:2-plan", "status:in-progress"]
    lane_ledger.add_row(_add_env(), tmp_path, NOW)
    assert github.rows()[0]["class"] == "afk:2-plan"


def test_a_run_while_the_smoke_checkpoint_is_open_is_marked_smoke(github, tmp_path):
    github.smoke_state = "OPEN"
    lane_ledger.add_row(_add_env(LANE_LEDGER_SMOKE_ISSUE="Osasuwu/jarvis#2014"), tmp_path, NOW)
    assert github.rows()[0]["window"] == "smoke"


def test_a_run_after_the_smoke_checkpoint_closed_is_counted(github, tmp_path):
    github.smoke_state = "CLOSED"
    lane_ledger.add_row(_add_env(LANE_LEDGER_SMOKE_ISSUE="Osasuwu/jarvis#2014"), tmp_path, NOW)
    assert github.rows()[0]["window"] == "counted"


def test_a_rerun_of_the_same_run_refreshes_its_row_instead_of_adding_one(github, tmp_path):
    lane_ledger.add_row(_add_env(), tmp_path, NOW)
    later = datetime(2026, 10, 20, 13, 0, tzinfo=timezone.utc)
    github.prs = [{"number": 77, "additions": 1, "deletions": 1, "body": "Risk: LOW — x"}]
    lane_ledger.add_row(_add_env(), tmp_path, later)
    assert [(r["outcome"], r["at"]) for r in github.rows()] == [
        ("pr-opened", "2026-10-20T12:00:00+00:00")
    ]


def test_a_rerun_after_the_pr_closed_keeps_the_settled_final_and_window(github, tmp_path):
    github.prs = [{"number": 77, "additions": 1, "deletions": 1, "body": "Risk: LOW — x"}]
    lane_ledger.add_row(_add_env(LANE_LEDGER_SMOKE_ISSUE="Osasuwu/jarvis#2014"), tmp_path, NOW)
    github.comments[0]["body"] = lane_ledger.render(
        {**github.rows()[0], "final": "merged-unedited", "window": "smoke"}
    )
    # #2014 is CLOSED in the fake, so a fresh evaluation would say `counted` / `pending`.
    lane_ledger.add_row(_add_env(LANE_LEDGER_SMOKE_ISSUE="Osasuwu/jarvis#2014"), tmp_path, NOW)
    assert [(r["final"], r["window"]) for r in github.rows()] == [("merged-unedited", "smoke")]


def test_a_forged_row_for_the_same_run_is_not_taken_for_the_runs_own_row(github, tmp_path):
    github.comments.append(
        {
            "id": 5,
            "user": "someone-else",
            "body": lane_ledger.render(_row(9001, repo="Osasuwu/jarvis")),
        }
    )
    lane_ledger.add_row(_add_env(), tmp_path, NOW)
    assert [c["user"] for c in github.comments] == ["someone-else", BOT]


def test_an_unset_smoke_checkpoint_is_warned_about(github, tmp_path, capsys):
    lane_ledger.add_row(_add_env(), tmp_path, NOW)
    assert "LANE_LEDGER_SMOKE_ISSUE" in capsys.readouterr().out


def test_without_a_configured_ledger_nothing_is_written(github, tmp_path, capsys):
    assert lane_ledger.add_row(_add_env(LANE_LEDGER_ISSUE=""), tmp_path, NOW) is None
    assert github.calls == []
    assert "::warning::" in capsys.readouterr().out


def _close_env(**over):
    env = {
        "LANE_LEDGER_ISSUE": "Osasuwu/jarvis#3000",
        "GH_REPO": "Osasuwu/jarvis",
        "PR_NUMBER": "77",
        "PR_HEAD_REF": "claude/issue-55-9001",
        "PR_MERGED": "true",
    }
    env.update(over)
    return env


@pytest.fixture
def open_row(github, tmp_path):
    github.prs = [{"number": 77, "additions": 1, "deletions": 1, "body": "Risk: LOW — x"}]
    lane_ledger.add_row(_add_env(), tmp_path, NOW)
    return github


def test_a_merged_pr_of_only_bot_commits_finalises_its_row_as_unedited(open_row):
    open_row.authors = [BOT, BOT]
    lane_ledger.close_row(_close_env())
    assert [r["final"] for r in open_row.rows()] == ["merged-unedited"]
    assert open_row.rows()[0]["outcome"] == "pr-opened"


def test_a_merged_pr_with_a_human_commit_is_finalised_as_edited(open_row):
    open_row.authors = [BOT, "Osasuwu"]
    lane_ledger.close_row(_close_env())
    assert [r["final"] for r in open_row.rows()] == ["merged-edited"]


def test_a_closed_unmerged_pr_is_finalised_as_closed_unmerged(open_row):
    lane_ledger.close_row(_close_env(PR_MERGED="false"))
    assert [r["final"] for r in open_row.rows()] == ["closed-unmerged"]


def test_a_pr_that_is_not_the_one_in_the_row_is_left_alone(open_row):
    lane_ledger.close_row(_close_env(PR_NUMBER="78"))
    assert [r["final"] for r in open_row.rows()] == ["pending"]


def test_a_branch_outside_the_lane_naming_is_left_alone(open_row):
    lane_ledger.close_row(_close_env(PR_HEAD_REF="feat/issue-55-9001"))
    assert [r["final"] for r in open_row.rows()] == ["pending"]


# --- workflow wiring ------------------------------------------------------------------


def _load(name):
    return yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))


def _step_running(job, command):
    return next(s for s in job["steps"] if command in s.get("run", ""))


def test_the_ledger_job_runs_after_every_run_that_passed_intake():
    job = _load("agent-dispatch.yml")["jobs"]["ledger"]
    assert set(job["needs"]) == {"intake", "worker", "publish"}
    # `always()` so a worker or publish failure still leaves its row; the intake output
    # keeps refusals and the job-level-`if` skips out.
    assert job["if"] == "always() && needs.intake.outputs.pass == 'true'"
    assert "write" not in set(job["permissions"].values())


def test_the_ledger_step_posts_as_the_bot_to_a_configured_issue():
    job = _load("agent-dispatch.yml")["jobs"]["ledger"]
    step = _step_running(job, "lane_ledger.py add")
    assert step["env"]["GH_TOKEN"] == "${{ secrets.AGENT_DISPATCH_PAT }}"
    assert step["env"]["LANE_LEDGER_ISSUE"] == "${{ vars.LANE_LEDGER_ISSUE }}"
    assert step["env"]["LANE_SHA"] == "${{ github.sha }}"


def test_the_ledger_job_runs_default_branch_code_only():
    job = _load("agent-dispatch.yml")["jobs"]["ledger"]
    checkout = next(
        s for s in job["steps"] if str(s.get("uses", "")).startswith("actions/checkout@")
    )
    assert "ref" not in checkout["with"]
    assert checkout["with"]["persist-credentials"] is False


def test_no_ledger_issue_is_hardcoded_on_the_shared_lane_path():
    for path in (
        WORKFLOWS / "agent-dispatch.yml",
        WORKFLOWS / "lane-ledger-close.yml",
        _root / ".github" / "scripts" / "lane_ledger.py",
    ):
        assert not re.search(r"[\w.-]+/[\w.-]+#\d+", path.read_text(encoding="utf-8")), path.name


def test_the_close_workflow_finalises_lane_prs_from_default_branch_code():
    workflow = _load("lane-ledger-close.yml")
    # `pull_request` would run the PR's own copy of the script with the bot token.
    assert list(workflow[True]) == ["pull_request_target"]
    assert workflow[True]["pull_request_target"]["types"] == ["closed"]
    job = workflow["jobs"]["finalise"]
    assert "startsWith(github.event.pull_request.head.ref, 'claude/issue-')" in job["if"]
    assert "github.event.pull_request.head.repo.full_name == github.repository" in job["if"]
    checkout = next(
        s for s in job["steps"] if str(s.get("uses", "")).startswith("actions/checkout@")
    )
    assert "ref" not in checkout["with"]
    step = _step_running(job, "lane_ledger.py close")
    assert step["env"]["GH_TOKEN"] == "${{ secrets.AGENT_DISPATCH_PAT }}"
    assert step["env"]["PR_HEAD_REF"] == "${{ github.event.pull_request.head.ref }}"
    assert step["env"]["PR_MERGED"] == "${{ github.event.pull_request.merged }}"


def test_the_worker_commits_as_the_bot_before_it_runs():
    steps = _load("agent-dispatch.yml")["jobs"]["worker"]["steps"]
    identity = next(i for i, s in enumerate(steps) if s.get("name") == "Commit as the bot")
    worker = next(i for i, s in enumerate(steps) if "claude-code-action" in s.get("uses", ""))
    assert identity < worker
    lines = steps[identity]["run"]
    for var in ("GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME"):
        assert f"{var}=osasuwu-bot" in lines
    for var in ("GIT_AUTHOR_EMAIL", "GIT_COMMITTER_EMAIL"):
        assert f"{var}=339131200+osasuwu-bot@users.noreply.github.com" in lines


def test_no_run_script_expands_a_template_expression():
    # Untrusted strings (branch names, labels) reach the shell only through `env`.
    for name in ("agent-dispatch.yml", "lane-ledger-close.yml"):
        for job_name, job in _load(name)["jobs"].items():
            for step in job.get("steps", []):
                assert "${{" not in step.get("run", ""), f"{name}:{job_name}:{step.get('name')}"
