"""
Chat Service V4 - Main Entry Point

The ChatServiceV4 class orchestrates the multi-agent architecture:
1. Message intake and classification
2. Reference resolution
3. Execution engine coordination
4. Response generation

This is the primary interface for Django views to interact with V4.
"""

import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any, List
from datetime import datetime

from django.utils import timezone

from .intake import (
    IntakeClassifier, SimpleIntakeClassifier, RouterIntakeClassifier,
    QuickClassifier, IntakeResult, RouteType
)

# V4 Pipeline logging
V4_LOG_ENABLED = True

def v4_log(stage: str, message: str, data: dict = None):
    """Log V4 pipeline events with visual formatting"""
    if not V4_LOG_ENABLED:
        return

    print(f"\n{'='*80}")
    print(f"🔹 V4 {stage.upper()}")
    print(f"{'='*80}")
    print(f"📍 {message}")
    if data:
        for key, value in data.items():
            if isinstance(value, str) and len(value) > 200:
                value = value[:200] + "..."
            print(f"   • {key}: {value}")
    print(f"{'='*80}\n")
from .resolver import ReferenceResolver, ResolutionResult
from .context import ConversationManager, ConversationContext
from .engine import ExecutionEngine, EngineConfig, EngineResult
from .models import ConversationState
from .agents.registry import AgentRegistry

logger = logging.getLogger(__name__)


@dataclass
class ServiceResult:
    """Result from ChatServiceV4.process()"""
    success: bool
    response: str
    route_type: RouteType

    # Token tracking
    input_tokens: int = 0
    output_tokens: int = 0

    # Execution metadata
    execution_id: Optional[str] = None
    awaiting_user: bool = False
    steps_executed: int = 0

    # Classification metadata
    message_type: Optional[str] = None
    confidence: float = 0.0

    # Affected entities (for UI linking)
    affected_entities: Dict[str, List[int]] = None

    # Error details
    error: Optional[str] = None

    def __post_init__(self):
        if self.affected_entities is None:
            self.affected_entities = {}


@dataclass
class ServiceConfig:
    """Configuration for ChatServiceV4"""
    # Engine settings
    max_steps: int = 20
    max_retries: int = 3
    max_replan_attempts: int = 2
    enable_quick_planning: bool = True

    # Classification settings
    use_quick_classifier: bool = True
    classification_model: str = "gemini-flash"
    # NEW: Switch between classifiers
    # True = RouterIntakeClassifier (V2-style, combined classify + respond)
    # False = SimpleIntakeClassifier (classify only)
    use_router_classifier: bool = True

    # Context settings
    max_context_messages: int = 20
    enable_summarization: bool = True

    # Feature flags
    enable_confirmations: bool = True
    log_executions: bool = False


class ChatServiceV4:
    """
    Main service class for Chat V4 multi-agent architecture.

    Usage:
        service = ChatServiceV4(user, conversation)
        result = service.process("Create a task called Review proposal")

        # For resuming after user response
        result = service.resume(execution_id, "Yes, proceed")
    """

    def __init__(
        self,
        user,
        conversation,
        config: ServiceConfig = None
    ):
        """
        Initialize ChatServiceV4.

        Args:
            user: Django User instance
            conversation: Django Conversation instance
            config: Optional service configuration
        """
        self.user = user
        self.conversation = conversation
        self.config = config or ServiceConfig()

        # Get or create conversation state
        self.state = ConversationState.get_or_create_for_conversation(conversation)

        # Initialize components
        self._quick_classifier = QuickClassifier()
        self._full_classifier = None  # Lazy init
        self._resolver = ReferenceResolver()
        self._context_manager = ConversationManager(
            user_id=str(user.id),
            conversation_id=str(conversation.id)
        )

        # Register agents with engine
        self._agent_factories = self._build_agent_factories()

    def _build_agent_factories(self) -> Dict[str, callable]:
        """Build agent factory functions for the execution engine"""
        factories = {}
        for agent_type in AgentRegistry.list_agents():
            # Create a closure to capture agent_type
            def factory(at=agent_type):
                return AgentRegistry.get(at)
            factories[agent_type] = factory
        return factories

    def process(self, message: str) -> ServiceResult:
        """
        Process an incoming user message.

        Main entry point for handling chat messages. Routes to appropriate
        handler based on classification.

        Args:
            message: The user's message text

        Returns:
            ServiceResult with response and metadata
        """
        start_time = datetime.now()

        # Save user message to database
        user_msg = self._save_message(message, role='user')

        # Update conversation timestamp
        self.conversation.last_message_at = timezone.now()
        self.conversation.save(update_fields=['last_message_at'])

        # Increment state message count
        self.state.increment_message_count()

        try:
            v4_log("service", f"Processing message: '{message[:100]}...' " if len(message) > 100 else f"Processing message: '{message}'", {
                "user_id": str(self.user.id),
                "conversation_id": str(self.conversation.id),
                "classifier": "RouterIntakeClassifier" if self.config.use_router_classifier else "SimpleIntakeClassifier"
            })

            # Check for active execution (awaiting user response)
            if self.state.has_active_execution():
                v4_log("service", "Active execution found, resuming", {"execution_id": self.state.active_execution_id})
                return self._handle_resume(message)

            # Step 1: Classify the message
            classification = self._classify_message(message)
            logger.debug(f"Classification: {classification.route} ({classification.confidence:.2f})")

            v4_log("classification", f"Message classified", {
                "route": classification.route.value,
                "message_type": classification.message_type.value if classification.message_type else "N/A",
                "confidence": f"{classification.confidence:.2f}",
                "intent": classification.extracted_intent,
                "has_direct_response": bool(classification.direct_response),
                "has_clarify_question": bool(classification.clarify_question)
            })

            # Step 2: Route based on classification
            if classification.route == RouteType.DIRECT:
                v4_log("routing", "Routing to DIRECT handler (no execution needed)")
                result = self._handle_direct(message, classification)

            elif classification.route == RouteType.EXECUTE:
                v4_log("routing", "Routing to EXECUTE handler (will create plan and execute)")
                result = self._handle_execute(message, classification)

            elif classification.route == RouteType.RESUME:
                v4_log("routing", "Routing to RESUME handler")
                result = self._handle_resume(message)

            elif classification.route == RouteType.MODIFY:
                v4_log("routing", "Routing to MODIFY handler")
                result = self._handle_modify(message, classification)

            else:
                # Default to execute
                v4_log("routing", "No matching route, defaulting to EXECUTE")
                result = self._handle_execute(message, classification)

            # Save assistant response
            self._save_message(
                result.response,
                role='assistant',
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens
            )

            # Update conversation token totals
            self.conversation.total_input_tokens += result.input_tokens
            self.conversation.total_output_tokens += result.output_tokens
            self.conversation.save(update_fields=[
                'total_input_tokens', 'total_output_tokens'
            ])

            v4_log("response", f"Final response generated", {
                "success": result.success,
                "route": result.route_type.value,
                "steps_executed": result.steps_executed,
                "tokens": f"{result.input_tokens} in / {result.output_tokens} out",
                "response_preview": result.response[:150] + "..." if len(result.response) > 150 else result.response
            })

            return result

        except Exception as e:
            logger.error(f"Service error: {e}", exc_info=True)
            error_response = f"I encountered an error: {str(e)}"

            self._save_message(error_response, role='assistant', is_error=True)

            return ServiceResult(
                success=False,
                response=error_response,
                route_type=RouteType.DIRECT,
                error=str(e)
            )

    def resume(self, execution_id: str, user_response: str) -> ServiceResult:
        """
        Resume an execution that was awaiting user input.

        Args:
            execution_id: ID of the paused execution
            user_response: User's response to the question

        Returns:
            ServiceResult with response and metadata
        """
        # Save user message
        self._save_message(user_response, role='user')
        self.state.increment_message_count()

        # Create engine and resume
        engine = self._create_engine()
        engine_result = engine.resume(execution_id, user_response)

        result = self._engine_result_to_service_result(
            engine_result,
            route_type=RouteType.RESUME
        )

        # Update state after execution
        if not engine_result.awaiting_user:
            self.state.clear_active_execution()

        # Save assistant response
        self._save_message(
            result.response,
            role='assistant',
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens
        )

        return result

    def _classify_message(self, message: str) -> IntakeResult:
        """Classify incoming message using LLM"""
        model_name = getattr(self.conversation, 'model_name', None) or 'gemini-flash'

        # Initialize classifier with conversation's model if not already done
        if self._full_classifier is None:
            if self.config.use_router_classifier:
                # V2-style: combined classify + respond
                self._full_classifier = RouterIntakeClassifier(model_name=model_name)
            else:
                # Simple: classify only
                self._full_classifier = SimpleIntakeClassifier(model_name=model_name)

        # Get recent messages for RouterIntakeClassifier context
        recent_messages = None
        if self.config.use_router_classifier:
            recent_msgs = list(
                self.conversation.messages.order_by('-created_at')[:10]
            )
            recent_msgs.reverse()
            recent_messages = [
                {'role': m.role, 'content': m.content}
                for m in recent_msgs
            ]

        # Use appropriate classify method based on classifier type
        if self.config.use_router_classifier:
            return self._full_classifier.classify_sync(
                message=message,
                user=self.user,
                conversation_summary=self.state.summary or "",
                has_active_execution=self.state.has_active_execution(),
                mentioned_entities=self.state.mentioned_entities or {},
                recent_messages=recent_messages
            )
        else:
            return self._full_classifier.classify_sync(
                message=message,
                conversation_summary=self.state.summary or "",
                has_active_execution=self.state.has_active_execution(),
                mentioned_entities=self.state.mentioned_entities or {}
            )

    def _handle_direct(
        self,
        message: str,
        classification: IntakeResult
    ) -> ServiceResult:
        """
        Handle DIRECT route - answer without execution.

        For questions that can be answered from context/state.
        """
        # Check if RouterIntakeClassifier already provided a response
        if classification.direct_response:
            response = classification.direct_response
        elif classification.clarify_question:
            response = classification.clarify_question
        else:
            # Fallback: generate response using pattern matching
            context = self._build_context()
            response = self._generate_direct_response(message, context)

        return ServiceResult(
            success=True,
            response=response,
            route_type=classification.route,
            message_type=classification.message_type.value if classification.message_type else None,
            confidence=classification.confidence
        )

    def _handle_execute(
        self,
        message: str,
        classification: IntakeResult
    ) -> ServiceResult:
        """
        Handle EXECUTE route - run through execution engine.

        For task requests that need planning and agent execution.
        """
        # Step 1: Resolve references ("it", "that", etc.)
        resolution = self._resolve_references(message)
        resolved_message = resolution.resolved_message or message

        # Step 2: Build context
        context = self._build_context()

        # Step 3: Create and run engine
        engine = self._create_engine()

        # Extract resolved references as dict
        resolved_refs = {}
        for ref in resolution.references:
            if ref.entity_type not in resolved_refs:
                resolved_refs[ref.entity_type] = []
            resolved_refs[ref.entity_type].extend(ref.entity_ids)

        engine_result = engine.execute(
            user_request=resolved_message,
            conversation_summary=context.summary,
            resolved_references=resolved_refs
        )

        # Step 4: Update state
        if engine_result.awaiting_user:
            self.state.set_active_execution(engine_result.execution_id)
        elif engine_result.success:
            # Update state with execution results
            self.state.update_after_execution(
                execution_summary={
                    'execution_id': engine_result.execution_id,
                    'request': message,
                    'success': engine_result.success,
                    'steps': engine_result.steps_executed
                },
                created_entities={},  # TODO: Extract from engine result
                affected_entities={}  # TODO: Extract from engine result
            )

        return self._engine_result_to_service_result(
            engine_result,
            route_type=RouteType.EXECUTE,
            classification=classification
        )

    def _handle_resume(self, message: str) -> ServiceResult:
        """
        Handle RESUME route - continue paused execution.
        """
        execution_id = self.state.active_execution_id
        if not execution_id:
            return ServiceResult(
                success=False,
                response="I don't have a pending question. How can I help?",
                route_type=RouteType.RESUME,
                error="No active execution"
            )

        return self.resume(execution_id, message)

    def _handle_modify(
        self,
        message: str,
        classification: IntakeResult
    ) -> ServiceResult:
        """
        Handle MODIFY route - adjust previous execution.

        For corrections like "actually, make it high priority".
        """
        # For now, treat modifications as new executions
        # TODO: Implement smarter modification handling
        return self._handle_execute(message, classification)

    def _resolve_references(self, message: str) -> ResolutionResult:
        """Resolve pronoun references in message"""
        return self._resolver.resolve(
            message=message,
            last_created=self.state.last_created_entities,
            last_affected=self.state.last_affected_entities,
            mentioned=self.state.mentioned_entities
        )

    def _build_context(self) -> ConversationContext:
        """Build conversation context from state and history"""
        # Get recent messages for context
        recent_messages = list(
            self.conversation.messages.order_by('-created_at')
            [:self.config.max_context_messages]
        )
        recent_messages.reverse()

        return ConversationContext(
            conversation_id=str(self.conversation.id),
            user_id=str(self.user.id),
            summary=self.state.summary or "",
            topics=self.state.topics or [],
            message_count=self.state.message_count,
            mentioned_entities=self.state.mentioned_entities or {},
            last_created_entities=self.state.last_created_entities or {},
            last_affected_entities=self.state.last_affected_entities or {},
            has_active_execution=self.state.has_active_execution(),
            active_execution_id=self.state.active_execution_id,
            last_execution_summary=self.state.last_execution_summary,
            recent_messages=[
                {'role': m.role, 'content': m.content}
                for m in recent_messages
            ]
        )

    def _create_engine(self) -> ExecutionEngine:
        """Create a new execution engine instance"""
        # Get model from conversation settings
        model_name = getattr(self.conversation, 'model_name', None) or 'gemini-flash'

        engine_config = EngineConfig(
            max_steps=self.config.max_steps,
            max_retries=self.config.max_retries,
            max_replan_attempts=self.config.max_replan_attempts,
            enable_quick_planning=self.config.enable_quick_planning,
            enable_confirmations=self.config.enable_confirmations,
            log_executions=self.config.log_executions,
            model_name=model_name  # Pass conversation's selected model
        )

        return ExecutionEngine(
            user_id=str(self.user.id),
            conversation_id=str(self.conversation.id),
            config=engine_config,
            agent_registry=self._agent_factories,
            conversation=self.conversation,
            user=self.user
        )

    def _engine_result_to_service_result(
        self,
        engine_result: EngineResult,
        route_type: RouteType,
        classification: IntakeResult = None
    ) -> ServiceResult:
        """Convert EngineResult to ServiceResult"""
        return ServiceResult(
            success=engine_result.success,
            response=engine_result.response,
            route_type=route_type,
            input_tokens=engine_result.input_tokens,
            output_tokens=engine_result.output_tokens,
            execution_id=engine_result.execution_id,
            awaiting_user=engine_result.awaiting_user,
            steps_executed=engine_result.steps_executed,
            message_type=classification.message_type.value if classification and classification.message_type else None,
            confidence=classification.confidence if classification else 0.0,
            error=engine_result.error
        )

    def _generate_direct_response(
        self,
        message: str,
        context: ConversationContext
    ) -> str:
        """Generate a simple direct response"""
        # Simple pattern matching for common questions
        message_lower = message.lower().strip()

        # Greeting responses
        if any(g in message_lower for g in ['hi', 'hello', 'hey', 'good morning', 'good afternoon']):
            return "Hello! I'm ready to help you manage your notes, tasks, and projects. What would you like to do?"

        # Help requests
        if message_lower in ['help', 'what can you do', 'what can you do?']:
            return (
                "I can help you with:\n"
                "• Creating and managing tasks and notes\n"
                "• Organizing projects and areas\n"
                "• Searching your content\n"
                "• Managing tags and inbox\n"
                "• Calendar and deadline tracking\n\n"
                "Just tell me what you'd like to do!"
            )

        # Thank you responses
        if any(t in message_lower for t in ['thank', 'thanks', 'great', 'perfect', 'awesome']):
            return "You're welcome! Let me know if you need anything else."

        # Default response
        return "I'm not sure how to help with that. Could you tell me more about what you'd like to do?"

    def _save_message(
        self,
        content: str,
        role: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        is_error: bool = False
    ):
        """Save a message to the conversation"""
        from chat.models import Message

        return Message.objects.create(
            conversation=self.conversation,
            role=role,
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            is_error=is_error
        )


def process_message(user, conversation, message: str) -> ServiceResult:
    """
    Convenience function to process a chat message.

    Usage:
        result = process_message(request.user, conversation, "Create a task")
        if result.success:
            return JsonResponse({'response': result.response})
    """
    service = ChatServiceV4(user, conversation)
    return service.process(message)
