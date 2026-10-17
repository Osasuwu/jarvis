"""Decision rules of .github/scripts/code_gate_verdict.py — the "Review evidence" gate (#1964).

Every function under test is pure: plain dicts in, a value out. The fixtures
are shaped like real GitHub API payloads (workflow runs, pull requests, PR
files) and every expected value is a literal worked out from the locked design,
not read back from the module.
"""

import argparse
import http.client
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import urllib.error
from pathlib import Path

import pytest

from ._github_fake import (
    FakeApi,
    FakeResponse,
    FakeTransport,
    SequencedApi,
    http_error,
    load_client,
)

_root = next(p for p in Path(__file__).resolve().parents if (p / ".github" / "scripts").is_dir())
_spec = importlib.util.spec_from_file_location(
    "code_gate_verdict", _root / ".github" / "scripts" / "code_gate_verdict.py"
)
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)

SHA = "a" * 40
OTHER_SHA = "b" * 40
PR = 7


# --- classify_paths -------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "docs/guide.md",
        "docs/decisions/2026-Q3.md",  # docs-only PRs must not wait on a review (#1897)
        "docs/img/arch.png",
        "docs/deep/nested/shot.webp",
        "README.md",
        "SECURITY.md",
        "LICENSE",
        "LICENSE-APACHE",
        "THIRD_PARTY_LICENSES",
        "assets/logo.png",
        "src/pkg/icon.jpg",
        "anim.gif",
        "pic.webp",
    ],
)
def test_cosmetic_paths(path):
    assert gate.classify_paths([path]) == {"code": [], "cosmetic": [path]}


@pytest.mark.parametrize(
    "path",
    [
        "docs/reference/github-repo-setup.md",  # docs/reference is behaviour-carrying
        "docs/notes.txt",  # extension outside the docs allow-list
        "docs/diagram.svg",  # svg can carry script
        "AGENTS.md",
        "SOUL.md",
        "CONTEXT.md",
        "sub/README.md",  # README is cosmetic at the root only
        "notes.txt",
        "logo.svg",
        ".claude/skills/x/SKILL.md",
        ".claude/agents/planner.md",
        ".github/workflows/pytest.yml",
        "src/app.py",
        "supabase/migrations/20260415_create_registry.sql",  # schema is code (#1816)
        "scripts/install.ps1",  # PowerShell is code (#1816)
        "CLAUDE.md",  # behaviour-carrying markdown is reviewed by path (#1897)
        "config/SOUL.md",
        ".claude/session-snapshots/de927bb9.md",
        "docs/PNG.PNG",  # extension match is case-sensitive: stricter, fails safe
    ],
)
def test_code_paths(path):
    assert gate.classify_paths([path]) == {"code": [path], "cosmetic": []}


def test_classify_preserves_input_order_in_each_bucket():
    got = gate.classify_paths(["b.py", "docs/a.md", "a.py", "docs/b.md"])
    assert got == {"code": ["b.py", "a.py"], "cosmetic": ["docs/a.md", "docs/b.md"]}


# --- changed_paths --------------------------------------------------------


def test_rename_is_judged_on_both_paths():
    files = [{"filename": "docs/new.md", "previous_filename": "src/old.py", "status": "renamed"}]
    assert gate.changed_paths(files) == ["docs/new.md", "src/old.py"]


def test_rename_of_code_into_docs_is_not_all_cosmetic():
    files = [{"filename": "docs/new.md", "previous_filename": "src/old.py", "status": "renamed"}]
    assert gate.classify_paths(gate.changed_paths(files))["code"] == ["src/old.py"]


def test_deleted_file_keeps_its_path():
    files = [{"filename": "src/gone.py", "status": "removed"}]
    assert gate.changed_paths(files) == ["src/gone.py"]


# --- is_gate_machinery ----------------------------------------------------

REPO = "Osasuwu/jarvis"


@pytest.mark.parametrize(
    "path",
    [
        ".github/workflows/code-review.yml",
        ".github/workflows/code-gate-verdict.yml",
        ".github/scripts/code_gate_verdict.py",
        ".github/scripts/github_client.py",  # the verdict job executes it (#2068)
        ".github/actions/anything/action.yml",
        "agents/path_policy.py",  # the list moved out of this script (#2067): its reader
        "config/protected-paths.json",  # and the list itself are gate machinery now
    ],
)
def test_gate_machinery_paths(path):
    assert gate.is_gate_machinery([path], REPO) is True


@pytest.mark.parametrize(
    "path",
    [
        ".github/workflows/pytest.yml",
        ".github/scripts/unblock_ready.py",
        "tests/ci/test_code_gate_verdict.py",
        "docs/reference/github-repo-setup.md",
    ],
)
def test_non_machinery_paths(path):
    assert gate.is_gate_machinery([path], REPO) is False


def test_machinery_on_the_old_side_of_a_rename_counts():
    files = [
        {
            "filename": "docs/x.md",
            "previous_filename": ".github/scripts/code_gate_verdict.py",
            "status": "renamed",
        }
    ]
    assert gate.is_gate_machinery(gate.changed_paths(files), REPO) is True


def _gate_tree(tmp_path, policy):
    """A checkout holding the script, path_policy.py and a literal protected list."""
    (tmp_path / ".github" / "scripts").mkdir(parents=True)
    (tmp_path / "agents").mkdir()
    (tmp_path / "config").mkdir()
    shutil.copy(
        _root / ".github" / "scripts" / "code_gate_verdict.py", tmp_path / ".github" / "scripts"
    )
    shutil.copy(_root / "agents" / "path_policy.py", tmp_path / "agents")
    (tmp_path / "config" / "protected-paths.json").write_text(json.dumps(policy), "utf-8")
    spec = importlib.util.spec_from_file_location(
        "code_gate_verdict_tree", tmp_path / ".github" / "scripts" / "code_gate_verdict.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_gate_set_is_the_lists_gate_bucket_not_a_literal_in_the_script(tmp_path):
    tree = _gate_tree(tmp_path, {REPO: {"gate": ["only/this.py"], "machinery": ["m/**"]}})
    assert tree.is_gate_machinery(["only/this.py"], REPO) is True
    assert tree.is_gate_machinery([".github/workflows/code-review.yml", "m/x.py"], REPO) is False


@pytest.mark.parametrize(
    "policy",
    [{"other/repo": {"gate": ["x"]}}, {REPO: {"machinery": ["x"]}}],
    ids=["no-entry-for-the-repo", "no-gate-bucket"],
)
def test_a_list_that_cannot_name_the_gate_set_raises(tmp_path, policy):
    """Fail closed: `cmd_verdict` posts a raise as `verdict-error` red, never as a pass."""
    tree = _gate_tree(tmp_path, policy)
    with pytest.raises(ValueError, match=REPO):
        tree.is_gate_machinery(["src/a.py"], REPO)


def test_the_review_side_subcommands_run_from_the_script_alone(tmp_path):
    """code-review.yml runs `validate`, `check-tree` and `stamp` after the reviewer,
    under `python -I` in a workspace the reviewer can write to (#2024): they must load
    nothing beside the script, neither path_policy nor github_client, so a copy of the
    script alone still validates. (`prepare` runs before the reviewer and loads
    github_client.py; `skip` loads nothing either.)"""
    script = tmp_path / "code_gate_verdict.py"
    shutil.copy(_root / ".github" / "scripts" / "code_gate_verdict.py", script)
    findings = tmp_path / "findings.json"
    findings.write_text(json.dumps({"blocking": False, "findings": []}), "utf-8")
    run = subprocess.run(
        [sys.executable, "-I", str(script), "validate", "--findings", str(findings)],
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )
    assert (run.returncode, run.stderr) == (0, "")


# --- is_untrusted_author / is_draft ---------------------------------------


def _pr(**over):
    pr = {
        "number": PR,
        "draft": False,
        "changed_files": 1,
        "user": {"login": "Osasuwu", "type": "User"},
        "base": {"ref": "main", "repo": {"full_name": "Osasuwu/jarvis"}},
        "head": {"sha": SHA, "repo": {"full_name": "Osasuwu/jarvis"}},
        "created_at": "2026-10-01T12:00:00Z",
    }
    pr.update(over)
    return pr


def test_same_repo_human_is_trusted():
    assert gate.is_untrusted_author(_pr()) is False


def test_fork_head_is_untrusted():
    pr = _pr(head={"sha": SHA, "repo": {"full_name": "stranger/jarvis"}})
    assert gate.is_untrusted_author(pr) is True


def test_deleted_fork_head_is_untrusted():
    assert gate.is_untrusted_author(_pr(head={"sha": SHA, "repo": None})) is True


def test_dependabot_is_untrusted_even_from_the_same_repo():
    pr = _pr(user={"login": "dependabot[bot]", "type": "Bot"})
    assert gate.is_untrusted_author(pr) is True


def test_draft_flag():
    assert gate.is_draft(_pr(draft=True)) is True
    assert gate.is_draft(_pr(draft=False)) is False


# --- validate_findings ----------------------------------------------------


def test_clean_findings_are_valid():
    assert gate.validate_findings({"blocking": False, "findings": []}) == []


def test_blocking_findings_are_valid():
    obj = {"blocking": True, "findings": [{"class": "regression", "file": "a.py"}]}
    assert gate.validate_findings(obj) == []


@pytest.mark.parametrize(
    "obj",
    [
        {"blocking": True, "findings": []},  # blocking with nothing to block on
        {"blocking": False, "findings": [{"class": "regression", "file": "a.py"}]},
        {"blocking": True, "findings": [{"class": "nitpick", "file": "a.py"}]},  # unknown class
        {"blocking": True, "findings": [{"class": "regression"}]},  # no file
        {"blocking": "no", "findings": []},  # not a bool
        {"findings": []},
        {"blocking": False},
        {"status": "unreviewed"},  # the seed the review job writes before the reviewer runs
        [],
        None,
    ],
)
def test_invalid_findings_are_rejected(obj):
    assert gate.validate_findings(obj) != []


def test_all_eight_classes_are_accepted():
    classes = [
        "regression",
        "exception-handling",
        "intent-vs-logic",
        "breaking-contract",
        "concurrency",
        "requirement-semantics",
        "design-modularity",
        "performance",
    ]
    findings = [{"class": c, "file": "a.py"} for c in classes]
    assert gate.validate_findings({"blocking": True, "findings": findings}) == []


# --- check_clean_tree -----------------------------------------------------


def test_clean_tree_apart_from_findings_file():
    porcelain = "?? code-review-findings.json\n"
    assert gate.check_clean_tree(porcelain, "code-review-findings.json") == []


def test_modified_tracked_file_is_dirty():
    porcelain = " M .github/workflows/pytest.yml\n?? code-review-findings.json\n"
    assert gate.check_clean_tree(porcelain, "code-review-findings.json") == [
        ".github/workflows/pytest.yml"
    ]


def test_stray_untracked_file_is_dirty():
    porcelain = "?? code-review-findings.json\n?? scratch.sh\n"
    assert gate.check_clean_tree(porcelain, "code-review-findings.json") == ["scratch.sh"]


# --- build_evidence -------------------------------------------------------


def test_build_evidence_stamps_sha_and_base():
    got = gate.build_evidence(
        {"blocking": True, "findings": [{"class": "regression", "file": "a.py"}]},
        sha=SHA,
        base_ref="main",
    )
    assert got == {
        "schema": 1,
        "status": "reviewed",
        "sha": SHA,
        "base_ref": "main",
        "blocking": True,
        "findings": [{"class": "regression", "file": "a.py"}],
    }


def test_skipped_evidence_shape():
    assert gate.build_skipped_evidence(sha=SHA, base_ref="main", reason="cosmetic") == {
        "schema": 1,
        "status": "skipped",
        "sha": SHA,
        "base_ref": "main",
        "reason": "cosmetic",
    }


# --- run_provenance (real run-API shape) ---------------------------------


def _pr_run(**over):
    run = {
        "id": 1001,
        "name": "Code review",
        "path": ".github/workflows/code-review.yml",
        "event": "pull_request",
        "status": "completed",
        "conclusion": "success",
        "head_branch": "feat/x",
        "head_sha": SHA,
        "display_title": f"Code review PR #{PR} @ {SHA}",
        "pull_requests": [
            {
                "number": PR,
                "base": {"ref": "main", "sha": OTHER_SHA},
                "head": {"ref": "feat/x", "sha": SHA},
            }
        ],
    }
    run.update(over)
    return run


def _dispatch_run(**over):
    """A dispatch run as `gather_entries` hands it on: the history fact is set."""
    run = {
        "id": 2002,
        "name": "Code review",
        "path": ".github/workflows/code-review.yml",
        "event": "workflow_dispatch",
        "status": "completed",
        "conclusion": "success",
        "head_branch": "main",
        "head_sha": OTHER_SHA,  # the default branch tip, not the PR head
        "display_title": f"Code review PR #{PR} @ {SHA}",
        "pull_requests": [],
        "_in_default_history": True,
    }
    run.update(over)
    return run


def _q(run):
    return gate.run_provenance(run, pr_number=PR, head_sha=SHA, default_branch="main")


def _listed(number, base):
    return {"number": number, "base": {"ref": base}, "head": {"sha": SHA}}


def test_pull_request_run_bound_to_pr_qualifies():
    assert _q(_pr_run()) == "bound"


def test_pull_request_run_for_another_pr_is_excluded():
    assert _q(_pr_run(pull_requests=[_listed(8, "main")])) == ""


def test_pull_request_run_with_no_pull_requests_is_excluded():
    """A fork's pull_request run carries an empty pull_requests[]."""
    assert _q(_pr_run(pull_requests=[])) == ""


def test_pull_request_run_into_a_non_default_base_is_foreign():
    assert _q(_pr_run(pull_requests=[_listed(PR, "release")])) == "foreign-base"


@pytest.mark.parametrize("order", ["foreign-first", "foreign-last"])
def test_pull_request_run_also_listing_a_pr_into_another_base_is_foreign(order):
    """#2024: the run lists every open PR on its head, and may have run the other
    base's copy of the workflow — whichever order the list comes in."""
    listed = [_listed(PR, "main"), _listed(8, "release")]
    if order == "foreign-first":
        listed.reverse()
    assert _q(_pr_run(pull_requests=listed)) == "foreign-base"


def test_pull_request_run_also_listing_another_pr_into_the_default_base_is_bound():
    run = _pr_run(pull_requests=[_listed(8, "main"), _listed(PR, "main")])
    assert _q(run) == "bound"


def test_foreign_pull_request_run_for_an_older_head_sha_is_excluded():
    run = _pr_run(head_sha=OTHER_SHA, pull_requests=[_listed(PR, "release")])
    assert _q(run) == ""


def test_pull_request_run_for_an_older_head_sha_is_excluded():
    assert _q(_pr_run(head_sha=OTHER_SHA)) == ""


def test_dispatch_run_from_default_branch_history_qualifies():
    assert _q(_dispatch_run()) == "bound"


@pytest.mark.parametrize("fact", [False, None, "true", 1], ids=["false", "absent", "str", "int"])
def test_dispatch_run_off_default_branch_history_is_excluded(fact):
    """#2024: a tag or branch named like the default one does not put a commit in
    its history; only an exact True set by gather_entries does."""
    run = _dispatch_run()
    if fact is None:
        del run["_in_default_history"]
    else:
        run["_in_default_history"] = fact
    assert _q(run) == ""


def test_dispatch_run_bound_by_history_not_by_head_branch():
    """head_branch is spoofable (a tag named `main`), so it decides nothing."""
    assert _q(_dispatch_run(head_branch="feat/x")) == "bound"
    assert _q(_dispatch_run(head_branch="main", _in_default_history=False)) == ""


def test_dispatch_run_titled_for_another_sha_is_excluded():
    assert _q(_dispatch_run(display_title=f"Code review PR #{PR} @ {OTHER_SHA}")) == ""


def test_dispatch_run_titled_for_another_pr_is_excluded():
    assert _q(_dispatch_run(display_title=f"Code review PR #8 @ {SHA}")) == ""


def test_dispatch_run_with_unparseable_title_is_excluded():
    assert _q(_dispatch_run(display_title="Code review")) == ""


def test_run_of_another_workflow_is_excluded():
    assert _q(_pr_run(path=".github/workflows/pytest.yml")) == ""


def test_run_path_with_ref_suffix_is_still_the_review_workflow():
    assert _q(_pr_run(path=".github/workflows/code-review.yml@refs/heads/main")) == "bound"


def test_other_event_types_are_excluded():
    assert _q(_pr_run(event="push")) == ""


# --- evaluate_evidence ----------------------------------------------------


def _artifact(**over):
    art = {
        "schema": 1,
        "status": "reviewed",
        "sha": SHA,
        "base_ref": "main",
        "blocking": False,
        "findings": [],
    }
    art.update(over)
    return art


def _entry(run, artifact="default", state="ok"):
    return {
        "run": run,
        "artifact": _artifact() if artifact == "default" else artifact,
        "state": state,
    }


def _ev(entries):
    return gate.evaluate_evidence(
        entries, pr_number=PR, head_sha=SHA, base_ref="main", default_branch="main"
    )


def test_clean_run_is_green():
    got = _ev([_entry(_pr_run())])
    assert (got.green, got.code) == (True, "evidence-clean")


def test_blocking_run_is_red():
    art = _artifact(blocking=True, findings=[{"class": "regression", "file": "a.py"}])
    got = _ev([_entry(_pr_run(), art)])
    assert (got.green, got.code) == (False, "evidence-blocking")


def test_no_runs_is_red():
    got = _ev([])
    assert (got.green, got.code) == (False, "evidence-none")


def test_unbound_runs_do_not_count():
    got = _ev([_entry(_pr_run(head_sha=OTHER_SHA))])
    assert (got.green, got.code) == (False, "evidence-none")


def test_skip_only_evidence_is_red():
    skipped = {
        "schema": 1,
        "status": "skipped",
        "sha": SHA,
        "base_ref": "main",
        "reason": "cosmetic",
    }
    got = _ev([_entry(_pr_run(), skipped)])
    assert (got.green, got.code) == (False, "evidence-none")


def test_skipped_artifact_is_ignored_next_to_a_clean_one():
    skipped = {
        "schema": 1,
        "status": "skipped",
        "sha": SHA,
        "base_ref": "main",
        "reason": "cosmetic",
    }
    got = _ev([_entry(_pr_run(id=1), skipped), _entry(_dispatch_run(id=2))])
    assert (got.green, got.code) == (True, "evidence-clean")


def test_success_run_missing_its_artifact_is_red():
    got = _ev([_entry(_pr_run(), None, state="missing")])
    assert (got.green, got.code) == (False, "evidence-missing")


def test_expired_artifact_is_red_with_its_own_code():
    got = _ev([_entry(_pr_run(), None, state="expired")])
    assert (got.green, got.code) == (False, "evidence-expired")


def test_sticky_worst_blocking_beats_a_later_clean_run():
    blocking = _artifact(blocking=True, findings=[{"class": "concurrency", "file": "a.py"}])
    got = _ev([_entry(_pr_run(id=1), blocking), _entry(_dispatch_run(id=2))])
    assert (got.green, got.code) == (False, "evidence-blocking")


# A non-blocking red is a failure to produce evidence, not a verdict on the code:
# the remediation its message names ("re-dispatch the review") must be able to
# turn the check green, so a clean run for the SHA supersedes it.
_SUPERSEDABLE_REDS = {
    "evidence-missing": lambda run: _entry(run, None, state="missing"),
    "evidence-expired": lambda run: _entry(run, None, state="expired"),
    "evidence-invalid": lambda run: _entry(run, _artifact(blocking=True, findings=[])),
    "evidence-sha-mismatch": lambda run: _entry(run, _artifact(sha=OTHER_SHA)),
    "evidence-base-mismatch": lambda run: _entry(run, _artifact(base_ref="release")),
    # #2024: clean evidence from a run that also lists a PR into another base.
    "evidence-foreign-base": lambda run: _entry(
        {**run, "pull_requests": [_listed(PR, "main"), _listed(8, "release")]}
    ),
}


@pytest.mark.parametrize("code", sorted(_SUPERSEDABLE_REDS))
def test_clean_redispatch_supersedes_a_non_blocking_red(code):
    red = _SUPERSEDABLE_REDS[code](_pr_run(id=1))
    assert _ev([red]).code == code  # the red alone is what the fixture claims
    got = _ev([red, _entry(_dispatch_run(id=2))])
    assert (got.green, got.code) == (True, "evidence-clean")


def test_blocking_stays_sticky_next_to_supersedable_reds_and_a_clean_run():
    blocking = _artifact(blocking=True, findings=[{"class": "regression", "file": "a.py"}])
    got = _ev(
        [
            _entry(_pr_run(id=1), blocking),
            _entry(_pr_run(id=2), None, state="missing"),
            _entry(_dispatch_run(id=3)),
        ]
    )
    assert (got.green, got.code) == (False, "evidence-blocking")


def test_blocking_evidence_from_a_foreign_base_run_still_sticks():
    """A foreign run cannot clear the PR, but its blocking verdict is only stricter."""
    foreign = _pr_run(id=1, pull_requests=[_listed(PR, "main"), _listed(8, "release")])
    got = _ev([_entry(foreign, _artifact(**_BLOCKING)), _entry(_dispatch_run(id=2))])
    assert (got.green, got.code) == (False, "evidence-blocking")


def test_foreign_base_verdict_says_why():
    """The summary the PR author reads names the cause (#2024)."""
    foreign = _pr_run(pull_requests=[_listed(PR, "main"), _listed(8, "release")])
    got = _ev([_entry(foreign)])
    assert got.message == (
        "A review run for this commit also lists an open PR into another base branch, "
        "so it may have run that branch's copy of the review workflow; it is evidence "
        "for no PR. Close or retarget that PR, or have a maintainer re-dispatch the review."
    )


def test_foreign_base_outranks_other_supersedable_reds():
    foreign = _pr_run(id=1, pull_requests=[_listed(PR, "main"), _listed(8, "release")])
    got = _ev([_entry(foreign), _entry(_pr_run(id=2), _artifact(sha=OTHER_SHA))])
    assert (got.green, got.code) == (False, "evidence-foreign-base")


def test_worst_supersedable_red_reported_when_no_clean_run():
    got = _ev(
        [
            _entry(_pr_run(id=1), None, state="missing"),
            _entry(_pr_run(id=2), _artifact(sha=OTHER_SHA)),
        ]
    )
    assert (got.green, got.code) == (False, "evidence-sha-mismatch")


def test_artifact_for_another_sha_is_red():
    got = _ev([_entry(_pr_run(), _artifact(sha=OTHER_SHA))])
    assert (got.green, got.code) == (False, "evidence-sha-mismatch")


def test_artifact_for_another_base_is_red():
    got = _ev([_entry(_pr_run(), _artifact(base_ref="release"))])
    assert (got.green, got.code) == (False, "evidence-base-mismatch")


def test_malformed_artifact_is_red():
    got = _ev([_entry(_pr_run(), _artifact(blocking=True, findings=[]))])
    assert (got.green, got.code) == (False, "evidence-invalid")


def test_failed_run_is_ignored_when_a_success_run_has_clean_evidence():
    failed = _pr_run(id=1, conclusion="failure")
    got = _ev([_entry(failed, None, state="missing"), _entry(_dispatch_run(id=2))])
    assert (got.green, got.code) == (True, "evidence-clean")


def test_failed_run_alone_is_not_evidence():
    got = _ev([_entry(_pr_run(conclusion="failure"), None, state="missing")])
    assert (got.green, got.code) == (False, "evidence-none")


def test_cancelled_run_is_ignored():
    got = _ev(
        [
            _entry(_pr_run(id=1, conclusion="cancelled"), None, state="missing"),
            _entry(_dispatch_run(id=2)),
        ]
    )
    assert (got.green, got.code) == (True, "evidence-clean")


@pytest.mark.parametrize("status", ["queued", "in_progress", "waiting", "pending", "requested"])
def test_unfinished_bound_run_is_red_pending(status):
    run = _pr_run(status=status, conclusion=None)
    got = _ev([_entry(run, None, state="missing"), _entry(_dispatch_run(id=2))])
    assert (got.green, got.code) == (False, "evidence-pending")


def test_action_required_run_is_red():
    run = _pr_run(status="completed", conclusion="action_required")
    got = _ev([_entry(run, None, state="missing")])
    assert (got.green, got.code) == (False, "evidence-pending")


# Each run attempt uploads its own artifact, so one run can yield several entries;
# a run's `conclusion` is its latest attempt's.

_BLOCKING = {"blocking": True, "findings": [{"class": "regression", "file": "a.py"}]}


def test_blocking_attempt_is_not_lifted_by_a_clean_re_run_of_the_same_run():
    run = _pr_run(id=1, run_attempt=2)
    got = _ev([_entry(run, _artifact(**_BLOCKING)), _entry(run)])
    assert (got.green, got.code) == (False, "evidence-blocking")


@pytest.mark.parametrize("conclusion", ["failure", "cancelled"])
def test_blocking_from_a_run_whose_re_run_did_not_succeed_still_counts(conclusion):
    failed = _pr_run(id=1, run_attempt=2, conclusion=conclusion)
    got = _ev([_entry(failed, _artifact(**_BLOCKING)), _entry(_dispatch_run(id=2))])
    assert (got.green, got.code) == (False, "evidence-blocking")


def test_clean_evidence_from_a_run_that_did_not_succeed_is_not_evidence():
    got = _ev([_entry(_pr_run(id=1, run_attempt=2, conclusion="failure"))])
    assert (got.green, got.code) == (False, "evidence-none")


@pytest.mark.parametrize(
    "art",
    [
        _artifact(sha=OTHER_SHA),
        _artifact(blocking=True, findings=[]),
        {"schema": 1, "status": "skipped", "sha": SHA, "base_ref": "main", "reason": "draft"},
    ],
    ids=["sha-mismatch", "invalid", "skipped"],
)
def test_non_blocking_evidence_from_a_failed_run_is_ignored(art):
    failed = _pr_run(id=1, conclusion="failure")
    got = _ev([_entry(failed, art), _entry(_dispatch_run(id=2))])
    assert (got.green, got.code) == (True, "evidence-clean")


def test_unreadable_artifact_alone_is_red():
    got = _ev([_entry(_pr_run(), None, state="unreadable")])
    assert (got.green, got.code) == (False, "evidence-unreadable")


def test_unreadable_artifact_is_not_lifted_by_a_clean_run():
    """It might be the blocking one; a clean run cannot prove otherwise."""
    got = _ev([_entry(_pr_run(id=1), None, state="unreadable"), _entry(_dispatch_run(id=2))])
    assert (got.green, got.code) == (False, "evidence-unreadable")


def test_unreadable_artifact_of_a_failed_run_still_counts():
    failed = _pr_run(id=1, conclusion="failure")
    got = _ev([_entry(failed, None, state="unreadable"), _entry(_dispatch_run(id=2))])
    assert (got.green, got.code) == (False, "evidence-unreadable")


def test_blocking_outranks_unreadable():
    got = _ev(
        [
            _entry(_pr_run(id=1), None, state="unreadable"),
            _entry(_pr_run(id=2), _artifact(**_BLOCKING)),
        ]
    )
    assert (got.green, got.code) == (False, "evidence-blocking")


# --- evaluate_pr: the whole rule ------------------------------------------


def _files(*names):
    return [{"filename": n, "status": "modified"} for n in names]


def _eval(pr, files, entries):
    return gate.evaluate_pr(pr, files, entries, default_branch="main")


def test_draft_is_red_with_the_literal_reason_draft_even_with_clean_evidence():
    got = _eval(_pr(draft=True, changed_files=1), _files("src/a.py"), [_entry(_pr_run())])
    assert (got.green, got.code) == (False, "draft")


def test_draft_beats_an_all_cosmetic_change_set():
    got = _eval(_pr(draft=True, changed_files=1), _files("docs/a.md"), [])
    assert (got.green, got.code) == (False, "draft")


def test_all_cosmetic_change_set_is_green_without_evidence():
    got = _eval(_pr(changed_files=2), _files("docs/a.md", "docs/b.png"), [])
    assert (got.green, got.code) == (True, "cosmetic")


def test_one_code_file_among_cosmetic_ones_needs_evidence():
    got = _eval(_pr(changed_files=2), _files("docs/a.md", "src/a.py"), [])
    assert (got.green, got.code) == (False, "evidence-none")


def test_code_change_with_clean_evidence_is_green():
    got = _eval(_pr(changed_files=1), _files("src/a.py"), [_entry(_pr_run())])
    assert (got.green, got.code) == (True, "evidence-clean")


def test_code_change_with_blocking_evidence_is_red():
    blocking = _artifact(blocking=True, findings=[{"class": "regression", "file": "src/a.py"}])
    got = _eval(_pr(changed_files=1), _files("src/a.py"), [_entry(_pr_run(), blocking)])
    assert (got.green, got.code) == (False, "evidence-blocking")


def test_changed_files_count_mismatch_is_red():
    got = _eval(_pr(changed_files=3001), _files("docs/a.md"), [])
    assert (got.green, got.code) == (False, "files-incomplete")


def test_changed_files_count_mismatch_is_red_even_with_clean_evidence():
    got = _eval(_pr(changed_files=2), _files("src/a.py"), [_entry(_pr_run())])
    assert (got.green, got.code) == (False, "files-incomplete")


def test_empty_change_set_is_red():
    got = _eval(_pr(changed_files=0), [], [])
    assert (got.green, got.code) == (False, "files-empty")


def test_gate_machinery_with_clean_evidence_is_red():
    got = _eval(
        _pr(changed_files=1),
        _files(".github/workflows/code-review.yml"),
        [_entry(_pr_run())],
    )
    assert (got.green, got.code) == (False, "gate-machinery")


def test_the_gate_set_is_read_for_the_prs_base_repo():
    pr = _pr(changed_files=1, base={"ref": "main", "repo": {"full_name": "stranger/other"}})
    with pytest.raises(ValueError, match="stranger/other"):
        _eval(pr, _files("src/a.py"), [_entry(_pr_run())])


def test_dependabot_pr_without_evidence_is_red_with_dispatch_remediation():
    pr = _pr(changed_files=1, user={"login": "dependabot[bot]", "type": "Bot"})
    got = _eval(pr, _files("requirements.txt"), [])
    assert (got.green, got.code) == (False, "untrusted-needs-dispatch")


def test_fork_pr_without_evidence_is_red_with_dispatch_remediation():
    pr = _pr(changed_files=1, head={"sha": SHA, "repo": {"full_name": "stranger/jarvis"}})
    got = _eval(pr, _files("src/a.py"), [])
    assert (got.green, got.code) == (False, "untrusted-needs-dispatch")


def test_fork_pr_with_a_dispatched_clean_review_is_green():
    pr = _pr(changed_files=1, head={"sha": SHA, "repo": {"full_name": "stranger/jarvis"}})
    got = _eval(pr, _files("src/a.py"), [_entry(_dispatch_run())])
    assert (got.green, got.code) == (True, "evidence-clean")


def test_fork_pr_with_a_blocking_dispatched_review_stays_blocking_not_remediation():
    pr = _pr(changed_files=1, head={"sha": SHA, "repo": {"full_name": "stranger/jarvis"}})
    blocking = _artifact(blocking=True, findings=[{"class": "regression", "file": "a.py"}])
    got = _eval(pr, _files("src/a.py"), [_entry(_dispatch_run(), blocking)])
    assert (got.green, got.code) == (False, "evidence-blocking")


def test_fork_pr_all_cosmetic_is_green():
    pr = _pr(changed_files=1, head={"sha": SHA, "repo": {"full_name": "stranger/jarvis"}})
    got = _eval(pr, _files("docs/a.md"), [])
    assert (got.green, got.code) == (True, "cosmetic")


# --- review_skip_reason ---------------------------------------------------


def _skip(pr, files, event="pull_request"):
    return gate.review_skip_reason(pr, files, event)


def test_skip_reason_draft():
    assert _skip(_pr(draft=True), _files("src/a.py")) == "draft"


def test_skip_reason_cosmetic():
    assert _skip(_pr(changed_files=1), _files("docs/a.md")) == "cosmetic"


def test_skip_reason_files_incomplete():
    assert _skip(_pr(changed_files=3001), _files("src/a.py")) == "files-incomplete"


def test_skip_reason_untrusted_on_pull_request_event():
    pr = _pr(changed_files=1, user={"login": "dependabot[bot]", "type": "Bot"})
    assert _skip(pr, _files("requirements.txt")) == "untrusted"


def test_untrusted_pr_is_reviewed_when_a_maintainer_dispatches():
    pr = _pr(changed_files=1, head={"sha": SHA, "repo": {"full_name": "stranger/jarvis"}})
    assert _skip(pr, _files("src/a.py"), event="workflow_dispatch") == ""


def test_trusted_code_change_is_reviewed():
    assert _skip(_pr(changed_files=1), _files("src/a.py")) == ""


# --- resolve_run_target ---------------------------------------------------


def _resolve(event, title, head_sha, pull_requests):
    return gate.resolve_run_target(event, title, head_sha, pull_requests, "main")


def test_resolve_dispatch_target_from_the_run_title():
    got = _resolve("workflow_dispatch", f"Code review PR #{PR} @ {SHA}", OTHER_SHA, [])
    assert got == (7, SHA)


def test_resolve_pull_request_target_from_pull_requests():
    got = _resolve("pull_request", "x", SHA, [_listed(7, "main")])
    assert got == (7, SHA)


@pytest.mark.parametrize("order", ["default-first", "default-last"])
def test_resolve_picks_the_pr_into_the_default_branch(order):
    """#2024: the list holds every open PR on the head, in no promised order."""
    listed = [_listed(7, "main"), _listed(8, "release")]
    if order == "default-last":
        listed.reverse()
    assert _resolve("pull_request", "x", SHA, listed) == (7, SHA)


def test_resolve_run_listing_only_prs_into_other_bases_is_unbound():
    assert _resolve("pull_request", "x", SHA, [_listed(8, "release")]) is None


def test_resolve_command_binds_the_pr_into_the_repos_default_branch(monkeypatch, tmp_path):
    """The workflow's DEFAULT_BRANCH decides, not a hard-coded `main`."""
    out = tmp_path / "out"
    env = {
        "EVENT_NAME": "workflow_run",
        "RUN_EVENT": "pull_request",
        "RUN_HEAD_SHA": SHA,
        "RUN_PULL_REQUESTS": json.dumps([_listed(8, "main"), _listed(7, "trunk")]),
        "DEFAULT_BRANCH": "trunk",
        "GITHUB_OUTPUT": str(out),
    }
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    assert gate.cmd_resolve(_no_client()) == 0
    assert out.read_text(encoding="utf-8") == f'targets=[{{"pr_number":7,"head_sha":"{SHA}"}}]\n'


def _no_client():
    """An event resolve reads its target from the event: building a client is a bug."""

    def make_client(token):
        raise AssertionError("an event resolve must make no API call")

    return argparse.Namespace(make_client=make_client)


def test_resolve_command_with_nothing_bound_emits_no_targets(monkeypatch, tmp_path):
    out = tmp_path / "out"
    env = {
        "EVENT_NAME": "workflow_run",
        "RUN_EVENT": "pull_request",
        "RUN_HEAD_SHA": SHA,
        "RUN_PULL_REQUESTS": "[]",
        "DEFAULT_BRANCH": "main",
        "GITHUB_OUTPUT": str(out),
    }
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    assert gate.cmd_resolve(_no_client()) == 0
    assert out.read_text(encoding="utf-8") == "targets=[]\n"


def test_resolve_command_on_pull_request_target_emits_its_one_target(monkeypatch, tmp_path):
    out = tmp_path / "out"
    env = {
        "EVENT_NAME": "pull_request_target",
        "PR_NUMBER": "7",
        "HEAD_SHA": SHA,
        "GITHUB_OUTPUT": str(out),
    }
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    assert gate.cmd_resolve(_no_client()) == 0
    assert out.read_text(encoding="utf-8") == f'targets=[{{"pr_number":7,"head_sha":"{SHA}"}}]\n'


# --- the scheduled sweep (#2079) -------------------------------------------

SWEEP_LISTING = "repos/o/r/pulls?state=open&base=trunk&per_page=100&page="


def _sha_of(number):
    return f"{number:040x}"


def _sweep(monkeypatch, tmp_path, open_prs=None, page=None):
    """A `schedule` resolve over a read API whose repo defaults to `trunk` and whose
    open PRs into it are `open_prs`, 100 to a page (or `page(n)` answers page n).

    The event variables are absent, as on a real schedule: the sweep must take the
    default branch from the API."""
    if page is None:

        def page(n):
            return open_prs[(n - 1) * 100 : n * 100]

    def listing(method, path, body):
        return page(int(path.removeprefix(SWEEP_LISTING)))

    api = FakeApi({"repos/o/r": {"default_branch": "trunk"}, SWEEP_LISTING: listing})
    out = tmp_path / "out"
    for k in ("RUN_EVENT", "RUN_PULL_REQUESTS", "PR_NUMBER", "HEAD_SHA", "DEFAULT_BRANCH"):
        monkeypatch.delenv(k, raising=False)
    env = {
        "EVENT_NAME": "schedule",
        "GITHUB_REPOSITORY": "o/r",
        "GH_TOKEN": "read-token",
        "GITHUB_OUTPUT": str(out),
    }
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    # Any token but GH_TOKEN is a KeyError.
    return argparse.Namespace(make_client={"read-token": api}.__getitem__), api, out


def test_resolve_on_schedule_targets_every_open_pr_into_the_default_branch(monkeypatch, tmp_path):
    """Expired evidence fires no event, so only a schedule re-decides its PR (#2079)."""
    args, _, out = _sweep(
        monkeypatch, tmp_path, [_open(9, OTHER_SHA, "trunk"), _open(7, SHA, "trunk")]
    )
    assert gate.cmd_resolve(args) == 0
    assert out.read_text(encoding="utf-8") == (
        f'targets=[{{"pr_number":7,"head_sha":"{SHA}"}},'
        f'{{"pr_number":9,"head_sha":"{OTHER_SHA}"}}]\n'
    )


def test_schedule_sweep_with_more_prs_than_one_matrix_holds_fails(monkeypatch, tmp_path):
    """A workflow run holds at most 256 matrix jobs: a sweep that cannot re-decide
    every PR fails rather than leave some greens standing unseen."""
    prs = [_open(n, _sha_of(n), "trunk") for n in range(100, 357)]
    args, _, out = _sweep(monkeypatch, tmp_path, prs)
    with pytest.raises(RuntimeError, match="257 open PRs"):
        gate.cmd_resolve(args)
    assert not out.exists()


def test_schedule_sweep_of_256_prs_targets_them_all(monkeypatch, tmp_path):
    prs = [_open(n, _sha_of(n), "trunk") for n in range(100, 356)]
    args, _, out = _sweep(monkeypatch, tmp_path, prs)
    assert gate.cmd_resolve(args) == 0
    name, _, value = out.read_text(encoding="utf-8").rstrip("\n").partition("=")
    assert name == "targets"
    assert json.loads(value) == [{"pr_number": n, "head_sha": _sha_of(n)} for n in range(100, 356)]


def test_schedule_sweep_whose_open_pr_listing_hits_its_page_cap_sweeps_none(monkeypatch, tmp_path):
    """A listing that never ends within its cap is not read as whole (#2076): the
    PRs it leaves unread would keep a stale green, so the sweep fails and sweeps none."""
    args, api, out = _sweep(
        monkeypatch, tmp_path, page=lambda n: [_open(n * 100 + i, SHA, "trunk") for i in range(100)]
    )
    with pytest.raises(load_client().ListingTruncated):
        gate.cmd_resolve(args)
    assert [p for _, p, _ in api.calls if p.startswith(SWEEP_LISTING)] == [
        f"{SWEEP_LISTING}{n}" for n in range(1, 11)
    ]
    assert not out.exists()


def test_resolve_fork_pull_request_run_is_unbound():
    assert _resolve("pull_request", "x", SHA, []) is None


def test_resolve_unparseable_dispatch_title_is_unbound():
    assert _resolve("workflow_dispatch", "Code review", SHA, []) is None


# --- read_evidence_zip ----------------------------------------------------


def _zip(name, payload):
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(name, payload)
    return buf.getvalue()


def test_zip_with_evidence_is_parsed():
    blob = _zip("review-evidence.json", '{"status": "skipped"}')
    assert gate.read_evidence_zip(blob) == {"status": "skipped"}


def test_zip_without_the_evidence_file_is_malformed():
    assert gate.read_evidence_zip(_zip("other.json", "{}")) == {"status": "malformed"}


def _corrupt(blob):
    """Flip one byte of the stored payload: the zip still opens, its CRC no longer matches."""
    i = blob.index(b'"status"')
    return blob[:i] + b"X" + blob[i + 1 :]


@pytest.mark.parametrize(
    "blob",
    [
        b"not a zip",
        _zip("review-evidence.json", '{"status": "skipped"}')[:-30],
        _corrupt(_zip("review-evidence.json", '{"status": "skipped"}')),
    ],
    ids=["not-a-zip", "cut-off", "crc-mismatch"],
)
def test_unreadable_zip_raises_instead_of_reading_as_malformed(blob):
    """upload-artifact never writes a bad zip, so one means a broken download: its
    verdict is unknown, which is not the same as malformed (a clean run lifts that)."""
    with pytest.raises(gate.UnreadableArtifact):
        gate.read_evidence_zip(blob)


def test_zip_with_invalid_json_is_malformed():
    assert gate.read_evidence_zip(_zip("review-evidence.json", "{nope")) == {"status": "malformed"}


# --- load_entries (fake API) ----------------------------------------------


ARTIFACTS_PATH = "repos/o/r/actions/runs/1001/artifacts"


def _evidence_zip(sha=SHA, blocking=False):
    findings = [{"class": "regression", "file": "a.py"}] if blocking else []
    return _zip(
        "review-evidence.json",
        json.dumps(
            {
                "schema": 1,
                "status": "reviewed",
                "sha": sha,
                "base_ref": "main",
                "blocking": blocking,
                "findings": findings,
            }
        ),
    )


def _art(id, name, expired=False):
    return {"id": id, "name": name, "expired": expired}


def _downloads(api):
    return sorted(int(path.split("/")[-2]) for m, path, _ in api.calls if m == "DOWNLOAD")


def test_load_entries_reads_every_live_attempt():
    """One entry per attempt, keyed `<run id>:<attempt>`: the live ones read, the
    expired attempt 3 an expired entry (the ledger decides whether it sticks, #2062)."""
    api = FakeApi(
        {
            ARTIFACTS_PATH: {
                "artifacts": [
                    _art(1, "review-evidence-1"),
                    _art(2, "review-evidence-2"),
                    _art(3, "review-evidence-3", expired=True),
                ]
            }
        },
        blobs={1: _evidence_zip(blocking=True), 2: _evidence_zip()},
    )
    got = gate.load_entries(api, "o/r", _pr_run(run_attempt=3))
    assert [(e["key"], e["state"], (e["artifact"] or {}).get("blocking")) for e in got] == [
        ("1001:1", "ok", True),
        ("1001:2", "ok", False),
        ("1001:3", "expired", None),
    ]
    assert _downloads(api) == [1, 2]


def test_load_entries_marks_a_successful_attempt_whose_artifact_vanished():
    """A re-run deletes the earlier attempts' artifacts (mim#251). Attempt 1
    succeeded, so it uploaded evidence that is gone now: a keyed missing entry.
    Attempt 2 failed before the upload step, so it left none: no entry."""
    api = FakeApi(
        {
            ARTIFACTS_PATH: {"artifacts": [_art(3, "review-evidence-3")]},
            "repos/o/r/actions/runs/1001/attempts/1": {"conclusion": "success"},
            "repos/o/r/actions/runs/1001/attempts/2": {"conclusion": "failure"},
        },
        blobs={3: _evidence_zip()},
    )
    got = gate.load_entries(api, "o/r", _pr_run(run_attempt=3))
    assert [(e["key"], e["state"]) for e in got] == [("1001:1", "missing"), ("1001:3", "ok")]


def test_load_entries_reads_the_latest_attempts_conclusion_from_the_run():
    """No attempts call for the latest attempt: the run payload is its conclusion."""
    api = FakeApi({ARTIFACTS_PATH: {"artifacts": []}})
    got = gate.load_entries(api, "o/r", _pr_run(run_attempt=1))
    assert [(e["key"], e["state"]) for e in got] == [("1001:1", "missing")]
    assert [p for _, p, _ in api.calls if "/attempts/" in p] == []


@pytest.mark.parametrize(
    "name",
    [
        "claude-execution-output-1",
        "review-evidence-x",
        "review-evidence",  # the pre-#2024 single, overwritable artifact
        "review-evidence-0",
        "review-evidence-1-extra",
        "my-review-evidence-1",
    ],
)
def test_load_entries_ignores_artifacts_not_named_review_evidence_attempt(name):
    api = FakeApi(
        {ARTIFACTS_PATH: {"artifacts": [_art(9, name), _art(1, "review-evidence-1")]}},
        blobs={1: _evidence_zip()},
    )
    got = gate.load_entries(api, "o/r", _pr_run())
    assert [e["state"] for e in got] == ["ok"]
    assert _downloads(api) == [1]


def test_load_entries_all_expired_is_one_expired_entry_per_attempt():
    api = FakeApi(
        {
            ARTIFACTS_PATH: {
                "artifacts": [
                    _art(1, "review-evidence-1", expired=True),
                    _art(2, "review-evidence-2", expired=True),
                ]
            }
        }
    )
    got = gate.load_entries(api, "o/r", _pr_run(run_attempt=2))
    assert [(e["key"], e["state"], e["artifact"]) for e in got] == [
        ("1001:1", "expired", None),
        ("1001:2", "expired", None),
    ]
    assert _downloads(api) == []


@pytest.mark.parametrize(
    "artifacts", [[], [_art(4, "claude-execution-output-1")]], ids=["none", "only-other"]
)
def test_load_entries_without_evidence_is_one_missing_entry(artifacts):
    api = FakeApi({ARTIFACTS_PATH: {"artifacts": artifacts}})
    got = gate.load_entries(api, "o/r", _pr_run())
    assert [(e["state"], e["artifact"]) for e in got] == [("missing", None)]


@pytest.mark.parametrize(
    "exc",
    [
        urllib.error.HTTPError("u", 500, "boom", {}, None),
        urllib.error.URLError("dns"),
        TimeoutError("read timed out"),
        ConnectionResetError("reset"),
        http.client.IncompleteRead(b"PK"),
    ],
    ids=["http", "url", "timeout", "reset", "truncated"],
)
def test_load_entries_failed_download_is_unreadable_not_missing(exc):
    api = FakeApi(
        {
            ARTIFACTS_PATH: {
                "artifacts": [_art(1, "review-evidence-1"), _art(2, "review-evidence-2")]
            }
        },
        blobs={1: exc, 2: _evidence_zip()},
    )
    got = gate.load_entries(api, "o/r", _pr_run())
    assert sorted(e["state"] for e in got) == ["ok", "unreadable"]
    (unreadable,) = [e for e in got if e["state"] == "unreadable"]
    assert unreadable["artifact"] is None


def test_cut_off_blocking_download_is_not_lifted_by_a_clean_attempt():
    """`HTTPResponse.read(amt)` hands back a short body without raising. Attempt 1
    blocking but cut off, attempt 2 clean: the SHA must not go green."""
    api = FakeApi(
        {
            ARTIFACTS_PATH: {
                "artifacts": [_art(1, "review-evidence-1"), _art(2, "review-evidence-2")]
            }
        },
        blobs={1: _evidence_zip(blocking=True)[:-30], 2: _evidence_zip()},
    )
    got = gate.load_entries(api, "o/r", _pr_run())
    assert sorted(e["state"] for e in got) == ["ok", "unreadable"]
    verdict = _ev(got)
    assert (verdict.green, verdict.code) == (False, "evidence-unreadable")


class _Resp:
    def __init__(self, body, content_length=None):
        self._body = body
        self.headers = {} if content_length is None else {"Content-Length": str(content_length)}

    def read(self, amt):
        return self._body[:amt]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


ZIP = "repos/o/r/actions/artifacts/1/zip"
ZIP_URL = f"https://api.github.com/{ZIP}"
BLOB_URL = "https://blob.example/z"


def _download(script):
    """`download(ZIP, read_capped)` of a real client over `script`."""
    transport = FakeTransport(script)
    client = load_client().Client(
        "tok", user_agent="code-gate-verdict", sleep=lambda s: None, transport=transport
    )
    return lambda: client.download(ZIP, gate.read_capped), transport


def test_download_rejects_a_cut_off_body_served_directly():
    cut_off = FakeResponse(b"PK-z", headers={"Content-Length": "6"})
    download, transport = _download({ZIP_URL: [cut_off]})
    with pytest.raises(gate.UnreadableArtifact):
        download()
    assert [r.url for r in transport.requests] == [ZIP_URL]


def test_download_rejects_a_cut_off_body_behind_the_redirect():
    redirect = http_error(302, headers={"Location": BLOB_URL}, url=ZIP_URL)
    cut_off = FakeResponse(b"PK-z", headers={"Content-Length": "6"})
    download, transport = _download({ZIP_URL: [redirect], BLOB_URL: [cut_off]})
    with pytest.raises(gate.UnreadableArtifact):
        download()
    _, follow = transport.requests
    assert follow.url == BLOB_URL
    assert "authorization" not in follow.headers


def test_read_capped_returns_a_whole_body():
    assert gate.read_capped(_Resp(b"PK-zip", content_length=6)) == b"PK-zip"
    assert gate.read_capped(_Resp(b"PK-zip")) == b"PK-zip"


def test_read_capped_raises_on_a_body_shorter_than_its_content_length():
    with pytest.raises(gate.UnreadableArtifact):
        gate.read_capped(_Resp(b"PK-z", content_length=6))


def test_read_capped_raises_on_an_oversized_body_instead_of_truncating_it():
    with pytest.raises(gate.UnreadableArtifact):
        gate.read_capped(_Resp(b"x" * 11), limit=10)
    assert gate.read_capped(_Resp(b"x" * 10), limit=10) == b"x" * 10


@pytest.mark.parametrize("conclusion", ["failure", "cancelled", "timed_out"])
def test_load_entries_reads_a_run_whose_latest_attempt_did_not_succeed(conclusion):
    """An earlier attempt's blocking artifact outlives a failed or cancelled re-run."""
    api = FakeApi(
        {ARTIFACTS_PATH: {"artifacts": [_art(1, "review-evidence-1")]}},
        blobs={1: _evidence_zip(blocking=True)},
    )
    got = gate.load_entries(api, "o/r", _pr_run(conclusion=conclusion))
    assert [(e["state"], e["artifact"]["blocking"]) for e in got] == [("ok", True)]


@pytest.mark.parametrize(
    "status,conclusion",
    [("in_progress", None), ("queued", None), ("completed", "action_required")],
)
def test_load_entries_makes_no_call_for_an_unfinished_or_unapproved_run(status, conclusion):
    api = FakeApi()
    got = gate.load_entries(api, "o/r", _pr_run(status=status, conclusion=conclusion))
    assert [(e["state"], e["artifact"]) for e in got] == [("missing", None)]
    assert api.calls == []


RUNS_PATH = "repos/o/r/actions/workflows/code-review.yml/runs"


def test_gather_then_evaluate_keeps_blocking_from_an_earlier_attempt():
    """End to end over the API shape: attempt 1 blocking, the re-run (attempt 2)
    clean and the run's conclusion success — the SHA stays blocked."""
    api = FakeApi(
        {
            RUNS_PATH: {"workflow_runs": [_pr_run(run_attempt=2)]},
            ARTIFACTS_PATH: {
                "artifacts": [_art(1, "review-evidence-1"), _art(2, "review-evidence-2")]
            },
        },
        blobs={1: _evidence_zip(blocking=True), 2: _evidence_zip()},
    )
    entries = gate.gather_entries(api, "o/r", PR, SHA, "main", _pr()["created_at"])
    assert len(entries) == 2
    got = _ev(entries)
    assert (got.green, got.code) == (False, "evidence-blocking")


COMPARE_PATH = f"repos/o/r/compare/main...{OTHER_SHA}"
DISPATCH_ARTIFACTS = "repos/o/r/actions/runs/2002/artifacts"


def _payload_dispatch(**over):
    """A dispatch run as the runs API returns it: no history fact."""
    run = _dispatch_run(**over)
    if "_in_default_history" not in over:
        del run["_in_default_history"]
    return run


def _gather(runs, compare):
    api = FakeApi(
        {
            COMPARE_PATH: compare,
            RUNS_PATH: {"workflow_runs": runs},
            DISPATCH_ARTIFACTS: {"artifacts": [_art(1, "review-evidence-1")]},
        },
        blobs={1: _evidence_zip()},
    )
    return api, gate.gather_entries(api, "o/r", PR, SHA, "main", _pr()["created_at"])


def _compares(api):
    return [path for _, path, _ in api.calls if path.startswith("repos/o/r/compare/")]


@pytest.mark.parametrize("status", ["identical", "behind"])
def test_dispatch_run_in_default_history_is_evidence(status):
    """'behind': the default branch moved on past the run's head, and the run still counts (#2024)."""
    api, entries = _gather([_payload_dispatch()], {"status": status})
    assert _compares(api) == [f"{COMPARE_PATH}?per_page=1"]
    got = _ev(entries)
    assert (got.green, got.code) == (True, "evidence-clean")


@pytest.mark.parametrize("status", ["ahead", "diverged"])
def test_dispatch_run_off_default_history_is_not_loaded(status):
    """A tag or branch named `main` puts the run on `branch=main`, not in its history."""
    api, entries = _gather([_payload_dispatch()], {"status": status})
    assert _compares(api) == [f"{COMPARE_PATH}?per_page=1"]
    assert entries == []
    assert _downloads(api) == []


def test_spoofed_history_key_in_the_run_payload_is_ignored():
    _, entries = _gather([_payload_dispatch(_in_default_history=True)], {"status": "diverged"})
    assert entries == []


def test_history_is_checked_only_for_dispatch_runs_titled_for_this_pr_and_sha():
    runs = [
        _payload_dispatch(id=2003, display_title=f"Code review PR #8 @ {SHA}"),
        _payload_dispatch(id=2004, display_title=f"Code review PR #{PR} @ {OTHER_SHA}"),
        _pr_run(),
    ]
    api = FakeApi(
        {
            RUNS_PATH: {"workflow_runs": runs},
            ARTIFACTS_PATH: {"artifacts": [_art(1, "review-evidence-1")]},
        },
        blobs={1: _evidence_zip()},
    )
    entries = gate.gather_entries(api, "o/r", PR, SHA, "main", _pr()["created_at"])
    assert _compares(api) == []
    assert [e["run"]["id"] for e in entries] == [1001]


def test_gather_loads_a_foreign_base_run_so_its_blocking_verdict_sticks():
    foreign = _pr_run(pull_requests=[_listed(PR, "main"), _listed(8, "release")])
    api = FakeApi(
        {
            RUNS_PATH: {"workflow_runs": [foreign]},
            ARTIFACTS_PATH: {"artifacts": [_art(1, "review-evidence-1")]},
        },
        blobs={1: _evidence_zip(blocking=True)},
    )
    got = _ev(gate.gather_entries(api, "o/r", PR, SHA, "main", _pr()["created_at"]))
    assert (got.green, got.code) == (False, "evidence-blocking")


@pytest.mark.parametrize("code", [404, 422])
def test_unknown_or_unrelated_commit_is_not_in_default_history(code):
    err = urllib.error.HTTPError(COMPARE_PATH, code, "x", {}, None)
    assert gate.in_default_history(FakeApi({COMPARE_PATH: err}), "o/r", "main", OTHER_SHA) is False


def test_compare_server_error_is_raised_not_read_as_off_history():
    err = urllib.error.HTTPError(COMPARE_PATH, 502, "x", {}, None)
    with pytest.raises(urllib.error.HTTPError) as caught:
        gate.in_default_history(FakeApi({COMPARE_PATH: err}), "o/r", "main", OTHER_SHA)
    assert caught.value.code == 502


# --- fetch_pr_snapshot ----------------------------------------------------


def test_snapshot_returns_pr_and_files():
    pr = _pr(changed_files=1)
    api = FakeApi({"repos/o/r/pulls/7/files": [{"filename": "a.py"}], "repos/o/r/pulls/7": pr})
    got_pr, got_files = gate.fetch_pr_snapshot(api, "o/r", 7)
    assert got_pr["head"]["sha"] == SHA
    assert got_files == [{"filename": "a.py"}]


def _open_pr(head_sha=SHA, **over):
    return _pr(
        state="open",
        merged=False,
        head={"sha": head_sha, "repo": {"full_name": "Osasuwu/jarvis"}},
        **over,
    )


def _moving_api(**over):
    return SequencedApi(_open_pr(SHA, **over), _open_pr(OTHER_SHA, **over))


def test_snapshot_fails_when_the_head_moves_mid_read():
    with pytest.raises(gate.HeadMovedError, match="head moved"):
        gate.fetch_pr_snapshot(_moving_api(), "o/r", 7)


# --- post_check (fake API) ------------------------------------------------


CHECKS_PATH = f"repos/o/r/commits/{SHA}/check-runs"
RED = gate.Verdict(False, "evidence-none", "no review")
GREEN = gate.Verdict(True, "cosmetic", "cosmetic")


def test_post_check_patches_this_apps_existing_check_run():
    runs = [{"id": 9, "app": {"id": 123}}, {"id": 8, "app": {"id": 15368}}]
    api = FakeApi({CHECKS_PATH: {"check_runs": runs}})
    assert gate.post_check(api, "o/r", SHA, RED, 123)[0] == "patched"
    method, path, body = api.calls[-1]
    assert (method, path) == ("PATCH", "repos/o/r/check-runs/9")
    assert body["conclusion"] == "failure"
    assert body["output"]["title"] == "code-gate: evidence-none"


def test_post_check_creates_only_when_the_app_has_none():
    """A new commit has no check yet, so it starts with an empty ledger: that is
    how a new commit, and only a new commit, clears a sticky red."""
    api = FakeApi({CHECKS_PATH: {"check_runs": [{"id": 8, "app": {"id": 15368}}]}})
    assert gate.post_check(api, "o/r", SHA, GREEN, 123)[0] == "created"
    method, path, body = api.calls[-1]
    assert (method, path) == ("POST", "repos/o/r/check-runs")
    assert (body["name"], body["head_sha"], body["conclusion"]) == ("code-gate", SHA, "success")
    assert _ledger_of(body) == {"v": 1, "sticky": None, "observed": []}


# --- the ledger: blocking stays sticky after its artifact is gone (#2062) ---


def _ledger_text(sticky, observed):
    return (
        "<!-- code-gate-ledger "
        + json.dumps({"v": 1, "sticky": sticky, "observed": observed})
        + " -->"
    )


def _check(id=9, app=123, title="code-gate: evidence-clean", text=None):
    out = {"title": title, "summary": "s"}
    if text is not None:
        out["text"] = text
    return {"id": id, "app": {"id": app}, "output": out}


def _ledger_of(body):
    m = re.search(r"<!-- code-gate-ledger (\{.*?\}) -->", body["output"].get("text") or "")
    assert m, body["output"]
    return json.loads(m.group(1))


CLEAN = gate.Verdict(True, "evidence-clean", "clean")
NOTHING = gate.Observation(frozenset(), frozenset(), False)


def _post(checks, verdict, observation=NOTHING):
    api = FakeApi({CHECKS_PATH: {"check_runs": checks}})
    how, posted = gate.post_check(api, "o/r", SHA, verdict, 123, observation)
    bodies = [body for m, _, body in api.calls if m in ("PATCH", "POST")]
    return api, posted, bodies


def test_post_check_reads_every_check_run_of_the_app_not_just_the_latest():
    api, _, _ = _post([], CLEAN)
    ((_, path, _),) = [c for c in api.calls if c[0] == "GET"]
    assert "filter=all" in path


def test_observed_blocking_is_written_to_the_ledger():
    obs = gate.Observation(frozenset({"1001:1"}), frozenset(), True)
    _, posted, (body,) = _post([_check()], gate._verdict("evidence-blocking"), obs)
    assert posted.code == "evidence-blocking"
    assert _ledger_of(body) == {"v": 1, "sticky": "evidence-blocking", "observed": ["1001:1"]}


def test_ledgered_blocking_outlives_its_artifact_and_a_clean_result():
    """AC1: the blocking artifact was read once; it is now deleted or expired and
    a re-run came back clean. The SHA stays red, and the ledger keeps saying so."""
    prior = _check(text=_ledger_text("evidence-blocking", ["1001:1"]))
    obs = gate.Observation(frozenset({"1001:2"}), frozenset({"1001:1"}), False)
    _, posted, (body,) = _post([prior], CLEAN, obs)
    assert (posted.green, posted.code) == (False, "evidence-blocking")
    assert body["conclusion"] == "failure"
    assert body["output"]["title"] == "code-gate: evidence-blocking"
    assert _ledger_of(body) == {
        "v": 1,
        "sticky": "evidence-blocking",
        "observed": ["1001:1", "1001:2"],
    }


@pytest.mark.parametrize(
    "verdict",
    [
        gate.Verdict(False, "verdict-error", "boom"),
        gate.Verdict(False, "draft", "draft"),
        gate.Verdict(True, "cosmetic", "cosmetic"),
    ],
    ids=["verdict-error", "draft", "cosmetic"],
)
def test_no_other_verdict_erases_the_ledger(verdict):
    prior = _check(text=_ledger_text("evidence-blocking", ["1001:1"]))
    _, posted, (body,) = _post([prior], verdict)
    assert posted.code == "evidence-blocking"
    assert _ledger_of(body)["sticky"] == "evidence-blocking"


def test_a_successful_attempt_never_read_before_it_vanished_is_sticky():
    """The re-run raced the verdict: attempt 1's artifact was deleted before any
    verdict read it. It may have been blocking, so the SHA stays red."""
    obs = gate.Observation(frozenset({"1001:2"}), frozenset({"1001:1"}), False)
    _, posted, (body,) = _post([_check()], CLEAN, obs)
    assert (posted.green, posted.code) == (False, "evidence-unobserved")
    assert _ledger_of(body)["sticky"] == "evidence-unobserved"


def test_a_gone_artifact_that_was_read_clean_does_not_stick():
    """AC3: attempt 1 was read clean and has expired since; a clean run lifts it."""
    prior = _check(text=_ledger_text(None, ["1001:1"]))
    obs = gate.Observation(frozenset({"2002:1"}), frozenset({"1001:1"}), False)
    _, posted, (body,) = _post([prior], CLEAN, obs)
    assert (posted.green, posted.code) == (True, "evidence-clean")
    assert _ledger_of(body) == {"v": 1, "sticky": None, "observed": ["1001:1", "2002:1"]}


def test_blocking_seen_later_upgrades_an_unobserved_sticky():
    prior = _check(text=_ledger_text("evidence-unobserved", ["1001:2"]))
    obs = gate.Observation(frozenset({"3003:1"}), frozenset(), True)
    _, posted, _ = _post([prior], gate._verdict("evidence-blocking"), obs)
    assert posted.code == "evidence-blocking"


def test_another_apps_ledger_can_neither_lift_nor_plant():
    """AC4: only this App's check runs carry the ledger: a same-named check by
    another app cannot clear a sticky red, nor make a clean SHA red."""
    forged_clear = _check(id=8, app=999, text=_ledger_text(None, ["1001:1"]))
    mine = _check(text=_ledger_text("evidence-blocking", ["1001:1"]))
    _, posted, _ = _post([forged_clear, mine], CLEAN)
    assert posted.code == "evidence-blocking"
    forged_plant = _check(id=8, app=999, text=_ledger_text("evidence-blocking", []))
    _, posted, _ = _post([forged_plant, _check()], CLEAN)
    assert posted.code == "evidence-clean"


def test_ledgers_of_several_own_check_runs_merge_and_all_are_patched():
    a = _check(id=9, text=_ledger_text(None, ["1001:1"]))
    b = _check(id=10, text=_ledger_text("evidence-blocking", ["1001:2"]))
    api, posted, bodies = _post([a, b], CLEAN)
    assert posted.code == "evidence-blocking"
    assert sorted(p for m, p, _ in api.calls if m == "PATCH") == [
        "repos/o/r/check-runs/10",
        "repos/o/r/check-runs/9",
    ]
    assert all(_ledger_of(b)["observed"] == ["1001:1", "1001:2"] for b in bodies)


@pytest.mark.parametrize("order", ["blocking-first", "unobserved-first"])
def test_merged_ledgers_keep_the_strictest_sticky_whatever_the_order(order):
    """A weaker sticky on another of the App's check runs must not mask a blocking
    one, whichever the API lists first (#2062)."""
    blocking = _check(id=9, text=_ledger_text("evidence-blocking", []))
    unobserved = _check(id=10, text=_ledger_text("evidence-unobserved", []))
    checks = [blocking, unobserved] if order == "blocking-first" else [unobserved, blocking]
    _, posted, bodies = _post(checks, CLEAN)
    assert posted.code == "evidence-blocking"
    assert all(_ledger_of(b)["sticky"] == "evidence-blocking" for b in bodies)


def test_a_check_posted_before_the_ledger_existed_keeps_a_blocking_title_sticky():
    legacy = _check(title="code-gate: evidence-blocking")
    _, posted, _ = _post([legacy], CLEAN)
    assert posted.code == "evidence-blocking"


def test_a_check_posted_before_the_ledger_existed_with_another_title_is_an_empty_ledger():
    legacy = _check(title="code-gate: evidence-none")
    _, posted, (body,) = _post([legacy], CLEAN)
    assert posted.code == "evidence-clean"
    assert _ledger_of(body) == {"v": 1, "sticky": None, "observed": []}


@pytest.mark.parametrize(
    "text",
    [
        "<!-- code-gate-ledger {not json -->",
        '<!-- code-gate-ledger {"v": 2, "sticky": null, "observed": []} -->',
        '<!-- code-gate-ledger {"v": 1, "sticky": "evidence-none", "observed": []} -->',
        '<!-- code-gate-ledger {"v": 1, "sticky": null, "observed": "1001:1"} -->',
    ],
    ids=["not-json", "unknown-version", "unknown-sticky", "observed-not-a-list"],
)
def test_an_unreadable_ledger_fails_closed(text):
    _, posted, _ = _post([_check(text=text)], CLEAN)
    assert (posted.green, posted.code) == (False, "evidence-unobserved")


# --- observe: what one evaluation read, for the ledger ----------------------


def _observe(entries):
    return gate.observe(entries, pr_number=PR, head_sha=SHA, base_ref="main", default_branch="main")


def _keyed(run, key, artifact="default", state="ok"):
    return dict(_entry(run, artifact, state), key=key)


def test_observe_records_read_attempts_and_blocking():
    blocking = _artifact(blocking=True, findings=[{"class": "regression", "file": "a.py"}])
    got = _observe(
        [
            _keyed(_pr_run(), "1001:1", blocking),
            _keyed(_pr_run(), "1001:2"),
            _keyed(_pr_run(), "1001:3", None, "missing"),
            _keyed(_pr_run(), "1001:4", None, "expired"),
            _keyed(_pr_run(), "1001:5", None, "unreadable"),
        ]
    )
    assert got == gate.Observation(
        frozenset({"1001:1", "1001:2"}), frozenset({"1001:3", "1001:4"}), True
    )


def test_observe_counts_blocking_from_a_foreign_base_run():
    blocking = _artifact(blocking=True, findings=[{"class": "regression", "file": "a.py"}])
    run = _pr_run(pull_requests=[_listed(PR, "main"), _listed(8, "release")])
    assert _observe([_keyed(run, "1001:1", blocking)]).blocking is True


def test_observe_ignores_runs_not_about_this_pr_and_sha():
    blocking = _artifact(blocking=True, findings=[{"class": "regression", "file": "a.py"}])
    got = _observe(
        [
            _keyed(_pr_run(head_sha=OTHER_SHA), "1001:1", blocking),
            _keyed(_pr_run(id=1002, head_sha=OTHER_SHA), "1002:1", None, "missing"),
        ]
    )
    assert got == NOTHING


def test_observe_does_not_count_a_clean_artifact_as_blocking():
    assert _observe([_keyed(_pr_run(), "1001:1")]).blocking is False


# --- safe_relpath / build_diff --------------------------------------------


@pytest.mark.parametrize(
    "path", ["../x", "/etc/passwd", "a/../b", "a\\b", "C:/x", "a//b", "", "./a"]
)
def test_unsafe_relpaths_are_rejected(path):
    assert gate.safe_relpath(path) is None


def test_ordinary_relpath_is_kept():
    assert gate.safe_relpath("src/pkg/a.py") == "src/pkg/a.py"


def test_build_diff_labels_added_removed_and_renamed_files():
    files = [
        {"filename": "new.py", "status": "added", "patch": "@@ -0,0 +1 @@\n+x"},
        {"filename": "gone.py", "status": "removed", "patch": "@@ -1 +0,0 @@\n-x"},
        {
            "filename": "b.py",
            "previous_filename": "a.py",
            "status": "renamed",
            "patch": "@@ -1 +1 @@\n-x\n+y",
        },
        {"filename": "img.png", "status": "added"},
    ]
    assert gate.build_diff(files) == (
        "diff --git a/new.py b/new.py\n--- /dev/null\n+++ b/new.py\n@@ -0,0 +1 @@\n+x\n"
        "diff --git a/gone.py b/gone.py\n--- a/gone.py\n+++ /dev/null\n@@ -1 +0,0 @@\n-x\n"
        "diff --git a/a.py b/b.py\n--- a/a.py\n+++ b/b.py\n@@ -1 +1 @@\n-x\n+y\n"
    )


# --- dispatch target (#1978 L2) -------------------------------------------


def _http_error(code):
    return urllib.error.HTTPError("https://api.github.com/x", code, "x", {}, None)


def _target_api(pr):
    return FakeApi({"repos/o/r/pulls/7/files": [{"filename": "a.py"}], "repos/o/r/pulls/7": pr})


def _target(api, expected=SHA, event="workflow_dispatch"):
    return gate.snapshot_review_target(api, "o/r", 7, expected, event)


def test_dispatch_at_the_current_open_head_is_snapshotted():
    pr, files = _target(_target_api(_pr(state="open", merged=False)))
    assert pr["head"]["sha"] == SHA
    assert files == [{"filename": "a.py"}]


def test_dispatch_for_a_nonexistent_pr_names_the_cause():
    api = FakeApi({"repos/o/r/pulls/7": _http_error(404)})
    with pytest.raises(gate.DispatchTargetError) as exc:
        _target(api)
    assert str(exc.value) == (
        "PR #7 was not found in o/r: no such pull request "
        "(an issue number is not one), or the token cannot see it"
    )


def test_a_404_on_the_file_list_is_not_reported_as_a_missing_pr():
    api = FakeApi(
        {
            "repos/o/r/pulls/7": _pr(state="open", merged=False),
            "repos/o/r/pulls/7/files": _http_error(404),
        }
    )
    with pytest.raises(urllib.error.HTTPError):
        _target(api)


def test_a_merged_pr_is_refused_before_its_files_are_paged():
    api = _target_api(_pr(state="closed", merged=True))
    with pytest.raises(gate.DispatchTargetError):
        _target(api)
    assert [path for _, path, _ in api.calls] == ["repos/o/r/pulls/7"]


def test_dispatch_for_a_merged_pr_names_the_cause():
    with pytest.raises(gate.DispatchTargetError) as exc:
        _target(_target_api(_pr(state="closed", merged=True)))
    assert str(exc.value) == "PR #7 is merged; there is nothing to review"


def test_dispatch_for_a_closed_pr_names_the_cause():
    with pytest.raises(gate.DispatchTargetError) as exc:
        _target(_target_api(_pr(state="closed", merged=False)))
    assert str(exc.value) == "PR #7 is closed; reopen it before dispatching a review"


def test_dispatch_for_a_superseded_head_names_both_shas():
    with pytest.raises(gate.DispatchTargetError) as exc:
        _target(_target_api(_pr(state="open", merged=False)), expected=OTHER_SHA)
    assert str(exc.value) == (
        f"PR #7 head is {SHA}, this run was for {OTHER_SHA}: "
        "the head moved, dispatch again with the new head_sha"
    )


def test_a_non_404_api_failure_is_not_reported_as_a_missing_pr():
    api = FakeApi({"repos/o/r/pulls/7": _http_error(500)})
    with pytest.raises(urllib.error.HTTPError):
        _target(api)


def test_a_pull_request_run_for_a_since_merged_pr_is_not_a_dispatch_error():
    pr, _ = _target(
        _target_api(_pr(state="closed", merged=True)), expected="", event="pull_request"
    )
    assert pr["number"] == PR


def test_a_pr_merged_while_its_files_are_read_is_not_reviewed_on_dispatch():
    api = SequencedApi(_open_pr(), _pr(state="closed", merged=True))
    with pytest.raises(gate.DispatchTargetError) as exc:
        _target(api)
    assert str(exc.value) == "PR #7 is merged; there is nothing to review"


def test_a_pull_request_run_whose_head_moves_mid_read_is_not_told_to_dispatch():
    with pytest.raises(gate.DispatchTargetError) as exc:
        _target(_moving_api(), event="pull_request")
    assert str(exc.value) == (
        "PR #7 changed while its files were being read: "
        "the head moved, the run on the new head reviews it"
    )


def test_a_fork_pull_request_run_on_a_moved_head_is_told_only_a_dispatch_reviews_it():
    fork = {"sha": SHA, "repo": {"full_name": "stranger/jarvis"}}
    with pytest.raises(gate.DispatchTargetError) as exc:
        _target(
            _target_api(_pr(state="open", merged=False, head=fork)),
            expected=OTHER_SHA,
            event="pull_request",
        )
    assert str(exc.value) == (
        f"PR #7 head is {SHA}, this run was for {OTHER_SHA}: the head moved; "
        "a fork or Dependabot PR is reviewed only by a maintainer dispatch with the new head_sha"
    )


def test_a_runtime_error_from_the_snapshot_is_not_a_dispatch_error():
    api = FakeApi({"repos/o/r/pulls/7": _pr(state="open", merged=False)})
    api.responses["repos/o/r/pulls/7/files"] = RuntimeError("boom")
    with pytest.raises(RuntimeError, match="boom"):
        _target(api)


def _prepare_env(monkeypatch, tmp_path, **overrides):
    summary = tmp_path / "summary.md"
    env = {
        "GITHUB_REPOSITORY": "o/r",
        "GH_TOKEN": "t",
        "PR_NUMBER": "7",
        "EVENT_NAME": "workflow_dispatch",
        "EXPECTED_HEAD_SHA": SHA,
        "GITHUB_STEP_SUMMARY": str(summary),
    }
    env.update(overrides)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    return summary


@pytest.mark.parametrize(
    ("make_api", "expected_head", "message"),
    [
        (
            lambda: _target_api(_pr(state="closed", merged=False)),
            SHA,
            "PR #7 is closed; reopen it before dispatching a review",
        ),
        (
            lambda: FakeApi({"repos/o/r/pulls/7": _http_error(404)}),
            SHA,
            "PR #7 was not found in o/r: no such pull request "
            "(an issue number is not one), or the token cannot see it",
        ),
        (
            lambda: _target_api(_pr(state="open", merged=False)),
            OTHER_SHA,
            f"PR #7 head is {SHA}, this run was for {OTHER_SHA}: "
            "the head moved, dispatch again with the new head_sha",
        ),
        (
            _moving_api,
            SHA,
            "PR #7 changed while its files were being read: "
            "the head moved, dispatch again with the new head_sha",
        ),
    ],
    ids=["closed", "nonexistent", "superseded-head", "moved-mid-read"],
)
def test_prepare_fails_the_step_with_an_annotation_and_a_summary(
    monkeypatch, tmp_path, capsys, make_api, expected_head, message
):
    summary = _prepare_env(monkeypatch, tmp_path, EXPECTED_HEAD_SHA=expected_head)
    api = make_api()
    args = argparse.Namespace(head_dir=str(tmp_path / "head"), make_client={"t": api}.__getitem__)
    code = gate.cmd_prepare(args)
    assert code == 1
    assert f"::error::{message}" in capsys.readouterr().err
    assert summary.read_text("utf-8") == f"**Review not run:** {message}\n"


def test_prepare_lets_an_unrelated_api_failure_propagate(monkeypatch, tmp_path):
    _prepare_env(monkeypatch, tmp_path)
    api = FakeApi({"repos/o/r/pulls/7": _http_error(500)})
    args = argparse.Namespace(head_dir=str(tmp_path / "head"), make_client={"t": api}.__getitem__)
    with pytest.raises(urllib.error.HTTPError):
        gate.cmd_prepare(args)


def test_verdict_on_a_head_moving_mid_read_posts_nothing_and_exits_clean(monkeypatch, capsys):
    for key, value in {
        "GITHUB_REPOSITORY": "o/r",
        "GH_TOKEN": "read-t",
        "GATE_TOKEN": "gate-t",
        "GATE_APP_ID": "123",
        "PR_NUMBER": "7",
        "HEAD_SHA": SHA,
    }.items():
        monkeypatch.setenv(key, value)
    api = _moving_api()
    clients = {"read-t": api, "gate-t": FakeApi()}
    assert gate.cmd_verdict(argparse.Namespace(make_client=clients.__getitem__)) == 0
    assert [m for m, _, _ in api.calls] == ["GET", "GET", "GET"]
    assert capsys.readouterr().out == (
        "PR head moved while its files were being read; the newer SHA has its own evaluation\n"
    )


CHECKS_PATH = f"repos/o/r/commits/{SHA}/check-runs"


def _run_verdict(monkeypatch, read_responses, blobs=None, checks=None):
    """cmd_verdict over a read API answering `read_responses` and a gate API whose
    `code-gate` for the SHA is `checks` (default: green, id 9, app 123)."""
    read = FakeApi(read_responses, blobs)
    if checks is None:
        checks = [{"id": 9, "app": {"id": 123}}]
    write = FakeApi({CHECKS_PATH: {"check_runs": checks}})
    apis = {"read-token": read, "gate-token": write}
    # A token reaching the wrong client is a KeyError: reads use GH_TOKEN, the
    # check write GATE_TOKEN.
    write.args = argparse.Namespace(make_client=apis.__getitem__)
    env = {
        "GITHUB_REPOSITORY": "o/r",
        "HEAD_SHA": SHA,
        "GH_TOKEN": "read-token",
        "GATE_TOKEN": "gate-token",
        "GATE_APP_ID": "123",
        "PR_NUMBER": str(PR),
    }
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    write.read = read
    return write


def test_main_reads_with_gh_token_and_writes_the_check_with_gate_token(monkeypatch):
    """Every other verdict test injects `make_client`. This one runs `main(["verdict"])`
    on the parser's default factory and the real client, at the transport seam: reads
    carry GH_TOKEN and the check write GATE_TOKEN, both as `code-gate-verdict`
    (#2068 review). Swapped, the job's token posts the check or the App's reads."""
    api = "https://api.github.com/"
    pr = _pr(changed_files=1)
    checks = f"{CHECKS_PATH}?check_name=code-gate&filter=all&per_page=100&page=1"
    transport = FakeTransport(
        {
            f"{api}repos/o/r/pulls/{PR}": [pr, pr],
            f"{api}repos/o/r/pulls/{PR}/files?per_page=100&page=1": [
                [{"filename": "a.py", "status": "modified"}]
            ],
            f"{api}repos/o/r": [{"default_branch": "main"}],
            f"{api}{OPEN_PULLS}&per_page=100&page=1": [[pr, _pr(number=8)]],
            f"{api}{checks}": [{"check_runs": []}],
            f"{api}repos/o/r/check-runs": [{"id": 1}],
        }
    )
    monkeypatch.setattr(load_client(), "urllib_transport", transport)
    _run_verdict(monkeypatch, {})
    assert gate.main(["verdict"]) == 0
    reader, writer = "Bearer read-" + "token", "Bearer gate-" + "token"
    assert [
        (r.method, r.url.removeprefix(api), r.headers["authorization"], r.headers["user-agent"])
        for r in transport.requests
    ] == [
        ("GET", f"repos/o/r/pulls/{PR}", reader, "code-gate-verdict"),
        ("GET", f"repos/o/r/pulls/{PR}/files?per_page=100&page=1", reader, "code-gate-verdict"),
        ("GET", f"repos/o/r/pulls/{PR}", reader, "code-gate-verdict"),
        ("GET", "repos/o/r", reader, "code-gate-verdict"),
        ("GET", f"{OPEN_PULLS}&per_page=100&page=1", reader, "code-gate-verdict"),
        ("GET", checks, writer, "code-gate-verdict"),
        ("POST", "repos/o/r/check-runs", writer, "code-gate-verdict"),
    ]
    assert transport.requests[-1].body["conclusion"] == "failure"


def _patched(write):
    return [(path, body) for m, path, body in write.calls if m == "PATCH"]


OPEN_PULLS = "repos/o/r/pulls?state=open&base=main"


def _snapshot_responses(pr=None, **extra):
    pr = pr or _pr(changed_files=1)
    responses = {**extra}
    responses.setdefault(OPEN_PULLS, [pr])
    responses.update(
        {
            f"repos/o/r/pulls/{PR}/files": [{"filename": "a.py", "status": "modified"}],
            f"repos/o/r/pulls/{PR}": pr,
            "repos/o/r": {"default_branch": "main"},
        }
    )
    return responses


@pytest.mark.parametrize(
    "responses",
    [
        _snapshot_responses(
            **{
                "repos/o/r/actions/workflows/code-review.yml/runs": {"workflow_runs": [_pr_run()]},
                ARTIFACTS_PATH: ConnectionResetError("reset"),
            }
        ),
        {f"repos/o/r/pulls/{PR}": urllib.error.URLError("dns")},
    ],
    ids=["artifacts-listing", "pr-snapshot"],
)
def test_a_crashing_verdict_replaces_a_green_check_with_a_red_one(monkeypatch, responses):
    """A crash must not leave the SHA's earlier green standing: it posts red, then fails the job."""
    write = _run_verdict(monkeypatch, responses)
    with pytest.raises(OSError):
        gate.cmd_verdict(write.args)
    ((path, body),) = _patched(write)
    assert path == "repos/o/r/check-runs/9"
    assert body["conclusion"] == "failure"
    assert body["output"]["title"] == "code-gate: verdict-error"


def test_a_pr_into_another_base_posts_no_verdict(monkeypatch):
    """#2024: the check belongs to the commit, so a verdict for a PR into `release`
    would land on a PR into the default branch that shares the head."""
    pr = _pr(changed_files=1, base={"ref": "release", "repo": {"full_name": "o/r"}})
    write = _run_verdict(monkeypatch, _snapshot_responses(pr=pr))
    assert gate.cmd_verdict(write.args) == 0
    assert write.calls == []


def test_two_open_prs_on_one_head_post_shared_head(monkeypatch):
    responses = _snapshot_responses(
        **{OPEN_PULLS: [_pr(changed_files=1), _pr(number=8, changed_files=1)]}
    )
    write = _run_verdict(monkeypatch, responses)
    assert gate.cmd_verdict(write.args) == 0
    ((_, body),) = _patched(write)
    assert (body["conclusion"], body["output"]["title"]) == ("failure", "code-gate: shared-head")


def test_an_open_pr_listing_too_long_to_read_whole_fails_closed(monkeypatch):
    page = [_pr(number=100 + i, head={"sha": OTHER_SHA}) for i in range(100)]
    write = _run_verdict(monkeypatch, _snapshot_responses(**{OPEN_PULLS: page}))
    with pytest.raises(RuntimeError, match="truncated"):
        gate.cmd_verdict(write.args)
    ((_, body),) = _patched(write)
    assert body["conclusion"] == "failure"
    assert body["output"]["title"] == "code-gate: listing-truncated"
    assert "repos/o/r/pulls" in body["output"]["summary"]


# --- page caps fail closed (#2076) -------------------------------------------


def _other_dispatches(n):
    return [
        _payload_dispatch(id=3000 + i, display_title=f"Code review PR #{900 + i} @ {SHA}")
        for i in range(n)
    ]


DISPATCH_LISTING = f"{RUNS_PATH}?event=workflow_dispatch&branch=main&"


def test_a_dispatch_listing_past_its_cap_is_red_naming_the_truncation_not_green(monkeypatch):
    """The PR's own (blocking) dispatch could sit past the cap: a clean pull_request
    run must not read green over a listing the verdict did not read whole."""
    write = _run_verdict(
        monkeypatch,
        _snapshot_responses(
            **{
                f"{RUNS_PATH}?head_sha={SHA}&": {"workflow_runs": [_pr_run()]},
                DISPATCH_LISTING: {"workflow_runs": _other_dispatches(100)},
                ARTIFACTS_PATH: {"artifacts": [_art(1, "review-evidence-1")]},
            }
        ),
        blobs={1: _evidence_zip()},
    )
    with pytest.raises(RuntimeError, match="truncated"):
        gate.cmd_verdict(write.args)
    ((_, body),) = _patched(write)
    assert body["conclusion"] == "failure"
    assert body["output"]["title"] == "code-gate: listing-truncated"
    assert "event=workflow_dispatch" in body["output"]["summary"]
    # The runs API serves at most 1000 results to a filtered query: 10 pages of 100.
    listed = [p for _, p, _ in write.read.calls if p.startswith(DISPATCH_LISTING)]
    assert len(listed) == 10


def test_dispatch_listing_reads_only_runs_created_since_the_pr_could_be_dispatched(monkeypatch):
    """A dispatch for the PR needs the PR to exist (prepare fetches it), and a run
    lives at most 35 days, so older dispatches of other PRs are never read."""
    write = _run_verdict(
        monkeypatch,
        _snapshot_responses(
            **{
                f"{RUNS_PATH}?head_sha={SHA}&": {"workflow_runs": [_pr_run()]},
                DISPATCH_LISTING: {"workflow_runs": []},
                ARTIFACTS_PATH: {"artifacts": [_art(1, "review-evidence-1")]},
            }
        ),
        blobs={1: _evidence_zip()},
    )
    assert gate.cmd_verdict(write.args) == 0
    assert _title(write) == "code-gate: evidence-clean"
    (listed,) = [p for _, p, _ in write.read.calls if p.startswith(DISPATCH_LISTING)]
    # PR created 2026-10-01T12:00:00Z, minus 35 days; `>=` and `:` percent-encoded.
    assert "&created=%3E%3D2026-08-27T12%3A00%3A00Z&" in listed
    (by_sha,) = [p for _, p, _ in write.read.calls if p.startswith(f"{RUNS_PATH}?head_sha=")]
    assert "created=" not in by_sha


def test_post_check_with_a_check_run_listing_past_its_cap_posts_a_new_red_check():
    """This App's check (and its ledger) could sit past the cap, under other apps'
    same-named checks: the verdict posted is red, on a check of its own."""
    foreign = [{"id": 5000 + i, "app": {"id": 15368}} for i in range(100)]
    api = FakeApi({CHECKS_PATH: {"check_runs": foreign}})
    how, posted = gate.post_check(api, "o/r", SHA, GREEN, 123)
    assert (posted.green, posted.code) == (False, "listing-truncated")
    method, path, body = api.calls[-1]
    assert (method, path) == ("POST", "repos/o/r/check-runs")
    assert body["conclusion"] == "failure"
    assert body["output"]["title"] == "code-gate: listing-truncated"


def test_post_check_past_its_cap_reddens_the_read_check_of_ours_and_posts_a_new_one():
    """The check of ours that was read goes red too, and a new red one is posted:
    another of ours past the cap could be the one branch protection reads."""
    foreign = {"check_runs": [{"id": 5000 + i, "app": {"id": 15368}} for i in range(100)]}
    first = {"check_runs": [*foreign["check_runs"][:99], _check(id=77)]}
    page = f"{CHECKS_PATH}?check_name=code-gate&filter=all&per_page=100&page="
    # Longest prefix wins: page 10 is answered by its own key, not page 1's.
    api = FakeApi({f"{page}10": foreign, f"{page}1": first, CHECKS_PATH: foreign})
    gate.post_check(api, "o/r", SHA, GREEN, 123)
    writes = [(m, p, b["conclusion"]) for m, p, b in api.calls if m != "GET"]
    assert writes == [
        ("PATCH", "repos/o/r/check-runs/77", "failure"),
        ("POST", "repos/o/r/check-runs", "failure"),
    ]


@pytest.mark.parametrize("failing_page", [1, 2, 10])
@pytest.mark.parametrize(
    ("status", "body"),
    [(403, "You have exceeded a secondary rate limit"), (429, "")],
    ids=["403-secondary", "429"],
)
def test_post_check_waits_out_a_rate_limited_check_runs_page(failing_page, status, body):
    """#2068: a 403/429 on any check-runs page used to raise out of post_check
    before the check was written. Under the client's policy it is waited out
    (2 s on the first retry) and this App's check is patched."""
    listing = (
        f"https://api.github.com/{CHECKS_PATH}?check_name=code-gate&filter=all&per_page=100&page="
    )
    foreign = {"check_runs": [{"id": 5000 + i, "app": {"id": 15368}} for i in range(100)]}
    script = {f"{listing}{n}": [foreign] for n in range(1, failing_page)}
    script[f"{listing}{failing_page}"] = [
        http_error(status, body),
        {"check_runs": [{"id": 9, "app": {"id": 123}}]},
    ]
    script["https://api.github.com/repos/o/r/check-runs/9"] = [b""]
    sleeps = []
    transport = FakeTransport(script)
    client = load_client().Client(
        "tok", user_agent="code-gate-verdict", sleep=sleeps.append, transport=transport
    )
    how, posted = gate.post_check(client, "o/r", SHA, GREEN, 123)
    assert (how, posted.code) == ("patched", "cosmetic")
    writes = [(r.method, r.url, r.body["conclusion"]) for r in transport.requests if r.body]
    assert writes == [("PATCH", "https://api.github.com/repos/o/r/check-runs/9", "success")]
    assert sleeps == [2]


# --- post_check cannot read its own check-run listing (#2081) ---------------


@pytest.mark.parametrize(
    "listing",
    [
        {},
        {"check_runs": None},
        {"check_runs": ["x"]},
        http_error(500, "server error"),
        json.JSONDecodeError("Expecting value", "", 0),
        # #2085 AC4: a check of ours whose body is malformed fails in the ledger
        # merge, which sits inside the guarded read: moved out, check 9 is never
        # patched and no red is posted.
        {"check_runs": [{"id": 9, "app": {"id": 123}, "output": "x"}]},
    ],
    ids=[
        "no-check_runs-key",
        "check_runs-null",
        "check_run-not-an-object",
        "http-500",
        "bad-json",
        "own-check-output-not-an-object",
    ],
)
def test_post_check_that_cannot_read_its_listing_posts_a_new_red_check_then_raises(listing):
    """An earlier green check of ours cannot be patched unread, so it would stay
    the latest: a new red check is posted without the listing, and the error
    still leaves post_check so the job fails."""
    api = FakeApi({CHECKS_PATH: listing})
    expected = type(listing) if isinstance(listing, BaseException) else (ValueError, AttributeError)
    with pytest.raises(expected) as raised:
        gate.post_check(api, "o/r", SHA, GREEN, 123)
    if isinstance(listing, BaseException):
        assert raised.value is listing
    writes = [(m, p, b) for m, p, b in api.calls if m != "GET"]
    ((method, path, body),) = writes
    assert (method, path) == ("POST", "repos/o/r/check-runs")
    assert (body["name"], body["head_sha"], body["status"]) == ("code-gate", SHA, "completed")
    assert body["conclusion"] == "failure"
    assert body["output"]["title"] == "code-gate: verdict-error"
    assert type(raised.value).__name__ in body["output"]["summary"]
    assert "`cosmetic`" in body["output"]["summary"]
    assert _ledger_of(body) == {"v": 1, "sticky": None, "observed": []}


def test_post_check_unreadable_listing_keeps_a_blocking_seen_this_run_sticky():
    api = FakeApi({CHECKS_PATH: {}})
    seen_blocking = gate.Observation(frozenset({"1001:1"}), frozenset(), True)
    with pytest.raises(ValueError):
        gate.post_check(api, "o/r", SHA, GREEN, 123, seen_blocking)
    (body,) = [b for m, _, b in api.calls if m == "POST"]
    assert _ledger_of(body) == {"v": 1, "sticky": "evidence-blocking", "observed": ["1001:1"]}


def test_post_check_unreadable_listing_plants_no_unobserved_sticky_it_cannot_check():
    """Attempt 1001:1 is gone now, but a ledger that could not be read may record it
    as observed: an `evidence-unobserved` planted here would hold until a new commit."""
    api = FakeApi({CHECKS_PATH: {}})
    observation = gate.Observation(frozenset({"1001:2"}), frozenset({"1001:1"}), False)
    with pytest.raises(ValueError):
        gate.post_check(api, "o/r", SHA, GREEN, 123, observation)
    (body,) = [b for m, _, b in api.calls if m == "POST"]
    assert _ledger_of(body) == {"v": 1, "sticky": None, "observed": ["1001:2"]}


def test_post_check_unreadable_listing_whose_red_post_fails_raises_the_listing_error(capsys):
    api = FakeApi({CHECKS_PATH: {}}, writes={"repos/o/r/check-runs": http_error(502)})
    with pytest.raises(ValueError, match="check_runs"):
        gate.post_check(api, "o/r", SHA, GREEN, 123)
    assert [m for m, _, _ in api.calls] == ["GET", "POST"]
    assert "::error::" in capsys.readouterr().err


def test_verdict_whose_check_listing_is_malformed_posts_red_and_fails_the_job(monkeypatch):
    """AC: the clean verdict is computed, but check 9 (green) cannot be read to be
    patched, so a new red check is posted and cmd_verdict still raises."""
    write = _run_verdict(
        monkeypatch,
        _snapshot_responses(
            **{
                RUNS_PATH: {"workflow_runs": [_pr_run(run_attempt=1)]},
                ARTIFACTS_PATH: {"artifacts": [_art(1, "review-evidence-1")]},
            }
        ),
        blobs={1: _evidence_zip()},
    )
    write.responses[CHECKS_PATH] = {}
    with pytest.raises(ValueError, match="check_runs"):
        gate.cmd_verdict(write.args)
    assert _patched(write) == []
    ((method, path, body),) = [c for c in write.calls if c[0] != "GET"]
    assert (method, path, body["conclusion"]) == ("POST", "repos/o/r/check-runs", "failure")
    assert body["output"]["title"] == "code-gate: verdict-error"
    assert "`evidence-clean`" in body["output"]["summary"]


def test_verdict_that_crashed_over_an_unreadable_check_listing_keeps_the_crash(monkeypatch):
    """#2085 AC3: the verdict crashed, then the check listing could not be read
    either. The red check's summary carries the crash text, and the listing error
    the job fails with is chained to the crash."""
    crash = urllib.error.URLError("dns")
    write = _run_verdict(monkeypatch, {f"repos/o/r/pulls/{PR}": crash})
    write.responses[CHECKS_PATH] = {}
    with pytest.raises(ValueError, match="check_runs") as raised:
        gate.cmd_verdict(write.args)
    assert raised.value.__cause__ is crash
    ((method, _, body),) = [c for c in write.calls if c[0] != "GET"]
    assert (method, body["output"]["title"]) == ("POST", "code-gate: verdict-error")
    assert "(URLError: <urlopen error dns>)" in body["output"]["summary"]


# --- post_check whose PATCH fails (#2085) ------------------------------------


PATCH_9 = "repos/o/r/check-runs/9"


@pytest.mark.parametrize(
    "make_failure",
    [
        lambda: http_error(502),
        # github_client raises these at once, with no retry: the likeliest
        # single-shot PATCH failures (#2102 review m1).
        lambda: urllib.error.URLError("dns"),
        lambda: TimeoutError("timed out"),
    ],
    ids=["http-502", "url-error", "timeout"],
)
def test_post_check_whose_patch_fails_on_a_red_verdict_posts_a_new_red_check_then_raises(
    make_failure,
):
    """Check 9 (green) could not be patched red, so it would stay the latest: a new
    red check carrying the merged ledger is posted, and the PATCH's error still
    leaves post_check so the job fails — whatever kind of error the PATCH raised."""
    failed = make_failure()
    prior = _check(text=_ledger_text(None, ["1001:1"]))
    api = FakeApi({CHECKS_PATH: {"check_runs": [prior]}}, writes={PATCH_9: failed})
    obs = gate.Observation(frozenset({"1001:2"}), frozenset(), False)
    with pytest.raises(type(failed)) as raised:
        gate.post_check(api, "o/r", SHA, RED, 123, obs)
    assert raised.value is failed
    writes = [(m, p, b["conclusion"]) for m, p, b in api.calls if m != "GET"]
    assert writes == [
        ("PATCH", PATCH_9, "failure"),
        ("POST", "repos/o/r/check-runs", "failure"),
    ]
    body = api.calls[-1][2]
    assert (body["name"], body["head_sha"], body["status"]) == ("code-gate", SHA, "completed")
    assert body["output"]["title"] == "code-gate: evidence-none"
    assert _ledger_of(body) == {"v": 1, "sticky": None, "observed": ["1001:1", "1001:2"]}


def test_post_check_whose_patch_fails_on_a_green_verdict_posts_nothing_new():
    """A green that could not be written leaves the earlier check as it was; the
    job failing is enough."""
    failed = http_error(502)
    api = FakeApi({CHECKS_PATH: {"check_runs": [_check()]}}, writes={PATCH_9: failed})
    with pytest.raises(urllib.error.HTTPError) as raised:
        gate.post_check(api, "o/r", SHA, CLEAN, 123)
    assert raised.value is failed
    assert [(m, p) for m, p, _ in api.calls if m != "GET"] == [("PATCH", PATCH_9)]


def test_post_check_whose_patch_and_red_post_both_fail_raises_the_patch_error(capsys):
    """The PATCH fails on a red verdict and the red POST that should replace it
    fails too: the PATCH's error is the one raised, and `::error::` says an earlier
    check may still stand."""
    failed = http_error(502)
    api = FakeApi(
        {CHECKS_PATH: {"check_runs": [_check()]}},
        writes={PATCH_9: failed, "repos/o/r/check-runs": http_error(503)},
    )
    with pytest.raises(urllib.error.HTTPError) as raised:
        gate.post_check(api, "o/r", SHA, RED, 123)
    assert raised.value is failed
    assert [m for m, _, _ in api.calls] == ["GET", "PATCH", "POST"]
    assert api.calls[-1][2]["conclusion"] == "failure"
    assert f"an earlier code-gate check may still stand for {SHA}" in capsys.readouterr().err


def test_post_check_whose_later_patch_fails_on_a_red_verdict_posts_a_new_red_check():
    """Two checks of ours: check 9 is patched red, check 10 cannot be. Check 10 may
    be the latest green, so a new red check is still posted after it, and the
    PATCH's error leaves post_check (#2102 review m2)."""
    failed = http_error(502)
    api = FakeApi(
        {CHECKS_PATH: {"check_runs": [_check(), _check(id=10)]}},
        writes={"repos/o/r/check-runs/10": failed},
    )
    with pytest.raises(urllib.error.HTTPError) as raised:
        gate.post_check(api, "o/r", SHA, RED, 123)
    assert raised.value is failed
    writes = [(m, p, b["conclusion"]) for m, p, b in api.calls if m != "GET"]
    assert writes == [
        ("PATCH", PATCH_9, "failure"),
        ("PATCH", "repos/o/r/check-runs/10", "failure"),
        ("POST", "repos/o/r/check-runs", "failure"),
    ]


# --- cmd_verdict end to end: stickiness past the artifact (#2062) ------------


ATTEMPT_1 = "repos/o/r/actions/runs/1001/attempts/1"


def _rerun_responses(artifacts, attempt_1="success", **extra):
    """Run 1001 re-run once (attempt 2 concluded success); `artifacts` is what the
    artifacts listing shows now."""
    return _snapshot_responses(
        **{
            RUNS_PATH: {"workflow_runs": [_pr_run(run_attempt=2)]},
            ARTIFACTS_PATH: {"artifacts": artifacts},
            ATTEMPT_1: {"conclusion": attempt_1},
            **extra,
        }
    )


def _title(write):
    ((_, body),) = _patched(write)
    return body["output"]["title"]


def test_verdict_reads_blocking_then_the_rerun_deletes_it_stays_blocking(monkeypatch):
    """AC1/AC2, deleted: event 1 reads attempt 1 blocking; the re-run deletes that
    artifact and comes back clean; event 2 must still post blocking."""
    first = _run_verdict(
        monkeypatch,
        _snapshot_responses(
            **{
                RUNS_PATH: {"workflow_runs": [_pr_run(run_attempt=1)]},
                ARTIFACTS_PATH: {"artifacts": [_art(1, "review-evidence-1")]},
            }
        ),
        blobs={1: _evidence_zip(blocking=True)},
    )
    assert gate.cmd_verdict(first.args) == 0
    ((_, body),) = _patched(first)
    assert body["output"]["title"] == "code-gate: evidence-blocking"
    after = [_check(text=body["output"]["text"])]
    second = _run_verdict(
        monkeypatch,
        _rerun_responses([_art(2, "review-evidence-2")]),
        blobs={2: _evidence_zip()},
        checks=after,
    )
    assert gate.cmd_verdict(second.args) == 0
    assert _title(second) == "code-gate: evidence-blocking"


def test_ledgered_blocking_stays_after_expiry_and_a_clean_redispatch(monkeypatch):
    """AC1, expired: the blocking attempt expired, a dispatched review is clean."""
    responses = _snapshot_responses(
        **{
            RUNS_PATH: {"workflow_runs": [_pr_run(run_attempt=1), _payload_dispatch()]},
            ARTIFACTS_PATH: {"artifacts": [_art(1, "review-evidence-1", expired=True)]},
            DISPATCH_ARTIFACTS: {"artifacts": [_art(5, "review-evidence-1")]},
            COMPARE_PATH: {"status": "behind"},
        }
    )
    write = _run_verdict(
        monkeypatch,
        responses,
        blobs={5: _evidence_zip()},
        checks=[_check(text=_ledger_text("evidence-blocking", ["1001:1"]))],
    )
    assert gate.cmd_verdict(write.args) == 0
    assert _title(write) == "code-gate: evidence-blocking"


def test_rerun_before_the_verdict_read_attempt_1_is_red_unobserved(monkeypatch):
    """The race: nothing ever read attempt 1, a successful attempt whose artifact
    the re-run deleted. A clean attempt 2 does not lift it."""
    write = _run_verdict(
        monkeypatch,
        _rerun_responses([_art(2, "review-evidence-2")]),
        blobs={2: _evidence_zip()},
        checks=[_check()],
    )
    assert gate.cmd_verdict(write.args) == 0
    assert _title(write) == "code-gate: evidence-unobserved"


def test_rerun_after_a_failed_attempt_1_can_go_green(monkeypatch):
    """Attempt 1 failed before uploading anything: there is nothing it could hide."""
    write = _run_verdict(
        monkeypatch,
        _rerun_responses([_art(2, "review-evidence-2")], attempt_1="failure"),
        blobs={2: _evidence_zip()},
        checks=[_check()],
    )
    assert gate.cmd_verdict(write.args) == 0
    assert _title(write) == "code-gate: evidence-clean"


def test_clean_read_then_expired_is_lifted_by_a_clean_redispatch(monkeypatch):
    """AC3: never blocking, attempt 1 read clean and since expired; a clean
    dispatched review turns the SHA green."""
    responses = _snapshot_responses(
        **{
            RUNS_PATH: {"workflow_runs": [_pr_run(run_attempt=1), _payload_dispatch()]},
            ARTIFACTS_PATH: {"artifacts": [_art(1, "review-evidence-1", expired=True)]},
            DISPATCH_ARTIFACTS: {"artifacts": [_art(5, "review-evidence-1")]},
            COMPARE_PATH: {"status": "behind"},
        }
    )
    write = _run_verdict(
        monkeypatch,
        responses,
        blobs={5: _evidence_zip()},
        checks=[_check(text=_ledger_text(None, ["1001:1"]))],
    )
    assert gate.cmd_verdict(write.args) == 0
    assert _title(write) == "code-gate: evidence-clean"


def test_a_green_check_whose_only_evidence_expired_goes_red_expired(monkeypatch):
    """#2079 AC2: attempt 1 was read clean, so the check is green; its artifact has
    since expired. Re-deciding the SHA (what the daily sweep does) turns it red, and
    not sticky: the ledger records no sticky red."""
    responses = _snapshot_responses(
        **{
            RUNS_PATH: {"workflow_runs": [_pr_run(run_attempt=1)]},
            ARTIFACTS_PATH: {"artifacts": [_art(1, "review-evidence-1", expired=True)]},
        }
    )
    write = _run_verdict(
        monkeypatch, responses, checks=[_check(text=_ledger_text(None, ["1001:1"]))]
    )
    assert gate.cmd_verdict(write.args) == 0
    ((_, body),) = _patched(write)
    assert body["conclusion"] == "failure"
    assert body["output"]["title"] == "code-gate: evidence-expired"
    assert _ledger_of(body) == {"v": 1, "sticky": None, "observed": ["1001:1"]}


def test_a_crashing_verdict_keeps_the_ledger(monkeypatch):
    """verdict-error must not erase what the gate already knows about the SHA."""
    write = _run_verdict(
        monkeypatch,
        {f"repos/o/r/pulls/{PR}": urllib.error.URLError("dns")},
        checks=[_check(text=_ledger_text("evidence-blocking", ["1001:1"]))],
    )
    with pytest.raises(OSError):
        gate.cmd_verdict(write.args)
    ((_, body),) = _patched(write)
    assert body["conclusion"] == "failure"
    assert _ledger_of(body) == {"v": 1, "sticky": "evidence-blocking", "observed": ["1001:1"]}


# --- shared_head_verdict --------------------------------------------------


def _open(number, sha=SHA, base="main"):
    return _pr(number=number, head={"sha": sha}, base={"ref": base})


def test_shared_head_names_every_other_pr_on_the_commit():
    got = gate.shared_head_verdict(_open(PR), [_open(9), _open(PR), _open(8)])
    assert (got.green, got.code) == (False, "shared-head")
    assert got.message.startswith("Open PR(s) #8, #9 into the same base have this same head commit")


@pytest.mark.parametrize(
    "others",
    [[], [_open(8, sha=OTHER_SHA)], [_open(8, base="release")]],
    ids=["alone", "other-head", "other-base"],
)
def test_no_shared_head_without_another_pr_on_the_same_commit_and_base(others):
    assert gate.shared_head_verdict(_open(PR), [_open(PR), *others]) is None


def test_a_pull_request_run_on_a_moved_head_is_not_told_to_dispatch():
    with pytest.raises(gate.DispatchTargetError) as exc:
        _target(
            _target_api(_pr(state="open", merged=False)), expected=OTHER_SHA, event="pull_request"
        )
    assert str(exc.value) == (
        f"PR #7 head is {SHA}, this run was for {OTHER_SHA}: "
        "the head moved, the run on the new head reviews it"
    )


# --- stale-evidence remediation (#1978 L3/L5) -----------------------------


def test_no_evidence_message_covers_a_head_superseded_mid_run():
    got = _ev([])
    assert got.code == "evidence-none"
    assert (
        "superseded: wait for the run on the new head, or dispatch again with the new head_sha"
        in got.message
    )


def test_no_evidence_message_covers_dispatch_before_the_final_push():
    got = _ev([])
    assert got.code == "evidence-none"
    assert "Dispatch after the final push, with that push's head_sha" in got.message


def test_untrusted_dispatch_message_says_to_dispatch_after_the_final_push():
    pr = _pr(changed_files=1, head={"sha": SHA, "repo": {"full_name": "stranger/jarvis"}})
    got = _eval(pr, _files("src/a.py"), [])
    assert got.code == "untrusted-needs-dispatch"
    assert "Dispatch after the final push" in got.message
    assert "the head_sha must be the one pushed last" in got.message


# --- real-API fixtures (#1978 L6) -----------------------------------------
# Payloads captured from Osasuwu/jarvis on 2026-10-07; see the file's _about for
# what was trimmed and the one entry that is derived rather than captured.

REAL = json.loads(
    (Path(__file__).parent / "fixtures" / "code_gate_real_api.json").read_text("utf-8")
)


def _real_entry(case, state="ok", artifact=None):
    return {"run": REAL[case]["run"], "artifact": artifact, "state": state}


def test_real_fork_head_run_is_not_evidence_and_needs_a_dispatch():
    fx = REAL["fork_head"]
    run = fx["run"]
    assert run["head_repository"]["full_name"] == "DaNi64j/jarvis"  # the real shape: a fork run
    assert run["pull_requests"] == []  # GitHub never links a fork-head run to the base repo's PR
    assert gate.run_provenance(run, 2020, fx["pr"]["head"]["sha"], "main") == ""
    got = gate.evaluate_pr(fx["pr"], fx["files"], [_real_entry("fork_head")], "main")
    assert (got.green, got.code) == (False, "untrusted-needs-dispatch")
    # The captured run failed, so evaluate_pr would skip it on that alone; a succeeded twin
    # with clean evidence must still not count, or run_provenance alone guards the fork.
    sha = fx["pr"]["head"]["sha"]
    clean = {
        "schema": 1,
        "status": "reviewed",
        "sha": sha,
        "base_ref": "main",
        "blocking": False,
        "findings": [],
    }
    twin = dict(run, status="completed", conclusion="success")
    got = gate.evaluate_pr(
        fx["pr"], fx["files"], [{"run": twin, "artifact": clean, "state": "ok"}], "main"
    )
    assert (got.green, got.code) == (False, "untrusted-needs-dispatch")


def _per_attempt(fx):
    """The captured artifacts listing, named as the per-attempt upload names them.

    The capture predates the switch to `review-evidence-<run_attempt>` (#2024); the
    payload stays as captured and the name is derived here from the run's own attempt.
    """
    name = f"review-evidence-{fx['run']['run_attempt']}"
    return {
        **fx["artifacts"],
        "artifacts": [dict(a, name=name) for a in fx["artifacts"]["artifacts"]],
    }


def _real_api(fx):
    listing = _per_attempt(fx)
    blob = _zip("review-evidence.json", json.dumps(fx["evidence"])) if "evidence" in fx else None
    return FakeApi(
        {f"repos/o/r/actions/runs/{fx['run']['id']}/artifacts": listing},
        blobs={a["id"]: blob for a in listing["artifacts"]},
    )


def test_real_legacy_artifact_name_is_not_read_as_evidence():
    """The pre-#2024 name is not evidence. The captured attempt succeeded, so it is
    a keyed missing entry: the ledger fails it closed as unobserved (#2062)."""
    fx = REAL["skipped_artifact"]
    assert fx["artifacts"]["artifacts"][0]["name"] == "review-evidence"  # as captured
    assert (fx["run"]["conclusion"], fx["run"].get("run_attempt", 1)) == ("success", 1)
    api = FakeApi({f"repos/o/r/actions/runs/{fx['run']['id']}/artifacts": fx["artifacts"]})
    entries = gate.load_entries(api, "o/r", fx["run"])
    assert entries == [
        {"run": fx["run"], "artifact": None, "state": "missing", "key": "37652874843:1"}
    ]
    got = gate.observe(entries, 1991, fx["run"]["head_sha"], "main", "main")
    assert got == gate.Observation(frozenset(), frozenset({"37652874843:1"}), False)


def test_real_skipped_artifact_is_not_evidence():
    fx = REAL["skipped_artifact"]
    run = fx["run"]
    assert fx["evidence"]["status"] == "skipped"
    entries = gate.load_entries(_real_api(fx), "o/r", run)
    assert [e["state"] for e in entries] == ["ok"]
    assert gate.run_provenance(run, 1991, run["head_sha"], "main") == "bound"
    got = gate.evaluate_evidence(entries, 1991, run["head_sha"], "main", "main")
    assert (got.green, got.code) == (False, "evidence-none")


def _gathered_dispatch(run):
    """A captured dispatch run as gather_entries hands it on once the compare puts
    its head in the default branch's history (#2024)."""
    assert run["event"] == "workflow_dispatch" and "_in_default_history" not in run
    return {**run, "_in_default_history": True}


def test_real_cancelled_run_with_uploaded_evidence_neither_counts_nor_goes_missing():
    fx = REAL["cancelled_run"]
    run = _gathered_dispatch(fx["run"])
    assert (run["status"], run["conclusion"]) == ("completed", "cancelled")
    assert fx["evidence"]["status"] == "reviewed" and fx["evidence"]["blocking"] is False
    sha = fx["pr_head_sha"]
    assert gate.run_provenance(run, 2021, sha, "main") == "bound"  # so the cancel is what decides
    entries = gate.load_entries(_real_api(fx), "o/r", run)
    # Read now (an earlier attempt's blocking artifact would outlive the cancel), and clean.
    assert [(e["state"], e["artifact"]) for e in entries] == [("ok", fx["evidence"])]
    got = gate.evaluate_evidence(entries, 2021, sha, "main", "main")
    assert (got.green, got.code) == (False, "evidence-none")  # not clean, and not evidence-missing


def test_real_cancelled_run_does_not_hide_a_later_clean_run():
    fx = REAL["cancelled_run"]
    sha = fx["pr_head_sha"]
    clean = {
        "id": 1,
        "path": ".github/workflows/code-review.yml@refs/heads/main",
        "event": "workflow_dispatch",
        "status": "completed",
        "conclusion": "success",
        "head_branch": "main",
        "display_title": f"Code review PR #2021 @ {sha}",
        "_in_default_history": True,
    }
    entries = [
        *gate.load_entries(_real_api(fx), "o/r", _gathered_dispatch(fx["run"])),
        {"run": clean, "artifact": fx["evidence"], "state": "ok"},
    ]
    got = gate.evaluate_evidence(entries, 2021, sha, "main", "main")
    assert (got.green, got.code) == (True, "evidence-clean")


def test_real_expired_artifact_is_unlisted_so_its_attempt_is_red_missing():
    """GitHub does not list an expired artifact as `expired: true`: it drops it from
    the run's listing and 404s it by id. So evidence that expires reaches the gate as
    a succeeded attempt with nothing listed, a keyed missing entry: red, and sticky
    unobserved (#2062) for an attempt the gate never read."""
    fx = REAL["expired_artifact"]
    run = fx["run"]
    gone = fx["expired_artifact_id"]
    assert fx["upload_log"][-1].endswith(f"Artifact ID is {gone}")  # it was uploaded
    assert fx["expired_artifact_get"]["status"] == 404
    listed = fx["artifacts"]["artifacts"]
    assert [(a["id"], a["expired"]) for a in listed] == [(11663001308, False)]  # not 'gone'
    # The run's evidence expires the same way, leaving this listing. Derived: the
    # evidence (90-day retention) has not expired yet; the execution log above has.
    after = {**fx["artifacts"], "total_count": 0, "artifacts": []}
    api = FakeApi({f"repos/o/r/actions/runs/{run['id']}/artifacts": after})
    entries = gate.load_entries(api, "o/r", run)
    assert entries == [{"run": run, "artifact": None, "state": "missing", "key": "38032557503:1"}]
    # Captured after PR #2037 merged, which empties pull_requests[]; relink it so the
    # run binds and the verdict, not provenance, decides.
    pr_link = {"number": 2037, "base": {"ref": "main"}}
    bound = [dict(e, run=dict(run, pull_requests=[pr_link])) for e in entries]
    sha = run["head_sha"]
    assert gate.run_provenance(bound[0]["run"], 2037, sha, "main") == "bound"
    got = gate.evaluate_evidence(bound, 2037, sha, "main", "main")
    assert (got.green, got.code) == (False, "evidence-missing")
    seen = gate.observe(bound, 2037, sha, "main", "main")
    assert seen == gate.Observation(frozenset(), frozenset({"38032557503:1"}), False)
