"""Task dispatcher agent — Pillar 7 Sprint 2 first federation jurisdiction (issue #298, S2-3).

Wires together every Sprint 2 primitive:

- S2-0 safety gate (``agents/safety.py``) — identity/idempotency/audit.
- S2-1 task_queue (``mcp-memory/schema.sql``) — FSM: pending → dispatched | escalated | rejected.
- S2-2 usage probe (``agents/usage_probe.py``) — budget check before dispatch.
- S2-4 escalation triggers (``agents/escalation.py``) — stale / drift / limit / conflict / pattern.
- S2-5 APScheduler (``agents/scheduler.py``) — run-loop engine.

Graph::

    START → poll_queue ──(empty)──────────────────────────────→ END
              │
              ▼
           evaluate ──(escalate)→ escalate ──→ END
              │
              ▼
           dispatch ─────────────────────────→ END

One row per tick by design: the dispatcher is the first agent that spawns
external subprocesses, and keeping the safety surface narrow (exactly one
``claude`` process per tick at most) beats throughput in v1.

**Subscription auth.** Claude Max billing trap (#37686): if
``ANTHROPIC_API_KEY`` is set in the dispatcher's environment, the spawned
``claude`` subprocess would bill the API account instead of the Max
subscription. :func:`_sanitize_env` strips every known variant before
``Popen``; the integration test asserts the leak path is closed.

**Fire-and-forget.** Per the issue body: v1 launches the subprocess and
returns. Result collection is out of scope — the child session writes
its own ``audit_log`` rows as it runs. A failed spawn surfaces as an
``audit_log`` row with ``outcome='failure:<ExceptionType>'``.
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import os
import shutil
import subprocess
from datetime import UTC, datetime
from typing import Any, TypedDict

from dotenv import load_dotenv

from agents import escalation, safety, supabase_client, usage_probe
from agents.config import load_config

logger = logging.getLogger(__name__)

# Identity stamped onto every audit_log / events.source row we write. Must
# match the constants in usage_probe and escalation so probe queries line
# up with the rows this module produces.
AGENT_ID = "task-dispatcher"
TOOL_NAME = "claude_cli"
DISPATCH_ACTION = "dispatch"

# Env vars that must not reach the Claude subprocess. Keeping them here
# (not on a config surface) means a future Anthropic env name — likely
# shipped as a breaking rename — turns into a one-line edit rather than a
# billing incident.
_SENSITIVE_ENV_KEYS: frozenset[str] = frozenset(
    {
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "CLAUDE_API_KEY",
    }
)

# Permission spec for the spawned ``claude -p`` session (#372, #378). Without
# these flags, headless Claude hangs waiting for approval that no operator
# can give. Design: ``acceptEdits`` auto-approves Write/Edit (matches
# dispatcher's primary shape — "make the change"), plus a narrow allowlist
# of read-only and safely-namespaced tools that ``acceptEdits`` does not
# cover. Widen this list only with a design note; do NOT switch to
# ``bypassPermissions`` — that defeats the Sprint 2 safety layering.
#
# Security rationale (#378):
# - Dropped: Bash(python:*) — arbitrary code escape hatch. If a task needs
#   to run a script, agent can invoke Edit + commit; CI tests for us.
# - Replaced: Bash(gh:*) with scoped read/create verbs only. Removed:
#   destructive verbs (merge --admin, repo delete, api DELETE).
_SPAWN_PERMISSION_MODE = "acceptEdits"
_SPAWN_ALLOWED_TOOLS = (
    "Read",
    "Glob",
    "Grep",
    "TodoWrite",
    "Bash(git:*)",
    "Bash(gh pr view:*)",
    "Bash(gh pr create:*)",
    "Bash(gh pr list:*)",
    "Bash(gh issue view:*)",
    "Bash(gh issue create:*)",
    "Bash(gh issue list:*)",
    "Bash(gh issue comment:*)",
    "Bash(gh api repos/*/issues:*)",
    "Bash(gh api repos/*/pulls:*)",
    "Bash(pytest:*)",
    "Bash(npm:*)",
)

# How many recent dispatches to scan for pattern-repeat detection. Large
# enough that a run of 3 same-goal tasks plus the pending one is visible;
# small enough that the Supabase query stays cheap on every tick.
_RECENT_LOOKBACK = 10

# Hardcoded ceiling on how many in-flight ``dispatched`` peers the
# cross-task-conflict check considers. If more than this are in flight,
# the owner is already behind and a new dispatch would only pile on.
_ACTIVE_DISPATCHED_SCAN = 50


class DispatcherState(TypedDict):
    """Graph state for one dispatch tick.

    ``row`` carries the chosen ``task_queue`` row through the graph;
    nodes mutate a copy and return it, so the checkpointed snapshot
    reflects the actual dispatch decision. ``_check`` (the escalation
    outcome) is tucked onto ``row`` so the TypedDict itself can stay
    primitive — LangGraph pickles the state between nodes and typed
    dataclasses on the surface make that serialization fragile.
    """

    dry_run: bool
    row: dict[str, Any] | None
    outcome: str
    reason: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


# Documented Windows install locations to probe when neither override, env
# var, nor PATH lookup yields a binary. Templates expand against ``os.environ``
# so absent vars (e.g. running under a service account) are skipped silently.
# Order matters: official installer first, then common alt locations seen in
# the wild (`.local/bin/claude.exe`, npm shim, pipx).
_CLAUDE_DEFAULT_WINDOWS_PATHS: tuple[str, ...] = (
    r"{LOCALAPPDATA}\Programs\claude\claude.exe",
    r"{USERPROFILE}\.local\bin\claude.exe",
    r"{APPDATA}\npm\claude.exe",
)


def _resolve_claude_binary(override: str | None = None) -> str:
    """Resolve the absolute path to the ``claude`` executable.

    Resolution chain — earlier sources win and are validated against the
    filesystem before being returned:

    1. ``override`` argument — for tests and programmatic callers that need
       to inject a known path. None / empty string skips this layer.
    2. ``JARVIS_CLAUDE_BIN`` env var — operator override for unattended
       contexts (NSSM service, cron, CI) where PATH is sparse. Set via
       ``nssm set jarvis-scheduler AppEnvironmentExtra JARVIS_CLAUDE_BIN=...``.
    3. :func:`shutil.which` — works in interactive shells where ``claude``
       is on the user PATH but breaks under ``LocalSystem`` (issue #385,
       7× ``failure:FileNotFoundError`` over 24 h before this fix).
    4. Documented Windows install paths — covers official and common alt
       installs without forcing the operator to set an env var on every box.

    Raises :class:`FileNotFoundError` when nothing resolves to an existing
    file, with a message that lists each step that was tried so operators
    can see at a glance which override slot to fill.
    """
    if override:
        if os.path.exists(override):
            return override
        raise FileNotFoundError(
            f"claude binary override does not exist: {override!r}"
        )

    env_path = os.environ.get("JARVIS_CLAUDE_BIN")
    if env_path:
        if os.path.exists(env_path):
            return env_path
        raise FileNotFoundError(
            f"JARVIS_CLAUDE_BIN points to a missing file: {env_path!r}"
        )

    found = shutil.which("claude")
    if found:
        return found

    if os.name == "nt":
        for tmpl in _CLAUDE_DEFAULT_WINDOWS_PATHS:
            try:
                candidate = tmpl.format(**os.environ)
            except KeyError:
                continue
            if os.path.exists(candidate):
                return candidate

    tried = ["override arg", "JARVIS_CLAUDE_BIN", "shutil.which('claude')"]
    if os.name == "nt":
        tried.append(f"Windows defaults {_CLAUDE_DEFAULT_WINDOWS_PATHS}")
    raise FileNotFoundError(
        "claude binary not found. Tried: "
        + ", ".join(tried)
        + ". Set JARVIS_CLAUDE_BIN to the absolute path; under NSSM, "
        "'nssm set jarvis-scheduler AppEnvironmentExtra JARVIS_CLAUDE_BIN=...'."
    )


def _sanitize_env(env: dict[str, str] | None = None) -> dict[str, str]:
    """Return ``env`` (defaults to ``os.environ``) minus API-billing keys.

    Claude Max auth lives in the CLI's on-disk session (``~/.claude/``),
    not in an env var; the subprocess inherits it automatically when we
    don't poison the env with an API key.
    """
    source = env if env is not None else os.environ
    return {k: v for k, v in source.items() if k not in _SENSITIVE_ENV_KEYS}


def _hash_scope_files(scope_files: list[str] | tuple[str, ...]) -> str:
    """Deterministic scope-files hash for drift detection.

    Matches the approval-time hashing convention S2-1 expects. Sort the
    list so "files reordered" doesn't read as "files changed"; newline-join
    so a glob that grew by one file ``['a']`` vs ``['a', 'b']`` produces
    different hashes (concatenation ``'ab'`` vs ``'a'`` would too, but
    a separator makes the invariant human-readable).
    """
    normalized = "\n".join(sorted(scope_files or []))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


# ---------------------------------------------------------------------------
# Graph nodes
# ---------------------------------------------------------------------------


def poll_queue_node(
    state: DispatcherState,
    *,
    client: Any | None = None,
) -> dict[str, Any]:
    """Fetch the oldest ``pending`` row with ``auto_dispatch=True``.

    Order by ``approved_at`` ascending — oldest approval goes first so
    nothing gets perpetually starved. Non-auto rows stay pending forever
    (owner drives them manually); the dispatcher never touches them.
    """
    cli = client or supabase_client.get_client()
    result = (
        cli.table("task_queue")
        .select("*")
        .eq("status", "pending")
        .eq("auto_dispatch", True)
        .order("approved_at", desc=False)
        .limit(1)
        .execute()
    )
    rows = result.data or []
    if not rows:
        return {"row": None, "outcome": "no_pending", "reason": "queue empty"}
    return {"row": rows[0]}


def evaluate_node(
    state: DispatcherState,
    *,
    client: Any | None = None,
) -> dict[str, Any]:
    """Build escalation context (probe + peers + recent history) and run checks.

    :func:`escalation.check_all` priority-orders the five triggers and
    returns the first one that fires — surface one actionable reason,
    never a pile of five. The outcome is stashed on ``row['_check']`` so
    :func:`evaluate_branch` can route without re-running checks.
    """
    row = dict(state.get("row") or {})
    cli = client or supabase_client.get_client()

    reading = usage_probe.read_usage()

    own_id = row.get("id")
    active_q = (
        cli.table("task_queue")
        .select("id, scope_files")
        .eq("status", "dispatched")
        .limit(_ACTIVE_DISPATCHED_SCAN)
    )
    if own_id is not None:
        active_q = active_q.neq("id", own_id)
    active_rows = active_q.execute().data or []

    recent_rows = (
        cli.table("task_queue")
        .select("id, goal, dispatched_at")
        .eq("status", "dispatched")
        .order("dispatched_at", desc=True)
        .limit(_RECENT_LOOKBACK)
        .execute()
        .data
        or []
    )

    ctx = escalation.EscalationContext(
        current_scope_hash=_hash_scope_files,
        usage_reading=reading,
        active_dispatched_rows=active_rows,
        recent_successful_dispatches=recent_rows,
    )
    check = escalation.check_all(row, ctx)
    row["_check"] = check
    return {"row": row}


def evaluate_branch(state: DispatcherState) -> str:
    """Conditional edge: ``escalate`` if any trigger fired, else ``dispatch``."""
    row = state.get("row") or {}
    check = row.get("_check")
    if check is not None and getattr(check, "should_escalate", False):
        return "escalate"
    return "dispatch"


def escalate_node(
    state: DispatcherState,
    *,
    client: Any | None = None,
) -> dict[str, Any]:
    """Persist the escalation via :func:`escalation.escalate`."""
    row = state.get("row") or {}
    check = row.get("_check")
    if check is None or not check.should_escalate:
        # Defensive — evaluate_branch should have sent us to dispatch. If
        # something's wrong, record the anomaly as a no-op and move on.
        return {"outcome": "blocked", "reason": "evaluate produced no escalation"}
    escalation.escalate(row, check, client=client)
    trigger_name = check.trigger.value if check.trigger is not None else "unknown"
    return {"outcome": "escalated", "reason": trigger_name}


def dispatch_node(
    state: DispatcherState,
    *,
    client: Any | None = None,
    popen: Any = None,
) -> dict[str, Any]:
    """Spawn the Claude subprocess with sanitized env, flip row to ``dispatched``.

    ``popen`` is injectable so integration tests can capture the env dict
    without shelling out to a real ``claude`` binary; production wiring
    goes through :func:`subprocess.Popen` directly.
    """
    row = state.get("row") or {}
    dry_run = bool(state.get("dry_run", False))
    cli = client or supabase_client.get_client()

    row_id = row.get("id")
    goal = row.get("goal") or ""
    target = f"task_queue:{row_id}" if row_id is not None else "task_queue:unknown"
    # Reuse the row's idempotency_key if the approval flow put one there
    # (it should — task_queue.idempotency_key is NOT NULL); otherwise
    # derive one from the agent/action/target/scope tuple.
    idem = row.get("idempotency_key") or safety.idempotency_key(
        AGENT_ID,
        DISPATCH_ACTION,
        target,
        row.get("approved_scope_hash"),
    )

    spawn = popen or subprocess.Popen

    if dry_run:
        safety.audit(
            agent_id=AGENT_ID,
            tool_name=TOOL_NAME,
            action=DISPATCH_ACTION,
            target=target,
            tier=safety.Tier.AUTO,
            outcome="dry_run",
            idempotency_key=idem,
        )
        return {"outcome": "dry_run_dispatched", "reason": f"idem={idem[:12]}"}

    try:
        env = _sanitize_env()
        argv = [
            _resolve_claude_binary(),
            "-p",
            goal,
            "--permission-mode",
            _SPAWN_PERMISSION_MODE,
            "--allowedTools",
            *_SPAWN_ALLOWED_TOOLS,
        ]
        spawn(
            argv,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )
    except Exception as exc:  # noqa: BLE001 — audit must capture cause
        safety.audit(
            agent_id=AGENT_ID,
            tool_name=TOOL_NAME,
            action=DISPATCH_ACTION,
            target=target,
            tier=safety.Tier.AUTO,
            outcome=f"failure:{type(exc).__name__}",
            idempotency_key=idem,
            error=str(exc),
        )
        return {"outcome": "failed", "reason": f"{type(exc).__name__}: {exc}"}

    safety.audit(
        agent_id=AGENT_ID,
        tool_name=TOOL_NAME,
        action=DISPATCH_ACTION,
        target=target,
        tier=safety.Tier.AUTO,
        outcome="success",
        idempotency_key=idem,
    )

    if row_id is not None:
        (
            cli.table("task_queue")
            .update({"status": "dispatched", "dispatched_at": _now_iso()})
            .eq("id", row_id)
            .execute()
        )

    return {"outcome": "dispatched", "reason": f"idem={idem[:12]}"}


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------


def build_graph(
    *,
    client: Any | None = None,
    popen: Any = None,
) -> Any:
    """Compose the dispatcher graph.

    ``client`` / ``popen`` forward through to every node, so integration
    tests can inject stubs at a single seam without threading kwargs
    through each call site.
    """
    from langgraph.graph import END, START, StateGraph

    graph: StateGraph = StateGraph(DispatcherState)

    def _poll(state: DispatcherState) -> dict[str, Any]:
        return poll_queue_node(state, client=client)

    def _eval(state: DispatcherState) -> dict[str, Any]:
        return evaluate_node(state, client=client)

    def _escalate(state: DispatcherState) -> dict[str, Any]:
        return escalate_node(state, client=client)

    def _dispatch(state: DispatcherState) -> dict[str, Any]:
        return dispatch_node(state, client=client, popen=popen)

    graph.add_node("poll_queue", _poll)
    graph.add_node("evaluate", _eval)
    graph.add_node("escalate", _escalate)
    graph.add_node("dispatch", _dispatch)

    graph.add_edge(START, "poll_queue")

    def _after_poll(state: DispatcherState) -> str:
        return "evaluate" if state.get("row") else "end"

    graph.add_conditional_edges(
        "poll_queue",
        _after_poll,
        {"evaluate": "evaluate", "end": END},
    )
    graph.add_conditional_edges(
        "evaluate",
        evaluate_branch,
        {"escalate": "escalate", "dispatch": "dispatch"},
    )
    graph.add_edge("escalate", END)
    graph.add_edge("dispatch", END)

    return graph


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------


def run(
    thread_id: str = AGENT_ID,
    *,
    dry_run: bool = False,
    client: Any | None = None,
    popen: Any = None,
    checkpointer: Any | None = None,
) -> dict[str, Any]:
    """Execute one dispatch tick.

    Returns the final state so callers (scheduler hook, integration test,
    CLI) can inspect ``outcome`` / ``reason`` without re-querying the DB.

    ``checkpointer`` is injectable for tests; production wiring opens a
    :class:`PostgresSaver` from the shared Postgres URL used by every
    persistent agent.
    """
    initial: DispatcherState = {
        "dry_run": dry_run,
        "row": None,
        "outcome": "",
        "reason": "",
    }

    if checkpointer is not None:
        app = build_graph(client=client, popen=popen).compile(checkpointer=checkpointer)
        config = {"configurable": {"thread_id": thread_id}}
        result = app.invoke(initial, config=config)
        return dict(result)

    from langgraph.checkpoint.postgres import PostgresSaver

    cfg = load_config()
    with PostgresSaver.from_conn_string(cfg.postgres_url) as saver:
        saver.setup()
        app = build_graph(client=client, popen=popen).compile(checkpointer=saver)
        config = {"configurable": {"thread_id": thread_id}}
        result = app.invoke(initial, config=config)
        logger.info(
            "[dispatcher] tick outcome=%s reason=%s",
            result.get("outcome"),
            result.get("reason"),
        )
        return dict(result)


def _scheduled_tick() -> None:
    """Module-level job target for APScheduler.

    Lives at module scope (not a closure) so the SQLAlchemy jobstore can
    pickle the reference and restore it across restarts.
    """
    dry_run = os.environ.get("TASK_DISPATCHER_DRY_RUN", "0") == "1"
    try:
        run(AGENT_ID, dry_run=dry_run)
    except Exception as exc:  # noqa: BLE001 — tick failures must not tear scheduler down
        logger.exception("[dispatcher] tick failed: %s", exc)


def register(
    handle: Any,
    *,
    dry_run: bool = False,
    interval_seconds: int = 60,
    jitter_seconds: int | None = None,
) -> Any:
    """Register the dispatcher as an APScheduler job on ``handle``.

    ``dry_run`` is persisted via an env var so :func:`_scheduled_tick`
    picks it up at fire time — APScheduler's jobstore pickles the job
    target, and a closure carrying ``dry_run`` would bloat the persisted
    row and couple the stored job to this process's Python instance.

    ``jitter_seconds=None`` means "use scheduler default"; pass an int to
    override when multiple devices run the same agent and need to avoid
    lockstep DB contention.
    """
    from agents.scheduler import register_agent

    os.environ["TASK_DISPATCHER_DRY_RUN"] = "1" if dry_run else "0"
    kwargs: dict[str, Any] = {
        "agent_id": AGENT_ID,
        "fn": _scheduled_tick,
        "interval_seconds": interval_seconds,
    }
    if jitter_seconds is not None:
        kwargs["jitter_seconds"] = jitter_seconds
    return register_agent(handle, **kwargs)


def main() -> int:
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--thread",
        default=AGENT_ID,
        help=f"LangGraph thread_id (default: {AGENT_ID})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Full graph traversal, no external subprocess launch.",
    )
    args = parser.parse_args()
    result = run(args.thread, dry_run=args.dry_run)
    print(f"[dispatcher] outcome={result.get('outcome')} reason={result.get('reason')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
