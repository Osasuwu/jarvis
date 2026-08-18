"""pr_evidence — PR-existence and closing-ref evidence gathering for the reactive dispatch loop.

Extracted from ``agents/task_dispatch.py`` (#1606, milestone #66 — task_dispatch
decomposition 2/7). Pure extraction, no behavior change: ``task_dispatch.py``
calls into this module directly (shape (b) — no event bus, no plugin registry).
"""

from __future__ import annotations

import logging
import os
import re
import sys
from collections.abc import Callable
from datetime import datetime
from typing import Any

from agents.github_client import (
    GitHubClient,
    check_pr_closing_ref_fresh_shape,
    check_pr_evidence_fresh_shape,
    check_pr_evidence_rework_shape,
    parse_executor_stdout,
    parse_goal_shape,
)

logger = logging.getLogger(__name__)

# First "#N" reference in a goal string — the issue a fresh-shape task targets.
# Right-anchored like the gate's closing-keyword regex so "#93" never reads as
# "#931" (the (?!\d) lookahead).
_GOAL_ISSUE_RE = re.compile(r"#(\d+)(?!\d)")


def goal_issue_number(goal: str) -> int | None:
    """Issue number a goal references, or ``None`` when it references none."""
    m = _GOAL_ISSUE_RE.search(goal)
    return int(m.group(1)) if m else None


def load_gate_module() -> Any:
    """Load ``scripts/delegate_predispatch_gate.py`` for its shared predicate (#931).

    The gate module lives outside the ``agents`` package (it is the /delegate
    CLI reference implementation), so import it by path, anchored to the repo
    root the same way :data:`agents.task_dispatch._EXECUTOR_LOG_DIR` is. Cached
    in ``sys.modules`` under its plain name — the tests import it the same way,
    so the two share one module object.
    """
    mod = sys.modules.get("delegate_predispatch_gate")
    if mod is not None:
        return mod
    import importlib.util

    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "scripts",
        "delegate_predispatch_gate.py",
    )
    spec = importlib.util.spec_from_file_location("delegate_predispatch_gate", path)
    if spec is None or spec.loader is None:  # pragma: no cover — repo layout broken
        raise ImportError(f"cannot load dispatch gate module from {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["delegate_predispatch_gate"] = mod
    spec.loader.exec_module(mod)
    return mod


def compute_pr_evidence(
    task_id: str,
    goal: str,
    spawned_at: datetime | None,
    *,
    client: GitHubClient | None,
    stdout_reader: Callable[[str], str | None] | None = None,
    issue_number: int | None = None,
) -> tuple[bool | None, bool | None]:
    """Compute PR evidence AND closing-ref status for one completed task.

    Returns ``(pr_evidence, closing_ref)`` — the first element is the PR
    existence tri-state (legacy flow), the second is whether the PR body
    carries a closing ref for the task's issue (#1169). For rework-shape
    goals and goals with no issue reference, ``closing_ref`` is ``None``.

    The closing-ref channel is separate from the evidence tri-state per
    grill decision ``ec66db74`` — the two questions have independent
    None/False/True semantics.

    ``issue_number`` (#1085 S1-5), when given, is the task_queue row's real
    ``issue_number`` column value — preferred over parsing it out of ``goal``.
    ``None`` (the default) falls back to the goal-text regex, exactly the
    pre-#1085 behavior — every caller not yet threading the column keeps
    working unchanged.
    """
    if client is None or spawned_at is None:
        return (None, None)
    shape, pr_number = parse_goal_shape(goal)
    if shape == "empty":
        return (None, None)
    if shape == "rework":
        assert pr_number is not None  # noqa: S101
        evidence = check_pr_evidence_rework_shape(
            task_id, goal, pr_number, spawned_at, client=client
        )
        return (evidence, None)

    evidence = check_pr_evidence_fresh_shape(task_id, goal, spawned_at, client=client)
    # #1136 AC5: advisory-only — surface a fresh-shape PR that links but does not
    # *close* its named issue. Runs at this evidence boundary regardless of the
    # freshness verdict; never blocks and never edits the PR.
    warn_if_pr_lacks_closing_ref(task_id, goal, client=client, issue_number=issue_number)
    closing_ref = compute_closing_ref_fresh_shape(
        task_id, goal, client=client, issue_number=issue_number
    )
    if evidence is False and stdout_reader is not None:
        # AC3 — the head-branch lookup found nothing; fall back to whatever PR
        # the agent claimed in its stdout, then verify it actually exists.
        try:
            text = stdout_reader(task_id)
        except Exception:  # noqa: BLE001 — secondary channel is best-effort
            text = None
        claimed = parse_executor_stdout(text) if text else None
        if claimed and claimed.get("number"):
            try:
                pr = client.get_pull_by_number(int(claimed["number"]))
            except Exception:  # noqa: BLE001 — a claimed-PR lookup error is non-fatal
                pr = None
            if pr:
                return (True, closing_ref)
    return (evidence, closing_ref)


def compute_closing_ref_fresh_shape(
    task_id: str,
    goal: str,
    *,
    client: GitHubClient | None = None,
    issue_number: int | None = None,
) -> bool | None:
    """Compute closing-ref status for a fresh-shape task (#1169).

    Calls ``check_pr_closing_ref_fresh_shape`` through the gate module.
    Returns ``True`` if the PR carries a closing ref, ``False`` if it
    doesn't, ``None`` if it can't be computed.

    ``issue_number``, when given, is preferred over parsing ``goal`` (#1085
    S1-5) — see :func:`compute_pr_evidence`.
    """
    if issue_number is None:
        issue_number = goal_issue_number(goal)
    if issue_number is None:
        return None
    if client is None:
        return None
    try:
        gate = load_gate_module()
    except Exception:  # noqa: BLE001
        return None
    return check_pr_closing_ref_fresh_shape(
        task_id,
        goal,
        issue_number,
        client=client,
        closing_ref_matcher=gate._closing_ref_re,
    )


def warn_if_pr_lacks_closing_ref(
    task_id: str,
    goal: str,
    *,
    client: GitHubClient,
    issue_number: int | None = None,
) -> None:
    """Log an advisory WARNING if a fresh-shape task's PR does not close its issue (#1136 AC5).

    Advisory-only: this neither blocks the pipeline nor edits the PR. It is a
    SEPARATE, deliberate second fetch of the PR (via
    :func:`check_pr_closing_ref_fresh_shape`) — the freshness evidence and the
    closing-ref question are orthogonal (grill decision ``ec66db74``), so they
    are not folded into one call. The closing-ref matcher is the /delegate gate's
    ``_closing_ref_re`` (recognizing ``closes/fixes/resolves`` only, NOT
    ``Refs``), reused by injection so this module keeps its single path-load in
    :func:`load_gate_module` rather than importing gate internals directly.

    Fires only when the goal names an issue AND a PR exists on the branch whose
    body carries no closing ref for that issue (``check_...`` returns ``False``).
    A missing issue reference, an absent PR (``None``), or a genuine ``Closes #N``
    (``True``) are all silent. The AC7 follow-up (#1169) turns this signal into a
    disposition; here it is observation only.

    ``issue_number``, when given, is preferred over parsing ``goal`` (#1085
    S1-5) — see :func:`compute_pr_evidence`.
    """
    if issue_number is None:
        issue_number = goal_issue_number(goal)
    if issue_number is None:
        return
    try:
        gate = load_gate_module()
    except Exception:  # noqa: BLE001 — advisory must never break the evidence path
        logger.debug("closing-ref advisory: gate module unavailable; skipping")
        return
    closes = check_pr_closing_ref_fresh_shape(
        task_id,
        goal,
        issue_number,
        client=client,
        closing_ref_matcher=gate._closing_ref_re,
    )
    if closes is False:
        logger.warning(
            "pr_closing_ref_missing: task=%s issue=#%s — the PR links but carries "
            "no `Closes #%s` keyword; this merge will NOT auto-close the issue "
            "(native auto-close is suppressed for bot/App merges). Use `Closes #%s` "
            "for a full close; `Refs #%s` is correct only for partial work. "
            "Advisory only — see #1169 for enforcement.",
            task_id,
            issue_number,
            issue_number,
            issue_number,
            issue_number,
        )


def ensure_pr_closing_ref(
    task_id: str,
    goal: str,
    *,
    client: GitHubClient | None = None,
    issue_number: int | None = None,
) -> bool | None:
    """Ensure a fresh-shape task's PR body carries a closing ref (#1169 item 1).

    Structural enforcement: if the PR exists on the task's branch but its body
    lacks a ``Closes/Fixes/Resolves #<N>`` for the referenced issue, the
    supervisor auto-edits the PR body to add it. This makes the requirement
    structural (not advisory) — even if the spawned agent fails to include the
    closing keyword, the merge gate still fires.

    Returns the same tri-state as :func:`check_pr_closing_ref_fresh_shape`:
    - ``True`` — PR has (or now has) a closing ref
    - ``False`` — no PR to fix, or goal has no issue reference
    - ``None`` — unparseable or client unavailable

    ``issue_number``, when given, is preferred over parsing ``goal`` (#1085
    S1-5) — see :func:`compute_pr_evidence`.
    """
    shape, _ = parse_goal_shape(goal)
    if shape != "fresh":
        return False
    if issue_number is None:
        issue_number = goal_issue_number(goal)
    if issue_number is None:
        return False
    if client is None:
        return None

    try:
        gate = load_gate_module()
    except Exception:  # noqa: BLE001 — enforcement must not crash the poll
        logger.debug("ensure-closing-ref: gate module unavailable; skipping")
        return None

    current = check_pr_closing_ref_fresh_shape(
        task_id,
        goal,
        issue_number,
        client=client,
        closing_ref_matcher=gate._closing_ref_re,
    )
    if current is True:
        return True

    if current is False:
        branch_match = re.search(r"\(branch=([^)]+)\)", goal)
        branch = branch_match.group(1).strip() if branch_match else f"task/{task_id}"
        pr = client.get_pull_by_head_branch(branch)
        if pr is None:
            return None
        pr_number = pr.get("number")
        existing_body = pr.get("body") or ""
        closing_line = f"\nCloses #{issue_number}\n"
        if not existing_body.endswith("\n"):
            closing_line = "\n" + closing_line
        new_body = existing_body + closing_line
        try:
            result = client.update_pull(pr_number, body=new_body)
            if result is not None:
                logger.info(
                    "[pr_evidence] auto-fixed missing closing ref: "
                    "PR #%s for issue #%s (task %s)",
                    pr_number,
                    issue_number,
                    task_id,
                )
                return True
        except Exception:  # noqa: BLE001 — enforcement failure must not crash the poll
            logger.exception(
                "[pr_evidence] auto-fix of PR #%s closing ref failed for task %s",
                pr_number,
                task_id,
            )
        return None

    return None
