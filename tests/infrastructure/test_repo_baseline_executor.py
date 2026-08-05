"""Tests for scripts/repo_baseline/executor.py — live sync-PR executor.

Mocks at the GhRunner/GhWriteRunner seam via FakeRunner/FakeWriteRunner
(conftest.py) — no subprocess, no network, per AC10.
"""

from __future__ import annotations

import base64

import pytest
from conftest import FakeRunner, FakeWriteRunner, _jarvis_responses

from scripts.repo_baseline.applier import GhCall, GhCallKind
from scripts.repo_baseline.auditor import (
    OSASUWU_REPOS,
    BranchProtection,
    RepoSettings,
    RepoSnapshot,
)
from scripts.repo_baseline.executor import (
    SYNC_BRANCH,
    IdentityError,
    apply_protection,
    diff_phase,
    ensure_sync_branch,
    evaluate_protection_guard,
    execute_account_pass,
    execute_repo,
    find_sync_pr,
    preflight_identity,
    render_pr_body,
    resolve_repos,
    split_calls,
    sync_pr_status,
)
from scripts.repo_baseline.manifest import Manifest

PULLS_PATH = "repos/Osasuwu/jarvis/pulls?head=Osasuwu:repo-baseline/sync&state=all"


def _manifest(**kw) -> Manifest:
    base = {
        "repo": "Osasuwu/jarvis",
        "managed_files": ["a.yml"],
        "language_test_files": [],
        "required_check_contexts": [],
    }
    base.update(kw)
    return Manifest.from_dict(base)


def _pr(
    ref: str = SYNC_BRANCH, state: str = "open", merged_at=None, html_url: str = "https://x/pr/1"
):
    return {"head": {"ref": ref}, "state": state, "merged_at": merged_at, "html_url": html_url}


def _snapshot(*, protection=None) -> RepoSnapshot:
    return RepoSnapshot(
        repo="Osasuwu/jarvis",
        settings=RepoSettings(default_branch="main"),
        labels=[],
        workflows=[],
        branch_protection=protection,
        dependabot_ecosystems=[],
    )


# ── resolve_repos ────────────────────────────────────────────────────────


def test_resolve_repos_unknown_account_raises():
    with pytest.raises(ValueError):
        resolve_repos("nope")


def test_resolve_repos_all_repos_when_repo_none():
    assert resolve_repos("osasuwu") == OSASUWU_REPOS


def test_resolve_repos_single_repo_must_belong_to_account():
    assert resolve_repos("osasuwu", "Osasuwu/jarvis") == ["Osasuwu/jarvis"]


def test_resolve_repos_rejects_repo_not_in_account():
    with pytest.raises(ValueError):
        resolve_repos("osasuwu", "SergazyNarynov/redrobot")


# ── preflight_identity ──────────────────────────────────────────────────


def test_preflight_identity_accepts_matching_login():
    runner = FakeRunner({"user": {"login": "Osasuwu"}})
    preflight_identity(runner, account="osasuwu")


def test_preflight_identity_rejects_mismatched_login():
    runner = FakeRunner({"user": {"login": "SomeoneElse"}})
    with pytest.raises(IdentityError):
        preflight_identity(runner, account="osasuwu")


# ── find_sync_pr / sync_pr_status ───────────────────────────────────────


def test_find_sync_pr_returns_none_when_no_matching_branch():
    runner = FakeRunner({PULLS_PATH: [{"head": {"ref": "other-branch"}, "state": "open"}]})
    assert find_sync_pr(runner, "Osasuwu/jarvis") is None


def test_find_sync_pr_returns_matching_pr():
    pr = _pr()
    runner = FakeRunner({PULLS_PATH: [pr]})
    assert find_sync_pr(runner, "Osasuwu/jarvis") == pr


def test_sync_pr_status_variants():
    assert sync_pr_status(None) == "none"
    assert sync_pr_status(_pr(state="open")) == "pending"
    assert sync_pr_status(_pr(state="closed", merged_at=None)) == "declined"
    assert sync_pr_status(_pr(state="closed", merged_at="2026-01-01T00:00:00Z")) == "none"


# ── split_calls ──────────────────────────────────────────────────────────


def test_split_calls_separates_file_and_context_calls():
    put_call = GhCall(kind=GhCallKind.PUT_FILE, path="a.yml", content="x", file_class="managed")
    del_call = GhCall(kind=GhCallKind.DELETE_FILE, path="b.yml")
    ctx_call = GhCall(
        kind=GhCallKind.SET_CHECK_CONTEXTS, path="<repo-settings>", contexts=("review",)
    )
    file_calls, context_call = split_calls([put_call, del_call, ctx_call])
    assert file_calls == [put_call, del_call]
    assert context_call == ctx_call


def test_split_calls_context_call_none_when_absent():
    put_call = GhCall(kind=GhCallKind.PUT_FILE, path="a.yml", content="x")
    file_calls, context_call = split_calls([put_call])
    assert file_calls == [put_call]
    assert context_call is None


# ── diff_phase ───────────────────────────────────────────────────────────


def _b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def test_diff_phase_skips_identical_content():
    call = GhCall(kind=GhCallKind.PUT_FILE, path="a.yml", content="same\n", file_class="managed")
    runner = FakeRunner(
        {
            "repos/Osasuwu/jarvis/contents/a.yml?ref=main": {
                "sha": "deadbeef",
                "content": _b64("same\n"),
                "encoding": "base64",
            }
        }
    )
    write_ops, skipped = diff_phase(runner, "Osasuwu/jarvis", "main", [call])
    assert write_ops == []
    assert skipped == [call]


def test_diff_phase_emits_write_op_on_content_mismatch():
    call = GhCall(kind=GhCallKind.PUT_FILE, path="a.yml", content="new\n", file_class="managed")
    runner = FakeRunner(
        {
            "repos/Osasuwu/jarvis/contents/a.yml?ref=main": {
                "sha": "deadbeef",
                "content": _b64("old\n"),
                "encoding": "base64",
            }
        }
    )
    write_ops, skipped = diff_phase(runner, "Osasuwu/jarvis", "main", [call])
    assert len(write_ops) == 1
    assert write_ops[0].call == call
    assert write_ops[0].blob_sha == "deadbeef"
    assert skipped == []


def test_diff_phase_new_file_has_no_blob_sha():
    call = GhCall(kind=GhCallKind.PUT_FILE, path="a.yml", content="new\n", file_class="managed")
    runner = FakeRunner({}, not_found={"repos/Osasuwu/jarvis/contents/a.yml?ref=main"})
    write_ops, skipped = diff_phase(runner, "Osasuwu/jarvis", "main", [call])
    assert len(write_ops) == 1
    assert write_ops[0].blob_sha is None
    assert skipped == []


def test_diff_phase_delete_carries_sha_when_present():
    call = GhCall(kind=GhCallKind.DELETE_FILE, path=".github/workflows/stale.yml")
    runner = FakeRunner(
        {"repos/Osasuwu/jarvis/contents/.github/workflows/stale.yml?ref=main": {"sha": "cafebabe"}}
    )
    write_ops, skipped = diff_phase(runner, "Osasuwu/jarvis", "main", [call])
    assert len(write_ops) == 1
    assert write_ops[0].blob_sha == "cafebabe"
    assert skipped == []


def test_diff_phase_delete_skipped_when_already_absent():
    call = GhCall(kind=GhCallKind.DELETE_FILE, path=".github/workflows/gone.yml")
    runner = FakeRunner(
        {}, not_found={"repos/Osasuwu/jarvis/contents/.github/workflows/gone.yml?ref=main"}
    )
    write_ops, skipped = diff_phase(runner, "Osasuwu/jarvis", "main", [call])
    assert write_ops == []
    assert skipped == [call]


# ── evaluate_protection_guard ───────────────────────────────────────────


def test_guard_reportable_when_context_already_live():
    snapshot = _snapshot(protection=BranchProtection(strict=True, contexts=["review"]))
    reportable, reason = evaluate_protection_guard(
        ["review"], snapshot, file_exists=lambda _p: False
    )
    assert reportable is True
    assert reason is None


def test_guard_reportable_when_mapped_and_file_present():
    snapshot = _snapshot(protection=None)
    reportable, reason = evaluate_protection_guard(
        ["pytest"], snapshot, file_exists=lambda _p: True
    )
    assert reportable is True
    assert reason is None


def test_guard_not_reportable_when_mapped_but_file_absent():
    snapshot = _snapshot(protection=None)
    reportable, reason = evaluate_protection_guard(
        ["pytest"], snapshot, file_exists=lambda _p: False
    )
    assert reportable is False
    assert reason


def test_guard_not_reportable_when_unmapped_and_never_checks_file():
    snapshot = _snapshot(protection=None)
    calls = []

    def _file_exists(path):
        calls.append(path)
        return True

    reportable, reason = evaluate_protection_guard(
        ["unmapped-ctx"], snapshot, file_exists=_file_exists
    )
    assert reportable is False
    assert reason
    assert calls == []


# ── apply_protection ─────────────────────────────────────────────────────


def test_apply_protection_defers_on_unreportable_context():
    snapshot = _snapshot(protection=None)
    runner = FakeRunner({})
    write_runner = FakeWriteRunner()
    status = apply_protection(
        runner, write_runner, "Osasuwu/jarvis", "main", ["unmapped-ctx"], snapshot
    )
    assert status.startswith("deferred:")
    assert write_runner.calls == []


def test_apply_protection_patches_when_protection_exists():
    snapshot = _snapshot(protection=BranchProtection(strict=True, contexts=["review"]))
    runner = FakeRunner({})
    write_runner = FakeWriteRunner()
    status = apply_protection(runner, write_runner, "Osasuwu/jarvis", "main", ["review"], snapshot)
    assert status == "applied"
    assert len(write_runner.calls) == 1
    method, path, body = write_runner.calls[0]
    assert method == "PATCH"
    assert path == "repos/Osasuwu/jarvis/branches/main/protection/required_status_checks"
    assert body == {"strict": True, "contexts": ["review"]}


def test_apply_protection_puts_full_payload_when_no_protection():
    snapshot = _snapshot(protection=None)
    runner = FakeRunner(
        {"repos/Osasuwu/jarvis/contents/.github/workflows/pytest.yml?ref=main": {"sha": "x"}}
    )
    write_runner = FakeWriteRunner()
    status = apply_protection(runner, write_runner, "Osasuwu/jarvis", "main", ["pytest"], snapshot)
    assert status == "applied"
    assert len(write_runner.calls) == 1
    method, path, body = write_runner.calls[0]
    assert method == "PUT"
    assert path == "repos/Osasuwu/jarvis/branches/main/protection"
    assert body["required_status_checks"] == {"strict": False, "contexts": ["pytest"]}
    assert body["enforce_admins"] is False
    assert body["required_pull_request_reviews"] is None
    assert body["restrictions"] is None


# ── render_pr_body ───────────────────────────────────────────────────────


def test_render_pr_body_lists_file_calls_sorted_by_path():
    calls = [
        GhCall(kind=GhCallKind.PUT_FILE, path="z.yml", content="x", file_class="managed"),
        GhCall(kind=GhCallKind.DELETE_FILE, path="a.yml"),
    ]
    body = render_pr_body(_manifest(), calls)
    assert body.index("a.yml") < body.index("z.yml")
    assert "delete" in body
    assert "update" in body


def test_render_pr_body_includes_required_contexts_section():
    calls = [
        GhCall(
            kind=GhCallKind.SET_CHECK_CONTEXTS,
            path="<repo-settings>",
            contexts=("review", "pytest"),
        )
    ]
    body = render_pr_body(_manifest(), calls)
    assert "Required check contexts" in body
    assert "review" in body
    assert "pytest" in body


def test_render_pr_body_warns_on_self_modifying_gate():
    calls = [
        GhCall(
            kind=GhCallKind.PUT_FILE,
            path=".github/workflows/code-review.yml",
            content="x",
            file_class="managed",
        )
    ]
    body = render_pr_body(_manifest(), calls)
    assert "Self-modifying gate" in body


def test_render_pr_body_no_gate_warning_when_not_touched():
    calls = [GhCall(kind=GhCallKind.PUT_FILE, path="a.yml", content="x", file_class="managed")]
    body = render_pr_body(_manifest(), calls)
    assert "Self-modifying gate" not in body


# ── ensure_sync_branch ───────────────────────────────────────────────────


def test_ensure_sync_branch_resets_when_branch_exists():
    write_runner = FakeWriteRunner()
    runner = FakeRunner(
        {
            "repos/Osasuwu/jarvis/git/refs/heads/main": {"object": {"sha": "base-sha"}},
            f"repos/Osasuwu/jarvis/git/refs/heads/{SYNC_BRANCH}": {"object": {"sha": "old-sha"}},
        }
    )
    ensure_sync_branch(runner, write_runner, "Osasuwu/jarvis", "main")
    assert len(write_runner.calls) == 1
    method, path, body = write_runner.calls[0]
    assert method == "PATCH"
    assert path == f"repos/Osasuwu/jarvis/git/refs/heads/{SYNC_BRANCH}"
    assert body == {"sha": "base-sha", "force": True}


def test_ensure_sync_branch_creates_when_branch_absent():
    write_runner = FakeWriteRunner()
    runner = FakeRunner(
        {"repos/Osasuwu/jarvis/git/refs/heads/main": {"object": {"sha": "base-sha"}}},
        not_found={f"repos/Osasuwu/jarvis/git/refs/heads/{SYNC_BRANCH}"},
    )
    ensure_sync_branch(runner, write_runner, "Osasuwu/jarvis", "main")
    assert len(write_runner.calls) == 1
    method, path, body = write_runner.calls[0]
    assert method == "POST"
    assert path == "repos/Osasuwu/jarvis/git/refs"
    assert body == {"ref": f"refs/heads/{SYNC_BRANCH}", "sha": "base-sha"}


# ── execute_repo — AC10 minimum cases + AC7 ─────────────────────────────


def test_execute_repo_zero_write_issues_zero_mutating_calls():
    manifest = _manifest(managed_files=[], language_test_files=[], required_check_contexts=[])
    responses = _jarvis_responses()
    responses[PULLS_PATH] = []
    runner = FakeRunner(responses)
    write_runner = FakeWriteRunner()

    outcome = execute_repo(
        "Osasuwu/jarvis", manifest, runner=runner, write_runner=write_runner, execute=True
    )

    assert outcome.file_status == "skipped"
    assert outcome.protection_status == "skipped"
    assert write_runner.calls == []


def test_execute_repo_delete_carries_blob_sha():
    manifest = _manifest(
        managed_files=[], language_test_files=[], required_check_contexts=[], prune=True
    )
    responses = _jarvis_responses()
    responses["repos/Osasuwu/jarvis/actions/workflows?per_page=100"] = {
        "workflows": [{"path": ".github/workflows/stale.yml", "name": "stale"}]
    }
    responses[PULLS_PATH] = []
    responses["repos/Osasuwu/jarvis/contents/.github/workflows/stale.yml?ref=main"] = {
        "sha": "stale-sha"
    }
    responses["repos/Osasuwu/jarvis/git/refs/heads/main"] = {"object": {"sha": "base-sha"}}
    not_found = {f"repos/Osasuwu/jarvis/git/refs/heads/{SYNC_BRANCH}"}
    runner = FakeRunner(responses, not_found=not_found)
    write_runner = FakeWriteRunner(
        responses={("POST", "repos/Osasuwu/jarvis/pulls"): {"html_url": "https://x/pr/9"}}
    )

    outcome = execute_repo(
        "Osasuwu/jarvis", manifest, runner=runner, write_runner=write_runner, execute=True
    )

    assert outcome.file_status == "applied"
    assert outcome.pr_url == "https://x/pr/9"
    delete_calls = [c for c in write_runner.calls if c[0] == "DELETE"]
    assert len(delete_calls) == 1
    _, path, body = delete_calls[0]
    assert path == "repos/Osasuwu/jarvis/contents/.github/workflows/stale.yml"
    assert body["sha"] == "stale-sha"
    branch_create_calls = [
        c for c in write_runner.calls if c[0] == "POST" and c[1] == "repos/Osasuwu/jarvis/git/refs"
    ]
    assert len(branch_create_calls) == 1
    assert branch_create_calls[0][2]["sha"] == "base-sha"


def test_execute_repo_declined_pr_skips_repo():
    manifest = _manifest(
        managed_files=["a.yml"], language_test_files=[], required_check_contexts=[]
    )
    responses = _jarvis_responses()
    responses[PULLS_PATH] = [_pr(state="closed", merged_at=None)]
    runner = FakeRunner(responses)
    write_runner = FakeWriteRunner()

    outcome = execute_repo(
        "Osasuwu/jarvis",
        manifest,
        runner=runner,
        write_runner=write_runner,
        execute=True,
        canon={"a.yml": "content-a\n"},
    )

    assert outcome.file_status == "declined"
    assert outcome.protection_status == "skipped"
    assert outcome.pr_url == "https://x/pr/1"
    assert write_runner.calls == []


def test_execute_repo_guard_defers_on_unreportable_context():
    manifest = _manifest(
        managed_files=[], language_test_files=[], required_check_contexts=["unmapped-ctx"]
    )
    responses = _jarvis_responses()
    responses[PULLS_PATH] = []
    runner = FakeRunner(responses)
    write_runner = FakeWriteRunner()

    outcome = execute_repo(
        "Osasuwu/jarvis", manifest, runner=runner, write_runner=write_runner, execute=True
    )

    assert outcome.file_status == "skipped"
    assert outcome.protection_status.startswith("deferred:")
    assert write_runner.calls == []


def test_execute_repo_identity_preflight_aborts_before_any_write():
    runner = FakeRunner({"user": {"login": "SomeoneElse"}})
    write_runner = FakeWriteRunner()

    with pytest.raises(IdentityError):
        execute_account_pass(
            "osasuwu", runner=runner, write_runner=write_runner, execute=True, canon={}
        )

    assert write_runner.calls == []
    assert runner.calls == [("user", False)]


def test_execute_repo_fails_fast_on_write_error():
    manifest = _manifest(
        managed_files=["a.yml"], language_test_files=[], required_check_contexts=[]
    )
    responses = _jarvis_responses()
    responses[PULLS_PATH] = []
    responses["repos/Osasuwu/jarvis/git/refs/heads/main"] = {"object": {"sha": "base-sha"}}
    not_found = {
        "repos/Osasuwu/jarvis/contents/a.yml?ref=main",
        f"repos/Osasuwu/jarvis/git/refs/heads/{SYNC_BRANCH}",
    }
    runner = FakeRunner(responses, not_found=not_found)
    write_runner = FakeWriteRunner(
        raise_for={("PUT", "repos/Osasuwu/jarvis/contents/a.yml"): RuntimeError("boom")}
    )

    outcome = execute_repo(
        "Osasuwu/jarvis",
        manifest,
        runner=runner,
        write_runner=write_runner,
        execute=True,
        canon={"a.yml": "content\n"},
    )

    assert outcome.file_status.startswith("failed:")
    assert "boom" in outcome.file_status
    assert outcome.protection_status == "skipped"
    assert outcome.pr_url is None
    pulls_calls = [
        c for c in write_runner.calls if c[0] == "POST" and c[1] == "repos/Osasuwu/jarvis/pulls"
    ]
    assert pulls_calls == []


# ── execute_account_pass — AC2 per-repo isolation ───────────────────────


def test_execute_account_pass_isolates_per_repo_errors():
    responses = {}
    not_found = set()
    for repo in OSASUWU_REPOS:
        responses[f"repos/{repo}"] = {"default_branch": "main"}
        responses[f"repos/{repo}/labels"] = []
        responses[f"repos/{repo}/actions/workflows?per_page=100"] = {"workflows": []}
        not_found.add(f"repos/{repo}/branches/main/protection")
        not_found.add(f"repos/{repo}/contents/.github/dependabot.yml")

    failing_repo = "Osasuwu/dnd-calendar"
    raise_for = {f"repos/{failing_repo}": RuntimeError("gh api boom")}
    runner = FakeRunner(responses, not_found=not_found, raise_for=raise_for)
    write_runner = FakeWriteRunner()

    outcomes = execute_account_pass(
        "osasuwu", runner=runner, write_runner=write_runner, execute=False, canon={}
    )

    assert [o.repo for o in outcomes] == OSASUWU_REPOS
    by_repo = {o.repo: o for o in outcomes}

    failed = by_repo[failing_repo]
    assert failed.file_status == "errored"
    assert failed.protection_status == "skipped"
    assert "gh api boom" in failed.error

    for repo in OSASUWU_REPOS:
        if repo == failing_repo:
            continue
        assert by_repo[repo].file_status == "gapped"
        assert by_repo[repo].protection_status == "skipped"

    assert write_runner.calls == []
