"""Tests for Ollama embedding routing added in #1621.

Verifies: _is_ollama_model routing gate, _embed_ollama happy-path,
and that _embed routes to Ollama (not Voyage AI) when configured.
No network calls — all HTTP mocked.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


# Load embeddings.py directly (not installed as a package)
def _load_embeddings(monkeypatch_env=None):
    path = Path(__file__).resolve().parent.parent.parent / "mcp-memory" / "embeddings.py"
    spec = importlib.util.spec_from_file_location("embeddings_1621", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run(coro):
    return asyncio.run(coro)


class TestIsOllamaModel:
    def test_false_when_no_url(self, monkeypatch):
        import os

        monkeypatch.delenv("OLLAMA_EMBED_URL", raising=False)
        emb = _load_embeddings()
        # OLLAMA_EMBED_URL is read at module load; re-check with patched constant
        emb.OLLAMA_EMBED_URL = ""
        emb.OLLAMA_EMBED_MODEL = "mxbai-embed-large"
        assert emb._is_ollama_model("mxbai-embed-large") is False

    def test_false_when_model_mismatch(self):
        emb = _load_embeddings()
        emb.OLLAMA_EMBED_URL = "http://localhost:11434"
        emb.OLLAMA_EMBED_MODEL = "mxbai-embed-large"
        assert emb._is_ollama_model("voyage-3-lite") is False

    def test_true_when_url_set_and_model_matches(self):
        emb = _load_embeddings()
        emb.OLLAMA_EMBED_URL = "http://localhost:11434"
        emb.OLLAMA_EMBED_MODEL = "mxbai-embed-large"
        assert emb._is_ollama_model("mxbai-embed-large") is True


class TestEmbedOllama:
    def test_happy_path_returns_vector(self):
        emb = _load_embeddings()
        emb.OLLAMA_EMBED_URL = "http://localhost:11434"
        fake_vec = [0.1, 0.2, 0.3]

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"embedding": fake_vec}

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = _run(emb._embed_ollama("hello", "mxbai-embed-large"))

        assert result == fake_vec
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert "api/embeddings" in call_args[0][0]
        assert call_args[1]["json"]["model"] == "mxbai-embed-large"

    def test_returns_none_on_http_error(self):
        import httpx

        emb = _load_embeddings()
        emb.OLLAMA_EMBED_URL = "http://localhost:11434"

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=httpx.ConnectError("refused"))

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = _run(emb._embed_ollama("hello", "mxbai-embed-large"))

        assert result is None


class TestEmbedRouting:
    def test_routes_to_ollama_not_voyage_when_configured(self):
        emb = _load_embeddings()
        emb.OLLAMA_EMBED_URL = "http://localhost:11434"
        emb.OLLAMA_EMBED_MODEL = "mxbai-embed-large"

        fake_vec = [0.5] * 1024
        ollama_called = []

        async def fake_embed_ollama(text, model):
            ollama_called.append((text, model))
            return fake_vec

        emb._embed_ollama = fake_embed_ollama
        result = _run(emb._embed("some text", model="mxbai-embed-large"))

        assert result == fake_vec
        assert len(ollama_called) == 1
        assert ollama_called[0] == ("some text", "mxbai-embed-large")

    def test_routes_to_voyage_when_no_ollama_url(self, monkeypatch):
        emb = _load_embeddings()
        emb.OLLAMA_EMBED_URL = ""

        voyage_called = []
        fake_vec = [0.1] * 512

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"data": [{"embedding": fake_vec}]}

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        monkeypatch.setenv("VOYAGE_API_KEY", "test-key")
        with patch("httpx.AsyncClient", return_value=mock_client):
            result = _run(emb._embed("some text", model="voyage-3-lite"))

        assert result == fake_vec
        call_url = mock_client.post.call_args[0][0]
        assert "voyageai" in call_url


class TestMxbaiEmbedLargeInModelRegistry:
    def test_mxbai_in_embedding_models(self):
        emb = _load_embeddings()
        assert "mxbai-embed-large" in emb.EMBEDDING_MODELS

    def test_mxbai_uses_v2_column(self):
        emb = _load_embeddings()
        slot = emb.EMBEDDING_MODELS["mxbai-embed-large"]
        assert slot["embedding_column"] == "embedding_v2"
        assert slot["rpc"] == "match_memories_v2"
