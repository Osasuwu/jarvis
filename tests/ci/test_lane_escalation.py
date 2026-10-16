"""The escalation marker of the AFK lane (.github/scripts/lane_escalation.py, #2011).

A run that passes intake and ends without a PR must leave `needs-human` and one comment
that @-mentions the operator; a red required check on an open lane PR does the same on the
PR. What must hold: no write when a PR exists, exactly one comment per run (and per check
and head SHA), nothing the worker wrote becomes live markdown, and no assignee or body
edit ever. The GitHub REST API is a fake behind the `github_client` seam (#2068); the
main-level tests run the production client over a fake transport.
"""

import importlib.util
import urllib.error
import urllib.parse
from pathlib import Path

import pytest

from ._github_fake import FakeApi, FakeTransport, http_error, load_client

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

API = "https://api.github.com"
REPO = "Osasuwu/jarvis"
SHA = "a" * 40
BOT = "osasuwu-bot"
ISSUE = f"repos/{REPO}/issues/2011"
# The run's PR, looked up by its owner-qualified head branch (lane_publish.branch_name).
HEAD_QUERY = f"repos/{REPO}/pulls?head=Osasuwu:claude/issue-2011-9001&state=all&per_page=1"
OPEN_PRS = f"repos/{REPO}/pulls?state=open"
JOBS = f"repos/{REPO}/actions/runs/9001/jobs"
REVIEWS = f"repos/{REPO}/actions/workflows/code-review.yml/runs"
LABEL_ADD = f"{ISSUE}/labels"
IN_PROGRESS_DELETE = f"{ISSUE}/labels/status%3Ain-progress"
COMMENTS = f"{ISSUE}/comments"


def _page(items, path):
    """The page of `items` that `paged`'s query in `path` asks for."""
    query = dict(part.split("=", 1) for part in path.split("?", 1)[1].split("&"))
    per_page, page = int(query["per_page"]), int(query["page"])
    return items[(page - 1) * per_page : page * per_page]


class FakeGitHub(FakeApi):
    """The REST API as the script reads it; every write is recorded and answered `{}`.

    Comments, open PRs and check runs are served page by page as `paged` asks for them,
    so a listing past its cap truncates as it does on GitHub. A read of any path not
    routed here is an unrouted GET and fails the test."""

    def __init__(self):
        self.branch_prs = []
        self.issue_labels = ["afk:1-auto", "status:in-progress"]
        self.comments = {}  # number -> [{"user" (login), "body"}]
        self.jobs = None  # the run's jobs, REST shape; None answers the jobs API with a 404
        self.open_prs = []  # REST shape, see _pr
        self.check_runs = {}  # head sha -> REST check runs
        self.review_runs = []  # Code Review runs for the head SHA, REST shape
        self.dispatched_runs = []  # dispatched Code Review runs, REST shape
        super().__init__(
            responses={
                f"repos/{REPO}/pulls?head=": lambda *_: self.branch_prs,
                f"{OPEN_PRS}&": lambda _m, path, _b: _page(self.open_prs, path),
                f"repos/{REPO}/issues/": self._issues,
                JOBS: self._jobs,
                f"repos/{REPO}/commits/": self._check_runs,
                f"{REVIEWS}?head_sha=": lambda *_: {"workflow_runs": self.review_runs},
                f"{REVIEWS}?event=workflow_dispatch&per_page=100": lambda *_: {
                    "workflow_runs": self.dispatched_runs
                },
            }
        )

    def _issues(self, _method, path, _body):
        number, _, rest = path.removeprefix(f"repos/{REPO}/issues/").partition("/")
        if not rest:
            assert number == "2011", path
            return {"number": 2011, "labels": [{"name": n} for n in self.issue_labels]}
        assert rest.startswith("comments?"), path
        comments = [
            {"id": n, "user": {"login": c["user"]}, "body": c["body"]}
            for n, c in enumerate(self.comments.get(int(number), []), start=1)
        ]
        return _page(comments, path)

    def _jobs(self, *_):
        if self.jobs is None:
            return http_error(404, '{"message":"Not Found"}')
        return {"total_count": len(self.jobs), "jobs": self.jobs}

    def _check_runs(self, _method, path, _body):
        sha, _, rest = path.removeprefix(f"repos/{REPO}/commits/").partition("/")
        assert rest.startswith("check-runs?"), path
        runs = self.check_runs.get(sha, [])
        return {"total_count": len(runs), "check_runs": _page(runs, path)}

    def written(self):
        return [(method, path, body) for method, path, body in self.calls if method != "GET"]

    def reads(self):
        return [path for method, path, _ in self.calls if method == "GET"]


@pytest.fixture
def github():
    return FakeGitHub()


def _main(github, argv, tokens=None):
    """`main` with the fake behind its client seam; `tokens` collects the token it was given."""

    def make_client(token):
        if tokens is not None:
            tokens.append(token)
        return github

    return lane_escalation.main(["lane_escalation.py", *argv], make_client=make_client)


def _env(**over):
    env = {
        "GH_REPO": REPO,
        "ISSUE_NUMBER": "2011",
        "RUN_ID": "9001",
        "LANE_OPERATOR": "Osasuwu",
        "LANE_BOT_LOGIN": BOT,
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


def _comment_body(github):
    (body,) = [b["body"] for m, p, b in github.written() if (m, p) == ("POST", COMMENTS)]
    return body


def _worker_job(started="2026-10-08T10:00:00Z", completed="2026-10-08T10:45:03Z"):
    return {"name": "worker", "started_at": started, "completed_at": completed}


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


def test_run_with_a_pr_on_the_run_branch_writes_nothing(github, tmp_path):
    github.branch_prs = [{"number": 77}]
    assert lane_escalation.escalate(github, _env(), _out(tmp_path, escalation="blocked")) is None
    assert github.calls == [("GET", HEAD_QUERY, None)]


def test_an_empty_pr_lookup_answer_raises_instead_of_escalating(tmp_path):
    """Base read gh's empty output as "no PR" and escalated; now nothing is written."""
    transport = FakeTransport([b""])
    api = load_client().Client("t", user_agent="t", transport=transport)
    with pytest.raises(ValueError, match="empty response body"):
        lane_escalation.escalate(api, _env(), _out(tmp_path, escalation="x"))
    assert [(r.method, r.url) for r in transport.requests] == [("GET", f"{API}/{HEAD_QUERY}")]


def test_escalation_labels_the_issue_and_posts_one_comment(github, tmp_path):
    cause = lane_escalation.escalate(
        github, _env(), _out(tmp_path, escalation="Scope is ambiguous.\n")
    )
    assert cause == "escalated"
    assert github.written() == [
        ("POST", LABEL_ADD, {"labels": ["needs-human"]}),
        ("DELETE", IN_PROGRESS_DELETE, None),
        (
            "POST",
            COMMENTS,
            {
                "body": "<!-- lane-escalation run=9001 -->\n"
                "@Osasuwu run [9001](https://github.com/Osasuwu/jarvis/actions/runs/9001) ended"
                " without a PR: the worker stopped and escalated; its note is quoted below.\n"
                "\n"
                "The worker's `escalation.md`, quoted (untrusted):\n"
                "\n"
                "```\n"
                "Scope is ambiguous.\n"
                "```\n"
                "\n"
                "Decide, then re-dispatch: remove `needs-human` and re-apply `agent:dispatch`."
                " Cause: `escalated`.\n"
            },
        ),
    ]
    # A 5xx after a committed comment must not post a second one (Decision d).
    assert github.once == [("POST", COMMENTS)]


def test_status_in_progress_is_dropped_only_when_present(github, tmp_path):
    github.issue_labels = ["afk:1-auto"]
    lane_escalation.escalate(github, _env(), _out(tmp_path, escalation="x"))
    assert [(m, p) for m, p, _ in github.written()] == [("POST", LABEL_ADD), ("POST", COMMENTS)]


def test_an_in_progress_label_already_gone_still_escalates(github, tmp_path):
    """A human removed `status:in-progress` between the read and the DELETE: a 404."""
    github.writes = {
        IN_PROGRESS_DELETE: lambda *_: http_error(404, '{"message":"Label does not exist"}')
    }
    assert lane_escalation.escalate(github, _env(), _out(tmp_path, escalation="x")) == "escalated"
    assert [(m, p) for m, p, _ in github.written()] == [
        ("POST", LABEL_ADD),
        ("DELETE", IN_PROGRESS_DELETE),
        ("POST", COMMENTS),
    ]


def test_a_crash_without_a_note_names_the_cause(github, tmp_path):
    cause = lane_escalation.escalate(github, _env(WORKER_RESULT="failure"), _out(tmp_path))
    assert cause == "crash"
    body = _comment_body(github)
    assert "ended without a PR: the worker job ended `failure` before it finished." in body
    assert "quoted" not in body


def test_a_job_that_ran_its_full_timeout_is_reported_as_a_timeout(github, tmp_path):
    github.jobs = [{"name": "intake", "started_at": "2026-10-08T09:00:00Z"}, _worker_job()]
    cause = lane_escalation.escalate(github, _env(WORKER_RESULT="cancelled"), _out(tmp_path))
    assert cause == "timeout"
    assert "the worker hit its 45-minute job timeout." in _comment_body(github)
    assert JOBS in github.reads()


def test_an_unreadable_jobs_api_falls_back_to_the_worker_result(github, tmp_path):
    github.jobs = None
    assert (
        lane_escalation.escalate(github, _env(WORKER_RESULT="cancelled"), _out(tmp_path))
        == "cancelled"
    )


@pytest.mark.parametrize(
    "answer",
    [
        http_error(404, '{"message":"Not Found"}'),
        http_error(500, "boom"),
        urllib.error.URLError("unreachable"),
        TimeoutError("timed out"),
        ValueError("empty response body for GET"),
        {"total_count": 0},
        {"jobs": []},
        {"jobs": [{"name": "intake", "started_at": "2026-10-08T09:00:00Z"}]},
        {"jobs": [_worker_job(completed=None)]},
        {"jobs": [_worker_job(started="not a time")]},
    ],
    ids=[
        "404",
        "500",
        "url-error",
        "timeout",
        "empty-body",
        "no-jobs-key",
        "no-jobs",
        "no-worker-job",
        "worker-not-completed",
        "bad-timestamp",
    ],
)
def test_a_jobs_answer_that_does_not_say_reads_as_no_duration(answer):
    api = FakeApi(responses={JOBS: answer})
    assert lane_escalation._worker_minutes(api, REPO, "9001") is None


def test_the_worker_jobs_duration_is_read_from_its_own_job():
    api = FakeApi(
        responses={
            JOBS: {
                "jobs": [
                    {
                        "name": "intake",
                        "started_at": "2026-10-08T00:00:00Z",
                        "completed_at": "2026-10-08T05:00:00Z",
                    },
                    _worker_job(completed="2026-10-08T10:30:00Z"),
                ]
            }
        }
    )
    assert lane_escalation._worker_minutes(api, REPO, "9001") == 30.0


def test_turn_limit_is_reported_from_the_workers_ending_record(github, tmp_path):
    env = _env(WORKER_RESULT="failure", WORKER_RESULT_SUBTYPE="error_max_turns")
    assert lane_escalation.escalate(github, env, _out(tmp_path)) == "max-turns"
    assert "the worker ran out of turns (limit 100)." in _comment_body(github)


def test_a_rerun_of_the_job_posts_no_second_comment(github, tmp_path):
    marker = "<!-- lane-escalation run=9001 -->\nearlier body"
    github.comments = {2011: [{"user": BOT, "body": marker}]}
    lane_escalation.escalate(github, _env(), _out(tmp_path, escalation="x"))
    assert [(m, p) for m, p, _ in github.written()] == [
        ("POST", LABEL_ADD),
        ("DELETE", IN_PROGRESS_DELETE),
    ]


@pytest.mark.parametrize(
    "forged",
    [
        {"user": "someone-else", "body": "<!-- lane-escalation run=9001 -->\nhi"},
        {"user": BOT, "body": "quoting\n<!-- lane-escalation run=9001 -->"},
        {"user": BOT, "body": "<!-- lane-escalation run=9002 -->\nother run"},
    ],
)
def test_only_the_bots_own_marker_for_this_run_suppresses_the_comment(github, tmp_path, forged):
    github.comments = {2011: [forged]}
    lane_escalation.escalate(github, _env(), _out(tmp_path, escalation="x"))
    assert [(m, p) for m, p, _ in github.written()][-1] == ("POST", COMMENTS)


def test_a_truncated_comment_listing_raises_before_the_comment(github, tmp_path):
    """The run marker could sit past the cap: no comment rather than a second one."""
    github.comments = {2011: [{"user": "someone-else", "body": "x"}] * 1000}
    with pytest.raises(load_client().ListingTruncated):
        lane_escalation.escalate(github, _env(), _out(tmp_path, escalation="x"))
    # The label lands first, as in base order; the comment never does.
    assert [(m, p) for m, p, _ in github.written()] == [
        ("POST", LABEL_ADD),
        ("DELETE", IN_PROGRESS_DELETE),
    ]
    assert len([p for p in github.reads() if p.startswith(f"{COMMENTS}?")]) == 10


def test_hostile_escalation_text_stays_inside_one_code_fence(github, tmp_path):
    hostile = "done\n```\n@everyone ping <!-- lane-escalation run=1 -->\n````\n@Osasuwu"
    lane_escalation.escalate(github, _env(), _out(tmp_path, escalation=hostile))
    lines = _comment_body(github).splitlines()
    opening = lines.index("`````")
    closing = lines.index("`````", opening + 1)
    assert lines[opening + 1 : closing] == hostile.splitlines()
    live = lines[:opening] + lines[closing + 1 :]
    assert not any("@everyone" in line or "run=1" in line for line in live)


def test_an_overlong_note_is_truncated_with_a_pointer_to_the_artifact(github, tmp_path):
    lane_escalation.escalate(github, _env(), _out(tmp_path, escalation="y" * 20000))
    body = _comment_body(github)
    quoted = body.split("```\n")[1]
    assert quoted.count("y") == 8000
    assert "[truncated; the full text is in the run's `lane-out` artifact]" in body


def test_a_note_that_is_not_utf8_is_read_with_replacement(github, tmp_path):
    out = _out(tmp_path)
    (out / "escalation.md").write_bytes(b"bad \xff byte")
    lane_escalation.escalate(github, _env(), out)
    assert "bad � byte" in _comment_body(github)


def test_nothing_in_a_run_touches_an_assignee_or_the_issue_body(github, tmp_path):
    allowed = {
        ("POST", LABEL_ADD): lambda body: body == {"labels": ["needs-human"]},
        ("DELETE", IN_PROGRESS_DELETE): lambda body: body is None,
        ("POST", COMMENTS): lambda body: set(body) == {"body"},
    }
    for result in ("success", "failure", "cancelled"):
        github.calls.clear()
        lane_escalation.escalate(github, _env(WORKER_RESULT=result), _out(tmp_path, escalation="x"))
        writes = github.written()
        assert writes
        for method, path, body in writes:
            assert (method, path) in allowed
            assert allowed[(method, path)](body)


def test_without_an_operator_the_label_and_comment_still_land_and_the_command_fails(
    github, tmp_path, monkeypatch, capsys
):
    out = _out(tmp_path, escalation="x")
    for key, value in _env(LANE_OPERATOR="", GH_TOKEN="bot-pat").items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("LANE_OUT", str(out))
    with pytest.raises(SystemExit) as exit_info:
        _main(github, ["run"])
    assert exit_info.value.code == 1
    assert [(m, p) for m, p, _ in github.written()] == [
        ("POST", LABEL_ADD),
        ("DELETE", IN_PROGRESS_DELETE),
        ("POST", COMMENTS),
    ]
    body = _comment_body(github)
    assert " @" not in body and not body.splitlines()[1].startswith("@")
    assert "::warning::LANE_OPERATOR" in capsys.readouterr().out


def test_a_configured_operator_exits_clean(github, tmp_path, monkeypatch):
    out = _out(tmp_path, escalation="x")
    for key, value in _env(GH_TOKEN="bot-pat").items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("LANE_OUT", str(out))
    tokens = []
    assert _main(github, ["run"], tokens) is None
    assert tokens == ["bot-pat"]


def test_redispatch_after_an_escalation_needs_the_human_to_clear_the_marker(github, tmp_path):
    labels = ["afk:1-auto", "agent:dispatch", "status:in-progress"]
    github.issue_labels = list(labels)
    lane_escalation.escalate(github, _env(), _out(tmp_path, escalation="x"))
    writes = github.written()
    removed = {urllib.parse.unquote(p.rsplit("/", 1)[1]) for m, p, _ in writes if m == "DELETE"}
    added = [n for m, p, b in writes if (m, p) == ("POST", LABEL_ADD) for n in b["labels"]]
    after = [n for n in labels if n not in removed] + added
    body = "Do the thing.\n\n## Acceptance criteria\n\n- [ ] it works\n"
    facts = {
        "body": body,
        "state": "open",
        "labels": after,
        "editors": ["Osasuwu"],
        "closing_prs": [],
        "blocked_by": 0,
        "label_sender": "Osasuwu",
    }
    assert lane_intake.check(facts, body, BOT)[0] == "needs-human"
    facts["labels"] = [n for n in after if n != "needs-human"]
    assert lane_intake.check(facts, body, BOT) is None


def test_run_through_main_builds_its_own_client_and_escalates(monkeypatch, tmp_path, capsys):
    """The production `_make_client`, with only the transport patched: the token, the user
    agent, every request path and the REST-to-facts mapping (PR lookup, the worker job's
    duration, the issue's labels, comment authors) are pinned at main level."""
    transport = FakeTransport(
        [
            [],  # no PR for the run's branch
            {
                "total_count": 2,
                "jobs": [
                    {
                        "name": "intake",
                        "started_at": "2026-10-08T09:00:00Z",
                        "completed_at": "2026-10-08T09:01:00Z",
                    },
                    _worker_job(),
                ],
            },
            {"number": 2011, "labels": [{"name": "status:in-progress"}, {"name": "afk:1-auto"}]},
            [{"name": "needs-human"}],
            b"",  # the label DELETE answers 204
            # The run's marker, posted by someone else: it is not the bot's comment.
            [
                {
                    "id": 3,
                    "user": {"login": "someone-else"},
                    "body": "<!-- lane-escalation run=9001 -->",
                }
            ],
            {"id": 4},
        ]
    )
    monkeypatch.setattr(load_client(), "urllib_transport", transport)
    env = {
        **_env(WORKER_RESULT="cancelled"),
        "GH_TOKEN": "bot-pat",
        "LANE_OUT": str(_out(tmp_path)),
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    assert lane_escalation.main(["lane_escalation.py", "run"]) is None
    assert [
        (r.method, r.url, r.headers["authorization"], r.headers["user-agent"])
        for r in transport.requests
    ] == [
        ("GET", f"{API}/{HEAD_QUERY}", "Bearer bot-pat", "lane-escalation"),
        ("GET", f"{API}/{JOBS}", "Bearer bot-pat", "lane-escalation"),
        ("GET", f"{API}/{ISSUE}", "Bearer bot-pat", "lane-escalation"),
        ("POST", f"{API}/{LABEL_ADD}", "Bearer bot-pat", "lane-escalation"),
        ("DELETE", f"{API}/{IN_PROGRESS_DELETE}", "Bearer bot-pat", "lane-escalation"),
        ("GET", f"{API}/{COMMENTS}?per_page=100&page=1", "Bearer bot-pat", "lane-escalation"),
        ("POST", f"{API}/{COMMENTS}", "Bearer bot-pat", "lane-escalation"),
    ]
    assert transport.requests[3].body == {"labels": ["needs-human"]}
    body = transport.requests[-1].body["body"]
    assert body.startswith("<!-- lane-escalation run=9001 -->\n@Osasuwu run [9001](")
    assert "the worker hit its 45-minute job timeout." in body
    assert capsys.readouterr().out == f"{REPO}#2011: run 9001 escalated (timeout)\n"


# --- watch: the PR side ---------------------------------------------------------------


def _pr(number=40, head="claude/issue-2011-9001", sha=SHA, source=REPO, labels=()):
    """An open PR as `GET pulls` answers it; `source` is the head repository (None: deleted)."""
    return {
        "number": number,
        "head": {"ref": head, "sha": sha, "repo": {"full_name": source} if source else None},
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


def _watch_env(watched=WATCHED):
    return {
        "GH_REPO": REPO,
        "LANE_OPERATOR": "Osasuwu",
        "LANE_BOT_LOGIN": BOT,
        "LANE_WATCHED_CHECKS": watched,
    }


def _watch(github, watched=WATCHED):
    return lane_escalation.watch(github, _watch_env(watched))


def test_a_red_required_check_on_a_lane_pr_labels_it_and_comments_once(github):
    github.open_prs = [_pr()]
    github.check_runs = {
        SHA: [_check("pytest", "failure", id_=7), _check("gitleaks", "success", 8)]
    }
    flagged, handle = _watch(github)
    assert flagged == [(40, "pytest")] and handle == "Osasuwu"
    assert github.written() == [
        ("POST", f"repos/{REPO}/issues/40/labels", {"labels": ["needs-human"]}),
        (
            "POST",
            f"repos/{REPO}/issues/40/comments",
            {
                "body": f"<!-- lane-red-check pytest {SHA} -->\n"
                "@Osasuwu required check `pytest` is red on `aaaaaaa`"
                f" (https://github.com/{REPO}/actions/runs/7/job/1).\n"
                "\n"
                "Fix it and push, or close the PR. Remove `needs-human` once you have decided.\n"
            },
        ),
    ]
    assert github.once == [("POST", f"repos/{REPO}/issues/40/comments")]


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
def test_green_pending_superseded_and_unwatched_checks_get_nothing(github, runs):
    github.open_prs = [_pr()]
    github.check_runs = {SHA: runs}
    assert _watch(github)[0] == []
    assert github.written() == []


def test_a_red_rerun_after_a_green_one_is_the_latest(github):
    github.open_prs = [_pr()]
    github.check_runs = {SHA: [_check("pytest", "success", 1), _check("pytest", "timed_out", 2)]}
    assert _watch(github)[0] == [(40, "pytest")]


@pytest.mark.parametrize(
    "pr",
    [
        _pr(head="feat/2011-thing"),
        _pr(source="someone-else/jarvis"),
        _pr(source=None),
    ],
    ids=["not-a-lane-branch", "fork", "deleted-head-repo"],
)
def test_non_lane_and_cross_repo_prs_are_not_read_at_all(github, pr):
    github.open_prs = [pr]
    github.check_runs = {SHA: [_check("pytest", "failure")]}
    assert _watch(github)[0] == []
    assert github.calls == [("GET", f"{OPEN_PRS}&per_page=100&page=1", None)]


def test_the_head_repository_is_compared_without_case(github):
    github.open_prs = [_pr(source="osasuwu/JARVIS")]
    github.check_runs = {SHA: [_check("pytest", "failure")]}
    assert _watch(github)[0] == [(40, "pytest")]


def test_one_comment_per_check_and_head_sha(github):
    github.open_prs = [_pr(labels=["needs-human"])]
    github.check_runs = {SHA: [_check("pytest", "failure", 1), _check("gitleaks", "failure", 2)]}
    github.comments = {40: [{"user": BOT, "body": f"<!-- lane-red-check pytest {SHA} -->\nold"}]}
    _watch(github)
    writes = github.written()
    assert [(m, p) for m, p, _ in writes] == [("POST", f"repos/{REPO}/issues/40/comments")]
    assert "required check `gitleaks` is red" in writes[0][2]["body"]


def test_a_second_event_for_the_same_red_head_writes_nothing(github):
    github.open_prs = [_pr(labels=["needs-human"])]
    github.check_runs = {SHA: [_check("pytest", "failure", 1)]}
    github.comments = {40: [{"user": BOT, "body": f"<!-- lane-red-check pytest {SHA} -->\nold"}]}
    _watch(github)
    assert github.written() == []


def test_a_new_head_sha_is_reported_again(github):
    new = "b" * 40
    github.open_prs = [_pr(sha=new, labels=["needs-human"])]
    github.check_runs = {new: [_check("pytest", "failure", 1)]}
    github.comments = {40: [{"user": BOT, "body": f"<!-- lane-red-check pytest {SHA} -->\nold"}]}
    _watch(github)
    assert [(m, p) for m, p, _ in github.written()] == [
        ("POST", f"repos/{REPO}/issues/40/comments")
    ]


def test_a_full_open_pr_listing_flags_what_was_read_then_fails(github, capsys):
    """Past 1000 open PRs the rest is unread: what was read is flagged, then the run is red."""
    github.open_prs = [_pr(number=n, head=f"feat/{n}") for n in range(1000, 2000)]
    github.open_prs[0] = _pr(number=40)
    github.open_prs[-1] = _pr(number=41)
    github.check_runs = {SHA: [_check("pytest", "failure", 1)]}
    with pytest.raises(load_client().ListingTruncated):
        _watch(github)
    assert [(m, p) for m, p, _ in github.written()] == [
        ("POST", f"repos/{REPO}/issues/40/labels"),
        ("POST", f"repos/{REPO}/issues/40/comments"),
        ("POST", f"repos/{REPO}/issues/41/labels"),
        ("POST", f"repos/{REPO}/issues/41/comments"),
    ]
    assert len([p for p in github.reads() if p.startswith(f"{OPEN_PRS}&")]) == 10
    assert capsys.readouterr().out.endswith(
        f"{REPO}: red required checks on lane PRs: [(40, 'pytest'), (41, 'pytest')]\n"
    )


def test_a_truncated_check_run_listing_stops_the_watch_before_any_write(github):
    other = "c" * 40
    github.open_prs = [_pr(number=40), _pr(number=41, sha=other)]
    github.check_runs = {
        SHA: [_check(f"matrix-{n}", "success", n) for n in range(1000)],
        other: [_check("pytest", "failure", 1)],
    }
    with pytest.raises(load_client().ListingTruncated):
        _watch(github, "pytest")
    assert github.written() == []
    assert not [p for p in github.reads() if other in p]


def test_a_truncated_pr_comment_listing_raises_before_the_red_comment(github):
    github.open_prs = [_pr()]
    github.check_runs = {SHA: [_check("pytest", "failure", 1)]}
    github.comments = {40: [{"user": "someone-else", "body": "x"}] * 1000}
    with pytest.raises(load_client().ListingTruncated):
        _watch(github)
    assert [(m, p) for m, p, _ in github.written()] == [("POST", f"repos/{REPO}/issues/40/labels")]


_GATE_AT = "2026-10-08T10:10:00Z"


def _review(status="completed", at="2026-10-08T10:05:00Z", title="Code Review"):
    return {"status": status, "updated_at": at, "display_title": title}


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
def test_a_red_code_gate_before_the_review_settles_is_not_reported(github, reviews):
    github.open_prs = [_pr()]
    github.check_runs = {SHA: [_check("code-gate", "failure", 5, at=_GATE_AT)]}
    github.review_runs = reviews
    assert _watch(github)[0] == []
    assert github.written() == []


def test_a_red_code_gate_after_the_review_settled_is_reported(github):
    github.open_prs = [_pr()]
    github.check_runs = {SHA: [_check("code-gate", "failure", 5, at=_GATE_AT)]}
    github.review_runs = [_review()]
    assert _watch(github)[0] == [(40, "code-gate")]
    assert f"{REVIEWS}?head_sha={SHA}&per_page=100" in github.reads()


def test_a_dispatched_review_counts_by_its_run_title(github):
    github.open_prs = [_pr()]
    github.check_runs = {SHA: [_check("code-gate", "failure", 5, at=_GATE_AT)]}
    github.dispatched_runs = [
        _review(title=f"Code review PR #40 @ {SHA}"),
        _review(status="in_progress", title=f"Code review PR #41 @ {SHA}"),
    ]
    assert _watch(github)[0] == [(40, "code-gate")]


def test_watch_without_an_operator_exits_cleanly_when_nothing_is_red(github, monkeypatch, capsys):
    github.open_prs = [_pr()]
    github.check_runs = {SHA: [_check("pytest", "success", 1)]}
    for key, value in {**_watch_env(), "GH_TOKEN": "bot-pat"}.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("LANE_OPERATOR", raising=False)
    _main(github, ["watch"])  # must not raise SystemExit
    assert github.written() == []
    assert "::warning::" not in capsys.readouterr().out


def test_watch_without_an_operator_still_flags_and_exits_failing(github, monkeypatch, capsys):
    github.open_prs = [_pr()]
    github.check_runs = {SHA: [_check("pytest", "failure", 1)]}
    for key, value in {**_watch_env(), "GH_TOKEN": "bot-pat"}.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("LANE_OPERATOR", raising=False)
    with pytest.raises(SystemExit) as exit_info:
        _main(github, ["watch"])
    assert exit_info.value.code == 1
    writes = github.written()
    assert [(m, p) for m, p, _ in writes] == [
        ("POST", f"repos/{REPO}/issues/40/labels"),
        ("POST", f"repos/{REPO}/issues/40/comments"),
    ]
    assert writes[1][2]["body"].splitlines()[1].startswith("required check")
    assert "::warning::LANE_OPERATOR" in capsys.readouterr().out


def test_the_watched_checks_come_from_the_caller_not_from_the_script(github):
    github.open_prs = [_pr()]
    github.check_runs = {SHA: [_check("pytest", "failure", 1), _check("lint", "failure", 2)]}
    assert _watch(github, "lint")[0] == [(40, "lint")]


def test_the_code_review_runs_are_read_only_when_code_gate_is_watched(github):
    github.open_prs = [_pr()]
    github.check_runs = {SHA: [_check("pytest", "failure", 1)]}
    _watch(github, "pytest")
    assert not [p for p in github.reads() if "code-review.yml" in p]


@pytest.mark.parametrize("value", [None, "", " , "])
def test_watch_with_no_watched_checks_fails_naming_the_variable(github, monkeypatch, capsys, value):
    github.open_prs = [_pr()]
    monkeypatch.setenv("GH_REPO", REPO)
    monkeypatch.setenv("GH_TOKEN", "bot-pat")
    monkeypatch.setenv("LANE_BOT_LOGIN", BOT)
    monkeypatch.delenv("LANE_WATCHED_CHECKS", raising=False)
    if value is not None:
        monkeypatch.setenv("LANE_WATCHED_CHECKS", value)
    with pytest.raises(SystemExit) as exit_info:
        _main(github, ["watch"])
    assert exit_info.value.code == 1
    assert "::error::LANE_WATCHED_CHECKS" in capsys.readouterr().out
    assert github.calls == []


@pytest.mark.parametrize("command", ["run", "watch"])
def test_escalation_without_a_bot_login_fails_naming_the_variable(
    github, monkeypatch, capsys, command
):
    monkeypatch.setenv("GH_REPO", REPO)
    monkeypatch.setenv("GH_TOKEN", "bot-pat")
    monkeypatch.setenv("LANE_WATCHED_CHECKS", WATCHED)
    monkeypatch.delenv("LANE_BOT_LOGIN", raising=False)
    tokens = []
    with pytest.raises(SystemExit) as exit_info:
        _main(github, [command], tokens)
    assert exit_info.value.code == 1
    assert "::error::lane_escalation: LANE_BOT_LOGIN" in capsys.readouterr().out
    assert tokens == [] and github.calls == []


def test_an_unknown_command_prints_usage_and_builds_no_client(github, monkeypatch):
    monkeypatch.setenv("LANE_BOT_LOGIN", BOT)
    monkeypatch.setenv("GH_TOKEN", "bot-pat")
    tokens = []
    with pytest.raises(SystemExit) as exit_info:
        _main(github, ["tally"], tokens)
    assert exit_info.value.code == "usage: lane_escalation.py run|watch"
    assert tokens == []


def test_watch_with_a_rejected_token_shows_the_reason_in_the_log(capsys):
    """#2057: the reason a call failed reaches the job log, now from the client (Decision c)."""
    url = f"{API}/{OPEN_PRS}&per_page=100&page=1"
    transport = FakeTransport({url: [http_error(401, '{"message":"Bad credentials"}')]})
    api = load_client().Client("t", user_agent="t", transport=transport)
    with pytest.raises(urllib.error.HTTPError) as raised:
        lane_escalation.watch(api, _watch_env())
    assert raised.value.code == 401
    assert capsys.readouterr().err == (
        f'GET {OPEN_PRS}&per_page=100&page=1 -> HTTP 401: {{"message":"Bad credentials"}}\n'
    )


def test_watch_through_main_builds_its_own_client_and_flags_the_lane_pr(monkeypatch, capsys):
    """The production `_make_client`, with only the transport patched: the token, the user
    agent, every request path and the REST-to-facts mapping (head repository, branch and
    SHA, labels, check runs, Code Review runs by title, comment authors) are pinned at
    main level."""
    other = "d" * 40
    comments_40 = f"{API}/repos/{REPO}/issues/40/comments"
    transport = FakeTransport(
        {
            f"{API}/{OPEN_PRS}&per_page=100&page=1": [
                [
                    _pr(number=40, source="osasuwu/Jarvis", labels=["bug"]),
                    _pr(number=41, sha=other, source="fork/jarvis"),
                    _pr(number=42, sha=other, source=None),
                    _pr(number=43, sha=other, head="feat/43"),
                ]
            ],
            f"{API}/{REVIEWS}?head_sha={SHA}&per_page=100": [{"workflow_runs": []}],
            f"{API}/{REVIEWS}?event=workflow_dispatch&per_page=100": [
                {
                    "workflow_runs": [
                        _review(title=f"Code review PR #40 @ {SHA}"),
                        _review(status="in_progress", title=f"Code review PR #41 @ {SHA}"),
                    ]
                }
            ],
            f"{API}/repos/{REPO}/commits/{SHA}/check-runs?per_page=100&page=1": [
                {
                    "total_count": 2,
                    "check_runs": [
                        _check("code-gate", "failure", 5, at=_GATE_AT),
                        _check("pytest", "failure", 6),
                    ],
                }
            ],
            f"{API}/repos/{REPO}/issues/40/labels": [[{"name": "bug"}, {"name": "needs-human"}]],
            f"{comments_40}?per_page=100&page=1": [
                [{"id": 1, "user": {"login": BOT}, "body": f"<!-- lane-red-check pytest {SHA} -->"}]
            ],
            comments_40: [{"id": 2}],
        }
    )
    monkeypatch.setattr(load_client(), "urllib_transport", transport)
    for key, value in {**_watch_env(), "GH_TOKEN": "bot-pat"}.items():
        monkeypatch.setenv(key, value)
    assert lane_escalation.main(["lane_escalation.py", "watch"]) is None
    assert [
        (r.method, r.url, r.headers["authorization"], r.headers["user-agent"])
        for r in transport.requests
    ] == [
        ("GET", f"{API}/{OPEN_PRS}&per_page=100&page=1", "Bearer bot-pat", "lane-escalation"),
        (
            "GET",
            f"{API}/{REVIEWS}?head_sha={SHA}&per_page=100",
            "Bearer bot-pat",
            "lane-escalation",
        ),
        (
            "GET",
            f"{API}/{REVIEWS}?event=workflow_dispatch&per_page=100",
            "Bearer bot-pat",
            "lane-escalation",
        ),
        (
            "GET",
            f"{API}/repos/{REPO}/commits/{SHA}/check-runs?per_page=100&page=1",
            "Bearer bot-pat",
            "lane-escalation",
        ),
        ("POST", f"{API}/repos/{REPO}/issues/40/labels", "Bearer bot-pat", "lane-escalation"),
        ("GET", f"{comments_40}?per_page=100&page=1", "Bearer bot-pat", "lane-escalation"),
        ("POST", comments_40, "Bearer bot-pat", "lane-escalation"),
    ]
    assert transport.requests[4].body == {"labels": ["needs-human"]}
    # pytest already carries the bot's marker for this SHA; only code-gate is new.
    assert (
        transport.requests[-1]
        .body["body"]
        .startswith(
            f"<!-- lane-red-check code-gate {SHA} -->\n@Osasuwu required check `code-gate` is red"
        )
    )
    assert capsys.readouterr().out == (
        f"{REPO}: red required checks on lane PRs: [(40, 'pytest'), (40, 'code-gate')]\n"
    )
