"""
Execution State Storage for Chat V4

Handles persistence of ExecutionState during execution.
Uses database storage for reliability, debugging, and audit trails.
"""

import logging
from typing import Optional

from .state import ExecutionState
from .errors import StorageError

logger = logging.getLogger(__name__)


class ExecutionStorage:
    """
    Storage backend for ExecutionState using database.

    Uses ExecutionStateRecord model for:
    - Persistence across server restarts
    - Queryable state for debugging
    - Audit trail of all executions
    - Support for paused/resumed executions
    """

    @classmethod
    def save(cls, state: ExecutionState, conversation=None, user=None) -> None:
        """
        Save execution state to database.

        Args:
            state: The ExecutionState to save
            conversation: Conversation model instance (required for new states)
            user: User model instance (required for new states)
        """
        from .models import ExecutionStateRecord

        try:
            # Try to get existing record
            try:
                record = ExecutionStateRecord.objects.get(
                    execution_id=state.execution_id
                )
                record.save_state(state)
                logger.debug(f"Updated execution state {state.execution_id}")
            except ExecutionStateRecord.DoesNotExist:
                # Create new record
                if not conversation or not user:
                    raise StorageError(
                        "conversation and user required for new execution state"
                    )
                ExecutionStateRecord.create_from_state(state, conversation, user)
                logger.debug(f"Created execution state {state.execution_id}")

        except Exception as e:
            logger.error(f"Failed to save execution state: {e}")
            raise StorageError(f"Failed to save execution state: {e}")

    @classmethod
    def load(cls, execution_id: str) -> Optional[ExecutionState]:
        """
        Load execution state from database.

        Args:
            execution_id: The execution ID to load

        Returns:
            ExecutionState if found, None otherwise
        """
        from .models import ExecutionStateRecord

        try:
            record = ExecutionStateRecord.objects.get(execution_id=execution_id)
            return record.load_state()
        except ExecutionStateRecord.DoesNotExist:
            return None
        except Exception as e:
            logger.error(f"Failed to load execution state {execution_id}: {e}")
            return None

    @classmethod
    def delete(cls, execution_id: str) -> None:
        """
        Remove execution state from database.

        Note: Consider keeping for audit trail instead of deleting.

        Args:
            execution_id: The execution ID to delete
        """
        from .models import ExecutionStateRecord

        try:
            ExecutionStateRecord.objects.filter(
                execution_id=execution_id
            ).delete()
            logger.debug(f"Deleted execution state {execution_id}")
        except Exception as e:
            logger.warning(f"Failed to delete execution state: {e}")

    @classmethod
    def exists(cls, execution_id: str) -> bool:
        """
        Check if an execution state exists.

        Args:
            execution_id: The execution ID to check

        Returns:
            True if exists, False otherwise
        """
        from .models import ExecutionStateRecord

        return ExecutionStateRecord.objects.filter(
            execution_id=execution_id
        ).exists()

    @classmethod
    def update_status(cls, execution_id: str, status: str) -> bool:
        """
        Quick update of just the status field.

        Args:
            execution_id: The execution ID
            status: New status value

        Returns:
            True if successful, False if execution not found
        """
        from .models import ExecutionStateRecord

        try:
            record = ExecutionStateRecord.objects.get(execution_id=execution_id)
            state = record.load_state()
            state.status = status
            record.save_state(state)
            return True
        except ExecutionStateRecord.DoesNotExist:
            return False

    @classmethod
    def get_active_for_conversation(
        cls,
        conversation_id: str
    ) -> Optional[ExecutionState]:
        """
        Get the active (paused) execution for a conversation.

        Args:
            conversation_id: The conversation ID

        Returns:
            ExecutionState if found and still active, None otherwise
        """
        from .models import ExecutionStateRecord

        record = ExecutionStateRecord.get_active_for_conversation(conversation_id)
        if record:
            return record.load_state()
        return None

    @classmethod
    def get_awaiting_user(
        cls,
        conversation_id: str
    ) -> Optional[ExecutionState]:
        """
        Get execution awaiting user response.

        Args:
            conversation_id: The conversation ID

        Returns:
            ExecutionState if found, None otherwise
        """
        from .models import ExecutionStateRecord

        record = ExecutionStateRecord.get_awaiting_user(conversation_id)
        if record:
            return record.load_state()
        return None

    @classmethod
    def get_recent_for_user(
        cls,
        user_id: int,
        limit: int = 10
    ) -> list:
        """
        Get recent executions for a user (for debugging/admin).

        Args:
            user_id: The user ID
            limit: Maximum number to return

        Returns:
            List of ExecutionStateRecord objects
        """
        from .models import ExecutionStateRecord

        return list(
            ExecutionStateRecord.objects.filter(user_id=user_id)
            .order_by('-created_at')[:limit]
        )

    @classmethod
    def get_failed_executions(
        cls,
        hours: int = 24,
        limit: int = 50
    ) -> list:
        """
        Get recent failed executions (for debugging).

        Args:
            hours: Look back this many hours
            limit: Maximum number to return

        Returns:
            List of ExecutionStateRecord objects
        """
        from .models import ExecutionStateRecord
        from django.utils import timezone
        from datetime import timedelta

        since = timezone.now() - timedelta(hours=hours)

        return list(
            ExecutionStateRecord.objects.filter(
                status='failed',
                created_at__gte=since
            ).order_by('-created_at')[:limit]
        )

    @classmethod
    def cleanup_old_executions(cls, days: int = 30) -> int:
        """
        Clean up old completed executions.

        Args:
            days: Delete executions older than this

        Returns:
            Number of executions deleted
        """
        from .models import ExecutionStateRecord
        from django.utils import timezone
        from datetime import timedelta

        cutoff = timezone.now() - timedelta(days=days)

        result = ExecutionStateRecord.objects.filter(
            status__in=['completed', 'failed'],
            created_at__lt=cutoff
        ).delete()

        count = result[0] if result else 0
        logger.info(f"Cleaned up {count} old executions")
        return count


class ExecutionLogger:
    """
    Logging for execution events.

    Provides structured logging for debugging and monitoring.
    """

    @classmethod
    def log_start(cls, state: ExecutionState) -> None:
        """Log execution start"""
        logger.info(
            f"Execution started: {state.execution_id} "
            f"for conversation {state.conversation_id} "
            f"request: {state.user_request[:100]}"
        )

    @classmethod
    def log_step(cls, state: ExecutionState, step_id: int, result: dict) -> None:
        """Log step execution"""
        logger.info(
            f"Step {step_id} completed in {state.execution_id}: "
            f"success={result.get('success')}"
        )

    @classmethod
    def log_complete(cls, state: ExecutionState) -> None:
        """Log execution completion"""
        logger.info(
            f"Execution completed: {state.execution_id} "
            f"status={state.status} "
            f"tokens={state.total_tokens}"
        )

    @classmethod
    def log_error(cls, state: ExecutionState, error: str) -> None:
        """Log execution error"""
        logger.error(
            f"Execution error in {state.execution_id}: {error}"
        )

    @classmethod
    def log_replan(cls, state: ExecutionState, reason: str) -> None:
        """Log replanning event"""
        logger.info(
            f"Replanning in {state.execution_id}: {reason}"
        )
