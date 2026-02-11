"""
Conversation Context for Chat V4

Provides context management for multi-message conversations:
- ConversationContext: Data class with all context for a message
- ContextBuilder: Builds context from database state
- ContextCompressor: Compresses conversation history into summaries
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime

from .resolver import ReferenceResolver, ResolutionResult

logger = logging.getLogger(__name__)


@dataclass
class ConversationContext:
    """
    Context for processing a user message.

    Contains all information needed to understand and process
    a message in the context of an ongoing conversation.
    """

    # Conversation identity
    conversation_id: str
    user_id: str

    # Conversation state
    summary: str
    topics: List[str]
    message_count: int

    # Entity tracking
    mentioned_entities: Dict[str, List[int]]
    last_created_entities: Dict[str, int]
    last_affected_entities: Dict[str, List[int]]

    # Execution state
    has_active_execution: bool
    active_execution_id: Optional[str]
    last_execution_summary: Optional[Dict[str, Any]]

    # Recent messages (for reference)
    recent_messages: List[Dict[str, str]] = field(default_factory=list)

    def get_summary_for_agent(self) -> str:
        """Get conversation summary formatted for agent prompts"""
        parts = []

        if self.summary:
            parts.append(f"Conversation summary: {self.summary}")

        if self.topics:
            parts.append(f"Topics discussed: {', '.join(self.topics)}")

        if self.last_execution_summary:
            last = self.last_execution_summary
            parts.append(
                f"Last action: {last.get('request', 'unknown')} -> {last.get('outcome', 'unknown')}"
            )

        if self.mentioned_entities:
            entities = []
            for etype, ids in self.mentioned_entities.items():
                if ids:
                    entities.append(f"{etype}s: {ids[-5:]}")  # Last 5
            if entities:
                parts.append(f"Recently mentioned: {', '.join(entities)}")

        return "\n".join(parts) if parts else "No prior context"

    def resolve_references(self, message: str) -> ResolutionResult:
        """Resolve references in a message using this context"""
        return ReferenceResolver.resolve(
            message=message,
            last_created=self.last_created_entities,
            last_affected=self.last_affected_entities,
            mentioned=self.mentioned_entities
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict"""
        return {
            'conversation_id': self.conversation_id,
            'user_id': self.user_id,
            'summary': self.summary,
            'topics': self.topics,
            'message_count': self.message_count,
            'mentioned_entities': self.mentioned_entities,
            'last_created_entities': self.last_created_entities,
            'last_affected_entities': self.last_affected_entities,
            'has_active_execution': self.has_active_execution,
            'active_execution_id': self.active_execution_id,
            'last_execution_summary': self.last_execution_summary,
            'recent_messages': self.recent_messages
        }


class ContextBuilder:
    """
    Builds ConversationContext from database state.
    """

    @classmethod
    def build(
        cls,
        conversation_id: str,
        user_id: str,
        include_messages: bool = True,
        message_limit: int = 5
    ) -> ConversationContext:
        """
        Build context for a conversation.

        Args:
            conversation_id: ID of the conversation
            user_id: ID of the user
            include_messages: Whether to include recent messages
            message_limit: Max recent messages to include

        Returns:
            ConversationContext with all available context
        """
        from chat.models import Conversation, Message
        from .models import ConversationState

        try:
            conversation = Conversation.objects.get(
                id=conversation_id,
                user_id=user_id
            )
        except Conversation.DoesNotExist:
            # Return empty context for new conversations
            return cls._empty_context(conversation_id, user_id)

        # Get or create V4 state
        state = ConversationState.get_or_create_for_conversation(conversation)

        # Build recent messages if requested
        recent_messages = []
        if include_messages:
            messages = Message.objects.filter(
                conversation=conversation
            ).order_by('-created_at')[:message_limit]

            recent_messages = [
                {
                    'role': msg.role,
                    'content': msg.content[:500]  # Truncate long messages
                }
                for msg in reversed(messages)
            ]

        return ConversationContext(
            conversation_id=str(conversation_id),
            user_id=str(user_id),
            summary=state.summary,
            topics=state.topics or [],
            message_count=state.message_count,
            mentioned_entities=state.mentioned_entities or {},
            last_created_entities=state.last_created_entities or {},
            last_affected_entities=state.last_affected_entities or {},
            has_active_execution=state.has_active_execution(),
            active_execution_id=state.active_execution_id,
            last_execution_summary=state.last_execution_summary,
            recent_messages=recent_messages
        )

    @classmethod
    def _empty_context(cls, conversation_id: str, user_id: str) -> ConversationContext:
        """Create empty context for new conversations"""
        return ConversationContext(
            conversation_id=conversation_id,
            user_id=user_id,
            summary="",
            topics=[],
            message_count=0,
            mentioned_entities={},
            last_created_entities={},
            last_affected_entities={},
            has_active_execution=False,
            active_execution_id=None,
            last_execution_summary=None,
            recent_messages=[]
        )

    @classmethod
    def build_minimal(cls, conversation_id: str, user_id: str) -> ConversationContext:
        """Build minimal context (no messages, faster)"""
        return cls.build(
            conversation_id=conversation_id,
            user_id=user_id,
            include_messages=False
        )


class ContextCompressor:
    """
    Compresses conversation history into summaries.

    Used to maintain context without keeping full message history.
    """

    # Compress after this many messages
    COMPRESSION_THRESHOLD = 10

    # Target summary length
    TARGET_SUMMARY_LENGTH = 500

    @classmethod
    def should_compress(cls, message_count: int, current_summary: str) -> bool:
        """Check if compression is needed"""
        # Compress every THRESHOLD messages or if summary is getting long
        return (
            message_count > 0 and
            message_count % cls.COMPRESSION_THRESHOLD == 0
        ) or len(current_summary) > cls.TARGET_SUMMARY_LENGTH * 2

    @classmethod
    def compress(
        cls,
        current_summary: str,
        new_messages: List[Dict[str, str]],
        execution_results: List[Dict[str, Any]] = None
    ) -> str:
        """
        Compress messages into updated summary.

        For now, uses rule-based compression. Can be upgraded to LLM-based.

        Args:
            current_summary: Existing conversation summary
            new_messages: Recent messages to incorporate
            execution_results: Recent execution results

        Returns:
            Updated summary string
        """
        parts = []

        # Keep core of existing summary
        if current_summary:
            # Truncate if too long
            if len(current_summary) > cls.TARGET_SUMMARY_LENGTH:
                parts.append(current_summary[:cls.TARGET_SUMMARY_LENGTH] + "...")
            else:
                parts.append(current_summary)

        # Summarize new messages
        user_requests = []
        for msg in new_messages:
            if msg.get('role') == 'user':
                content = msg.get('content', '')[:100]
                user_requests.append(content)

        if user_requests:
            parts.append(f"Recent requests: {'; '.join(user_requests[-3:])}")

        # Summarize execution results
        if execution_results:
            actions = []
            for result in execution_results[-3:]:
                action = result.get('action', 'unknown')
                outcome = result.get('outcome', 'completed')
                actions.append(f"{action}:{outcome}")

            if actions:
                parts.append(f"Recent actions: {', '.join(actions)}")

        # Combine and truncate
        combined = " | ".join(parts)
        if len(combined) > cls.TARGET_SUMMARY_LENGTH * 1.5:
            combined = combined[:int(cls.TARGET_SUMMARY_LENGTH * 1.5)] + "..."

        return combined

    @classmethod
    def extract_topics(cls, messages: List[Dict[str, str]]) -> List[str]:
        """
        Extract topics from messages.

        Args:
            messages: List of messages

        Returns:
            List of topic strings
        """
        topics = set()

        topic_keywords = {
            'inbox': ['inbox', 'capture', 'quick note'],
            'tasks': ['task', 'todo', 'complete', 'deadline', 'due'],
            'notes': ['note', 'summarize', 'distill', 'highlight'],
            'projects': ['project', 'milestone', 'goal'],
            'areas': ['area', 'responsibility', 'domain'],
            'search': ['search', 'find', 'look for', 'where'],
            'organize': ['organize', 'move', 'archive', 'categorize'],
        }

        for msg in messages:
            content = msg.get('content', '').lower()
            for topic, keywords in topic_keywords.items():
                if any(kw in content for kw in keywords):
                    topics.add(topic)

        return list(topics)


class ConversationManager:
    """
    High-level manager for conversation context operations.
    """

    def __init__(self, conversation_id: str, user_id: str):
        """Initialize manager for a conversation"""
        self.conversation_id = conversation_id
        self.user_id = user_id
        self._context: Optional[ConversationContext] = None
        self._state = None

    def get_context(self, refresh: bool = False) -> ConversationContext:
        """Get conversation context, with optional refresh"""
        if self._context is None or refresh:
            self._context = ContextBuilder.build(
                self.conversation_id,
                self.user_id
            )
        return self._context

    def get_state(self):
        """Get the ConversationState model instance"""
        if self._state is None:
            from chat.models import Conversation
            from .models import ConversationState

            try:
                conversation = Conversation.objects.get(
                    id=self.conversation_id,
                    user_id=self.user_id
                )
                self._state = ConversationState.get_or_create_for_conversation(
                    conversation
                )
            except Conversation.DoesNotExist:
                return None

        return self._state

    def update_after_message(self, message: str, role: str = 'user'):
        """Update state after a new message"""
        state = self.get_state()
        if state:
            state.increment_message_count()

            # Check if compression needed
            if ContextCompressor.should_compress(
                state.message_count,
                state.summary
            ):
                # Get recent messages for compression
                context = self.get_context(refresh=True)
                new_summary = ContextCompressor.compress(
                    state.summary,
                    context.recent_messages
                )
                new_topics = ContextCompressor.extract_topics(
                    context.recent_messages
                )
                state.update_summary(new_summary, new_topics)

            self._context = None  # Force refresh

    def update_after_execution(
        self,
        execution_summary: Dict[str, Any],
        created_entities: Dict[str, int],
        affected_entities: Dict[str, List[int]]
    ):
        """Update state after execution completes"""
        state = self.get_state()
        if state:
            state.update_after_execution(
                execution_summary,
                created_entities,
                affected_entities
            )
            self._context = None  # Force refresh

    def set_active_execution(self, execution_id: str):
        """Set an active execution awaiting user response"""
        state = self.get_state()
        if state:
            state.set_active_execution(execution_id)
            self._context = None

    def clear_active_execution(self):
        """Clear the active execution"""
        state = self.get_state()
        if state:
            state.clear_active_execution()
            self._context = None

    def resolve_message_references(self, message: str) -> ResolutionResult:
        """Resolve references in a message"""
        context = self.get_context()
        return context.resolve_references(message)
