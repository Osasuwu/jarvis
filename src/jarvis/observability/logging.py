"""Structured logging setup (skeleton).

Keeps stdlib logging for now; ready to swap to structlog or OpenTelemetry later.
"""

from __future__ import annotations

import logging
from typing import Optional


DEFAULT_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def setup_logging(level: str = "INFO", fmt: str = DEFAULT_FORMAT) -> None:
    """Configure base logging.

    TODO:
    - Add structured formatter (JSON) with fields: component, action, status, duration_ms, request_id.
    - Add correlation id propagation.
    - Provide OTLP/Prometheus hooks when available.
    """

    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO), format=fmt)


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Get configured logger (wrapper for future swaps)."""

    return logging.getLogger(name or __name__)
