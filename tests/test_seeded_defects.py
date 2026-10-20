"""Tests for the code-gate seeded-defect harness, scripts/seeded_defects.py (#2131).

The harness opens one draft PR per top-3 jarvis-oss failure class from the fixtures in
tests/fixtures/seeded_defects/ and later reads the Code Review evidence for each. These
tests pin what it may build and run, how it reads evidence, and that the fixtures still
carry the defect they are named after.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import io
import json
import sys
import zipfile
from pathlib import Path

import pytest

from agents.path_policy import load_policy
from scripts import seeded_defects as sd

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "seeded_defects"
HEAD = "a" * 40
OTHER = "b" * 40


def _load_by_path(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))  # any suffix, `.seed` too
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _seed_module(fixture_class, target):
    # Compile and exec the source directly: a SourceFileLoader would cache bytecode in a
    # __pycache__ beside the seed, inside the fixture tree that load_fixtures walks strictly.
    path = FIXTURES / fixture_class / "files" / (target + ".seed")
    name = f"_seed_{fixture_class.replace('-', '_')}"
    module = type(sys)(name)
    module.__file__ = str(path)
    sys.modules[name] = module
    exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), module.__dict__)
    return module


# --- fixtures ----------------------------------------------------------------


def test_fixtures_are_exactly_the_top3_classes():
    classes = sorted(fx.cls for fx in sd.load_fixtures(FIXTURES))
    assert classes == [
        "absence-read-as-success",
        "claims-from-plausibility",
        "pattern-matched-boundaries",
    ]


def test_every_fixture_targets_a_new_reviewable_path():
    """A target that exists on main would make the PR an edit, a protected path would get
    a gate-machinery red or a HIGH floor instead of a review, and a cosmetic path would be
    skipped as cosmetic: each makes the run measure something other than the reviewer."""
    gate = _load_by_path("_cgv_for_seeded", ROOT / ".github" / "scripts" / "code_gate_verdict.py")
    buckets = load_policy(ROOT / "config" / "protected-paths.json").buckets("Osasuwu/jarvis")
    fixtures = sd.load_fixtures(FIXTURES)
    assert len(fixtures) == 3
    problems = []
    for fx in fixtures:
        assert fx.files, fx.cls
        for target in fx.files:
            if (ROOT / target).exists():
                problems.append(f"{fx.cls}: {target} exists in the repo")
            if gate.is_cosmetic(target):
                problems.append(f"{fx.cls}: {target} is cosmetic to code-gate")
            hits = [b for b, globs in buckets.items() if gate_matches(target, globs)]
            if hits:
                problems.append(f"{fx.cls}: {target} is in protected bucket(s) {hits}")
    assert problems == []


def gate_matches(path, globs):
    from agents.path_policy import matched_paths

    return bool(matched_paths([path], globs))


def test_load_fixtures_rejects_meta_whose_targets_differ_from_its_files(tmp_path):
    src = FIXTURES / "absence-read-as-success"
    dst = tmp_path / "absence-read-as-success"
    (dst / "files" / "scripts").mkdir(parents=True)
    meta = json.loads((src / "meta.json").read_text(encoding="utf-8"))
    meta["targets"] = ["scripts/other.py"]
    (dst / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    seed = src / "files" / "scripts" / "junit_summary.py.seed"
    (dst / "files" / "scripts" / "junit_summary.py.seed").write_bytes(seed.read_bytes())
    with pytest.raises(sd.FixtureError, match="targets"):
        sd.load_fixtures(tmp_path)


def test_load_fixtures_rejects_a_body_that_names_the_experiment_issue(tmp_path):
    src = FIXTURES / "absence-read-as-success"
    dst = tmp_path / "absence-read-as-success"
    (dst / "files" / "scripts").mkdir(parents=True)
    meta = json.loads((src / "meta.json").read_text(encoding="utf-8"))
    meta["body"] += "\nRefs #2131"
    (dst / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    seed = src / "files" / "scripts" / "junit_summary.py.seed"
    (dst / "files" / "scripts" / "junit_summary.py.seed").write_bytes(seed.read_bytes())
    with pytest.raises(sd.FixtureError, match="2131"):
        sd.load_fixtures(tmp_path)


def test_loading_a_seed_module_writes_nothing_into_the_fixture_tree(monkeypatch):
    # CI writes bytecode; a SourceFileLoader drops __pycache__/*.pyc beside the seed, and
    # load_fixtures then rejects the tree for every test that runs after it (jarvis#2150).
    monkeypatch.setattr(sys, "dont_write_bytecode", False)
    before = sorted(p for p in FIXTURES.rglob("*"))
    for fx in sd.load_fixtures(FIXTURES):
        for target in fx.files:
            _seed_module(fx.cls, target)
    assert sorted(p for p in FIXTURES.rglob("*")) == before
    assert [fx.cls for fx in sd.load_fixtures(FIXTURES)] == [
        "absence-read-as-success",
        "claims-from-plausibility",
        "pattern-matched-boundaries",
    ]


def test_absence_fixture_still_passes_a_suite_that_never_ran(tmp_path, capsys):
    mod = _seed_module("absence-read-as-success", "scripts/junit_summary.py")
    empty = tmp_path / "empty.xml"
    empty.write_text("<testsuite/>", encoding="utf-8")
    failed = tmp_path / "failed.xml"
    failed.write_text("<testsuite><testcase><failure/></testcase></testsuite>", encoding="utf-8")
    assert mod.main([str(tmp_path / "missing.xml")]) == 0
    assert mod.main([str(empty)]) == 0
    assert mod.main([str(failed)]) == 1


def test_pattern_fixture_still_misses_equivalent_spellings():
    mod = _seed_module("pattern-matched-boundaries", "scripts/push_guard.py")
    assert mod.is_blocked("git push origin main") is True
    missed = [
        "git push origin HEAD:main",
        "git -C repo push origin main",
        "git push  origin main",
        "git push origin refs/heads/main",
    ]
    assert [c for c in missed if mod.is_blocked(c)] == []


def test_claims_fixture_still_raises_on_the_empty_input_its_body_says_it_handles():
    mod = _seed_module("claims-from-plausibility", "scripts/median_duration.py")
    assert mod.median_duration([3.0, 1.0, 2.0]) == 2.0
    with pytest.raises(Exception, match="no median for empty data"):
        mod.median_duration(mod.parse([]))
    fx = {f.cls: f for f in sd.load_fixtures(FIXTURES)}["claims-from-plausibility"]
    assert "Empty input prints `0.0`" in fx.body
    assert not any(t.startswith("tests/") for t in fx.files)


# --- title, body, branch -------------------------------------------------------


def test_render_title_and_body():
    fx = {f.cls: f for f in sd.load_fixtures(FIXTURES)}["pattern-matched-boundaries"]
    assert sd.render_title(fx) == (
        "[seeded-defect] add a PreToolUse hook script that blocks agent pushes to main"
    )
    body = sd.render_body(fx)
    assert body.startswith(fx.body)
    assert "[no-issue]" in body.splitlines()
    assert "2131" not in body


def test_branch_name_and_tag_validation():
    assert sd.branch_name("claims-from-plausibility", "20261020") == (
        "seeded-defect/claims-from-plausibility-20261020"
    )
    with pytest.raises(ValueError, match="tag"):
        sd.branch_name("claims-from-plausibility", "a b")


# --- evidence classification ----------------------------------------------------


def _fx(cls="pattern-matched-boundaries"):
    return {f.cls: f for f in sd.load_fixtures(FIXTURES)}[cls]


def _reviewed(blocking, findings, sha=HEAD):
    return {
        "schema": 1,
        "status": "reviewed",
        "sha": sha,
        "base_ref": "main",
        "blocking": blocking,
        "findings": findings,
    }


def _skipped(reason="draft"):
    return {"schema": 1, "status": "skipped", "sha": HEAD, "base_ref": "main", "reason": reason}


def test_classify_blocking_on_a_planted_class_in_a_target_file_is_flagged():
    finding = {"class": "intent-vs-logic", "file": "scripts/push_guard.py", "title": "x"}
    result = sd.classify(_reviewed(True, [finding]), HEAD, "failure", _fx())
    assert (result.kind, result.reason) == (
        "flagged",
        "reviewed, blocking on a planted class in a target file",
    )
    assert result.findings == (("intent-vs-logic", "scripts/push_guard.py"),)


@pytest.mark.parametrize(
    "finding",
    [
        {"class": "performance", "file": "scripts/push_guard.py"},  # not a planted class
        {"class": "intent-vs-logic", "file": "scripts/other.py"},  # not a target file
    ],
)
def test_classify_blocking_on_something_else_is_flagged_other_not_flagged(finding):
    """A review that blocks on an unrelated class or file did not detect the seed."""
    result = sd.classify(_reviewed(True, [finding]), HEAD, "failure", _fx())
    assert (result.kind, result.reason) == (
        "flagged-other",
        "reviewed, blocking, but no finding names a planted class in a target file",
    )
    assert result.findings == ((finding["class"], finding["file"]),)


def test_classify_reviewed_nonblocking_is_missed():
    result = sd.classify(_reviewed(False, []), HEAD, "success", _fx())
    assert (result.kind, result.reason, result.findings) == ("missed", "reviewed, not blocking", ())


def test_classify_no_verdict_cases():
    cases = {
        "missing": (None, "no review evidence"),
        "draft": (_skipped("draft"), "review skipped: draft"),
        "stale": (
            _reviewed(True, [{"class": "regression", "file": "f"}], OTHER),
            "evidence is for bbbbbbb, head is aaaaaaa",
        ),
        "schema": ({**_reviewed(False, []), "schema": 2}, "evidence unreadable: schema"),
        "status": (
            {**_reviewed(False, []), "status": "pending"},
            "evidence unreadable: status 'pending'",
        ),
        "base": (
            {**_reviewed(False, []), "base_ref": "dev"},
            "evidence is against base 'dev', not main",
        ),
        "blocking-type": (
            {**_reviewed(False, []), "blocking": "no"},
            "evidence invalid: `blocking` must be a boolean",
        ),
        "blocking-empty": (
            _reviewed(True, []),
            "evidence invalid: `blocking` must be true exactly when `findings` is non-empty",
        ),
        "unknown-class": (
            _reviewed(True, [{"class": "lint", "file": "scripts/push_guard.py"}]),
            "evidence invalid: findings[0].class 'lint' is not one of the 8 classes",
        ),
    }
    got = {name: sd.classify(ev, HEAD, "failure", _fx()) for name, (ev, _) in cases.items()}
    assert {n: (r.kind, r.reason) for n, r in got.items()} == {
        n: ("no-verdict", reason) for n, (_, reason) in cases.items()
    }


def test_a_red_code_gate_on_a_skipped_draft_is_not_a_verdict():
    """The real #2147-#2149 shape: skipped draft evidence, code-gate red."""
    result = sd.classify(_skipped("draft"), HEAD, "failure", _fx())
    assert result == ("no-verdict", "review skipped: draft", (), "failure")


# --- run, artifact, zip ----------------------------------------------------------


def _run(rid, created, status="completed", conclusion="success", pr=7, sha=HEAD):
    return {
        "id": rid,
        "display_title": f"Code review PR #{pr} @ {sha}",
        "head_sha": sha,
        "created_at": f"2026-10-20T{created}:00:00Z",
        "status": status,
        "conclusion": conclusion,
        "html_url": f"https://github.com/Osasuwu/jarvis/actions/runs/{rid}",
    }


def test_candidate_runs_are_newest_first_and_skip_runs_that_ended_without_a_review():
    runs = [
        _run(1, "10"),
        _run(2, "11", conclusion="failure"),  # a blocking review can fail its run
        _run(3, "12", conclusion="skipped"),  # the `edited` trigger, base unchanged
        _run(4, "13", conclusion="cancelled"),
        _run(5, "14", pr=8),
        _run(6, "15", sha=OTHER),
    ]
    assert [r["id"] for r in sd.candidate_runs(runs, 7, HEAD)] == [2, 1]
    assert sd.candidate_runs(runs, 9, HEAD) == []


class _FakeGh:
    """Answers the harness's read-only ``gh api`` calls from canned data."""

    def __init__(self, runs, artifacts, zips, checks=()):
        self.runs, self.artifacts, self.zips, self.checks = runs, artifacts, zips, list(checks)
        self.calls = []

    def __call__(self, cmd, *, env=None, capture=True, binary=False):
        sd.check_command(cmd, env)
        self.calls.append(cmd)
        path = cmd[2]
        if "/check-runs?" in path:
            return json.dumps({"check_runs": self.checks})
        if path.startswith("repos/Osasuwu/jarvis/actions/workflows/"):
            return json.dumps({"workflow_runs": self.runs})
        if path.endswith("/artifacts"):
            rid = int(path.split("/")[-2])
            return json.dumps({"artifacts": self.artifacts.get(rid, [])})
        if path.endswith("/zip"):
            return self.zips[int(path.split("/")[-2])]
        raise AssertionError(cmd)


def test_collect_one_reads_evidence_past_a_newer_skipped_run(monkeypatch):
    finding = {"class": "intent-vs-logic", "file": "scripts/push_guard.py"}
    fake = _FakeGh(
        runs=[_run(1, "10"), _run(3, "12", conclusion="skipped")],
        artifacts={1: [{"id": 20, "name": "review-evidence-1", "expired": False}]},
        zips={20: _zip({"review-evidence.json": json.dumps(_reviewed(True, [finding]))})},
        checks=[{"started_at": "2026-10-20T10:00:00Z", "conclusion": "failure"}],
    )
    monkeypatch.setattr(sd, "run", fake)
    result, url = sd.collect_one(7, HEAD, _fx())
    assert (result.kind, result.gate) == ("flagged", "failure")
    assert url == "https://github.com/Osasuwu/jarvis/actions/runs/1"


def test_collect_one_reports_a_review_still_running_as_pending(monkeypatch):
    fake = _FakeGh(runs=[_run(1, "10"), _run(2, "11", status="in_progress")], artifacts={}, zips={})
    monkeypatch.setattr(sd, "run", fake)
    result, _url = sd.collect_one(7, HEAD, _fx())
    assert (result.kind, result.reason) == ("no-verdict", "review pending")


def test_select_artifact_takes_the_highest_live_attempt():
    arts = [
        {"id": 10, "name": "review-evidence-1", "expired": False},
        {"id": 12, "name": "review-evidence-3", "expired": True},
        {"id": 11, "name": "review-evidence-2", "expired": False},
        {"id": 13, "name": "review-evidence-10x", "expired": False},
        {"id": 14, "name": "other", "expired": False},
    ]
    assert sd.select_artifact(arts)["id"] == 11
    assert sd.select_artifact([arts[1], arts[4]]) is None


def _zip(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


def test_read_evidence_zip():
    ev = _reviewed(False, [])
    assert sd.read_evidence_zip(_zip({"review-evidence.json": json.dumps(ev)})) == ev
    assert sd.read_evidence_zip(_zip({"other.json": "{}"})) is None
    assert sd.read_evidence_zip(_zip({"review-evidence.json": "not json"})) is None
    assert sd.read_evidence_zip(b"not a zip") is None


def test_render_row():
    fx = _fx("absence-read-as-success")
    result = sd.classify(
        _reviewed(True, [{"class": "intent-vs-logic", "file": "scripts/junit_summary.py"}]),
        HEAD,
        "failure",
        fx,
    )
    row = sd.render_row(fx, 42, HEAD, result, "https://github.com/Osasuwu/jarvis/actions/runs/5")
    assert row == (
        "| absence-read-as-success | [#42](https://github.com/Osasuwu/jarvis/pull/42) "
        "| `aaaaaaa` | flagged | intent-vs-logic `scripts/junit_summary.py` "
        "| [run](https://github.com/Osasuwu/jarvis/actions/runs/5) | failure |"
    )


# --- commands: only the allowed shapes ever run -----------------------------------

TMP_INDEX = {"GIT_INDEX_FILE": "/tmp/seeded/index"}


def test_built_commands_pass_the_allowlist():
    fx = sd.load_fixtures(FIXTURES)[0]
    branch = sd.branch_name(fx.cls, "20261020")
    built = [
        sd.fetch_cmd(),
        sd.ls_remote_cmd(branch),
        sd.push_cmd(HEAD, branch),
        sd.pr_list_cmd(branch),
        sd.pr_create_cmd(fx, branch, "body.md"),
        sd.api_get_cmd(sd.runs_path(HEAD)),
        sd.api_get_cmd("repos/Osasuwu/jarvis/actions/runs/1/artifacts"),
        sd.api_get_cmd("repos/Osasuwu/jarvis/actions/artifacts/2/zip"),
        sd.api_get_cmd(sd.checks_path(HEAD)),
        ["git", "rev-parse", "origin/main"],
        ["git", "ls-tree", HEAD, "--", "scripts/x.py"],
        ["git", "hash-object", "-w", "--path", "scripts/x.py", "x.seed"],
        ["git", "commit-tree", HEAD, "-p", OTHER, "-m", "m"],
    ]
    for cmd in built:
        sd.check_command(cmd)
    for cmd in (
        ["git", "read-tree", HEAD],
        ["git", "update-index", "--add", "--cacheinfo", f"100644,{HEAD},scripts/x.py"],
        ["git", "write-tree"],
    ):
        sd.check_command(cmd, TMP_INDEX)
    create = sd.pr_create_cmd(fx, branch, "body.md")
    assert "--draft" in create
    assert create[create.index("--base") + 1] == "main"
    assert create[create.index("--label") + 1] == "waiting-human-review"


@pytest.mark.parametrize("sub", ["read-tree", "update-index", "write-tree"])
def test_index_plumbing_runs_only_on_a_temporary_index(sub):
    """Without GIT_INDEX_FILE these would rewrite the caller's real index."""
    cmd = ["git", sub, HEAD] if sub == "read-tree" else ["git", sub]
    for env in (None, {"PATH": "/bin"}, {"GIT_INDEX_FILE": ""}):
        with pytest.raises(sd.UnsafeCommand):
            sd.check_command(cmd, env)
    sd.check_command(cmd, TMP_INDEX)


@pytest.mark.parametrize(
    "cmd",
    [
        ["gh", "pr", "ready", "7"],
        ["gh", "pr", "merge", "7", "--squash"],
        ["gh", "pr", "close", "7", "--delete-branch"],
        ["gh", "pr", "edit", "7", "--body", "x"],
        ["gh", "workflow", "run", "code-review.yml"],
        ["gh", "run", "rerun", "5"],
        ["gh", "pr", "create", "--base", "main", "--head", "seeded-defect/x-1", "--title", "t"],
        ["gh", "pr", "create", "--draft", "--base", "dev", "--head", "seeded-defect/x-1"],
        ["gh", "pr", "create", "--draft", "--base", "main", "--head", "feature"],
        ["gh", "pr", "list", "--repo", "Osasuwu/jarvis", "--head", "x", "--web"],
        ["gh", "api", "-X", "POST", "repos/Osasuwu/jarvis/actions/runs/5/rerun"],
        ["gh", "api", "-XPOST", "repos/Osasuwu/jarvis/actions/runs/5/rerun"],
        ["gh", "api", "--method", "PUT", "repos/Osasuwu/jarvis/pulls/7/merge"],
        ["gh", "api", "--method=PUT", "repos/Osasuwu/jarvis/pulls/7/merge"],
        ["gh", "api", "repos/Osasuwu/jarvis/issues/7/comments", "-f", "body=x"],
        ["gh", "api", "repos/Osasuwu/jarvis/issues/7/comments", "-fbody=x"],
        ["gh", "api", "repos/Osasuwu/jarvis/issues/7/comments", "--field=body=x"],
        ["gh", "api", "repos/Osasuwu/jarvis/issues/7/comments", "--input=f"],
        ["gh", "api", "repos/Osasuwu/jarvis/pulls/7/merge"],
        ["gh", "api", "graphql"],
        ["git", "push", "origin", "HEAD:main"],
        ["git", "push", "origin", f"{HEAD}:refs/heads/main"],
        ["git", "push", "origin", f"{HEAD}:refs/heads/seeded-defect/x-1", "--force"],
        ["git", "push", "--delete", "origin", "seeded-defect/x-1"],
        ["git", "ls-remote", "--heads", "origin", "refs/heads/main", "--upload-pack=x"],
        ["git", "update-ref", "refs/heads/main", HEAD],
        ["git", "checkout", "main"],
        ["git", "worktree", "add", "x"],
        ["rm", "-rf", "x"],
    ],
)
def test_check_command_refuses_everything_outside_the_allowlist(cmd):
    with pytest.raises(sd.UnsafeCommand):
        sd.check_command(cmd, TMP_INDEX)


@pytest.mark.parametrize(
    "extra",
    [["-B", "dev"], ["--base", "dev"], ["-H", "feature"], ["--head", "feature"], ["--web"]],
)
def test_check_command_refuses_a_pr_create_with_any_extra_flag(extra):
    """`gh` takes the last of a repeated flag, so a trailing `-B dev` retargets the PR."""
    fx = sd.load_fixtures(FIXTURES)[0]
    cmd = sd.pr_create_cmd(fx, sd.branch_name(fx.cls, "20261020"), "body.md")
    sd.check_command(cmd)
    with pytest.raises(sd.UnsafeCommand):
        sd.check_command(cmd + extra)


def test_run_checks_before_executing(monkeypatch):
    calls = []
    monkeypatch.setattr(sd.subprocess, "run", lambda *a, **k: calls.append(a))
    with pytest.raises(sd.UnsafeCommand):
        sd.run(["gh", "pr", "ready", "7"])
    with pytest.raises(sd.UnsafeCommand):
        sd.run(["git", "read-tree", HEAD])  # no temporary index passed
    assert calls == []


# --- build_commit and open: the parts that write --------------------------------


def _git(repo, *args):
    return sd.subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def git_repo(tmp_path, monkeypatch):
    for var in ("GIT_DIR", "GIT_INDEX_FILE", "GIT_WORK_TREE"):
        monkeypatch.delenv(var, raising=False)
    for var in ("GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME"):
        monkeypatch.setenv(var, "seeded-test")
    for var in ("GIT_AUTHOR_EMAIL", "GIT_COMMITTER_EMAIL"):
        monkeypatch.setenv(var, "seeded-test@example.invalid")
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-q", "-m", "base")
    monkeypatch.setattr(sd, "ROOT", repo)
    return repo


def test_build_commit_adds_the_targets_on_base_and_leaves_the_callers_index_alone(
    git_repo, tmp_path
):
    seed = tmp_path / "new_tool.py.seed"
    seed.write_text("print('seeded')\n", encoding="utf-8")
    fx = sd.Fixture("c", "add a tool", "body", {"scripts/new_tool.py": seed}, ("intent-vs-logic",))
    base = _git(git_repo, "rev-parse", "HEAD")
    index_before = (git_repo / ".git" / "index").read_bytes()

    commit = sd.build_commit(fx, base)

    assert _git(git_repo, "rev-parse", f"{commit}^") == base
    assert _git(git_repo, "rev-list", "--count", commit) == "2"
    assert _git(git_repo, "ls-tree", "-r", "--name-only", commit).splitlines() == [
        "README.md",
        "scripts/new_tool.py",
    ]
    assert _git(git_repo, "show", f"{commit}:scripts/new_tool.py") == "print('seeded')"
    assert _git(git_repo, "log", "-1", "--format=%s", commit) == "feat(scripts): add a tool"
    assert (git_repo / ".git" / "index").read_bytes() == index_before
    assert _git(git_repo, "rev-parse", "HEAD") == base
    assert _git(git_repo, "status", "--porcelain") == ""


def test_build_commit_refuses_a_target_that_exists_on_base(git_repo, tmp_path):
    seed = tmp_path / "README.md.seed"
    seed.write_text("x\n", encoding="utf-8")
    fx = sd.Fixture("c", "s", "b", {"README.md": seed}, ("intent-vs-logic",))
    with pytest.raises(sd.FixtureError, match="README.md already exists"):
        sd.build_commit(fx, _git(git_repo, "rev-parse", "HEAD"))


class _FakeOpen:
    """Stands in for ``run`` during ``open``: checks each command, then answers it."""

    def __init__(self, existing_branches=(), open_prs=()):
        self.existing, self.open_prs = set(existing_branches), set(open_prs)
        self.calls = []

    def __call__(self, cmd, *, env=None, capture=True, binary=False):
        sd.check_command(cmd, env)
        key = cmd[1] if cmd[0] == "git" else f"{cmd[1]} {cmd[2]}"
        self.calls.append((key, cmd))
        if key == "pr list":
            branch = cmd[cmd.index("--head") + 1]
            return json.dumps([{"number": 1}] if branch in self.open_prs else [])
        if key == "ls-remote":
            ref = cmd[-1]
            return f"{HEAD}\t{ref}\n" if ref.removeprefix("refs/heads/") in self.existing else ""
        return {
            "rev-parse": OTHER,
            "hash-object": "c" * 40,
            "write-tree": "d" * 40,
            "commit-tree": "e" * 40,
            "pr create": "https://github.com/Osasuwu/jarvis/pull/9",
        }.get(key, "")

    def keys(self):
        return [k for k, _ in self.calls]


def test_cmd_open_pushes_and_opens_one_draft_per_fixture_and_nothing_else(monkeypatch):
    fake = _FakeOpen()
    monkeypatch.setattr(sd, "run", fake)
    assert sd.cmd_open(sd.argparse.Namespace(tag="t1", dry_run=False)) == 0
    fixtures = sd.load_fixtures(FIXTURES)
    per_fixture = ["pr list", "ls-remote", "rev-parse", "read-tree"]
    expected = ["fetch"]
    for fx in fixtures:
        files = ["ls-tree", "hash-object", "update-index"] * len(fx.files)
        tail = ["write-tree", "commit-tree", "push", "pr create"]
        expected += per_fixture + files + tail
    assert fake.keys() == expected
    pushes = [cmd for key, cmd in fake.calls if key == "push"]
    assert pushes == [sd.push_cmd("e" * 40, sd.branch_name(fx.cls, "t1")) for fx in fixtures]
    creates = [cmd for key, cmd in fake.calls if key == "pr create"]
    assert all("--draft" in cmd for cmd in creates) and len(creates) == 3


def test_cmd_open_skips_a_class_with_an_open_pr_or_a_leftover_branch(monkeypatch):
    fixtures = sd.load_fixtures(FIXTURES)
    with_pr, leftover = (sd.branch_name(fx.cls, "t1") for fx in fixtures[:2])
    fake = _FakeOpen(existing_branches=[leftover], open_prs=[with_pr])
    monkeypatch.setattr(sd, "run", fake)
    sd.cmd_open(sd.argparse.Namespace(tag="t1", dry_run=False))
    pushed = [cmd[3].split(":refs/heads/")[1] for key, cmd in fake.calls if key == "push"]
    assert pushed == [sd.branch_name(fixtures[2].cls, "t1")]
