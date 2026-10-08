"""The `risk-tier` required check (.github/scripts/risk_tier.py, #2004).

The PR body's `Risk:` line is a merge hold: the check goes red on a bad line, floors the tier by
the diff, and holds HIGH/CRITICAL until an admin human approves the current head. These tests run
the real script against a fake GitHub API and the real workflow file; expected values are literals.
"""

import importlib.util
import json
import re
import shutil
from pathlib import Path

import pytest
import yaml

_root = next(p for p in Path(__file__).resolve().parents if (p / ".github" / "scripts").is_dir())


def _load(name):
    spec = importlib.util.spec_from_file_location(
        name, _root / ".github" / "scripts" / f"{name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


risk_tier = _load("risk_tier")
lane_publish = _load("lane_publish")

REPO = "Osasuwu/jarvis"
HEAD = "a" * 40
OLD = "b" * 40
GRAMMAR_LINE = "Risk: LOW|MEDIUM|HIGH|CRITICAL — <reason>"
BASE_LIST = {
    REPO: {
        "hitl": ["AGENTS.md"],
        "guarded": ["supabase/**"],
        "machinery": [".github/**", "docs/security/**"],
    }
}
GOOD_BODY = "Refs #1\n\nRisk: LOW — small"


@pytest.fixture
def base(tmp_path):
    """A base-branch checkout: a literal protected list and the real plan_review.yaml."""
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "protected-paths.json").write_text(json.dumps(BASE_LIST), "utf-8")
    shutil.copy(_root / "config" / "plan_review.yaml", tmp_path / "config" / "plan_review.yaml")
    return tmp_path


class FakeGitHub:
    """GET-only GitHub API; unknown routes fail the test instead of answering."""

    def __init__(
        self, body=GOOD_BODY, files=(), reviews=(), permissions=None, head=HEAD, changed_files=None
    ):
        self.pr = {
            "body": body,
            "head": {"sha": head},
            "changed_files": len(files) if changed_files is None else changed_files,
        }
        self.files = list(files)
        self.reviews = list(reviews)
        self.permissions = permissions or {}

    def __call__(self, path):
        route, _, query = path.partition("?")
        prefix = f"repos/{REPO}/pulls/7"
        if route == prefix:
            return self.pr
        if route in (f"{prefix}/files", f"{prefix}/reviews"):
            params = dict(q.split("=") for q in query.split("&"))
            per_page, page = int(params["per_page"]), int(params["page"])
            items = self.files if route.endswith("/files") else self.reviews
            return items[(page - 1) * per_page : page * per_page]
        m = re.fullmatch(rf"repos/{REPO}/collaborators/([^/]+)/permission", route)
        if m:
            if m.group(1) not in self.permissions:
                raise RuntimeError("HTTP 404")
            return {"permission": self.permissions[m.group(1)]}
        raise AssertionError(f"unexpected API call: {path}")


def _file(name, patch="@@ -0,0 +1 @@\n+x", status="modified", additions=1, deletions=0, **extra):
    f = {"filename": name, "status": status, "additions": additions, "deletions": deletions}
    if patch is not None:
        f["patch"] = patch
    return {**f, **extra}


def _review(login, state, commit=HEAD, user_type="User"):
    return {"user": {"login": login, "type": user_type}, "state": state, "commit_id": commit}


def _run(base, api, head=HEAD):
    return risk_tier.evaluate(api, REPO, 7, head, base, "osasuwu-bot")


def _computed(base, files, changed_files=None):
    return risk_tier.computed_tier(
        files, len(files) if changed_files is None else changed_files, REPO, base
    )


# --- AC1: the Risk line grammar ----------------------------------------------------------

_ROW = re.compile(r"^\| `(?P<example>[^`]+)` \| (?P<verdict>\w+) \|$")


def _doc_rows():
    text = (_root / ".github" / "scripts" / "risk_tier.md").read_text(encoding="utf-8")
    rows = [m for m in map(_ROW.match, text.splitlines()) if m]
    return [(m["example"].replace("<br>", "\n"), m["verdict"]) for m in rows]


def test_every_documented_grammar_row_is_parsed_as_documented():
    rows = _doc_rows()
    assert len(rows) >= 20  # the table was found, not an empty walk
    wrong = []
    for example, verdict in rows:
        tier, problem = risk_tier.parse_declared(example)
        got = tier if tier else problem
        if got != (verdict if verdict in risk_tier.SEVERITY else verdict):
            wrong.append(f"{example!r}: documented {verdict}, parsed {got}")
    assert wrong == []


def test_documented_tier_rows_parse_to_the_same_tier_in_the_lenient_lane_parser():
    one_liners = [(ex, v) for ex, v in _doc_rows() if v in risk_tier.SEVERITY and "\n" not in ex]
    assert len(one_liners) >= 7
    wrong = [ex for ex, v in one_liners if lane_publish.parse_risk(ex) != v]
    assert wrong == []


def test_the_unfilled_pr_template_line_is_malformed_not_missing():
    template = (_root / ".github" / "PULL_REQUEST_TEMPLATE.md").read_text(encoding="utf-8")
    assert risk_tier.parse_declared(template) == (None, "malformed")


def test_a_valid_low_line_on_a_clean_diff_is_green(base):
    api = FakeGitHub(files=[_file("scripts/x.py")])
    ok, messages = _run(base, api)
    assert (ok, messages) == (True, ["declared LOW, computed LOW, final LOW"])


def test_a_valid_medium_line_on_a_clean_diff_is_green_without_any_review(base):
    api = FakeGitHub(body="Risk: MEDIUM — new helper", files=[_file("scripts/x.py")])
    ok, messages = _run(base, api)
    assert (ok, messages) == (True, ["declared MEDIUM, computed LOW, final MEDIUM"])


@pytest.mark.parametrize(
    ("body", "problem"),
    [
        ("Refs #1", "missing"),
        ("Risk: LOW", "malformed"),
        ("Risk: LOW — a\nRisk: HIGH — b", "duplicate"),
    ],
)
def test_a_bad_risk_line_is_red_and_names_the_expected_grammar(base, body, problem):
    ok, messages = _run(base, FakeGitHub(body=body, files=[_file("scripts/x.py")]))
    assert (ok, messages) == (
        False,
        [
            f"The PR body has a {problem} Risk line. Expected exactly one line "
            f"`{GRAMMAR_LINE}` (grammar and examples: .github/scripts/risk_tier.md)."
        ],
    )


# --- AC2: the computed tier floors the declared one --------------------------------------


@pytest.mark.parametrize(
    "path",
    ["AGENTS.md", ".github/workflows/x.yml", "supabase/x.sql"],
    ids=["hitl", "machinery", "guarded"],
)
def test_a_path_in_any_bucket_of_the_base_list_reads_high_whatever_the_declared_line(base, path):
    ok, messages = _run(base, FakeGitHub(body="Risk: LOW — x", files=[_file(path)]))
    assert ok is False
    assert messages[0].startswith(
        f"declared LOW, computed HIGH, final HIGH\n  - protected path(s): {path}"
    )


@pytest.mark.parametrize(
    "path",
    [
        ".gitleaksignore",
        "SECURITY.md",
        ".github/workflows/x.yml",
        "config/plan_review.yaml",
        "pyproject.toml",
    ],
)
def test_the_real_protected_list_floors_the_gate_machinery_at_high(path):
    tier, reasons = risk_tier.path_tier([path], REPO, _root)
    assert (tier, reasons) == ("HIGH", [f"protected path(s): {path}"])


def test_a_rename_out_of_a_protected_path_reads_high(base):
    files = [_file("scripts/moved.py", status="renamed", previous_filename="AGENTS.md")]
    tier, reasons = _computed(base, files)
    assert (tier, reasons[0]) == ("HIGH", "protected path(s): AGENTS.md")


def test_a_corrupt_protected_list_reads_high(base):
    (base / "config" / "protected-paths.json").write_text("{", "utf-8")
    tier, reasons = _computed(base, [_file("scripts/x.py")])
    assert tier == "HIGH"
    assert len(reasons) == 1
    assert reasons[0].startswith("protected-path list unreadable at base (")


# A host that has not adopted the lane has no protected list: every diff is HIGH and the check
# output says why and where the fix is (D2, D7; docs/reference/lane-host-setup.md).
def test_a_host_without_a_protected_list_reads_high_with_the_reason(base):
    (base / "config" / "protected-paths.json").unlink()
    assert _computed(base, [_file("scripts/x.py")]) == (
        "HIGH",
        [
            "config/protected-paths.json not found at the base commit: every diff is HIGH "
            "until the host adds it (D2, docs/reference/lane-host-setup.md)"
        ],
    )


def test_a_host_list_without_an_entry_for_the_repo_reads_high_naming_the_repo(base):
    (base / "config" / "protected-paths.json").write_text(
        json.dumps({"Other/repo": {"hitl": []}}), "utf-8"
    )
    assert _computed(base, [_file("scripts/x.py")]) == (
        "HIGH",
        [
            "config/protected-paths.json has no entry for Osasuwu/jarvis at the base commit: "
            "every diff is HIGH until the host adds it (D2, docs/reference/lane-host-setup.md)"
        ],
    )


def test_an_unset_host_root_reads_high_with_its_own_reason():
    assert risk_tier.path_tier(["scripts/x.py"], REPO, None) == (
        "HIGH",
        [
            "RISK_TIER_HOST_ROOT is not set: no host checkout to read config/protected-paths.json from"
        ],
    )


def test_a_path_only_the_hosts_own_list_names_reads_high(tmp_path):
    host = tmp_path / "host"
    (host / "config").mkdir(parents=True)
    (host / "config" / "protected-paths.json").write_text(
        json.dumps({REPO: {"guarded": ["host_only/**"]}}), "utf-8"
    )
    assert risk_tier.path_tier(["host_only/a.py"], REPO, host) == (
        "HIGH",
        ["protected path(s): host_only/a.py"],
    )
    assert risk_tier.path_tier(["AGENTS.md"], REPO, host) == ("LOW", [])


def test_the_classifier_config_comes_from_the_code_not_the_host(base):
    (base / "config" / "plan_review.yaml").unlink()  # a host carries none; the code checkout does
    assert _computed(base, [_file("scripts/a.py"), _file("agents/b.py")]) == (
        "MEDIUM",
        ["classifier ordinal 2"],
    )


def test_a_files_listing_shorter_than_changed_files_reads_high(base):
    tier, reasons = _computed(base, [_file("scripts/x.py")], changed_files=3000)
    assert (tier, reasons) == ("HIGH", ["only 1 of 3000 changed files listable: fail closed"])


def test_a_files_listing_is_read_past_the_first_page(base):
    files = [_file(f"scripts/f{i}.py") for i in range(150)]
    assert _computed(
        base,
        risk_tier._paged(FakeGitHub(files=files), f"repos/{REPO}/pulls/7/files"),
        changed_files=150,
    ) == ("LOW", [])


def test_two_production_areas_read_medium_through_the_classifier(base):
    files = [_file("scripts/a.py"), _file("agents/b.py")]
    assert _computed(base, files) == ("MEDIUM", ["classifier ordinal 2"])


def test_the_docs_only_exemption_does_not_lower_a_protected_path(base):
    tier, reasons = _computed(base, [_file("docs/security/agent-boundaries.md")])
    assert (tier, reasons) == ("HIGH", ["protected path(s): docs/security/agent-boundaries.md"])


def test_an_unreadable_plan_review_config_reads_high(base, tmp_path):
    code = tmp_path / "code"
    (code / "config").mkdir(parents=True)
    (code / "config" / "plan_review.yaml").write_text("not: [valid", "utf-8")
    tier, reasons = risk_tier.computed_tier([_file("scripts/x.py")], 1, REPO, base, code_root=code)
    assert tier == "HIGH"
    assert reasons[0].startswith("plan_review.yaml unreadable (")


# --- AC3: test weakening -----------------------------------------------------------------


def test_a_removed_test_function_reads_high(base):
    files = [_file("tests/test_a.py", patch="@@ -1,2 +0,0 @@\n-def test_old():\n-    pass")]
    assert _computed(base, files) == ("HIGH", ["test function removed: test_old"])


def test_a_test_function_moved_to_another_file_does_not(base):
    files = [
        _file("tests/test_a.py", patch="@@ -1 +0,0 @@\n-def test_moved():"),
        _file("tests/test_b.py", patch="@@ -0,0 +1 @@\n+def test_moved():"),
    ]
    assert _computed(base, files) == ("LOW", [])


def test_a_removed_test_function_in_a_non_test_named_file_under_tests_reads_high(base):
    files = [_file("tests/helpers.py", patch="@@ -1,2 +0,0 @@\n-def test_old():\n-    pass")]
    assert _computed(base, files) == ("HIGH", ["test function removed: test_old"])


def test_a_test_file_renamed_out_of_the_test_set_reads_high(base):
    files = [_file("docs/a.txt", patch=None, status="renamed", previous_filename="tests/test_a.py")]
    assert _computed(base, files) == (
        "HIGH",
        ["test file renamed out of the test set: tests/test_a.py"],
    )


def test_a_pure_rename_between_test_files_is_not_an_unreadable_diff(base):
    files = [
        _file(
            "tests/test_b.py",
            patch=None,
            status="renamed",
            previous_filename="tests/test_a.py",
            additions=0,
            changes=0,
        )
    ]
    assert _computed(base, files) == ("LOW", [])


def test_a_renamed_test_file_with_edits_but_no_patch_still_reads_high(base):
    files = [
        _file(
            "tests/test_b.py",
            patch=None,
            status="renamed",
            previous_filename="tests/test_a.py",
            changes=3,
        )
    ]
    assert _computed(base, files) == ("HIGH", ["test file with no readable diff: tests/test_b.py"])


def test_a_newline_in_a_file_name_cannot_start_a_workflow_command_line(base):
    files = [_file("tests/a\n::stop-commands::x.py", patch=None, status="removed")]
    tier, reasons = _computed(base, files)
    assert (tier, reasons) == ("HIGH", ["test file removed: tests/a\\n::stop-commands::x.py"])
    assert not any(line.startswith("::") for r in reasons for line in r.split("\n"))


def test_adding_a_test_function_does_not(base):
    files = [_file("tests/test_a.py", patch="@@ -0,0 +1 @@\n+def test_new():")]
    assert _computed(base, files) == ("LOW", [])


def test_every_listed_skip_marker_added_to_a_test_file_reads_high(base):
    markers = [
        "@pytest.mark.skip(reason='x')",
        "@pytest.mark.skipif(True, reason='x')",
        "@mark.skipif(True, reason='x')",
        "@pytest.mark.xfail",
        "    pytest.skip('x')",
        "pytest.importorskip('yaml')",
        "@unittest.skipIf(True, 'x')",
        "collect_ignore = ['a.py']",
    ]
    not_high = []
    for marker in markers:
        files = [_file("tests/test_a.py", patch=f"@@ -0,0 +1 @@\n+{marker}")]
        tier, _ = _computed(base, files)
        if tier != "HIGH":
            not_high.append(marker)
    assert not_high == []


def test_a_skip_marker_in_a_non_test_file_does_not(base):
    files = [_file("scripts/x.py", patch="@@ -1 +1 @@\n-def test_helper():\n+# pytest.mark.skip")]
    assert _computed(base, files) == ("LOW", [])


def test_a_removed_test_file_reads_high(base):
    files = [_file("tests/test_a.py", status="removed", patch="@@ -1 +0,0 @@\n-x", deletions=1)]
    assert _computed(base, files) == ("HIGH", ["test file removed: tests/test_a.py"])


def test_a_test_file_without_a_readable_diff_reads_high(base):
    files = [_file("tests/test_big.py", patch=None)]
    assert _computed(base, files) == (
        "HIGH",
        ["test file with no readable diff: tests/test_big.py"],
    )


# --- AC4: the release is an admin human's approval at the current head -------------------

HIGH_FILES = [_file("AGENTS.md")]


@pytest.fixture
def high(base):
    """Evaluate a PR that touches AGENTS.md (HIGH by path) with the given reviews."""

    def run(reviews, permissions, body="Risk: HIGH — rules file", head=HEAD, files=HIGH_FILES):
        api = FakeGitHub(body=body, files=files, reviews=reviews, permissions=permissions)
        return risk_tier.evaluate(api, REPO, 7, head, base, "osasuwu-bot")

    return run


def test_an_admin_approval_on_the_current_head_releases_a_high_pr(high):
    ok, messages = high([_review("alice", "APPROVED")], {"alice": "admin"})
    assert ok is True
    assert messages[-1] == "released by an APPROVED review from admin alice at aaaaaaa"


@pytest.mark.parametrize(
    ("reviews", "permissions"),
    [
        ([_review("alice", "APPROVED", commit=OLD)], {"alice": "admin"}),
        ([_review("osasuwu-bot", "APPROVED")], {"osasuwu-bot": "admin"}),
        ([_review("ci-app", "APPROVED", user_type="Bot")], {"ci-app": "admin"}),
        ([_review("bob", "APPROVED")], {"bob": "write"}),
        ([_review("alice", "APPROVED"), _review("alice", "CHANGES_REQUESTED")], {"alice": "admin"}),
        ([_review("alice", "APPROVED"), _review("alice", "DISMISSED")], {"alice": "admin"}),
        ([_review("alice", "COMMENTED")], {"alice": "admin"}),
        ([_review("alice", "APPROVED")], {}),
        ([], {}),
    ],
    ids=[
        "old head",
        "the lane's bot",
        "a Bot account",
        "not admin",
        "changes requested later",
        "dismissed",
        "comment only",
        "permission lookup fails",
        "no reviews",
    ],
)
def test_nothing_but_an_admin_humans_approval_at_head_releases_a_high_pr(
    high, reviews, permissions
):
    ok, messages = high(reviews, permissions)
    assert ok is False
    assert messages[-1] == (
        "HIGH holds until an admin human (not osasuwu-bot) leaves an APPROVED review on the "
        "current head aaaaaaa; a new push needs a new approval. See "
        ".github/scripts/risk_tier.md (residual risks)."
    )


def test_a_later_approval_and_an_unrelated_comment_still_release(high):
    reviews = [
        _review("alice", "CHANGES_REQUESTED", commit=OLD),
        _review("alice", "APPROVED"),
        _review("alice", "COMMENTED"),
    ]
    ok, _ = high(reviews, {"alice": "admin"})
    assert ok is True


def test_a_declared_critical_line_holds_a_clean_diff(high):
    ok, messages = high([], {}, body="Risk: CRITICAL — data loss", files=[_file("scripts/x.py")])
    assert ok is False
    assert messages[0] == "declared CRITICAL, computed LOW, final CRITICAL"
    assert messages[-1].startswith("CRITICAL holds until an admin human")


def test_an_event_for_a_head_that_has_since_moved_is_red_as_superseded(high):
    ok, messages = high([_review("alice", "APPROVED")], {"alice": "admin"}, head=OLD)
    assert (ok, messages) == (
        False,
        ["head moved to aaaaaaa (event was bbbbbbb): superseded by a newer push"],
    )


# --- main(): the exit code and the annotation --------------------------------------------


def _main_env(monkeypatch, host):
    env = {
        "GITHUB_REPOSITORY": REPO,
        "PR_NUMBER": "7",
        "HEAD_SHA": HEAD,
        "LANE_BOT_LOGIN": "osasuwu-bot",
        "RISK_TIER_HOST_ROOT": str(host),
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)


@pytest.mark.parametrize(("body", "code"), [("Risk: LOW — x", 0), ("Refs #1", 1)])
def test_main_exits_with_the_verdict_and_annotates_a_failure(monkeypatch, capsys, base, body, code):
    api = FakeGitHub(body=body, files=[_file("scripts/x.py")])
    _main_env(monkeypatch, base)
    monkeypatch.setattr(risk_tier, "_github_get", api)
    with pytest.raises(SystemExit) as exit_info:
        risk_tier.main()
    assert exit_info.value.code == code
    out = capsys.readouterr().out
    assert ("::error::The PR body has a missing Risk line." in out) == (code == 1)


def test_main_reads_the_protected_list_from_the_host_root(monkeypatch, capsys, tmp_path):
    host = tmp_path / "host"
    (host / "config").mkdir(parents=True)
    (host / "config" / "protected-paths.json").write_text(
        json.dumps({REPO: {"guarded": ["scripts/**"]}}), "utf-8"
    )
    _main_env(monkeypatch, host)
    monkeypatch.setattr(
        risk_tier, "_github_get", FakeGitHub(body="Risk: LOW — x", files=[_file("scripts/x.py")])
    )
    with pytest.raises(SystemExit) as exit_info:
        risk_tier.main()
    assert exit_info.value.code == 1
    assert "computed HIGH" in capsys.readouterr().out


def test_main_without_a_bot_login_fails_naming_the_variable(monkeypatch, capsys, base):
    _main_env(monkeypatch, base)
    monkeypatch.setenv("LANE_BOT_LOGIN", "")
    monkeypatch.setattr(risk_tier, "_github_get", FakeGitHub(files=[_file("scripts/x.py")]))
    with pytest.raises(SystemExit) as exit_info:
        risk_tier.main()
    assert exit_info.value.code == 1
    assert capsys.readouterr().out.strip() == (
        "::error::risk-tier: LANE_BOT_LOGIN is empty; the calling workflow must pass the lane's "
        "bot login"
    )


# --- AC5: the workflow ------------------------------------------------------------------

WORKFLOW = yaml.safe_load(
    (_root / ".github" / "workflows" / "pr-body-check.yml").read_text(encoding="utf-8")
)
TRIGGERS = WORKFLOW.get("on", WORKFLOW.get(True))  # PyYAML reads the bare key `on` as True


def _job():
    return WORKFLOW["jobs"]["risk-tier"]


def test_the_check_context_is_the_job_id_and_it_re_runs_on_reviews():
    assert "name" not in _job()  # a `name:` would change the check context from `risk-tier`
    assert TRIGGERS["pull_request_review"]["types"] == ["submitted", "dismissed"]
    assert TRIGGERS["pull_request"]["types"] == ["opened", "edited", "reopened", "synchronize"]
    assert "pull_request_target" not in TRIGGERS


def test_the_check_only_ever_checks_out_the_base_branch():
    checkouts = [s for s in _job()["steps"] if s.get("uses", "").startswith("actions/checkout@")]
    assert len(checkouts) == 1
    assert checkouts[0]["with"]["ref"] == "${{ github.event.pull_request.base.ref }}"
    assert checkouts[0]["with"]["persist-credentials"] is False


def test_no_pr_text_is_interpolated_into_a_shell_step():
    runs = [s["run"] for s in _job()["steps"] if "run" in s]
    assert any(r.rstrip().endswith("python .github/scripts/risk_tier.py") for r in runs)
    assert [r for r in runs if "${{" in r] == []


def test_the_job_is_time_boxed_and_names_a_base_without_the_script():
    job = _job()
    assert job["timeout-minutes"] == 10
    guard = [s["run"] for s in job["steps"] if "risk_tier.py" in s.get("run", "")]
    assert len(guard) == 1
    assert "[ ! -f .github/scripts/risk_tier.py ]" in guard[0]
    assert "::error::risk-tier: the base branch has no .github/scripts/risk_tier.py" in guard[0]


def test_the_in_place_job_names_its_host_root_and_the_bot():
    (step,) = [s for s in _job()["steps"] if "risk_tier.py" in s.get("run", "")]
    assert step["env"]["RISK_TIER_HOST_ROOT"] == "${{ github.workspace }}"
    assert step["env"]["LANE_BOT_LOGIN"] == "osasuwu-bot"


# --- the composite action a host repo calls (#2013, D7) ----------------------------------

ACTION = yaml.safe_load(
    (_root / ".github" / "actions" / "risk-tier" / "action.yml").read_text(encoding="utf-8")
)


def test_the_action_reads_protected_paths_only_from_the_hosts_base_commit():
    checkouts = [
        s for s in ACTION["runs"]["steps"] if s.get("uses", "").startswith("actions/checkout@")
    ]
    assert len(checkouts) == 1
    assert checkouts[0]["with"] == {
        "ref": "${{ github.event.pull_request.base.ref }}",
        "path": ".risk-tier-host",
        "sparse-checkout": "config",
        "persist-credentials": False,
    }


def test_the_action_runs_the_classifier_from_its_own_pinned_checkout():
    (step,) = [s for s in ACTION["runs"]["steps"] if "risk_tier.py" in s.get("run", "")]
    # `$GITHUB_ACTION_PATH` is the action's repo at the pinned SHA: the host's tree is never run.
    assert step["run"] == 'python "$GITHUB_ACTION_PATH/../../scripts/risk_tier.py"'
    assert step["env"]["RISK_TIER_HOST_ROOT"] == "${{ github.workspace }}/.risk-tier-host"
    assert step["env"]["LANE_BOT_LOGIN"] == "${{ inputs.bot-login }}"
    assert step["env"]["HEAD_SHA"] == "${{ github.event.pull_request.head.sha }}"
    assert step["shell"] == "bash"


def test_no_context_value_is_interpolated_into_an_action_shell_step():
    runs = [s["run"] for s in ACTION["runs"]["steps"] if "run" in s]
    assert len(runs) == 2
    assert [r for r in runs if "${{" in r] == []


def test_the_github_call_is_authenticated_and_bounded_by_a_timeout(monkeypatch):
    seen = {}

    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return b'{"ok": true}'

    def fake_urlopen(req, timeout=None):
        seen["url"], seen["auth"], seen["timeout"] = (
            req.full_url,
            req.get_header("Authorization"),
            timeout,
        )
        return Resp()

    monkeypatch.setenv("GITHUB_TOKEN", "t0ken")
    monkeypatch.setattr(risk_tier.urllib.request, "urlopen", fake_urlopen)
    assert risk_tier._github_get("repos/Osasuwu/jarvis/pulls/1") == {"ok": True}
    assert seen == {
        "url": "https://api.github.com/repos/Osasuwu/jarvis/pulls/1",
        "auth": "Bearer t0ken",
        "timeout": 30,
    }


def test_a_review_event_does_not_skip_the_linked_issue_job():
    assert "if" not in WORKFLOW["jobs"]["require-linked-issue"]  # a skipped job reads as passing
