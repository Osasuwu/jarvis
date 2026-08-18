"""task_outcomes — outcome-recording helpers for the reactive dispatch loop.

Extracted from ``agents/task_dispatch.py`` (#1605, milestone #66 — task_dispatch
decomposition 1/7). Pure extraction, no behavior change: ``task_dispatch.py``
calls into this module directly (shape (b) — no event bus, no plugin registry).

``/task-implement`` runs headless with no MCP tools, so it can never call
``outcome_record`` itself — :func:`record_completion_outcome` writes the
``task_outcomes`` row from the orchestrator side instead, at the terminal
boundary where ``poll_completions`` already knows the task succeeded (exit 0).
:func:`record_skip_outcome` covers the sibling case: a dispatch-dedup skip in
``drain_tasks``. :func:`resolve_pr_url` is the best-effort PR URL lookup that
feeds ``record_completion_outcome``'s payload.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

from agents.github_client import GitHubClient, parse_goal_shape

logger = logging.getLogger(__name__)


def resolve_pr_url(
    task_id: str,
    goal: str,
    *,
    client: GitHubClient | None,
) -> str | None:
    """Best-effort PR URL for a just-completed task (#1085 S2 review finding 2).

    ``pr_evidence.compute_pr_evidence`` and the ``check_pr_evidence_*`` functions
    it calls only ever surface a ``bool | None`` tri-state — the PR object they
    fetch to compute it is discarded, so callers that need the actual URL
    (here: the completion outcome-writer) must resolve it separately. This is a
    SEPARATE, deliberate second fetch of the PR, mirroring
    ``pr_evidence.warn_if_pr_lacks_closing_ref``'s established pattern rather
    than reaching into evidence internals. Returns ``None`` on any resolution
    failure — never
    raises, since the caller treats this as advisory.
    """
    if client is None:
        return None
    shape, pr_number = parse_goal_shape(goal)
    try:
        if shape == "rework" and pr_number is not None:
            pr = client.get_pull_by_number(pr_number)
        elif shape == "fresh":
            branch_match = re.search(r"\(branch=([^)]+)\)", goal)
            branch = branch_match.group(1).strip() if branch_match else f"task/{task_id}"
            pr = client.get_pull_by_head_branch(branch)
        else:
            return None
    except Exception:  # noqa: BLE001 — advisory lookup, never raises to the caller
        logger.exception("[task_outcomes] PR URL resolution failed for task %s", task_id)
        return None
    if not pr:
        return None
    return pr.get("html_url")


def record_skip_outcome(payload: dict[str, Any]) -> None:
    """Best-effort ``task_outcomes`` write for a skipped-duplicate (#931).

    Sandcastle-anon insert, so ``source_provenance`` carries the required
    ``sandcastle:`` prefix (mcp-memory/schema.sql RLS, #542). Any failure is the
    caller's to swallow — this never raises on the happy path but the caller
    still guards it. ``GITHUB_REPO`` builds the issue URL for the ``issue_url``
    link column.
    """
    from agents.supabase_client import get_client

    repo = os.environ.get("GITHUB_REPO", "Osasuwu/jarvis")
    issue_number = payload.get("issue_number")
    get_client().table("task_outcomes").insert(
        {
            "task_type": "autonomous",
            "task_description": f"dispatch-dedup skip: {payload.get('goal')}",
            "outcome_status": "unknown",
            "outcome_summary": (
                f"Skipped duplicate dispatch for #{issue_number}: {payload.get('pointer')}"
            ),
            "project": "jarvis",
            "issue_url": (
                f"https://github.com/{repo}/issues/{issue_number}"
                if issue_number is not None
                else None
            ),
            "pattern_tags": ["dispatch-dedup", "skip", "autonomous"],
            "source_provenance": "sandcastle:task_dispatch-dedup",
        }
    ).execute()


def record_completion_outcome(payload: dict[str, Any]) -> None:
    """Best-effort ``task_outcomes`` write for a completed subagent task (#1085
    S2 review finding 2).

    ``/task-implement`` runs headless with no MCP tools (HARD RULE 3, its
    SKILL.md) — it cannot call ``outcome_record`` itself. Without this write, a
    subagent-dispatched task never gets a ``task_outcomes`` row at all, so
    ``/verify`` Step 1's ``outcome_list(outcome_status="pending")`` never sees
    it and Step 2b's divergence/drive-by audit checks never run. This writes
    the row from the orchestrator side instead, at the terminal boundary where
    ``poll_completions`` already knows the task succeeded (exit 0).
    ``pattern_tags`` MUST include ``"subagent"`` — that's the exact filter
    Step 2b keys on. Sandcastle-anon insert, mirroring
    :func:`record_skip_outcome`'s pattern.
    """
    from agents.supabase_client import get_client

    repo = os.environ.get("GITHUB_REPO", "Osasuwu/jarvis")
    issue_number = payload.get("issue_number")
    get_client().table("task_outcomes").insert(
        {
            "task_type": "autonomous",
            "task_description": f"task-implement: {payload.get('goal')}",
            "outcome_status": "pending",
            "outcome_summary": (
                f"Task {payload.get('task_id')} completed (exit 0); awaiting /verify audit."
            ),
            "project": "jarvis",
            "issue_url": (
                f"https://github.com/{repo}/issues/{issue_number}"
                if issue_number is not None
                else None
            ),
            "pr_url": payload.get("pr_url"),
            "pattern_tags": ["subagent", "headless", "task-implement"],
            "source_provenance": "sandcastle:task_dispatch-completion",
        }
    ).execute()
