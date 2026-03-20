"""Structured logging setup for Jarvis.

Provides structured logging with context fields for better observability.
Uses stdlib logging for now; ready to swap to structlog or OpenTelemetry later.
"""

from __future__ import annotations

import logging
import sys
import time
import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LogContext:
    """
    Request-scoped logging context for tracing operations.

    Contains all contextual information that should be tracked
    across the entire request lifecycle through all layers.

    Attributes:
        request_id: Unique ID for this request (UUID)
        user_id: Optional user identifier
        start_time: Request start timestamp (seconds since epoch)
        operation: Current operation being performed
        metadata: Additional context-specific metadata
    """

    request_id: str
    start_time: float = field(default_factory=time.time)
    user_id: str | None = None
    operation: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert context to dictionary for logging."""
        data = {
            "request_id": self.request_id,
            "start_time": self.start_time,
        }
        if self.user_id:
            data["user_id"] = self.user_id
        if self.operation:
            data["operation"] = self.operation
        if self.metadata:
            data.update(self.metadata)
        return data

    def elapsed_ms(self) -> int:
        """Calculate elapsed time in milliseconds."""
        return int((time.time() - self.start_time) * 1000)


# Context variables for request tracking
_log_context: ContextVar[LogContext | None] = ContextVar("log_context", default=None)

# Legacy: Keep request_id_var for backward compatibility
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


DEFAULT_FORMAT = "%(asctime)s [%(levelname)s] %(name)s - %(message)s"


class StructuredFormatter(logging.Formatter):
    """Formatter that adds structured fields to log records."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record with structured fields from LogContext."""
        # Get log context if available
        ctx = _log_context.get()
        if ctx:
            # Add all context fields to record
            record.request_id = ctx.request_id
            if ctx.user_id:
                record.user_id = ctx.user_id
            if ctx.operation:
                record.operation = ctx.operation
            record.elapsed_ms = ctx.elapsed_ms()
        else:
            # Fallback to legacy request_id_var for backward compatibility
            request_id = request_id_var.get()
            if request_id:
                record.request_id = request_id

        # Add component from module name if not set
        if not hasattr(record, "component"):
            record.component = record.name.split(".")[-1]

        # Format with extra fields
        extra_fields = []
        for field_name in [
            "request_id",
            "user_id",
            "component",
            "operation",
            "action",
            "status",
            "elapsed_ms",
            "duration_ms",
            "tool_name",
        ]:
            if hasattr(record, field_name):
                value = getattr(record, field_name)
                if value is not None:
                    extra_fields.append(f"{field_name}={value}")

        msg = super().format(record)
        if extra_fields:
            msg = f"{msg} [{', '.join(extra_fields)}]"

        return msg


def setup_logging(
    level: str = "INFO",
    fmt: str = DEFAULT_FORMAT,
    structured: bool = True,
) -> None:
    """Configure base logging with optional structured formatting.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        fmt: Log format string.
        structured: Use structured formatter with extra fields.
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    # Create handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(log_level)

    # Set formatter
    formatter = StructuredFormatter(fmt) if structured else logging.Formatter(fmt)

    handler.setFormatter(formatter)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove existing handlers
    root_logger.handlers.clear()
    root_logger.addHandler(handler)


def get_logger(name: str | None = None) -> logging.Logger:
    """Get configured logger with optional name.

    Args:
        name: Logger name (uses caller's module if None).

    Returns:
        Logger instance.
    """
    return logging.getLogger(name or __name__)


def set_request_id(request_id: str | None = None) -> str:
    """
    Set request ID for current context (legacy API).

    This function maintains backward compatibility. New code should use
    set_log_context() instead.

    Args:
        request_id: Request ID to set (generates UUID if None).

    Returns:
        The request ID that was set.
    """
    rid = request_id or str(uuid.uuid4())
    request_id_var.set(rid)

    # Also update LogContext if one exists
    ctx = _log_context.get()
    if ctx:
        ctx.request_id = rid

    return rid


def get_request_id() -> str | None:
    """
    Get current request ID from context (legacy API).

    Returns:
        Request ID or None if not set.
    """
    # Try LogContext first
    ctx = _log_context.get()
    if ctx:
        return ctx.request_id

    # Fallback to legacy var
    return request_id_var.get()


def clear_request_id() -> None:
    """
    Clear request ID from context (legacy API).

    This function maintains backward compatibility. New code should use
    clear_log_context() instead.
    """
    request_id_var.set(None)
    # Also clear LogContext
    _log_context.set(None)


def set_log_context(
    request_id: str | None = None,
    user_id: str | None = None,
    operation: str | None = None,
    **metadata: Any,
) -> LogContext:
    """
    Set logging context for current request.

    Creates a new LogContext and stores it in context variable, making it
    available to all logging calls in the current async/thread context.

    Args:
        request_id: Unique request ID (generates UUID if None)
        user_id: Optional user identifier
        operation: Current operation being performed
        **metadata: Additional context metadata

    Returns:
        The created LogContext
    """
    rid = request_id or str(uuid.uuid4())
    ctx = LogContext(
        request_id=rid,
        user_id=user_id,
        operation=operation,
        metadata=metadata,
    )
    _log_context.set(ctx)

    # Set legacy var for backward compatibility
    request_id_var.set(rid)

    return ctx


def get_log_context() -> LogContext | None:
    """
    Get current logging context.

    Returns:
        Current LogContext or None if not set.
    """
    return _log_context.get()


def update_log_context(
    operation: str | None = None,
    **metadata: Any,
) -> None:
    """
    Update current logging context with new information.

    Args:
        operation: Update current operation
        **metadata: Additional metadata to merge
    """
    ctx = _log_context.get()
    if ctx:
        if operation:
            ctx.operation = operation
        if metadata:
            ctx.metadata.update(metadata)


def clear_log_context() -> None:
    """
    Clear logging context from current async/thread context.

    Should be called in a finally block to ensure context is cleaned up
    after request processing completes.
    """
    _log_context.set(None)
    request_id_var.set(None)


def log_with_context(
    logger: logging.Logger,
    level: str,
    message: str,
    **extra: Any,
) -> None:
    """Log message with structured context fields.

    Args:
        logger: Logger to use.
        level: Log level (debug, info, warning, error, critical).
        message: Log message.
        **extra: Additional structured fields (component, action, status, etc.).
    """
    log_method = getattr(logger, level.lower())
    log_method(message, extra=extra)
