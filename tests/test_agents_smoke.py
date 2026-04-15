"""Smoke tests for the Pillar 7 agents package.

These are import/config-level sanity checks — no Postgres, no Ollama.
Full end-to-end validation is manual (see docs/agents/langgraph-setup.md).
"""

from __future__ import annotations

import os

import pytest


def test_config_loads_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """With no env overrides, config exposes the documented defaults."""
    for var in (
        "OLLAMA_HOST",
        "OLLAMA_MODEL",
        "AGENTS_POSTGRES_URL",
        "SUPABASE_URL",
        "SUPABASE_KEY",
    ):
        monkeypatch.delenv(var, raising=False)

    from agents.config import (
        DEFAULT_OLLAMA_HOST,
        DEFAULT_OLLAMA_MODEL,
        DEFAULT_POSTGRES_URL,
        load_config,
    )

    cfg = load_config()
    assert cfg.ollama_host == DEFAULT_OLLAMA_HOST
    assert cfg.ollama_model == DEFAULT_OLLAMA_MODEL
    assert cfg.postgres_url == DEFAULT_POSTGRES_URL
    # Supabase bridge has no safe default — empty string means "not configured".
    assert cfg.supabase_url == ""
    assert cfg.supabase_key == ""


def test_config_honours_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Environment variables override the defaults."""
    monkeypatch.setenv("OLLAMA_HOST", "http://example:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3.2:3b")
    monkeypatch.setenv("AGENTS_POSTGRES_URL", "postgresql://u:p@host:5432/db?sslmode=disable")
    monkeypatch.setenv("SUPABASE_URL", "https://proj.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "anon-key-xyz")

    from agents.config import load_config

    cfg = load_config()
    assert cfg.ollama_host == "http://example:11434"
    assert cfg.ollama_model == "llama3.2:3b"
    assert cfg.postgres_url.startswith("postgresql://u:p@host")
    assert cfg.supabase_url == "https://proj.supabase.co"
    assert cfg.supabase_key == "anon-key-xyz"


def test_graph_builds_without_runtime() -> None:
    """The LangGraph definition compiles without touching Ollama or Postgres."""
    pytest.importorskip("langgraph")

    from agents.main import DemoState, build_graph

    graph = build_graph()
    # Nodes registered: user node + implicit START/END.
    assert "respond" in graph.nodes
    # TypedDict schema surface — just confirm the keys we rely on.
    assert set(DemoState.__annotations__) == {"prompt", "reply", "step"}


def test_ollama_client_defaults_to_think_false() -> None:
    """Shared chat wrapper must default `think=False` for Qwen3 safety."""
    pytest.importorskip("ollama")

    import inspect

    from agents.ollama_client import chat

    sig = inspect.signature(chat)
    assert sig.parameters["think"].default is False, (
        "think must default to False — see docs/agents/ollama-setup.md "
        "for the Qwen3 empty-response gotcha"
    )


def test_env_example_documents_agent_vars() -> None:
    """`.env.example` must document the new agent variables."""
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)
    with open(os.path.join(root, ".env.example"), encoding="utf-8") as f:
        content = f.read()
    # Pillar 7 agent-only vars + shared Supabase vars used by the bridge.
    for key in (
        "OLLAMA_HOST",
        "OLLAMA_MODEL",
        "AGENTS_POSTGRES_URL",
        "SUPABASE_URL",
        "SUPABASE_KEY",
    ):
        assert key in content, f"{key} missing from .env.example"


def test_supabase_client_errors_without_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """`get_client` must fail loudly when SUPABASE_URL/KEY are missing.

    Silently defaulting would let a misconfigured agent run against nothing
    and look healthy until the first write failed.
    """
    pytest.importorskip("supabase")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)

    from agents.supabase_client import get_client

    with pytest.raises(RuntimeError, match="SUPABASE_URL and SUPABASE_KEY"):
        get_client()


def test_supabase_client_surface() -> None:
    """The bridge must expose the read/write helpers #173 requires."""
    pytest.importorskip("supabase")

    from agents import supabase_client as sb

    # Reads
    assert callable(sb.list_memories)
    assert callable(sb.list_events)
    assert callable(sb.list_goals)
    # Writes
    assert callable(sb.store_event)
    assert callable(sb.mark_event_processed)
    assert callable(sb.update_goal_progress)
    assert callable(sb.audit)


def test_github_client_event_allowlist() -> None:
    """Allow-list includes the six event types the monitor acts on."""
    from agents.github_client import RELEVANT_EVENT_TYPES

    for needed in (
        "IssuesEvent",
        "PullRequestEvent",
        "PullRequestReviewEvent",
        "IssueCommentEvent",
        "PullRequestReviewCommentEvent",
        "PushEvent",
    ):
        assert needed in RELEVANT_EVENT_TYPES
    # Things we intentionally drop as noise.
    assert "WatchEvent" not in RELEVANT_EVENT_TYPES
    assert "ForkEvent" not in RELEVANT_EVENT_TYPES


def test_fetch_repo_events_slices_oldest_first(monkeypatch: pytest.MonkeyPatch) -> None:
    """When new events outnumber ``limit``, pick the oldest N so the
    monitor's cursor advance stays contiguous.

    Regression guard for the bug Copilot flagged on #179: GitHub returns
    newest-first; a naive ``filtered[:limit]`` picks the newest N and the
    monitor then advances the cursor to the max id — permanently skipping
    the older-but-still-new events that didn't fit.
    """
    from agents import github_client

    # 12 relevant events, newest first — like the real /events endpoint.
    raw = [
        {"id": str(i), "type": "IssuesEvent", "actor": {}, "repo": {}, "payload": {}}
        for i in range(20, 8, -1)
    ]

    class _Resp:
        def __init__(self, data: list[dict[str, object]]) -> None:
            self._data = data

        def raise_for_status(self) -> None:
            return None

        def json(self) -> list[dict[str, object]]:
            return self._data

    monkeypatch.setattr(github_client.httpx, "get", lambda *a, **kw: _Resp(raw))

    out = github_client.fetch_repo_events("o/r", after_event_id="8", limit=5)

    # Must return the 5 OLDEST new events (ids 9–13), not the 5 newest (16–20).
    ids = [int(e["id"]) for e in out]
    assert ids == [9, 10, 11, 12, 13], ids


def test_summarise_event_covers_known_types() -> None:
    """Every event-type branch produces a string with actor + repo + detail."""
    from agents.github_client import summarise_event

    common = {"actor": {"login": "alice"}, "repo": {"name": "o/r"}}
    cases = [
        {
            **common,
            "type": "IssuesEvent",
            "payload": {"action": "opened", "issue": {"number": 42, "title": "bug"}},
        },
        {
            **common,
            "type": "PullRequestEvent",
            "payload": {"action": "opened", "pull_request": {"number": 7, "title": "feat"}},
        },
        {
            **common,
            "type": "PullRequestReviewEvent",
            "payload": {"review": {"state": "approved"}, "pull_request": {"number": 7}},
        },
        {
            **common,
            "type": "IssueCommentEvent",
            "payload": {"action": "created", "issue": {"number": 42}},
        },
        {
            **common,
            "type": "PushEvent",
            "payload": {"ref": "refs/heads/main", "commits": [{}, {}]},
        },
        {**common, "type": "WeirdEvent", "payload": {}},  # fallback branch
    ]
    for event in cases:
        s = summarise_event(event)
        assert "alice" in s, s
        assert "o/r" in s, s
        assert event["type"] in s, s


def test_event_monitor_graph_builds() -> None:
    """The monitor graph compiles to fetch -> classify -> store."""
    pytest.importorskip("langgraph")
    pytest.importorskip("supabase")

    from agents.event_monitor import MonitorState, build_graph

    graph = build_graph()
    assert {"fetch_events", "classify", "store"} <= set(graph.nodes)
    assert {"repos", "cursors", "fetched_events", "classified_events", "stored_count"} <= set(
        MonitorState.__annotations__
    )


def test_event_monitor_classification_schema() -> None:
    """Classifier enum stays three-tier — Ollama prompt depends on it."""
    # agents.event_monitor imports langgraph + supabase at module load, so
    # skip (not error) when the optional [agents] extras aren't installed.
    pytest.importorskip("langgraph")
    pytest.importorskip("supabase")

    from agents.event_monitor import _CLASSIFY_SCHEMA

    enum = _CLASSIFY_SCHEMA["properties"]["classification"]["enum"]
    assert set(enum) == {"noise", "info", "action"}
    assert set(_CLASSIFY_SCHEMA["required"]) == {"classification", "reason"}
