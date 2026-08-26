"""Ex-post plan-review drain gate (#1689).

Wires the ordinal 1/2/3 plan-review classification (#1685,
:mod:`agents.plan_classifier`; ordinal vocabulary + ``afk:2-plan``/
``afk:3-human`` labels per #1707) into
:func:`agents.task_dispatch.drain_tasks`: a class-2 row claimed off the
queue must carry a verified locked ``## Plan`` before it is spawned. Unlike
:mod:`agents.implement_plan_gate` (#1688, the *ex-ante* interactive-lane
gate), this gate has **no ``priority:critical`` carve-out** — a task
entering via the queue always gets ex-post review regardless of label,
because there is no operator present to judge the carve-out case in the
moment (:mod:`agents.task_dispatch` module docstring — admission here is
event/queue-routed, not human-judged).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from agents.github_client import GitHubClient
from agents.plan_classifier import classify_task_row
from agents.plan_lock import HEADING_RE, MalformedPlanError, parse_plan, verify_lock
from agents.plan_review_config import PlanReviewConfig, load_plan_review_config
from agents.plan_section import replace_plan_section

# Repo root — this module lives at ``<repo_root>/agents/plan_review_drain.py``,
# mirrored from ``agents.executor._REPO_ROOT`` so the planner subprocess's cwd
# resolves the same way a spawned worker's does.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Tool surface for the planner subprocess: read-only exploration, Agent (to
# spawn the critic-goal-fit/critic-state-fit/critic-tiebreak panel per
# agents/plan_lock.py's design), and the two memory calls the planner agent
# type is scoped to (mirrors the "planner" subagent's own tool list).
_PLANNER_ALLOWED_TOOLS = (
    "Read",
    "Grep",
    "Glob",
    "Agent",
    "mcp__memory__memory_recall",
    "mcp__memory__record_decision",
)


@dataclass(frozen=True)
class PlanResult:
    """Outcome of one planner run for a class-2 row.

    ``resolved`` is False when the critic panel raised a blocking objection
    that survived one revision cycle without consensus — the caller must
    park the row rather than spawn against an unresolved plan.
    """

    plan_text: str
    resolved: bool
    reason: str | None = None


@runtime_checkable
class PlannerPort(Protocol):
    """Injection seam for the planner subagent (mirrors ``TaskQueuePort``'s
    structural-typing pattern in :mod:`agents.task_dispatch`)."""

    def run_planner(
        self,
        row: dict[str, Any],
        config: PlanReviewConfig,
        prior_failure: str | None = None,
    ) -> PlanResult: ...


def class_gate(config: PlanReviewConfig, row: dict[str, Any]) -> int:
    """Classify ``row`` unconditionally — no ``priority:critical`` carve-out.

    Contrast with :func:`agents.implement_plan_gate.evaluate_trigger`, whose
    carve-out skips the plan *requirement* (never the reported
    classification) for the interactive lane. The ex-post drain gate skips
    nothing: classification always runs, and downstream callers must not
    special-case any label here.
    """
    return classify_task_row(config, row)


def needs_plan(config: PlanReviewConfig, row: dict[str, Any], github: GitHubClient) -> bool:
    """True when ``row`` is ordinal class 2 and lacks a verified locked plan.

    ``task_queue`` carries no cached issue-body column, so a verified plan
    can only be confirmed by a fresh ``github.get_issue`` fetch — this
    deliberately re-fetches on every call rather than trusting a stale
    ``plan_digest`` alone, since the digest only proves *a* plan was once
    locked, not that the issue's current Plan section still matches it.
    """
    if class_gate(config, row) != 2:
        return False

    if not row.get("plan_digest"):
        return True

    issue_number = row.get("issue_number")
    if issue_number is None:
        return True

    issue = github.get_issue(int(issue_number))
    body = (issue or {}).get("body") or ""
    try:
        return not verify_lock(body)
    except MalformedPlanError:
        return True


def pre_spawn_digest_mismatch(github: GitHubClient, row: dict[str, Any]) -> bool:
    """True iff ``row``'s locked plan no longer matches the issue's current body.

    AC6 fail-closed pre-spawn recheck: the issue body may have drifted
    (edited post-approval) since ``row["plan_digest"]`` was recorded, whether
    just now (in the same drain, after ``write_plan_section``) or in a prior
    drain. Unlike :func:`needs_plan`, which tolerates ``MalformedPlanError``
    as "a plan is still needed", this function guards a *spawn* rather than
    a plan-write decision — any malformed/unlocked body is a mismatch here,
    with no softer outcome to fall back to.
    """
    issue_number = int(row["issue_number"])
    fresh_issue = github.get_issue(issue_number)
    fresh_body = (fresh_issue or {}).get("body") or ""
    try:
        return not verify_lock(fresh_body) or parse_plan(fresh_body).lock != row.get("plan_digest")
    except MalformedPlanError:
        return True


def default_resolve_binary() -> str:
    """Lazy re-export of :func:`agents.task_dispatch.default_resolve_binary`.

    Lazy import mirrors the rest of the codebase's pattern for this adapter
    (:func:`agents.task_dispatch.default_spawn`) — keeps this module importable
    without pulling in the full dispatch stack, and gives tests a single
    monkeypatch target (``agents.plan_review_drain.default_resolve_binary``).
    """
    from agents.task_dispatch import default_resolve_binary as _impl

    return _impl()


def default_plan_config_loader() -> PlanReviewConfig:
    """Lazy default for ``drain_tasks``'s ``plan_config_loader`` param (#1689).

    Wraps :func:`agents.plan_review_config.load_plan_review_config` against
    the repo-standard config path — a zero-arg factory (not a module-level
    constant) so tests can inject a fixture config without touching disk,
    mirroring :func:`default_resolve_binary`'s injection-seam pattern.
    """
    return load_plan_review_config(Path(_REPO_ROOT) / "config" / "plan_review.yaml")


def default_run_planner(
    row: dict[str, Any],
    config: PlanReviewConfig,
    prior_failure: str | None = None,
) -> PlanResult:
    """Blocking ``claude -p`` invocation of the planner subagent (#1689).

    Unlike :func:`agents.executor.spawn` (fire-and-forget worker), this call
    is synchronous: :func:`agents.task_dispatch.drain_tasks` needs the
    resulting plan text before it can write it to the issue and decide
    whether to spawn. The prompt instructs the session to act as the
    ``planner`` subagent type (Read/Grep/Glob exploration, spawn the critic
    panel via ``Agent``, then emit a single JSON object
    ``{"plan_text": ..., "resolved": ..., "reason": ...}`` as its final text).

    ``prior_failure`` (#1690): when set, this is a replan re-run — the
    executor found the first plan's assumption broken mid-implementation and
    posted a replan-request comment. The text (broken assumption + evidence)
    is folded into the prompt so the second plan is informed by the first
    one's failure instead of repeating it blind.

    # ceiling: assumes the CLI's ``--output-format json`` wraps the session's
    # final text output in a top-level ``{"result": "<text>"}`` envelope, and
    # that MCP tools (``mcp__memory__*``) are discoverable in a headless
    # ``-p`` invocation the same way they are in an interactive session — the
    # first live drain run against a real ordinal-2 issue is what verifies
    # this; if it's wrong, widen this docstring into a real integration test
    # against a throwaway issue instead of guessing further.
    """
    prior_failure_block = (
        f"\n\nA prior plan for this issue was attempted and failed mid-implementation. "
        f"The executor reported this broken assumption — take it into account so the "
        f"new plan does not repeat it:\n\n{prior_failure}\n"
        if prior_failure
        else ""
    )
    prompt = (
        "Act as the 'planner' subagent (agents/plan_lock.py convention): "
        f"write a checkable ## Plan for issue #{row.get('issue_number')} "
        f"({row.get('issue_title', '')}). Issue body:\n\n"
        f"{row.get('issue_body', '')}\n"
        f"{prior_failure_block}\n"
        "Spawn the critic-goal-fit and critic-state-fit panel via the Agent "
        "tool, resolve any disagreement via critic-tiebreak, then respond "
        "with ONLY a single JSON object of the shape "
        '{"plan_text": "<## Plan section text, with a lock: line>", '
        '"resolved": true|false, "reason": "<string or null>"} '
        "and nothing else."
    )

    argv = [
        default_resolve_binary(),
        "-p",
        prompt,
        "--permission-mode",
        "acceptEdits",
        "--allowedTools",
        *_PLANNER_ALLOWED_TOOLS,
        "--model",
        config.models.planner,
        "--output-format",
        "json",
    ]

    completed = subprocess.run(
        argv,
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    envelope = json.loads(completed.stdout)
    payload = json.loads(envelope["result"])
    return PlanResult(
        plan_text=payload["plan_text"],
        resolved=bool(payload["resolved"]),
        reason=payload.get("reason"),
    )


# Replan-request marker (#1690): an executor that discovers a broken plan
# assumption mid-implementation posts a comment starting with this literal
# line, followed by a fenced ```json block with `{"broken_assumption": str,
# "evidence": str}`. This is the one shape ``find_replan_request`` looks for
# — a free-prose "this isn't working" comment does not trigger a replan.
REPLAN_REQUEST_MARKER = "<!-- jarvis:replan-request -->"

_REPLAN_JSON_RE = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)


@dataclass(frozen=True)
class ReplanRequest:
    """A parsed replan-request comment (#1690)."""

    broken_assumption: str
    evidence: str
    created_at: str | None = None


def find_replan_request(
    github: GitHubClient,
    issue_number: int,
    *,
    since: str | None = None,
) -> ReplanRequest | None:
    """Return the most recent replan-request comment on ``issue_number``, if any.

    Scans comments oldest-to-newest and keeps the last one whose body starts
    with :data:`REPLAN_REQUEST_MARKER` and carries a parseable
    ``{"broken_assumption": ..., "evidence": ...}`` JSON block — a later valid
    comment supersedes an earlier one rather than erroring on multiples.
    ``since`` (an ISO-8601 timestamp, typically the tracked process's
    ``spawned_at``) filters out comments posted before the current run
    started, so a stale replan-request from a prior attempt is not
    reprocessed after the row already advanced past it (a comment's
    ``created_at`` is compared as a plain string — GitHub's ISO-8601 output
    sorts lexically the same as chronologically, so no datetime parse is
    needed here). Malformed marker comments (missing/invalid JSON block) are
    skipped rather than raising — a malformed comment is not a valid replan
    request, not a fatal error.
    """
    comments = github.list_issue_comments(issue_number)
    match: ReplanRequest | None = None
    for comment in comments:
        body = comment.get("body") or ""
        if not body.startswith(REPLAN_REQUEST_MARKER):
            continue
        created_at = comment.get("created_at")
        if since is not None and created_at is not None and created_at <= since:
            continue
        json_match = _REPLAN_JSON_RE.search(body)
        if not json_match:
            continue
        try:
            payload = json.loads(json_match.group(1))
        except json.JSONDecodeError:
            continue
        broken_assumption = payload.get("broken_assumption")
        evidence = payload.get("evidence")
        if not isinstance(broken_assumption, str) or not isinstance(evidence, str):
            continue
        match = ReplanRequest(
            broken_assumption=broken_assumption,
            evidence=evidence,
            created_at=created_at,
        )
    return match


def write_plan_section(github: GitHubClient, issue_number: int, plan_text: str) -> str:
    """Write ``plan_text`` into ``issue_number``'s ``## Plan`` section.

    Fresh-fetches the issue body first (never trusts a caller-supplied
    stale copy). If a ``## Plan`` section already exists, the full prior
    body is posted as a comment before it is overwritten — a superseded
    plan is never silently lost, it's demoted to a comment. Returns the
    new full issue body.
    """
    issue = github.get_issue(int(issue_number))
    body = (issue or {}).get("body") or ""

    if HEADING_RE.search(body):
        github.create_issue_comment(issue_number, body=body)

    new_body = replace_plan_section(body, plan_text)
    updated = github.update_issue(issue_number, body=new_body)
    return (updated or {}).get("body") or new_body
