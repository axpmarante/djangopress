"""
Retry Logic for Chat V4

Provides comprehensive retry handling for step execution,
including exponential backoff, batch reduction, and retry context generation.
"""

import time
import logging
from dataclasses import dataclass
from typing import Optional, Callable, Any
from functools import wraps

from .errors import ExecutionError, ErrorCategory, RetryStrategy

logger = logging.getLogger(__name__)


@dataclass
class RetryConfig:
    """Configuration for retry behavior"""
    max_retries: int = 3
    initial_delay: float = 1.0
    max_delay: float = 30.0
    exponential_base: float = 2.0
    jitter: bool = True


@dataclass
class RetryContext:
    """Context passed to retried operations"""
    attempt: int
    max_attempts: int
    last_error: Optional[ExecutionError]
    modification: Optional[str]
    reduced_batch_size: Optional[int]

    @property
    def is_retry(self) -> bool:
        return self.attempt > 1


class RetryManager:
    """
    Manages retry logic for step execution.

    Provides:
    - Exponential backoff delays
    - Batch size reduction for rate limits/timeouts
    - Context generation for retry attempts
    - Decorator for automatic retries
    """

    def __init__(self, config: RetryConfig = None):
        """Initialize retry manager"""
        self.config = config or RetryConfig()

    def should_retry(
        self,
        error: ExecutionError,
        attempt: int
    ) -> bool:
        """
        Determine if an operation should be retried.

        Args:
            error: The error that occurred
            attempt: Current attempt number (1-indexed)

        Returns:
            True if should retry, False otherwise
        """
        if attempt >= self.config.max_retries:
            return False

        return error.retryable

    def get_delay(self, attempt: int) -> float:
        """
        Calculate delay before next retry.

        Uses exponential backoff with optional jitter.

        Args:
            attempt: Current attempt number

        Returns:
            Delay in seconds
        """
        delay = min(
            self.config.initial_delay * (self.config.exponential_base ** (attempt - 1)),
            self.config.max_delay
        )

        if self.config.jitter:
            import random
            delay = delay * (0.5 + random.random())

        return delay

    def get_retry_context(
        self,
        error: ExecutionError,
        attempt: int,
        original_batch_size: int = None
    ) -> RetryContext:
        """
        Generate context for retry attempt.

        Args:
            error: The error that occurred
            attempt: Next attempt number
            original_batch_size: Original batch size if applicable

        Returns:
            RetryContext with modification hints
        """
        modification = None
        reduced_batch_size = None

        # Determine modification based on error category
        if error.category == ErrorCategory.RATE_LIMIT:
            modification = "Reduce request rate and batch size"
            if original_batch_size:
                reduced_batch_size = max(1, original_batch_size // 2)

        elif error.category == ErrorCategory.TIMEOUT:
            modification = "Process fewer items to avoid timeout"
            if original_batch_size:
                reduced_batch_size = max(1, original_batch_size // 2)

        elif error.category == ErrorCategory.VALIDATION:
            modification = "Verify and fix input data format"

        elif error.category == ErrorCategory.PARSE_ERROR:
            modification = "Request simpler response format"

        elif error.category == ErrorCategory.LLM_ERROR:
            modification = "Simplify the request"

        else:
            modification = "Retry with adjusted parameters"

        return RetryContext(
            attempt=attempt,
            max_attempts=self.config.max_retries,
            last_error=error,
            modification=modification,
            reduced_batch_size=reduced_batch_size
        )

    def wait_before_retry(self, attempt: int) -> None:
        """
        Wait appropriate delay before retry.

        Args:
            attempt: Current attempt number
        """
        delay = self.get_delay(attempt)
        logger.debug(f"Waiting {delay:.2f}s before retry attempt {attempt}")
        time.sleep(delay)

    def retry_decorator(
        self,
        on_retry: Callable[[RetryContext], None] = None
    ):
        """
        Decorator for automatic retries.

        Args:
            on_retry: Optional callback called before each retry

        Usage:
            @retry_manager.retry_decorator()
            def some_operation():
                ...
        """
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                last_error = None

                for attempt in range(1, self.config.max_retries + 1):
                    try:
                        return func(*args, **kwargs)

                    except Exception as e:
                        error = ExecutionError.from_exception(e)
                        last_error = error

                        if not self.should_retry(error, attempt):
                            raise

                        context = self.get_retry_context(error, attempt + 1)

                        if on_retry:
                            on_retry(context)

                        self.wait_before_retry(attempt)

                # Should not reach here, but if we do, raise last error
                raise last_error

            return wrapper
        return decorator


class BatchReducer:
    """
    Handles batch size reduction for retry attempts.

    When operations fail due to rate limits or timeouts,
    this helps reduce batch sizes progressively.
    """

    DEFAULT_REDUCTION_FACTOR = 0.5
    MIN_BATCH_SIZE = 1

    @classmethod
    def reduce(
        cls,
        current_size: int,
        factor: float = None
    ) -> int:
        """
        Reduce batch size by factor.

        Args:
            current_size: Current batch size
            factor: Reduction factor (default 0.5)

        Returns:
            Reduced batch size (minimum 1)
        """
        factor = factor or cls.DEFAULT_REDUCTION_FACTOR
        new_size = int(current_size * factor)
        return max(cls.MIN_BATCH_SIZE, new_size)

    @classmethod
    def split_batch(
        cls,
        items: list,
        batch_size: int
    ) -> list[list]:
        """
        Split items into batches.

        Args:
            items: List of items to batch
            batch_size: Maximum items per batch

        Returns:
            List of batches
        """
        if batch_size <= 0:
            batch_size = 1

        return [
            items[i:i + batch_size]
            for i in range(0, len(items), batch_size)
        ]

    @classmethod
    def estimate_safe_batch_size(
        cls,
        error_category: ErrorCategory,
        current_size: int,
        attempt: int
    ) -> int:
        """
        Estimate safe batch size based on error and attempt.

        Args:
            error_category: Type of error that occurred
            current_size: Current batch size
            attempt: Current attempt number

        Returns:
            Estimated safe batch size
        """
        # More aggressive reduction for certain errors
        if error_category == ErrorCategory.RATE_LIMIT:
            # Reduce more aggressively for rate limits
            factor = 0.3 ** attempt
        elif error_category == ErrorCategory.TIMEOUT:
            # Moderate reduction for timeouts
            factor = 0.5 ** attempt
        else:
            # Default reduction
            factor = 0.5 ** attempt

        return max(cls.MIN_BATCH_SIZE, int(current_size * factor))


class CircuitBreaker:
    """
    Circuit breaker pattern for preventing cascading failures.

    When too many failures occur, the circuit "opens" and
    fails fast without attempting the operation.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        reset_timeout: float = 60.0
    ):
        """
        Initialize circuit breaker.

        Args:
            failure_threshold: Failures before opening circuit
            reset_timeout: Seconds before attempting reset
        """
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.failures = 0
        self.last_failure_time = 0
        self.state = "closed"  # closed, open, half-open

    def record_failure(self) -> None:
        """Record a failure"""
        self.failures += 1
        self.last_failure_time = time.time()

        if self.failures >= self.failure_threshold:
            self.state = "open"
            logger.warning("Circuit breaker opened")

    def record_success(self) -> None:
        """Record a success"""
        self.failures = 0
        self.state = "closed"

    def can_execute(self) -> bool:
        """
        Check if operation can be attempted.

        Returns:
            True if operation should be attempted
        """
        if self.state == "closed":
            return True

        if self.state == "open":
            # Check if reset timeout has passed
            if time.time() - self.last_failure_time > self.reset_timeout:
                self.state = "half-open"
                return True
            return False

        # half-open: allow one attempt
        return True

    def __call__(self, func: Callable) -> Callable:
        """Use as decorator"""
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not self.can_execute():
                raise Exception("Circuit breaker is open")

            try:
                result = func(*args, **kwargs)
                self.record_success()
                return result
            except Exception:
                self.record_failure()
                raise

        return wrapper


# Default instances
default_retry_manager = RetryManager()
default_batch_reducer = BatchReducer()
