"""Guard: project-sync.yml retries transient GitHub API errors.

The `project_id` GraphQL lookup has no `|| true` fallback — a 503 from GitHub
causes the whole step to fail under `set -euo pipefail`, emitting a spurious
ci_failure event to the orchestrator event queue.

Fix: a `_retry` helper wraps the lookup in both steps.  This test pins the
structural invariant so the retry cannot be accidentally deleted.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "project-sync.yml"


def _get_step_scripts(step_name: str) -> str:
    """Return the `run:` body of the named step."""
    data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    for job in data.get("jobs", {}).values():
        for step in job.get("steps", []):
            if step.get("name") == step_name:
                return step.get("run", "")
    raise KeyError(f"Step {step_name!r} not found in {WORKFLOW}")


def test_sync_issue_fields_has_retry_helper() -> None:
    script = _get_step_scripts("Sync issue fields")
    assert "_retry()" in script, "Missing _retry helper in 'Sync issue fields' step"


def test_sync_issue_fields_project_id_uses_retry() -> None:
    script = _get_step_scripts("Sync issue fields")
    assert "project_id=$(_retry gh api graphql" in script, (
        "project_id lookup must use _retry to survive transient 503 errors"
    )


def test_set_pr_status_has_retry_helper() -> None:
    script = _get_step_scripts("Set PR status to In Progress")
    assert "_retry()" in script, "Missing _retry helper in 'Set PR status to In Progress' step"


def test_set_pr_status_project_id_uses_retry() -> None:
    script = _get_step_scripts("Set PR status to In Progress")
    assert "project_id=$(_retry gh api graphql" in script, (
        "project_id lookup must use _retry to survive transient 503 errors"
    )


def test_retry_helper_retries_at_least_three_times() -> None:
    script = _get_step_scripts("Sync issue fields")
    # _retry() { local n=0; until [ "$n" -ge N ]; ...
    match = re.search(r'until \[ "\$n" -ge (\d+) \]', script)
    assert match, "Could not parse retry count from _retry helper"
    assert int(match.group(1)) >= 3, "Retry count must be at least 3"
