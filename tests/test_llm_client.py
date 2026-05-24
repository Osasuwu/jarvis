"""Tests for scripts/lib/llm_client.py — fallback logic.

Covers the key acceptance criterion: Ollama failure → DeepSeek fallback,
with no half-write and correct endpoint usage.
"""

from __future__ import annotations

from unittest.mock import patch

from lib.llm_client import call_llm


def test_call_llm_uses_ollama_when_available():
    """call_llm returns Ollama response and does not call DeepSeek."""
    with (
        patch("lib.llm_client.call_ollama", return_value="ollama-result") as mock_ollama,
        patch("lib.llm_client.call_deepseek") as mock_deepseek,
    ):
        result = call_llm("test prompt", system_prompt="sys")

    assert result == "ollama-result"
    mock_ollama.assert_called_once()
    mock_deepseek.assert_not_called()


def test_call_llm_falls_back_to_deepseek_on_ollama_failure():
    """When Ollama returns None, call_llm falls back to DeepSeek."""
    deepseek_response = '[{"type":"user","name":"x","content":"y"}]'
    with (
        patch("lib.llm_client.call_ollama", return_value=None) as mock_ollama,
        patch("lib.llm_client.call_deepseek", return_value=deepseek_response) as mock_deepseek,
    ):
        result = call_llm("test prompt", system_prompt="sys")

    assert result == deepseek_response
    mock_ollama.assert_called_once()
    mock_deepseek.assert_called_once()


def test_call_llm_returns_none_when_both_backends_fail():
    """When both Ollama and DeepSeek fail, call_llm returns None (no half-write)."""
    with (
        patch("lib.llm_client.call_ollama", return_value=None),
        patch("lib.llm_client.call_deepseek", return_value=None),
    ):
        result = call_llm("test prompt")

    assert result is None
