"""Unit tests for mcp-memory/server.py — store path: handler, classifier,
auto-links, embedding slots, dual-embed writes, known unknowns.

conftest.py handles the sys.modules stubs for MCP SDK + Supabase before
this file loads, so `from server import` works without the real deps.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from server import (
    _apply_classifier_decision,
    _compute_write_embeddings,
    _create_auto_links,
    _embed_upsert_fields,
    _handle_store,
    _model_slot,
    _resolve_known_unknowns,
    _upsert_known_unknown,
    CLASSIFIER_APPLY_THRESHOLD,
    CLASSIFIER_TRIGGER_SIM,
    MAX_AUTO_LINKS,
    SUPERSEDE_SIM_THRESHOLD,
)
from classifier import ClassifierDecision
import server as server_module
import handlers.memory as mem
import events_canonical


# ---------------------------------------------------------------------------
# _create_auto_links (async, mocked Supabase)
# ---------------------------------------------------------------------------


class TestCreateAutoLinks:
    """Auto-linking creates memory_links entries based on similarity.

    Phase 2b changed the contract: links are always created as 'related'
    first, then the classifier (or legacy fallback) decides whether to
    upgrade to 'supersedes' / mark expired.
    """

    @pytest.fixture
    def mock_client(self):
        client = MagicMock()
        client.table.return_value.upsert.return_value.execute.return_value = MagicMock(data=[])
        client.table.return_value.select.return_value.in_.return_value.execute.return_value = (
            MagicMock(data=[])
        )
        return client

    def _first_links_upsert(self, mock_client):
        for call in mock_client.table.return_value.upsert.call_args_list:
            arg = call[0][0]
            if isinstance(arg, list):
                return arg
        return []

    @pytest.mark.asyncio
    async def test_creates_related_links(self, mock_client):
        similar = [
            {"id": "target-1", "type": "project", "similarity": 0.70},
            {"id": "target-2", "type": "project", "similarity": 0.65},
        ]
        await _create_auto_links(mock_client, "source-id", similar, mem_type="project")

        links = self._first_links_upsert(mock_client)
        assert len(links) == 2
        assert all(link["link_type"] == "related" for link in links)
        assert links[0]["strength"] == 0.70
        assert links[1]["strength"] == 0.65

    @pytest.mark.asyncio
    async def test_legacy_fallback_supersedes_same_type(self, mock_client, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        similar = [
            {
                "id": "old-decision",
                "type": "decision",
                "similarity": SUPERSEDE_SIM_THRESHOLD + 0.05,
            },
        ]
        await _create_auto_links(mock_client, "new-decision", similar, mem_type="decision")

        update_calls = [
            c
            for c in mock_client.table.return_value.update.call_args_list
            if c[0][0].get("superseded_by") == "new-decision"
        ]
        assert len(update_calls) == 1

    @pytest.mark.asyncio
    async def test_no_supersession_when_below_threshold(self, mock_client, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        similar = [
            {"id": "target", "type": "project", "similarity": 0.70},
        ]
        await _create_auto_links(mock_client, "source", similar, mem_type="project")

        update_calls = [
            c
            for c in mock_client.table.return_value.update.call_args_list
            if c[0][0].get("superseded_by") == "source"
        ]
        assert update_calls == []

    @pytest.mark.asyncio
    async def test_max_links_limit(self, mock_client):
        similar = [{"id": f"t-{i}", "type": "project", "similarity": 0.70} for i in range(10)]
        await _create_auto_links(mock_client, "source", similar, mem_type="project")

        links = self._first_links_upsert(mock_client)
        assert len(links) == MAX_AUTO_LINKS

    @pytest.mark.asyncio
    async def test_empty_similar_rows(self, mock_client):
        await _create_auto_links(mock_client, "source", [], mem_type="project")
        link_calls = [c for c in mock_client.table.call_args_list if c[0][0] == "memory_links"]
        assert link_calls == []

    @pytest.mark.asyncio
    async def test_swallows_exceptions(self, mock_client):
        mock_client.table.side_effect = Exception("DB error")
        await _create_auto_links(
            mock_client, "source", [{"id": "t", "type": "p", "similarity": 0.7}], "project"
        )


# ---------------------------------------------------------------------------
# #1082: link_decision_path — durable record of which path actually resolved
# the auto-link decision (classifier / legacy_heuristic / classifier_failed).
# ---------------------------------------------------------------------------


class TestLinkDecisionPath:
    @pytest.fixture
    def mock_client(self):
        client = MagicMock()
        client.table.return_value.upsert.return_value.execute.return_value = MagicMock(data=[])
        client.table.return_value.select.return_value.in_.return_value.execute.return_value = (
            MagicMock(data=[])
        )
        client.table.return_value.update.return_value.eq.return_value.is_.return_value.execute.return_value = MagicMock(
            data=[{"id": "row"}]
        )
        client.table.return_value.insert.return_value.execute.return_value = MagicMock()
        return client

    @pytest.fixture
    def capture_emit(self, monkeypatch):
        calls = []

        def _fake_emit_event(client, **kwargs):
            calls.append(kwargs)
            return {"id": "event-uuid"}

        monkeypatch.setattr("events_canonical.emit_event", _fake_emit_event)
        return calls

    @pytest.mark.asyncio
    async def test_classifier_path_recorded_on_success(
        self, mock_client, monkeypatch, capture_emit
    ):
        decision = ClassifierDecision(
            decision="NOOP", target_id=None, confidence=0.9, reasoning="r"
        )

        async def _fake_classify_write(_candidate, _neighbors):
            return decision

        monkeypatch.setattr(mem, "classify_write", _fake_classify_write)

        similar = [
            {"id": "old", "type": "decision", "similarity": CLASSIFIER_TRIGGER_SIM + 0.05},
        ]
        await _create_auto_links(
            mock_client,
            "new-decision",
            similar,
            mem_type="decision",
            candidate={"id": "new-decision", "content": "c"},
        )

        assert len(capture_emit) == 1
        assert capture_emit[0]["action"] == "link_decision_path"
        assert capture_emit[0]["payload"]["path"] == "classifier"
        assert capture_emit[0]["payload"]["memory_id"] == "new-decision"

    @pytest.mark.asyncio
    async def test_classifier_failed_no_decision_recorded_when_classify_write_errors(
        self, mock_client, monkeypatch, capture_emit
    ):
        async def _fake_classify_write(_candidate, _neighbors):
            raise RuntimeError("API timeout")

        monkeypatch.setattr(mem, "classify_write", _fake_classify_write)

        similar = [
            {"id": "old", "type": "decision", "similarity": CLASSIFIER_TRIGGER_SIM + 0.05},
        ]
        await _create_auto_links(
            mock_client,
            "new-decision",
            similar,
            mem_type="decision",
            candidate={"id": "new-decision", "content": "c"},
        )

        assert len(capture_emit) == 1
        assert capture_emit[0]["payload"]["path"] == "classifier_failed_no_decision"

    @pytest.mark.asyncio
    async def test_legacy_heuristic_path_recorded_without_candidate(
        self, mock_client, monkeypatch, capture_emit
    ):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        similar = [
            {"id": "old", "type": "decision", "similarity": SUPERSEDE_SIM_THRESHOLD + 0.05},
        ]
        # No `candidate=` kwarg -> attempted_classifier is False regardless of
        # classify_write availability.
        await _create_auto_links(mock_client, "new-decision", similar, mem_type="decision")

        assert len(capture_emit) == 1
        assert capture_emit[0]["payload"]["path"] == "legacy_heuristic"

    @pytest.mark.asyncio
    async def test_no_path_recorded_when_no_candidates_above_trigger(
        self, mock_client, capture_emit
    ):
        similar = [{"id": "t", "type": "project", "similarity": 0.10}]
        await _create_auto_links(mock_client, "source", similar, mem_type="project")

        assert capture_emit == []


# ---------------------------------------------------------------------------
# Phase 2b classifier — _apply_classifier_decision routing + queue writes
# ---------------------------------------------------------------------------


class TestApplyClassifierDecision:
    """Routing of classifier decisions: which DB mutations fire when."""

    @pytest.fixture
    def mock_client(self):
        client = MagicMock()
        client._tables = {}

        def _get_table(name):
            if name not in client._tables:
                t = MagicMock()
                t.update.return_value.eq.return_value.is_.return_value.execute.return_value = (
                    MagicMock(data=[{"id": "row"}])
                )
                t.insert.return_value.execute.return_value = MagicMock()
                t.upsert.return_value.execute.return_value = MagicMock()
                client._tables[name] = t
            return client._tables[name]

        client.table.side_effect = _get_table
        return client

    def _update_calls(self, mock_client, key: str, table: str = "memories"):
        t = mock_client._tables.get(table)
        if t is None:
            return []
        return [c for c in t.update.call_args_list if isinstance(c[0][0], dict) and key in c[0][0]]

    def _queue_inserts(self, mock_client):
        t = mock_client._tables.get("memory_review_queue")
        if t is None:
            return []
        return t.insert.call_args_list

    def _link_upserts(self, mock_client, link_type: str | None = None):
        t = mock_client._tables.get("memory_links")
        if t is None:
            return []
        calls = t.upsert.call_args_list
        if link_type is None:
            return calls
        out = []
        for c in calls:
            payload = c[0][0]
            if isinstance(payload, dict) and payload.get("link_type") == link_type:
                out.append(c)
        return out

    @pytest.mark.asyncio
    async def test_high_confidence_update_marks_superseded(self, mock_client):
        decision = ClassifierDecision(
            decision="UPDATE",
            target_id="old-id",
            confidence=0.95,
            reasoning="refines target",
        )
        neighbors = [{"id": "old-id", "name": "old", "similarity": 0.82}]
        await _apply_classifier_decision(mock_client, "new-id", decision, neighbors)

        sup_calls = self._update_calls(mock_client, "superseded_by")
        assert len(sup_calls) == 1
        assert sup_calls[0][0][0]["superseded_by"] == "new-id"

        sup_links = self._link_upserts(mock_client, link_type="supersedes")
        assert len(sup_links) == 1
        link_payload = sup_links[0][0][0]
        assert link_payload["source_id"] == "new-id"
        assert link_payload["target_id"] == "old-id"

        inserts = self._queue_inserts(mock_client)
        assert len(inserts) == 1
        payload = inserts[0][0][0]
        assert payload["decision"] == "UPDATE"
        assert payload["status"] == "auto_applied"
        assert payload["target_id"] == "old-id"

    @pytest.mark.asyncio
    async def test_high_confidence_delete_sets_expired(self, mock_client):
        decision = ClassifierDecision(
            decision="DELETE",
            target_id="old-id",
            confidence=0.92,
            reasoning="negates target",
        )
        neighbors = [{"id": "old-id", "name": "old", "similarity": 0.85}]
        await _apply_classifier_decision(mock_client, "new-id", decision, neighbors)

        exp_calls = self._update_calls(mock_client, "expired_at")
        assert len(exp_calls) == 1

        inserts = self._queue_inserts(mock_client)
        assert inserts[0][0][0]["decision"] == "DELETE"
        assert inserts[0][0][0]["status"] == "auto_applied"

    @pytest.mark.asyncio
    async def test_low_confidence_update_queues_pending(self, mock_client):
        decision = ClassifierDecision(
            decision="UPDATE",
            target_id="old-id",
            confidence=CLASSIFIER_APPLY_THRESHOLD - 0.1,
            reasoning="ambiguous",
        )
        neighbors = [{"id": "old-id", "name": "old", "similarity": 0.78}]
        await _apply_classifier_decision(mock_client, "new-id", decision, neighbors)

        sup_calls = self._update_calls(mock_client, "superseded_by")
        assert sup_calls == []

        inserts = self._queue_inserts(mock_client)
        payload = inserts[0][0][0]
        assert payload["status"] == "pending"
        assert payload["applied_at"] is None

    @pytest.mark.asyncio
    async def test_noop_records_decision_no_mutation(self, mock_client):
        decision = ClassifierDecision(
            decision="NOOP",
            target_id=None,
            confidence=0.9,
            reasoning="redundant",
        )
        neighbors = [{"id": "x", "name": "x", "similarity": 0.9}]
        await _apply_classifier_decision(mock_client, "new-id", decision, neighbors)

        assert self._update_calls(mock_client, "superseded_by") == []
        assert self._update_calls(mock_client, "expired_at") == []
        inserts = self._queue_inserts(mock_client)
        assert len(inserts) == 1
        assert inserts[0][0][0]["decision"] == "NOOP"

    @pytest.mark.asyncio
    async def test_high_confidence_add_no_queue_entry(self, mock_client):
        decision = ClassifierDecision(
            decision="ADD",
            target_id=None,
            confidence=0.95,
            reasoning="genuinely new",
        )
        neighbors = [{"id": "x", "name": "x", "similarity": 0.76}]
        await _apply_classifier_decision(mock_client, "new-id", decision, neighbors)

        assert self._queue_inserts(mock_client) == []

    @pytest.mark.asyncio
    async def test_hallucinated_target_id_refused(self, mock_client):
        decision = ClassifierDecision(
            decision="UPDATE",
            target_id="never-existed",
            confidence=0.95,
            reasoning="...",
        )
        neighbors = [{"id": "real-id", "name": "real", "similarity": 0.85}]
        await _apply_classifier_decision(mock_client, "new-id", decision, neighbors)

        assert self._update_calls(mock_client, "superseded_by") == []
        inserts = self._queue_inserts(mock_client)
        payload = inserts[0][0][0]
        assert payload["status"] == "pending"
        assert payload["target_id"] is None


# ---------------------------------------------------------------------------
# Phase 2c: memory_store must reject writes missing source_provenance
# ---------------------------------------------------------------------------


class TestHandleStoreProvenance:
    """Phase 2c — every memory write carries a namespaced source_provenance."""

    @pytest.fixture(autouse=True)
    def _patch_client(self, monkeypatch):
        self.client = MagicMock()
        monkeypatch.setattr(server_module, "_get_client", lambda: self.client)

    @pytest.mark.asyncio
    async def test_rejects_missing_provenance(self):
        result = await _handle_store(
            {
                "type": "project",
                "name": "test_missing",
                "content": "test content",
                "project": "jarvis",
            }
        )
        assert len(result) == 1
        assert "source_provenance is required" in result[0].text
        self.client.table.assert_not_called()

    @pytest.mark.asyncio
    async def test_rejects_blank_provenance(self):
        result = await _handle_store(
            {
                "type": "project",
                "name": "test_blank",
                "content": "test content",
                "source_provenance": "   ",
                "project": "jarvis",
            }
        )
        assert "source_provenance is required" in result[0].text
        self.client.table.assert_not_called()

    @pytest.mark.asyncio
    async def test_rejects_none_provenance(self):
        result = await _handle_store(
            {
                "type": "project",
                "name": "test_none",
                "content": "test content",
                "source_provenance": None,
                "project": "jarvis",
            }
        )
        assert "source_provenance is required" in result[0].text
        self.client.table.assert_not_called()

    @pytest.mark.asyncio
    async def test_provenance_stripped_before_persist(self, monkeypatch):
        async def _fake_embed(_text, **_kwargs):
            return None

        monkeypatch.setattr(server_module, "_embed", _fake_embed)

        tbl = MagicMock()
        tbl.upsert.return_value.execute.return_value = MagicMock(data=[{"id": "stored-1"}])
        self.client.table.return_value = tbl

        await _handle_store(
            {
                "type": "project",
                "name": "test_strip",
                "content": "test content",
                "project": "jarvis",
                "source_provenance": "  skill:test  ",
            }
        )

        upsert_calls = tbl.upsert.call_args_list
        assert upsert_calls
        data_arg = upsert_calls[-1][0][0]
        assert data_arg["source_provenance"] == "skill:test"


class TestHandleStoreProjectRequired:
    """#1613 — project scope must not silently default to global/NULL."""

    @pytest.fixture(autouse=True)
    def _patch_client(self, monkeypatch):
        self.client = MagicMock()
        monkeypatch.setattr(server_module, "_get_client", lambda: self.client)

    @pytest.mark.asyncio
    async def test_rejects_missing_project(self):
        result = await _handle_store(
            {
                "type": "project",
                "name": "test_missing_project",
                "content": "test content",
                "source_provenance": "skill:test",
            }
        )
        assert len(result) == 1
        assert "project is required" in result[0].text
        self.client.table.assert_not_called()

    @pytest.mark.asyncio
    async def test_rejects_none_project(self):
        result = await _handle_store(
            {
                "type": "project",
                "name": "test_none_project",
                "content": "test content",
                "source_provenance": "skill:test",
                "project": None,
            }
        )
        assert "project is required" in result[0].text
        self.client.table.assert_not_called()

    @pytest.mark.asyncio
    async def test_global_is_accepted_and_normalized_to_null(self, monkeypatch):
        async def _no_embed(_text):
            return {}

        monkeypatch.setattr(server_module, "_compute_write_embeddings", _no_embed)

        async def _noop_links(*_a, **_k):
            return None

        monkeypatch.setattr(server_module, "_create_auto_links", _noop_links)

        tbl = MagicMock()
        tbl.select.return_value.eq.return_value.is_.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[]
        )
        tbl.insert.return_value.execute.return_value = MagicMock(data=[{"id": "stored-1"}])
        self.client.table.return_value = tbl

        result = await _handle_store(
            {
                "type": "project",
                "name": "test_global_scope",
                "content": "test content",
                "source_provenance": "skill:test",
                "project": "global",
            }
        )

        assert "project is required" not in result[0].text
        insert_calls = [call for call in tbl.insert.call_args_list if "project" in call[0][0]]
        assert insert_calls
        data_arg = insert_calls[-1][0][0]
        assert data_arg["project"] is None


class TestMemoryStoreSchemaRequiresProject:
    """#1613 AC1 — the JSON-schema `required` declaration, not just the handler guard."""

    def test_project_is_in_required_array(self, monkeypatch):
        # `Tool` is a raw MagicMock class stub in this test environment
        # (conftest.py) — instances aren't distinguishable by `.name` and
        # the class itself doesn't record calls. Swap in a spy to capture
        # the constructor kwargs for the memory_store Tool() call.
        import tools_schema

        spy = MagicMock()
        monkeypatch.setattr(tools_schema, "Tool", spy)

        tools_schema.tool_definitions()

        store_call = next(
            call for call in spy.call_args_list if call.kwargs.get("name") == "memory_store"
        )
        assert "project" in store_call.kwargs["input_schema"]["required"]


class TestHandleStoreStructuredResponse:
    """#658: success-path returns JSON, not prose."""

    @pytest.fixture(autouse=True)
    def _patch_client(self, monkeypatch):
        self.client = MagicMock()
        monkeypatch.setattr(server_module, "_get_client", lambda: self.client)

        async def _no_embed(_text):
            return {}

        monkeypatch.setattr(server_module, "_compute_write_embeddings", _no_embed)

        async def _noop_links(*_a, **_k):
            return None

        monkeypatch.setattr(server_module, "_create_auto_links", _noop_links)

    @pytest.mark.asyncio
    async def test_project_scoped_upsert_returns_structured_json(self):
        tbl = MagicMock()
        tbl.upsert.return_value.execute.return_value = MagicMock(data=[{"id": "mem-uuid-1"}])
        self.client.table.return_value = tbl

        result = await _handle_store(
            {
                "type": "project",
                "name": "test_struct_project",
                "content": "test content",
                "project": "jarvis",
                "source_provenance": "session:test",
            }
        )

        assert len(result) == 1
        body = json.loads(result[0].text)
        assert body["stored"] is True
        assert body["action"] == "saved"
        assert body["memory_id"] == "mem-uuid-1"
        assert body["project"] == "jarvis"
        assert body["consolidation_candidates"] == []
        assert body["classifier_pending"] is False
        assert "test_struct_project" in body["message"]
        assert "saved" in body["message"]

    @pytest.mark.asyncio
    async def test_global_new_returns_action_created(self):
        tbl = MagicMock()
        select_chain = tbl.select.return_value.eq.return_value.is_.return_value
        select_chain.limit.return_value.execute.return_value = MagicMock(data=[])
        tbl.insert.return_value.execute.return_value = MagicMock(data=[{"id": "mem-new"}])
        self.client.table.return_value = tbl

        result = await _handle_store(
            {
                "type": "feedback",
                "name": "test_struct_global_new",
                "content": "x",
                "source_provenance": "session:test",
                "project": "global",
            }
        )

        body = json.loads(result[0].text)
        assert body["stored"] is True
        assert body["action"] == "created"
        assert body["memory_id"] == "mem-new"
        assert body["project"] == "global"

    @pytest.mark.asyncio
    async def test_global_existing_returns_action_updated(self):
        tbl = MagicMock()
        select_chain = tbl.select.return_value.eq.return_value.is_.return_value
        select_chain.limit.return_value.execute.return_value = MagicMock(
            data=[{"id": "mem-existing"}]
        )
        tbl.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        self.client.table.return_value = tbl

        result = await _handle_store(
            {
                "type": "feedback",
                "name": "test_struct_global_update",
                "content": "x",
                "source_provenance": "session:test",
                "project": "global",
            }
        )

        body = json.loads(result[0].text)
        assert body["stored"] is True
        assert body["action"] == "updated"
        assert body["memory_id"] == "mem-existing"
        assert body["project"] == "global"

    @pytest.mark.asyncio
    async def test_consolidation_uses_neutral_phrasing(self, monkeypatch):
        async def _real_embed(_text):
            return {"embedding": [0.1] * 512}

        monkeypatch.setattr(server_module, "_compute_write_embeddings", _real_embed)

        tbl = MagicMock()
        tbl.upsert.return_value.execute.return_value = MagicMock(data=[{"id": "mem-uuid-2"}])
        self.client.table.return_value = tbl

        self.client.rpc.return_value.execute.return_value = MagicMock(
            data=[
                {"id": "sib-1", "name": "sibling_a", "similarity": 0.85},
                {"id": "sib-2", "name": "sibling_b", "similarity": 0.82},
                {"id": "sib-3", "name": "sibling_c", "similarity": 0.81},
            ]
        )

        result = await _handle_store(
            {
                "type": "feedback",
                "name": "test_struct_consolidation",
                "content": "content",
                "project": "jarvis",
                "source_provenance": "session:test",
            }
        )

        body = json.loads(result[0].text)
        assert body["stored"] is True
        assert body["action"] == "saved"
        assert "⚠" not in body["message"]
        assert "hint" not in body["message"].lower()
        assert "info:" in body["message"].lower()
        assert body["consolidation_candidates"] == [
            "sibling_a",
            "sibling_b",
            "sibling_c",
        ]
        assert body["classifier_pending"] is True


class TestHandleStoreMergeSectionFailureModes:
    """#1352 review fix: merge_section RPC failures must fail closed.

    The RPC retry loop in _handle_store's mode="merge_section" branch sets
    action="conflict" (all retries exhausted) or action="error" (unhandled
    RPC exception) but previously fell through to the shared response block,
    which unconditionally returned stored=True with a null memory_id — a
    violation of the #658 contract that stored=True is the unambiguous
    success signal. These tests pin the fail-closed behavior.
    """

    @pytest.fixture(autouse=True)
    def _patch_client(self, monkeypatch):
        self.client = MagicMock()
        monkeypatch.setattr(server_module, "_get_client", lambda: self.client)

        async def _no_embed(_text):
            return {}

        monkeypatch.setattr(server_module, "_compute_write_embeddings", _no_embed)

        tbl = MagicMock()
        select_chain = MagicMock()
        tbl.select.return_value = select_chain
        # _handle_store's merge_section fetch chains .eq()/.is_() a variable
        # number of times depending on whether `project` is set (an extra
        # trailing .eq("project", ...) when it is) — make both self-chaining
        # so .limit().execute() lands on the same configured mock regardless.
        select_chain.eq.return_value = select_chain
        select_chain.is_.return_value = select_chain
        select_chain.limit.return_value.execute.return_value = MagicMock(data=[])
        self.client.table.return_value = tbl
        self.tbl = tbl

    @pytest.mark.asyncio
    async def test_conflict_after_retries_exhausted_returns_stored_false(self, monkeypatch):
        self.client.rpc.return_value.execute.return_value = MagicMock(
            data=[{"success": False, "memory_id": None, "conflict_reason": "updated_at mismatch"}]
        )
        emitted = []
        monkeypatch.setattr(
            events_canonical, "emit_event", lambda client, **kwargs: emitted.append(kwargs) or {}
        )

        result = await _handle_store(
            {
                "type": "project",
                "name": "test_merge_conflict",
                "content": "## [entry] foo — 2026-01-01\n\nbody",
                "project": "jarvis",
                "source_provenance": "session:test",
                "mode": "merge_section",
            }
        )

        assert len(result) == 1
        body = json.loads(result[0].text)
        assert body["stored"] is False
        assert body["action"] == "conflict"
        assert body["memory_id"] is None
        assert self.client.rpc.call_count == 3
        # #1582 AC2: the actual conflict_reason must be surfaced, not just
        # a generic "write did not persist" message.
        assert "updated_at mismatch" in body["message"]
        # #1582 AC4: the same detail must land in events_canonical, durably
        # queryable regardless of --debug=mcp.
        assert len(emitted) == 1
        assert emitted[0]["action"] == "merge_section_write_failed"
        assert emitted[0]["payload"]["detail"] == "updated_at mismatch"
        assert emitted[0]["payload"]["action"] == "conflict"

    @pytest.mark.asyncio
    async def test_rpc_exception_on_every_attempt_returns_stored_false(self, monkeypatch):
        self.client.rpc.side_effect = RuntimeError("connection reset")
        emitted = []
        monkeypatch.setattr(
            events_canonical, "emit_event", lambda client, **kwargs: emitted.append(kwargs) or {}
        )

        result = await _handle_store(
            {
                "type": "project",
                "name": "test_merge_rpc_error",
                "content": "## [entry] bar — 2026-01-01\n\nbody",
                "project": "jarvis",
                "source_provenance": "session:test",
                "mode": "merge_section",
            }
        )

        assert len(result) == 1
        body = json.loads(result[0].text)
        assert body["stored"] is False
        assert body["action"] == "error"
        assert body["memory_id"] is None
        # #1582 AC3: the caught exception's type + message must be surfaced,
        # not just a generic "write did not persist" message.
        assert "RuntimeError" in body["message"]
        assert "connection reset" in body["message"]
        # #1582 AC4: the same detail must land in events_canonical.
        assert len(emitted) == 1
        assert emitted[0]["action"] == "merge_section_write_failed"
        assert "RuntimeError" in emitted[0]["payload"]["detail"]
        assert "connection reset" in emitted[0]["payload"]["detail"]
        assert emitted[0]["payload"]["action"] == "error"

    @pytest.mark.asyncio
    async def test_rpc_exception_verified_as_already_persisted_returns_stored_true(self):
        """#1580: a Postgres RPC commits as part of executing the function,
        before the HTTP response reaches the client — if that response is
        lost in transit after commit (timeout, dropped connection), the
        client sees an exception even though the write already landed. Pins
        the fix: on exception, verify via a read before reporting failure,
        and treat a matching read as success instead of a false stored=False.

        Contrast with test_rpc_exception_on_every_attempt_returns_stored_false
        above, whose always-empty table mock means the verify read never
        matches — that test pins the still-correct "truly never persisted"
        path, this one pins the new "persisted despite the exception" path.
        """
        content = "## [entry] foo — 2026-01-01\n\nbody"
        responses = iter(
            [
                MagicMock(data=[]),  # initial fetch: no existing doc
                MagicMock(
                    data=[{"id": "verified-1", "content": content}]
                ),  # post-exception verify read
            ]
        )
        self.tbl.select.return_value.limit.return_value.execute.side_effect = lambda: next(
            responses
        )
        self.client.rpc.side_effect = RuntimeError("connection reset")

        result = await _handle_store(
            {
                "type": "project",
                "name": "test_merge_exception_but_persisted",
                "content": content,
                "project": "jarvis",
                "source_provenance": "session:test",
                "mode": "merge_section",
            }
        )

        body = json.loads(result[0].text)
        assert body["stored"] is True
        assert body["action"] == "merged"
        assert body["memory_id"] == "verified-1"
        # Confirmed via read on the first exception — no need to exhaust retries.
        assert self.client.rpc.call_count == 1

    @pytest.mark.asyncio
    async def test_success_on_first_attempt_still_returns_stored_true(self):
        self.client.rpc.return_value.execute.return_value = MagicMock(
            data=[{"success": True, "memory_id": "merged-1", "conflict_reason": None}]
        )

        result = await _handle_store(
            {
                "type": "project",
                "name": "test_merge_success",
                "content": "## [entry] baz — 2026-01-01\n\nbody",
                "project": "jarvis",
                "source_provenance": "session:test",
                "mode": "merge_section",
            }
        )

        body = json.loads(result[0].text)
        assert body["stored"] is True
        assert body["action"] == "merged"
        assert body["memory_id"] == "merged-1"
        assert self.client.rpc.call_count == 1

    @pytest.mark.asyncio
    async def test_merge_forwards_computed_embedding_to_rpc(self, monkeypatch):
        """#1352 review fix: merge_section must forward embed_fields to the RPC,
        same as the standard write path's data.update(embed_fields) — otherwise
        rows written via merge_section never get an embedding until a lazy
        backfill runs.
        """

        async def _real_embed(_text):
            return {
                "embedding": [0.1] * 512,
                "embedding_model": "voyage-3-lite",
                "embedding_version": "v2",
            }

        monkeypatch.setattr(server_module, "_compute_write_embeddings", _real_embed)

        self.client.rpc.return_value.execute.return_value = MagicMock(
            data=[{"success": True, "memory_id": "merged-2", "conflict_reason": None}]
        )

        await _handle_store(
            {
                "type": "project",
                "name": "test_merge_embedding_forward",
                "content": "## [entry] qux — 2026-01-01\n\nbody",
                "project": "jarvis",
                "source_provenance": "session:test",
                "mode": "merge_section",
            }
        )

        # A populated embedding also triggers the fire-and-forget auto-link
        # rpc call (semantic similarity search), so don't assume this is the
        # only rpc() call — pick out the merge_section_into_memory_upsert one.
        merge_calls = [
            c
            for c in self.client.rpc.call_args_list
            if c.args and c.args[0] == "merge_section_into_memory_upsert"
        ]
        assert len(merge_calls) == 1
        rpc_call = merge_calls[0]
        params = rpc_call.args[1] if len(rpc_call.args) > 1 else rpc_call.kwargs.get("params")
        assert params["p_embedding"] == [0.1] * 512
        assert params["p_embedding_model"] == "voyage-3-lite"
        assert params["p_embedding_version"] == "v2"
        assert params["p_embedding_v2"] is None
        assert params["p_embedding_model_v2"] is None
        assert params["p_embedding_version_v2"] is None

    @pytest.mark.asyncio
    async def test_merge_forwards_type_and_source_provenance_to_rpc(self):
        """#1352 review round 2: merge_section must forward the caller's type
        and source_provenance to the RPC, not rely on a hardcoded literal —
        `type` is NOT NULL with no default on the memories table, so a new
        row created via merge_section on a never-before-seen name fails
        without it, and a hardcoded source_provenance silently discards the
        validated value the handler requires from every caller.
        """
        self.client.rpc.return_value.execute.return_value = MagicMock(
            data=[{"success": True, "memory_id": "merged-3", "conflict_reason": None}]
        )

        await _handle_store(
            {
                "type": "decision",
                "name": "test_merge_type_forward",
                "content": "## [entry] quux — 2026-01-01\n\nbody",
                "project": "jarvis",
                "source_provenance": "session:test-provenance",
                "mode": "merge_section",
            }
        )

        merge_calls = [
            c
            for c in self.client.rpc.call_args_list
            if c.args and c.args[0] == "merge_section_into_memory_upsert"
        ]
        assert len(merge_calls) == 1
        rpc_call = merge_calls[0]
        params = rpc_call.args[1] if len(rpc_call.args) > 1 else rpc_call.kwargs.get("params")
        assert params["p_type"] == "decision"
        assert params["p_source_provenance"] == "session:test-provenance"

    @pytest.mark.asyncio
    async def test_merge_recomputes_embedding_after_conflict_retry(self, monkeypatch):
        """#1352 review round 3 finding #2: embed_fields/embedding were computed
        once, before the RPC retry loop, from the FIRST attempt's content. A
        conflicting first attempt re-fetches and re-merges fresh content for
        the retry, but without recomputing the embedding too, the retried
        write would persist a row whose embedding vector doesn't match its
        actual (re-merged) text. Pins that the second RPC attempt carries a
        freshly computed embedding, not the stale first one.
        """
        embed_calls = []

        async def _tracking_embed(text):
            embed_calls.append(text)
            return {"embedding": [float(len(embed_calls))] * 512}

        monkeypatch.setattr(server_module, "_compute_write_embeddings", _tracking_embed)

        conflict = MagicMock(
            data=[{"success": False, "memory_id": None, "conflict_reason": "updated_at mismatch"}]
        )
        success = MagicMock(
            data=[{"success": True, "memory_id": "merged-4", "conflict_reason": None}]
        )
        responses = iter([conflict, success])
        # Defensive: a populated embedding also fires the auto-link fire-and-
        # forget RPC call, which shares this same mock — fall back to `success`
        # for any call beyond the two the merge_section retry loop itself makes
        # rather than raising StopIteration (see test_merge_forwards_computed_
        # embedding_to_rpc above for the same caveat).
        self.client.rpc.return_value.execute.side_effect = lambda: next(responses, success)

        await _handle_store(
            {
                "type": "project",
                "name": "test_merge_embedding_retry",
                "content": "## [entry] retry — 2026-01-01\n\nbody",
                "project": "jarvis",
                "source_provenance": "session:test",
                "mode": "merge_section",
            }
        )

        assert len(embed_calls) == 2

        merge_calls = [
            c
            for c in self.client.rpc.call_args_list
            if c.args and c.args[0] == "merge_section_into_memory_upsert"
        ]
        assert len(merge_calls) == 2
        second_params = (
            merge_calls[1].args[1]
            if len(merge_calls[1].args) > 1
            else merge_calls[1].kwargs.get("params")
        )
        assert second_params["p_embedding"] == [2.0] * 512

    @pytest.mark.asyncio
    async def test_initial_fetch_exception_returns_graceful_error_not_raise(self):
        """#1352 review round 3 finding #3: the initial existing-row fetch used
        to be wrapped in a dead-code retry loop whose only real exception
        handling was `except ValueError`, unlike the RPC call further down
        which already degrades on the wider `except Exception`. A transient
        Supabase/network error here must not crash the request either.
        """
        self.tbl.select.return_value.limit.return_value.execute.side_effect = RuntimeError(
            "network blip"
        )

        result = await _handle_store(
            {
                "type": "project",
                "name": "test_merge_initial_fetch_error",
                "content": "## [entry] boom — 2026-01-01\n\nbody",
                "project": "jarvis",
                "source_provenance": "session:test",
                "mode": "merge_section",
            }
        )

        assert len(result) == 1
        assert "could not fetch existing document" in result[0].text
        assert self.client.rpc.call_count == 0

    @pytest.mark.asyncio
    async def test_retry_remerge_valueerror_calls_log_swallowed(self, monkeypatch):
        """#1352 review round 3 finding #4: the retry-path re-merge's
        `except ValueError` set action="error" and broke out of the loop but
        never reported the swallowed exception anywhere, unlike every other
        degrade-on-exception path in this module (`log_swallowed` convention,
        #1082). Pins that the retry-unparseable path is now observable.
        """
        swallowed = []
        monkeypatch.setattr(mem, "log_swallowed", lambda tag, exc: swallowed.append((tag, exc)))
        emitted = []
        monkeypatch.setattr(
            events_canonical, "emit_event", lambda client, **kwargs: emitted.append(kwargs) or {}
        )

        real_merge = mem._merge_section_into_markdown
        call_count = {"n": 0}

        def _merge_then_raise(existing_content, section_header, new_section_content):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return real_merge(existing_content, section_header, new_section_content)
            raise ValueError("document became unparseable")

        monkeypatch.setattr(mem, "_merge_section_into_markdown", _merge_then_raise)

        self.client.rpc.return_value.execute.return_value = MagicMock(
            data=[{"success": False, "memory_id": None, "conflict_reason": "updated_at mismatch"}]
        )

        result = await _handle_store(
            {
                "type": "project",
                "name": "test_merge_retry_unparseable",
                "content": "## [entry] retry-error — 2026-01-01\n\nbody",
                "project": "jarvis",
                "source_provenance": "session:test",
                "mode": "merge_section",
            }
        )

        body = json.loads(result[0].text)
        assert body["stored"] is False
        assert body["action"] == "error"
        assert any(
            tag == "memory._handle_store.merge_section_retry_unparseable" for tag, _ in swallowed
        )
        # #1582 AC3/AC4 sibling coverage: this ValueError-during-retry path
        # is a third "action=error" exit alongside the two covered above —
        # it must surface the same detail in the message and the event.
        assert "document became unparseable" in body["message"]
        assert len(emitted) == 1
        assert emitted[0]["action"] == "merge_section_write_failed"
        assert "document became unparseable" in emitted[0]["payload"]["detail"]


# ---------------------------------------------------------------------------
# #242: dual-embedding machinery — column/RPC mapping + dual-write
# ---------------------------------------------------------------------------


class TestModelSlotMapping:
    """#242: the model -> column/RPC table drives both read and write paths."""

    def test_voyage_3_lite_maps_to_v1_column(self):
        slot = _model_slot("voyage-3-lite")
        assert slot["embedding_column"] == "embedding"
        assert slot["rpc"] == "match_memories"

    def test_voyage_3_maps_to_v2_column(self):
        slot = _model_slot("voyage-3")
        assert slot["embedding_column"] == "embedding_v2"
        assert slot["rpc"] == "match_memories_v2"

    def test_unknown_model_falls_back_to_legacy(self):
        slot = _model_slot("nonexistent-model")
        assert slot["embedding_column"] == "embedding"
        assert slot["rpc"] == "match_memories"

    def test_upsert_fields_shape(self):
        fields = _embed_upsert_fields([0.1, 0.2], "voyage-3-lite")
        assert fields == {
            "embedding": [0.1, 0.2],
            "embedding_model": "voyage-3-lite",
            "embedding_version": "v2",
        }

    def test_upsert_fields_v2(self):
        fields = _embed_upsert_fields([0.3, 0.4], "voyage-3")
        assert fields == {
            "embedding_v2": [0.3, 0.4],
            "embedding_model_v2": "voyage-3",
            "embedding_version_v2": "v2",
        }

    def test_upsert_fields_unknown_returns_empty(self):
        assert _embed_upsert_fields([0.1], "no-such-model") == {}


class TestDualEmbedWrite:
    """#242: when SECONDARY is set, writes compute both embeddings."""

    @pytest.mark.asyncio
    async def test_secondary_unset_single_write(self, monkeypatch):
        calls: list[dict] = []

        async def fake_embed(text, input_type="document", model=None):
            calls.append({"model": model})
            return [0.1, 0.2, 0.3]

        monkeypatch.setattr(server_module, "_embed", fake_embed)
        monkeypatch.setattr(server_module, "EMBEDDING_MODEL_PRIMARY", "voyage-3-lite")
        monkeypatch.setattr(server_module, "EMBEDDING_MODEL_SECONDARY", None)

        fields = await _compute_write_embeddings("canonical text")

        assert "embedding" in fields
        assert "embedding_model" in fields
        assert fields["embedding_model"] == "voyage-3-lite"
        assert "embedding_v2" not in fields
        assert len(calls) == 1
        assert calls[0]["model"] == "voyage-3-lite"

    @pytest.mark.asyncio
    async def test_secondary_set_dual_write(self, monkeypatch):
        calls: list[dict] = []

        async def fake_embed(text, input_type="document", model=None):
            calls.append({"model": model})
            return [0.1] * 512 if model == "voyage-3-lite" else [0.9] * 1024

        monkeypatch.setattr(server_module, "_embed", fake_embed)
        monkeypatch.setattr(server_module, "EMBEDDING_MODEL_PRIMARY", "voyage-3-lite")
        monkeypatch.setattr(server_module, "EMBEDDING_MODEL_SECONDARY", "voyage-3")

        fields = await _compute_write_embeddings("canonical text")

        assert fields["embedding"] == [0.1] * 512
        assert fields["embedding_v2"] == [0.9] * 1024
        assert fields["embedding_model"] == "voyage-3-lite"
        assert fields["embedding_model_v2"] == "voyage-3"
        assert {c["model"] for c in calls} == {"voyage-3-lite", "voyage-3"}

    @pytest.mark.asyncio
    async def test_secondary_failure_single_leg(self, monkeypatch):
        async def fake_embed(text, input_type="document", model=None):
            if model == "voyage-3":
                return None
            return [0.1] * 512

        monkeypatch.setattr(server_module, "_embed", fake_embed)
        monkeypatch.setattr(server_module, "EMBEDDING_MODEL_PRIMARY", "voyage-3-lite")
        monkeypatch.setattr(server_module, "EMBEDDING_MODEL_SECONDARY", "voyage-3")

        fields = await _compute_write_embeddings("canonical text")
        assert fields["embedding"] == [0.1] * 512
        assert "embedding_v2" not in fields

    @pytest.mark.asyncio
    async def test_primary_failure_no_write(self, monkeypatch):
        async def fake_embed(text, input_type="document", model=None):
            return None

        monkeypatch.setattr(server_module, "_embed", fake_embed)
        monkeypatch.setattr(server_module, "EMBEDDING_MODEL_PRIMARY", "voyage-3-lite")
        monkeypatch.setattr(server_module, "EMBEDDING_MODEL_SECONDARY", "voyage-3")

        fields = await _compute_write_embeddings("canonical text")
        assert fields == {}

    @pytest.mark.asyncio
    async def test_secondary_equals_primary_no_duplicate_call(self, monkeypatch):
        calls: list[dict] = []

        async def fake_embed(text, input_type="document", model=None):
            calls.append({"model": model})
            return [0.1] * 512

        monkeypatch.setattr(server_module, "_embed", fake_embed)
        monkeypatch.setattr(server_module, "EMBEDDING_MODEL_PRIMARY", "voyage-3-lite")
        monkeypatch.setattr(server_module, "EMBEDDING_MODEL_SECONDARY", "voyage-3-lite")

        fields = await _compute_write_embeddings("canonical text")
        assert len(calls) == 1
        assert "embedding" in fields
        assert "embedding_v2" not in fields


# =========================================================================
# Known unknowns — retrieval gaps + unsatisfied queries (#249)
# =========================================================================


class TestKnownUnknowns:
    """Unit tests for known_unknowns insertion + dedup + resolution."""

    @pytest.mark.asyncio
    async def test_known_unknowns_insert_on_low_sim(self):
        mock_client = MagicMock()

        mock_select_chain = MagicMock()
        mock_select_chain.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[]
        )

        mock_insert = MagicMock()
        mock_update = MagicMock()

        mock_table = MagicMock()
        mock_table.select.return_value = mock_select_chain
        mock_table.insert.return_value = mock_insert
        mock_table.update.return_value = mock_update
        mock_client.table.return_value = mock_table

        await _upsert_known_unknown(
            mock_client,
            query="what is the meaning of life",
            query_embedding=[0.1, 0.2, 0.3],
            top_similarity=0.3,
            top_memory_id="mem-123",
            context={"project": "jarvis"},
        )

        mock_insert.execute.assert_called_once()
        insert_payload = mock_table.insert.call_args.args[0]
        assert insert_payload["query"] == "what is the meaning of life"
        assert insert_payload["top_similarity"] == 0.3
        assert insert_payload["top_memory_id"] == "mem-123"
        assert insert_payload["query_embedding"] is None
        assert not mock_update.execute.called

    @pytest.mark.asyncio
    async def test_known_unknowns_dedup_increments_hit_count(self):
        mock_client = MagicMock()

        existing_embedding = [0.10] * 512
        similar_embedding = [0.11] * 512

        mock_select_return = MagicMock()
        mock_select_return.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "uk-1", "query_embedding": existing_embedding, "hit_count": 5}]
        )

        mock_update_return = MagicMock()
        mock_insert_return = MagicMock()

        mock_table = MagicMock()
        mock_table.select.return_value = mock_select_return
        mock_table.update.return_value = mock_update_return
        mock_table.insert.return_value = mock_insert_return
        mock_client.table.return_value = mock_table

        await _upsert_known_unknown(
            mock_client,
            query="what is the meaning of existence",
            query_embedding=similar_embedding,
            top_similarity=0.35,
            top_memory_id="mem-456",
        )

        select_cols = mock_table.select.call_args.args[0]
        assert "hit_count" in select_cols

        mock_table.update.assert_called_once()
        update_payload = mock_table.update.call_args.args[0]
        assert update_payload["hit_count"] == 6

        assert not mock_insert_return.execute.called

    @pytest.mark.asyncio
    async def test_known_unknowns_resolution_on_store(self):
        mock_client = MagicMock()
        unknown_embedding = [0.5, 0.5, 0.0]

        mock_select = MagicMock()
        mock_eq = MagicMock()
        mock_eq.execute.return_value = MagicMock(
            data=[{"id": "uk-2", "query_embedding": unknown_embedding}]
        )
        mock_select.eq.return_value = mock_eq

        mock_update = MagicMock()
        mock_update_eq = MagicMock()
        mock_update_eq.execute.return_value = MagicMock()
        mock_update.eq.return_value = mock_update_eq

        def table_side_effect(table_name):
            if table_name == "known_unknowns":
                result = MagicMock()
                result.select.return_value = mock_select
                result.update.return_value = mock_update
                return result
            return MagicMock()

        mock_client.table.side_effect = table_side_effect

        memory_embedding = [0.6, 0.55, 0.1]
        await _resolve_known_unknowns(mock_client, memory_embedding, "mem-789")

        assert mock_update.eq.called
