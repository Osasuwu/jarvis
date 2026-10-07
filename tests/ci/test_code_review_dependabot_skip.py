"""Untrusted PRs (forks, Dependabot) are never silently skipped (#1964, #944).

History: code-review.yml used to carry a job-level `if:` that skipped fork and
Dependabot PRs. A skipped job counts as a passing required check, so those PRs
merged unreviewed (#1964). Before that, the guard keyed off `github.actor`, which
is the *pusher* on `synchronize` — when merge-train.yml updated a stale
Dependabot branch with an App token the guard stopped matching and the review
ran on a trivial dep bump (#944).

Now: the review workflow has NO fork/Dependabot predicate at all. Whether a PR
is untrusted is decided in one place, `is_untrusted_author` /
`review_skip_reason` in .github/scripts/code_gate_verdict.py, and the verdict is
red with remediation, never green. The review itself runs for such a PR only
through a maintainer `workflow_dispatch` (environment `untrusted-review`).
"""

from __future__ import annotations

from pathlib import Path

import yaml

WORKFLOWS = Path(__file__).resolve().parents[2] / ".github" / "workflows"
REVIEW = WORKFLOWS / "code-review.yml"
VERDICT = WORKFLOWS / "code-gate-verdict.yml"


def _spec(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _job_ifs(path: Path) -> list[str]:
    return [str(job["if"]) for job in _spec(path)["jobs"].values() if "if" in job]


def test_no_job_level_fork_or_dependabot_skip():
    conditions = _job_ifs(REVIEW) + _job_ifs(VERDICT)
    assert conditions, "expected the `edited` guard as a job-level if"
    for condition in conditions:
        assert "user.login" not in condition and "dependabot" not in condition, condition
        assert "head.repo" not in condition, condition
        assert "github.actor" not in condition, (
            "github.actor is the pusher on synchronize — keying a Dependabot decision "
            f"off it reintroduces #944: {condition}"
        )


def test_review_job_if_is_only_the_edited_guard():
    (condition,) = _job_ifs(REVIEW)
    assert condition == (
        "github.event_name != 'pull_request' || github.event.action != 'edited' "
        "|| github.event.changes.base"
    )


def test_untrusted_review_runs_only_via_the_untrusted_environment():
    environment = _spec(REVIEW)["jobs"]["review"]["environment"]
    assert (
        environment == "${{ github.event_name == 'workflow_dispatch' && 'untrusted-review' || '' }}"
    )


def test_allowed_bots_is_narrowed_to_dependabot_on_every_reviewer_step():
    reviewer_steps = [
        step
        for step in _spec(REVIEW)["jobs"]["review"]["steps"]
        if str(step.get("uses", "")).startswith("anthropics/claude-code-action@")
    ]
    assert len(reviewer_steps) == 2  # attempt 1 and the retry
    for step in reviewer_steps:
        assert step["with"]["allowed_bots"] == "dependabot[bot]"
