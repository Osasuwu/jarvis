"""Tests for structured logging functionality."""

import logging

from jarvis.observability.logging import (
    StructuredFormatter,
    clear_request_id,
    get_logger,
    get_request_id,
    set_request_id,
    setup_logging,
)


def test_setup_logging_default():
    """Test basic logging setup."""
    setup_logging(level="INFO")
    logger = logging.getLogger()
    assert logger.level == logging.INFO


def test_setup_logging_debug():
    """Test logging setup with DEBUG level."""
    setup_logging(level="DEBUG")
    logger = logging.getLogger()
    assert logger.level == logging.DEBUG


def test_get_logger():
    """Test logger retrieval."""
    logger = get_logger("test_module")
    assert logger.name == "test_module"
    assert isinstance(logger, logging.Logger)


def test_set_and_get_request_id():
    """Test request ID context management."""
    # Set custom ID
    rid = set_request_id("test-request-123")
    assert rid == "test-request-123"
    assert get_request_id() == "test-request-123"

    # Clear ID
    clear_request_id()
    assert get_request_id() is None


def test_set_request_id_auto_generate():
    """Test automatic request ID generation."""
    rid = set_request_id()
    assert rid is not None
    assert len(rid) > 0
    assert get_request_id() == rid

    clear_request_id()


def test_structured_formatter():
    """Test structured formatter adds extra fields."""
    formatter = StructuredFormatter("%(message)s")

    # Create log record
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="test message",
        args=(),
        exc_info=None,
    )

    # Add extra fields
    record.component = "test_component"
    record.action = "test_action"
    record.status = "success"

    formatted = formatter.format(record)
    assert "test message" in formatted
    assert "component=test_component" in formatted
    assert "action=test_action" in formatted
    assert "status=success" in formatted


def test_structured_formatter_with_request_id():
    """Test formatter includes request ID when set."""
    formatter = StructuredFormatter("%(message)s")

    # Set request ID
    set_request_id("req-456")

    # Create log record
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="test message",
        args=(),
        exc_info=None,
    )

    formatted = formatter.format(record)
    assert "request_id=req-456" in formatted

    clear_request_id()


def test_structured_formatter_optional_fields():
    """Test formatter handles missing optional fields gracefully."""
    formatter = StructuredFormatter("%(message)s")

    # Create minimal log record
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="test message",
        args=(),
        exc_info=None,
    )

    # Should not crash with no extra fields
    formatted = formatter.format(record)
    assert "test message" in formatted


def test_request_id_isolation():
    """Test request IDs are isolated across contexts."""
    # In real async code, each context would have its own ID
    # For sync test, just verify basic isolation

    set_request_id("req-1")
    assert get_request_id() == "req-1"

    clear_request_id()
    assert get_request_id() is None

    set_request_id("req-2")
    assert get_request_id() == "req-2"

    clear_request_id()
