"""
Chat V4 Router

Bridge between Django views and V4 service.
Provides a compatible interface with V2 router while using V4 architecture.
"""

import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any, List

from .service import ChatServiceV4, ServiceResult, ServiceConfig
from .intake import RouteType

logger = logging.getLogger(__name__)


@dataclass
class V4RouterResult:
    """
    Result from V4 router, compatible with V2 RouterResult interface.
    """
    route_type: RouteType
    response: str
    success: bool = True

    # Token tracking
    input_tokens: int = 0
    output_tokens: int = 0

    # Execution details
    execution_id: Optional[str] = None
    awaiting_user: bool = False
    steps_executed: int = 0

    # Classification details
    message_type: Optional[str] = None
    confidence: float = 0.0

    # Entity links for UI
    affected_entities: Dict[str, List[int]] = None

    # Error handling
    error: Optional[str] = None

    def __post_init__(self):
        if self.affected_entities is None:
            self.affected_entities = {}

    @property
    def is_direct(self) -> bool:
        """Check if this was a DIRECT route"""
        return self.route_type == RouteType.DIRECT

    @property
    def is_agentic(self) -> bool:
        """Check if this was an EXECUTE route (agentic)"""
        return self.route_type == RouteType.EXECUTE

    @property
    def needs_user_input(self) -> bool:
        """Check if awaiting user response"""
        return self.awaiting_user


class V4Router:
    """
    V4 Router - routes messages through the multi-agent architecture.

    Provides a compatible interface for Django views while using
    the full V4 service underneath.

    Usage:
        router = V4Router(user, conversation)
        result = router.route("Create a task called Review docs")

        if result.success:
            # Use result.response
            pass
    """

    def __init__(
        self,
        user,
        conversation,
        config: ServiceConfig = None
    ):
        """
        Initialize V4 router.

        Args:
            user: Django User instance
            conversation: Django Conversation instance
            config: Optional service configuration
        """
        self.user = user
        self.conversation = conversation
        self.service = ChatServiceV4(user, conversation, config)

    def route(self, message: str) -> V4RouterResult:
        """
        Route and process a user message.

        This is the main entry point that handles the full flow:
        1. Saves user message
        2. Classifies and routes
        3. Executes if needed
        4. Returns response

        Args:
            message: User's message text

        Returns:
            V4RouterResult with response and metadata
        """
        # Process through service
        service_result = self.service.process(message)

        # Convert to router result
        return V4RouterResult(
            route_type=service_result.route_type,
            response=service_result.response,
            success=service_result.success,
            input_tokens=service_result.input_tokens,
            output_tokens=service_result.output_tokens,
            execution_id=service_result.execution_id,
            awaiting_user=service_result.awaiting_user,
            steps_executed=service_result.steps_executed,
            message_type=service_result.message_type,
            confidence=service_result.confidence,
            affected_entities=service_result.affected_entities,
            error=service_result.error
        )

    def resume(self, execution_id: str, user_response: str) -> V4RouterResult:
        """
        Resume a paused execution.

        Args:
            execution_id: ID of paused execution
            user_response: User's response

        Returns:
            V4RouterResult with response
        """
        service_result = self.service.resume(execution_id, user_response)

        return V4RouterResult(
            route_type=service_result.route_type,
            response=service_result.response,
            success=service_result.success,
            input_tokens=service_result.input_tokens,
            output_tokens=service_result.output_tokens,
            execution_id=service_result.execution_id,
            awaiting_user=service_result.awaiting_user,
            steps_executed=service_result.steps_executed,
            error=service_result.error
        )

    def has_pending_execution(self) -> bool:
        """Check if there's a pending execution awaiting user input"""
        return self.service.state.has_active_execution()

    def get_pending_execution_id(self) -> Optional[str]:
        """Get the pending execution ID if any"""
        return self.service.state.active_execution_id

    def cancel_pending(self) -> bool:
        """Cancel any pending execution"""
        if self.service.state.has_active_execution():
            self.service.state.clear_active_execution()
            return True
        return False


def route_v4_message(user, conversation, message: str) -> V4RouterResult:
    """
    Convenience function to route a message through V4.

    Usage:
        result = route_v4_message(request.user, conversation, "Create a task")
        return JsonResponse({
            'response': result.response,
            'success': result.success
        })
    """
    router = V4Router(user, conversation)
    return router.route(message)
