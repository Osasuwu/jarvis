"""Resilience utilities (skeleton).

This module will provide retry/timeout wrappers for LLM and tool execution.
Implementation to follow after design approval.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Coroutine, Optional, Type

from jarvis.core.exceptions import RetryableError, TimeoutError


@dataclass
class RetryPolicy:
    """Retry policy settings.

    TODO:
    - max_attempts, backoff strategy (exponential with jitter), retryable exceptions.
    - per-call overrides for tools vs LLM.
    """

    max_attempts: int = 1
    # TODO: add backoff parameters and retryable exception set


class ResilientExecutor:
    """Wrapper for executing callables with retry/timeout semantics."""

    def __init__(self, retry_policy: RetryPolicy | None = None, timeout_seconds: float | None = None):
        self.retry_policy = retry_policy or RetryPolicy()
        self.timeout_seconds = timeout_seconds

    async def run_async(self, func: Callable[[], Coroutine], *, retryable: tuple[Type[Exception], ...] = (RetryableError,)):
        """Execute an async function with retry/timeout per policy.

        Placeholder implementation; real logic will add retries, timeouts, and
        structured logging of attempts.
        """

        # TODO: implement retry loop with backoff and asyncio timeout
        # TODO: integrate structured logging hooks
        raise NotImplementedError("Resilient execution not yet implemented")
