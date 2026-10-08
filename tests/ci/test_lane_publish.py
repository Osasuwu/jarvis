"""The publish step of the AFK lane (.github/scripts/lane_publish.py, #2007).

The worker holds no writable token; this step pushes its bundle and opens the PR as the
bot. What must hold: the review request depends only on the `Risk:` line (HIGH/CRITICAL,
or unreadable), the body always closes the issue, and exactly the worker's branch is
pushed. Git runs for real against a local bare repo; `gh` is recorded, not run.
"""

import importlib.util
import os
import subprocess
from pathlib import Path

import pytest

_root = next(p for p in Path(__file__).resolve().parents if (p / ".github" / "scripts").is_dir())
_spec = importlib.util.spec_from_file_location(
    "lane_publish", _root / ".github" / "scripts" / "lane_publish.py"
)
lane_publish = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lane_publish)

_GIT_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.com",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.com",
}


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("## Risk Assessment\nRisk: HIGH — logic change", "HIGH"),
        ("Risk: LOW — docs", "LOW"),
        ("**Risk:** critical — data loss", "CRITICAL"),
        ("- Risk: MEDIUM — new helper", "MEDIUM"),
        # The PR template's own legend names every tier without a `Risk:` label.
        ("- **LOW**: cosmetic\n- **HIGH**: logic changes", None),
        ("no risk line at all", None),
        ("", None),
        # Two lines disagree: the higher tier wins, so a hedge cannot lower it.
        ("Risk: LOW — first\n\nRisk: HIGH — second", "HIGH"),
    ],
)
def test_parse_risk(body, expected):
    assert lane_publish.parse_risk(body) == expected


@pytest.mark.parametrize(
    ("risk", "expected"),
    [("LOW", False), ("MEDIUM", False), ("HIGH", True), ("CRITICAL", True), (None, True)],
)
def test_review_is_requested_only_for_high_or_unreadable_risk(risk, expected):
    assert lane_publish.needs_human_review(risk) is expected


def test_closes_line_is_appended_when_missing():
    assert lane_publish.with_closes("Summary.", 2007) == "Summary.\n\nCloses #2007\n"


def test_existing_closes_line_is_kept():
    body = "Summary.\n\nCloses #2007\n"
    assert lane_publish.with_closes(body, 2007) == body


def test_closes_of_a_longer_issue_number_does_not_count():
    assert lane_publish.with_closes("Closes #20071", 2007) == "Closes #20071\n\nCloses #2007\n"


def _git(cwd, *args):
    return subprocess.run(
        ["git", *args], cwd=cwd, env=_GIT_ENV, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def lane(tmp_path, monkeypatch):
    """A bare origin, a publisher checkout of it, and a worker bundle with one commit."""
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "--bare", "-b", "main", str(origin))
    seed = tmp_path / "seed"
    _git(tmp_path, "clone", str(origin), str(seed))
    (seed / "README.md").write_text("base\n", encoding="utf-8")
    _git(seed, "add", ".")
    _git(seed, "commit", "-m", "init")
    _git(seed, "push", "origin", "HEAD:main")

    publisher = tmp_path / "publisher"
    _git(tmp_path, "clone", str(origin), str(publisher))

    worker = tmp_path / "worker"
    _git(tmp_path, "clone", str(origin), str(worker))
    _git(worker, "switch", "-c", "claude/issue-2007-slug")
    (worker / "feature.txt").write_text("done\n", encoding="utf-8")
    _git(worker, "add", ".")
    _git(worker, "commit", "-m", "feat(lane): publish the worker branch (#2007)")
    out = tmp_path / "lane-out"
    out.mkdir()
    _git(worker, "bundle", "create", str(out / "work.bundle"), "origin/main..HEAD")

    calls = []

    def fake_gh(*args):
        calls.append(args)
        return "https://github.com/Osasuwu/jarvis/pull/77" if args[:2] == ("pr", "create") else ""

    monkeypatch.setattr(lane_publish, "gh", fake_gh)

    class Lane:
        pass

    lane = Lane()
    lane.origin, lane.publisher, lane.out, lane.calls = origin, publisher, out, calls
    lane.worker_sha = _git(worker, "rev-parse", "HEAD")
    return lane


def _publish(lane, **over):
    args = {
        "issue": "2007",
        "run_id": "555",
        "default_branch": "main",
        "out_dir": lane.out,
        "reviewer": "Osasuwu",
        "repo_dir": lane.publisher,
    }
    args.update(over)
    return lane_publish.publish(**args)


def test_worker_branch_is_pushed_under_the_run_scoped_name(lane):
    (lane.out / "pr-body.md").write_text("Risk: LOW — docs\n", encoding="utf-8")
    _publish(lane)
    pushed = _git(lane.origin, "rev-parse", "refs/heads/claude/issue-2007-555")
    assert pushed == lane.worker_sha
    assert _git(lane.origin, "for-each-ref", "--format=%(refname)", "refs/heads/claude") == (
        "refs/heads/claude/issue-2007-555"
    )


def test_low_risk_pr_opens_without_a_reviewer_and_moves_the_issue_to_review(lane):
    (lane.out / "pr-body.md").write_text("Risk: LOW — docs\n", encoding="utf-8")
    number = _publish(lane)
    final = lane.out / "pr-body.final.md"
    assert number == 77
    assert lane.calls == [
        (
            "pr",
            "create",
            "--head",
            "claude/issue-2007-555",
            "--base",
            "main",
            "--title",
            "feat(lane): publish the worker branch (#2007)",
            "--body-file",
            str(final),
        ),
        (
            "issue",
            "edit",
            "2007",
            "--remove-label",
            "status:in-progress",
            "--add-label",
            "status:review",
        ),
    ]
    assert final.read_text(encoding="utf-8") == "Risk: LOW — docs\n\nCloses #2007\n"


@pytest.mark.parametrize("body", ["Risk: HIGH — logic", "Risk: CRITICAL — data loss", "no risk"])
def test_high_critical_or_unreadable_risk_requests_the_operator(lane, body):
    (lane.out / "pr-body.md").write_text(body + "\n", encoding="utf-8")
    _publish(lane)
    create = next(c for c in lane.calls if c[:2] == ("pr", "create"))
    assert create[-2:] == ("--reviewer", "Osasuwu")


def test_missing_pr_description_still_opens_a_pr_that_closes_the_issue(lane):
    _publish(lane)
    final = (lane.out / "pr-body.final.md").read_text(encoding="utf-8")
    assert final == "\n\nCloses #2007\n"
    create = next(c for c in lane.calls if c[:2] == ("pr", "create"))
    assert create[-2:] == ("--reviewer", "Osasuwu")


def test_no_bundle_publishes_nothing(lane):
    (lane.out / "work.bundle").unlink()
    assert _publish(lane) is None
    assert lane.calls == []
    assert _git(lane.origin, "for-each-ref", "--format=%(refname)", "refs/heads/claude") == ""


@pytest.mark.parametrize("value", [None, "", "  "])
def test_require_bot_refuses_a_missing_login_and_names_the_caller(capsys, value):
    env = {} if value is None else {"LANE_BOT_LOGIN": value}
    with pytest.raises(SystemExit) as exit_info:
        lane_publish.require_bot(env, "lane_x")
    assert exit_info.value.code == 1
    assert capsys.readouterr().out.strip() == (
        "::error::lane_x: LANE_BOT_LOGIN is empty; the calling workflow must pass the lane's bot login"
    )


def test_require_bot_returns_the_login_trimmed():
    assert lane_publish.require_bot({"LANE_BOT_LOGIN": " some-bot "}, "lane_x") == "some-bot"
