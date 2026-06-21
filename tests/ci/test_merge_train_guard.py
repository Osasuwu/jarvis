"""Meta-test for .github/workflows/merge-train.yml.

Reimplements the merge-train's PR-selection rule in Python and asserts it
picks/excludes the PRs the workflow promises, plus a config dimension that
keeps the YAML and this test in lockstep.

Why this test exists (CLAUDE.md §326): merge-train.yml is NOT path-filtered,
so #326's *config* mandate doesn't strictly apply. But the selection rule is
exactly the silent-drift class #326 targets — a wrong filter would quietly
update the wrong PRs (or none) with no red signal. The *logic* dimension is
worth a sibling test even though the path-filter dimension is N/A.

Selection rule mirrored here (see the `--jq` filter + bash loop in the YAML):
  candidate  = open AND not draft AND auto-merge enabled AND no
               `status:owner-queue` label, sorted oldest-first (createdAt asc)
  conflict   = candidate whose mergeable==CONFLICTING or mergeStateStatus==DIRTY
               -> labelled needs-rebase, skipped (never updated)
  update     = candidate whose mergeStateStatus==BEHIND -> update-branch,
               capped at CAP (default 10), oldest-first
  other      = candidate in any other state -> left alone
"""

from __future__ import annotations

from pathlib import Path

import pytest


WORKFLOW_PATH = (
    Path(__file__).resolve().parents[2]
    / ".github"
    / "workflows"
    / "merge-train.yml"
)

CAP = 10


def _is_candidate(pr: dict) -> bool:
    """Open + non-draft + auto-merge-enabled + not owner-parked."""
    if pr.get("isDraft"):
        return False
    if not pr.get("autoMerge"):
        return False
    if "status:owner-queue" in pr.get("labels", []):
        return False
    return True


def select(prs: list[dict], cap: int = CAP) -> tuple[list[int], list[int]]:
    """Mirror the workflow's selection rule.

    Returns (to_update, to_flag_conflict) as lists of PR numbers, oldest-first.
    """
    candidates = sorted(
        (p for p in prs if _is_candidate(p)),
        key=lambda p: p["createdAt"],
    )

    to_update: list[int] = []
    to_flag_conflict: list[int] = []

    for pr in candidates:
        ms = pr.get("mergeStateStatus")
        mg = pr.get("mergeable")
        if mg == "CONFLICTING" or ms == "DIRTY":
            to_flag_conflict.append(pr["number"])
            continue
        if ms == "BEHIND" and len(to_update) < cap:
            to_update.append(pr["number"])
        # any other state (CLEAN / BLOCKED / UNSTABLE / UNKNOWN) -> left alone

    return to_update, to_flag_conflict


def _pr(number, *, created, draft=False, auto=True, ms="BEHIND", mg="MERGEABLE", labels=None):
    return {
        "number": number,
        "createdAt": created,
        "isDraft": draft,
        "autoMerge": auto,
        "mergeStateStatus": ms,
        "mergeable": mg,
        "labels": labels or [],
    }


# ---- logic dimension --------------------------------------------------------


def test_picks_behind_auto_prs_oldest_first():
    prs = [
        _pr(3, created="2026-06-03"),
        _pr(1, created="2026-06-01"),
        _pr(2, created="2026-06-02"),
    ]
    to_update, conflicts = select(prs)
    assert to_update == [1, 2, 3], "must update oldest-first"
    assert conflicts == []


def test_draft_excluded():
    prs = [_pr(1, created="2026-06-01", draft=True)]
    assert select(prs) == ([], [])


def test_non_auto_merge_excluded():
    prs = [_pr(1, created="2026-06-01", auto=False)]
    assert select(prs) == ([], [])


def test_owner_queue_label_excluded():
    prs = [_pr(1, created="2026-06-01", labels=["status:owner-queue"])]
    assert select(prs) == ([], [])


def test_owner_queue_excluded_even_with_other_labels():
    prs = [_pr(1, created="2026-06-01", labels=["bug", "status:owner-queue"])]
    assert select(prs) == ([], [])


def test_conflicting_goes_to_flag_not_update():
    prs = [_pr(1, created="2026-06-01", mg="CONFLICTING")]
    to_update, conflicts = select(prs)
    assert to_update == []
    assert conflicts == [1]


def test_dirty_state_treated_as_conflict():
    prs = [_pr(1, created="2026-06-01", ms="DIRTY", mg="UNKNOWN")]
    to_update, conflicts = select(prs)
    assert to_update == []
    assert conflicts == [1]


def test_non_behind_states_left_alone():
    for state in ("CLEAN", "BLOCKED", "UNSTABLE", "UNKNOWN", "HAS_HOOKS"):
        prs = [_pr(1, created="2026-06-01", ms=state)]
        to_update, conflicts = select(prs)
        assert to_update == [], f"{state} must not be force-updated"
        assert conflicts == []


def test_empty_set_no_pick():
    assert select([]) == ([], [])


def test_cap_enforced():
    prs = [_pr(n, created=f"2026-06-{n:02d}") for n in range(1, 16)]  # 15 BEHIND
    to_update, _ = select(prs, cap=10)
    assert len(to_update) == 10
    assert to_update == list(range(1, 11)), "cap keeps the 10 oldest"


def test_conflicts_do_not_consume_cap():
    # 10 conflicting (flagged, not updated) + 2 behind -> both behind get updated.
    prs = [_pr(n, created=f"2026-06-{n:02d}", mg="CONFLICTING") for n in range(1, 11)]
    prs += [_pr(11, created="2026-06-11"), _pr(12, created="2026-06-12")]
    to_update, conflicts = select(prs, cap=10)
    assert to_update == [11, 12]
    assert len(conflicts) == 10


def test_mixed_realistic_set():
    prs = [
        _pr(1, created="2026-06-01", ms="BEHIND"),                       # update
        _pr(2, created="2026-06-02", draft=True),                        # excluded (draft)
        _pr(3, created="2026-06-03", auto=False),                        # excluded (no auto)
        _pr(4, created="2026-06-04", mg="CONFLICTING"),                  # conflict
        _pr(5, created="2026-06-05", labels=["status:owner-queue"]),     # excluded (parked)
        _pr(6, created="2026-06-06", ms="CLEAN"),                        # left alone
        _pr(7, created="2026-06-07", ms="BEHIND"),                       # update
    ]
    to_update, conflicts = select(prs)
    assert to_update == [1, 7]
    assert conflicts == [4]


# ---- config dimension (keep YAML and test in lockstep) ----------------------


def test_workflow_exists():
    assert WORKFLOW_PATH.is_file(), "merge-train.yml missing"


def test_workflow_uses_app_token_not_github_token():
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "create-github-app-token" in text, (
        "merge-train must mint a GitHub App token — GITHUB_TOKEN-pushed "
        "updates do not re-trigger required checks (recursion prevention)."
    )
    # Minting isn't enough: the update-branch step must USE the App token. If
    # GH_TOKEN reverts to GITHUB_TOKEN while the mint step stays, update-branch
    # stops re-triggering checks and auto-merge stalls again (the original bug).
    assert "steps.app-token.outputs.token" in text, (
        "GH_TOKEN must use the minted App token output (steps.app-token.outputs.token)."
    )
    assert "secrets.GITHUB_TOKEN" not in text, (
        "merge-train must never pass secrets.GITHUB_TOKEN to gh — recursion "
        "prevention would stop update-branch from re-triggering required checks."
    )


def test_workflow_filters_match_selection_rule():
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    for token in ("isDraft", "autoMergeRequest", "status:owner-queue", "BEHIND", "update-branch"):
        assert token in text, f"merge-train.yml no longer references {token!r}; selection rule drifted from this test."


def test_workflow_has_concurrency_guard():
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "concurrency:" in text and "cancel-in-progress: false" in text, (
        "merge-train must serialize per-repo without cancelling in-flight self-heal runs."
    )


def test_workflow_flags_conflicts_with_needs_rebase():
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "needs-rebase" in text, "conflict handling (needs-rebase label) drifted."


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
