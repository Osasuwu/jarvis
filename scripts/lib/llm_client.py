"""Shared LLM client — Ollama primary with DeepSeek fallback.

Patterns (not a library — too small to extract):
  - ``call_ollama(prompt, ...)`` — POST to ``/api/generate``.
  - ``call_deepseek(prompt, ...)`` — POST to OpenAI-compatible ``/v1/chat/completions``.
  - ``call_llm(prompt)`` — tries Ollama first, falls back to DeepSeek.

All return the response text on success, or None on any error (timeout,
network, parse).  Caller decides what to do with None.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_OLLAMA_HOST = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL = "qwen2.5-coder:14b"  # Workshop primary (docs/agents/ollama-workshop-bench-538.md)
DEFAULT_OLLAMA_TIMEOUT_S = 120

DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_DEEPSEEK_MODEL = "deepseek-chat"
DEFAULT_DEEPSEEK_TIMEOUT_S = 180

# ---------------------------------------------------------------------------
# Ollama
# ---------------------------------------------------------------------------


def call_ollama(
    prompt: str,
    *,
    host: str | None = None,
    model: str | None = None,
    timeout_s: int = DEFAULT_OLLAMA_TIMEOUT_S,
    system_prompt: str | None = None,
    format_json: bool = True,
) -> str | None:
    """Call Ollama ``/api/generate`` with *prompt* and return the response text.

    Returns None on any error.  *system_prompt* is passed as the ``system``
    field (supported by Ollama 0.3+).  When *format_json* is true (default)
    the request sets ``"format": "json"``.
    """
    host = host or os.environ.get("OLLAMA_HOST", DEFAULT_OLLAMA_HOST)
    model = model or os.environ.get("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL)

    body: dict = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0, "num_predict": 1500},
    }
    if system_prompt:
        body["system"] = system_prompt
    if format_json:
        body["format"] = "json"

    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{host.rstrip('/')}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError):
        return None

    try:
        envelope = json.loads(raw)
    except Exception:
        return None
    return envelope.get("response")


# ---------------------------------------------------------------------------
# DeepSeek (OpenAI-compatible API)
# ---------------------------------------------------------------------------


def call_deepseek(
    prompt: str,
    *,
    base_url: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
    timeout_s: int = DEFAULT_DEEPSEEK_TIMEOUT_S,
    system_prompt: str | None = None,
) -> str | None:
    """Call DeepSeek chat-completions API and return the response text.

    Returns None on any error.  Uses ``requests``-style JSON POST via
    stdlib ``urllib`` — no extra dependency.
    """
    base_url = base_url or os.environ.get("DEEPSEEK_BASE_URL", DEFAULT_DEEPSEEK_BASE_URL)
    model = model or os.environ.get("DEEPSEEK_MODEL", DEFAULT_DEEPSEEK_MODEL)
    api_key = api_key or os.environ.get("DEEPSEEK_API_KEY", "")

    if not api_key:
        return None

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    body = {
        "model": model,
        "messages": messages,
        "temperature": 0,
        "max_tokens": 1500,
    }
    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/v1/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError):
        return None

    try:
        envelope = json.loads(raw)
    except Exception:
        return None

    choices = envelope.get("choices", [])
    if not choices:
        return None
    return choices[0].get("message", {}).get("content")


# ---------------------------------------------------------------------------
# Orchestrator: Ollama primary, DeepSeek fallback
# ---------------------------------------------------------------------------


def call_llm(
    prompt: str,
    *,
    system_prompt: str | None = None,
    format_json: bool = True,
) -> str | None:
    """Try Ollama first; fall back to DeepSeek on any error.

    Returns None only if **both** backends fail.
    """
    result = call_ollama(prompt, system_prompt=system_prompt, format_json=format_json)
    if result is not None:
        return result
    # Fallback
    return call_deepseek(prompt, system_prompt=system_prompt)
