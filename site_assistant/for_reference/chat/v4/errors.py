"""
Error Types and Handling for Chat V4

Provides structured error handling with categories, retry strategies,
and actionable error messages.
"""

from dataclasses import dataclass
from typing import Optional, Literal
from enum import Enum


class ErrorCategory(Enum):
    """Categories of errors for retry strategy decisions"""

    RATE_LIMIT = "rate_limit"       # API rate limit hit
    TIMEOUT = "timeout"             # Request timed out
    VALIDATION = "validation"       # Invalid data/parameters
    NOT_FOUND = "not_found"         # Resource doesn't exist
    PERMISSION = "permission"       # Access denied
    LLM_ERROR = "llm_error"         # LLM service error
    PARSE_ERROR = "parse_error"     # Failed to parse LLM response
    DATABASE_ERROR = "database"     # Database operation failed
    UNKNOWN = "unknown"             # Unclassified error


@dataclass
class ExecutionError:
    """Structured error information for execution failures"""

    category: ErrorCategory
    message: str
    step_id: Optional[int] = None
    retryable: bool = False
    suggested_action: Optional[str] = None
    original_exception: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for storage"""
        return {
            'category': self.category.value,
            'message': self.message,
            'step_id': self.step_id,
            'retryable': self.retryable,
            'suggested_action': self.suggested_action,
            'original_exception': self.original_exception
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'ExecutionError':
        """Create from dictionary"""
        return cls(
            category=ErrorCategory(data['category']),
            message=data['message'],
            step_id=data.get('step_id'),
            retryable=data.get('retryable', False),
            suggested_action=data.get('suggested_action'),
            original_exception=data.get('original_exception')
        )

    @classmethod
    def from_exception(
        cls,
        e: Exception,
        step_id: int = None
    ) -> 'ExecutionError':
        """Create ExecutionError from an exception, auto-classifying it"""

        error_str = str(e).lower()
        exception_type = type(e).__name__

        # Rate limit errors
        if any(x in error_str for x in ['rate limit', 'rate_limit', '429', 'too many requests']):
            return cls(
                category=ErrorCategory.RATE_LIMIT,
                message=str(e),
                step_id=step_id,
                retryable=True,
                suggested_action="Wait and retry with smaller batch",
                original_exception=exception_type
            )

        # Timeout errors
        if any(x in error_str for x in ['timeout', 'timed out', 'deadline exceeded']):
            return cls(
                category=ErrorCategory.TIMEOUT,
                message=str(e),
                step_id=step_id,
                retryable=True,
                suggested_action="Retry with simpler request",
                original_exception=exception_type
            )

        # Not found errors
        if any(x in error_str for x in ['not found', 'does not exist', '404', 'matching query does not exist']):
            return cls(
                category=ErrorCategory.NOT_FOUND,
                message=str(e),
                step_id=step_id,
                retryable=False,
                suggested_action="Verify the resource exists",
                original_exception=exception_type
            )

        # Permission errors
        if any(x in error_str for x in ['permission', 'denied', 'forbidden', '403', 'unauthorized', '401']):
            return cls(
                category=ErrorCategory.PERMISSION,
                message=str(e),
                step_id=step_id,
                retryable=False,
                suggested_action="Check user permissions",
                original_exception=exception_type
            )

        # Validation errors
        if any(x in error_str for x in ['invalid', 'validation', 'required field', 'must be']):
            return cls(
                category=ErrorCategory.VALIDATION,
                message=str(e),
                step_id=step_id,
                retryable=True,
                suggested_action="Check data format and required fields",
                original_exception=exception_type
            )

        # LLM specific errors
        if any(x in error_str for x in ['openai', 'anthropic', 'gemini', 'api error', 'model']):
            return cls(
                category=ErrorCategory.LLM_ERROR,
                message=str(e),
                step_id=step_id,
                retryable=True,
                suggested_action="Retry or try different model",
                original_exception=exception_type
            )

        # JSON parse errors
        if any(x in error_str for x in ['json', 'parse', 'decode', 'unexpected token']):
            return cls(
                category=ErrorCategory.PARSE_ERROR,
                message=str(e),
                step_id=step_id,
                retryable=True,
                suggested_action="Request clearer JSON format",
                original_exception=exception_type
            )

        # Database errors
        if any(x in error_str for x in ['database', 'integrity', 'constraint', 'duplicate']):
            return cls(
                category=ErrorCategory.DATABASE_ERROR,
                message=str(e),
                step_id=step_id,
                retryable=False,
                suggested_action="Check database constraints",
                original_exception=exception_type
            )

        # Unknown/default
        return cls(
            category=ErrorCategory.UNKNOWN,
            message=str(e),
            step_id=step_id,
            retryable=True,
            suggested_action="Retry once",
            original_exception=exception_type
        )


# Custom Exceptions

class V4Exception(Exception):
    """Base exception for all V4 errors"""

    def __init__(self, message: str, error: ExecutionError = None):
        super().__init__(message)
        self.error = error


class PlanningError(V4Exception):
    """Error during planning phase"""
    pass


class StepExecutionError(V4Exception):
    """Error executing a step"""

    def __init__(self, message: str, step_id: int, error: ExecutionError):
        super().__init__(message, error)
        self.step_id = step_id


class IntakeError(V4Exception):
    """Error classifying message in intake"""
    pass


class StorageError(V4Exception):
    """Error with execution state storage"""
    pass


class LLMError(V4Exception):
    """Error calling LLM service"""
    pass


class ParseError(V4Exception):
    """Error parsing LLM response"""

    def __init__(self, message: str, raw_response: str = None):
        super().__init__(message)
        self.raw_response = raw_response


class AgentError(V4Exception):
    """Error in specialized agent"""

    def __init__(self, message: str, agent_type: str, action: str, error: ExecutionError = None):
        super().__init__(message, error)
        self.agent_type = agent_type
        self.action = action


# Retry Strategy

@dataclass
class RetryStrategy:
    """Strategy for retrying failed operations"""
    should_retry: bool
    modification: Optional[str] = None
    wait_seconds: int = 0
    reduce_batch: bool = False


class RetryHandler:
    """Determines retry strategy for failed steps"""

    MAX_RETRIES = 3

    STRATEGIES = {
        ErrorCategory.RATE_LIMIT: {
            'should_retry': True,
            'wait_seconds': 5,
            'modification': "Reduce batch size by half",
            'reduce_batch': True
        },
        ErrorCategory.TIMEOUT: {
            'should_retry': True,
            'wait_seconds': 0,
            'modification': "Process fewer items",
            'reduce_batch': True
        },
        ErrorCategory.VALIDATION: {
            'should_retry': True,
            'wait_seconds': 0,
            'modification': "Check data format and required fields"
        },
        ErrorCategory.NOT_FOUND: {
            'should_retry': False
        },
        ErrorCategory.PERMISSION: {
            'should_retry': False
        },
        ErrorCategory.LLM_ERROR: {
            'should_retry': True,
            'wait_seconds': 2,
            'modification': "Simplify request"
        },
        ErrorCategory.PARSE_ERROR: {
            'should_retry': True,
            'wait_seconds': 0,
            'modification': "Request clearer JSON format"
        },
        ErrorCategory.DATABASE_ERROR: {
            'should_retry': False
        },
        ErrorCategory.UNKNOWN: {
            'should_retry': True,
            'wait_seconds': 1,
            'modification': None
        }
    }

    @classmethod
    def get_strategy(
        cls,
        error: ExecutionError,
        retry_count: int
    ) -> RetryStrategy:
        """
        Get retry strategy for an error.

        Args:
            error: The error that occurred
            retry_count: Number of retries already attempted

        Returns:
            RetryStrategy with decision and modifications
        """
        if retry_count >= cls.MAX_RETRIES:
            return RetryStrategy(should_retry=False, modification=None)

        strategy_config = cls.STRATEGIES.get(
            error.category,
            cls.STRATEGIES[ErrorCategory.UNKNOWN]
        )

        if not strategy_config.get('should_retry', False):
            return RetryStrategy(should_retry=False, modification=None)

        return RetryStrategy(
            should_retry=True,
            modification=strategy_config.get('modification'),
            wait_seconds=strategy_config.get('wait_seconds', 0),
            reduce_batch=strategy_config.get('reduce_batch', False)
        )

    @classmethod
    def should_replan(cls, error: ExecutionError, retry_count: int) -> bool:
        """
        Determine if we should replan instead of retry.

        Returns True if:
        - Max retries exceeded for a retryable error
        - Error indicates fundamental plan problem
        """
        if retry_count >= cls.MAX_RETRIES and error.retryable:
            return True

        # Some errors suggest the plan itself is wrong
        if error.category == ErrorCategory.NOT_FOUND:
            return True

        return False
