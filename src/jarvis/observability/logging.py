"""Structured logging setup for Jarvis.

Provides structured logging with context fields for better observability.
Uses stdlib logging for now; ready to swap to structlog or OpenTelemetry later.
"""

from __future__ import annotations

import logging
import sys
import uuid
from contextvars import ContextVar
from typing import Any, Optional

# Context variable for request tracking
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

DEFAULT_FORMAT = "%(asctime)s [%(levelname)s] %(name)s - %(message)s"


class StructuredFormatter(logging.Formatter):
    """Formatter that adds structured fields to log records."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record with structured fields."""
        # Add request_id if available
        request_id = request_id_var.get()
        if request_id:
            record.request_id = request_id
        
        # Add structured fields if present
        if not hasattr(record, "component"):
            record.component = record.name.split(".")[-1]
        
        # Format with extra fields
        extra_fields = []
        for field in ["request_id", "component", "action", "status", "duration_ms", "tool_name"]:
            if hasattr(record, field):
                value = getattr(record, field)
                if value is not None:
                    extra_fields.append(f"{field}={value}")
        
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
    if structured:
        formatter = StructuredFormatter(fmt)
    else:
        formatter = logging.Formatter(fmt)
    
    handler.setFormatter(formatter)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Remove existing handlers
    root_logger.handlers.clear()
    root_logger.addHandler(handler)


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Get configured logger with optional name.
    
    Args:
        name: Logger name (uses caller's module if None).
        
    Returns:
        Logger instance.
    """
    return logging.getLogger(name or __name__)


def set_request_id(request_id: str | None = None) -> str:
    """Set request ID for current context.
    
    Args:
        request_id: Request ID to set (generates UUID if None).
        
    Returns:
        The request ID that was set.
    """
    rid = request_id or str(uuid.uuid4())
    request_id_var.set(rid)
    return rid


def get_request_id() -> str | None:
    """Get current request ID from context."""
    return request_id_var.get()


def clear_request_id() -> None:
    """Clear request ID from context."""
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
