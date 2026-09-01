"""task_dedup — pre-spawn dispatch-dedup wiring (#931).

Extracted from ``agents/task_dispatch.py`` (#1610, milestone #66 —
task_dispatch decomposition 6/7). Holds the :class:`DedupConfig` DI shape,
the production :func:`default_task_dedup` builder, and :func:`row_issue_number`
— the column-first/regex-fallback helper both ``drain_tasks``'s dedup check
and its sibling-row scan use to resolve a task_queue row's target issue.

``drain_tasks`` (``agents/task_dispatch.py``) imports these directly (shape
(b) — no event bus, decision ``250479f9-8923-4a68-accb-7468acd969f8``) and
still owns the actual duplicate/stale-branch/readiness decision logic and
its ``TaskQueuePort`` state transitions — that control flow stays put since
it is inseparable from the per-drain counters and early-return contract
:class:`~agents.task_dispatch.DrainResult` depends on. This module holds
only the side-effect-free wiring shape and the one small pure helper.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from agents import pr_evidence, task_outcomes, task_queue

if TYPE_CHECKING:
    from agents.github_client import GitHubClient


def row_issue_number(row: dict[str, Any], goal: str) -> int | None:
    """Issue number for a task_queue row: real column first, regex fallback (#1085 S1-5).

    ``row["issue_number"]`` is populated for every row enqueued after the
    #1085 S1-1/S1-2 migration; legacy/null rows (enqueued before the column
    existed, or via a path that never set it) fall back to ``target_number``
    when ``target_type == "issue"`` (#1119 — the structured-pin path is now
    the primary way ``issue_number`` gets populated, so a row enqueued via
    pins alone must still resolve here), then to
    :func:`pr_evidence.goal_issue_number` parsing ``goal`` — the pre-#1085 behavior.
    """
    value = row.get("issue_number")
    if value is not None:
        return int(value)
    if row.get("target_type") == "issue":
        target_number = row.get("target_number")
        if target_number is not None:
            return int(target_number)
    return pr_evidence.goal_issue_number(goal)


@dataclass(frozen=True)
class DedupConfig:
    """Pre-spawn dispatch-dedup wiring for :func:`~agents.task_dispatch.drain_tasks` (#931).

    ``fetch_in_flight`` returns ``(open_prs, open_branches)`` in the shapes the
    gate's ``check_in_flight`` predicate takes — PR dicts with ``number`` /
    ``body`` / ``headRefName``, branch names as plain strings. It is called
    lazily, at most once per drain (the first fresh-shape task with an issue
    reference triggers it), and a raise means *unverifiable*: the in-flight row
    is requeued to ``pending`` and the drain stops — never a terminal state on
    evidence we could not read.

    ``list_active_rows`` returns live (``claimed``/``running``) task_queue rows
    (``id``/``goal``/``status``/``issue_number``) for the sibling check; queried
    fresh per task so a row spawned earlier in this same drain is seen by later
    tasks. The sibling predicate prefers each row's ``issue_number`` column
    (#1085 S1-5), falling back to parsing ``goal`` for legacy/null rows.

    ``record_outcome`` (optional) is called best-effort with a small payload
    dict on each ``skipped_duplicate`` — a raise is logged and swallowed.

    ``fetch_issue`` (optional, #1085 S2-3) fetches a single issue fresh at
    spawn time — returns ``None`` if the issue is gone/inaccessible, raises on
    a genuine fetch failure. Used for rows whose ``idempotency_key`` starts
    with ``"delegate:"`` (i.e. ``/dispatch``-originated) — the mechanical
    re-run of ``check_issue`` against a fresh fetch, since ``/dispatch``'s own
    check at enqueue time is advisory, not enforcement — and for
    orchestrator-emitted rows pinned to ``target_type == "issue"``, via
    :func:`~scripts.delegate_predispatch_gate.check_orchestrator_target`
    (#1617). ``None`` here (the default) disables both re-checks — a row this
    was never wired for must not start being refused by omission.

    ``fetch_pull`` (optional, #1617) fetches a single PR fresh at spawn time —
    returns ``None`` if the PR is gone/inaccessible, raises on a genuine fetch
    failure. Used only for orchestrator-emitted rows pinned to
    ``target_type == "pr"``, via ``check_orchestrator_target``'s PR-state
    check (open vs. closed/merged). ``None`` here (the default) disables that
    re-check entirely.
    """

    fetch_in_flight: Callable[[], tuple[list[dict[str, Any]], list[str]]]
    list_active_rows: Callable[[], list[dict[str, Any]]]
    record_outcome: Callable[[dict[str, Any]], None] | None = None
    fetch_issue: Callable[[int], dict[str, Any] | None] | None = None
    fetch_pull: Callable[[int], dict[str, Any] | None] | None = None


def default_task_dedup(
    github: GitHubClient,
    *,
    list_active: Callable[[], list[dict[str, Any]]] | None = None,
) -> DedupConfig:
    """Build the production :class:`DedupConfig` from a live GitHub client (#931).

    ``fetch_in_flight`` maps the client's ``list_open_pulls`` / ``list_branch_names``
    into the ``(open_prs, open_branches)`` shape the gate predicate takes;
    ``list_active_rows`` defaults to :func:`task_queue.list_active`; ``record_outcome``
    is the best-effort ``task_outcomes`` writer above; ``fetch_issue`` is
    ``github.get_issue`` directly (#1085 S2-3), used for delegate-originated
    re-checks and orchestrator-emitted ``issue``-pinned rows alike;
    ``fetch_pull`` is ``github.get_pull_by_number`` directly (#1617), used for
    orchestrator-emitted ``pr``-pinned rows. Wired from
    :func:`wake_driver.main`; unit tests inject fakes into :class:`DedupConfig` directly.
    """
    active = list_active if list_active is not None else task_queue.list_active

    def fetch_in_flight() -> tuple[list[dict[str, Any]], list[str]]:
        return github.list_open_pulls(), github.list_branch_names()

    return DedupConfig(
        fetch_in_flight=fetch_in_flight,
        list_active_rows=active,
        record_outcome=task_outcomes.record_skip_outcome,
        fetch_issue=github.get_issue,
        fetch_pull=github.get_pull_by_number,
    )
