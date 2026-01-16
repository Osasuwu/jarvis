"""Tests for resilience and error handling."""

import asyncio
import pytest
from jarvis.core.exceptions import (
    RetryableError,
    NonRetryableError,
    TimeoutError as JarvisTimeoutError,
)
from jarvis.core.resilience import (
    RetryPolicy,
    ResilientExecutor,
    retry_async,
    with_timeout,
)


class TestRetryPolicy:
    """Test RetryPolicy configuration and behavior."""

    def test_default_policy(self):
        """Test default retry policy settings."""
        policy = RetryPolicy()
        assert policy.max_attempts == 3
        assert policy.initial_delay == 1.0
        assert policy.max_delay == 30.0
        assert policy.exponential_base == 2.0

    def test_calculate_delay_exponential(self):
        """Test exponential backoff calculation."""
        policy = RetryPolicy(initial_delay=1.0, exponential_base=2.0, jitter=0.0)
        
        # First retry (attempt 0)
        delay0 = policy.calculate_delay(0)
        assert delay0 == 1.0
        
        # Second retry (attempt 1)
        delay1 = policy.calculate_delay(1)
        assert delay1 == 2.0
        
        # Third retry (attempt 2)
        delay2 = policy.calculate_delay(2)
        assert delay2 == 4.0

    def test_calculate_delay_with_max(self):
        """Test delay capped at max_delay."""
        policy = RetryPolicy(initial_delay=10.0, max_delay=15.0, jitter=0.0)
        
        # Should be capped
        delay = policy.calculate_delay(5)
        assert delay == 15.0

    def test_calculate_delay_with_jitter(self):
        """Test jitter adds randomness."""
        policy = RetryPolicy(initial_delay=1.0, jitter=0.5, exponential_base=1.0)
        
        # With jitter, delay should vary
        delays = [policy.calculate_delay(0) for _ in range(10)]
        assert len(set(delays)) > 1  # Should have variation
        assert all(1.0 <= d <= 1.5 for d in delays)  # Within jitter range

    def test_should_retry_on_retryable_error(self):
        """Test that retryable errors trigger retry."""
        policy = RetryPolicy(max_attempts=3)
        
        error = RetryableError("transient error")
        assert policy.should_retry(error, 0) is True
        assert policy.should_retry(error, 1) is True
        assert policy.should_retry(error, 2) is False  # Last attempt

    def test_should_not_retry_on_non_retryable_error(self):
        """Test that non-retryable errors don't trigger retry."""
        policy = RetryPolicy(max_attempts=3)
        
        error = NonRetryableError("permanent error")
        assert policy.should_retry(error, 0) is False


class TestResilientExecutor:
    """Test ResilientExecutor retry and timeout behavior."""

    @pytest.mark.asyncio
    async def test_success_first_attempt(self):
        """Test successful execution on first attempt."""
        executor = ResilientExecutor(operation_name="test_op")
        
        async def successful_func():
            return "success"
        
        result = await executor.run_async(successful_func)
        assert result == "success"

    @pytest.mark.asyncio
    async def test_success_after_retry(self):
        """Test successful execution after transient failure."""
        executor = ResilientExecutor(
            retry_policy=RetryPolicy(max_attempts=3, initial_delay=0.1),
            operation_name="test_op",
        )
        
        attempts = []
        
        async def flaky_func():
            attempts.append(1)
            if len(attempts) < 2:
                raise RetryableError("transient error")
            return "success"
        
        result = await executor.run_async(flaky_func)
        assert result == "success"
        assert len(attempts) == 2  # Failed once, succeeded on retry

    @pytest.mark.asyncio
    async def test_all_retries_exhausted(self):
        """Test that all retries are exhausted on persistent failure."""
        executor = ResilientExecutor(
            retry_policy=RetryPolicy(max_attempts=2, initial_delay=0.1),
            operation_name="test_op",
        )
        
        async def always_fails():
            raise RetryableError("persistent error")
        
        with pytest.raises(RetryableError, match="persistent error"):
            await executor.run_async(always_fails)

    @pytest.mark.asyncio
    async def test_non_retryable_error_no_retry(self):
        """Test that non-retryable errors fail immediately."""
        executor = ResilientExecutor(
            retry_policy=RetryPolicy(max_attempts=3, initial_delay=0.1),
            operation_name="test_op",
        )
        
        attempts = []
        
        async def non_retryable_func():
            attempts.append(1)
            raise NonRetryableError("permanent error")
        
        with pytest.raises(NonRetryableError, match="permanent error"):
            await executor.run_async(non_retryable_func)
        
        assert len(attempts) == 1  # Should not retry

    @pytest.mark.asyncio
    async def test_timeout(self):
        """Test timeout enforcement."""
        executor = ResilientExecutor(
            timeout_seconds=0.1,
            operation_name="test_op",
        )
        
        async def slow_func():
            await asyncio.sleep(1.0)
            return "too slow"
        
        with pytest.raises(JarvisTimeoutError):
            await executor.run_async(slow_func)

    @pytest.mark.asyncio
    async def test_timeout_with_retry(self):
        """Test timeout triggers retry on retryable timeout."""
        executor = ResilientExecutor(
            retry_policy=RetryPolicy(max_attempts=2, initial_delay=0.05),
            timeout_seconds=0.1,
            operation_name="test_op",
        )
        
        attempts = []
        
        async def sometimes_slow_func():
            attempts.append(1)
            if len(attempts) < 2:
                await asyncio.sleep(1.0)  # Will timeout
            return "success"
        
        # Timeout is retryable, so should succeed on retry
        result = await executor.run_async(sometimes_slow_func)
        assert result == "success"
        assert len(attempts) == 2


class TestConvenienceFunctions:
    """Test convenience functions."""

    @pytest.mark.asyncio
    async def test_retry_async(self):
        """Test retry_async convenience function."""
        attempts = []
        
        async def flaky_func():
            attempts.append(1)
            if len(attempts) < 2:
                raise RetryableError("transient")
            return "ok"
        
        result = await retry_async(flaky_func, max_attempts=3)
        assert result == "ok"
        assert len(attempts) == 2

    @pytest.mark.asyncio
    async def test_with_timeout(self):
        """Test with_timeout convenience function."""
        async def fast_func():
            return "done"
        
        result = await with_timeout(fast_func, timeout=1.0)
        assert result == "done"

    @pytest.mark.asyncio
    async def test_with_timeout_exceeded(self):
        """Test with_timeout raises on timeout."""
        async def slow_func():
            await asyncio.sleep(1.0)
            return "too slow"
        
        with pytest.raises(JarvisTimeoutError):
            await with_timeout(slow_func, timeout=0.1)
