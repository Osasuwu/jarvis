"""Tests for the repo-baseline Applier (#939, milestone #48 slice 5).

The Applier is a pure translator (no network), so these tests need no live gh
boundary — they assert the exact ``GhCall`` sequence produced from a plan +
actual state, plus the orchestrator's dry-run report over the committed
fixtures.
"""

from __future__ import annotations

import hashlib

import pytest

from scripts.repo_baseline.applier import (
    OSASUWU_REPOS,
    ApplyError,
    Applier,
    GhCall,
    GhCallKind,
    RepoPlan,
    actual_state_from_snapshot,
    load_canon,
    load_manifest,
    load_snapshot,
    plan_account_pass,
)
from scripts.repo_baseline.auditor import BranchProtection, RepoSettings, RepoSnapshot
from scripts.repo_baseline.manifest import Manifest
from scripts.repo_baseline.planner import Action, ActionKind, ActualState, Planner


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# A canon map keyed by basename, covering exactly the paths a tiny test plan
# touches — so tests don't depend on the real (intentionally incomplete) canon.
_TEST_CANON = {
    "code-review.yml": "review for {{ code_review_marketplace }}\n",
    "owner-queue-guard.yml": "guard on {{ runs_on }}\n",
}


def _manifest(**kw) -> Manifest:
    base = {"repo": "Osasuwu/test", "managed_files": [], "language_test_files": []}
    base.update(kw)
    return Manifest.from_dict(base)


# ── render_content ────────────────────────────────────────────────────


def test_render_content_substitutes_axes():
    applier = Applier(_manifest(), _TEST_CANON)
    out = applier.render_content(".github/workflows/code-review.yml")
    assert out == "review for anthropics/claude-code-action@v1\n"


def test_render_content_missing_canon_raises_with_path():
    applier = Applier(_manifest(), _TEST_CANON)
    with pytest.raises(ApplyError) as exc:
        applier.render_content(".github/workflows/pytest.yml")
    # Error names both the repo-path and the expected canon basename.
    assert "pytest.yml" in str(exc.value)
    assert "Osasuwu/test" in str(exc.value)


# ── translate: WRITE_FILE ─────────────────────────────────────────────


def test_translate_write_file_emits_put_with_rendered_content():
    plan = [
        Action(
            kind=ActionKind.WRITE_FILE,
            path=".github/workflows/code-review.yml",
            file_class="managed",
        )
    ]
    applier = Applier(_manifest(), _TEST_CANON)
    calls = applier.translate(plan, ActualState())
    assert calls == [
        GhCall(
            kind=GhCallKind.PUT_FILE,
            path=".github/workflows/code-review.yml",
            content="review for anthropics/claude-code-action@v1\n",
            file_class="managed",
        )
    ]


def test_translate_write_file_idempotent_when_hash_matches():
    path = ".github/workflows/code-review.yml"
    rendered = "review for anthropics/claude-code-action@v1\n"
    plan = [Action(kind=ActionKind.WRITE_FILE, path=path, file_class="managed")]
    actual = ActualState(files={path: _hash(rendered)})
    calls = Applier(_manifest(), _TEST_CANON).translate(plan, actual)
    assert calls == []  # byte-identical on the repo → no write


def test_translate_write_file_emitted_when_hash_unknown():
    # The auditor records paths with an empty-string hash (body unknown) — the
    # write must still be emitted; the git layer dedupes downstream.
    path = ".github/workflows/code-review.yml"
    plan = [Action(kind=ActionKind.WRITE_FILE, path=path, file_class="managed")]
    actual = ActualState(files={path: ""})
    calls = Applier(_manifest(), _TEST_CANON).translate(plan, actual)
    assert [c.kind for c in calls] == [GhCallKind.PUT_FILE]


# ── translate: DELETE_FILE ────────────────────────────────────────────


def test_translate_delete_only_when_present():
    plan = [
        Action(kind=ActionKind.DELETE_FILE, path=".github/workflows/old.yml"),
        Action(kind=ActionKind.DELETE_FILE, path=".github/workflows/gone.yml"),
    ]
    actual = ActualState(files={".github/workflows/old.yml": ""})
    calls = Applier(_manifest(), _TEST_CANON).translate(plan, actual)
    assert calls == [GhCall(kind=GhCallKind.DELETE_FILE, path=".github/workflows/old.yml")]


# ── translate: SET_CHECK_CONTEXTS ─────────────────────────────────────


def test_translate_set_contexts_emitted_when_differ():
    plan = [
        Action(
            kind=ActionKind.SET_CHECK_CONTEXTS,
            path="<repo-settings>",
            context_names=["review", "owner-queue-guard"],
        )
    ]
    actual = ActualState(required_check_contexts=["review"])
    calls = Applier(_manifest(), _TEST_CANON).translate(plan, actual)
    assert calls == [
        GhCall(
            kind=GhCallKind.SET_CHECK_CONTEXTS,
            path="<repo-settings>",
            contexts=("review", "owner-queue-guard"),
        )
    ]


def test_translate_set_contexts_idempotent_order_insensitive():
    plan = [
        Action(
            kind=ActionKind.SET_CHECK_CONTEXTS,
            path="<repo-settings>",
            context_names=["review", "owner-queue-guard"],
        )
    ]
    actual = ActualState(required_check_contexts=["owner-queue-guard", "review"])
    calls = Applier(_manifest(), _TEST_CANON).translate(plan, actual)
    assert calls == []  # same set, different order → no-op


# ── ordering ──────────────────────────────────────────────────────────


def test_translate_preserves_plan_order():
    plan = [
        Action(kind=ActionKind.WRITE_FILE, path=".github/workflows/code-review.yml"),
        Action(kind=ActionKind.WRITE_FILE, path=".github/workflows/owner-queue-guard.yml"),
        Action(
            kind=ActionKind.SET_CHECK_CONTEXTS,
            path="<repo-settings>",
            context_names=["review"],
        ),
    ]
    calls = Applier(_manifest(), _TEST_CANON).translate(plan, ActualState())
    # Files-before-protection invariant carried through unchanged.
    assert [c.kind for c in calls] == [
        GhCallKind.PUT_FILE,
        GhCallKind.PUT_FILE,
        GhCallKind.SET_CHECK_CONTEXTS,
    ]


# ── missing_canon ─────────────────────────────────────────────────────


def test_missing_canon_flags_uncovered_writes():
    plan = [
        Action(kind=ActionKind.WRITE_FILE, path=".github/workflows/code-review.yml"),
        Action(kind=ActionKind.WRITE_FILE, path=".github/workflows/pytest.yml"),
        Action(kind=ActionKind.DELETE_FILE, path=".github/workflows/old.yml"),
    ]
    gaps = Applier(_manifest(), _TEST_CANON).missing_canon(plan)
    assert gaps == [".github/workflows/pytest.yml"]  # delete is not a canon need


# ── snapshot → actual-state bridge ────────────────────────────────────


def test_actual_state_from_snapshot_maps_workflows_and_contexts():
    snap = RepoSnapshot(
        repo="Osasuwu/test",
        settings=RepoSettings(),
        workflows=[".github/workflows/code-review.yml", ".github/workflows/ci.yml"],
        branch_protection=BranchProtection(strict=True, contexts=["review", "pytest"]),
    )
    actual = actual_state_from_snapshot(snap)
    assert set(actual.files) == {
        ".github/workflows/code-review.yml",
        ".github/workflows/ci.yml",
    }
    assert all(v == "" for v in actual.files.values())  # bodies unknown
    assert actual.required_check_contexts == ["review", "pytest"]


def test_actual_state_from_snapshot_handles_no_branch_protection():
    snap = RepoSnapshot(
        repo="Osasuwu/bare", settings=RepoSettings(), workflows=[], branch_protection=None
    )
    actual = actual_state_from_snapshot(snap)
    assert actual.files == {}
    assert actual.required_check_contexts == []


# ── loaders over committed fixtures ───────────────────────────────────


def test_load_canon_real_fixtures_skip_dunder():
    canon = load_canon()
    assert "code-review.yml" in canon
    assert "__init__.py" not in canon
    # The pytest.yml canon gap this slice surfaces is real (no canon authored yet).
    assert "pytest.yml" not in canon


@pytest.mark.parametrize("repo", OSASUWU_REPOS)
def test_load_manifest_and_snapshot_round_trip(repo):
    manifest = load_manifest(repo)
    snapshot = load_snapshot(repo)
    assert manifest.repo == repo
    assert snapshot.repo == repo


# ── per-account-pass orchestrator (dry-run) ───────────────────────────


def test_plan_account_pass_reports_per_repo():
    plans = plan_account_pass(OSASUWU_REPOS)
    assert [p.repo for p in plans] == OSASUWU_REPOS
    assert all(isinstance(p, RepoPlan) for p in plans)


def test_plan_account_pass_surfaces_pytest_canon_gap():
    # Full-profile repos plan a write for the language-test pytest.yml, which has
    # no canon template yet — the orchestrator must flag it, not crash, and must
    # leave that repo's calls empty (not partially applied).
    plans = {p.repo: p for p in plan_account_pass(OSASUWU_REPOS)}
    flagged = [p for p in plans.values() if p.missing_canon]
    assert flagged, "expected at least one repo to surface the pytest.yml canon gap"
    for p in flagged:
        assert ".github/workflows/pytest.yml" in p.missing_canon
        assert p.calls == []


def test_plan_account_pass_injected_canon_makes_repo_applyable(tmp_path):
    # With a canon map that covers every planned write (including pytest.yml),
    # a repo translates to a non-empty call sequence and no gaps.
    full_canon = dict(load_canon())
    full_canon["pytest.yml"] = "name: pytest on {{ runs_on }}\n"
    plans = plan_account_pass(OSASUWU_REPOS, canon=full_canon)
    assert any(p.calls and not p.missing_canon for p in plans)
    for p in plans:
        assert p.missing_canon == []


def test_plan_account_pass_is_idempotent_against_synced_state(tmp_path):
    # A repo whose actual state already carries every rendered managed body and
    # the required contexts must translate to an empty call sequence — a re-run
    # on a fully-synced repo is a no-op (PRD story 23).
    full_canon = dict(load_canon())
    full_canon["pytest.yml"] = "name: pytest\n"
    repo = OSASUWU_REPOS[0]
    manifest = load_manifest(repo)
    applier = Applier(manifest, full_canon)
    plan = Planner(manifest).plan(ActualState())
    # Build an actual state that is byte-identical to what the plan would write.
    synced_files = {}
    contexts = []
    for action in plan:
        if action.kind == ActionKind.WRITE_FILE:
            synced_files[action.path] = _hash(applier.render_content(action.path))
        elif action.kind == ActionKind.SET_CHECK_CONTEXTS:
            contexts = list(action.context_names)
    actual = ActualState(files=synced_files, required_check_contexts=contexts)
    assert applier.translate(plan, actual) == []
