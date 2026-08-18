"""Embedding helpers (Voyage AI + Ollama) + canonical embed-text builder.

(#360 split.) Pure I/O around embedding providers, plus the
_canonical_embed_text helper that produces the structured text fed
into the embedder. Read by both server.py and handlers/memory.py.

Providers:
- Voyage AI (default): set VOYAGE_API_KEY. Models: voyage-3-lite (512-dim),
  voyage-3 (1024-dim).
- Ollama (local/offline): set OLLAMA_EMBED_URL (e.g. http://localhost:11434)
  and optionally OLLAMA_EMBED_MODEL (default: mxbai-embed-large, 1024-dim).
  Requires the mxbai-embed-large model pulled in Ollama and the embedding_v2
  column present in Supabase (run mcp-memory/schema.sql through step 2181+).
  Set EMBEDDING_MODEL_PRIMARY=mxbai-embed-large to activate.
"""

from __future__ import annotations

import asyncio
import os

import httpx

VOYAGE_API_URL = "https://api.voyageai.com/v1/embeddings"
VOYAGE_MODEL = "voyage-3-lite"
EMBED_TIMEOUT = 30.0  # seconds

# Local Ollama embedding provider (alternative to Voyage AI for offline/GPU use).
# Set OLLAMA_EMBED_URL=http://localhost:11434 and pull the model:
#   ollama pull mxbai-embed-large
OLLAMA_EMBED_URL = os.environ.get("OLLAMA_EMBED_URL", "").rstrip("/")
OLLAMA_EMBED_MODEL = os.environ.get("OLLAMA_EMBED_MODEL", "mxbai-embed-large")

# #242 dual-embedding machinery. PRIMARY drives reads (which RPC is called
# + what model embeds the query). SECONDARY, if set, enables dual-write so
# the v2 column fills up in parallel without touching the read path.
# When SECONDARY is unset, behavior is bit-identical to pre-#242.
EMBEDDING_MODEL_PRIMARY = os.environ.get("EMBEDDING_MODEL_PRIMARY", VOYAGE_MODEL)
EMBEDDING_MODEL_SECONDARY = os.environ.get("EMBEDDING_MODEL_SECONDARY") or None

# Model → (column, RPC, version-tag) mapping. Extend here when adding a
# new supported model. Keep the table read-only at runtime.
EMBEDDING_MODELS = {
    "voyage-3-lite": {
        "embedding_column": "embedding",
        "model_column": "embedding_model",
        "version_column": "embedding_version",
        "rpc": "match_memories",
        "version_tag": "v2",  # Phase 2a canonical form
    },
    "voyage-3": {
        "embedding_column": "embedding_v2",
        "model_column": "embedding_model_v2",
        "version_column": "embedding_version_v2",
        "rpc": "match_memories_v2",
        "version_tag": "v2",
    },
    # Ollama local model — 1024-dim, shares the embedding_v2 column.
    # Use when OLLAMA_EMBED_URL is set and no Voyage AI key available.
    "mxbai-embed-large": {
        "embedding_column": "embedding_v2",
        "model_column": "embedding_model_v2",
        "version_column": "embedding_version_v2",
        "rpc": "match_memories_v2",
        "version_tag": "v2",
    },
}


def _model_slot(model: str) -> dict:
    """Look up the column/RPC slot for a model. Falls back to PRIMARY for
    unknown models so misconfiguration never crashes startup — it just
    degrades to legacy behavior."""
    return EMBEDDING_MODELS.get(model) or EMBEDDING_MODELS[VOYAGE_MODEL]


def _is_ollama_model(model: str) -> bool:
    """True when OLLAMA_EMBED_URL is set and model matches the configured Ollama model."""
    return bool(OLLAMA_EMBED_URL) and model == OLLAMA_EMBED_MODEL


async def _embed_ollama(text: str, model: str) -> list[float] | None:
    """Call local Ollama /api/embeddings. No input_type — Ollama ignores it."""
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=EMBED_TIMEOUT) as client:
                resp = await client.post(
                    f"{OLLAMA_EMBED_URL}/api/embeddings",
                    json={"model": model, "prompt": text},
                )
                resp.raise_for_status()
                return resp.json()["embedding"]
        except asyncio.CancelledError:
            raise
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError):
            if attempt < 2:
                await asyncio.sleep(2**attempt)
                continue
            return None
    return None


async def _embed(
    text: str, input_type: str = "document", model: str | None = None
) -> list[float] | None:
    """Embed one text via Voyage AI or Ollama. Retries up to 3x on transient errors."""
    use_model = model or VOYAGE_MODEL
    if _is_ollama_model(use_model):
        return await _embed_ollama(text, use_model)
    api_key = os.environ.get("VOYAGE_API_KEY")
    if not api_key:
        return None
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=EMBED_TIMEOUT) as client:
                resp = await client.post(
                    VOYAGE_API_URL,
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={"model": use_model, "input": [text], "input_type": input_type},
                )
                resp.raise_for_status()
                return resp.json()["data"][0]["embedding"]
        except asyncio.CancelledError:
            raise
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429 and attempt < 2:
                await asyncio.sleep(2**attempt)
                continue
            return None
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError):
            return None
    return None


async def _embed_batch(
    texts: list[str], input_type: str = "document", model: str | None = None
) -> list[list[float]] | None:
    """Embed multiple texts. Voyage AI: single batch call. Ollama: sequential calls."""
    if not texts:
        return None
    use_model = model or VOYAGE_MODEL
    if _is_ollama_model(use_model):
        # ceiling: sequential calls to Ollama; no batch API on /api/embeddings
        results = []
        for text in texts:
            vec = await _embed_ollama(text, use_model)
            if vec is None:
                return None
            results.append(vec)
        return results
    api_key = os.environ.get("VOYAGE_API_KEY")
    if not api_key:
        return None
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=EMBED_TIMEOUT) as client:
                resp = await client.post(
                    VOYAGE_API_URL,
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={"model": use_model, "input": texts, "input_type": input_type},
                )
                resp.raise_for_status()
                data = sorted(resp.json()["data"], key=lambda x: x["index"])
                return [item["embedding"] for item in data]
        except asyncio.CancelledError:
            raise
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429 and attempt < 2:
                await asyncio.sleep(2**attempt)
                continue
            return None
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError):
            return None
    return None


def _embed_upsert_fields(embedding: list[float], model: str) -> dict:
    """Build the dict of columns to upsert for a (embedding, model) pair.
    Returns {} if model is unknown (shouldn't happen at write time; silently
    degrades so we never corrupt rows)."""
    slot = EMBEDDING_MODELS.get(model)
    if not slot:
        return {}
    return {
        slot["embedding_column"]: embedding,
        slot["model_column"]: model,
        slot["version_column"]: slot["version_tag"],
    }


async def _embed_query(text: str) -> list[float] | None:
    # #242: read path embeds with PRIMARY so the vector matches whichever
    # column we're about to query via _hybrid_recall's RPC selection.
    return await _embed(text, input_type="query", model=EMBEDDING_MODEL_PRIMARY)


def _canonical_embed_text(name: str, description: str, tags: list[str], content: str) -> str:
    """Build the text used for embedding. Structured so name/tags get weight.

    Why: a long-form memory whose key topic is in the name but whose content
    drifts into narrative detail embeds poorly — name/tags get drowned out.
    Prefixing them in a separate line gives them comparable weight under the
    tokenizer.
    """
    parts: list[str] = []
    if name:
        parts.append(name.replace("_", " "))
    if tags:
        parts.append("tags: " + ", ".join(tags))
    if description:
        parts.append(description)
    if content:
        parts.append(content)
    return "\n".join(p for p in parts if p).strip()
