"""Domain-specific exceptions (skeleton)."""

from __future__ import annotations


class JarvisError(Exception):
    """Base class for Jarvis-specific errors."""


class ToolDiscoveryError(JarvisError):
    """Raised when tool discovery fails fatally."""


class ToolLoadError(JarvisError):
    """Raised when a tool cannot be loaded/validated."""


class RetryableError(JarvisError):
    """Indicates an operation may succeed on retry (e.g., transient network)."""


class NonRetryableError(JarvisError):
    """Indicates an operation should not be retried (e.g., validation failure)."""


class TimeoutError(JarvisError):
    """Raised when an operation exceeds its allowed time budget."""
