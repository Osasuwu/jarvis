"""End-to-end integration tests for the Pillar 7 event flow (issue #175).

Validates the full pipeline:

    synthetic GitHub event
      -> agents.event_monitor graph (fetch -> classify -> store)
      -> Supabase ``events`` + ``audit_log`` tables
      -> visible to Claude Code via ``events_list`` (read back through the
         same supabase_client the MCP server uses)

These are **opt-in** — CI doesn't have live Ollama / Supabase / Postgres,
and we deliberately don't mock the last two because the whole point is to
verify that the real bridge works. Set ``AGENTS_E2E=1`` to run, e.g.:

    AGENTS_E2E=1 pytest tests/test_agents_integration.py -v

The test harness monkey-patches only ``fetch_repo_events`` (so we don't
depend on what GitHub happens to be surfacing at test time). Everything
downstream — Ollama classification, Supabase writes, LangGraph
checkpointing — runs for real.

Cleanup: every test tags rows with a fresh UUID marker and deletes
matching rows in teardown. Thread IDs are UUID-suffixed so parallel
invocations (and the real ``event-monitor`` thread) never collide.
"""

from __future__ import annotations

import os
import uuid
from typing import Any

import pytest

# Skip the whole module unless explicitly opted in.
pytestmark = pytest.mark.skipif(
    os.environ.get("AGENTS_E2E") != "1",
    reason="opt-in integration suite — set AGENTS_E2E=1 to run",
)


def _synth_event(event_id: str, marker: str, repo: str) -> dict[str, Any]:
    """Shape a fake IssuesEvent with a traceable marker in the title."""
    return {
        "id": event_id,
        "type": "IssuesEvent",
        "actor": {"login": "e2e-test"},
        "repo": {"name": repo},
        "payload": {
            "action": "opened",
            "issue": {"number": 1, "title": f"e2e smoke {marker}"},
        },
    }


def _delete_by_marker(marker: str) -> None:
    """Best-effort cleanup of rows tagged with ``marker``.

    Called from test teardown; swallowed errors only matter in that they'd
    leave rows behind. The marker keeps those rows obviously-test, so a
    human can spot and drop them manually if cleanup ever fails.
    """
    from agents.supabase_client import get_client

    try:
        cli = get_client()
        cli.table("events").delete().like("title", f"%{marker}%").execute()
    except Exception:
        pass


@pytest.fixture
def marker() -> str:
    """Per-test UUID tag — fresh marker for every test, cleaned up after."""
    tag = f"e2e-{uuid.uuid4()}"
    yield tag
    _delete_by_marker(tag)


@pytest.fixture
def thread_id() -> str:
    """Unique thread so each run gets its own LangGraph checkpoint history."""
    return f"e2e-{uuid.uuid4()}"


def test_full_pipeline_injects_and_stores(
    monkeypatch: pytest.MonkeyPatch, marker: str, thread_id: str
) -> None:
    """Inject a synthetic event; expect a stored Supabase row we can read back."""
    pytest.importorskip("langgraph")
    pytest.importorskip("supabase")

    from agents import event_monitor, supabase_client

    repo = "e2e/marker-repo"
    fake_events = [_synth_event("900000001", marker, repo)]

    # Only fetch is mocked — classify + store run for real.
    monkeypatch.setattr(event_monitor, "fetch_repo_events", lambda *a, **kw: list(fake_events))

    event_monitor.run(thread_id, [repo])

    # Event visible via the same list API Claude Code's MCP server hits.
    rows = supabase_client.list_events(repo=repo, processed=None, limit=20)
    matching = [r for r in rows if marker in (r.get("title") or "")]
    assert matching, f"no events matched marker {marker!r}; got {rows!r}"
    row = matching[0]
    assert row["source"] == "langgraph-monitor"
    assert row["event_type"] == "github.IssuesEvent"
    payload = row.get("payload") or {}
    assert payload.get("github_event_id") == "900000001"
    assert payload.get("classification") in ("info", "action")


def test_restart_skips_via_cursor(
    monkeypatch: pytest.MonkeyPatch, marker: str, thread_id: str
) -> None:
    """Second invocation with the same thread must not duplicate the event.

    Simulates GitHub's own cursor filtering: when the cursor has advanced
    past the synthetic event's id, the mock returns an empty list — which
    is exactly what the real Events API would do.
    """
    pytest.importorskip("langgraph")
    pytest.importorskip("supabase")

    from agents import event_monitor, supabase_client

    repo = "e2e/marker-repo"
    fake_id = "900000002"
    fake_events = [_synth_event(fake_id, marker, repo)]

    def cursor_aware_fetch(
        _repo: str, *, after_event_id: str | None = None, **_kw: object
    ) -> list[dict[str, Any]]:
        if after_event_id is not None and int(after_event_id) >= int(fake_id):
            return []
        return list(fake_events)

    monkeypatch.setattr(event_monitor, "fetch_repo_events", cursor_aware_fetch)

    # Run 1: should see and store the event.
    event_monitor.run(thread_id, [repo])
    first_rows = [
        r
        for r in supabase_client.list_events(repo=repo, processed=None, limit=20)
        if marker in (r.get("title") or "")
    ]
    assert len(first_rows) == 1, first_rows

    # Run 2: cursor persisted from run 1 should make the mock return [],
    # so no new row lands. Any extra row is a checkpoint regression.
    event_monitor.run(thread_id, [repo])
    second_rows = [
        r
        for r in supabase_client.list_events(repo=repo, processed=None, limit=20)
        if marker in (r.get("title") or "")
    ]
    assert len(second_rows) == 1, (
        f"restart produced duplicate rows — cursor didn't persist: {second_rows!r}"
    )


def test_audit_log_records_poll(
    monkeypatch: pytest.MonkeyPatch, marker: str, thread_id: str
) -> None:
    """Every poll should leave an audit row with agent_id=langgraph-monitor."""
    pytest.importorskip("langgraph")
    pytest.importorskip("supabase")

    from agents import event_monitor
    from agents.supabase_client import get_client

    repo = f"e2e/audit-{marker}"  # unique repo tag -> unique audit target string
    monkeypatch.setattr(
        event_monitor, "fetch_repo_events", lambda *a, **kw: []
    )  # empty poll is still audited

    event_monitor.run(thread_id, [repo])

    cli = get_client()
    # audit_log orders by `timestamp` (not `created_at` — the MCP server
    # uses a bespoke schema defined in mcp-memory/server.py).
    audit_rows = (
        cli.table("audit_log")
        .select("agent_id, tool_name, action, target")
        .eq("target", repo)
        .order("timestamp", desc=True)
        .limit(5)
        .execute()
        .data
        or []
    )
    try:
        assert audit_rows, f"no audit rows for target={repo!r}"
        assert audit_rows[0]["agent_id"] == "langgraph-monitor"
        assert audit_rows[0]["tool_name"] == "event_monitor"
        assert audit_rows[0]["action"] == "poll"
    finally:
        # Cleanup: remove the audit rows this test created.
        cli.table("audit_log").delete().eq("target", repo).execute()
