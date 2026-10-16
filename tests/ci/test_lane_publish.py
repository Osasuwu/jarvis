"""The publish step of the AFK lane (.github/scripts/lane_publish.py, #2007).

The worker holds no writable token; this step pushes its bundle and opens the PR as the
bot. What must hold: the review request depends only on the `Risk:` line (HIGH/CRITICAL,
or unreadable), the body always closes the issue, and exactly the worker's branch is
pushed. Git runs for real against a local bare repo; GitHub is a `FakeApi` passed as
`api` (#2068), or a real `Client` over a `FakeTransport` where the client's own policy
(the one-shot PR create, the token, the user agent) is what is under test.
"""

import importlib.util
import os
import subprocess
import urllib.error
from pathlib import Path

import pytest

from ._github_fake import FakeApi, FakeTransport, http_error, load_client

_root = next(p for p in Path(__file__).resolve().parents if (p / ".github" / "scripts").is_dir())
_spec = importlib.util.spec_from_file_location(
    "lane_publish", _root / ".github" / "scripts" / "lane_publish.py"
)
lane_publish = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lane_publish)

REPO = "Osasuwu/jarvis"
PR_URL = "https://github.com/Osasuwu/jarvis/pull/77"
TITLE = "feat(lane): publish the worker branch (#2007)"

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


def _api():
    """GitHub as the publish step sees it: the PR create answers PR #77."""
    return FakeApi(
        writes={
            f"repos/{REPO}/pulls": {"number": 77, "html_url": PR_URL},
            f"repos/{REPO}/pulls/77/requested_reviewers": {"number": 77},
            f"repos/{REPO}/issues/2007/labels": [{"name": "status:review"}],
        }
    )


@pytest.fixture
def lane(tmp_path):
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
    _git(worker, "commit", "-m", TITLE)
    out = tmp_path / "lane-out"
    out.mkdir()
    _git(worker, "bundle", "create", str(out / "work.bundle"), "origin/main..HEAD")

    class Lane:
        pass

    lane = Lane()
    lane.origin, lane.publisher, lane.out, lane.api = origin, publisher, out, _api()
    lane.worker_sha = _git(worker, "rev-parse", "HEAD")
    return lane


def _publish(lane, **over):
    args = {
        "issue": "2007",
        "run_id": "555",
        "default_branch": "main",
        "out_dir": lane.out,
        "reviewer": "Osasuwu",
        "repo": REPO,
        "repo_dir": lane.publisher,
    }
    args.update(over)
    return lane_publish.publish(lane.api, **args)


def _create(body):
    return (
        "POST",
        f"repos/{REPO}/pulls",
        {"head": "claude/issue-2007-555", "base": "main", "title": TITLE, "body": body},
    )


LABELS_MOVED = [
    ("POST", f"repos/{REPO}/issues/2007/labels", {"labels": ["status:review"]}),
    ("DELETE", f"repos/{REPO}/issues/2007/labels/status%3Ain-progress", None),
]


def test_worker_branch_is_pushed_under_the_run_scoped_name(lane):
    (lane.out / "pr-body.md").write_text("Risk: LOW — docs\n", encoding="utf-8")
    _publish(lane)
    pushed = _git(lane.origin, "rev-parse", "refs/heads/claude/issue-2007-555")
    assert pushed == lane.worker_sha
    assert _git(lane.origin, "for-each-ref", "--format=%(refname)", "refs/heads/claude") == (
        "refs/heads/claude/issue-2007-555"
    )


def test_low_risk_pr_opens_without_a_reviewer_and_moves_the_issue_to_review(lane, capsys):
    (lane.out / "pr-body.md").write_text("Risk: LOW — docs\n", encoding="utf-8")
    number = _publish(lane)
    final = lane.out / "pr-body.final.md"
    assert number == 77
    assert lane.api.calls == [_create("Risk: LOW — docs\n\nCloses #2007\n"), *LABELS_MOVED]
    assert final.read_text(encoding="utf-8") == "Risk: LOW — docs\n\nCloses #2007\n"
    assert capsys.readouterr().out == f"#2007: opened {PR_URL} (risk LOW)\n"


def test_the_pr_create_is_made_once_and_never_retried(lane):
    # A 5xx can follow a created PR; a retry would open a second one, or fail on the
    # first with a 422 after the branch already has its PR (#2068).
    (lane.out / "pr-body.md").write_text("Risk: LOW — docs\n", encoding="utf-8")
    _publish(lane)
    assert lane.api.once == [("POST", f"repos/{REPO}/pulls")]


@pytest.mark.parametrize("body", ["Risk: HIGH — logic", "Risk: CRITICAL — data loss", "no risk"])
def test_high_critical_or_unreadable_risk_requests_the_operator(lane, body):
    (lane.out / "pr-body.md").write_text(body + "\n", encoding="utf-8")
    _publish(lane)
    assert lane.api.calls[1:] == [
        ("POST", f"repos/{REPO}/pulls/77/requested_reviewers", {"reviewers": ["Osasuwu"]}),
        *LABELS_MOVED,
    ]


def test_a_high_risk_pr_with_no_reviewer_still_opens_without_the_request(lane):
    # An org-owned host has no person to ask: the PR must still open, held by its labels.
    (lane.out / "pr-body.md").write_text("Risk: HIGH — logic\n", encoding="utf-8")
    assert _publish(lane, reviewer="") == 77
    assert lane.api.calls == [_create("Risk: HIGH — logic\n\nCloses #2007\n"), *LABELS_MOVED]


def test_missing_pr_description_still_opens_a_pr_that_closes_the_issue(lane):
    _publish(lane)
    final = (lane.out / "pr-body.final.md").read_text(encoding="utf-8")
    assert final == "\n\nCloses #2007\n"
    assert lane.api.calls[:2] == [
        _create("\n\nCloses #2007\n"),
        ("POST", f"repos/{REPO}/pulls/77/requested_reviewers", {"reviewers": ["Osasuwu"]}),
    ]


def test_an_in_progress_label_already_gone_still_publishes(lane):
    lane.api.writes[f"repos/{REPO}/issues/2007/labels/status%3Ain-progress"] = http_error(404)
    (lane.out / "pr-body.md").write_text("Risk: LOW — docs\n", encoding="utf-8")
    assert _publish(lane) == 77


def test_a_create_answer_without_a_number_raises_before_any_label_moves(lane):
    lane.api.writes[f"repos/{REPO}/pulls"] = {}
    (lane.out / "pr-body.md").write_text("Risk: LOW — docs\n", encoding="utf-8")
    with pytest.raises(KeyError):
        _publish(lane)
    assert lane.api.calls == [_create("Risk: LOW — docs\n\nCloses #2007\n")]


def test_a_failed_review_request_raises_before_the_issue_moves_to_review(lane):
    lane.api.writes[f"repos/{REPO}/pulls/77/requested_reviewers"] = http_error(422)
    (lane.out / "pr-body.md").write_text("Risk: HIGH — logic\n", encoding="utf-8")
    with pytest.raises(urllib.error.HTTPError):
        _publish(lane)
    assert [c[:2] for c in lane.api.calls] == [
        ("POST", f"repos/{REPO}/pulls"),
        ("POST", f"repos/{REPO}/pulls/77/requested_reviewers"),
    ]


def test_no_bundle_publishes_nothing(lane):
    (lane.out / "work.bundle").unlink()
    assert _publish(lane) is None
    assert lane.api.calls == []
    assert _git(lane.origin, "for-each-ref", "--format=%(refname)", "refs/heads/claude") == ""


# --- main: the job's entry point --------------------------------------------------------


def _main_env(monkeypatch, lane, *, body="Risk: LOW — docs\n"):
    """The publish step's environment, run from the publisher checkout as in lane.yml."""
    (lane.out / "pr-body.md").write_text(body, encoding="utf-8")
    output = lane.out.parent / "github-output"
    output.write_text("", encoding="utf-8")
    monkeypatch.chdir(lane.publisher)
    for name, value in {
        "GH_TOKEN": "bot-pat",
        "GH_REPO": REPO,
        "ISSUE_NUMBER": "2007",
        "RUN_ID": "555",
        "DEFAULT_BRANCH": "main",
        "LANE_OUT": str(lane.out),
        "LANE_REVIEWER": "Osasuwu",
        "GITHUB_OUTPUT": str(output),
    }.items():
        monkeypatch.setenv(name, value)
    return output


@pytest.fixture
def gh_cli(monkeypatch):
    """Every `gh` command main runs, recorded with its keywords; git still runs for real."""
    real_run = subprocess.run
    runs = []

    def run(cmd, **kw):
        if cmd[0] == "gh":
            runs.append((cmd, kw))
            return subprocess.CompletedProcess(cmd, 0)
        return real_run(cmd, **kw)

    monkeypatch.setattr(subprocess, "run", run)
    return runs


def test_main_installs_the_git_credential_helper_once_and_writes_the_pr_number(
    lane, monkeypatch, gh_cli
):
    output = _main_env(monkeypatch, lane)
    lane_publish.main(make_client=lambda token: lane.api)
    assert gh_cli == [(["gh", "auth", "setup-git"], {"check": True})]
    assert output.read_text(encoding="utf-8") == "pr=77\n"


def test_main_builds_its_own_client_with_the_bot_token_and_the_lane_publish_agent(
    lane, monkeypatch, gh_cli
):
    """The production `_make_client`, not an injected one: `main()` runs with only the
    transport patched, so a wrong token, user agent or constructor call goes red here."""
    transport = FakeTransport([{"number": 77, "html_url": PR_URL}, [], b""])
    monkeypatch.setattr(load_client(), "urllib_transport", transport)
    output = _main_env(monkeypatch, lane)
    lane_publish.main()
    assert [
        (r.method, r.url, r.headers["authorization"], r.headers["user-agent"])
        for r in transport.requests
    ] == [
        ("POST", f"https://api.github.com/repos/{REPO}/pulls", "Bearer bot-pat", "lane-publish"),
        (
            "POST",
            f"https://api.github.com/repos/{REPO}/issues/2007/labels",
            "Bearer bot-pat",
            "lane-publish",
        ),
        (
            "DELETE",
            f"https://api.github.com/repos/{REPO}/issues/2007/labels/status%3Ain-progress",
            "Bearer bot-pat",
            "lane-publish",
        ),
    ]
    assert transport.requests[0].body == {
        "head": "claude/issue-2007-555",
        "base": "main",
        "title": TITLE,
        "body": "Risk: LOW — docs\n\nCloses #2007\n",
    }
    assert output.read_text(encoding="utf-8") == "pr=77\n"


def test_a_502_on_the_pr_create_is_not_retried_and_writes_no_pr_output(lane, monkeypatch, gh_cli):
    gh = load_client()
    transport = FakeTransport([http_error(502, "bad gateway") for _ in range(5)])
    sleeps = []
    output = _main_env(monkeypatch, lane)
    with pytest.raises(urllib.error.HTTPError) as raised:
        lane_publish.main(
            make_client=lambda token: gh.Client(
                token, user_agent="t", transport=transport, sleep=sleeps.append
            )
        )
    assert raised.value.code == 502
    assert [(r.method, r.url) for r in transport.requests] == [
        ("POST", f"https://api.github.com/repos/{REPO}/pulls")
    ]
    assert sleeps == []
    assert output.read_text(encoding="utf-8") == ""


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
