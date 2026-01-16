"""Resilience utilities for retry and timeout handling.

This module provides retry/timeout wrappers for LLM and tool execution
with exponential backoff and configurable policies.
"""

from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, TypeVar

from jarvis.core.exceptions import RetryableError, TimeoutError as JarvisTimeoutError

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class RetryPolicy:
    """Retry policy settings.
    
    Attributes:
        max_attempts: Maximum number of retry attempts (including first try).
        initial_delay: Initial delay in seconds before first retry.
        max_delay: Maximum delay in seconds between retries.
        exponential_base: Base for exponential backoff (delay *= base ** attempt).
        jitter: Add random jitter to delays (0.0-1.0 = 0-100% of delay).
        retryable_exceptions: Tuple of exception types that should trigger retry.
    """
    
    max_attempts: int = 3
    initial_delay: float = 1.0
    max_delay: float = 30.0
    exponential_base: float = 2.0
    jitter: float = 0.1
    retryable_exceptions: tuple[type[Exception], ...] = field(
        default_factory=lambda: (RetryableError, ConnectionError, asyncio.TimeoutError)
    )
    
    def calculate_delay(self, attempt: int) -> float:
        """Calculate delay for given attempt number with exponential backoff and jitter.
        
        Args:
            attempt: Current attempt number (0-indexed).
            
        Returns:
            Delay in seconds.
        """
        # Exponential backoff
        delay = min(self.initial_delay * (self.exponential_base ** attempt), self.max_delay)
        
        # Add jitter
        if self.jitter > 0:
            jitter_amount = delay * self.jitter * random.random()
            delay += jitter_amount
            
        return delay
    
    def should_retry(self, exception: Exception, attempt: int) -> bool:
        """Check if exception should trigger retry.
        
        Args:
            exception: Exception that was raised.
            attempt: Current attempt number (0-indexed).
            
        Returns:
            True if should retry, False otherwise.
        """
        # Check if we have attempts left
        if attempt >= self.max_attempts - 1:
            return False
            
        # Check if exception is retryable
        return isinstance(exception, self.retryable_exceptions)


class ResilientExecutor:
    """Wrapper for executing callables with retry/timeout semantics."""

    def __init__(
        self,
        retry_policy: RetryPolicy | None = None,
        timeout_seconds: float | None = None,
        operation_name: str = "operation",
    ):
        """Initialize resilient executor.
        
        Args:
            retry_policy: Retry policy to use (default: 3 attempts).
            timeout_seconds: Timeout in seconds (default: no timeout).
            operation_name: Name for logging purposes.
        """
        self.retry_policy = retry_policy or RetryPolicy()
        self.timeout_seconds = timeout_seconds
        self.operation_name = operation_name

    async def run_async(
        self,
        func: Callable[[], Coroutine[Any, Any, T]],
        *,
        timeout: float | None = None,
        retry_policy: RetryPolicy | None = None,
    ) -> T:
        """Execute an async function with retry/timeout per policy.
        
        Args:
            func: Async callable to execute.
            timeout: Override default timeout (seconds).
            retry_policy: Override default retry policy.
            
        Returns:
            Result from successful execution.
            
        Raises:
            JarvisTimeoutError: If operation times out.
            Exception: Last exception if all retries fail.
        """
        policy = retry_policy or self.retry_policy
        timeout_val = timeout if timeout is not None else self.timeout_seconds
        
        last_exception: Exception | None = None
        
        for attempt in range(policy.max_attempts):
            try:
                logger.debug(
                    f"{self.operation_name}: attempt {attempt + 1}/{policy.max_attempts}"
                )
                
                # Execute with timeout if specified
                if timeout_val:
                    result = await asyncio.wait_for(func(), timeout=timeout_val)
                else:
                    result = await func()
                    
                if attempt > 0:
                    logger.info(
                        f"{self.operation_name}: succeeded on attempt {attempt + 1}"
                    )
                return result
                
            except asyncio.TimeoutError as e:
                last_exception = JarvisTimeoutError(
                    f"{self.operation_name} timed out after {timeout_val}s",
                    timeout_seconds=timeout_val or 0.0,
                )
                logger.warning(
                    f"{self.operation_name}: timeout on attempt {attempt + 1}/{policy.max_attempts}"
                )
                
                if not policy.should_retry(e, attempt):
                    raise last_exception from e
                    
            except Exception as e:
                last_exception = e
                logger.warning(
                    f"{self.operation_name}: error on attempt {attempt + 1}/{policy.max_attempts}: {e}"
                )
                
                if not policy.should_retry(e, attempt):
                    raise
                    
            # Wait before retry
            if attempt < policy.max_attempts - 1:
                delay = policy.calculate_delay(attempt)
                logger.debug(f"{self.operation_name}: retrying in {delay:.2f}s")
                await asyncio.sleep(delay)
        
        # All retries exhausted
        logger.error(
            f"{self.operation_name}: all {policy.max_attempts} attempts failed"
        )
        if last_exception:
            raise last_exception
        raise RuntimeError(f"{self.operation_name}: all retry attempts failed")


# Convenience functions for common patterns

async def retry_async(
    func: Callable[[], Coroutine[Any, Any, T]],
    *,
    max_attempts: int = 3,
    timeout: float | None = None,
    operation_name: str = "operation",
) -> T:
    """Execute async function with default retry policy.
    
    Args:
        func: Async callable to execute.
        max_attempts: Maximum number of attempts.
        timeout: Timeout in seconds.
        operation_name: Name for logging.
        
    Returns:
        Result from successful execution.
    """
    policy = RetryPolicy(max_attempts=max_attempts)
    executor = ResilientExecutor(
        retry_policy=policy,
        timeout_seconds=timeout,
        operation_name=operation_name,
    )
    return await executor.run_async(func)


async def with_timeout(
    func: Callable[[], Coroutine[Any, Any, T]],
    timeout: float,
    operation_name: str = "operation",
) -> T:
    """Execute async function with timeout (no retries).
    
    Args:
        func: Async callable to execute.
        timeout: Timeout in seconds.
        operation_name: Name for logging.
        
    Returns:
        Result from successful execution.
        
    Raises:
        JarvisTimeoutError: If operation times out.
    """
    policy = RetryPolicy(max_attempts=1)
    executor = ResilientExecutor(
        retry_policy=policy,
        timeout_seconds=timeout,
        operation_name=operation_name,
    )
    return await executor.run_async(func)
