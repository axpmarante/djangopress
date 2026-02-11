"""
Chat V3 Service

Main orchestrator for the V3 chat architecture.

Responsibilities:
- Route messages (conversational vs agentic)
- Manage conversation state
- Coordinate the agent loop
- Save messages and track tokens
"""

import logging
from dataclasses import dataclass
from typing import Optional
from datetime import datetime

from django.utils import timezone

from .config import RouteType
from .intake import classify_message
from .agent import AgentLoop
from .prompts import build_conversational_prompt
from .types import AgentResult

logger = logging.getLogger(__name__)


@dataclass
class ChatResponse:
    """Response from the chat service."""
    success: bool
    message: str
    route_type: RouteType
    iterations: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    error: Optional[str] = None


class ChatServiceV3:
    """
    Main chat service for V3 architecture.

    Usage:
        service = ChatServiceV3(conversation)
        response = service.send_message("What's in my inbox?")
    """

    def __init__(self, conversation):
        """
        Initialize the chat service.

        Args:
            conversation: Conversation model instance
        """
        self.conversation = conversation
        self.user = conversation.user
        self._llm_client = None

    def send_message(self, content: str) -> ChatResponse:
        """
        Process a user message and return a response.

        Args:
            content: The user's message

        Returns:
            ChatResponse with the assistant's response
        """
        logger.info(f"[V3] Processing message: {content[:50]}...")

        # Save user message
        user_message = self._save_user_message(content)

        try:
            # Classify the message
            intake_result = classify_message(
                content,
                has_pending_action=self._has_pending_action()
            )
            logger.info(f"[V3] Classified as {intake_result.route_type.value} (confidence: {intake_result.confidence})")

            # Route to appropriate handler
            if intake_result.route_type == RouteType.CONVERSATIONAL:
                response = self._handle_conversational(content)
            else:
                response = self._handle_agentic(content)

            # Save assistant message
            self._save_assistant_message(
                response.message,
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens
            )

            return response

        except Exception as e:
            logger.error(f"[V3] Error processing message: {e}")
            error_response = ChatResponse(
                success=False,
                message="I encountered an error processing your request. Please try again.",
                route_type=RouteType.AGENTIC,
                error=str(e)
            )
            self._save_assistant_message(error_response.message)
            return error_response

    def _handle_conversational(self, content: str) -> ChatResponse:
        """
        Handle a conversational message (no tools needed).

        Uses a simple LLM call without the agent loop.
        """
        logger.info("[V3] Handling as conversational")

        # Build prompt
        system_prompt = build_conversational_prompt(self.user)

        # Get recent history for context
        history = self._get_conversation_history(limit=5)

        messages = [
            {"role": "system", "content": system_prompt}
        ]

        # Add history
        for msg in history:
            messages.append({
                "role": msg.role,
                "content": msg.content[:500]  # Truncate
            })

        # Add current message
        messages.append({"role": "user", "content": content})

        # Call LLM
        client = self._get_llm_client()
        result = client.chat(messages)

        return ChatResponse(
            success=True,
            message=result['text'],
            route_type=RouteType.CONVERSATIONAL,
            iterations=0,
            input_tokens=result.get('input_tokens', 0),
            output_tokens=result.get('output_tokens', 0)
        )

    def _handle_agentic(self, content: str) -> ChatResponse:
        """
        Handle an agentic message using the agent loop.

        The agent loop will:
        1. Build context
        2. Call LLM
        3. Execute tools
        4. Iterate until response
        """
        logger.info("[V3] Handling as agentic")

        # Create and run agent loop
        agent = AgentLoop(
            user=self.user,
            conversation=self.conversation,
            llm_client=self._get_llm_client()
        )

        result = agent.run(content)

        return ChatResponse(
            success=result.success,
            message=result.response,
            route_type=RouteType.AGENTIC,
            iterations=len(result.iterations),
            input_tokens=result.total_input_tokens,
            output_tokens=result.total_output_tokens,
            error=result.error
        )

    def _get_llm_client(self):
        """Get or create LLM client."""
        if self._llm_client is None:
            from .llm import get_llm_client
            self._llm_client = get_llm_client(self.conversation)
        return self._llm_client

    def _has_pending_action(self) -> bool:
        """
        Check if there's a pending action from previous messages.

        This is used to determine if affirmations like "yes" should
        be treated as continuing a pending action.
        """
        # Check last assistant message for pending action indicators
        last_assistant = self.conversation.messages.filter(
            role='assistant'
        ).order_by('-created_at').first()

        if not last_assistant:
            return False

        # Look for question patterns
        pending_patterns = [
            "would you like",
            "should i",
            "do you want",
            "shall i",
            "ready to",
            "proceed with",
            "confirm",
        ]

        content_lower = last_assistant.content.lower()
        return any(pattern in content_lower for pattern in pending_patterns)

    def _get_conversation_history(self, limit: int = 10):
        """Get recent conversation messages."""
        return list(
            self.conversation.messages
            .order_by('-created_at')[:limit]
        )[::-1]  # Reverse to chronological order

    def _save_user_message(self, content: str):
        """Save a user message to the conversation."""
        from chat.models import Message

        return Message.objects.create(
            conversation=self.conversation,
            role='user',
            content=content,
            created_at=timezone.now()
        )

    def _save_assistant_message(
        self,
        content: str,
        input_tokens: int = 0,
        output_tokens: int = 0
    ):
        """Save an assistant message to the conversation."""
        from chat.models import Message

        message = Message.objects.create(
            conversation=self.conversation,
            role='assistant',
            content=content,
            created_at=timezone.now(),
            input_tokens=input_tokens,
            output_tokens=output_tokens
        )

        # Update conversation totals
        self.conversation.total_input_tokens += input_tokens
        self.conversation.total_output_tokens += output_tokens
        self.conversation.save(update_fields=[
            'total_input_tokens',
            'total_output_tokens',
            'updated_at'
        ])

        return message


def get_chat_service(conversation) -> ChatServiceV3:
    """
    Factory function to get the appropriate chat service.

    Currently always returns V3, but can be extended for
    A/B testing or gradual rollout.
    """
    return ChatServiceV3(conversation)
