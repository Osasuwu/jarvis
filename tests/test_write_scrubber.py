"""Tests for the MCP write-path Tier-2 secret-scrubber gate (#555).

Covers the standalone ``write_scrubber`` helper module plus its integration
into the two write paths (``_handle_store``, ``_handle_record_decision``).

Privacy invariant under test: when a write is blocked, NO value from the
blocked payload appears in the error, the event row, or anywhere else —
only pattern names + fire counts.

Test secrets are constructed dynamically (prefix + entropy concatenation) so
GitHub's static secret scanner does not flag this file — same convention as
tests/test_secret_scrubber.py.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock

import pytest

import write_scrubber
from server import _handle_store, _handle_record_decision
import server as server_module

from test_record_decision_helpers import make_client


# A realistic OpenAI-style key: prefix + 26 entropy chars (matches
# sk-[A-Za-z0-9]{20,}). Split so the static scanner never sees a whole token.
FAKE_OPENAI_KEY = "sk-proj" + "AbCdEfGhIjKlMnOpQrStUvWxYz"

# One fake per remaining blocking pattern (same split-construction convention as
# tests/test_secret_scrubber.py) so a regression in any single scrubber pattern
# is caught at the write-gate layer, not just for api_key_openai.
FAKE_GITHUB_TOKEN = "ghp_" + "ABCDEFGHIJKLM" + "NOPQRSTUVWXYZabcdefghij123456"
FAKE_SLACK_TOKEN = "xoxb" + "-1111111111-aaaaaaaaaaaaaaaaaaaa"
FAKE_JWT = "eyJhbGciOiJIUzI1NiJ9" + "." + "eyJzdWIiOiIxMjM0NTY3ODkwIn0" + ".signature_part_here"
FAKE_AWS_KEY = "AKIA" + "IOSFODNN7EXAMPLE"
FAKE_ENV_BLOCK = "```env\nDB_PASSWORD=supersecretpassword123\n```"

# (pattern name, text that fires exactly that blocking pattern)
BLOCKING_PATTERN_CASES = [
    ("api_key_openai", FAKE_OPENAI_KEY),
    ("api_key_github", FAKE_GITHUB_TOKEN),
    ("api_key_slack", FAKE_SLACK_TOKEN),
    ("api_key_jwt", FAKE_JWT),
    ("api_key_aws", FAKE_AWS_KEY),
    ("env_block", FAKE_ENV_BLOCK),
]


# ── scan_fields ───────────────────────────────────────────────────────────


class TestScanFields:
    def test_clean_fields_no_fires(self):
        fires = write_scrubber.scan_fields(
            {"name": "normal name", "content": "ordinary text", "tags": ["a", "b"]}
        )
        assert fires == {}

    def test_secret_in_str_field_fires(self):
        fires = write_scrubber.scan_fields({"content": f"key is {FAKE_OPENAI_KEY}"})
        assert fires.get("api_key_openai") == 1

    def test_secret_in_list_field_fires(self):
        fires = write_scrubber.scan_fields({"tags": ["fine", f"{FAKE_OPENAI_KEY}"]})
        assert fires.get("api_key_openai") == 1

    def test_counts_aggregate_across_fields(self):
        fires = write_scrubber.scan_fields({"name": FAKE_OPENAI_KEY, "content": FAKE_OPENAI_KEY})
        assert fires.get("api_key_openai") == 2

    def test_non_string_values_skipped(self):
        # ints / None / dicts must not raise — only str + list-of-str scanned.
        fires = write_scrubber.scan_fields(
            {"confidence": 0.9, "flag": None, "meta": {"x": 1}, "content": "clean"}
        )
        assert fires == {}

    def test_scrub_raising_is_contained_per_field(self, monkeypatch):
        """MAJOR-fix: a scrub() crash on one field must fail OPEN (skip that
        field, keep scanning the rest) — never propagate and crash the write.
        Also asserts the field name is logged but the value is not."""

        def _boom(text):
            if "BOOM" in text:
                raise ValueError("scrubber exploded")
            return text, {}

        monkeypatch.setattr(write_scrubber, "scrub", _boom)
        # First field raises, second is clean → no exception, empty totals.
        fires = write_scrubber.scan_fields({"bad": "trigger BOOM here", "good": "ordinary text"})
        assert fires == {}

    def test_scrub_raising_does_not_leak_value_to_stderr(self, monkeypatch, capsys):
        """Privacy invariant: the per-field crash log carries the exception
        *type* + field name only — never the raised exception's str() (which
        could embed the input text)."""

        secret_marker = "S3CR3T_" + "PAYLOAD_VALUE"

        def _boom(text):
            raise ValueError(text)  # exception str() == the input text

        monkeypatch.setattr(write_scrubber, "scrub", _boom)
        write_scrubber.scan_fields({"content": secret_marker})
        err = capsys.readouterr().err
        assert "ValueError" in err
        assert "content" in err
        assert secret_marker not in err


# ── rejection_error ───────────────────────────────────────────────────────


class TestRejectionError:
    def test_shape(self):
        payload = json.loads(write_scrubber.rejection_error({"api_key_openai": 1}))
        assert payload["error"] == "secret_pattern_detected"
        assert payload["patterns"] == {"api_key_openai": 1}

    def test_carries_only_names_and_counts_no_value(self):
        body = write_scrubber.rejection_error({"api_key_openai": 1})
        # The literal secret never appears in the rejection string.
        assert FAKE_OPENAI_KEY not in body


# ── log_block_event ───────────────────────────────────────────────────────


class TestLogBlockEvent:
    def test_inserts_counter_event_no_values(self):
        client = MagicMock()
        write_scrubber.log_block_event(client, {"api_key_openai": 2}, write_path="memory_store")

        client.table.assert_called_with("events")
        row = client.table.return_value.insert.call_args.args[0]
        assert row["event_type"] == "mcp_write_scrubber_block"
        assert row["severity"] in ("critical", "high", "medium", "low", "info")
        assert row["repo"] == "Osasuwu/jarvis"
        assert row["payload"]["patterns"] == {"api_key_openai": 2}
        assert row["payload"]["write_path"] == "memory_store"
        # No payload value leaks into the event row.
        assert FAKE_OPENAI_KEY not in json.dumps(row)

    def test_swallows_db_errors(self):
        client = MagicMock()
        client.table.side_effect = Exception("DB down")
        # Must not raise — logging is fire-and-forget.
        write_scrubber.log_block_event(client, {"x": 1}, write_path="memory_store")


# ── check_write (combined gate) ───────────────────────────────────────────


class TestCheckWrite:
    def test_clean_returns_none_no_event(self):
        client = MagicMock()
        out = write_scrubber.check_write(
            client, {"content": "all clean"}, write_path="memory_store"
        )
        assert out is None
        client.table.assert_not_called()

    def test_fired_returns_error_and_logs_event(self):
        client = MagicMock()
        out = write_scrubber.check_write(
            client, {"content": FAKE_OPENAI_KEY}, write_path="memory_store"
        )
        assert out is not None
        payload = json.loads(out)
        assert payload["error"] == "secret_pattern_detected"
        client.table.assert_called_with("events")

    def test_user_path_does_not_block(self):
        """AC#4: ~26% of the live corpus carries absolute user paths. A path
        is a normalization concern (scrub-and-keep), not a write-blocking
        secret leak — it must NOT reject the write or emit a block event."""
        client = MagicMock()
        out = write_scrubber.check_write(
            client,
            {"content": r"config at C:\Users\alice\.claude\settings.json"},
            write_path="memory_store",
        )
        assert out is None
        client.table.assert_not_called()

    def test_secret_blocks_even_alongside_path(self):
        """A real secret still blocks even when a (non-blocking) path is also
        present; the block payload carries only the secret pattern."""
        client = MagicMock()
        out = write_scrubber.check_write(
            client,
            {"content": f"/home/bob/app uses {FAKE_OPENAI_KEY}"},
            write_path="memory_store",
        )
        payload = json.loads(out)
        assert payload["patterns"] == {"api_key_openai": 1}
        assert "path_username" not in payload["patterns"]


# ── every blocking pattern is exercised, not just api_key_openai ──────────


class TestAllBlockingPatterns:
    @pytest.mark.parametrize("pattern_name,text", BLOCKING_PATTERN_CASES)
    def test_each_blocking_pattern_blocks(self, pattern_name, text):
        client = MagicMock()
        out = write_scrubber.check_write(client, {"content": text}, write_path="memory_store")
        assert out is not None, f"{pattern_name} did not block the write"
        assert pattern_name in json.loads(out)["patterns"]
        # The raw token never leaks into the rejection payload.
        assert text not in out


# ── fail-open when the scrubber lib is unavailable ────────────────────────


class TestScrubUnavailable:
    def test_scan_fields_fail_open_when_scrub_none(self, monkeypatch):
        """Security invariant: when scrub is unavailable the gate fails OPEN
        (availability > over-blocking) — documented + must stay covered."""
        monkeypatch.setattr(write_scrubber, "scrub", None)
        assert write_scrubber.scan_fields({"content": FAKE_OPENAI_KEY}) == {}

    def test_check_write_fail_open_when_scrub_none(self, monkeypatch):
        monkeypatch.setattr(write_scrubber, "scrub", None)
        client = MagicMock()
        out = write_scrubber.check_write(
            client, {"content": FAKE_OPENAI_KEY}, write_path="memory_store"
        )
        assert out is None
        client.table.assert_not_called()


# ── SCRUB_ONLY_PATTERNS coupling invariant ────────────────────────────────


class TestScrubOnlyCoupling:
    def test_scrub_only_names_are_real_pattern_names(self):
        """The import-time drift guard warns (no longer crashes) if
        SCRUB_ONLY_PATTERNS names a pattern secret_scrubber no longer emits.
        This test pins the invariant in committed code so a rename in
        secret_scrubber.py that silently turns path exclusion into a no-op
        (re-blocking ~26% of path-bearing writes) fails CI here."""
        assert write_scrubber.SCRUB_ONLY_PATTERNS <= write_scrubber._KNOWN_PATTERN_NAMES


# ── _handle_store integration ─────────────────────────────────────────────


class TestStoreGate:
    @pytest.fixture(autouse=True)
    def _patch(self, monkeypatch):
        self.client = MagicMock()
        monkeypatch.setattr(server_module, "_get_client", lambda: self.client)

        self.embed_calls: list = []

        async def _spy_embed(_text):
            self.embed_calls.append(_text)
            return {}

        monkeypatch.setattr(server_module, "_compute_write_embeddings", _spy_embed)

    async def test_secret_in_content_blocks_no_embed_no_insert(self):
        result = await _handle_store(
            {
                "type": "project",
                "name": "leaky",
                "content": f"my key {FAKE_OPENAI_KEY}",
                "project": "jarvis",
                "source_provenance": "session:test",
            }
        )

        body = json.loads(result[0].text)
        assert body["error"] == "secret_pattern_detected"
        assert "api_key_openai" in body["patterns"]
        # No embedding computed.
        assert self.embed_calls == []
        # No memory row written — only the events insert is permitted.
        memory_writes = [
            c for c in self.client.table.call_args_list if c.args and c.args[0] == "memories"
        ]
        assert memory_writes == []
        # The secret never appears in the returned error text.
        assert FAKE_OPENAI_KEY not in result[0].text

    async def test_block_event_is_actually_logged_on_async_path(self):
        """MAJOR-fix: under asyncio_mode=auto the handler runs in a loop, so the
        block-event insert is dispatched as a detached task. Without draining,
        no test ever observes it. Drain with ``asyncio.sleep(0)`` and assert the
        ``events`` insert fired with the value-free counter row."""
        result = await _handle_store(
            {
                "type": "project",
                "name": "leaky",
                "content": f"my key {FAKE_OPENAI_KEY}",
                "project": "jarvis",
                "source_provenance": "session:test",
            }
        )
        assert json.loads(result[0].text)["error"] == "secret_pattern_detected"

        # Let the detached _log_block_event_async task run to completion.
        for _ in range(5):
            await asyncio.sleep(0)

        events_inserts = [
            c for c in self.client.table.call_args_list if c.args and c.args[0] == "events"
        ]
        assert events_inserts, "block event was never inserted on the async path"
        row = self.client.table.return_value.insert.call_args.args[0]
        assert row["event_type"] == "mcp_write_scrubber_block"
        assert row["payload"]["write_path"] == "memory_store"
        assert FAKE_OPENAI_KEY not in json.dumps(row)

    async def test_secret_in_name_blocks(self):
        result = await _handle_store(
            {
                "type": "project",
                "name": FAKE_OPENAI_KEY,
                "content": "clean content",
                "project": "jarvis",
                "source_provenance": "session:test",
            }
        )
        assert json.loads(result[0].text)["error"] == "secret_pattern_detected"

    async def test_clean_store_passes_gate(self):
        tbl = MagicMock()
        tbl.upsert.return_value.execute.return_value = MagicMock(data=[{"id": "ok-1"}])
        self.client.table.return_value = tbl

        result = await _handle_store(
            {
                "type": "project",
                "name": "fine",
                "content": "nothing secret here",
                "project": "jarvis",
                "source_provenance": "session:test",
            }
        )
        # Reaches the normal store path → embedding spy was called.
        assert self.embed_calls
        assert "error" not in result[0].text


# ── _handle_record_decision integration ───────────────────────────────────


class TestDecisionGate:
    async def test_secret_in_rationale_blocks_no_episode(self, monkeypatch):
        client = make_client("ep-blocked")
        monkeypatch.setattr(server_module, "_get_client", lambda: client)

        result = await _handle_record_decision(
            {
                "decision": "do the thing",
                "rationale": f"because {FAKE_OPENAI_KEY} is the key",
                "reversibility": "reversible",
                "actor": "session:test",
            }
        )

        body = json.loads(result[0].text)
        assert body["error"] == "secret_pattern_detected"
        # No episode written.
        episode_inserts = [
            c for c in client.table.call_args_list if c.args and c.args[0] == "episodes"
        ]
        assert episode_inserts == []
        assert FAKE_OPENAI_KEY not in result[0].text

    async def test_secret_in_decision_blocks(self, monkeypatch):
        client = make_client("ep-blocked")
        monkeypatch.setattr(server_module, "_get_client", lambda: client)

        result = await _handle_record_decision(
            {
                "decision": f"adopt {FAKE_OPENAI_KEY} as the key",
                "rationale": "clean rationale",
                "reversibility": "reversible",
            }
        )
        body = json.loads(result[0].text)
        assert body["error"] == "secret_pattern_detected"
        episode_inserts = [
            c for c in client.table.call_args_list if c.args and c.args[0] == "episodes"
        ]
        assert episode_inserts == []

    async def test_secret_in_alternatives_blocks(self, monkeypatch):
        client = make_client("ep-blocked")
        monkeypatch.setattr(server_module, "_get_client", lambda: client)

        result = await _handle_record_decision(
            {
                "decision": "clean decision",
                "rationale": "clean rationale",
                "alternatives_considered": [f"option using {FAKE_OPENAI_KEY}"],
                "reversibility": "reversible",
            }
        )
        assert json.loads(result[0].text)["error"] == "secret_pattern_detected"

    async def test_clean_decision_passes_gate(self, monkeypatch):
        client = make_client("ep-ok")
        monkeypatch.setattr(server_module, "_get_client", lambda: client)

        result = await _handle_record_decision(
            {
                "decision": "clean decision",
                "rationale": "clean rationale",
                "reversibility": "reversible",
            }
        )
        # Reaches the normal path → episode id surfaced, no error.
        assert "ep-ok" in result[0].text
        assert "secret_pattern_detected" not in result[0].text
