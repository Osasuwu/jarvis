"""Local lightweight LLM provider fallback using Ollama.

This provider connects to a locally running Ollama server.
It has the same capabilities as the main LLM but is "dumber" (smaller model)
and can only access local tools (no web access).

To use this provider, install and run Ollama:
  https://ollama.ai
  ollama pull mistral  # or phi, neural-chat, etc.
  ollama serve
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from jarvis.llm.base import LLMProvider, LLMResponse, ToolCall
from jarvis.prompts import build_system_prompt, format_error_message

logger = logging.getLogger(__name__)


class LocalStubProvider(LLMProvider):
    """Lightweight local LLM provider using Ollama.

    This provider:
    - Connects to a local Ollama server
    - Uses a compact model (mistral, phi, etc.)
    - Can only access local tools (file, shell, directory)
    - Works with the same reasoning loop as the main LLM
    """

    def __init__(
        self,
        model: str = "mistral",
        base_url: str = "http://localhost:11434",
        timeout: float = 30.0,
    ) -> None:
        """
        Initialize local provider.

        Args:
            model: Ollama model name (default: mistral)
            base_url: Ollama API base URL (default: http://localhost:11434)
            timeout: Request timeout in seconds
        """
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._provider = "ollama"
        self._client = httpx.AsyncClient(timeout=timeout)
        self._last_request_had_tools = False  # Track if last request included tool calls
        logger.info(f"LocalStubProvider initialized with model={model}, url={base_url}")

    @property
    def model_name(self) -> str:  # pragma: no cover
        return self._model

    @property
    def provider_name(self) -> str:  # pragma: no cover
        return self._provider

    async def validate_connection(self) -> bool:  # pragma: no cover
        """Check if Ollama server is running."""
        try:
            response = await self._client.get(
                f"{self._base_url}/api/tags",
                timeout=5.0,
            )
            return response.status_code == 200
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Cannot connect to Ollama: {e}")
            return False

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """
        Get a completion from the local Ollama model.

        Args:
            messages: Conversation history
            tools: Available tools (only local tools are supported)
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate

        Returns:
            LLMResponse with content and optional tool calls
        """
        if not await self.validate_connection():
            logger.error(f"Ollama server is not running at {self._base_url}")
            # Fallback to simple heuristic if Ollama is unavailable
            response = self._fallback_complete(messages, tools)
            self._last_request_had_tools = response.tool_calls is not None
            return response

        # Filter tools to only include local ones (no web tools)
        local_tools = self._filter_local_tools(tools or [])

        # Build system prompt for local LLM using centralized prompts
        system_prompt = build_system_prompt(
            provider="local",
            tools=local_tools,
            include_tool_instructions=True,
        )

        # Format messages as text prompt (Ollama /api/generate expects text input)
        prompt_text = system_prompt + "\n\n"
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                continue  # Already in system prompt
            prompt_text += f"{role.capitalize()}: {content}\n"
        prompt_text += "Assistant: "

        try:
            response = await self._client.post(
                f"{self._base_url}/api/generate",
                json={
                    "model": self._model,
                    "prompt": prompt_text,
                    "stream": False,
                    "temperature": temperature or 0.7,
                },
                timeout=120.0,
            )
            response.raise_for_status()

            data = response.json()
            content = data.get("response", "")

            # Try to extract tool calls from the response
            tool_calls = self._extract_tool_calls(content, local_tools)
            self._last_request_had_tools = tool_calls is not None

            return LLMResponse(
                content=content,
                tool_calls=tool_calls,
            )

        except Exception as e:  # noqa: BLE001
            logger.exception(f"Error calling Ollama: {e}")
            # Try fallback heuristic
            response = self._fallback_complete(messages, tools)
            self._last_request_had_tools = response.tool_calls is not None
            return response

    def _fallback_complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        """Fallback to simple heuristics when Ollama is unavailable."""
        logger.info("Using fallback heuristic completion")

        user_text = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                user_text = (m.get("content") or "").lower()
                break

        logger.info(f"User text for heuristics: '{user_text}'")

        # If we already called a tool last time, now provide a summary
        if self._last_request_had_tools:
            logger.info("Previous response had tool calls, returning final summary")
            return LLMResponse(
                content="Готово. Я выполнил ваш запрос с использованием доступных локальных инструментов.",
                tool_calls=None,
            )

        # Simple heuristics for common tasks - just check keywords
        if "список" in user_text or "файл" in user_text or "dir" in user_text:
            logger.info("Matched: list directory heuristic")
            return LLMResponse(
                content="Получаю список файлов в текущей папке...",
                tool_calls=[
                    ToolCall(
                        name="list_directory",
                        arguments={"path": "."},
                    )
                ],
            )

        if "прочитай" in user_text and "readme" in user_text:
            logger.info("Matched: read readme heuristic")
            return LLMResponse(
                content="Читаю файл README.md...",
                tool_calls=[
                    ToolCall(
                        name="file_read",
                        arguments={"path": "README.md"},
                    )
                ],
            )

        # Default fallback message
        logger.info("No heuristic matched")
        return LLMResponse(
            content=format_error_message(
                "llm_error",
                error_message=(
                    "Local Ollama server is unavailable. "
                    "Operating in limited functionality mode. "
                    "Available commands: 'list files', 'read readme'. "
                    "For full functionality, start Ollama: 'ollama serve'"
                ),
            ),
            tool_calls=None,
        )

    def _filter_local_tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Filter to only local tools (no web tools)."""
        local_tool_names = {
            "file_read",
            "file_write",
            "list_directory",
            "shell_execute",
            "echo",
        }
        return [t for t in tools if t.get("name") in local_tool_names]

    def _extract_tool_calls(
        self,
        content: str,
        available_tools: list[dict[str, Any]],
    ) -> list[ToolCall] | None:
        """Try to extract tool calls from the response."""
        import re

        tool_calls = []
        available_tool_names = {t.get("name") for t in available_tools}

        # Pattern: <function=tool_name(json_args)></function>
        pattern = r"<function=(\w+)\((.*?)\)></function>"
        matches = re.findall(pattern, content, re.DOTALL)

        for tool_name, args_str in matches:
            if tool_name not in available_tool_names:
                logger.warning(f"Tool '{tool_name}' not in available tools, skipping")
                continue

            try:
                # Try to parse arguments as JSON
                arguments = json.loads(args_str)
                tool_calls.append(ToolCall(name=tool_name, arguments=arguments))
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse arguments for {tool_name}: {args_str}")

        return tool_calls if tool_calls else None
