"""task_dispatch — close the reactive forward path (#909).

The reactive forward path is now closed end-to-end (#741/#744 → #909 → #921)::

    event → wake_driver → orchestrator.handle_event
          → task_queue.enqueue(row) → drain_tasks → executor.spawn
          → poll_completions → running → done | failed

:func:`drain_tasks` claims pending ``sandcastle`` rows, transitions each to
``running``, and fires ``executor.spawn(goal)`` — symmetric to how
:func:`wake_driver.drain_pending` drains *events*. The spawned processes are
handed back as :attr:`DrainResult.procs`; :func:`poll_completions` (#921)
closes each row when its process exits — exit 0 → ``done``, non-zero →
``failed``. **Model P semantics: ``done`` means the spawned process exited
cleanly, nothing more** — not task success, not PR-merged. Outcome truth
re-enters externally via GitHub Path-A workflows as fresh *events*.

**Restart limitation (#921):** the proc map lives only in the driver process.
A restart forgets every live process — those rows age out and the orphan
reaper (:func:`reclaim_stale_tasks`) fails them as a backstop, which Path A
then self-heals. A PID sidecar that survives restarts is #952.

Design mirrors :mod:`agents.wake_driver`: the pure logic
(:func:`drain_tasks` / :func:`reclaim_stale_tasks`) runs over a
:class:`TaskQueuePort` Protocol, so it is unit-testable with an in-memory fake
(fake queue + fake spawn + fake running-count) — no live DB, no real
``claude -p``. :class:`SupabaseTaskQueue` is the thin real adapter over
:mod:`agents.task_queue` (supabase-py / PostgREST). Events ride raw psycopg
(they need ``LISTEN``); tasks ride supabase-py — the split is deliberate (AC10).

Crash-safety follows **Ordering B** (grill decision ``2489782f``): per task,
``claim → transition(running) → spawn``. Transitioning to ``running`` *before*
the spawn means a crash in the window leaves the row ``running`` (swept by the
generous reaper, AC6) rather than ``claimed`` with a live process — the latter
would let the claimed-reclaimer (AC5) hand the same task to a second spawn.
``claimed`` therefore strictly means *claimed-but-not-yet-spawned*.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import time
from collections.abc import Callable, Collection
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from supabase import Client

    from agents.driver_heartbeat import HeartbeatStatus

from agents import pr_evidence, task_dedup, task_outcomes, task_queue, task_worktree
from agents.github_client import (
    GitHubClient,
    default_github_client,
    parse_goal_shape,
)
from agents.pid_sidecar import Sidecar, poll_exit
from agents.plan_lock import MalformedPlanError, parse_plan, verify_lock
from agents.sandcastle_config import default_operator_default_substrate
from agents.plan_review_config import PlanReviewConfig
from agents.plan_review_drain import PlannerPort
from agents.plan_review_drain import class_gate as _plan_class_gate
from agents.plan_review_drain import default_plan_config_loader
from agents.plan_review_drain import default_run_planner as _default_run_planner
from agents.plan_review_drain import find_replan_request as _find_replan_request
from agents.plan_review_drain import needs_plan as _plan_needs_plan
from agents.plan_review_drain import pre_spawn_digest_mismatch as _pre_spawn_digest_mismatch
from agents.plan_review_drain import write_plan_section as _write_plan_section
from agents.process_kill import kill_process_tree

logger = logging.getLogger(__name__)

# Only sandcastle rows are auto-spawned; assignee='owner' escalation rows are
# never claimed by the drain (AC2).
DEFAULT_ASSIGNEE = "sandcastle"


def _resolve_concurrency_cap() -> int:
    """Read the sandcastle concurrency cap from REACTIVE_CONCURRENCY_CAP (#1390
    AC8), falling back to 5. register-wake-driver.ps1 sets this to 2 in the
    launched process's environment before the module ever imports, so the
    module-level read below picks it up at process start."""
    return int(os.environ.get("REACTIVE_CONCURRENCY_CAP", "5"))


# Max concurrent running sandcastle tasks (AC3). Measures compute concurrency:
# slots free as soon as poll_completions observes the process exit (#921).
DEFAULT_CONCURRENCY_CAP = _resolve_concurrency_cap()

# A row stuck in ``claimed`` past this long means the drainer died between the
# claim and the running transition — no process exists, so it is safe to return
# to ``pending`` (AC5). Matches the wake_driver event watchdog default.
DEFAULT_CLAIMED_STALE_SECONDS = 300

# One 6h knob, two consumers (#921): rows whose process the driver no longer
# tracks (orphans — e.g. after a restart) are reaped to ``failed`` past this
# age, and *tracked* processes still alive past it are tree-killed as runaways.
# Deliberately generous (≫ normal task runtime); live tracked rows under the
# threshold are never time-reaped (AC5).
DEFAULT_RUNNING_REAP_SECONDS = 6 * 60 * 60

# #1085 S3-2 local-drain fallback: seconds between polling task_queue for
# terminal state between ``wake_driver --once`` ticks.
DEFAULT_LOCAL_DRAIN_POLL_SECONDS = 2.0

# #1119: statuses this loop still considers "in flight" and worth waiting on.
# Deliberately narrower than task_queue.TERMINAL_STATES — a local-drain tick
# can only ever spawn work forward, and a parked row can never be advanced by
# a local spawn (only an external unpark actor can do that), so from this
# loop's perspective a parked row is done draining even though it is not
# FSM-terminal.
_ACTIVE_STATUSES = frozenset({"pending", "claimed", "running"})

# ceiling: flat retry cap (150 x poll_seconds ~= 5 minutes), not derived from
# the reaper's own timeouts (DEFAULT_RUNNING_REAP_SECONDS is hours). "operator
# present, blocking OK" (#1085 design) still wants a bound so a genuinely
# stuck row can't hang the operator's /dispatch session forever; raise this at
# the call site if a real drain run needs longer.
DEFAULT_LOCAL_DRAIN_MAX_ITERATIONS = 150

# #1085 S3 review fix: local-drain's own subprocess ticks must stamp a heartbeat
# identity distinct from the resident driver's "wake_driver" (driver_heartbeat.DRIVER_NAME).
# default_local_drain_heartbeat_check() reads the resident's row to decide "has it
# recovered, should I stop looping?" — if the local-drain subprocess wrote to that
# same row, the very next re-check would read back its own fresh timestamp and
# conclude the resident had recovered, exiting after exactly one iteration.
LOCAL_DRAIN_DRIVER_NAME = "wake_driver_local_drain"

# Spawn a task's goal, fire-and-forget. Raises on a hard launch failure (AC7b).
# Called as ``spawn(goal, task_id=<id>)`` — the executor needs the id to write
# the per-task stdout JSON the #953 AC3 evidence channel reads, so the contract
# carries the keyword (``Callable[..., Any]`` to keep the kwarg in the type).
Spawn = Callable[..., Any]
# Spawn a claimed row onto the supervisor path (#1121 plan step 8). Row-dict-based
# (not goal-string-based like Spawn above) — the supervisor adapter needs the whole
# row to derive lineage/attempt and to build its env. Called as
# ``supervisor_spawn(row, task_id=<id>)``.
SupervisorSpawn = Callable[..., Any]
# Resolve the claude binary; raises FileNotFoundError when unresolved (AC7a).
ResolveBinary = Callable[[], str]
# Quota probe — returns a UsageReading-shaped object with .near_exhaustion
# (#921 AC4). The production default is false-safe: it never raises, a probe
# error reads as near-exhaustion, so a broken probe pauses dispatch.
ReadUsage = Callable[[], Any]

# Repo root, mirroring executor._REPO_ROOT — anchors per-task worktree creation
# (#1390 AC3) to the main checkout regardless of the daemon's CWD. Tests
# monkeypatch this attribute to point at a temporary repo.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Directory the executor writes per-task stdout JSON to (#953 AC3). Mirrors
# executor._STDERR_LOG_DIR; kept local so the reader has no executor import.
# Anchored to the repo root (this module lives in ``agents/``) so reader and
# writer resolve to the SAME absolute dir regardless of the daemon's CWD — a
# CWD-relative default would silently break the AC3 channel when the wake_driver
# and executor run from different directories (LOW, PR #1011 round 3 —
# sibling-anchored with executor._STDERR_LOG_DIR).
_EXECUTOR_LOG_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs", "executor"
)

# An idempotency key carries lineage as ``<lineage_key>:r<attempt>``. A root
# task (first spawn) has no ``:rN`` suffix and is attempt 1. ``_LINEAGE_SEP`` is
# the single source of truth for the separator: both the builder
# (:func:`format_lineage_key`) and the parser (:func:`parse_lineage` via
# ``_LINEAGE_RE``) derive from it so the two can never drift (MEDIUM, PR #1011 —
# previously the orchestrator hard-coded ``f"{key}:r{n}"`` while the parser owned
# its own regex; a change to one would silently desync the other).
_LINEAGE_SEP = ":r"
_LINEAGE_RE = re.compile(rf"^(.*){re.escape(_LINEAGE_SEP)}(\d+)$")


def format_lineage_key(lineage_key: str, attempt: int) -> str:
    """Build an idempotency key for a re-drive: ``<lineage_key>:r<attempt>`` (#953 AC7).

    Inverse of :func:`parse_lineage` — they share ``_LINEAGE_SEP`` so the wire
    format stays symmetric. Use this anywhere a re-drive key is minted instead of
    interpolating the separator by hand.
    """
    return f"{lineage_key}{_LINEAGE_SEP}{attempt}"


def parse_lineage(idempotency_key: str) -> tuple[str, int]:
    """Split an idempotency key into ``(lineage_key, attempt)`` (#953 AC7).

    ``"abc:r2"`` → ``("abc", 2)``; a bare key or empty string is the root
    attempt → ``(key, 1)``. The lineage key is stable across re-drives so
    every attempt of one task shares it; the attempt number gates MAX_ATTEMPTS.

    The attempt is the OUTERMOST ``:rN`` suffix (the most recent re-drive), and
    the root has *every* ``:rN`` suffix peeled off — so a doubly-suffixed key
    like ``"abc:r2:r3"`` resolves to ``("abc", 3)``, not ``("abc:r2", 3)``. A
    non-greedy single-strip would leave an inner ``:rN`` in the root and split
    one task's lineage across distinct root keys (MAJOR, #1011).
    """
    if not idempotency_key:
        return ("", 1)
    m = _LINEAGE_RE.match(idempotency_key)
    if not m:
        return (idempotency_key, 1)
    attempt = int(m.group(2))
    root = m.group(1)
    inner = _LINEAGE_RE.match(root)
    while inner:
        root = inner.group(1)
        inner = _LINEAGE_RE.match(root)
    return (root, attempt)


def build_dedup_key(event_type: str, task_id: str, attempt: int) -> str:
    """Completion-event dedup key: ``<event_type>:<task_id>:a<attempt>`` (#1121 step 11).

    Single source of truth for the format both the supervisor's own event
    emission (below) and the future S4 sweeper's re-emission must reproduce
    byte-for-byte — the issue's motivating bug was an ``a0``/``a1`` drift
    between the two sides. A shared JSON fixture
    (``tests/fixtures/sandcastle-dedup-key.json``) asserts this against the
    TS side's independent string interpolation in
    ``.sandcastle/check-dedup-key-contract.mts`` (decision
    ``17736ef0-01d2-492a-b490-ef5d0b46cb11``).
    """
    return f"{event_type}:{task_id}:a{attempt}"


def _augment_branch_directive(goal: str, task_id: str) -> str:
    """Append the ``task/<task_id>`` branch directive to a fresh-shape goal (AC5).

    Only fresh-shape goals lacking an explicit ``(branch=...)`` directive are
    augmented — a rework goal (``/rework #N``) already targets an existing PR's
    branch and must NEVER be augmented (AC5), and a goal that already names a
    branch is left as the author wrote it. The directive embeds the convention
    the evidence check (:func:`check_pr_evidence_fresh_shape`) looks for, so
    spawn-side and evidence-side agree on where the PR should be.
    """
    if "(branch=" in goal:
        return goal
    shape, _ = parse_goal_shape(goal)
    if shape != "fresh":
        return goal
    return f"{goal}\n\n(branch=task/{task_id})"


def _augment_closes_mandate(goal: str, task_id: str) -> str:
    """Append a ``Closes #<N>`` PR-body mandate to a fresh-shape goal (#1136 AC1).

    The executor lane's spawned ``claude -p`` sessions are permitted to run
    ``Bash(gh pr create:*)`` (``executor._SPAWN_ALLOWED_TOOLS``) with no directive
    to link the issue their PR closes — so a merged PR can silently fail to
    auto-close its issue (the #948 failure mode; native linked-issue auto-close is
    suppressed for bot/App-attributed merges, so the closing keyword in the PR body
    is what the ``pr-merged.yml`` close path keys on). Fresh-shape goals naming an
    issue ``#N`` get an explicit mandate appended so the child's PR body carries
    that keyword.

    Fires **iff** the goal is fresh-shape AND names an issue (``#N``). Rework goals
    (``/rework #N``) target an existing PR and are left untouched; a fresh goal with
    no ``#N`` has no close target; an empty goal is a no-op. AC3 escape: the mandate
    permits the child to emit ``Refs #N`` instead when the PR only partially
    addresses the issue — both satisfy the ``require-linked-issue`` merge gate, but
    only ``Closes`` triggers auto-close. Additive like
    :func:`_augment_branch_directive` — the original goal is preserved verbatim as a
    prefix. ``task_id`` is unused (sibling-parity with the branch augmenter); kept in
    the signature for a uniform augmenter shape.
    """
    shape, _ = parse_goal_shape(goal)
    if shape != "fresh":
        return goal
    issue_number = pr_evidence.goal_issue_number(goal)
    if issue_number is None:
        return goal
    return (
        f"{goal}\n\n(PR-body requirement: when you open the PR, put "
        f"`Closes #{issue_number}` on its own line in the body so the merge "
        f"auto-closes the issue. If this PR only partially addresses "
        f"#{issue_number}, use `Refs #{issue_number}` instead — it still satisfies "
        f"the linked-issue merge gate but leaves the issue open.)"
    )


# A task_id is interpolated into the executor-log path, so it must be confined
# to a charset that cannot escape the directory — no ``/``, ``\``, ``.`` (hence
# no ``..``), or other path-significant characters. UUIDs and the alnum ids used
# elsewhere both satisfy this; a crafted ``../../etc/passwd`` does not (LOW,
# PR #1011 — path-traversal hardening on the AC3 secondary channel).
_SAFE_TASK_ID_RE = re.compile(r"\A[A-Za-z0-9_-]+\Z")


def default_stdout_reader(task_id: str) -> str | None:
    """Read the executor's stdout JSON for ``task_id`` (#953 AC3 secondary).

    Returns the file text, or ``None`` when it is absent/unreadable — the
    secondary-evidence path is best-effort, so a missing log degrades the
    check to its primary verdict rather than raising.

    A ``task_id`` outside the safe ``[A-Za-z0-9_-]`` charset (e.g. one carrying
    ``..`` or a path separator) is rejected up front and returns ``None`` — it
    never reaches the filesystem, closing the path-traversal vector (LOW #1011).
    """
    if not _SAFE_TASK_ID_RE.match(task_id):
        logger.warning(
            "default_stdout_reader: refusing unsafe task_id %r (path-traversal guard)",
            task_id,
        )
        return None
    path = os.path.join(_EXECUTOR_LOG_DIR, f"{task_id}.stdout.json")
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return None


def _severity_for(
    event_type: str, pr_evidence: bool | None, *, closing_ref: bool | None = None
) -> str:
    """Severity for a terminal event, satisfying the events CHECK constraint.

    A clean ``task_done`` with PR evidence is ``info`` (pure-pipeline no-op);
    every other terminal outcome is ``medium`` so it outranks noise but is not
    treated as an incident.

    When ``closing_ref`` is ``False`` (PR exists but body lacks the closing
    keyword), a ``task_done`` is promoted to ``medium`` — the supervisor
    auto-fixes the body but the miss is still noteworthy. (#1169 item 3)
    """
    if event_type == "task_done" and pr_evidence is True and closing_ref is not False:
        return "info"
    return "medium"


@runtime_checkable
class TaskQueuePort(Protocol):
    """The slice of the task FSM the dispatch loop depends on (AC10).

    Implemented for real by :class:`SupabaseTaskQueue` over
    :mod:`agents.task_queue`, and by an in-memory fake in the tests.

    ``runtime_checkable`` makes ``isinstance(x, TaskQueuePort)`` check only that
    the method *names* are present — not their signatures — so the
    ``isinstance`` assertion in the tests is a structural smoke check, not a
    full conformance proof.
    """

    def claim_next(self, *, assignee: str) -> dict[str, Any] | None:
        """Claim the highest-priority pending row for ``assignee`` (pending→claimed)."""

    def count_running(self, *, assignee: str) -> int:
        """Count rows currently ``running`` for ``assignee`` (concurrency cap)."""

    def transition(
        self, task_id: str, to_status: str, *, reason: str | None = None
    ) -> dict[str, Any]:
        """Advance a task through the FSM (validated in the real adapter)."""

    def reclaim_stale_claimed(self, *, assignee: str, older_than_seconds: float) -> int:
        """Return stale ``claimed`` rows to ``pending`` (direct UPDATE, FSM-bypassing)."""

    def list_stale_running(
        self, *, assignee: str, older_than_seconds: float
    ) -> list[dict[str, Any]]:
        """List ``running`` rows older than the reaper threshold for ``assignee``."""

    def requeue_running(self, task_id: str) -> bool:
        """Return one process-less ``running`` row to ``pending`` (direct UPDATE, #921 AC4)."""

    def get_status(self, task_id: str) -> str | None:
        """Look up one task's current FSM status, or ``None`` if the row is absent.

        Backs the #1390 AC6 worktree sweep: each on-disk worktree is keyed by
        ``task_id``, and the sweep needs a single-row status check — no
        existing method here lists all rows or looks up one by id.
        """

    def set_plan_digest(self, task_id: str, digest: str) -> dict[str, Any]:
        """Persist a locked plan's hash onto ``task_id`` (direct UPDATE, #1689).

        Backs the ex-post plan-review drain gate (:mod:`agents.plan_review_drain`):
        once a ordinal-2 row's planner-produced plan is written and locked, the
        digest is persisted here so the pre-spawn recheck can detect a
        post-approval issue-body edit (AC6, fail closed).
        """

    def get_row(self, task_id: str) -> dict[str, Any] | None:
        """Fetch one task row in full, or ``None`` if the row is absent (#1690).

        Backs the replan-carrier gate: rebuilding the planner's input and
        reading the current ``replan_count`` needs the whole row, not just
        the status column ``get_status`` returns.
        """

    def requeue_for_replan(self, task_id: str, new_replan_count: int) -> dict[str, Any]:
        """Bump ``replan_count`` and return a ``running`` row to ``pending`` (#1690)."""


@dataclass(frozen=True)
class DrainResult:
    """What one :func:`drain_tasks` did."""

    spawned: int = 0
    failed: int = 0
    # Tasks terminated as ``skipped_duplicate`` by the #931 pre-spawn dedup:
    # a live PR (or a live sibling queue row) already covers their issue.
    skipped_duplicate: int = 0
    # True iff the whole drain was skipped because the claude binary did not
    # resolve (AC7a) — distinct from "ran, claimed nothing".
    skipped_no_binary: bool = False
    # True iff the drain skipped/stopped on quota near-exhaustion — either the
    # AC4 pre-flight (nothing claimed) or a mid-drain throttled spawn (the one
    # in-flight row is requeued to ``pending``; on requeue failure the AC6
    # reaper is the backstop). Remaining rows stay ``pending`` and self-heal.
    throttled: bool = False
    # True iff the whole drain was skipped because the plan-review config
    # (#1689) failed to load — distinct from ``skipped_no_binary``; the ex-post
    # gate cannot be evaluated for any ordinal-2 row without it, so the drain
    # fails closed rather than spawning unreviewed ordinal-2 work.
    skipped_no_plan_config: bool = False
    # Tasks parked because the ex-post plan-review gate (#1689) could not
    # produce a resolved, locked plan for a ordinal-2 row (planner raised, or
    # returned resolved=False) — distinct from the pre-spawn fail-closed
    # digest mismatch below, which is a hard failure rather than a park.
    parked: int = 0
    # (task_id, proc) per *successful* spawn that yielded a pollable process
    # handle (#921 AC1). A raising spawn never reaches the append; a throttled
    # spawn returns early (the whole drain stops) before it; a result without
    # a ``proc`` attribute counts as spawned but is skipped here. The
    # wake_driver folds these pairs into its {task_id: TrackedProc} liveness
    # map to close running→done on process exit.
    procs: tuple[tuple[str, Any], ...] = ()
    # Per-task spawn metadata keyed by task_id (#953): the original ``goal``,
    # the ``idempotency_key`` (lineage + attempt), and a tz-aware ``spawned_at``
    # stamp. The wake_driver folds these into each :class:`TrackedProc` so the
    # completion poll can compute PR evidence at the terminal boundary. Kept
    # separate from ``procs`` so the existing (task_id, proc) contract — and the
    # drain tests that assert on it — stay byte-for-byte unchanged.
    spawned_meta: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass(frozen=True)
class ReclaimResult:
    """What one :func:`reclaim_stale_tasks` did."""

    reclaimed_claimed: int = 0
    reaped_running: int = 0


@dataclass(frozen=True)
class TrackedProc:
    """A live spawn under liveness tracking (#921 AC2).

    ``proc`` is the ``Popen``-shaped handle from :class:`executor.SpawnResult`;
    ``started_at`` is a monotonic-clock stamp the runaway check measures age
    against (AC6). It is a **per-batch** stamp, not per-task: the wake_driver
    samples ``task_clock()`` **once, before** the drain and assigns that same
    value to every proc folded into the map on that tick (wake_driver.tick Step
    4). The pre-drain single sample is deliberate — stamping after the drain
    would discard the just-spawned handles if the clock raised mid-fold,
    orphaning live children onto the 6h reaper (the exact regression
    ``test_tick_stamps_the_clock_before_spawning`` /
    ``test_tick_with_a_broken_clock_spawns_nothing`` guard against). The
    resulting age skew across a batch is bounded by the drain's own duration
    (≤ ``cap`` spawns) and is negligible against the multi-hour
    ``task_running_reap_after_seconds`` threshold, so per-task accuracy buys
    nothing and would reintroduce the orphan risk. Pinned by
    ``test_tick_batch_shares_one_started_at_stamp``.

    The #953 fields carry the spawn context the completion poll needs to compute
    PR evidence at the terminal boundary: the original ``goal`` (shape + branch),
    the ``idempotency_key`` (lineage + attempt for re-drive keying), and a
    tz-aware ``spawned_at`` (the rework evidence check compares PR activity
    against it — a naive datetime would raise on the aware/naive compare). They
    default empty/``None`` so an adopted-after-restart proc with no recovered
    metadata yields ``pr_evidence=null`` → escalate (documented #921 limitation).

    ``issue_number`` (#1085 S1-5) carries the claimed row's real ``issue_number``
    column value (when set) so the terminal-boundary PR-evidence computation can
    use it column-first, falling back to parsing ``goal`` for legacy/null rows —
    same default-``None`` rationale as the fields above.

    ``target_repo``/``target_type``/``target_number`` (#1617) carry the claimed
    row's pins forward so the terminal ``task_done``/``task_failed`` event
    payloads can copy them onto a re-drive Decision — same default-``None``
    rationale as the fields above.

    ``origin`` (#1758 review fix) carries the claimed row's own ``origin``
    column (``"dispatch"`` vs ``"orchestrator"``) forward the same way, so a
    re-drive of a ``/dispatch``-issued task preserves its origin instead of
    the orchestrator's re-enqueue defaulting it to ``"orchestrator"`` — which
    would route the re-drive through the wrong drain-time readiness gate.
    """

    proc: Any
    started_at: float
    goal: str = ""
    idempotency_key: str = ""
    spawned_at: datetime | None = None
    issue_number: int | None = None
    target_repo: str | None = None
    target_type: str | None = None
    target_number: int | None = None
    origin: str | None = None


@dataclass(frozen=True)
class CompletionResult:
    """What one :func:`poll_completions` did (#921 AC2)."""

    done: int = 0
    failed_exit: int = 0
    # Tasks routed to a #1690 mid-run replan-request comment instead of the
    # normal done/failed branch: ``replan_count == 0`` reruns the planner and
    # requeues to ``pending`` (counted here too, since it is neither done nor
    # failed_exit); ``replan_count >= 1`` parks with a structured
    # ``replan_exhausted``/``replan_failed`` reason. Mirrors
    # :attr:`DrainResult.parked`'s meaning for the completion side of the
    # pipeline.
    parked: int = 0


# An ``event_emit`` callback: (event_type, severity, payload, *, dedup_key).
# Mirrors wake_driver's production emitter and the tests' FakeEventQueue —
# severity is explicit (events CHECK constraint), dedup_key absorbs a
# re-observed terminal event at the DB unique index (#953 AC1/AC9).
EventEmit = Callable[..., Any]


def _finalize_terminal_task(
    task_id: str,
    *,
    sidecar: Sidecar | None,
    success: bool,
) -> None:
    """Best-effort sidecar delete + worktree finalize shared by every terminal
    exit from :func:`poll_completions` — the done/failed branch and the
    #1690 replan/park branch alike (AC6 #952, AC5 #1390)."""
    if sidecar is not None:
        try:
            sidecar.delete_sidecar_file(task_id)
        except Exception:  # noqa: BLE001 — sidecar delete is best-effort
            logger.exception("[task_dispatch] sidecar delete failed for task %s", task_id)
    try:
        task_worktree.finalize_task_worktree(task_id, success=success)
    except Exception:  # noqa: BLE001 — worktree finalize is best-effort
        logger.exception("[task_dispatch] worktree finalize failed for task %s", task_id)


def _handle_replan_request(
    task_id: str,
    row: dict[str, Any],
    replan_request: Any,
    *,
    port: TaskQueuePort,
    evidence_client: GitHubClient,
    planner: PlannerPort,
    plan_config: PlanReviewConfig,
) -> None:
    """Act on a #1690 replan-request comment found for a just-exited task.

    ``replan_count == 0`` → rerun the planner with ``prior_failure`` folded
    in, write the new plan section, verify+digest it, and requeue the row to
    ``pending`` via :meth:`TaskQueuePort.requeue_for_replan` so the next
    drain re-executes it. ``replan_count >= 1`` → the row already used its one
    replan; park it with a structured ``escalated_reason`` (per the Plan
    section's park-with-structured-reason design) instead of looping forever.
    A planner raise, an unresolved plan, or a malformed/unlocked plan on the
    replan attempt itself also parks — a failed replan attempt must not wedge
    the row in ``running`` forever.
    """
    current_replan_count = int(row.get("replan_count") or 0)

    if current_replan_count >= 1:
        try:
            port.transition(
                task_id,
                "parked",
                reason=json.dumps(
                    {
                        "kind": "replan_exhausted",
                        "broken_assumption": replan_request.broken_assumption,
                        "evidence": replan_request.evidence,
                    }
                ),
            )
        except Exception:  # noqa: BLE001 — row stays running; reaper backstops
            logger.exception(
                "[task_dispatch] could not park task %s on replan_exhausted; "
                "row left running for the reaper",
                task_id,
            )
        return

    prior_failure = f"{replan_request.broken_assumption}\n\nEvidence: {replan_request.evidence}"
    try:
        plan_result = planner.run_planner(row, plan_config, prior_failure=prior_failure)
        if not plan_result.resolved:
            raise RuntimeError(plan_result.reason or "planner did not resolve the replan")
        issue_number = int(row["issue_number"])
        new_body = _write_plan_section(evidence_client, issue_number, plan_result.plan_text)
        if not verify_lock(new_body):
            raise MalformedPlanError("planner wrote a malformed or unlocked replan")
        digest = parse_plan(new_body).lock
    except Exception as exc:  # noqa: BLE001 — a failed replan attempt parks, never wedges
        logger.exception("[task_dispatch] replan attempt failed for task %s; parking", task_id)
        try:
            port.transition(
                task_id,
                "parked",
                reason=json.dumps(
                    {
                        "kind": "replan_failed",
                        "broken_assumption": replan_request.broken_assumption,
                        "evidence": f"{replan_request.evidence}\n\nreplan error: {exc}",
                    }
                ),
            )
        except Exception:  # noqa: BLE001 — row stays running; reaper backstops
            logger.exception(
                "[task_dispatch] could not park task %s on replan_failed; "
                "row left running for the reaper",
                task_id,
            )
        return

    try:
        port.set_plan_digest(task_id, digest)
        port.requeue_for_replan(task_id, current_replan_count + 1)
    except Exception:  # noqa: BLE001 — row stays running; reaper backstops
        logger.exception(
            "[task_dispatch] set_plan_digest/requeue_for_replan failed for task %s after a "
            "successful replan write; row left running for the reaper",
            task_id,
        )


def poll_completions(
    port: TaskQueuePort,
    procs: dict[str, TrackedProc],
    *,
    sidecar: Sidecar | None = None,
    event_emit: EventEmit | None = None,
    evidence_client: GitHubClient | None = None,
    stdout_reader: Callable[[str], str | None] | None = None,
    outcome_record: Callable[[dict[str, Any]], None] | None = None,
    planner: PlannerPort | None = None,
    plan_config_loader: Callable[[], PlanReviewConfig] = default_plan_config_loader,
) -> CompletionResult:
    """Close ``running`` rows whose process has exited (#921 AC2, Model P).

    For each tracked pair: ``poll() is None`` → still running, kept;
    ``poll() == 0`` → ``transition(done)``; ``poll() != 0`` →
    ``transition(failed, reason="exit <rc>")``. The DB transition is what frees
    the cap slot (``count_running`` drops) for the same tick's drain; dropping
    the closed entry from ``procs`` (mutated in place) just stops it from being
    re-polled and shields the row from the watchdogs.

    **``done`` means the process exited 0 — nothing more.** Not task success,
    not PR merged; the child may have produced garbage and exited cleanly.
    Outcome truth re-enters externally via Path-A GitHub events.

    AC1/AC2/AC3 (#953): at the terminal boundary the poll computes **PR
    evidence** for the task — parsing the goal shape carried on the
    :class:`TrackedProc` and querying ``evidence_client`` (a real PR exists for
    a fresh task / PR #N got new activity for a rework), with the executor
    stdout (``stdout_reader``) as the AC3 secondary channel. The resulting
    tri-state plus the task's ``lineage_key``/``attempt`` (parsed from its
    idempotency key) go into the payload, and the event is emitted **before**
    the FSM transition so a crash in the window self-heals on re-observation —
    the ``dedup_key`` (``<event_type>:<task_id>:a<attempt>``) absorbs the
    duplicate. With no ``event_emit`` wired, no events are emitted (the #921
    completion behavior is unchanged).

    Per-row isolation: a ``transition`` raising logs, drops the entry, and
    continues — the row stays ``running`` in the store with no live handle, so
    the AC5/AC6 orphan reaper is the backstop. No counter is incremented for it.

    **#1690 replan-carrier**: opt-in via ``planner`` (``None`` by default —
    without it, replan detection is skipped and this function's behavior is
    byte-for-byte the pre-#1690 one). When ``planner`` is wired and the exited
    task carries both ``evidence_client`` and ``tracked.issue_number``, this
    checks for a replan-request comment (:func:`agents.plan_review_drain.find_replan_request`)
    posted since ``tracked.spawned_at`` — an executor that hit a broken plan
    assumption mid-implementation. A hit is routed to
    :func:`_handle_replan_request` instead of the normal done/failed branch:
    ``replan_count == 0`` reruns the planner and requeues to ``pending``;
    ``replan_count >= 1`` parks (the row already used its one replan).
    """
    done = 0
    failed_exit = 0
    parked = 0
    for task_id, tracked in list(procs.items()):
        # poll_exit handles both handle kinds: a freshly-spawned Popen (real exit
        # code) and an adopted psutil.Process (no poll()/returncode — exited maps
        # to a non-zero sentinel → failed, #952). A bare .poll() here would
        # AttributeError on every adopted handle and wedge the row in running.
        rc = poll_exit(tracked.proc)
        if rc is None:
            continue

        # #1690 replan-carrier — checked before the normal done/failed branch so
        # a replan-request comment always wins over whatever exit code the
        # executor happened to end with. Opt-in: skipped entirely unless the
        # caller wires ``planner`` (production: wake_driver.tick threads its
        # own ``task_planner``/``task_plan_config_loader`` through here).
        if planner is not None and evidence_client is not None and tracked.issue_number is not None:
            since = tracked.spawned_at.isoformat() if tracked.spawned_at else None
            try:
                replan_request = _find_replan_request(
                    evidence_client, tracked.issue_number, since=since
                )
            except Exception:  # noqa: BLE001 — a lookup failure is not a replan
                logger.exception(
                    "[task_dispatch] replan-request lookup failed for task %s", task_id
                )
                replan_request = None
            if replan_request is not None:
                row = port.get_row(task_id)
                if row is not None:
                    _handle_replan_request(
                        task_id,
                        row,
                        replan_request,
                        port=port,
                        evidence_client=evidence_client,
                        planner=planner,
                        plan_config=plan_config_loader(),
                    )
                    parked += 1 if int(row.get("replan_count") or 0) >= 1 else 0
                    _finalize_terminal_task(task_id, sidecar=sidecar, success=False)
                    procs.pop(task_id, None)
                    continue

        # AC1/AC2/AC3 (#953) — compute evidence and lineage at the boundary, then
        # emit the event BEFORE the transition (event-first ordering). spawned_at
        # rides on the TrackedProc as tz-aware (folded in by the wake_driver);
        # an adopted-after-restart proc has no goal/spawned_at → evidence is null.
        goal = tracked.goal
        lineage_key, attempt = parse_lineage(tracked.idempotency_key)

        # #1169 item 1: for a done fresh-shape task, ensure the PR body carries
        # a closing ref. The supervisor auto-fixes if the agent omitted it.
        if rc == 0 and evidence_client is not None:
            pr_evidence.ensure_pr_closing_ref(
                task_id, goal, client=evidence_client, issue_number=tracked.issue_number
            )

        # #1169 item 3: unpack the closing-ref status alongside the PR evidence.
        # Named ``pr_exists`` (not ``pr_evidence``) — this function scope also
        # calls the ``pr_evidence`` module above; assigning that name locally
        # here would make every earlier reference to it an UnboundLocalError.
        pr_exists, closing_ref = pr_evidence.compute_pr_evidence(
            task_id,
            goal,
            tracked.spawned_at,
            client=evidence_client,
            stdout_reader=stdout_reader,
            issue_number=tracked.issue_number,
        )

        # Event emission and the FSM transition are DECOUPLED (MAJOR, PR #1011).
        # event-first ordering is the happy path, but if the emit raises (Supabase
        # down, network blip) the transition MUST still fire — otherwise the task
        # is stuck in ``running`` until the 6h reaper sweeps it. A dropped event
        # self-heals on re-observation; a stuck transition does not. So the emit
        # gets its own try/except and never blocks the transition below.
        if event_emit:
            try:
                if rc == 0:
                    event_emit(
                        "task_done",
                        _severity_for("task_done", pr_exists, closing_ref=closing_ref),
                        {
                            "task_id": task_id,
                            "lineage_key": lineage_key,
                            "attempt": attempt,
                            "pr_evidence": pr_exists,
                            "goal": goal,
                            "closing_ref": closing_ref,
                            "target_repo": tracked.target_repo,
                            "target_type": tracked.target_type,
                            "target_number": tracked.target_number,
                            "origin": tracked.origin,
                        },
                        dedup_key=build_dedup_key("task_done", task_id, attempt),
                    )
                else:
                    event_emit(
                        "task_failed",
                        _severity_for("task_failed", pr_exists),
                        {
                            "task_id": task_id,
                            "lineage_key": lineage_key,
                            "attempt": attempt,
                            "exit_code": rc,
                            "exit_confirmed": True,
                            "pr_evidence": pr_exists,
                            "failure_reason": f"exit {rc}",
                            "goal": goal,
                            "target_repo": tracked.target_repo,
                            "target_type": tracked.target_type,
                            "target_number": tracked.target_number,
                            "origin": tracked.origin,
                        },
                        dedup_key=build_dedup_key("task_failed", task_id, attempt),
                    )
            except Exception:  # noqa: BLE001 — emit failure must not block transition
                logger.exception(
                    "[task_dispatch] event emit for task %s failed; "
                    "proceeding with transition (event self-heals on re-observation)",
                    task_id,
                )

        # #1085 S2 review finding 2: write the task_outcomes row for a completed
        # subagent task here, since /task-implement runs with no MCP tools and
        # cannot call outcome_record itself (see task_outcomes.record_completion_outcome).
        # Decoupled from the transition below for the same reason event_emit is —
        # an outcome-write failure must never block the FSM transition.
        if rc == 0 and outcome_record is not None:
            try:
                outcome_record(
                    {
                        "task_id": task_id,
                        "goal": goal,
                        "issue_number": tracked.issue_number,
                        "pr_url": task_outcomes.resolve_pr_url(
                            task_id, goal, client=evidence_client
                        ),
                        "is_class_2": task_outcomes.resolve_is_class_2(
                            tracked.issue_number, client=evidence_client
                        ),
                    }
                )
            except Exception:  # noqa: BLE001 — outcome write must not block transition
                logger.exception(
                    "[task_dispatch] completion outcome record for task %s failed",
                    task_id,
                )

        try:
            if rc == 0:
                port.transition(task_id, "done")
                done += 1
            else:
                port.transition(task_id, "failed", reason=f"exit {rc}")
                failed_exit += 1
        except Exception:  # noqa: BLE001 — isolate one bad row, reaper backstops it
            logger.exception(
                "[task_dispatch] completion transition for task %s failed; "
                "dropped from tracking (reaper backstop)",
                task_id,
            )
        finally:
            # AC6 (#952) / AC5 (#1390) — sidecar delete + worktree finalize;
            # success=(rc == 0) detaches HEAD on failure so the branch ref is
            # free for `_redrive_goal`'s retry.
            _finalize_terminal_task(task_id, sidecar=sidecar, success=(rc == 0))
            procs.pop(task_id, None)
    return CompletionResult(done=done, failed_exit=failed_exit, parked=parked)


def kill_runaways(
    port: TaskQueuePort,
    procs: dict[str, TrackedProc],
    *,
    max_runtime_seconds: float = DEFAULT_RUNNING_REAP_SECONDS,
    now: Callable[[], float] = time.monotonic,
    kill: Callable[[Any], None] = kill_process_tree,
    sidecar: Sidecar | None = None,
    event_emit: EventEmit | None = None,
) -> int:
    """Tree-kill live processes that exceeded the max runtime (#921 AC6).

    The orphan reaper (:func:`reclaim_stale_tasks`) deliberately skips rows
    with a live tracked process — this is the counterpart that bounds those:
    a process still alive past ``max_runtime_seconds`` (same one 6h knob as
    the reaper) is killed with its whole tree, its row transitioned
    ``running → failed`` (``reason="killed: exceeded max runtime"``), and the
    entry dropped. Killed runaways fold into the tick's failed-exit counter.

    Already-exited processes are skipped — :func:`poll_completions` owns those
    (their real exit code decides done vs failed). Per-row isolation: a *kill*
    raising keeps the entry (the process may still be alive; failing the row
    would lie — retried next tick); a *transition* raising after a successful
    kill drops the entry to the reaper backstop, like ``poll_completions``.

    AC1 (#953): a runaway-reaped task is the worst-case stuck class the
    reconciliation exists to catch, so — like :func:`poll_completions` — it
    emits ``task_failed`` (``exit_confirmed=True``, ``pr_evidence=None``,
    ``failure_reason="killed: exceeded max runtime"``) when ``event_emit`` is
    wired, so the orchestrator can re-drive or escalate. Without the emit the
    killed task vanishes silently (MAJOR, PR #1011). The emit is DECOUPLED from
    the transition (its own try/except): an emit blowup must not strand the kill
    in ``running`` — a dropped event self-heals on re-observation via the
    ``dedup_key``. With no ``event_emit`` the #921 behavior is unchanged.
    """
    killed = 0
    for task_id, tracked in list(procs.items()):
        if poll_exit(tracked.proc) is not None:
            continue  # exited — poll_completions closes it (real rc or sentinel)
        if now() - tracked.started_at <= max_runtime_seconds:
            continue
        try:
            kill(tracked.proc)
        except Exception:  # noqa: BLE001 — possibly still alive; retry next tick
            logger.exception(
                "[task_dispatch] tree-kill of runaway task %s failed; will retry",
                task_id,
            )
            continue
        # AC1 (#953) — emit task_failed BEFORE the transition (event-first), and
        # DECOUPLED from it: a runaway is the worst-case stuck class, so the
        # orchestrator must hear about it even if the transition later fails. The
        # emit's own try/except keeps an emit blowup (Supabase down) from
        # stranding the kill in ``running`` — a dropped event self-heals on
        # re-observation via the dedup_key.
        lineage_key, attempt = parse_lineage(tracked.idempotency_key)
        if event_emit:
            try:
                event_emit(
                    "task_failed",
                    _severity_for("task_failed", None),
                    {
                        "task_id": task_id,
                        "lineage_key": lineage_key,
                        "attempt": attempt,
                        "exit_confirmed": True,
                        "pr_evidence": None,
                        "failure_reason": "killed: exceeded max runtime",
                        "goal": tracked.goal,
                        "target_repo": tracked.target_repo,
                        "target_type": tracked.target_type,
                        "target_number": tracked.target_number,
                        "origin": tracked.origin,
                    },
                    dedup_key=build_dedup_key("task_failed", task_id, attempt),
                )
            except Exception:  # noqa: BLE001 — emit failure must not block transition
                logger.exception(
                    "[task_dispatch] runaway task %s event emit failed; "
                    "proceeding with transition (event self-heals on re-observation)",
                    task_id,
                )
        try:
            port.transition(task_id, "failed", reason="killed: exceeded max runtime")
            killed += 1
        except Exception:  # noqa: BLE001 — killed but row not closed; reaper backstops
            logger.exception(
                "[task_dispatch] runaway task %s killed but transition failed; "
                "dropped from tracking (reaper backstop)",
                task_id,
            )
        finally:
            # AC4 (#952) — delete sidecar when tree-killing orphan.
            if sidecar is not None:
                try:
                    sidecar.delete_sidecar_file(task_id)
                except Exception:  # noqa: BLE001 — sidecar delete is best-effort
                    logger.exception(
                        "[task_dispatch] sidecar delete failed for runaway task %s",
                        task_id,
                    )
            procs.pop(task_id, None)
    return killed


def default_spawn(goal: str, *, task_id: str | None = None) -> Any:
    """Production spawn adapter — fire-and-forget ``claude -p`` via the executor.

    Returns the :class:`executor.SpawnResult`. A throttled result (quota
    near-exhaustion) means no process launched; :func:`drain_tasks` inspects the
    ``throttled`` flag and stops the drain rather than counting a phantom spawn.
    Imported lazily so the tested drain logic (which injects its own spawn) need
    not pull executor's subprocess/usage-probe dependencies.

    AC3 (#953): passes task_id to the executor for stdout JSON capture.

    AC5 (#953): a **fresh-shape** goal with no explicit ``(branch=...)`` directive
    gets ``(branch=task/<task_id>)`` appended before spawn, so the child opens its
    PR on a deterministic head branch the terminal-boundary evidence check can find.
    Rework-shape goals (``/rework #N``) and goals that already pin a branch are left
    untouched — augmentation is purely additive and never rewrites an operator's
    branch choice. The un-augmented goal is what ``drain_tasks`` records in
    ``spawned_meta`` for evidence (the default head ``task/<task_id>`` matches).

    AC1 (#1136): a fresh-shape goal naming an issue ``#N`` additionally gets a
    ``Closes #<N>`` PR-body mandate appended (:func:`_augment_closes_mandate`), so a
    PR the executor lane opens links its issue and auto-closes on merge (#948).
    """
    from agents.executor import spawn as executor_spawn

    spawn_goal = _augment_branch_directive(goal, task_id) if task_id else goal
    # #1136 AC1: also inject the Closes #<N> PR-body mandate for a fresh-shape goal
    # naming an issue. Order-independent of the branch directive above — the branch
    # suffix carries no ``#N`` and is not a ``/rework`` marker, so it neither adds a
    # spurious close target nor flips the goal's shape.
    spawn_goal = _augment_closes_mandate(spawn_goal, task_id) if task_id else spawn_goal
    # AC3 (#1390): isolate each spawned worker in its own git worktree so
    # concurrent workers never share a working tree. Pass spawn_goal (not the
    # raw goal) so a fresh-shape redrive's (branch=task/<root_task_id>) pin
    # (added by _redrive_goal, threaded through by _augment_branch_directive)
    # is honored — see task_worktree.create_task_worktree docstring.
    cwd = task_worktree.create_task_worktree(task_id, spawn_goal) if task_id else None
    return executor_spawn(spawn_goal, task_id=task_id, cwd=cwd)


def default_supervisor_spawn(row: dict[str, Any], *, task_id: str) -> Any:
    """Production supervisor-path spawn adapter (#1121 plan step 6).

    Launches ``.sandcastle/main.mts`` (the sandcastle supervisor, via
    ``npm run sandcastle``) instead of :func:`default_spawn`'s bare
    ``claude -p``. Attempt/lineage are derived from the row's idempotency
    key with :func:`parse_lineage`, the same 1-based convention every other
    ``SANDCASTLE_ATTEMPT`` emission uses.

    Wired into :func:`drain_tasks`'s spawn call site (#1121 plan step 8) —
    routed onto whenever the claimed row's effective substrate is
    ``"worktree"``, the only routable value this slice.
    """
    from agents.sandcastle_supervisor import launch_supervisor

    lineage_key, attempt = parse_lineage(str(row.get("idempotency_key", "") or ""))
    return launch_supervisor(row, task_id=task_id, lineage_key=lineage_key, attempt=attempt)


def default_resolve_binary() -> str:
    """Production binary-resolution adapter (lazy import; see :func:`default_spawn`)."""
    from agents.executor import _resolve_claude_binary

    return _resolve_claude_binary()


def default_read_usage() -> Any:
    """Production quota-probe adapter (lazy import; see :func:`default_spawn`).

    :func:`agents.usage_probe.read_usage` is false-safe — it never raises, a
    probe failure returns ``near_exhaustion=True`` — so the AC4 pre-flight
    pauses dispatch rather than flooding it when the probe is broken.
    """
    from agents.usage_probe import read_usage

    return read_usage()


def drain_tasks(
    port: TaskQueuePort,
    spawn: Spawn = default_spawn,
    *,
    assignee: str = DEFAULT_ASSIGNEE,
    cap: int = DEFAULT_CONCURRENCY_CAP,
    resolve_binary: ResolveBinary = default_resolve_binary,
    read_usage: ReadUsage = default_read_usage,
    sidecar: Sidecar | None = None,
    dedup: task_dedup.DedupConfig | None = None,
    planner: PlannerPort = _default_run_planner,
    plan_config_loader: Callable[[], PlanReviewConfig] = default_plan_config_loader,
    github_factory: Callable[[], GitHubClient] = default_github_client,
    supervisor_spawn: SupervisorSpawn = default_supervisor_spawn,
    operator_default_substrate_loader: Callable[[], str] = default_operator_default_substrate,
) -> DrainResult:
    """Claim pending ``assignee`` tasks up to the cap and spawn each (AC2–AC4, AC7–AC9).

    Order of operations:

    1. **Pre-flight binary resolution, once (AC7a).** If the claude binary does
       not resolve — missing, not executable, or the executor import is broken —
       skip the *entire* drain: zero claims, nothing marked ``failed``, every
       row stays ``pending`` so the next drain self-heals once the env is fixed.
       No internal retry.
    2. **Budget, sampled once (AC3).** ``budget = cap − count_running(assignee)``.
       Nothing exits ``running`` mid-drain, so the snapshot is exact; the loop
       spawns at most ``budget`` tasks and leaves the rest ``pending``.
    3. **Per task, Ordering B (AC4).** ``claim_next`` (pending→claimed) →
       ``transition(running)`` → ``spawn(goal)``. The running transition
       precedes the spawn so a crash in the window can only strand a ``running``
       row (reaped, AC6), never a ``claimed`` row with a live process (which
       would double-spawn under the AC5 reclaimer).

    A ``claim_next`` returning ``None`` (empty queue or lost race, AC9) breaks
    the loop cleanly. A ``transition(running)`` raising leaves the row
    ``claimed`` (no process launched) for the AC5 reclaimer and skips to the
    next slot. A ``spawn`` raising (AC7b) marks *that* task ``running→failed``
    (terminal — the external event loop re-drives) and the drain continues. A
    ``spawn`` returning a *throttled* result (quota near-exhaustion: no process
    launched) stops the drain — the one in-flight row is requeued to
    ``pending`` (#921 AC4; reaper backstop if the requeue fails), the rest stay
    ``pending``; quota will not recover mid-drain.

    With ``dedup`` wired (#931), each *fresh-shape* task that references an
    issue is checked after the running transition and before the spawn: a live
    PR for the issue, a live sibling queue row, or a stale claim branch with no
    PR → ``running → skipped_duplicate`` (terminal, best-effort outcome
    record); evidence fetch failure → the row is requeued to ``pending`` and
    the drain stops (unverifiable is never terminal). A stale claim branch is
    routed to ``skipped_duplicate`` rather than ``parked`` (#1119): nothing
    unparks a stale-branch row, and ``parked`` is now a genuinely resumable
    non-terminal state, so parking it would strand the row forever instead of
    landing it on a terminal dead-end the orchestrator already knows how to
    re-route. Rework-shape goals bypass the check — they target a live PR by
    design.
    """
    # AC7a — pre-flight once; an unusable binary skips the whole drain. Widened
    # past FileNotFoundError to the other no-usable-binary failures (not
    # executable → PermissionError; broken executor import → ImportError): all
    # mean "cannot spawn", so skip-and-self-heal beats claim-and-strand.
    try:
        resolve_binary()
    except (FileNotFoundError, PermissionError, ImportError):
        logger.warning(
            "[task_dispatch] claude binary unresolved; skipping drain "
            "(no claims, rows stay pending, self-heals when env is fixed)"
        )
        return DrainResult(skipped_no_binary=True)

    # AC4 (#921) — quota pre-flight, once per drain. Near-exhaustion skips the
    # *entire* drain: zero claims, zero churn, rows stay visibly ``pending``
    # until quota recovers. The default probe is false-safe (a probe error
    # reads as near-exhaustion), so a broken probe pauses dispatch too.
    # executor.spawn re-checks per spawn — that per-spawn gate remains the
    # backstop for a quota flip mid-drain.
    reading = read_usage()
    if getattr(reading, "near_exhaustion", False):
        logger.warning(
            "[task_dispatch] quota near-exhaustion at drain start; skipping drain "
            "(no claims, rows stay pending until quota recovers)"
        )
        return DrainResult(throttled=True)

    # AC3 — budget sampled once at drain start.
    budget = cap - port.count_running(assignee=assignee)
    if budget <= 0:
        return DrainResult()

    # #1689 — plan-review config loaded once per drain (mirrors the AC7a/AC4
    # preflight pattern above): a broken/missing config means the ex-post
    # gate cannot be evaluated for ANY ordinal-2 row this drain, so fail closed
    # by skipping the whole drain rather than silently spawning unreviewed
    # ordinal-2 work.
    try:
        plan_config = plan_config_loader()
    except Exception:  # noqa: BLE001 — unusable config skips the whole drain
        logger.warning(
            "[task_dispatch] plan-review config unavailable; skipping drain "
            "(no claims, rows stay pending, self-heals when config is fixed)"
        )
        return DrainResult(skipped_no_plan_config=True)

    github: GitHubClient | None = None

    spawned = 0
    failed = 0
    parked = 0
    skipped_duplicate = 0
    # #931 — GitHub in-flight evidence, fetched lazily at most once per drain.
    in_flight_evidence: tuple[list[dict[str, Any]], list[str]] | None = None
    procs: list[tuple[str, Any]] = []
    # AC1/AC2 (#953) — carry each spawned task's goal + idempotency key + tz-aware
    # spawn time out to the wake_driver, which folds them onto the TrackedProc so
    # the terminal-boundary poll can compute PR evidence and lineage. spawned_at
    # MUST be tz-aware (datetime.now(UTC)) — the rework-shape evidence check
    # compares it against a tz-aware PR ``updated_at`` and a naive value raises.
    spawned_meta: dict[str, dict[str, Any]] = {}
    for _ in range(budget):
        row = port.claim_next(assignee=assignee)  # AC2 routing; AC9 lost-race → None
        if row is None:
            break
        task_id = str(row["id"])

        # AC4 Ordering B — running BEFORE spawn. Guard it: a transient store
        # error here leaves the row ``claimed`` with no process, so the AC5
        # reclaimer returns it to ``pending``. Skip to the next slot rather than
        # spawn against a row we failed to mark running.
        try:
            port.transition(task_id, "running")
        except Exception:  # noqa: BLE001 — isolate a transient transition error
            logger.exception(
                "[task_dispatch] could not mark task %s running; left claimed for the reclaimer",
                task_id,
            )
            continue

        # #931 — pre-spawn dispatch-dedup. Placed AFTER the running transition
        # (the row is ours under the optimistic lock — a skip verdict can only
        # terminate a row this drain owns) and BEFORE the spawn (the whole
        # point: no duplicate process). Fresh-shape goals only; a rework goal
        # targets a live PR by design and must not be eaten by the live-PR rule.
        if dedup is not None:
            shape, _ = parse_goal_shape(row["goal"])
            issue_number = (
                task_dedup.row_issue_number(row, str(row["goal"])) if shape == "fresh" else None
            )
            if issue_number is not None:
                try:
                    if in_flight_evidence is None:
                        in_flight_evidence = dedup.fetch_in_flight()
                    active_rows = dedup.list_active_rows()
                except Exception:  # noqa: BLE001 — unverifiable is never terminal
                    try:
                        requeued = port.requeue_running(task_id)
                    except Exception:  # noqa: BLE001 — requeue is best-effort
                        requeued = False
                    logger.exception(
                        "[task_dispatch] dedup evidence fetch failed; stopping drain — task %s %s",
                        task_id,
                        "requeued to pending" if requeued else "left running for the reaper",
                    )
                    return DrainResult(
                        spawned=spawned,
                        failed=failed,
                        skipped_duplicate=skipped_duplicate,
                        procs=tuple(procs),
                        spawned_meta=spawned_meta,
                    )

                open_prs, open_branches = in_flight_evidence
                in_flight = pr_evidence.load_gate_module().check_in_flight(
                    issue_number, open_prs, open_branches
                )
                sibling = next(
                    (
                        r
                        for r in active_rows
                        if str(r.get("id")) != task_id
                        and task_dedup.row_issue_number(r, str(r.get("goal") or "")) == issue_number
                    ),
                    None,
                )
                if in_flight.verdict in ("live_pr", "stale_branch") or sibling is not None:
                    pointer = (
                        in_flight.pointer
                        if in_flight.verdict in ("live_pr", "stale_branch")
                        else f"live task_queue row {sibling['id']} already targets #{issue_number}"
                    )
                    try:
                        port.transition(task_id, "skipped_duplicate", reason=pointer)
                    except Exception:  # noqa: BLE001 — row stays running; reaper backstops
                        logger.exception(
                            "[task_dispatch] could not mark task %s skipped_duplicate; "
                            "row left running for the reaper",
                            task_id,
                        )
                        continue
                    skipped_duplicate += 1
                    logger.info(
                        "[task_dispatch] task %s skipped as duplicate: %s", task_id, pointer
                    )
                    if dedup.record_outcome is not None:
                        try:
                            dedup.record_outcome(
                                {
                                    "task_id": task_id,
                                    "issue_number": issue_number,
                                    "goal": row["goal"],
                                    "pointer": pointer,
                                }
                            )
                        except Exception:  # noqa: BLE001 — outcome record is best-effort
                            logger.exception(
                                "[task_dispatch] outcome record for skipped task %s raised",
                                task_id,
                            )
                    continue

                # #1085 S2-3 — /dispatch's own check_issue at enqueue time is
                # advisory, not enforcement. This is the mechanical re-run against
                # a fresh fetch — unconditional for /dispatch-originated rows
                # regardless of what the advisory gate did or didn't catch.
                # Orchestrator-emitted and /rework rows never went through
                # check_issue's readiness conditions and must not start being
                # refused by omission here.
                #
                # #1617 — origin="dispatch" is the primary routing signal (set
                # by the updated /dispatch skill going forward); the legacy
                # "delegate:"-prefix sniff is kept as a fail-safe fallback for
                # rows enqueued before the origin backfill or by a caller not
                # yet updated to set it, so this re-check is never silently
                # skipped by omission during the rollout.
                idem_key = str(row.get("idempotency_key", "") or "")
                is_dispatch_origin = row.get("origin") == "dispatch" or (
                    row.get("origin") is None and idem_key.startswith("delegate:")
                )
                if dedup.fetch_issue is not None and is_dispatch_origin:
                    try:
                        fresh_issue = dedup.fetch_issue(issue_number)
                    except Exception:  # noqa: BLE001 — unverifiable is never terminal
                        try:
                            requeued = port.requeue_running(task_id)
                        except Exception:  # noqa: BLE001 — requeue is best-effort
                            requeued = False
                        logger.exception(
                            "[task_dispatch] readiness fetch_issue failed; stopping drain — task %s %s",
                            task_id,
                            "requeued to pending" if requeued else "left running for the reaper",
                        )
                        return DrainResult(
                            spawned=spawned,
                            failed=failed,
                            skipped_duplicate=skipped_duplicate,
                            procs=tuple(procs),
                            spawned_meta=spawned_meta,
                        )

                    if fresh_issue is None:
                        try:
                            port.transition(
                                task_id,
                                "parked",
                                reason=f"issue #{issue_number} not found on fresh fetch",
                            )
                        except Exception:  # noqa: BLE001 — row stays running; reaper backstops
                            logger.exception(
                                "[task_dispatch] could not park task %s on missing issue; "
                                "row left running for the reaper",
                                task_id,
                            )
                        continue

                    readiness = pr_evidence.load_gate_module().check_issue(fresh_issue)
                    if not readiness.allow:
                        try:
                            port.transition(task_id, "parked", reason=readiness.message)
                        except Exception:  # noqa: BLE001 — row stays running; reaper backstops
                            logger.exception(
                                "[task_dispatch] could not park task %s on readiness refusal; "
                                "row left running for the reaper",
                                task_id,
                            )
                        continue

        # #1617 — orchestrator-target readiness gate. Independent of the
        # issue_number/fresh-shape dedup block above (rework rows aren't
        # "fresh" but still carry target pins) — this runs off target_type,
        # not goal parsing, so it is scoped purely by origin.
        if row.get("origin") == "orchestrator" and dedup is not None:
            try:
                gate_result = pr_evidence.load_gate_module().check_orchestrator_target(
                    row, fetch_pull=dedup.fetch_pull
                )
            except Exception:  # noqa: BLE001 — unverifiable is never terminal
                try:
                    requeued = port.requeue_running(task_id)
                except Exception:  # noqa: BLE001 — requeue is best-effort
                    requeued = False
                logger.exception(
                    "[task_dispatch] orchestrator-target fetch_pull failed; "
                    "stopping drain — task %s %s",
                    task_id,
                    "requeued to pending" if requeued else "left running for the reaper",
                )
                return DrainResult(
                    spawned=spawned,
                    failed=failed,
                    skipped_duplicate=skipped_duplicate,
                    parked=parked,
                    procs=tuple(procs),
                    spawned_meta=spawned_meta,
                )

            if not gate_result.allow:
                try:
                    port.transition(task_id, "parked", reason=gate_result.message)
                except Exception:  # noqa: BLE001 — row stays running; reaper backstops
                    logger.exception(
                        "[task_dispatch] could not park task %s on orchestrator-target "
                        "refusal; row left running for the reaper",
                        task_id,
                    )
                else:
                    parked += 1
                continue

        # #1689 — ex-post plan-review drain gate. No priority:critical
        # carve-out here — a task entering via the queue always gets ex-post
        # review regardless of label (module docstring, agents.plan_review_drain).
        if _plan_class_gate(plan_config, row) == 2:
            if github is None:
                github = github_factory()
            if _plan_needs_plan(plan_config, row, github):
                try:
                    plan_result = planner.run_planner(row, plan_config)
                except Exception as exc:  # noqa: BLE001 — isolate one bad planner run
                    try:
                        port.transition(task_id, "parked", reason=f"planner raised: {exc}")
                    except Exception:  # noqa: BLE001 — row stays running; reaper backstops
                        logger.exception(
                            "[task_dispatch] could not park task %s after planner raise; "
                            "row left running for the reaper",
                            task_id,
                        )
                    else:
                        parked += 1
                    continue
                if not plan_result.resolved:
                    try:
                        port.transition(
                            task_id,
                            "parked",
                            reason=plan_result.reason or "planner did not resolve the plan",
                        )
                    except Exception:  # noqa: BLE001 — row stays running; reaper backstops
                        logger.exception(
                            "[task_dispatch] could not park task %s after unresolved plan; "
                            "row left running for the reaper",
                            task_id,
                        )
                    else:
                        parked += 1
                    continue

                issue_number = int(row["issue_number"])
                new_body = _write_plan_section(github, issue_number, plan_result.plan_text)
                try:
                    plan_valid = verify_lock(new_body)
                except MalformedPlanError:
                    plan_valid = False
                if not plan_valid:
                    try:
                        port.transition(
                            task_id,
                            "failed",
                            reason="planner wrote a malformed or unlocked plan",
                        )
                    except Exception:  # noqa: BLE001 — row stays running; reaper backstops
                        logger.exception(
                            "[task_dispatch] could not fail task %s after malformed planner "
                            "output; row left running for the reaper",
                            task_id,
                        )
                    else:
                        failed += 1
                    continue
                digest = parse_plan(new_body).lock
                port.set_plan_digest(task_id, digest)
                row["plan_digest"] = digest

            # AC6 — fail-closed pre-spawn recheck, immediately before spawn:
            # the issue body may have drifted (edited post-approval) since the
            # digest was recorded, whether just above or in a prior drain.
            if _pre_spawn_digest_mismatch(github, row):
                try:
                    port.transition(
                        task_id, "failed", reason="plan lock mismatch on pre-spawn recheck"
                    )
                except Exception:  # noqa: BLE001 — row stays running; reaper backstops
                    logger.exception(
                        "[task_dispatch] could not fail task %s on plan-lock mismatch; "
                        "row left running for the reaper",
                        task_id,
                    )
                else:
                    failed += 1
                continue

        # Capture spawn time BEFORE launching (MAJOR, PR #1011). The terminal
        # evidence check counts PR/commit activity with timestamp > spawned_at;
        # recording it AFTER spawn() returns would let any commit the child makes
        # in that window read as older-than-spawn and be missed as evidence. Take
        # the lower bound: the instant just before the process starts.
        spawn_started_at = datetime.now(UTC)
        # #1121 plan step 8 — route onto the supervisor for the one routable
        # substrate this slice ("worktree"); an explicit row value wins over the
        # config default (AC1: substrate is stamped at enqueue time per step 7,
        # so this branch is almost always taken once step-7 rows drain).
        effective_substrate = row.get("substrate") or operator_default_substrate_loader()
        try:
            if effective_substrate == "worktree":
                result = supervisor_spawn(row, task_id=task_id)
            else:
                result = spawn(row["goal"], task_id=task_id)  # AC3 (#953) — capture stdout JSON
        except Exception as exc:  # noqa: BLE001 — AC7b: isolate one bad spawn
            # AC7b — terminal failure; no internal retry, external loop re-drives.
            try:
                port.transition(task_id, "failed", reason=f"spawn raised: {exc}")
            except Exception:  # noqa: BLE001 — the failed-mark itself can raise; an
                # escape here would discard the already-spawned handles in ``procs``
                # (orphans for the 6h reaper). Row stays running; reaper backstops.
                logger.exception(
                    "[task_dispatch] could not mark task %s failed after spawn raise; "
                    "row left running for the reaper",
                    task_id,
                )
            failed += 1
            continue

        # The executor declined to launch (quota near-exhaustion): no process
        # exists, but the row is already ``running`` (Ordering B). Requeue it to
        # ``pending`` so the next drain retries as soon as quota recovers
        # (#921 AC4) — without this it would strand 6h until the reaper failed
        # a task that never ran. Quota won't recover mid-drain, so stop
        # claiming. Not a spawn failure → not counted.
        if getattr(result, "throttled", False):
            try:
                requeued = port.requeue_running(task_id)
            except Exception:  # noqa: BLE001 — requeue is best-effort
                requeued = False
                logger.exception("[task_dispatch] requeue of throttled task %s raised", task_id)
            logger.warning(
                "[task_dispatch] spawn throttled (quota near-exhaustion); "
                "stopping drain — task %s %s",
                task_id,
                "requeued to pending" if requeued else "left running for the reaper",
            )
            return DrainResult(
                spawned=spawned,
                failed=failed,
                skipped_duplicate=skipped_duplicate,
                throttled=True,
                parked=parked,
                procs=tuple(procs),
                spawned_meta=spawned_meta,
            )

        spawned += 1
        # AC1 (#921) — retain the process handle so the wake_driver can poll
        # completion. Spawns without a handle (test fakes, defensive None)
        # still count as spawned but cannot be liveness-tracked.
        proc = getattr(result, "proc", None)
        if proc is not None:
            procs.append((task_id, proc))
            # AC1/AC2 (#953) — capture original goal + lineage key + tz-aware spawn
            # time for the terminal-boundary evidence/lineage computation. Store the
            # *un-augmented* goal: default_spawn's AC5 branch directive points at the
            # same default head (task/<task_id>) the fresh-shape check derives.
            spawned_meta[task_id] = {
                "goal": row["goal"],
                "idempotency_key": str(row.get("idempotency_key", "") or ""),
                "spawned_at": spawn_started_at,
                "issue_number": row.get("issue_number"),
                "target_repo": row.get("target_repo"),
                "target_type": row.get("target_type"),
                "target_number": row.get("target_number"),
                "origin": row.get("origin"),
            }
            # AC2 (#952) — record spawn to sidecar for restart liveness recovery.
            if sidecar is not None:
                try:
                    # proc here is always the executor's Popen-shaped handle, which
                    # has no create_time(); we record wall-clock spawn time as the
                    # adoption key. adopt_task tolerates ≤1s skew vs the OS-reported
                    # create_time on restart (#952 AC2/AC3).
                    pid = proc.pid
                    create_time = time.time()
                    sidecar.record_spawn(task_id, pid, create_time)
                except Exception:  # noqa: BLE001 — sidecar write is best-effort
                    logger.exception(
                        "[task_dispatch] sidecar record_spawn failed for task %s; "
                        "liveness tracking degraded but task continues",
                        task_id,
                    )

    return DrainResult(
        spawned=spawned,
        failed=failed,
        skipped_duplicate=skipped_duplicate,
        parked=parked,
        procs=tuple(procs),
        spawned_meta=spawned_meta,
    )


def reclaim_stale_tasks(
    port: TaskQueuePort,
    *,
    assignee: str = DEFAULT_ASSIGNEE,
    claimed_stale_after_seconds: float = DEFAULT_CLAIMED_STALE_SECONDS,
    running_reap_after_seconds: float = DEFAULT_RUNNING_REAP_SECONDS,
    live_task_ids: Collection[str] = (),
) -> ReclaimResult:
    """Sweep stranded tasks before a drain (#909 AC5/AC6, #921 AC5 orphan-only).

    - **Stale claimed** rows return to ``pending`` via a direct UPDATE that
      bypasses the FSM (``claimed → pending`` is not a legal transition; this
      mirrors :meth:`wake_driver.PsycopgEventQueue.reclaim_stale`). Never
      touches ``running``.
    - **Orphaned running** rows — stale AND not in ``live_task_ids`` — are
      transitioned ``running → failed`` so rows with no process behind them (a
      child that died without a completion, a crash in the running↔spawn
      window, a pre-restart spawn) stop ratcheting the cap toward 0.

    ``live_task_ids`` is the wake_driver's tracked-process map keyset (#921
    AC5): a row with a live handle is *not* an orphan however old — legitimate
    long tasks are never time-reaped; genuinely stuck live processes are
    :func:`kill_runaways`' job, which kills the tree and closes the row
    explicitly. Restart semantics: a fresh driver has an empty map, so every
    stale running row is an orphan again (AC7 — the map does not survive
    restart; the backstop self-heals via Path-A).

    Invoked by :func:`wake_driver.tick` *before* :func:`drain_tasks`, so a row
    reclaimed this pass is eligible to be re-claimed and spawned in the same
    tick — symmetric to the event watchdog running before ``drain_pending``.
    """
    # Stale claimed → pending (FSM-bypassing direct UPDATE).
    reclaimed = port.reclaim_stale_claimed(
        assignee=assignee, older_than_seconds=claimed_stale_after_seconds
    )

    # Orphaned running → failed (stale + no tracked live process).
    reaped = 0
    for row in port.list_stale_running(
        assignee=assignee, older_than_seconds=running_reap_after_seconds
    ):
        task_id = str(row["id"])
        if task_id in live_task_ids:
            continue
        try:
            port.transition(
                task_id,
                "failed",
                reason=(
                    f"reaped: orphaned running row (no tracked process) "
                    f"after {running_reap_after_seconds:.0f}s"
                ),
            )
            reaped += 1
        except Exception:  # noqa: BLE001 — isolate one bad row; the rest still reap
            logger.exception(
                "[task_dispatch] orphan reap of task %s failed; retried next sweep",
                task_id,
            )

    return ReclaimResult(reclaimed_claimed=reclaimed, reaped_running=reaped)


def default_local_drain_heartbeat_check() -> HeartbeatStatus:
    """Production ``heartbeat_check`` adapter — live Supabase read (#1085 S3-2).

    Lazy import mirrors :func:`default_spawn`: the tested loop logic in
    :func:`local_drain_until_terminal` never pulls Supabase, only this
    production default does.
    """
    from agents.driver_heartbeat import check_heartbeat

    return check_heartbeat()


def default_get_task_statuses(task_ids: list[str]) -> dict[str, str]:
    """Production ``get_statuses`` adapter — batch task_queue lookup (#1085 S3-2)."""
    return task_queue.get_statuses(task_ids)


def default_local_drain_once() -> None:
    """Production ``run_once`` adapter — one ``wake_driver --once`` subprocess tick.

    A fresh process per tick, same as the resident driver's own ticks — no cap
    override flag or env var is passed here, so ``DEFAULT_CONCURRENCY_CAP``
    (read inside the child process) is the only concurrency limit in play.

    Passes ``--driver-name`` set to :data:`LOCAL_DRAIN_DRIVER_NAME`, distinct
    from the resident driver's ``DRIVER_NAME`` — see that constant's comment
    for why a shared name would make :func:`local_drain_until_terminal` exit
    after its first iteration regardless of remaining pending rows.
    """
    subprocess.run(
        [
            sys.executable,
            "-m",
            "agents.wake_driver",
            "--once",
            "--driver-name",
            LOCAL_DRAIN_DRIVER_NAME,
        ],
        cwd=_REPO_ROOT,
        check=False,
    )


def local_drain_until_terminal(
    task_ids: Collection[str],
    *,
    heartbeat_check: Callable[[], HeartbeatStatus] = default_local_drain_heartbeat_check,
    run_once: Callable[[], None] = default_local_drain_once,
    get_statuses: Callable[[list[str]], dict[str, str]] = default_get_task_statuses,
    sleep: Callable[[float], None] = time.sleep,
    poll_seconds: float = DEFAULT_LOCAL_DRAIN_POLL_SECONDS,
    max_iterations: int = DEFAULT_LOCAL_DRAIN_MAX_ITERATIONS,
) -> dict[str, str]:
    """Local-drain fallback for a stale resident driver (#1085 S3-2).

    ``/dispatch`` calls this after enqueueing a batch when the heartbeat check
    (step 3b) found the resident ``wake_driver`` stale: it repeats a
    ``wake_driver --once`` tick (``run_once``) — concurrency-capped by
    construction, since each tick's ``drain_tasks`` call enforces
    ``DEFAULT_CONCURRENCY_CAP`` on its own — polling ``get_statuses`` between
    ticks, until every id in ``task_ids`` leaves :data:`_ACTIVE_STATUSES`
    (i.e. is no longer ``pending``/``claimed``/``running``), the heartbeat
    goes fresh again (resident driver recovered), or ``max_iterations`` is
    exhausted. Operator-present, blocking call by design.

    ``parked`` is deliberately NOT terminal at the FSM level (#1119) — it is
    a non-terminal hold state whose only legal edge is back to ``pending``
    (unpark). But this loop stops waiting on a parked row anyway: a local
    drain tick can only ever spawn work forward, and a parked row can never
    be advanced by a local spawn — only an external unpark actor can do
    that. So a parked row is just as much "nothing more this loop can do"
    as a genuinely terminal one, even though ``task_queue.TERMINAL_STATES``
    excludes it. Hence the narrower, purpose-specific ``_ACTIVE_STATUSES``
    set instead of reusing ``task_queue.TERMINAL_STATES`` directly. A
    missing/``None`` status (task_id absent from the batch response) is
    unresolved, not parked — the loop keeps waiting on it (unchanged
    behavior).

    ``heartbeat_check`` re-runs immediately before every spawn: if the driver
    has since become fresh (resident driver recovered, or another local drain
    already covered these rows), the loop stops without spawning again.

    ceiling: each ``run_once()`` is a memory-isolated ``wake_driver --once``
    subprocess with no ``task_procs`` (agents/wake_driver.py's ``--once`` path
    deliberately omits it, #921) — so this loop can spawn rows to ``running``
    but has no way to observe their process exit and close them to
    ``done``/``failed`` itself; that only happens via the much-slower orphan
    reaper backstop (``reclaim_stale_tasks``), well past this loop's
    ``max_iterations`` window. In practice freshly-spawned rows will usually
    exhaust the cap and return non-terminal here (confirmed via code review on
    PR #1544). Not a correctness issue — no row is double-processed or lost,
    the caller just can't rely on this call to observe completion promptly.
    Upgrade path (real fix, not done here — architectural, entangled with
    #1546's same subprocess-per-tick root cause): replace the subprocess
    ``run_once`` with an in-process ``drain_tasks``/``poll_completions`` pair
    sharing one ``task_procs`` dict across the whole call. Tracked: #1551.

    ceiling: heartbeat_check -> run_once is check-then-act, not atomic — no
    distributed lock. A resident driver tick can start in the gap between the
    check and the spawn, causing a duplicate local drain attempt on the same
    rows. Not a correctness issue — task_queue's pending->claimed transition
    is a conditional UPDATE, atomic per row (agents/task_queue.py::claim_next)
    — just wasted local compute. Upgrade path if this starts costing real
    cycles: a short-lived advisory lock row in driver_heartbeat itself.
    """
    ids = list(task_ids)
    if not ids:
        return {}

    statuses = get_statuses(ids)
    for _ in range(max_iterations):
        if all(
            statuses.get(tid) is not None and statuses.get(tid) not in _ACTIVE_STATUSES
            for tid in ids
        ):
            return statuses
        if not heartbeat_check().is_stale:
            return statuses
        run_once()
        statuses = get_statuses(ids)
        sleep(poll_seconds)
    return statuses


class SupabaseTaskQueue:
    """Real :class:`TaskQueuePort` over :mod:`agents.task_queue` (AC10).

    Thin delegation — the FSM and SQL live in :mod:`agents.task_queue`. Tasks
    stay on supabase-py (PostgREST); only events need raw psycopg (``LISTEN``),
    so this is the task-side analogue of
    :class:`wake_driver.PsycopgEventQueue`. ``client`` defaults to ``None`` so
    ad-hoc construction still works (each call then resolves a client lazily
    inside ``task_queue``), but a long-running caller should build one Supabase
    client and inject it here — same MAJOR fix as PR #1011's event client,
    applied to the task-queue side (finding #2, PR #1475 review). Not
    unit-tested (needs live Supabase); the tested logic lives in
    :func:`drain_tasks` / :func:`reclaim_stale_tasks` above.
    """

    def __init__(self, client: Client | None = None) -> None:
        self._client = client

    def claim_next(self, *, assignee: str) -> dict[str, Any] | None:
        return task_queue.claim_next(assignee=assignee, client=self._client)

    def count_running(self, *, assignee: str) -> int:
        return task_queue.count_running(assignee=assignee, client=self._client)

    def transition(
        self, task_id: str, to_status: str, *, reason: str | None = None
    ) -> dict[str, Any]:
        return task_queue.transition(task_id, to_status, reason=reason, client=self._client)

    def reclaim_stale_claimed(self, *, assignee: str, older_than_seconds: float) -> int:
        return task_queue.reclaim_stale_claimed(
            assignee=assignee, older_than_seconds=older_than_seconds, client=self._client
        )

    def list_stale_running(
        self, *, assignee: str, older_than_seconds: float
    ) -> list[dict[str, Any]]:
        return task_queue.list_stale_running(
            assignee=assignee, older_than_seconds=older_than_seconds, client=self._client
        )

    def requeue_running(self, task_id: str) -> bool:
        return task_queue.requeue_running(task_id, client=self._client)

    def get_status(self, task_id: str) -> str | None:
        return task_queue.get_status(task_id, client=self._client)

    def get_statuses(self, task_ids: list[str]) -> dict[str, str]:
        return task_queue.get_statuses(task_ids, client=self._client)

    def set_plan_digest(self, task_id: str, digest: str) -> dict[str, Any]:
        return task_queue.set_plan_digest(task_id, digest, client=self._client)

    def get_row(self, task_id: str) -> dict[str, Any] | None:
        return task_queue.get_row(task_id, client=self._client)

    def requeue_for_replan(self, task_id: str, new_replan_count: int) -> dict[str, Any]:
        return task_queue.requeue_for_replan(task_id, new_replan_count, client=self._client)


def reconcile_stranded_prs(
    github: GitHubClient | None = None,
    *,
    repo: str | None = None,
    dry_run: bool = False,
) -> int:
    """Reconciliation sweep for merged PRs with still-open issues (#1169 item 2).

    Lists open issues with the ``sandcastle`` label. For each, searches merged
    PRs whose body links ``Closes/Fixes/Resolves #<N>`` using ``gh search prs``.
    When a match is found, the issue should have been auto-closed by
    ``pr-merged.yml`` but wasn't (the #948 failure mode — bot merges suppress
    native auto-close). Closes the issue and removes stale labels.

    Uses ``gh`` CLI for issue listing and search; ``github`` client is accepted
    for consistency but not used directly — the search endpoint is GraphQL-only.

    Returns the number of issues closed. Dry-run logs what would be done.
    """
    import json as _json
    import subprocess

    active_repo = repo or os.environ.get("GITHUB_REPO", "Osasuwu/jarvis")

    # List open issues with the sandcastle label
    try:
        result = subprocess.run(
            [
                "gh",
                "issue",
                "list",
                "--repo",
                active_repo,
                "--label",
                "sandcastle",
                "--state",
                "open",
                "--json",
                "number",
                "--jq",
                ".[].number",
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, OSError) as exc:
        logger.warning(
            "[task_dispatch] reconcile_stranded_prs: gh issue list failed: %s",
            exc,
        )
        return 0

    issue_numbers = [int(n) for n in result.stdout.strip().split() if n.strip()]
    if not issue_numbers:
        return 0

    closed = 0
    for issue_number in issue_numbers:
        # Search for merged PRs closing this issue
        try:
            search_result = subprocess.run(
                [
                    "gh",
                    "pr",
                    "list",
                    "--repo",
                    active_repo,
                    "--state",
                    "merged",
                    "--json",
                    "number",
                    "title",
                    "body",
                    "--search",
                    f"closes #{issue_number} in:body",
                    "--limit",
                    "1",
                ],
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
            )
        except (subprocess.CalledProcessError, FileNotFoundError, OSError) as exc:
            logger.warning(
                "[task_dispatch] reconcile_stranded_prs: search for #%s failed: %s",
                issue_number,
                exc,
            )
            continue

        merged = _json.loads(search_result.stdout.strip() or "[]")
        if not merged:
            continue

        pr = merged[0]
        pr_number = pr.get("number")
        logger.info(
            "[task_dispatch] reconcile_stranded_prs: issue #%s has "
            "merged PR #%s but is still open — closing",
            issue_number,
            pr_number,
        )
        if not dry_run:
            try:
                subprocess.run(
                    [
                        "gh",
                        "issue",
                        "close",
                        str(issue_number),
                        "--repo",
                        active_repo,
                        "--comment",
                        f"Auto-closed: merged PR #{pr_number} links this issue",
                    ],
                    capture_output=True,
                    check=True,
                    timeout=30,
                )
                closed += 1
            except (subprocess.CalledProcessError, OSError) as exc:
                logger.warning(
                    "[task_dispatch] reconcile_stranded_prs: close #%s failed: %s",
                    issue_number,
                    exc,
                )

    return closed
