"""Unit tests for the record_decision tool (#252).

Exercises the real handler in mcp-memory/server.py with a mock Supabase
client — asserts validation logic, episode-row shape, and failure paths.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from server import _handle_record_decision


def _make_client_returning(inserted_id: str = "ep-1") -> MagicMock:
    """MagicMock client whose table().insert().execute() returns one row."""
    client = MagicMock()
    client.table.return_value.insert.return_value.execute.return_value = MagicMock(
        data=[{"id": inserted_id}]
    )
    return client


class TestRecordDecisionValidation:
    @pytest.mark.asyncio
    async def test_missing_decision_errors(self, monkeypatch):
        client = _make_client_returning()
        monkeypatch.setattr("server._get_client", lambda: client)
        result = await _handle_record_decision({
            "rationale": "because reasons",
            "reversibility": "reversible",
        })
        assert "decision is required" in result[0].text.lower()
        assert not client.table.called

    @pytest.mark.asyncio
    async def test_missing_rationale_errors(self, monkeypatch):
        client = _make_client_returning()
        monkeypatch.setattr("server._get_client", lambda: client)
        result = await _handle_record_decision({
            "decision": "pick X",
            "reversibility": "reversible",
        })
        assert "rationale is required" in result[0].text.lower()
        assert not client.table.called

    @pytest.mark.asyncio
    async def test_invalid_reversibility_errors(self, monkeypatch):
        client = _make_client_returning()
        monkeypatch.setattr("server._get_client", lambda: client)
        result = await _handle_record_decision({
            "decision": "pick X",
            "rationale": "because",
            "reversibility": "permanent",  # not in enum
        })
        assert "reversibility" in result[0].text.lower()
        assert not client.table.called

    @pytest.mark.asyncio
    async def test_confidence_out_of_range_errors(self, monkeypatch):
        client = _make_client_returning()
        monkeypatch.setattr("server._get_client", lambda: client)
        for bad in (-0.1, 1.1, 2.0):
            result = await _handle_record_decision({
                "decision": "pick X",
                "rationale": "because",
                "reversibility": "reversible",
                "confidence": bad,
            })
            assert "confidence" in result[0].text.lower()
        assert not client.table.called


class TestRecordDecisionInsert:
    @pytest.mark.asyncio
    async def test_inserts_decision_made_episode(self, monkeypatch):
        client = _make_client_returning("ep-42")
        monkeypatch.setattr("server._get_client", lambda: client)

        result = await _handle_record_decision({
            "decision": "implement #252 directly",
            "rationale": "additive change, no breaking schema modifications",
            "memories_used": ["mem-a", "mem-b"],
            "outcomes_referenced": ["out-1"],
            "confidence": 0.85,
            "alternatives_considered": ["delegate to agent"],
            "reversibility": "reversible",
            "actor": "skill:delegate",
            "project": "jarvis",
        })

        # Returned message contains episode id
        assert "ep-42" in result[0].text

        # Correct table + row shape
        client.table.assert_called_with("episodes")
        insert_arg = client.table.return_value.insert.call_args.args[0]
        assert insert_arg["actor"] == "skill:delegate"
        assert insert_arg["kind"] == "decision_made"

        payload = insert_arg["payload"]
        assert payload["decision"] == "implement #252 directly"
        assert payload["rationale"].startswith("additive change")
        assert payload["memories_used"] == ["mem-a", "mem-b"]
        assert payload["outcomes_referenced"] == ["out-1"]
        assert payload["confidence"] == 0.85
        assert payload["alternatives_considered"] == ["delegate to agent"]
        assert payload["reversibility"] == "reversible"
        assert payload["project"] == "jarvis"

    @pytest.mark.asyncio
    async def test_defaults_actor_when_omitted(self, monkeypatch):
        client = _make_client_returning()
        monkeypatch.setattr("server._get_client", lambda: client)

        await _handle_record_decision({
            "decision": "x",
            "rationale": "y",
            "reversibility": "hard",
        })
        insert_arg = client.table.return_value.insert.call_args.args[0]
        assert insert_arg["actor"] == "skill:unknown"

    @pytest.mark.asyncio
    async def test_optional_fields_default_to_empty(self, monkeypatch):
        client = _make_client_returning()
        monkeypatch.setattr("server._get_client", lambda: client)

        await _handle_record_decision({
            "decision": "x",
            "rationale": "y",
            "reversibility": "reversible",
        })
        payload = client.table.return_value.insert.call_args.args[0]["payload"]
        assert payload["memories_used"] == []
        assert payload["outcomes_referenced"] == []
        assert payload["alternatives_considered"] == []
        # Confidence is omitted when not supplied — don't fabricate a value.
        assert "confidence" not in payload

    @pytest.mark.asyncio
    async def test_db_failure_returns_error_text(self, monkeypatch):
        client = MagicMock()
        client.table.return_value.insert.return_value.execute.side_effect = RuntimeError("boom")
        monkeypatch.setattr("server._get_client", lambda: client)

        result = await _handle_record_decision({
            "decision": "x",
            "rationale": "y",
            "reversibility": "reversible",
        })
        assert "boom" in result[0].text


def test_handler_defined_before_main_entry():
    """Regression guard: _handle_record_decision must live ABOVE the
    `if __name__ == "__main__"` block in server.py.

    When the module runs as main, Python enters `asyncio.run(main())` and
    blocks — any def after that point never gets bound to the module
    namespace. Tests don't catch this (they import server as a module,
    so __main__ never fires), but the dispatcher at runtime hits a
    NameError. This test parses the source and asserts the line ordering
    so we never ship the bug again.
    """
    server_path = Path(__file__).resolve().parents[1] / "mcp-memory" / "server.py"
    src = server_path.read_text(encoding="utf-8").splitlines()

    handler_line = next(
        (i for i, line in enumerate(src, start=1)
         if line.startswith("async def _handle_record_decision")),
        None,
    )
    main_guard_line = next(
        (i for i, line in enumerate(src, start=1)
         if line.startswith('if __name__ == "__main__"')),
        None,
    )
    assert handler_line is not None, "_handle_record_decision def not found in server.py"
    assert main_guard_line is not None, 'if __name__ == "__main__" not found in server.py'
    assert handler_line < main_guard_line, (
        f"_handle_record_decision defined at line {handler_line} is AFTER "
        f'`if __name__ == "__main__"` at line {main_guard_line} — the def '
        "will never be bound at runtime. Move it above the main entry."
    )


def test_decision_made_in_schema_check_constraint():
    """Regression guard: schema.sql must include 'decision_made' in episodes.kind CHECK.

    This asserts against the actual schema artifact rather than a Python
    list, so a schema rename or removal would fail the test.
    """
    schema = (Path(__file__).resolve().parents[1] / "mcp-memory" / "schema.sql").read_text()
    # Find the episodes.kind CHECK constraint line and assert decision_made is in it.
    # The constraint reads:
    #   check (kind in ('tool_call', 'decision', ..., 'decision_made'))
    lines = [line for line in schema.splitlines() if "check (kind in" in line]
    assert lines, "No 'check (kind in ...)' clause found in schema.sql"
    assert any("'decision_made'" in line for line in lines), \
        "episodes.kind CHECK constraint does not include 'decision_made'"
