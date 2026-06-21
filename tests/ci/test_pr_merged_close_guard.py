"""Meta-test for .github/workflows/pr-merged.yml.

Reimplements the workflow's close/skip decision rule in Python and asserts it
closes/skips the issues it promises, plus a config dimension keeping the YAML
and this test in lockstep.

Why this test exists (#948 Bug A, #1012): native linked-issue auto-close does
NOT fire for automated (bot/App) merges — GitHub recursion-prevention suppresses
it. The App-token merge (auto-merge-enable.yml) un-suppresses the
`pull_request: closed` event, so pr-merged.yml is the deterministic close path.
A silent drift here (back to comment-only, or dropping the reopen guard) would
re-open Bug A with no red signal. pr-merged.yml is NOT path-filtered, so #326's
*config* mandate doesn't strictly apply — but the close/skip rule is exactly the
silent-drift class #326 targets, so the logic+config sibling test is warranted
(same rationale as test_merge_train_guard.py).

Decision rule mirrored here (see the bash loop in the YAML):
  - issue already CLOSED                        -> skip (idempotent)
  - issue reopened AFTER the PR's merged_at     -> skip (respect human reopen)
  - otherwise                                   -> close (state_reason=completed)
The candidate set is `closingIssuesReferences` (authoritative linkage), not a
body regex.
"""

from __future__ import annotations

from pathlib import Path

import pytest


WORKFLOW_PATH = (
    Path(__file__).resolve().parents[2]
    / ".github"
    / "workflows"
    / "pr-merged.yml"
)


def decide(state: str, latest_reopen: str | None, merged_at: str) -> str:
    """Mirror the workflow's per-issue close/skip rule.

    Returns one of: "close", "skip-already-closed", "skip-reopened".
    Timestamps are ISO-8601 Z strings; lexicographic comparison matches the
    bash `[[ "$latest_reopen" > "$MERGED_AT" ]]` test.
    """
    if state == "CLOSED":
        return "skip-already-closed"
    if latest_reopen and latest_reopen > merged_at:
        return "skip-reopened"
    return "close"


MERGED_AT = "2026-06-21T12:00:00Z"


# ---- logic dimension --------------------------------------------------------


def test_open_never_reopened_is_closed():
    assert decide("OPEN", None, MERGED_AT) == "close"
    assert decide("OPEN", "", MERGED_AT) == "close"


def test_already_closed_is_skipped():
    # Idempotent: a re-delivered event or a backstop must not re-close.
    assert decide("CLOSED", None, MERGED_AT) == "skip-already-closed"


def test_reopened_after_merge_is_skipped():
    # Human reopened the issue after the PR merged -> respect it, leave open.
    assert decide("OPEN", "2026-06-21T13:00:00Z", MERGED_AT) == "skip-reopened"


def test_reopened_before_merge_is_closed():
    # A reopen that predates this merge is stale w.r.t. this PR -> still close.
    assert decide("OPEN", "2026-06-20T09:00:00Z", MERGED_AT) == "close"


def test_reopen_exactly_at_merge_is_closed():
    # Strict `>`: a reopen timestamped exactly at merge is not "after".
    assert decide("OPEN", MERGED_AT, MERGED_AT) == "close"


def test_closed_state_wins_over_reopen_signal():
    # If the issue is currently CLOSED, skip regardless of any reopen history.
    assert decide("CLOSED", "2026-06-21T13:00:00Z", MERGED_AT) == "skip-already-closed"


# ---- config dimension (keep YAML and test in lockstep) ----------------------


def test_workflow_exists():
    assert WORKFLOW_PATH.is_file(), "pr-merged.yml missing"


def test_workflow_triggers_on_pr_closed_to_main():
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "pull_request:" in text and "closed" in text, "must trigger on pull_request closed."
    assert "branches: [main]" in text, "must scope to merges into main."
    assert "github.event.pull_request.merged == true" in text, (
        "must act only on MERGED (not merely closed) PRs."
    )


def test_workflow_actually_closes_not_just_comments():
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    # The whole point of #1012: it must CLOSE, not only post a comment. A
    # `gh issue close --reason completed` is the close; comment-only is the
    # regression that left #1005 open with a false "Closed via" note.
    assert "gh issue close" in text, "workflow must close linked issues, not just comment."
    assert "--reason completed" in text, "closes must use state_reason=completed."


def test_workflow_uses_authoritative_linkage_not_regex():
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    # Use closingIssuesReferences (the set native auto-close targets), not a body
    # regex — avoids cross-repo / malformed-ref leakage.
    assert "closingIssuesReferences" in text, (
        "candidate issues must come from closingIssuesReferences (authoritative linkage)."
    )


def test_workflow_has_reopen_guard():
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    # A deliberate human reopen after merge must not be re-closed.
    assert "reopened" in text and "MERGED_AT" in text, (
        "reopen-after-merge guard (compare reopened event time vs merged_at) drifted."
    )


def test_workflow_needs_issues_write():
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "issues: write" in text, "closing issues requires issues: write permission."


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
