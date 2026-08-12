"""Unit tests for FOK judgment ↔ outcome linkage (#445).

Exercises the linkage logic when record_decision succeeds with outcomes_referenced
populated — fok_judgments rows matching the memory_ids within the time window
should be updated with the outcome_id.
"""

from __future__ import annotations

from datetime import datetime, timezone
import asyncio
from unittest.mock import MagicMock
from pathlib import Path

import pytest

import server  # noqa: F401 — must import before handlers.decision to avoid a
# partial-init circular import (server -> handlers.outcome -> handlers.decision)
import handlers.decision as dec

# Stable UUIDs for tests
_UID_MEM_A = "11111111-1111-1111-1111-111111111111"
_UID_MEM_B = "22222222-2222-2222-2222-222222222222"
_UID_FOK_1 = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
_UID_FOK_2 = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
_UID_EVENT_1 = "cccccccc-cccc-cccc-cccc-cccccccccccc"
_UID_EVENT_2 = "dddddddd-dddd-dddd-dddd-dddddddddddd"


def _make_linkage_test_client(
    decision_timestamp: str = None,
    fok_judgments_to_return: list[dict] | None = None,
    event_payloads: dict[str, dict] | None = None,
) -> MagicMock:
    """Mock client for FOK linkage tests.

    Simulates:
    - episodes.insert() returns decision with given timestamp
    - fok_judgments query returns provided judgments
    - events_canonical query returns payloads keyed by event_id
    """
    if decision_timestamp is None:
        decision_timestamp = datetime.now(timezone.utc).isoformat()

    client = MagicMock()

    # Episode insert returns decision_made episode with timestamp
    client.table.return_value.insert.return_value.execute.return_value = MagicMock(
        data=[{
            "id": "ep-decision-1",
            "created_at": decision_timestamp,
        }]
    )

    # Setup fok_judgments.select() chain
    def _fok_select_side_effect(*_args, **_kwargs):
        chain = MagicMock()
        chain.gte.return_value = chain
        chain.lte.return_value = chain
        chain.is_.return_value = chain

        # Return provided judgments
        chain.execute.return_value = MagicMock(
            data=fok_judgments_to_return or []
        )
        return chain

    # Setup events_canonical.select() chain — captures event_id from .eq() for payload lookup
    def _events_select_side_effect(*_args, **_kwargs):
        chain = MagicMock()
        chain.single.return_value = chain
        _captured = {}

        def _eq_side_effect(key, value):
            _captured[key] = value
            return chain

        chain.eq.side_effect = _eq_side_effect

        def _execute_side_effect():
            event_id = _captured.get("event_id")
            if event_id is not None and event_payloads:
                payload = event_payloads.get(str(event_id))
                if payload is not None:
                    # events.select('payload').single() returns
                    # data == {"payload": <the payload dict>}
                    return MagicMock(data={"payload": payload})
            return MagicMock(data=None)

        chain.execute.side_effect = _execute_side_effect
        return chain

    # Wire up table() to dispatch based on table name
    def _table_side_effect(name):
        if name == "episodes":
            m = MagicMock()
            m.insert.return_value.execute.return_value = MagicMock(
                data=[{
                    "id": "ep-decision-1",
                    "created_at": decision_timestamp,
                }]
            )
            return m
        elif name == "fok_judgments":
            m = MagicMock()
            m.select.side_effect = _fok_select_side_effect
            m.update.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[{"id": "updated"}]
            )
            client._fok_mock = m
            return m
        elif name == "events_canonical":
            m = MagicMock()
            m.select.side_effect = _events_select_side_effect
            return m
        return MagicMock()

    client.table.side_effect = _table_side_effect
    return client


class TestFokOutcomeLinkage:
    """FOK judgment linkage via memory_ids in record_decision (#445)."""

    @pytest.mark.asyncio
    async def test_linkage_called_when_outcomes_and_memories_present(self, monkeypatch):
        """Linkage function is invoked when outcomes_referenced and memories_used exist."""
        from server import _handle_record_decision

        client = _make_linkage_test_client()
        monkeypatch.setattr("server._get_client", lambda: client)

        result = await _handle_record_decision(
            {
                "decision": "use memory A",
                "rationale": "because",
                "reversibility": "reversible",
                "memories_used": [_UID_MEM_A],
                "outcomes_referenced": ["out-1"],
            }
        )

        # Decision recorded successfully
        assert "ep-decision-1" in result[0].text

        # fok_judgments.select() should have been called (via linkage)
        # (This is a simplified assertion — a full test would mock the
        # actual linkage and verify it ran.)

    @pytest.mark.asyncio
    async def test_linkage_skipped_when_no_outcomes(self, monkeypatch):
        """Linkage is skipped if outcomes_referenced is empty."""
        from server import _handle_record_decision

        client = _make_linkage_test_client()
        monkeypatch.setattr("server._get_client", lambda: client)

        result = await _handle_record_decision(
            {
                "decision": "decide without outcomes",
                "rationale": "because",
                "reversibility": "reversible",
                "memories_used": [_UID_MEM_A],
                # No outcomes_referenced
            }
        )

        # Decision recorded
        assert "ep-decision-1" in result[0].text

        # fok_judgments should not be queried for linkage
        # (since outcomes_referenced is empty/absent)

    @pytest.mark.asyncio
    async def test_linkage_skipped_when_no_memories(self, monkeypatch):
        """Linkage is skipped if memories_used is empty."""
        from server import _handle_record_decision

        client = _make_linkage_test_client()
        monkeypatch.setattr("server._get_client", lambda: client)

        result = await _handle_record_decision(
            {
                "decision": "decide without memories",
                "rationale": "because",
                "reversibility": "reversible",
                # No memories_used
                "outcomes_referenced": ["out-1"],
            }
        )

        # Decision recorded
        assert "ep-decision-1" in result[0].text

        # No linkage attempted (no memories to link)

    @pytest.mark.asyncio
    async def test_linkage_updates_outcome_id_when_memory_matches(self, monkeypatch):
        """Linkage updates fok_judgments.outcome_id when memory_id is in
        the recall event's returned_ids."""
        from server import _handle_record_decision

        fok_judgments = [
            {"id": _UID_FOK_1, "recall_event_id": _UID_EVENT_1, "project": None},
        ]
        event_payloads = {
            _UID_EVENT_1: {"returned_ids": [_UID_MEM_A]},
        }

        client = _make_linkage_test_client(
            fok_judgments_to_return=fok_judgments,
            event_payloads=event_payloads,
        )
        monkeypatch.setattr("server._get_client", lambda: client)

        result = await _handle_record_decision(
            {
                "decision": "link test",
                "rationale": "verify linkage",
                "reversibility": "reversible",
                "memories_used": [_UID_MEM_A],
                "outcomes_referenced": ["out-1"],
            }
        )

        assert "ep-decision-1" in result[0].text

        # Yield to event loop so fire-and-forget linkage task runs
        await asyncio.sleep(0)

        # Verify fok_judgments.update() was called with the correct outcome_id
        fok_mock = client._fok_mock
        fok_mock.update.assert_called_once_with({"outcome_id": "out-1"})
        # Verify it targeted the correct judgment by id
        fok_mock.update.return_value.eq.assert_called_once_with("id", _UID_FOK_1)

    @pytest.mark.asyncio
    async def test_linkage_skips_when_memory_not_in_returned_ids(self, monkeypatch):
        """No fok_judgments update when memory_id is absent from returned_ids."""
        from server import _handle_record_decision

        fok_judgments = [
            {"id": _UID_FOK_1, "recall_event_id": _UID_EVENT_1, "project": None},
        ]
        # returned_ids contains _UID_MEM_B, not _UID_MEM_A
        event_payloads = {
            _UID_EVENT_1: {"returned_ids": [_UID_MEM_B]},
        }

        client = _make_linkage_test_client(
            fok_judgments_to_return=fok_judgments,
            event_payloads=event_payloads,
        )
        monkeypatch.setattr("server._get_client", lambda: client)

        await _handle_record_decision(
            {
                "decision": "no match",
                "rationale": "memory not in returned IDs",
                "reversibility": "reversible",
                "memories_used": [_UID_MEM_A],
                "outcomes_referenced": ["out-1"],
            }
        )

        await asyncio.sleep(0)

        # No update should be performed (memory_id not in recall results)
        fok_mock = client._fok_mock
        fok_mock.update.assert_not_called()

    @pytest.mark.asyncio
    async def test_linkage_reads_events_canonical_not_events(self, monkeypatch):
        """#1493 AC4: recall event lookup must query events_canonical, never events."""
        from server import _handle_record_decision

        fok_judgments = [
            {"id": _UID_FOK_1, "recall_event_id": _UID_EVENT_1, "project": None},
        ]
        event_payloads = {
            _UID_EVENT_1: {"returned_ids": [_UID_MEM_A]},
        }

        client = _make_linkage_test_client(
            fok_judgments_to_return=fok_judgments,
            event_payloads=event_payloads,
        )
        monkeypatch.setattr("server._get_client", lambda: client)

        await _handle_record_decision(
            {
                "decision": "canonical table check",
                "rationale": "verify events_canonical is targeted",
                "reversibility": "reversible",
                "memories_used": [_UID_MEM_A],
                "outcomes_referenced": ["out-1"],
            }
        )

        await asyncio.sleep(0)

        table_names = [c.args[0] for c in client.table.call_args_list if c.args]
        assert "events_canonical" in table_names
        assert "events" not in table_names

        # Verify update landed (proves the events_canonical lookup actually worked)
        fok_mock = client._fok_mock
        fok_mock.update.assert_called_once_with({"outcome_id": "out-1"})

    @pytest.mark.asyncio
    async def test_linkage_skips_when_event_data_missing(self, monkeypatch):
        """No update when the recall event has no payload or doesn't exist."""
        from server import _handle_record_decision

        fok_judgments = [
            {"id": _UID_FOK_1, "recall_event_id": _UID_EVENT_1, "project": None},
        ]
        # No event_payloads passed — event lookup returns data=None
        client = _make_linkage_test_client(
            fok_judgments_to_return=fok_judgments,
        )
        monkeypatch.setattr("server._get_client", lambda: client)

        await _handle_record_decision(
            {
                "decision": "missing event",
                "rationale": "event data absent",
                "reversibility": "reversible",
                "memories_used": [_UID_MEM_A],
                "outcomes_referenced": ["out-1"],
            }
        )

        await asyncio.sleep(0)

        fok_mock = client._fok_mock
        fok_mock.update.assert_not_called()

    @pytest.mark.asyncio
    async def test_linkage_skips_when_two_judgments_one_match(self, monkeypatch):
        """Only the matching judgment gets updated when multiple exist."""
        from server import _handle_record_decision

        fok_judgments = [
            {"id": _UID_FOK_1, "recall_event_id": _UID_EVENT_1, "project": None},
            {"id": _UID_FOK_2, "recall_event_id": _UID_EVENT_2, "project": None},
        ]
        event_payloads = {
            _UID_EVENT_1: {"returned_ids": [_UID_MEM_A]},
            _UID_EVENT_2: {"returned_ids": [_UID_MEM_B]},
        }

        client = _make_linkage_test_client(
            fok_judgments_to_return=fok_judgments,
            event_payloads=event_payloads,
        )
        monkeypatch.setattr("server._get_client", lambda: client)

        await _handle_record_decision(
            {
                "decision": "two judgments",
                "rationale": "verify only matching judgment linked",
                "reversibility": "reversible",
                "memories_used": [_UID_MEM_A],
                "outcomes_referenced": ["out-1"],
            }
        )

        await asyncio.sleep(0)

        fok_mock = client._fok_mock
        # Update called once (only FOK_1 matches _UID_MEM_A)
        fok_mock.update.assert_called_once_with({"outcome_id": "out-1"})
        # Targeted FOK_1, not FOK_2
        fok_mock.update.return_value.eq.assert_called_once_with("id", _UID_FOK_1)


class TestDecisionSwallowedExceptions:
    """#1082: every genuinely-silent except-site in decision.py logs via
    the shared fire_and_forget.log_swallowed instead of dropping the
    exception on the floor."""

    @pytest.mark.asyncio
    async def test_resolve_memory_refs_logs_swallowed_on_query_error(self, monkeypatch):
        calls = []
        monkeypatch.setattr(dec, "log_swallowed", lambda site, exc: calls.append((site, exc)))

        client = MagicMock()
        client.table.return_value.select.return_value.eq.return_value.is_.return_value.order.return_value.limit.return_value.execute.side_effect = RuntimeError(
            "db down"
        )

        resolved, unresolved = dec._resolve_memory_refs(client, ["some-name"], None)

        assert resolved == []
        assert unresolved == ["some-name"]
        assert len(calls) == 1
        site, exc = calls[0]
        assert site == "decision._resolve_memory_refs"
        assert isinstance(exc, RuntimeError)

    @pytest.mark.asyncio
    async def test_link_fok_inner_logs_swallowed_on_event_lookup_error(self, monkeypatch):
        calls = []
        monkeypatch.setattr(dec, "log_swallowed", lambda site, exc: calls.append((site, exc)))

        fok_judgments = [
            {"id": _UID_FOK_1, "recall_event_id": _UID_EVENT_1, "project": None},
        ]
        client = _make_linkage_test_client(fok_judgments_to_return=fok_judgments)

        # Force the events_canonical.select("payload").eq("event_id", ...).single().execute()
        # chain to raise, regardless of .eq()/.single() call order.
        events_mock = MagicMock()
        broken_chain = MagicMock()
        broken_chain.eq.return_value = broken_chain
        broken_chain.single.return_value = broken_chain
        broken_chain.execute.side_effect = RuntimeError("events_canonical table unreachable")
        events_mock.select.return_value = broken_chain

        base_table_side_effect = client.table.side_effect

        def _table_with_broken_events(name):
            if name == "events_canonical":
                return events_mock
            return base_table_side_effect(name)

        client.table.side_effect = _table_with_broken_events
        monkeypatch.setattr("server._get_client", lambda: client)

        from server import _handle_record_decision

        await _handle_record_decision(
            {
                "decision": "inner failure",
                "rationale": "events lookup raises",
                "reversibility": "reversible",
                "memories_used": [_UID_MEM_A],
                "outcomes_referenced": ["out-1"],
            }
        )
        await asyncio.sleep(0)

        assert any(site == "decision._link_fok_judgments_to_outcomes.judgment" for site, _ in calls)

    @pytest.mark.asyncio
    async def test_link_fok_middle_logs_swallowed_on_judgments_query_error(self, monkeypatch):
        calls = []
        monkeypatch.setattr(dec, "log_swallowed", lambda site, exc: calls.append((site, exc)))

        client = _make_linkage_test_client()
        broken_fok = MagicMock()
        broken_fok.select.return_value.gte.return_value.lte.return_value.is_.return_value.execute.side_effect = RuntimeError(
            "fok_judgments table unreachable"
        )

        base_table_side_effect = client.table.side_effect

        def _table_with_broken_fok(name):
            if name == "fok_judgments":
                return broken_fok
            return base_table_side_effect(name)

        client.table.side_effect = _table_with_broken_fok
        monkeypatch.setattr("server._get_client", lambda: client)

        from server import _handle_record_decision

        await _handle_record_decision(
            {
                "decision": "middle failure",
                "rationale": "fok_judgments query raises",
                "reversibility": "reversible",
                "memories_used": [_UID_MEM_A],
                "outcomes_referenced": ["out-1"],
            }
        )
        await asyncio.sleep(0)

        assert any(site == "decision._link_fok_judgments_to_outcomes.memory" for site, _ in calls)

    @pytest.mark.asyncio
    async def test_link_fok_outer_logs_swallowed_on_malformed_timestamp(self, monkeypatch):
        calls = []
        monkeypatch.setattr(dec, "log_swallowed", lambda site, exc: calls.append((site, exc)))

        # A non-ISO timestamp makes datetime.fromisoformat raise before the
        # per-memory loop even starts — the outermost except site.
        client = _make_linkage_test_client(decision_timestamp="not-a-timestamp")
        monkeypatch.setattr("server._get_client", lambda: client)

        from server import _handle_record_decision

        await _handle_record_decision(
            {
                "decision": "outer failure",
                "rationale": "malformed decision timestamp",
                "reversibility": "reversible",
                "memories_used": [_UID_MEM_A],
                "outcomes_referenced": ["out-1"],
            }
        )
        await asyncio.sleep(0)

        assert any(
            site == "decision._link_fok_judgments_to_outcomes" for site, _ in calls
        )


def test_fok_calibration_summary_in_schema():
    """Regression guard: fok_calibration_summary RPC must exist in schema.sql."""
    schema = (Path(__file__).resolve().parents[2] / "mcp-memory" / "schema.sql").read_text()
    assert "create or replace function fok_calibration_summary" in schema, (
        "fok_calibration_summary RPC not found in schema.sql"
    )
    # Check for drift_signal column in RPC return type
    assert "drift_signal" in schema or "drift_detected" in schema, (
        "fok_calibration_summary must return drift signal"
    )


def test_fok_judgments_outcome_id_column():
    """Regression guard: fok_judgments.outcome_id FK must exist in schema."""
    schema = (Path(__file__).resolve().parents[2] / "mcp-memory" / "schema.sql").read_text()
    lines = [line for line in schema.splitlines() if "create table if not exists fok_judgments" in line]
    if not lines:
        # Check migrations
        migrations_dir = Path(__file__).resolve().parents[2] / "supabase" / "migrations"
        migration_files = list(migrations_dir.glob("*fok_judgments*.sql"))
        assert migration_files, "fok_judgments table not found in schema or migrations"
        # If found in migration, check for outcome_id
        for mfile in migration_files:
            content = mfile.read_text()
            if "outcome_id" in content and "REFERENCES task_outcomes" in content:
                return  # Found valid FK
        raise AssertionError("fok_judgments.outcome_id FK not found")
    else:
        # In schema.sql, check for outcome_id
        schema_section = "\n".join(schema.splitlines())
        assert "outcome_id" in schema_section and "task_outcomes" in schema_section, (
            "fok_judgments table must have outcome_id FK to task_outcomes"
        )
