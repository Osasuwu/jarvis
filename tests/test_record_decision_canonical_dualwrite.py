"""Integration tests for record_decision dual-write (#477).

The handler now writes to BOTH the legacy ``episodes`` table AND the
canonical ``events_canonical`` substrate. These tests verify:

1. Both tables receive an insert on a successful call.
2. OTel-shaped keys appear in the events_canonical payload only when
   ``llm`` metadata is supplied.
3. A failure in the events_canonical write does NOT propagate — the
   episodes write is still surfaced as success.
4. Without ``llm`` metadata, the events_canonical row has no cost
   columns (substrate uses NULL — design 1-pager §1).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from server import _handle_record_decision
import events_canonical as events_canonical_mod


@pytest.fixture(autouse=True)
def _isolate_buffer() -> None:
    events_canonical_mod._buffer_clear_for_test()
    yield
    events_canonical_mod._buffer_clear_for_test()


def _dual_write_client(
    *,
    canonical_raises: Exception | None = None,
    inserted_episode_id: str = "ep-123",
) -> MagicMock:
    """Stub that distinguishes inserts by table name.

    Caches one Table mock per name on first request — re-requests
    return the same mock, so .insert.call_args_list captures every
    payload sent to that table.
    """
    client = MagicMock()
    tables: dict[str, MagicMock] = {}

    def _table_factory(name: str) -> MagicMock:
        if name in tables:
            return tables[name]
        table = MagicMock()
        if name == "episodes":
            table.insert.return_value.execute.return_value = MagicMock(
                data=[{"id": inserted_episode_id, "created_at": "2026-04-29T15:00:00Z"}]
            )
        elif name == "events_canonical":
            insert = MagicMock()
            if canonical_raises is not None:
                insert.side_effect = canonical_raises
            else:
                insert.return_value.execute.return_value = MagicMock(
                    data=[{"event_id": "ev-456", "trace_id": "deadbeef" * 4}]
                )
            table.insert = insert
        elif name == "memories":
            chain = MagicMock()
            leaf = MagicMock()
            leaf.data = []
            chain.eq.return_value.is_.return_value.order.return_value.limit.return_value.execute.return_value = leaf
            chain.eq.return_value.is_.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = leaf
            chain.eq.return_value.eq.return_value.is_.return_value.order.return_value.limit.return_value.execute.return_value = leaf
            table.select.return_value = chain
        else:
            table.insert.return_value.execute.return_value = MagicMock(data=[])
            table.select.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[]
            )
        tables[name] = table
        # Stash the cache on client so tests can introspect.
        client._tables = tables  # type: ignore[attr-defined]
        return table

    client.table.side_effect = _table_factory
    client._tables = tables  # type: ignore[attr-defined]
    return client


def _calls_to_table(client: MagicMock, name: str) -> list:
    """Return the list of insert payloads executed against ``name``."""
    tables = getattr(client, "_tables", {})
    table = tables.get(name)
    if table is None:
        return []
    return [c.args[0] for c in table.insert.call_args_list if c.args]


# ---------------------------------------------------------------------------


class TestDualWriteHappyPath:
    @pytest.mark.asyncio
    async def test_writes_to_both_tables(self, monkeypatch):
        client = _dual_write_client()
        monkeypatch.setattr("server._get_client", lambda: client)

        result = await _handle_record_decision(
            {
                "decision": "Pick X",
                "rationale": "Because of Y",
                "reversibility": "reversible",
            }
        )
        assert "Decision recorded" in result[0].text

        episode_inserts = _calls_to_table(client, "episodes")
        canonical_inserts = _calls_to_table(client, "events_canonical")
        assert len(episode_inserts) == 1, f"expected 1 episodes insert, got {len(episode_inserts)}"
        assert len(canonical_inserts) == 1, f"expected 1 events_canonical insert, got {len(canonical_inserts)}"

        # Episodes path preserved (legacy contract).
        ep = episode_inserts[0]
        assert ep["kind"] == "decision_made"
        assert ep["payload"]["decision"] == "Pick X"

        # Canonical row carries action + actor + trace_id.
        ec = canonical_inserts[0]
        assert ec["action"] == "decision_made"
        assert ec["actor"]  # default 'skill:unknown' or whatever passed
        assert "trace_id" in ec and isinstance(ec["trace_id"], str)
        assert ec["outcome"] == "success"

    @pytest.mark.asyncio
    async def test_canonical_payload_includes_episode_id_link(self, monkeypatch):
        client = _dual_write_client(inserted_episode_id="ep-link-test")
        monkeypatch.setattr("server._get_client", lambda: client)

        await _handle_record_decision(
            {
                "decision": "x",
                "rationale": "y",
                "reversibility": "reversible",
            }
        )
        canonical = _calls_to_table(client, "events_canonical")[0]
        assert canonical["payload"]["episode_id"] == "ep-link-test"


class TestOTelKeysFromLLMMetadata:
    @pytest.mark.asyncio
    async def test_otel_keys_present_when_llm_provided(self, monkeypatch):
        client = _dual_write_client()
        monkeypatch.setattr("server._get_client", lambda: client)

        await _handle_record_decision(
            {
                "decision": "x",
                "rationale": "y",
                "reversibility": "reversible",
                "llm": {
                    "model": "claude-haiku-4-5-20251001",
                    "input_tokens": 1234,
                    "output_tokens": 567,
                    "cost_usd": 0.0125,
                    "provider": "anthropic",
                    "operation": "chat",
                },
            }
        )
        canonical = _calls_to_table(client, "events_canonical")[0]
        p = canonical["payload"]
        assert p["gen_ai.request.model"] == "claude-haiku-4-5-20251001"
        assert p["gen_ai.usage.input_tokens"] == 1234
        assert p["gen_ai.usage.output_tokens"] == 567
        assert p["gen_ai.usage.cost_usd"] == 0.0125
        assert p["gen_ai.provider.name"] == "anthropic"
        assert p["gen_ai.operation.name"] == "chat"
        # cost columns populated
        assert canonical["cost_tokens"] == 1234 + 567
        assert canonical["cost_usd"] == 0.0125

    @pytest.mark.asyncio
    async def test_otel_keys_absent_when_no_llm_metadata(self, monkeypatch):
        client = _dual_write_client()
        monkeypatch.setattr("server._get_client", lambda: client)

        await _handle_record_decision(
            {
                "decision": "x",
                "rationale": "y",
                "reversibility": "reversible",
            }
        )
        canonical = _calls_to_table(client, "events_canonical")[0]
        p = canonical["payload"]
        for key in (
            "gen_ai.request.model",
            "gen_ai.usage.input_tokens",
            "gen_ai.usage.output_tokens",
            "gen_ai.usage.cost_usd",
            "gen_ai.provider.name",
            "gen_ai.operation.name",
        ):
            assert key not in p, f"OTel key {key!r} unexpectedly set"
        assert "cost_tokens" not in canonical
        assert "cost_usd" not in canonical


class TestCanonicalFailureDoesNotBreakEpisodeWrite:
    @pytest.mark.asyncio
    async def test_substrate_failure_returns_success(self, monkeypatch):
        client = _dual_write_client(
            canonical_raises=RuntimeError("connection dropped")
        )
        monkeypatch.setattr("server._get_client", lambda: client)

        result = await _handle_record_decision(
            {
                "decision": "x",
                "rationale": "y",
                "reversibility": "reversible",
            }
        )
        # Episode write succeeded — caller sees success.
        assert "Decision recorded" in result[0].text

        # Episode insert happened. Canonical insert was attempted.
        assert _calls_to_table(client, "episodes")
        # Buffer absorbed the failed canonical event.
        assert events_canonical_mod._buffer_len_for_test() == 1
