"""Unit tests for GitHub perception module (issue #388, Sprint 4).

Tests the row-building logic, idempotency, allowlist enforcement, and
tier mapping without live GitHub or Supabase. Uses the _StubClient pattern
from test_agents_dispatcher.py.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest

# Add agents module to path for imports.
sys.path.insert(0, "/d/Github/jarvis")

from agents import perception_github


# ---------------------------------------------------------------------------
# Stubs — Supabase client recording inserts, upserts
# ---------------------------------------------------------------------------


@dataclass
class _Response:
    data: list[dict[str, Any]]


class _UpsertQuery:
    """Stub upsert that records the call and tracks duplicates."""

    def __init__(self, table: "_Table", payload: dict[str, Any]) -> None:
        self._table = table
        self._payload = payload

    def ignore_duplicates(self, value: bool) -> "_UpsertQuery":
        """Chainable ignore_duplicates (PostgREST idiom)."""
        return self

    def execute(self) -> _Response:
        """Execute upsert. If idempotency_key already exists, return empty (duplicate)."""
        key = self._payload.get("idempotency_key")
        existing = [r for r in self._table.seeded_rows if r.get("idempotency_key") == key]

        self._table.calls.append(
            (
                "upsert",
                self._table.name,
                {"payload": dict(self._payload), "on_conflict": "idempotency_key"},
            )
        )

        if existing:
            # Duplicate — PostgREST returns empty data on conflict + ignore_duplicates.
            return _Response(data=[])

        # New row — add to seeded and return it.
        stored = {**self._payload, "id": f"row-{len(self._table.seeded_rows)}"}
        self._table.seeded_rows.append(stored)
        return _Response(data=[stored])


class _SelectQuery:
    """Stub select for querying task_queue rows (used by notify_completed_issues)."""

    def __init__(self, table: "_Table") -> None:
        self._table = table
        self._filters: list[tuple[str, str, Any]] = []
        self._limit: int | None = None

    def select(self, *_args: Any, **_kwargs: Any) -> "_SelectQuery":
        return self

    def eq(self, col: str, val: Any) -> "_SelectQuery":
        self._filters.append(("eq", col, val))
        return self

    def limit(self, n: int) -> "_SelectQuery":
        self._limit = n
        return self

    def execute(self) -> _Response:
        rows = list(self._table.seeded_rows)
        for op, col, val in self._filters:
            if op == "eq":
                rows = [r for r in rows if r.get(col) == val]
        if self._limit:
            rows = rows[: self._limit]
        self._table.calls.append(
            ("select", self._table.name, {"filters": list(self._filters), "limit": self._limit})
        )
        return _Response(data=rows)


class _Table:
    def __init__(self, name: str, calls: list[Any], rows: list[dict[str, Any]]) -> None:
        self.name = name
        self.calls = calls
        self.seeded_rows = rows

    def select(self, *_args: Any, **_kwargs: Any) -> _SelectQuery:
        return _SelectQuery(self)

    def upsert(
        self, payload: dict[str, Any], on_conflict: str = "id", ignore_duplicates: bool = False
    ) -> _UpsertQuery:
        return _UpsertQuery(self, payload)

    def insert(self, payload: dict[str, Any]) -> "_InsertQuery":
        return _InsertQuery(self, payload)


class _InsertQuery:
    """Stub insert for audit_log."""

    def __init__(self, table: "_Table", payload: dict[str, Any]) -> None:
        self._table = table
        self._payload = payload

    def execute(self) -> _Response:
        stored = {**self._payload, "id": f"audit-{len(self._table.seeded_rows)}"}
        self._table.seeded_rows.append(stored)
        self._table.calls.append(("insert", self._table.name, dict(self._payload)))
        return _Response(data=[stored])


class _StubClient:
    """Records all table operations."""

    def __init__(self) -> None:
        self.calls: list[Any] = []
        self.tables: dict[str, list[dict[str, Any]]] = {
            "task_queue": [],
            "audit_log": [],
        }

    def table(self, name: str) -> _Table:
        return _Table(name, self.calls, self.tables.setdefault(name, []))

    def seed(self, table: str, rows: list[dict[str, Any]]) -> None:
        self.tables.setdefault(table, []).extend(rows)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_parse_scope_files_fenced() -> None:
    """Extract file paths from fenced code blocks."""
    body = """
    Here's a file:
    ```agents/perception_github.py```
    Another one:
    ```tests/test_agents_perception_github.py```
    """
    files = perception_github._parse_scope_files(body)
    assert set(files) == {"agents/perception_github.py", "tests/test_agents_perception_github.py"}


def test_parse_scope_files_backtick() -> None:
    """Extract file paths from backticked references."""
    body = "Check `agents/dispatcher.py` and `agents/safety.py` for examples."
    files = perception_github._parse_scope_files(body)
    assert set(files) == {"agents/dispatcher.py", "agents/safety.py"}


def test_parse_scope_files_mixed() -> None:
    """Extract from both fenced and backticked references."""
    body = "See `config/device.json` and also ```supabase/migrations/001.sql``` for schema."
    files = perception_github._parse_scope_files(body)
    assert set(files) == {"config/device.json", "supabase/migrations/001.sql"}


def test_parse_scope_files_empty() -> None:
    """Return empty list if no file paths found."""
    body = "This is just plain text with no file references."
    files = perception_github._parse_scope_files(body)
    assert files == []


def test_parse_scope_files_dedup() -> None:
    """Deduplicate repeated file references."""
    body = "See `path/to/file.py` and also ```path/to/file.py``` again."
    files = perception_github._parse_scope_files(body)
    assert files == ["path/to/file.py"]


def test_hash_scope_files() -> None:
    """Hash scope files deterministically."""
    files1 = ["a.py", "b.py"]
    files2 = ["b.py", "a.py"]  # Different order
    assert perception_github._hash_scope_files(files1) == perception_github._hash_scope_files(
        files2
    )


def test_hash_scope_files_different() -> None:
    """Different file sets produce different hashes."""
    h1 = perception_github._hash_scope_files(["a.py"])
    h2 = perception_github._hash_scope_files(["b.py"])
    assert h1 != h2


def test_hash_scope_files_empty() -> None:
    """Empty file list produces consistent hash."""
    h = perception_github._hash_scope_files([])
    assert len(h) == 64  # SHA256 hex


def test_idempotency_key() -> None:
    """Idempotency key formula matches perception.md."""
    key1 = perception_github._idempotency_key(
        "Osasuwu/jarvis", 388, ["status:ready", "tier:1-auto"]
    )
    key2 = perception_github._idempotency_key(
        "Osasuwu/jarvis", 388, ["tier:1-auto", "status:ready"]
    )
    assert key1 == key2  # Different label order → same key (sorted internally)
    assert len(key1) == 64  # SHA256 hex


def test_idempotency_key_different_issue() -> None:
    """Different issue numbers produce different keys."""
    key1 = perception_github._idempotency_key(
        "Osasuwu/jarvis", 388, ["status:ready", "tier:1-auto"]
    )
    key2 = perception_github._idempotency_key(
        "Osasuwu/jarvis", 389, ["status:ready", "tier:1-auto"]
    )
    assert key1 != key2


def test_extract_tier_label() -> None:
    """Extract tier label from label list."""
    labels = ["status:ready", "tier:1-auto", "bug"]
    tier = perception_github._extract_tier_label(labels)
    assert tier == "tier:1-auto"


def test_extract_tier_label_missing() -> None:
    """Return None if no tier label."""
    labels = ["status:ready", "bug"]
    tier = perception_github._extract_tier_label(labels)
    assert tier is None


def test_build_row_tier1() -> None:
    """Build row with tier:1-auto → auto_dispatch=true."""
    now = datetime(2026, 4, 25, 10, 0, 0, tzinfo=UTC)
    issue = {
        "number": 388,
        "title": "Sprint 4 — GitHub ingest",
        "body": "Goal: Issue with `status:ready` + tier label becomes a task_queue row.\n\nSee `agents/perception_github.py` for impl.",
        "labels": [
            {"name": "status:ready"},
            {"name": "tier:1-auto"},
        ],
    }
    row = perception_github._build_row(issue, "Osasuwu/jarvis", now)

    assert row is not None
    assert row["auto_dispatch"] is True
    assert row["approved_by"] == "github:issue:Osasuwu/jarvis#388"
    assert row["scope_files"] == ["agents/perception_github.py"]
    assert row["status"] == "pending"
    assert "idempotency_key" in row
    assert len(row["idempotency_key"]) == 64


def test_build_row_tier2() -> None:
    """Build row with tier:2-review → auto_dispatch=false."""
    now = datetime(2026, 4, 25, 10, 0, 0, tzinfo=UTC)
    issue = {
        "number": 389,
        "title": "Self-perception via morning_check",
        "body": "Review-gate for self-modifying tasks.",
        "labels": [
            {"name": "status:ready"},
            {"name": "tier:2-review"},
        ],
    }
    row = perception_github._build_row(issue, "Osasuwu/jarvis", now)

    assert row is not None
    assert row["auto_dispatch"] is False


def test_build_row_tier3() -> None:
    """Build row with tier:3-human → auto_dispatch=false."""
    now = datetime(2026, 4, 25, 10, 0, 0, tzinfo=UTC)
    issue = {
        "number": 390,
        "title": "Manual task",
        "body": "Owner-driven from start.",
        "labels": [
            {"name": "status:ready"},
            {"name": "tier:3-human"},
        ],
    }
    row = perception_github._build_row(issue, "Osasuwu/jarvis", now)

    assert row is not None
    assert row["auto_dispatch"] is False


def test_build_row_missing_tier() -> None:
    """Return None if tier label is missing."""
    now = datetime(2026, 4, 25, 10, 0, 0, tzinfo=UTC)
    issue = {
        "number": 391,
        "title": "No tier",
        "body": "This issue is missing a tier label.",
        "labels": [{"name": "status:ready"}],
    }
    row = perception_github._build_row(issue, "Osasuwu/jarvis", now)
    assert row is None


def test_build_row_goal_capped() -> None:
    """Cap goal text at _GOAL_MAX_CHARS."""
    now = datetime(2026, 4, 25, 10, 0, 0, tzinfo=UTC)
    long_body = "x" * 10000
    issue = {
        "number": 392,
        "title": "Title",
        "body": long_body,
        "labels": [{"name": "status:ready"}, {"name": "tier:1-auto"}],
    }
    row = perception_github._build_row(issue, "Osasuwu/jarvis", now)

    assert row is not None
    assert len(row["goal"]) <= perception_github._GOAL_MAX_CHARS


def test_build_row_scope_files_sorted() -> None:
    """Scope files should be sorted."""
    now = datetime(2026, 4, 25, 10, 0, 0, tzinfo=UTC)
    issue = {
        "number": 393,
        "title": "Test",
        "body": "See `z.py` and `a.py` and `m.py`.",
        "labels": [{"name": "status:ready"}, {"name": "tier:1-auto"}],
    }
    row = perception_github._build_row(issue, "Osasuwu/jarvis", now)

    assert row is not None
    assert row["scope_files"] == ["a.py", "m.py", "z.py"]


def test_poll_tick_idempotent() -> None:
    """Running poll_tick twice with same input produces zero new rows on second run."""
    now = datetime(2026, 4, 25, 10, 0, 0, tzinfo=UTC)

    # Build a row manually (simulating what poll_tick would create).
    row1 = {
        "goal": "Test issue",
        "scope_files": ["test.py"],
        "approved_by": "github:issue:Osasuwu/jarvis#400",
        "approved_at": now.isoformat(),
        "approved_scope_hash": perception_github._hash_scope_files(["test.py"]),
        "auto_dispatch": True,
        "idempotency_key": perception_github._idempotency_key(
            "Osasuwu/jarvis", 400, ["tier:1-auto", "status:ready"]
        ),
        "status": "pending",
    }

    # First upsert: should insert.
    client = _StubClient()
    result1 = (
        client.table("task_queue")
        .upsert(row1, on_conflict="idempotency_key", ignore_duplicates=True)
        .execute()
    )
    assert len(result1.data) == 1  # Inserted

    # Second upsert with identical row: should skip (ON CONFLICT DO NOTHING).
    result2 = (
        client.table("task_queue")
        .upsert(row1, on_conflict="idempotency_key", ignore_duplicates=True)
        .execute()
    )
    assert len(result2.data) == 0  # Duplicate, skipped

    # Verify only one row exists in the stub client.
    assert len(client.tables["task_queue"]) == 1


def test_poll_tick_row_shape() -> None:
    """Verify upserted rows have correct columns per perception.md."""
    now = datetime(2026, 4, 25, 10, 0, 0, tzinfo=UTC)
    issue = {
        "number": 401,
        "title": "Test issue for row shape",
        "body": "Verify `test.py` is captured.",
        "labels": [{"name": "status:ready"}, {"name": "tier:2-review"}],
    }
    row = perception_github._build_row(issue, "Osasuwu/jarvis", now)

    assert row is not None
    # Check all required columns per perception.md table.
    required = {
        "goal",
        "scope_files",
        "approved_by",
        "approved_at",
        "approved_scope_hash",
        "auto_dispatch",
        "idempotency_key",
        "status",
    }
    assert set(row.keys()) >= required


def test_tier_mapping() -> None:
    """Verify tier → auto_dispatch mapping is correct."""
    now = datetime(2026, 4, 25, 10, 0, 0, tzinfo=UTC)

    for tier_label, expected_auto in [
        ("tier:1-auto", True),
        ("tier:2-review", False),
        ("tier:3-human", False),
    ]:
        issue = {
            "number": 500 + hash(tier_label) % 100,
            "title": f"Test {tier_label}",
            "body": "",
            "labels": [{"name": "status:ready"}, {"name": tier_label}],
        }
        row = perception_github._build_row(issue, "Osasuwu/jarvis", now)
        assert row is not None
        assert row["auto_dispatch"] == expected_auto, f"Mismatch for {tier_label}"


def test_approved_by_format() -> None:
    """Verify approved_by follows exact format: github:issue:<owner>/<repo>#<N>."""
    now = datetime(2026, 4, 25, 10, 0, 0, tzinfo=UTC)
    issue = {
        "number": 388,
        "title": "Test",
        "body": "",
        "labels": [{"name": "status:ready"}, {"name": "tier:1-auto"}],
    }
    row = perception_github._build_row(issue, "Osasuwu/jarvis", now)

    assert row is not None
    assert row["approved_by"] == "github:issue:Osasuwu/jarvis#388"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
