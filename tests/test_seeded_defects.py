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


def _reviewed(blocking, findings, sha=HEAD):
    return {
        "schema": 1,
        "status": "reviewed",
        "sha": sha,
        "base_ref": "main",
        "blocking": blocking,
        "findings": findings,
    }


def test_classify_reviewed_blocking_is_flagged_with_findings():
    finding = {"class": "intent-vs-logic", "file": "scripts/push_guard.py", "title": "x"}
    result = sd.classify(_reviewed(True, [finding]), HEAD, "failure")
    assert result.kind == "flagged"
    assert result.findings == (("intent-vs-logic", "scripts/push_guard.py"),)


def test_classify_reviewed_nonblocking_is_missed():
    result = sd.classify(_reviewed(False, []), HEAD, "success")
    assert result.kind == "missed"
    assert result.findings == ()


def test_classify_no_verdict_cases():
    skipped = {"schema": 1, "status": "skipped", "sha": HEAD, "base_ref": "main"}
    cases = {
        "missing": (None, "no review evidence"),
        "draft": ({**skipped, "reason": "draft"}, "review skipped: draft"),
        "stale": (
            _reviewed(True, [{"class": "regression", "file": "f"}], OTHER),
            "evidence is for",
        ),
        "schema": ({**_reviewed(False, []), "schema": 2}, "evidence unreadable"),
        "status": ({**_reviewed(False, []), "status": "pending"}, "evidence unreadable"),
        "blocking": ({**_reviewed(False, []), "blocking": "no"}, "evidence unreadable"),
    }
    got = {name: sd.classify(ev, HEAD, "failure") for name, (ev, _) in cases.items()}
    assert {n: r.kind for n, r in got.items()} == {n: "no-verdict" for n in cases}
    for name, (_, reason) in cases.items():
        assert got[name].reason.startswith(reason), (name, got[name].reason)


def test_a_red_code_gate_without_reviewed_evidence_is_not_a_verdict():
    result = sd.classify(None, HEAD, "failure")
    assert (result.kind, result.gate) == ("no-verdict", "failure")


# --- run, artifact, zip ----------------------------------------------------------


def test_select_run_takes_the_latest_run_titled_for_this_pr_and_head():
    runs = [
        {
            "id": 1,
            "display_title": f"Code review PR #7 @ {HEAD}",
            "head_sha": HEAD,
            "created_at": "2026-10-20T10:00:00Z",
        },
        {
            "id": 2,
            "display_title": f"Code review PR #7 @ {HEAD}",
            "head_sha": HEAD,
            "created_at": "2026-10-20T11:00:00Z",
        },
        {
            "id": 3,
            "display_title": f"Code review PR #8 @ {HEAD}",
            "head_sha": HEAD,
            "created_at": "2026-10-20T12:00:00Z",
        },
        {
            "id": 4,
            "display_title": f"Code review PR #7 @ {OTHER}",
            "head_sha": OTHER,
            "created_at": "2026-10-20T13:00:00Z",
        },
    ]
    assert sd.select_run(runs, 7, HEAD)["id"] == 2
    assert sd.select_run(runs, 9, HEAD) is None


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
    fx = {f.cls: f for f in sd.load_fixtures(FIXTURES)}["absence-read-as-success"]
    result = sd.classify(
        _reviewed(True, [{"class": "intent-vs-logic", "file": "scripts/junit_summary.py"}]),
        HEAD,
        "failure",
    )
    row = sd.render_row(fx, 42, HEAD, result, "https://github.com/Osasuwu/jarvis/actions/runs/5")
    assert row == (
        "| absence-read-as-success | [#42](https://github.com/Osasuwu/jarvis/pull/42) "
        "| `aaaaaaa` | flagged | intent-vs-logic `scripts/junit_summary.py` "
        "| [run](https://github.com/Osasuwu/jarvis/actions/runs/5) | failure |"
    )


# --- commands: only the allowed shapes ever run -----------------------------------


def test_built_commands_pass_the_allowlist():
    fx = sd.load_fixtures(FIXTURES)[0]
    branch = sd.branch_name(fx.cls, "20261020")
    built = [
        sd.fetch_cmd(),
        sd.push_cmd(HEAD, branch),
        sd.pr_list_cmd(branch),
        sd.pr_create_cmd(fx, branch, "body.md"),
        sd.api_get_cmd("repos/Osasuwu/jarvis/actions/runs/1/artifacts"),
    ]
    for cmd in built:
        sd.check_command(cmd)
    create = sd.pr_create_cmd(fx, branch, "body.md")
    assert "--draft" in create
    assert create[create.index("--base") + 1] == "main"
    assert create[create.index("--label") + 1] == "waiting-human-review"


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
        ["gh", "api", "-X", "POST", "repos/Osasuwu/jarvis/actions/runs/5/rerun"],
        ["gh", "api", "--method", "PUT", "repos/Osasuwu/jarvis/pulls/7/merge"],
        ["gh", "api", "repos/Osasuwu/jarvis/issues/7/comments", "-f", "body=x"],
        ["git", "push", "origin", "HEAD:main"],
        ["git", "push", "origin", f"{HEAD}:refs/heads/main"],
        ["git", "push", "origin", f"{HEAD}:refs/heads/seeded-defect/x-1", "--force"],
        ["git", "push", "--delete", "origin", "seeded-defect/x-1"],
        ["git", "checkout", "main"],
        ["git", "worktree", "add", "x"],
        ["rm", "-rf", "x"],
    ],
)
def test_check_command_refuses_everything_outside_the_allowlist(cmd):
    with pytest.raises(sd.UnsafeCommand):
        sd.check_command(cmd)


def test_run_checks_before_executing(monkeypatch):
    calls = []
    monkeypatch.setattr(sd.subprocess, "run", lambda *a, **k: calls.append(a))
    with pytest.raises(sd.UnsafeCommand):
        sd.run(["gh", "pr", "ready", "7"])
    assert calls == []
