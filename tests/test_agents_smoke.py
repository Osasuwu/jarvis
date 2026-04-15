"""Smoke tests for the Pillar 7 agents package.

These are import/config-level sanity checks — no Postgres, no Ollama.
Full end-to-end validation is manual (see docs/agents/langgraph-setup.md).
"""

from __future__ import annotations

import os

import pytest


def test_config_loads_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """With no env overrides, config exposes the documented defaults."""
    for var in ("OLLAMA_HOST", "OLLAMA_MODEL", "AGENTS_POSTGRES_URL"):
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


def test_config_honours_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Environment variables override the defaults."""
    monkeypatch.setenv("OLLAMA_HOST", "http://example:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3.2:3b")
    monkeypatch.setenv("AGENTS_POSTGRES_URL", "postgresql://u:p@host:5432/db?sslmode=disable")

    from agents.config import load_config

    cfg = load_config()
    assert cfg.ollama_host == "http://example:11434"
    assert cfg.ollama_model == "llama3.2:3b"
    assert cfg.postgres_url.startswith("postgresql://u:p@host")


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
    for key in ("OLLAMA_HOST", "OLLAMA_MODEL", "AGENTS_POSTGRES_URL"):
        assert key in content, f"{key} missing from .env.example"
