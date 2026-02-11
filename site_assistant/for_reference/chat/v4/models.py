"""
Django Models for Chat V4

ConversationState: Persistent state across a conversation session.
Tracks summary, mentioned entities, active executions, and context.

ExecutionStateRecord: Persistent storage for execution state.
Replaces cache-based storage for reliability and debugging.
"""

from django.db import models
from django.conf import settings
import json


class ConversationState(models.Model):
    """
    Persistent conversation state stored in database.

    This model maintains context across multiple messages in a conversation,
    enabling follow-up references, conversation summaries, and execution tracking.
    """

    conversation = models.OneToOneField(
        'chat.Conversation',
        on_delete=models.CASCADE,
        related_name='v4_state',
        help_text="The conversation this state belongs to"
    )

    # Compressed conversation history
    summary = models.TextField(
        blank=True,
        default='',
        help_text="Running summary of conversation topics and actions"
    )

    topics = models.JSONField(
        default=list,
        blank=True,
        help_text="List of topics discussed: ['inbox', 'tasks', 'para']"
    )

    # Entity tracking for follow-up references
    mentioned_entities = models.JSONField(
        default=dict,
        blank=True,
        help_text="Entities mentioned in conversation: {'task': [1,2,3], 'project': [5]}"
    )

    last_created_entities = models.JSONField(
        default=dict,
        blank=True,
        help_text="Most recent entity created per type: {'task': 42}"
    )

    last_affected_entities = models.JSONField(
        default=dict,
        blank=True,
        help_text="Entities affected by last execution: {'task': [1,2,3]}"
    )

    # Execution tracking
    active_execution_id = models.CharField(
        max_length=36,
        blank=True,
        null=True,
        help_text="UUID of execution currently awaiting user response"
    )

    last_execution_summary = models.JSONField(
        null=True,
        blank=True,
        help_text="Summary of the last completed execution"
    )

    # Statistics
    message_count = models.IntegerField(
        default=0,
        help_text="Total messages in this conversation"
    )

    total_executions = models.IntegerField(
        default=0,
        help_text="Total executions performed in this conversation"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'chat_v4_conversation_state'
        verbose_name = 'V4 Conversation State'
        verbose_name_plural = 'V4 Conversation States'

    def __str__(self):
        return f"V4State for Conversation {self.conversation_id}"

    def clear_active_execution(self):
        """Clear the active execution reference"""
        self.active_execution_id = None
        self.save(update_fields=['active_execution_id', 'updated_at'])

    def set_active_execution(self, execution_id: str):
        """Set an active execution (awaiting user response)"""
        self.active_execution_id = execution_id
        self.save(update_fields=['active_execution_id', 'updated_at'])

    def update_after_execution(
        self,
        execution_summary: dict,
        created_entities: dict,
        affected_entities: dict
    ):
        """
        Update state after an execution completes.

        Args:
            execution_summary: Summary dict with execution_id, request, outcome
            created_entities: Dict of entity_type -> id for created items
            affected_entities: Dict of entity_type -> [ids] for affected items
        """
        # Update entity tracking
        for entity_type, entity_ids in affected_entities.items():
            existing = self.mentioned_entities.get(entity_type, [])
            # Keep last 20 per type to avoid unbounded growth
            self.mentioned_entities[entity_type] = (existing + entity_ids)[-20:]

        self.last_created_entities = created_entities
        self.last_affected_entities = affected_entities
        self.last_execution_summary = execution_summary
        self.active_execution_id = None
        self.total_executions += 1

        self.save(update_fields=[
            'mentioned_entities',
            'last_created_entities',
            'last_affected_entities',
            'last_execution_summary',
            'active_execution_id',
            'total_executions',
            'updated_at'
        ])

    def increment_message_count(self, count: int = 1):
        """Increment the message count"""
        self.message_count += count
        self.save(update_fields=['message_count', 'updated_at'])

    def update_summary(self, new_summary: str, new_topics: list = None):
        """Update the conversation summary"""
        self.summary = new_summary
        if new_topics:
            # Merge topics, keep unique, limit to 20
            existing_topics = set(self.topics or [])
            existing_topics.update(new_topics)
            self.topics = list(existing_topics)[-20:]
        self.save(update_fields=['summary', 'topics', 'updated_at'])

    def get_entity_references(self, entity_type: str) -> list:
        """Get mentioned entity IDs for a type"""
        return self.mentioned_entities.get(entity_type, [])

    def get_last_created(self, entity_type: str) -> int | None:
        """Get the last created entity ID for a type"""
        return self.last_created_entities.get(entity_type)

    def has_active_execution(self) -> bool:
        """Check if there's an active execution awaiting user"""
        return bool(self.active_execution_id)

    @classmethod
    def get_or_create_for_conversation(cls, conversation) -> 'ConversationState':
        """Get or create state for a conversation"""
        state, created = cls.objects.get_or_create(
            conversation=conversation,
            defaults={
                'summary': '',
                'topics': [],
                'mentioned_entities': {},
                'last_created_entities': {},
                'last_affected_entities': {}
            }
        )
        return state


class ExecutionStateRecord(models.Model):
    """
    Persistent storage for ExecutionState during plan execution.

    Replaces cache-based storage to provide:
    - Persistence across server restarts
    - Queryable state for debugging
    - Audit trail of executions
    - Support for paused/resumed executions
    """

    # Status choices for quick filtering
    STATUS_CHOICES = [
        ('planning', 'Planning'),
        ('executing', 'Executing'),
        ('awaiting_user', 'Awaiting User'),
        ('completing', 'Completing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    execution_id = models.CharField(
        max_length=36,
        primary_key=True,
        help_text="UUID of this execution"
    )

    conversation = models.ForeignKey(
        'chat.Conversation',
        on_delete=models.CASCADE,
        related_name='v4_executions',
        help_text="The conversation this execution belongs to"
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='v4_executions',
        help_text="The user who initiated this execution"
    )

    # The full serialized ExecutionState
    state_data = models.JSONField(
        help_text="Full serialized ExecutionState object"
    )

    # Denormalized fields for quick queries
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='planning',
        db_index=True,
        help_text="Current execution status"
    )

    user_request = models.TextField(
        help_text="The original user request"
    )

    # Tracking
    step_count = models.IntegerField(
        default=0,
        help_text="Total number of steps in the plan"
    )

    steps_completed = models.IntegerField(
        default=0,
        help_text="Number of steps completed"
    )

    has_errors = models.BooleanField(
        default=False,
        help_text="Whether any errors occurred"
    )

    # Token usage
    total_tokens = models.IntegerField(
        default=0,
        help_text="Total tokens used in this execution"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When execution completed (success or failure)"
    )

    class Meta:
        db_table = 'chat_v4_execution_state'
        verbose_name = 'V4 Execution State'
        verbose_name_plural = 'V4 Execution States'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['conversation', 'status']),
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['status', 'created_at']),
        ]

    def __str__(self):
        return f"Execution {self.execution_id[:8]} ({self.status})"

    def save_state(self, state: 'ExecutionState') -> None:
        """
        Update record from an ExecutionState object.

        Args:
            state: The ExecutionState to save
        """
        from .state import ExecutionState

        self.state_data = state.to_dict()
        self.status = self._map_status(state.status)
        self.user_request = state.user_request
        self.step_count = len(state.plan.steps) if state.plan else 0
        self.steps_completed = len(state.get_completed_step_ids())
        self.has_errors = state.has_failures() or bool(state.errors)
        self.total_tokens = state.total_tokens

        if state.status in ('completed', 'failed'):
            from django.utils import timezone
            self.completed_at = timezone.now()

        self.save()

    def load_state(self) -> 'ExecutionState':
        """
        Load ExecutionState from this record.

        Returns:
            ExecutionState object
        """
        from .state import ExecutionState
        return ExecutionState.from_dict(self.state_data)

    def _map_status(self, state_status: str) -> str:
        """Map ExecutionState status to record status"""
        mapping = {
            'planning': 'planning',
            'stepping': 'executing',
            'executing_step': 'executing',
            'awaiting_user': 'awaiting_user',
            'finishing': 'completing',
            'completed': 'completed',
            'failed': 'failed',
        }
        return mapping.get(state_status, 'executing')

    @classmethod
    def create_from_state(cls, state: 'ExecutionState', conversation, user) -> 'ExecutionStateRecord':
        """
        Create a new record from an ExecutionState.

        Args:
            state: The ExecutionState to store
            conversation: The Conversation model instance
            user: The User model instance

        Returns:
            Created ExecutionStateRecord
        """
        record = cls(
            execution_id=state.execution_id,
            conversation=conversation,
            user=user,
            state_data=state.to_dict(),
            status=cls._map_status(cls, state.status),
            user_request=state.user_request,
        )
        record.save()
        return record

    @classmethod
    def get_active_for_conversation(cls, conversation_id: str) -> 'ExecutionStateRecord':
        """
        Get the active (non-completed) execution for a conversation.

        Args:
            conversation_id: The conversation ID

        Returns:
            ExecutionStateRecord or None
        """
        return cls.objects.filter(
            conversation_id=conversation_id,
            status__in=['planning', 'executing', 'awaiting_user']
        ).first()

    @classmethod
    def get_awaiting_user(cls, conversation_id: str) -> 'ExecutionStateRecord':
        """
        Get execution awaiting user response.

        Args:
            conversation_id: The conversation ID

        Returns:
            ExecutionStateRecord or None
        """
        return cls.objects.filter(
            conversation_id=conversation_id,
            status='awaiting_user'
        ).first()
