"""End-to-end integration test for the dispatcher flow (issue #301, S2-6).

Validates that S2-0..S2-5 primitives compose correctly:

    approved task_queue row
      -> dispatcher.run (poll → evaluate → dispatch|escalate)
      -> real Supabase writes (task_queue update + audit_log + events)
      -> mocked subprocess boundary (no real ``claude -p`` spawn in CI)

**Opt-in** via ``AGENTS_E2E=1`` — CI lacks live Supabase/Postgres and we
deliberately don't mock those because the whole point is to prove the
bridge works. Everything *except* the subprocess boundary runs for real.

Run::

    AGENTS_E2E=1 pytest tests/test_agents_dispatcher_e2e.py -v

Hermetic cleanup: every test tags rows with a fresh UUID marker (embedded
in ``goal``) and deletes matching rows in teardown. The marker also
propagates into ``audit_log.target`` and the escalation ``events`` row's
payload so the sweep catches everything this test run wrote.
"""

from __future__ import annotations

import hashlib
import os
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("AGENTS_E2E") != "1",
    reason="opt-in integration suite — set AGENTS_E2E=1 to run",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _hash_scope(files: list[str]) -> str:
    """Matches ``agents.dispatcher._hash_scope_files`` — duplicated here so
    the test can seed a row with a valid ``approved_scope_hash`` without
    importing dispatcher internals that change shape over time."""
    return hashlib.sha256("\n".join(sorted(files)).encode("utf-8")).hexdigest()


def _insert_queue_row(
    cli: Any,
    *,
    marker: str,
    goal_prefix: str,
    approved_at: datetime | None = None,
    scope_files: list[str] | None = None,
) -> dict[str, Any]:
    """Insert a real row into ``task_queue`` and return what Supabase stored.

    ``marker`` is embedded in both ``goal`` and ``idempotency_key`` so
    teardown can sweep without hitting rows from other runs.
    """
    files = scope_files or [f"agents/dispatcher.py#{marker}"]
    payload = {
        "goal": f"{goal_prefix} [{marker}]",
        "scope_files": files,
        "approved_at": (approved_at or datetime.now(UTC)).isoformat(),
        "approved_by": "e2e-test",
        "approved_scope_hash": _hash_scope(files),
        "auto_dispatch": True,
        "status": "pending",
        "idempotency_key": f"e2e-{marker}",
    }
    inserted = cli.table("task_queue").insert(payload).execute().data
    assert inserted, f"task_queue insert returned no data for marker={marker!r}"
    return inserted[0]


def _delete_by_marker(marker: str) -> None:
    """Best-effort teardown — sweep every table this test writes to."""
    from agents.supabase_client import get_client

    try:
        cli = get_client()
        cli.table("task_queue").delete().like("goal", f"%{marker}%").execute()
        cli.table("audit_log").delete().like("target", f"%{marker}%").execute()
        # events.payload is JSONB — Supabase's ``.like`` won't traverse it,
        # so filter on title which we control at insert time via the
        # escalation helper's "Dispatcher escalated task <id>: <trigger>"
        # pattern. We match on row id instead for precision.
        cli.table("events").delete().like("title", f"%{marker}%").execute()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def marker() -> str:
    tag = f"dispatcher-e2e-{uuid.uuid4()}"
    yield tag
    _delete_by_marker(tag)


@pytest.fixture
def captured_popen(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Mock the subprocess boundary — no real ``claude`` spawn in CI.

    Replacing ``agents.dispatcher.subprocess.Popen`` rather than passing
    a fake via kwargs keeps the test on the same call path production
    uses. The ``popen`` parameter on ``dispatch_node`` exists for unit
    tests; E2E should exercise the default seam.
    """
    calls: list[dict[str, Any]] = []

    class _Handle:
        pid = 424242

        def poll(self) -> None:
            return None

    def _popen(argv: list[str], **kwargs: Any) -> Any:
        calls.append({"argv": list(argv), "env": dict(kwargs.get("env") or {}), **kwargs})
        return _Handle()

    from agents import dispatcher

    monkeypatch.setattr(dispatcher.subprocess, "Popen", _popen)
    return calls


@pytest.fixture
def thread_id() -> str:
    return f"dispatcher-e2e-{uuid.uuid4()}"


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_happy_path_dispatches_and_audits(
    monkeypatch: pytest.MonkeyPatch,
    marker: str,
    captured_popen: list[dict[str, Any]],
    thread_id: str,
) -> None:
    """Approved row with healthy budget → dispatched + audit row + no API key leak."""
    pytest.importorskip("langgraph")
    pytest.importorskip("supabase")

    from agents import dispatcher, usage_probe
    from agents.supabase_client import get_client
    from agents.usage_probe import UsageReading

    # Healthy probe reading — keep escalation off the happy path.
    healthy = UsageReading(
        limit_window=timedelta(hours=5),
        used=5,
        total=100,
        reset_at=datetime.now(UTC),
        near_exhaustion=False,
    )
    monkeypatch.setattr(usage_probe, "read_usage", lambda: healthy)
    monkeypatch.setattr(dispatcher.usage_probe, "read_usage", lambda: healthy)

    # Simulate the billing-trap scenario: operator has ANTHROPIC_API_KEY
    # in their environment when running the dispatcher. The subprocess
    # must not inherit it.
    monkeypatch.setenv("ANTHROPIC_API_KEY", f"leak-sentinel-{marker}")

    cli = get_client()
    seeded = _insert_queue_row(cli, marker=marker, goal_prefix="e2e happy")
    row_id = seeded["id"]

    result = dispatcher.run(thread_id, dry_run=False)
    assert result["outcome"] == "dispatched", f"expected dispatched, got {result!r}"

    # Subprocess boundary was hit exactly once with claude -p <goal>.
    assert len(captured_popen) == 1
    call = captured_popen[0]
    assert call["argv"][0:2] == ["claude", "-p"]
    assert marker in call["argv"][2]  # goal contains our marker

    # Billing-trap leak guard: parent env had the key, child env must not.
    assert "ANTHROPIC_API_KEY" not in call["env"], (
        "billing-trap leak — ANTHROPIC_API_KEY reached subprocess env"
    )

    # Row transitioned to dispatched.
    row = (
        cli.table("task_queue")
        .select("status, dispatched_at")
        .eq("id", row_id)
        .limit(1)
        .execute()
        .data
    )
    assert row, f"seeded row {row_id} disappeared"
    assert row[0]["status"] == "dispatched"
    assert row[0]["dispatched_at"] is not None

    # audit_log has our dispatch with correct agent_id + nested idempotency/tier.
    # ``tier`` and ``idempotency_key`` live inside ``details`` (JSONB) — see
    # agents.safety._audit_best_effort.
    audit_rows = (
        cli.table("audit_log")
        .select("agent_id, tool_name, action, outcome, details, target")
        .eq("target", f"task_queue:{row_id}")
        .order("timestamp", desc=True)
        .limit(5)
        .execute()
        .data
        or []
    )
    assert audit_rows, f"no audit_log row for target=task_queue:{row_id}"
    entry = audit_rows[0]
    assert entry["agent_id"] == "task-dispatcher"
    assert entry["tool_name"] == "claude_cli"
    assert entry["action"] == "dispatch"
    assert entry["outcome"] == "success"
    details = entry.get("details") or {}
    assert details.get("tier") == 0  # Tier.AUTO
    idem = details.get("idempotency_key")
    assert idem and len(idem) == 64, f"idempotency_key not a sha256 hex: {idem!r}"


# ---------------------------------------------------------------------------
# Escalation path
# ---------------------------------------------------------------------------


def test_stale_approval_escalates(
    monkeypatch: pytest.MonkeyPatch,
    marker: str,
    captured_popen: list[dict[str, Any]],
    thread_id: str,
) -> None:
    """Approval older than STALE_APPROVAL_MAX_DAYS → escalated + events row written."""
    pytest.importorskip("langgraph")
    pytest.importorskip("supabase")

    from agents import dispatcher, usage_probe
    from agents.escalation import STALE_APPROVAL_MAX_DAYS
    from agents.supabase_client import get_client
    from agents.usage_probe import UsageReading

    healthy = UsageReading(
        limit_window=timedelta(hours=5),
        used=5,
        total=100,
        reset_at=datetime.now(UTC),
        near_exhaustion=False,
    )
    monkeypatch.setattr(usage_probe, "read_usage", lambda: healthy)
    monkeypatch.setattr(dispatcher.usage_probe, "read_usage", lambda: healthy)

    cli = get_client()
    stale_at = datetime.now(UTC) - timedelta(days=STALE_APPROVAL_MAX_DAYS + 2)
    seeded = _insert_queue_row(
        cli,
        marker=marker,
        goal_prefix="e2e stale",
        approved_at=stale_at,
    )
    row_id = seeded["id"]

    result = dispatcher.run(thread_id, dry_run=False)
    assert result["outcome"] == "escalated", f"expected escalated, got {result!r}"
    assert result["reason"] == "stale_approval"

    # No subprocess spawn on escalation path.
    assert captured_popen == [], "escalation must not invoke subprocess"

    # Row flipped to escalated with reason captured.
    row = (
        cli.table("task_queue")
        .select("status, escalated_reason")
        .eq("id", row_id)
        .limit(1)
        .execute()
        .data
    )
    assert row
    assert row[0]["status"] == "escalated"
    assert row[0]["escalated_reason"] and "stale_approval" in row[0]["escalated_reason"]

    # events row written with severity=high, source=task-dispatcher,
    # trigger in payload.
    # Title shape from agents.escalation.escalate:
    #   "Dispatcher escalated task <id>: <trigger>"
    event_rows = (
        cli.table("events")
        .select("event_type, severity, source, payload, title")
        .eq("event_type", "dispatcher_escalation")
        .ilike("title", f"%{row_id}%")
        .order("created_at", desc=True)
        .limit(5)
        .execute()
        .data
        or []
    )
    assert event_rows, f"no events row for escalated task {row_id}"
    event = event_rows[0]
    assert event["severity"] == "high"
    assert event["source"] == "task-dispatcher"
    payload = event["payload"] or {}
    assert payload.get("trigger") == "stale_approval"
    assert payload.get("queue_id") == row_id
