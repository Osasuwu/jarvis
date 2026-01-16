"""Base LLM provider interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ToolCall:
    """Represents a tool call from LLM."""

    name: str
    arguments: dict
    id: str | None = None


@dataclass
class LLMResponse:
    """LLM completion response."""

    content: str
    tool_calls: list[ToolCall] | None = None
    stop_reason: str | None = None
    tokens_used: int | None = None


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    async def complete(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """
        Send messages to LLM and get completion.

        Args:
            messages: List of message dicts with 'role' and 'content'
            tools: Optional list of tool definitions for function calling
            temperature: Optional temperature override
            max_tokens: Optional max tokens override

        Returns:
            LLMResponse with content and optional tool calls
        """
        pass

    @abstractmethod
    async def validate_connection(self) -> bool:
        """
        Validate that the provider is accessible and configured correctly.

        Returns:
            True if connection successful, False otherwise
        """
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Get the current model name."""
        pass

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Get the provider name (e.g., 'groq', 'openai')."""
        pass
