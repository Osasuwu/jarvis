"""Domain-specific exceptions for Jarvis AI Agent."""

from __future__ import annotations

from typing import Any

from jarvis.observability.logging import get_request_id


class JarvisError(Exception):
    """
    Base class for Jarvis-specific errors.

    Automatically includes request context in error details for tracing.
    """

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        """
        Initialize error with optional details and request context.

        Args:
            message: Human-readable error message
            details: Additional error context
        """
        super().__init__(message)
        self.message = message
        self.details = details or {}

        # Automatically capture request ID for tracing
        request_id = get_request_id()
        if request_id:
            self.details["request_id"] = request_id

    def __str__(self) -> str:
        """Format error message with request ID if available."""
        request_id = self.details.get("request_id")
        if request_id:
            return f"[request_id={request_id}] {self.message}"
        return self.message


class ToolDiscoveryError(JarvisError):
    """Raised when tool discovery fails fatally."""


class ToolLoadError(JarvisError):
    """Raised when a tool cannot be loaded/validated."""


class ToolExecutionError(JarvisError):
    """Raised when a tool execution fails."""


class RetryableError(JarvisError):
    """Indicates an operation may succeed on retry (e.g., transient network)."""

    def __init__(self, message: str, attempt: int = 0, max_attempts: int = 3, **kwargs):
        """Initialize with retry context."""
        super().__init__(
            message, details={"attempt": attempt, "max_attempts": max_attempts, **kwargs}
        )
        self.attempt = attempt
        self.max_attempts = max_attempts


class NonRetryableError(JarvisError):
    """Indicates an operation should not be retried (e.g., validation failure)."""


class TimeoutError(JarvisError):
    """Raised when an operation exceeds its allowed time budget."""

    def __init__(self, message: str, timeout_seconds: float, **kwargs):
        """Initialize with timeout context."""
        super().__init__(message, details={"timeout_seconds": timeout_seconds, **kwargs})
        self.timeout_seconds = timeout_seconds


class LLMError(JarvisError):
    """Base class for LLM-related errors."""


class LLMConnectionError(LLMError, RetryableError):
    """Raised when LLM connection fails (retryable)."""


class LLMTimeoutError(LLMError, TimeoutError):
    """Raised when LLM request times out."""


class LLMResponseError(LLMError, NonRetryableError):
    """Raised when LLM response is invalid or cannot be parsed."""
