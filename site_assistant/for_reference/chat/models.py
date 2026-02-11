from django.db import models
from django.conf import settings
from django.utils import timezone

from Core.models import BaseModel


class Conversation(BaseModel):
    """
    Represents a chat conversation/thread.
    Users can have multiple conversations for different purposes.
    """
    CONTEXT_TYPES = [
        ('general', 'General'),
        ('project', 'Project'),
        ('area', 'Area'),
    ]

    CHAT_VERSIONS = [
        ('v1', 'V1 - Monolithic'),
        ('v2', 'V2 - DIRECT/AGENTIC'),
        ('v3', 'V3 - Agentic Loop'),
        ('v4', 'V4 - Multi-Agent'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='chat_conversations'
    )

    title = models.CharField(
        max_length=200,
        blank=True,
        help_text="Auto-generated or user-set conversation title"
    )

    # Optional scoping to project/area for focused context
    context_type = models.CharField(
        max_length=20,
        choices=CONTEXT_TYPES,
        default='general'
    )
    context_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="ID of the linked Project or Area"
    )

    is_archived = models.BooleanField(default=False)

    # V2 Architecture flag (legacy, kept for backward compatibility)
    use_v2 = models.BooleanField(
        default=True,
        help_text="Use V2 chat architecture (DIRECT/AGENTIC/CLARIFY routing)"
    )
    v2_enabled_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When V2 was enabled for this conversation"
    )

    # Chat architecture version (v1, v2, v3)
    chat_version = models.CharField(
        max_length=10,
        choices=CHAT_VERSIONS,
        default='v1',
        help_text="Chat architecture version to use"
    )

    # Model configuration
    model_name = models.CharField(
        max_length=50,
        default='gemini-flash',
        help_text="LLM model used for this conversation"
    )

    # Token tracking for this conversation
    total_input_tokens = models.PositiveIntegerField(default=0)
    total_output_tokens = models.PositiveIntegerField(default=0)

    # Last activity timestamp for sorting
    last_message_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'chat_conversations'
        ordering = ['-last_message_at', '-created_at']
        indexes = [
            models.Index(fields=['user', 'is_archived']),
            models.Index(fields=['user', 'last_message_at']),
            models.Index(fields=['context_type', 'context_id']),
        ]

    def __str__(self):
        return self.title or f"Conversation {self.id}"

    def get_context_object(self):
        """Get the linked Project or Area object"""
        if self.context_type == 'project' and self.context_id:
            from para.models import Project
            return Project.objects.filter(id=self.context_id, user=self.user).first()
        elif self.context_type == 'area' and self.context_id:
            from para.models import Area
            return Area.objects.filter(id=self.context_id, user=self.user).first()
        return None

    def get_message_count(self):
        """Get total message count"""
        return self.messages.count()

    def generate_title(self):
        """Generate title from first user message"""
        first_message = self.messages.filter(role='user').first()
        if first_message:
            content = first_message.content[:50]
            if len(first_message.content) > 50:
                content += "..."
            self.title = content
            self.save(update_fields=['title'])

    def get_total_tokens(self):
        """Get total tokens used in this conversation"""
        return self.total_input_tokens + self.total_output_tokens

    def enable_v2(self):
        """Enable V2 architecture for this conversation."""
        if not self.use_v2:
            self.use_v2 = True
            self.v2_enabled_at = timezone.now()
            self.chat_version = 'v2'
            self.save(update_fields=['use_v2', 'v2_enabled_at', 'chat_version'])

    def disable_v2(self):
        """Disable V2 architecture (revert to V1)."""
        if self.use_v2:
            self.use_v2 = False
            self.chat_version = 'v1'
            self.save(update_fields=['use_v2', 'chat_version'])

    def set_version(self, version: str):
        """Set the chat architecture version (v1, v2, v3, or v4)."""
        if version not in ['v1', 'v2', 'v3', 'v4']:
            raise ValueError(f"Invalid version: {version}")

        self.chat_version = version
        # Keep use_v2 in sync for backward compatibility
        self.use_v2 = version in ['v2', 'v3', 'v4']
        if version == 'v2' and not self.v2_enabled_at:
            self.v2_enabled_at = timezone.now()

        self.save(update_fields=['chat_version', 'use_v2', 'v2_enabled_at'])

    def enable_v4(self):
        """Enable V4 multi-agent architecture for this conversation."""
        self.set_version('v4')

    def is_v4(self) -> bool:
        """Check if this conversation uses V4 architecture."""
        return self.chat_version == 'v4'


class Message(BaseModel):
    """
    Individual message in a conversation.
    Stores both user messages and assistant responses.
    """
    ROLE_CHOICES = [
        ('user', 'User'),
        ('assistant', 'Assistant'),
        ('system', 'System'),
    ]

    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name='messages'
    )

    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    content = models.TextField()

    # Token tracking per message
    input_tokens = models.PositiveIntegerField(
        default=0,
        help_text="Tokens used for this message's prompt"
    )
    output_tokens = models.PositiveIntegerField(
        default=0,
        help_text="Tokens in the response (for assistant messages)"
    )

    # Processing metadata
    model_used = models.CharField(max_length=50, blank=True)
    processing_time_ms = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Time taken to generate response"
    )

    # VEL execution tracking
    has_vel_commands = models.BooleanField(default=False)
    vel_session_id = models.CharField(
        max_length=64,
        blank=True,
        help_text="VEL session ID for audit linking"
    )

    # Error tracking
    is_error = models.BooleanField(default=False)
    error_message = models.TextField(blank=True)

    class Meta:
        db_table = 'chat_messages'
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['conversation', 'created_at']),
            models.Index(fields=['role']),
        ]

    def __str__(self):
        preview = self.content[:50] + "..." if len(self.content) > 50 else self.content
        return f"{self.role}: {preview}"


class ChatVELExecution(BaseModel):
    """
    Links chat messages to VEL executions for tracking
    which actions were performed during a conversation.
    """
    STATUS_CHOICES = [
        ('success', 'Success'),
        ('error', 'Error'),
        ('denied', 'Denied'),
        ('timeout', 'Timeout'),
        ('confirmation_required', 'Confirmation Required'),
        ('confirmed', 'Confirmed'),
        ('cancelled', 'Cancelled'),
    ]

    message = models.ForeignKey(
        Message,
        on_delete=models.CASCADE,
        related_name='vel_executions'
    )

    # VEL audit log reference
    audit_id = models.CharField(max_length=64)
    action = models.CharField(max_length=50)

    # Execution result
    status = models.CharField(max_length=25, choices=STATUS_CHOICES)
    result_summary = models.TextField(blank=True)
    result_data = models.JSONField(
        default=dict,
        blank=True,
        help_text="Full result data including created item IDs"
    )

    # Confirmation tracking
    requires_confirmation = models.BooleanField(default=False)
    confirmation_token = models.CharField(max_length=64, blank=True)
    confirmed = models.BooleanField(default=False)
    confirmed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'chat_vel_executions'
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['message', 'action']),
            models.Index(fields=['confirmation_token']),
        ]

    def __str__(self):
        return f"{self.action} - {self.status}"

    def get_formatted_action(self):
        """Return a nicely formatted action name for display."""
        # Map action prefixes to display names
        action_map = {
            'search': 'Search',
            'create': 'Created',
            'update': 'Updated',
            'delete': 'Deleted',
            'archive': 'Archived',
            'move': 'Moved',
            'complete': 'Completed',
            'start': 'Started',
            'uncomplete': 'Reopened',
            'get': 'Retrieved',
            'add_tags': 'Tagged',
            'remove_tags': 'Untagged',
        }

        # Extract the action part (before underscore) from action names like "search_note"
        action_parts = self.action.split('_', 1) if self.action else ['unknown']
        action_verb = action_parts[0]

        # Get formatted action name
        formatted = action_map.get(action_verb, action_verb.title())

        # Add resource type if present (e.g., "note", "task", "project")
        if len(action_parts) > 1:
            resource = action_parts[1].title()
            return f"{formatted} {resource}"

        return formatted

    def confirm(self):
        """Mark this execution as confirmed"""
        self.confirmed = True
        self.confirmed_at = timezone.now()
        self.status = 'confirmed'
        self.save(update_fields=['confirmed', 'confirmed_at', 'status'])

    def cancel(self):
        """Mark this execution as cancelled"""
        self.status = 'cancelled'
        self.save(update_fields=['status'])

    def get_link_data(self):
        """Return link info for this execution's created/affected item."""
        if self.status != 'success' or not self.result_data:
            return None

        # Map action types to their URL patterns and labels
        action_links = {
            'create_note': ('notes:note_detail', 'id', 'Note'),
            'create_task': ('tasks:task_detail', 'id', 'Task'),
            'create_project': ('para:project_detail', 'id', 'Project'),
            'create_area': ('para:area_detail', 'id', 'Area'),
            'get_note': ('notes:note_detail', 'id', 'Note'),
            'get_task': ('tasks:task_detail', 'id', 'Task'),
            'update_note': ('notes:note_detail', 'id', 'Note'),
            'update_task': ('tasks:task_detail', 'id', 'Task'),
            'move_note': ('notes:note_detail', 'id', 'Note'),
            'move_task': ('tasks:task_detail', 'id', 'Task'),
            'archive_note': ('notes:note_detail', 'id', 'Note'),
            'get_project': ('para:project_detail', 'id', 'Project'),
            'update_project': ('para:project_detail', 'id', 'Project'),
            'get_area': ('para:area_detail', 'id', 'Area'),
            'update_area': ('para:area_detail', 'id', 'Area'),
            'complete_task': ('tasks:task_detail', 'id', 'Task'),
            'start_task': ('tasks:task_detail', 'id', 'Task'),
            'uncomplete_task': ('tasks:task_detail', 'id', 'Task'),
        }

        if self.action in action_links:
            url_name, id_key, label = action_links[self.action]
            item_id = self.result_data.get(id_key)
            title = self.result_data.get('title', self.result_data.get('name', f'{label} #{item_id}'))
            if item_id:
                return {
                    'url_name': url_name,
                    'item_id': item_id,
                    'label': label,
                    'title': title,
                    'action': self.action,
                }
        return None


# Import V2 models to register them with Django
from chat.v2.models import AgentMemory, PlanStep

# Import V3 models to register them with Django
from chat.v3.models import V3Plan, V3PlanStep, V3Memory

# Import V4 models to register them with Django
from chat.v4.models import ConversationState as V4ConversationState
