"""Groq LLM provider implementation."""

import asyncio
import logging
from typing import Any

from groq import Groq, APIError

from jarvis.config import get_config
from jarvis.llm.base import LLMProvider, LLMResponse, ToolCall

logger = logging.getLogger(__name__)


class GroqProvider(LLMProvider):
    """Groq LLM provider using Groq API."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ):
        """
        Initialize Groq provider.

        Args:
            api_key: Groq API key (defaults to config)
            model: Model name (defaults to config)
            temperature: Default temperature
            max_tokens: Default max tokens
        """
        config = get_config()

        self._api_key = api_key or config.llm.groq_api_key
        self._model = model or config.llm.model
        self._temperature = temperature or config.llm.temperature
        self._max_tokens = max_tokens or config.llm.max_tokens
        self._timeout = config.llm.groq_timeout

        if not self._api_key:
            raise ValueError(
                "Groq API key not provided. "
                "Set GROQ_API_KEY env variable or pass api_key parameter."
            )

        self._client = Groq(api_key=self._api_key, timeout=self._timeout)

    async def complete(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Send messages to Groq and get completion."""
        temp = temperature if temperature is not None else self._temperature
        max_tok = max_tokens if max_tokens is not None else self._max_tokens

        try:
            # Run blocking Groq call in thread pool
            response = await asyncio.to_thread(
                self._sync_complete,
                messages=messages,
                tools=tools,
                temperature=temp,
                max_tokens=max_tok,
            )
            return response
        except APIError as e:
            logger.error(f"Groq API error: {e}")
            raise

    def _sync_complete(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Synchronous Groq completion (runs in thread pool)."""
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        # Add tools if provided
        if tools:
            kwargs["tools"] = [
                {"type": "function", "function": tool} for tool in tools
            ]

        response = self._client.chat.completions.create(**kwargs)

        # Parse tool calls from response
        tool_calls = None
        if response.choices[0].message.tool_calls:
            tool_calls = [
                ToolCall(
                    name=tc.function.name,
                    arguments=self._parse_json(tc.function.arguments),
                    id=tc.id,
                )
                for tc in response.choices[0].message.tool_calls
            ]

        content = response.choices[0].message.content or ""

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            stop_reason=response.choices[0].finish_reason,
            tokens_used=response.usage.total_tokens if response.usage else None,
        )

    async def validate_connection(self) -> bool:
        """Validate Groq connection."""
        try:
            await asyncio.to_thread(
                self._client.models.list,
            )
            logger.info("Groq connection validated successfully")
            return True
        except APIError as e:
            logger.error(f"Groq connection validation failed: {e}")
            return False

    @property
    def model_name(self) -> str:
        """Get current model name."""
        return self._model

    @property
    def provider_name(self) -> str:
        """Get provider name."""
        return "groq"

    @staticmethod
    def _parse_json(json_str: str) -> dict:
        """Safely parse JSON string."""
        import json

        try:
            return json.loads(json_str)
        except (json.JSONDecodeError, TypeError):
            logger.warning(f"Failed to parse JSON: {json_str}")
            return {}
