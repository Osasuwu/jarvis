"""Unit + integration tests for the task dispatcher (issue #298, S2-3).

No live Postgres, no real ``claude`` binary. A stub Supabase client
records every ``.table()`` call so we can assert the FSM transition
shape; a captured-Popen double records the subprocess env so the
billing-trap test can prove ``ANTHROPIC_API_KEY`` never reaches the
child.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Stubs — Supabase client recording inserts, updates, selects
# ---------------------------------------------------------------------------


@dataclass
class _Response:
    data: list[dict[str, Any]]


class _SelectQuery:
    """Chainable select query — records filters for inspection."""

    def __init__(self, table: "_Table") -> None:
        self._table = table
        self._filters: list[tuple[str, str, Any]] = []
        self._order: tuple[str, bool] | None = None
        self._limit: int | None = None
        self._exclude: tuple[str, Any] | None = None

    def select(self, *_args: Any, **_kwargs: Any) -> "_SelectQuery":
        return self

    def eq(self, col: str, val: Any) -> "_SelectQuery":
        self._filters.append(("eq", col, val))
        return self

    def neq(self, col: str, val: Any) -> "_SelectQuery":
        self._exclude = (col, val)
        return self

    def order(self, col: str, *, desc: bool = False) -> "_SelectQuery":
        self._order = (col, desc)
        return self

    def limit(self, n: int) -> "_SelectQuery":
        self._limit = n
        return self

    def execute(self) -> _Response:
        # Apply our eq/neq filters against the seeded rows so the test
        # surface looks like real Supabase.
        rows = list(self._table.seeded_rows)
        for op, col, val in self._filters:
            if op == "eq":
                rows = [r for r in rows if r.get(col) == val]
        if self._exclude is not None:
            col, val = self._exclude
            rows = [r for r in rows if r.get(col) != val]
        if self._order is not None:
            key_col, desc = self._order
            rows.sort(key=lambda r: (r.get(key_col) is None, r.get(key_col)), reverse=desc)
        if self._limit is not None:
            rows = rows[: self._limit]
        self._table.calls.append(
            (
                "select",
                self._table.name,
                {
                    "filters": list(self._filters),
                    "order": self._order,
                    "limit": self._limit,
                    "exclude": self._exclude,
                },
            )
        )
        return _Response(data=rows)


class _UpdateQuery:
    def __init__(self, table: "_Table", payload: dict[str, Any]) -> None:
        self._table = table
        self._payload = payload

    def eq(self, col: str, val: Any) -> "_UpdateQuery":
        self._table.calls.append(
            ("update", self._table.name, {"match": {col: val}, "set": dict(self._payload)})
        )
        # Mutate the seeded rows so subsequent selects reflect the transition.
        for row in self._table.seeded_rows:
            if row.get(col) == val:
                row.update(self._payload)
        return self

    def execute(self) -> _Response:
        return _Response(data=[self._payload])


class _InsertQuery:
    def __init__(self, table: "_Table", payload: dict[str, Any]) -> None:
        self._table = table
        self._payload = payload
        table.calls.append(("insert", table.name, dict(payload)))

    def execute(self) -> _Response:
        stored = {**self._payload, "id": f"{self._table.name}-row-{len(self._table.seeded_rows)}"}
        self._table.seeded_rows.append(stored)
        return _Response(data=[stored])


class _Table:
    def __init__(self, name: str, calls: list[Any], rows: list[dict[str, Any]]) -> None:
        self.name = name
        self.calls = calls
        self.seeded_rows = rows

    def select(self, *_args: Any, **_kwargs: Any) -> _SelectQuery:
        return _SelectQuery(self)

    def update(self, payload: dict[str, Any]) -> _UpdateQuery:
        return _UpdateQuery(self, payload)

    def insert(self, payload: dict[str, Any]) -> _InsertQuery:
        return _InsertQuery(self, payload)


class _StubClient:
    """Records every call made against a table and applies basic filters."""

    def __init__(self) -> None:
        self.calls: list[Any] = []
        self.tables: dict[str, list[dict[str, Any]]] = {
            "task_queue": [],
            "events": [],
            "audit_log": [],
        }

    def table(self, name: str) -> _Table:
        return _Table(name, self.calls, self.tables.setdefault(name, []))

    def seed(self, table: str, rows: list[dict[str, Any]]) -> None:
        self.tables.setdefault(table, []).extend(rows)


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


# Module-load snapshot — gives every test in this file a single,
# stable "current time" while still tracking real wall-clock so the
# production code's datetime.now(UTC) (called without explicit now=
# injection) sees a fresh approved_at relative to fixture rows.
_NOW = datetime.now(UTC)


def _now() -> datetime:
    return _NOW


def _queue_row(**overrides: Any) -> dict[str, Any]:
    base = {
        "id": "00000000-0000-0000-0000-000000000001",
        "goal": "fix: tighten error path",
        "scope_files": ["agents/dispatcher.py"],
        "approved_at": _now().isoformat(),
        "approved_by": "owner",
        "approved_scope_hash": "",
        "auto_dispatch": True,
        "status": "pending",
        "idempotency_key": "deadbeef",
        "dispatched_at": None,
    }
    base.update(overrides)
    # Match the approved_scope_hash to the files unless the test overrides
    # it — dispatcher's evaluate_node rebuilds the hash from scope_files.
    if not base["approved_scope_hash"]:
        from agents.dispatcher import _hash_scope_files

        base["approved_scope_hash"] = _hash_scope_files(base["scope_files"])
    return base


class _CapturedPopen:
    """Records the argv + env passed to each ``Popen`` instantiation."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def __call__(self, argv: list[str], **kwargs: Any) -> Any:
        self.calls.append({"argv": list(argv), "env": dict(kwargs.get("env") or {}), **kwargs})

        class _Handle:
            pid = 99999

            def poll(self) -> None:
                return None

        return _Handle()


def _healthy_reading() -> Any:
    from agents.usage_probe import UsageReading

    return UsageReading(
        limit_window=timedelta(hours=5),
        used=10,
        total=100,
        reset_at=_now(),
        near_exhaustion=False,
    )


def _near_exhaustion_reading() -> Any:
    from agents.usage_probe import UsageReading

    return UsageReading(
        limit_window=timedelta(hours=5),
        used=95,
        total=100,
        reset_at=_now(),
        near_exhaustion=True,
    )


# ---------------------------------------------------------------------------
# Module-level — surface & constants
# ---------------------------------------------------------------------------


def test_agent_id_matches_probe_and_escalation() -> None:
    """Single agent-id across probe/escalation/dispatcher keeps audit trail consistent."""
    from agents.dispatcher import AGENT_ID
    from agents.escalation import DISPATCHER_AGENT_ID
    from agents.usage_probe import DISPATCHER_AGENT_ID as PROBE_AGENT_ID

    assert AGENT_ID == DISPATCHER_AGENT_ID == PROBE_AGENT_ID == "task-dispatcher"


def test_spawn_allowlist_excludes_dangerous_permissions() -> None:
    """Verify spawn whitelist has been tightened per #378.

    - Bash(python:*) removed (arbitrary code escape)
    - Bash(gh:*) bare wildcard removed (destructive verbs)
    - Only scoped gh verbs (read/create, no merge/delete) present
    """
    from agents.dispatcher import _SPAWN_ALLOWED_TOOLS

    # Assert dangerous entries are NOT present
    assert "Bash(python:*)" not in _SPAWN_ALLOWED_TOOLS, \
        "Bash(python:*) must be removed — arbitrary code escape hatch (#378)"
    assert "Bash(gh:*)" not in _SPAWN_ALLOWED_TOOLS, \
        "bare Bash(gh:*) must be replaced with scoped verbs (#378)"

    # Assert safe scoped gh verbs ARE present
    safe_gh_verbs = {
        "Bash(gh pr view:*)",
        "Bash(gh pr create:*)",
        "Bash(gh pr list:*)",
        "Bash(gh issue view:*)",
        "Bash(gh issue create:*)",
        "Bash(gh issue list:*)",
        "Bash(gh issue comment:*)",
        "Bash(gh api repos/*/issues:*)",
        "Bash(gh api repos/*/pulls:*)",
    }
    for verb in safe_gh_verbs:
        assert verb in _SPAWN_ALLOWED_TOOLS, \
            f"Missing safe gh verb '{verb}' — dispatcher cannot read/create issues/PRs"

    # Assert no destructive gh verbs present
    destructive_patterns = [
        "merge",  # gh pr merge --admin
        "delete",  # gh repo delete, gh api DELETE
    ]
    for pattern in destructive_patterns:
        for tool in _SPAWN_ALLOWED_TOOLS:
            assert pattern not in tool, \
                f"Destructive pattern '{pattern}' found in allowlist entry '{tool}'"


# ---------------------------------------------------------------------------
# _resolve_claude_binary — issue #385
# ---------------------------------------------------------------------------


def test_resolve_claude_binary_override_wins(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    """Explicit override beats env var, PATH lookup, and Windows defaults."""
    import shutil as _shutil

    from agents import dispatcher

    real = tmp_path / "real-claude.exe"
    real.write_text("")
    fake_env = tmp_path / "env-claude.exe"
    fake_env.write_text("")

    monkeypatch.setenv("JARVIS_CLAUDE_BIN", str(fake_env))
    monkeypatch.setattr(_shutil, "which", lambda _name: "/never/used")

    assert dispatcher._resolve_claude_binary(override=str(real)) == str(real)


def test_resolve_claude_binary_override_must_exist(tmp_path: Any) -> None:
    """A non-existent override surfaces immediately, not at spawn time."""
    from agents import dispatcher

    missing = tmp_path / "does-not-exist.exe"
    with pytest.raises(FileNotFoundError, match="override does not exist"):
        dispatcher._resolve_claude_binary(override=str(missing))


def test_resolve_claude_binary_env_var_wins_over_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    """``JARVIS_CLAUDE_BIN`` is the operator-controlled override for NSSM/cron."""
    import shutil as _shutil

    from agents import dispatcher

    fake = tmp_path / "claude.exe"
    fake.write_text("")

    monkeypatch.setenv("JARVIS_CLAUDE_BIN", str(fake))
    monkeypatch.setattr(_shutil, "which", lambda _name: "/should/not/win")

    assert dispatcher._resolve_claude_binary() == str(fake)


def test_resolve_claude_binary_env_var_must_exist(monkeypatch: pytest.MonkeyPatch) -> None:
    """A misconfigured ``JARVIS_CLAUDE_BIN`` raises rather than silently falling through."""
    from agents import dispatcher

    monkeypatch.setenv("JARVIS_CLAUDE_BIN", "/no/such/file")
    with pytest.raises(FileNotFoundError, match="JARVIS_CLAUDE_BIN"):
        dispatcher._resolve_claude_binary()


def test_resolve_claude_binary_falls_through_to_shutil_which(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    """Without override or env, PATH lookup wins."""
    import shutil as _shutil

    from agents import dispatcher

    fake = tmp_path / "from-which.exe"
    fake.write_text("")

    monkeypatch.delenv("JARVIS_CLAUDE_BIN", raising=False)
    monkeypatch.setattr(
        _shutil, "which", lambda name: str(fake) if name == "claude" else None
    )

    assert dispatcher._resolve_claude_binary() == str(fake)


def test_resolve_claude_binary_falls_back_to_windows_default(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    """Last resort: documented Windows install location.

    Skipped on non-Windows because the module-level path templates only
    expand under ``os.name == 'nt'``.
    """
    import shutil as _shutil

    from agents import dispatcher

    if os.name != "nt":
        pytest.skip("Windows-default fallback only fires when os.name == 'nt'")

    fake = tmp_path / "Programs" / "claude" / "claude.exe"
    fake.parent.mkdir(parents=True)
    fake.write_text("")

    monkeypatch.delenv("JARVIS_CLAUDE_BIN", raising=False)
    monkeypatch.setattr(_shutil, "which", lambda _name: None)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    assert dispatcher._resolve_claude_binary() == str(fake)


def test_resolve_claude_binary_raises_with_actionable_message(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    """Final failure must name JARVIS_CLAUDE_BIN so operators can see the fix."""
    import shutil as _shutil

    from agents import dispatcher

    monkeypatch.delenv("JARVIS_CLAUDE_BIN", raising=False)
    monkeypatch.setattr(_shutil, "which", lambda _name: None)
    # Point Windows defaults at an empty directory so none resolve.
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "nope"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "nope"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "nope"))

    with pytest.raises(FileNotFoundError, match="JARVIS_CLAUDE_BIN"):
        dispatcher._resolve_claude_binary()


def test_dispatch_argv_uses_resolved_binary(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    """End-to-end: spawn receives an absolute path, not the bare string ``claude``."""
    from agents import dispatcher, usage_probe

    fake = tmp_path / "resolved-claude.exe"
    fake.write_text("")

    monkeypatch.setenv("JARVIS_CLAUDE_BIN", str(fake))
    monkeypatch.setattr(usage_probe, "read_usage", _healthy_reading)
    monkeypatch.setattr(dispatcher.usage_probe, "read_usage", _healthy_reading)

    client = _StubClient()
    client.seed("task_queue", [_queue_row(id="resolve-test")])
    popen = _CapturedPopen()

    app = _compile_graph(client, popen)
    result = app.invoke({"dry_run": False, "row": None, "outcome": "", "reason": ""})

    assert result["outcome"] == "dispatched"
    assert len(popen.calls) == 1
    argv = popen.calls[0]["argv"]
    assert argv[0] == str(fake), (
        "dispatcher must spawn the resolved binary path, not the bare 'claude' string"
    )


def test_sensitive_env_keys_cover_known_variants() -> None:
    """Env-sanitization must strip every historical Anthropic env name."""
    from agents.dispatcher import _SENSITIVE_ENV_KEYS

    # The billing-trap name from #37686 + sibling internal names that have
    # appeared in docs over the life of the CLI.
    assert "ANTHROPIC_API_KEY" in _SENSITIVE_ENV_KEYS
    assert "ANTHROPIC_AUTH_TOKEN" in _SENSITIVE_ENV_KEYS
    assert "CLAUDE_API_KEY" in _SENSITIVE_ENV_KEYS


# ---------------------------------------------------------------------------
# _sanitize_env
# ---------------------------------------------------------------------------


def test_sanitize_env_strips_api_key() -> None:
    from agents.dispatcher import _sanitize_env

    src = {"PATH": "/usr/bin", "ANTHROPIC_API_KEY": "sk-leak", "HOME": "/root"}
    out = _sanitize_env(src)
    assert "ANTHROPIC_API_KEY" not in out
    assert out["PATH"] == "/usr/bin"
    assert out["HOME"] == "/root"


def test_sanitize_env_strips_all_known_variants() -> None:
    from agents.dispatcher import _sanitize_env

    src = {
        "SAFE": "keep",
        "ANTHROPIC_API_KEY": "a",
        "ANTHROPIC_AUTH_TOKEN": "b",
        "CLAUDE_API_KEY": "c",
    }
    out = _sanitize_env(src)
    assert out == {"SAFE": "keep"}


def test_sanitize_env_defaults_to_os_environ(monkeypatch: pytest.MonkeyPatch) -> None:
    from agents.dispatcher import _sanitize_env

    monkeypatch.setenv("ANTHROPIC_API_KEY", "should-be-stripped")
    monkeypatch.setenv("PATH_FROM_TEST", "keep")
    out = _sanitize_env()
    assert "ANTHROPIC_API_KEY" not in out
    assert out.get("PATH_FROM_TEST") == "keep"


# ---------------------------------------------------------------------------
# _hash_scope_files
# ---------------------------------------------------------------------------


def test_hash_scope_files_is_order_independent() -> None:
    from agents.dispatcher import _hash_scope_files

    assert _hash_scope_files(["b.py", "a.py"]) == _hash_scope_files(["a.py", "b.py"])


def test_hash_scope_files_detects_added_file() -> None:
    from agents.dispatcher import _hash_scope_files

    assert _hash_scope_files(["a.py"]) != _hash_scope_files(["a.py", "b.py"])


def test_hash_scope_files_empty_list_is_stable() -> None:
    from agents.dispatcher import _hash_scope_files

    first = _hash_scope_files([])
    second = _hash_scope_files([])
    assert first == second
    assert len(first) == 64  # sha256 hex


# ---------------------------------------------------------------------------
# poll_queue_node
# ---------------------------------------------------------------------------


def test_poll_queue_empty_returns_no_pending() -> None:
    from agents.dispatcher import poll_queue_node

    client = _StubClient()
    state = {"dry_run": False, "row": None, "outcome": "", "reason": ""}
    result = poll_queue_node(state, client=client)
    assert result == {"row": None, "outcome": "no_pending", "reason": "queue empty"}


def test_poll_queue_returns_oldest_auto_dispatch_pending() -> None:
    from agents.dispatcher import poll_queue_node

    client = _StubClient()
    client.seed(
        "task_queue",
        [
            _queue_row(id="newer", approved_at=(_now() + timedelta(hours=1)).isoformat()),
            _queue_row(id="older", approved_at=(_now() - timedelta(hours=1)).isoformat()),
            _queue_row(id="no_auto", auto_dispatch=False),
            _queue_row(id="not_pending", status="dispatched"),
        ],
    )
    state = {"dry_run": False, "row": None, "outcome": "", "reason": ""}
    result = poll_queue_node(state, client=client)
    assert result["row"]["id"] == "older"


# ---------------------------------------------------------------------------
# Full graph — dry-run, dispatch, escalate
# ---------------------------------------------------------------------------


def _compile_graph(client: Any, popen: Any) -> Any:
    """Build + compile without a checkpointer — tests don't need persistence."""
    pytest.importorskip("langgraph")
    from agents.dispatcher import build_graph

    return build_graph(client=client, popen=popen).compile()


def test_graph_builds_with_expected_nodes() -> None:
    pytest.importorskip("langgraph")
    from agents.dispatcher import build_graph

    graph = build_graph()
    assert {"poll_queue", "evaluate", "escalate", "dispatch"} <= set(graph.nodes)


def test_full_flow_dispatches_healthy_row(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    """Happy path: healthy budget, fresh approval, no drift → subprocess spawned + row dispatched."""
    from agents import dispatcher, usage_probe

    # Pin claude binary so this test stays deterministic regardless of host PATH
    # (issue #385 — argv[0] is now the resolved absolute path, not the bare name).
    fake_claude = tmp_path / "claude.exe"
    fake_claude.write_text("")
    monkeypatch.setenv("JARVIS_CLAUDE_BIN", str(fake_claude))

    monkeypatch.setattr(usage_probe, "read_usage", _healthy_reading)
    # Dispatcher imports usage_probe at module load; monkeypatch the
    # attribute the module actually holds.
    monkeypatch.setattr(dispatcher.usage_probe, "read_usage", _healthy_reading)

    client = _StubClient()
    client.seed("task_queue", [_queue_row(id="go")])
    popen = _CapturedPopen()

    app = _compile_graph(client, popen)
    initial = {"dry_run": False, "row": None, "outcome": "", "reason": ""}
    result = app.invoke(initial)

    assert result["outcome"] == "dispatched"
    assert result["reason"].startswith("idem=")

    # Subprocess was invoked with <resolved-claude-path> -p <goal>.
    assert len(popen.calls) == 1
    call = popen.calls[0]
    assert call["argv"][0] == str(fake_claude)
    assert call["argv"][1] == "-p"

    # Permission flags present — without these, headless Claude hangs
    # on approval prompts (#372). acceptEdits + narrow allowedTools,
    # not bypassPermissions (which defeats Sprint 2 safety layering).
    argv = call["argv"]
    assert "--permission-mode" in argv
    assert argv[argv.index("--permission-mode") + 1] == "acceptEdits"
    assert "--allowedTools" in argv
    assert "Bash(git:*)" in argv, "expected narrow Bash allowlist"
    assert "--dangerously-skip-permissions" not in argv

    # Row flipped to dispatched.
    updates = [c for c in client.calls if c[0] == "update" and c[1] == "task_queue"]
    assert len(updates) == 1
    assert updates[0][2]["set"]["status"] == "dispatched"
    assert "dispatched_at" in updates[0][2]["set"]


def test_dry_run_does_not_spawn_or_update(monkeypatch: pytest.MonkeyPatch) -> None:
    """Dry-run: graph runs to completion, no Popen, no task_queue update."""
    from agents import dispatcher, usage_probe

    monkeypatch.setattr(usage_probe, "read_usage", _healthy_reading)
    monkeypatch.setattr(dispatcher.usage_probe, "read_usage", _healthy_reading)

    client = _StubClient()
    client.seed("task_queue", [_queue_row(id="dry")])
    popen = _CapturedPopen()

    app = _compile_graph(client, popen)
    result = app.invoke({"dry_run": True, "row": None, "outcome": "", "reason": ""})

    assert result["outcome"] == "dry_run_dispatched"
    assert popen.calls == [], "dry-run must not invoke subprocess"

    updates = [c for c in client.calls if c[0] == "update" and c[1] == "task_queue"]
    assert updates == [], "dry-run must not mutate task_queue"


def test_empty_queue_short_circuits_to_end(monkeypatch: pytest.MonkeyPatch) -> None:
    from agents import dispatcher, usage_probe

    monkeypatch.setattr(usage_probe, "read_usage", _healthy_reading)
    monkeypatch.setattr(dispatcher.usage_probe, "read_usage", _healthy_reading)

    client = _StubClient()
    popen = _CapturedPopen()

    app = _compile_graph(client, popen)
    result = app.invoke({"dry_run": False, "row": None, "outcome": "", "reason": ""})

    assert result["outcome"] == "no_pending"
    assert popen.calls == []


def test_budget_exhaustion_escalates(monkeypatch: pytest.MonkeyPatch) -> None:
    """Probe reports near_exhaustion → escalation.check_all fires → row flipped to escalated."""
    from agents import dispatcher, usage_probe

    monkeypatch.setattr(usage_probe, "read_usage", _near_exhaustion_reading)
    monkeypatch.setattr(dispatcher.usage_probe, "read_usage", _near_exhaustion_reading)

    client = _StubClient()
    client.seed("task_queue", [_queue_row(id="blocked-budget")])
    popen = _CapturedPopen()

    app = _compile_graph(client, popen)
    result = app.invoke({"dry_run": False, "row": None, "outcome": "", "reason": ""})

    assert result["outcome"] == "escalated"
    assert result["reason"] == "limit_near_exhaustion"
    assert popen.calls == [], "escalation must not spawn subprocess"

    # Event row recorded.
    event_inserts = [c for c in client.calls if c[0] == "insert" and c[1] == "events"]
    assert len(event_inserts) == 1
    assert event_inserts[0][2]["event_type"] == "dispatcher_escalation"
    assert event_inserts[0][2]["payload"]["trigger"] == "limit_near_exhaustion"

    # Row flipped to escalated (not dispatched).
    updates = [c for c in client.calls if c[0] == "update" and c[1] == "task_queue"]
    assert any(u[2]["set"].get("status") == "escalated" for u in updates)


def test_stale_approval_escalates(monkeypatch: pytest.MonkeyPatch) -> None:
    """Approval older than STALE_APPROVAL_MAX_DAYS → escalation first, no dispatch."""
    from agents import dispatcher, usage_probe

    monkeypatch.setattr(usage_probe, "read_usage", _healthy_reading)
    monkeypatch.setattr(dispatcher.usage_probe, "read_usage", _healthy_reading)

    from agents.escalation import STALE_APPROVAL_MAX_DAYS

    stale_at = (datetime.now(UTC) - timedelta(days=STALE_APPROVAL_MAX_DAYS + 2)).isoformat()

    client = _StubClient()
    client.seed("task_queue", [_queue_row(id="stale", approved_at=stale_at)])
    popen = _CapturedPopen()

    app = _compile_graph(client, popen)
    result = app.invoke({"dry_run": False, "row": None, "outcome": "", "reason": ""})

    assert result["outcome"] == "escalated"
    assert result["reason"] == "stale_approval"
    assert popen.calls == []


def test_dispatch_passes_sanitized_env_to_subprocess(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    """Integration-level leak test: ANTHROPIC_API_KEY in parent must NOT reach child env."""
    from agents import dispatcher, usage_probe

    fake_claude = tmp_path / "claude.exe"
    fake_claude.write_text("")
    monkeypatch.setenv("JARVIS_CLAUDE_BIN", str(fake_claude))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "leak-sentinel-xyz")
    monkeypatch.setenv("CLAUDE_API_KEY", "leak-sentinel-claude")
    monkeypatch.setenv("PATH_FROM_PARENT", "keep-me")
    monkeypatch.setattr(usage_probe, "read_usage", _healthy_reading)
    monkeypatch.setattr(dispatcher.usage_probe, "read_usage", _healthy_reading)

    client = _StubClient()
    client.seed("task_queue", [_queue_row(id="env-test")])
    popen = _CapturedPopen()

    app = _compile_graph(client, popen)
    result = app.invoke({"dry_run": False, "row": None, "outcome": "", "reason": ""})
    assert result["outcome"] == "dispatched"

    assert len(popen.calls) == 1
    env = popen.calls[0]["env"]
    assert "ANTHROPIC_API_KEY" not in env, "billing-trap leak: API key reached child env"
    assert "CLAUDE_API_KEY" not in env, "defensive-variant leak: CLAUDE_API_KEY reached child"
    assert env.get("PATH_FROM_PARENT") == "keep-me", "non-sensitive env must survive"


def test_dispatch_failure_audits_and_returns_failed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    """Popen raising must audit failure, not crash the tick.

    Pin ``JARVIS_CLAUDE_BIN`` so resolution succeeds and the failure path under
    test is the spawn itself, not the resolver (issue #385).
    """
    from agents import dispatcher, usage_probe

    fake_claude = tmp_path / "claude.exe"
    fake_claude.write_text("")
    monkeypatch.setenv("JARVIS_CLAUDE_BIN", str(fake_claude))
    monkeypatch.setattr(usage_probe, "read_usage", _healthy_reading)
    monkeypatch.setattr(dispatcher.usage_probe, "read_usage", _healthy_reading)

    client = _StubClient()
    client.seed("task_queue", [_queue_row(id="will-fail")])

    def _boom(argv: list[str], **kwargs: Any) -> Any:  # noqa: ARG001
        raise FileNotFoundError("claude not found")

    app = _compile_graph(client, _boom)
    result = app.invoke({"dry_run": False, "row": None, "outcome": "", "reason": ""})

    assert result["outcome"] == "failed"
    assert "FileNotFoundError" in result["reason"]
    # Row must NOT be flipped to dispatched when the spawn failed.
    updates = [c for c in client.calls if c[0] == "update" and c[1] == "task_queue"]
    assert updates == [], "failed dispatch must not advance queue FSM"


# ---------------------------------------------------------------------------
# Scheduler integration
# ---------------------------------------------------------------------------


def test_register_installs_job_on_scheduler(monkeypatch: pytest.MonkeyPatch) -> None:
    """``register()`` wires the module-level tick into APScheduler via S2-5."""
    pytest.importorskip("apscheduler")
    from apscheduler.jobstores.memory import MemoryJobStore

    from agents import dispatcher, scheduler

    handle = scheduler.build_scheduler(jobstore=MemoryJobStore())
    job = dispatcher.register(handle, dry_run=True, interval_seconds=30)

    assert job.id == dispatcher.AGENT_ID
    assert job.func_ref.endswith("_scheduled_tick")
    assert os.environ.get("TASK_DISPATCHER_DRY_RUN") == "1"


def test_scheduled_tick_swallows_exceptions(monkeypatch: pytest.MonkeyPatch) -> None:
    """A bad tick must log + return, not propagate (would tear the scheduler down)."""
    from agents import dispatcher

    def _boom(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("synthetic tick failure")

    monkeypatch.setattr(dispatcher, "run", _boom)
    # Should not raise.
    dispatcher._scheduled_tick()
