"""Unit tests for the record_decision tool (#252, #325).

Exercises the real handler in mcp-memory/server.py with a mock Supabase
client — asserts validation logic, episode-row shape, name→UUID
resolution, and failure paths.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from server import (
    _handle_record_decision,
    _looks_like_uuid,
    _resolve_memory_refs,
)

# Stable UUIDs for tests — chosen so the same input yields the same
# canonical form after uuid.UUID().
_UID_A = "11111111-1111-1111-1111-111111111111"
_UID_B = "22222222-2222-2222-2222-222222222222"
_UID_C = "33333333-3333-3333-3333-333333333333"


def _make_client_returning(
    inserted_id: str = "ep-1",
    name_to_id: dict[str, str] | None = None,
) -> MagicMock:
    """MagicMock client wiring both insert and name-lookup paths.

    - table().insert().execute() -> inserted_id row.
    - table().select().eq(name=X).is_(deleted_at=null).[eq(project=P)].order().limit().execute()
      -> {"id": name_to_id[X]} if X is mapped, else empty list.

    The select side-effect is implemented by configuring ``eq``'s return
    value as a MagicMock whose chained ``.is_().order().limit().execute()``
    returns ``data=[]`` by default, and by hooking ``eq`` on the ``name``
    column to look up ``name_to_id``.
    """
    client = MagicMock()
    client.table.return_value.insert.return_value.execute.return_value = MagicMock(
        data=[{"id": inserted_id}]
    )

    lookup = dict(name_to_id or {})

    def _select_side_effect(*_args, **_kwargs):
        chain = MagicMock()

        def _eq_name(column, value):
            # Only the ``name`` column drives resolution; other .eq() calls
            # (e.g. project scoping) pass through with the same return value.
            hit = lookup.get(value) if column == "name" else None
            leaf = MagicMock()
            leaf.data = [{"id": hit}] if hit else []
            tail = MagicMock()
            tail.is_.return_value.order.return_value.limit.return_value.execute.return_value = leaf
            tail.is_.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = leaf
            tail.eq.return_value.is_.return_value.order.return_value.limit.return_value.execute.return_value = leaf
            return tail

        chain.eq.side_effect = _eq_name
        return chain

    client.table.return_value.select.side_effect = _select_side_effect
    return client


class TestRecordDecisionValidation:
    @pytest.mark.asyncio
    async def test_missing_decision_errors(self, monkeypatch):
        client = _make_client_returning()
        monkeypatch.setattr("server._get_client", lambda: client)
        result = await _handle_record_decision(
            {
                "rationale": "because reasons",
                "reversibility": "reversible",
            }
        )
        assert "decision is required" in result[0].text.lower()
        assert not client.table.called

    @pytest.mark.asyncio
    async def test_missing_rationale_errors(self, monkeypatch):
        client = _make_client_returning()
        monkeypatch.setattr("server._get_client", lambda: client)
        result = await _handle_record_decision(
            {
                "decision": "pick X",
                "reversibility": "reversible",
            }
        )
        assert "rationale is required" in result[0].text.lower()
        assert not client.table.called

    @pytest.mark.asyncio
    async def test_invalid_reversibility_errors(self, monkeypatch):
        client = _make_client_returning()
        monkeypatch.setattr("server._get_client", lambda: client)
        result = await _handle_record_decision(
            {
                "decision": "pick X",
                "rationale": "because",
                "reversibility": "permanent",  # not in enum
            }
        )
        assert "reversibility" in result[0].text.lower()
        assert not client.table.called

    @pytest.mark.asyncio
    async def test_confidence_out_of_range_errors(self, monkeypatch):
        client = _make_client_returning()
        monkeypatch.setattr("server._get_client", lambda: client)
        for bad in (-0.1, 1.1, 2.0):
            result = await _handle_record_decision(
                {
                    "decision": "pick X",
                    "rationale": "because",
                    "reversibility": "reversible",
                    "confidence": bad,
                }
            )
            assert "confidence" in result[0].text.lower()
        assert not client.table.called


class TestRecordDecisionInsert:
    @pytest.mark.asyncio
    async def test_inserts_decision_made_episode(self, monkeypatch):
        client = _make_client_returning("ep-42")
        monkeypatch.setattr("server._get_client", lambda: client)

        result = await _handle_record_decision(
            {
                "decision": "implement #252 directly",
                "rationale": "additive change, no breaking schema modifications",
                "memories_used": [_UID_A, _UID_B],
                "outcomes_referenced": ["out-1"],
                "confidence": 0.85,
                "alternatives_considered": ["delegate to agent"],
                "reversibility": "reversible",
                "actor": "skill:delegate",
                "project": "jarvis",
            }
        )

        # Returned message contains episode id
        assert "ep-42" in result[0].text

        # Both legacy episodes and canonical substrate get a write
        # post-#477 (dual-write during cutover wave).
        client.table.assert_any_call("episodes")
        client.table.assert_any_call("events_canonical")
        # Find the episodes-shaped insert (has 'kind', no 'trace_id').
        all_inserts = [
            c.args[0]
            for c in client.table.return_value.insert.call_args_list
            if c.args
        ]
        episode_inserts = [
            p for p in all_inserts if "kind" in p and "trace_id" not in p
        ]
        assert len(episode_inserts) == 1, (
            "expected exactly one episodes insert, got "
            f"{len(episode_inserts)}: {all_inserts!r}"
        )
        insert_arg = episode_inserts[0]
        assert insert_arg["actor"] == "skill:delegate"
        assert insert_arg["kind"] == "decision_made"

        payload = insert_arg["payload"]
        assert payload["decision"] == "implement #252 directly"
        assert payload["rationale"].startswith("additive change")
        # UUIDs pass through, canonicalized (lower-case, hyphenated).
        assert payload["memories_used"] == [_UID_A, _UID_B]
        assert "memories_used_unresolved" not in payload
        assert payload["outcomes_referenced"] == ["out-1"]
        assert payload["confidence"] == 0.85
        assert payload["alternatives_considered"] == ["delegate to agent"]
        assert payload["reversibility"] == "reversible"
        assert payload["project"] == "jarvis"

    @pytest.mark.asyncio
    async def test_defaults_actor_when_omitted(self, monkeypatch):
        client = _make_client_returning()
        monkeypatch.setattr("server._get_client", lambda: client)

        await _handle_record_decision(
            {
                "decision": "x",
                "rationale": "y",
                "reversibility": "hard",
            }
        )
        insert_arg = client.table.return_value.insert.call_args.args[0]
        assert insert_arg["actor"] == "skill:unknown"

    @pytest.mark.asyncio
    async def test_optional_fields_default_to_empty(self, monkeypatch):
        client = _make_client_returning()
        monkeypatch.setattr("server._get_client", lambda: client)

        await _handle_record_decision(
            {
                "decision": "x",
                "rationale": "y",
                "reversibility": "reversible",
            }
        )
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

        result = await _handle_record_decision(
            {
                "decision": "x",
                "rationale": "y",
                "reversibility": "reversible",
            }
        )
        assert "boom" in result[0].text


class TestLooksLikeUuid:
    def test_accepts_canonical(self):
        assert _looks_like_uuid(_UID_A) is True

    def test_accepts_uppercase(self):
        # uuid.UUID accepts case-insensitively — important because callers
        # sometimes paste UUIDs copied from PostgREST/Supabase logs.
        assert _looks_like_uuid(_UID_A.upper()) is True

    def test_rejects_plain_name(self):
        assert _looks_like_uuid("mem-a") is False

    def test_rejects_empty_string(self):
        assert _looks_like_uuid("") is False

    def test_rejects_non_string(self):
        assert _looks_like_uuid(None) is False
        assert _looks_like_uuid(123) is False


def _resolver_client(
    name_to_id: dict[str, str] | None = None,
    project_capture: list | None = None,
) -> MagicMock:
    """Client for direct ``_resolve_memory_refs`` tests.

    - ``name_to_id``: maps memory name -> id returned by the select leaf.
    - ``project_capture``: if provided, every ``.eq("project", v)`` call on
      the chained query appends v to the list — lets tests assert that
      project scoping actually reached the query builder.
    """
    name_to_id = dict(name_to_id or {})
    client = MagicMock()

    def _select_side_effect(*_args, **_kwargs):
        chain = MagicMock()

        def _eq_name(column, value):
            assert column == "name", "_resolve_memory_refs must key on 'name'"
            hit = name_to_id.get(value)
            leaf = MagicMock()
            leaf.data = [{"id": hit}] if hit else []

            head = MagicMock()
            # Unscoped: .eq(name).is_(deleted_at).order.limit.execute
            head.is_.return_value.order.return_value.limit.return_value.execute.return_value = leaf

            def _project_eq(col, val):
                if col == "project" and project_capture is not None:
                    project_capture.append(val)
                scoped = MagicMock()
                scoped.order.return_value.limit.return_value.execute.return_value = leaf
                return scoped

            head.is_.return_value.eq.side_effect = _project_eq
            return head

        chain.eq.side_effect = _eq_name
        return chain

    client.table.return_value.select.side_effect = _select_side_effect
    return client


class TestResolveMemoryRefs:
    def test_passes_through_uuid(self):
        client = _resolver_client()
        resolved, unresolved = _resolve_memory_refs(client, [_UID_A], project=None)
        assert resolved == [_UID_A]
        assert unresolved == []

    def test_canonicalizes_uppercase_uuid(self):
        client = _resolver_client()
        resolved, unresolved = _resolve_memory_refs(client, [_UID_A.upper()], project=None)
        # Canonical form is lowercase — uuid.UUID() normalizes so downstream
        # joins against memories.id (lowercase in PostgreSQL) always hit.
        assert resolved == [_UID_A]
        assert unresolved == []

    def test_dedups_repeated_uuid(self):
        client = _resolver_client()
        resolved, unresolved = _resolve_memory_refs(
            client, [_UID_A, _UID_A.upper(), _UID_A], project=None
        )
        assert resolved == [_UID_A]
        assert unresolved == []

    def test_resolves_name_via_db(self):
        client = _resolver_client({"mem-a": _UID_A})
        resolved, unresolved = _resolve_memory_refs(client, ["mem-a"], project=None)
        assert resolved == [_UID_A]
        assert unresolved == []

    def test_unknown_name_goes_to_unresolved(self):
        client = _resolver_client()
        resolved, unresolved = _resolve_memory_refs(client, ["ghost-name"], project=None)
        assert resolved == []
        assert unresolved == ["ghost-name"]

    def test_mixed_preserves_input_order(self):
        client = _resolver_client({"mem-b": _UID_B})
        resolved, unresolved = _resolve_memory_refs(client, [_UID_A, "mem-b", _UID_C], project=None)
        assert resolved == [_UID_A, _UID_B, _UID_C]
        assert unresolved == []

    def test_scopes_lookup_by_project_when_provided(self):
        capture: list = []
        client = _resolver_client({"mem-a": _UID_A}, project_capture=capture)
        resolved, _ = _resolve_memory_refs(client, ["mem-a"], project="jarvis")
        assert resolved == [_UID_A]
        assert capture == ["jarvis"]

    def test_no_project_scope_when_project_none(self):
        capture: list = []
        client = _resolver_client({"mem-a": _UID_A}, project_capture=capture)
        resolved, _ = _resolve_memory_refs(client, ["mem-a"], project=None)
        assert resolved == [_UID_A]
        assert capture == []

    def test_skips_empty_and_non_string_refs(self):
        client = _resolver_client()
        resolved, unresolved = _resolve_memory_refs(client, [None, 123, "", "   "], project=None)
        assert resolved == []
        assert unresolved == []

    def test_db_error_marks_name_unresolved(self):
        client = MagicMock()
        client.table.return_value.select.side_effect = RuntimeError("postgrest down")
        resolved, unresolved = _resolve_memory_refs(client, ["mem-a"], project=None)
        assert resolved == []
        # A DB blip shouldn't throw — unresolved is the safe fallback so
        # the outer handler still writes the decision episode.
        assert unresolved == ["mem-a"]


class TestRecordDecisionResolution:
    """End-to-end: ``memories_used`` resolution visible through the handler."""

    @pytest.mark.asyncio
    async def test_name_resolves_to_canonical_uuid_in_payload(self, monkeypatch):
        client = _make_client_returning("ep-99", name_to_id={"mem-a": _UID_A})
        monkeypatch.setattr("server._get_client", lambda: client)

        await _handle_record_decision(
            {
                "decision": "x",
                "rationale": "y",
                "reversibility": "reversible",
                "memories_used": ["mem-a"],
                "project": "jarvis",
            }
        )
        payload = client.table.return_value.insert.call_args.args[0]["payload"]
        assert payload["memories_used"] == [_UID_A]
        assert "memories_used_unresolved" not in payload

    @pytest.mark.asyncio
    async def test_unresolved_names_surface_in_response_and_payload(self, monkeypatch):
        client = _make_client_returning("ep-99", name_to_id={})
        monkeypatch.setattr("server._get_client", lambda: client)

        result = await _handle_record_decision(
            {
                "decision": "x",
                "rationale": "y",
                "reversibility": "reversible",
                "memories_used": ["ghost-a", "ghost-b"],
            }
        )
        text = result[0].text
        assert "ep-99" in text
        # Warning text must name the unresolved refs so the owner can fix
        # spelling or re-run with a UUID.
        assert "ghost-a" in text and "ghost-b" in text
        payload = client.table.return_value.insert.call_args.args[0]["payload"]
        assert payload["memories_used"] == []
        assert payload["memories_used_unresolved"] == ["ghost-a", "ghost-b"]

    @pytest.mark.asyncio
    async def test_mix_of_uuid_and_name_resolves_both(self, monkeypatch):
        client = _make_client_returning("ep-99", name_to_id={"mem-b": _UID_B})
        monkeypatch.setattr("server._get_client", lambda: client)

        await _handle_record_decision(
            {
                "decision": "x",
                "rationale": "y",
                "reversibility": "reversible",
                "memories_used": [_UID_A, "mem-b", _UID_C],
            }
        )
        payload = client.table.return_value.insert.call_args.args[0]["payload"]
        assert payload["memories_used"] == [_UID_A, _UID_B, _UID_C]
        assert "memories_used_unresolved" not in payload


def test_handler_defined_before_main_entry():
    """Regression guard: `_handle_record_decision` must be bound to the
    server module's namespace BEFORE `if __name__ == "__main__"` triggers.

    When the module runs as main, Python enters `asyncio.run(main())` and
    blocks — any def or import after that point never gets bound. Tests
    don't catch this (they import server as a module, so __main__ never
    fires), but the dispatcher at runtime hits a NameError.

    Pre-#360: the def itself lived in server.py and the assertion was on
    its line ordering. Post-#360: the def lives in `handlers/decision.py`
    and is brought into server's namespace via `from handlers.decision
    import _handle_record_decision`. The invariant — that binding happens
    before the main guard — is still meaningful, just shifted to the
    import line.
    """
    repo_root = Path(__file__).resolve().parents[1]
    server_path = repo_root / "mcp-memory" / "server.py"
    decision_path = repo_root / "mcp-memory" / "handlers" / "decision.py"
    server_src = server_path.read_text(encoding="utf-8").splitlines()
    decision_src = decision_path.read_text(encoding="utf-8")

    # The def must exist somewhere — handlers/decision.py is the post-#360 home.
    assert "async def _handle_record_decision" in decision_src, (
        "_handle_record_decision def not found in handlers/decision.py"
    )

    # In server.py, the import binding `_handle_record_decision` must come
    # before `if __name__ == "__main__"` — same regression class as pre-#360,
    # just measured at the binding site (import) rather than the def site.
    # Match any line that names the handler before the main guard. Multiline
    # imports put `_handle_record_decision` on its own line inside parentheses,
    # which won't start with `from`/`import` itself — but it's still part of
    # the bind statement.
    binding_line = next(
        (
            i
            for i, line in enumerate(server_src, start=1)
            if "_handle_record_decision" in line
        ),
        None,
    )
    main_guard_line = next(
        (
            i
            for i, line in enumerate(server_src, start=1)
            if line.startswith('if __name__ == "__main__"')
        ),
        None,
    )
    assert binding_line is not None, (
        "no `from ... import _handle_record_decision` line found in server.py — "
        "the dispatcher will hit NameError at runtime"
    )
    assert main_guard_line is not None, 'if __name__ == "__main__" not found in server.py'
    assert binding_line < main_guard_line, (
        f"_handle_record_decision bound at line {binding_line} is AFTER "
        f'`if __name__ == "__main__"` at line {main_guard_line} — the binding '
        "will never run when the module starts as __main__."
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
    assert any("'decision_made'" in line for line in lines), (
        "episodes.kind CHECK constraint does not include 'decision_made'"
    )
