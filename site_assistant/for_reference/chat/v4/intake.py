"""
Intake Classification for Chat V4

Classifies incoming messages and determines routing:
- task_request: New task to execute
- user_response: Response to awaiting_user prompt
- follow_up: Follow-up on previous execution
- question: General question (not a task)
- correction: Correction to previous action
- feedback: Feedback on results
"""

import re
import logging
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from enum import Enum

from .llm import LLMClient

logger = logging.getLogger(__name__)


class MessageType(str, Enum):
    """Types of user messages"""
    TASK_REQUEST = "task_request"
    USER_RESPONSE = "user_response"
    FOLLOW_UP = "follow_up"
    QUESTION = "question"
    CORRECTION = "correction"
    FEEDBACK = "feedback"


class RouteType(str, Enum):
    """Where to route the message"""
    EXECUTE = "execute"      # Start new execution
    RESUME = "resume"        # Resume paused execution
    DIRECT = "direct"        # Answer directly (no execution needed)
    MODIFY = "modify"        # Modify previous action


@dataclass
class IntakeResult:
    """Result of message classification"""
    message_type: MessageType
    route: RouteType
    confidence: float
    extracted_intent: str
    requires_context: bool
    detected_entities: Dict[str, List[str]]
    original_message: str
    # For RouterIntakeClassifier - direct response included
    direct_response: Optional[str] = None
    # For CLARIFY route
    clarify_question: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {
            'message_type': self.message_type.value,
            'route': self.route.value,
            'confidence': self.confidence,
            'extracted_intent': self.extracted_intent,
            'requires_context': self.requires_context,
            'detected_entities': self.detected_entities,
            'original_message': self.original_message
        }
        if self.direct_response:
            result['direct_response'] = self.direct_response
        if self.clarify_question:
            result['clarify_question'] = self.clarify_question
        return result


class QuickClassifier:
    """
    Rule-based classifier for obvious message types.
    Avoids LLM calls for simple cases.
    """

    # Patterns for task requests
    TASK_PATTERNS = [
        r'^(create|add|make|new)\s+(a\s+)?(task|note|project|area)',
        r'^(show|list|get|find)\s+(my\s+)?(tasks|notes|projects|areas|inbox)',
        r'^(complete|finish|done|check off)\s+',
        r'^(delete|remove|archive)\s+',
        r'^(move|transfer)\s+.+\s+to\s+',
        r'^(search|find|look for)\s+',
        r'^(summarize|distill|highlight)\s+',
        r'^(organize|sort|categorize)\s+',
    ]

    # Patterns for questions
    QUESTION_PATTERNS = [
        r'^(what|how|why|when|where|who|which)\s+.+\?$',
        r'^(can|could|would|should|is|are|do|does)\s+.+\?$',
        r'^(tell me|explain|describe)\s+',
    ]

    # Patterns for yes/no responses
    RESPONSE_PATTERNS = [
        r'^(yes|yeah|yep|sure|ok|okay|confirm|approved?|go ahead)\.?$',
        r'^(no|nope|nah|cancel|stop|don\'t|abort)\.?$',
        r'^(option\s*)?[1-4]\.?$',
        r'^(first|second|third|fourth|the\s+\w+\s+one)\.?$',
    ]

    # Patterns for corrections
    CORRECTION_PATTERNS = [
        r'^(no,?\s+)?(actually|instead|i meant|not that)',
        r'^(change|update|modify|edit)\s+(it|that|the)',
        r'^(wrong|incorrect|mistake)',
        r'^undo\s+',
    ]

    # Patterns for feedback
    FEEDBACK_PATTERNS = [
        r'^(thanks|thank you|great|perfect|awesome|good job)',
        r'^(that\'s\s+)?(wrong|not right|incorrect)',
        r'^(looks?\s+)?(good|great|perfect|fine)',
    ]

    # Patterns for greetings (should get direct response)
    GREETING_PATTERNS = [
        r'^(hi|hello|hey|howdy|greetings)[\s!.,]*$',
        r'^good\s+(morning|afternoon|evening|day)[\s!.,]*$',
        r'^(what\'?s\s+up|sup|yo)[\s!.,]*$',
    ]

    # Patterns for help requests (direct response)
    HELP_PATTERNS = [
        r'^help[\s!.,]*$',
        r'^(what can you do|what do you do)[\s?.,]*$',
        r'^how (can|do) (you|i) (use|work)',
    ]

    @classmethod
    def classify(
        cls,
        message: str,
        has_active_execution: bool = False
    ) -> Optional[IntakeResult]:
        """
        Try to classify message without LLM.

        Args:
            message: User message
            has_active_execution: Whether there's a paused execution

        Returns:
            IntakeResult if confident, None otherwise
        """
        msg_lower = message.lower().strip()

        # If there's an active execution, check for responses first
        if has_active_execution:
            for pattern in cls.RESPONSE_PATTERNS:
                if re.match(pattern, msg_lower, re.IGNORECASE):
                    return IntakeResult(
                        message_type=MessageType.USER_RESPONSE,
                        route=RouteType.RESUME,
                        confidence=0.95,
                        extracted_intent="user_response",
                        requires_context=True,
                        detected_entities={},
                        original_message=message
                    )

        # Check for corrections
        for pattern in cls.CORRECTION_PATTERNS:
            if re.match(pattern, msg_lower, re.IGNORECASE):
                return IntakeResult(
                    message_type=MessageType.CORRECTION,
                    route=RouteType.MODIFY,
                    confidence=0.85,
                    extracted_intent="correction",
                    requires_context=True,
                    detected_entities={},
                    original_message=message
                )

        # Check for task requests
        for pattern in cls.TASK_PATTERNS:
            if re.match(pattern, msg_lower, re.IGNORECASE):
                return IntakeResult(
                    message_type=MessageType.TASK_REQUEST,
                    route=RouteType.EXECUTE,
                    confidence=0.9,
                    extracted_intent=cls._extract_intent(msg_lower),
                    requires_context=False,
                    detected_entities=cls._extract_entities(message),
                    original_message=message
                )

        # Check for simple questions
        for pattern in cls.QUESTION_PATTERNS:
            if re.match(pattern, msg_lower, re.IGNORECASE):
                # Some questions require execution (e.g., "what tasks are due today?")
                if cls._is_data_question(msg_lower):
                    return IntakeResult(
                        message_type=MessageType.TASK_REQUEST,
                        route=RouteType.EXECUTE,
                        confidence=0.85,
                        extracted_intent=cls._extract_intent(msg_lower),
                        requires_context=False,
                        detected_entities={},
                        original_message=message
                    )
                else:
                    return IntakeResult(
                        message_type=MessageType.QUESTION,
                        route=RouteType.DIRECT,
                        confidence=0.8,
                        extracted_intent="question",
                        requires_context=False,
                        detected_entities={},
                        original_message=message
                    )

        # Check for greetings (high priority - should respond directly)
        for pattern in cls.GREETING_PATTERNS:
            if re.match(pattern, msg_lower, re.IGNORECASE):
                return IntakeResult(
                    message_type=MessageType.FEEDBACK,  # Treat as simple feedback
                    route=RouteType.DIRECT,
                    confidence=0.95,
                    extracted_intent="greeting",
                    requires_context=False,
                    detected_entities={},
                    original_message=message
                )

        # Check for help requests
        for pattern in cls.HELP_PATTERNS:
            if re.match(pattern, msg_lower, re.IGNORECASE):
                return IntakeResult(
                    message_type=MessageType.QUESTION,
                    route=RouteType.DIRECT,
                    confidence=0.95,
                    extracted_intent="help",
                    requires_context=False,
                    detected_entities={},
                    original_message=message
                )

        # Check for feedback
        for pattern in cls.FEEDBACK_PATTERNS:
            if re.match(pattern, msg_lower, re.IGNORECASE):
                return IntakeResult(
                    message_type=MessageType.FEEDBACK,
                    route=RouteType.DIRECT,
                    confidence=0.85,
                    extracted_intent="feedback",
                    requires_context=True,
                    detected_entities={},
                    original_message=message
                )

        # Couldn't classify with rules
        return None

    @classmethod
    def _extract_intent(cls, message: str) -> str:
        """Extract rough intent from message"""
        if any(word in message for word in ['create', 'add', 'new', 'make']):
            return 'create'
        elif any(word in message for word in ['show', 'list', 'get', 'display']):
            return 'list'
        elif any(word in message for word in ['find', 'search', 'look for']):
            return 'search'
        elif any(word in message for word in ['complete', 'finish', 'done']):
            return 'complete'
        elif any(word in message for word in ['delete', 'remove']):
            return 'delete'
        elif any(word in message for word in ['archive']):
            return 'archive'
        elif any(word in message for word in ['move', 'transfer']):
            return 'move'
        return 'unknown'

    @classmethod
    def _extract_entities(cls, message: str) -> Dict[str, List[str]]:
        """Extract entity references from message"""
        entities = {}

        # Look for quoted strings (often titles)
        quoted = re.findall(r'"([^"]+)"', message)
        if quoted:
            entities['quoted'] = quoted

        # Look for entity type mentions
        if re.search(r'\btasks?\b', message, re.IGNORECASE):
            entities['entity_type'] = entities.get('entity_type', []) + ['task']
        if re.search(r'\bnotes?\b', message, re.IGNORECASE):
            entities['entity_type'] = entities.get('entity_type', []) + ['note']
        if re.search(r'\bprojects?\b', message, re.IGNORECASE):
            entities['entity_type'] = entities.get('entity_type', []) + ['project']
        if re.search(r'\bareas?\b', message, re.IGNORECASE):
            entities['entity_type'] = entities.get('entity_type', []) + ['area']

        return entities

    @classmethod
    def _is_data_question(cls, message: str) -> bool:
        """Check if question requires data lookup"""
        data_keywords = [
            'tasks', 'notes', 'projects', 'areas', 'inbox',
            'due', 'overdue', 'today', 'tomorrow', 'this week',
            'pending', 'completed', 'archived',
            'how many', 'count', 'total'
        ]
        return any(kw in message for kw in data_keywords)


class SimpleIntakeClassifier:
    """
    Simple LLM-based classifier for message types.
    Classification only - no direct response generation.
    """

    SYSTEM_PROMPT = """You are a message classifier for ZemoNotes, a personal knowledge management assistant.

Your job: Analyze the user's message and determine how to handle it.

## Message Types

1. **task_request**: User wants to perform an action on their data
   - Creating: "create a task", "add a note", "new project"
   - Reading: "show my tasks", "list projects", "what's in my inbox"
   - Updating: "mark task as done", "update the note", "change priority"
   - Deleting: "delete the task", "remove that note", "archive project"
   - Organizing: "move task to project X", "tag this as important"

2. **user_response**: User is answering a question you asked
   - "yes", "no", "option 1", "the first one", "go ahead"

3. **follow_up**: User wants more action on something just discussed
   - "now mark it as high priority", "also add a due date", "do the same for notes"

4. **question**: User is asking something that doesn't require data operations
   - "how do I use tags?", "what's the difference between projects and areas?"

5. **correction**: User is fixing something you did wrong
   - "no, I meant the other task", "actually change it to tomorrow", "undo that"

6. **feedback**: Simple acknowledgment or reaction
   - Greetings: "hi", "hello", "hey", "good morning"
   - Thanks: "thanks", "thank you", "great", "perfect"
   - Confirmation: "looks good", "that's right"

## Routes

- **execute**: Perform data operations (task_request, data-related follow_ups)
- **resume**: Continue paused operation (user_response when there's active execution)
- **direct**: Respond immediately without data operations (greetings, feedback, simple questions, help requests)
- **modify**: Adjust previous operation (corrections)

## Key Rules

1. **Greetings are ALWAYS direct** - "hi", "hello", "hey" → route: direct
2. **Thanks/feedback are ALWAYS direct** - "thanks", "great job" → route: direct
3. **Help questions are direct** - "what can you do?", "help" → route: direct
4. **If there's active execution and user says yes/no** → route: resume
5. **Creating/updating/deleting/listing data** → route: execute

Output ONLY valid JSON:
{
    "message_type": "task_request|user_response|follow_up|question|correction|feedback",
    "route": "execute|resume|direct|modify",
    "confidence": 0.0-1.0,
    "extracted_intent": "brief description of what user wants",
    "requires_context": true/false,
    "reasoning": "one sentence explaining your decision"
}"""

    def __init__(self, model_name: str = None):
        """Initialize with specified model"""
        self.llm = LLMClient(model_name=model_name or "gemini-flash")

    def _build_context(
        self,
        conversation_summary: str = "",
        has_active_execution: bool = False,
        mentioned_entities: Dict[str, List[int]] = None
    ) -> str:
        """Build context string for LLM"""
        context_parts = []

        if conversation_summary:
            context_parts.append(f"Conversation summary:\n{conversation_summary}")

        if has_active_execution:
            context_parts.append("⚠️ STATUS: There is a paused execution awaiting user response. If user says yes/no/confirms, route should be 'resume'.")

        if mentioned_entities:
            entities_str = ", ".join(
                f"{etype}: {ids}" for etype, ids in mentioned_entities.items()
            )
            context_parts.append(f"Recently mentioned entities: {entities_str}")

        return "\n\n".join(context_parts) if context_parts else "No prior context (new conversation)"

    def _call_llm(self, message: str, context: str) -> IntakeResult:
        """Call LLM for classification"""
        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": f"Context:\n{context}\n\nUser message: {message}"}
        ]

        try:
            result = self.llm.chat_json(messages, temperature=0.1)

            # Parse message_type safely
            msg_type_str = result.get('message_type', 'task_request')
            try:
                msg_type = MessageType(msg_type_str)
            except ValueError:
                msg_type = MessageType.TASK_REQUEST

            # Parse route safely
            route_str = result.get('route', 'execute')
            try:
                route = RouteType(route_str)
            except ValueError:
                route = RouteType.EXECUTE

            return IntakeResult(
                message_type=msg_type,
                route=route,
                confidence=float(result.get('confidence', 0.8)),
                extracted_intent=result.get('extracted_intent', ''),
                requires_context=result.get('requires_context', False),
                detected_entities=QuickClassifier._extract_entities(message),
                original_message=message
            )

        except Exception as e:
            logger.error(f"IntakeClassifier LLM error: {e}")
            # Default fallback - treat as task request
            return IntakeResult(
                message_type=MessageType.TASK_REQUEST,
                route=RouteType.EXECUTE,
                confidence=0.5,
                extracted_intent="unknown - classification failed",
                requires_context=False,
                detected_entities={},
                original_message=message
            )

    async def classify(
        self,
        message: str,
        conversation_summary: str = "",
        has_active_execution: bool = False,
        mentioned_entities: Dict[str, List[int]] = None
    ) -> IntakeResult:
        """
        Classify a message using LLM (async version).

        Args:
            message: User message
            conversation_summary: Summary of recent conversation
            has_active_execution: Whether there's a paused execution
            mentioned_entities: Recently mentioned entity IDs

        Returns:
            IntakeResult with classification
        """
        context = self._build_context(
            conversation_summary, has_active_execution, mentioned_entities
        )
        return self._call_llm(message, context)

    def classify_sync(
        self,
        message: str,
        conversation_summary: str = "",
        has_active_execution: bool = False,
        mentioned_entities: Dict[str, List[int]] = None
    ) -> IntakeResult:
        """
        Classify a message using LLM (sync version).

        Args:
            message: User message
            conversation_summary: Summary of recent conversation
            has_active_execution: Whether there's a paused execution
            mentioned_entities: Recently mentioned entity IDs

        Returns:
            IntakeResult with classification
        """
        context = self._build_context(
            conversation_summary, has_active_execution, mentioned_entities
        )
        return self._call_llm(message, context)


class RouterIntakeClassifier:
    """
    V2-style combined classifier + direct responder.

    Key differences from SimpleIntakeClassifier:
    - Acts as EXECUTIVE COACH persona
    - Generates direct responses for DIRECT route (saves LLM call)
    - Has CLARIFY route for ambiguous requests
    - Context-aware: knows what data is available vs needs fetching
    """

    SYSTEM_PROMPT = """You are the AI assistant for ZemoNotes.

Your primary role is to act as an EXECUTIVE COACH and CHIEF OF STAFF for the user.

You help the user think clearly, prioritize effectively, and turn ideas into concrete actions.
You are calm, structured, pragmatic, and outcome-oriented.
You challenge gently when needed and reduce cognitive overload.

## Your Dual Role

1. **Classify** the user's request into DIRECT, AGENTIC, or CLARIFY
2. **If DIRECT**, also provide the response immediately

## Classification Categories

### DIRECT - Answer Now
Use when you CAN answer from the context provided (conversation history, user profile, areas, projects, task counts).

DIRECT examples:
- "What areas do I have?" → You have the area names in context
- "How many tasks are overdue?" → You have the counts in context
- "What projects are in my Career area?" → You have the project-area mapping
- "Hello" / "Thanks" / "Help" → Greetings, no data lookup needed
- "What is PARA?" → Conceptual question
- "Yes, do it" / "Ok" → Continuation of conversation (check history!)
- Follow-up questions about things already discussed

### AGENTIC - Needs Tools
Use when you need to:
- **Fetch actual content** (item titles, descriptions, note contents)
- **Search** for specific items by text or criteria
- **Create, update, delete, move** any items (mutations)
- **Get inbox items** (you only see COUNT, not the actual items)
- **List items with details** beyond what's in context

AGENTIC examples:
- "What's in my inbox?" → Need to fetch actual inbox items
- "Show me tasks due this week" → Need to fetch task details
- "Create a task called X" → Mutation
- "Search for notes about meetings" → Content search
- "What are the tasks in project X?" → Need to fetch task list

### CLARIFY - Need More Info
Use when the request is genuinely ambiguous even WITH conversation history.

CLARIFY examples:
- "Delete it" (and no prior context about what "it" is)
- Contradictory requests
- Vague references without context

## IMPORTANT: Check Conversation History!

Before classifying as CLARIFY, check if the conversation history provides context:
- "Yes" after being asked "Should I create this task?" → AGENTIC (proceed with creation)
- "Do it" after discussing a specific action → AGENTIC (proceed)
- "The first one" after being shown options → AGENTIC (use that option)

## Default Coaching Behavior

If the user is vague, exploratory, or conversational:
- Assume they are thinking out loud
- Help them clarify intent
- Reflect the underlying goal
- Propose a concrete next step

You may:
- Reframe problems
- Surface priorities
- Suggest planning structures
- Ask one sharp question to move forward

Do NOT:
- Overwhelm with options
- Ask unnecessary follow-ups
- Fabricate data
- Act without confirmation on destructive actions

## Response Format

**Always respond with valid JSON:**

If DIRECT (you can answer now):
```json
{"classification": "DIRECT", "response": "Your helpful response here"}
```

If AGENTIC (needs tools):
```json
{"classification": "AGENTIC", "intent": "brief description of what's needed"}
```

If CLARIFY (need more info):
```json
{"classification": "CLARIFY", "question": "Your clarifying question here"}
```"""

    def __init__(self, model_name: str = None):
        """Initialize with specified model"""
        self.llm = LLMClient(model_name=model_name or "gemini-flash")

    def _build_context(
        self,
        user,
        conversation_summary: str = "",
        has_active_execution: bool = False,
        mentioned_entities: Dict[str, List[int]] = None,
        recent_messages: List[Dict] = None
    ) -> str:
        """Build rich context for V2-style routing"""
        from para.models import Area, Project
        from notes.models import Note
        from django.utils import timezone
        from datetime import timedelta

        context_parts = []
        today = timezone.now().date()

        # User's organizational structure
        if user:
            # Areas (names only)
            areas = list(Area.objects.filter(
                user=user, is_active=True
            ).values_list('name', flat=True))

            # Projects with area mapping
            projects = list(Project.objects.filter(
                user=user, is_archived=False
            ).select_related('area').values('name', 'area__name', 'status'))

            # Task counts from Task model
            from tasks.models import Task
            tasks = Task.objects.filter(user=user, is_archived=False)
            task_counts = {
                'total': tasks.exclude(status='done').count(),
                'overdue': tasks.filter(
                    due_date__date__lt=today,
                    status__in=['todo', 'in_progress', 'waiting']
                ).count(),
                'due_today': tasks.filter(due_date__date=today).exclude(status='done').count(),
                'due_this_week': tasks.filter(
                    due_date__date__gt=today,
                    due_date__date__lte=today + timedelta(days=7)
                ).exclude(status='done').count(),
            }

            # Inbox count
            inbox_notes = Note.objects.filter(
                user=user, container_type='inbox', is_archived=False
            ).count()

            context_parts.append("## Context Summary (structure only, not content)")
            context_parts.append(f"\n**Areas ({len(areas)}):** {', '.join(areas) if areas else 'None'}")

            project_lines = [f"\n**Projects ({len(projects)}):**"]
            for p in projects[:15]:
                status_flag = " [on hold]" if p.get('status') == 'on_hold' else ""
                area_name = p.get('area__name', 'No Area')
                project_lines.append(f"  - {p['name']} (in {area_name}){status_flag}")
            context_parts.append("\n".join(project_lines))

            context_parts.append(
                f"\n**Task Counts:** {task_counts['total']} total, "
                f"{task_counts['overdue']} overdue, {task_counts['due_today']} due today, "
                f"{task_counts['due_this_week']} due this week"
            )
            context_parts.append(f"\n**Inbox:** {inbox_notes} items (titles/content NOT available without fetching)")

        # Conversation context
        if conversation_summary:
            context_parts.append(f"\n## Conversation Summary\n{conversation_summary}")

        if has_active_execution:
            context_parts.append("\n⚠️ STATUS: There is a paused execution awaiting user response.")

        if mentioned_entities:
            entities_str = ", ".join(
                f"{etype}: {ids}" for etype, ids in mentioned_entities.items()
            )
            context_parts.append(f"\nRecently mentioned entities: {entities_str}")

        # Recent messages for conversation flow
        if recent_messages:
            context_parts.append("\n## Recent Messages")
            for msg in recent_messages[-5:]:  # Last 5 messages
                role = msg.get('role', 'user')
                content = msg.get('content', '')[:200]  # Truncate long messages
                context_parts.append(f"{role.upper()}: {content}")

        return "\n".join(context_parts) if context_parts else "No prior context (new conversation)"

    def _call_llm(self, message: str, context: str) -> IntakeResult:
        """Call LLM for combined classification + response"""
        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": f"{context}\n\n---\nUser message: {message}"}
        ]

        try:
            result = self.llm.chat_json(messages, temperature=0.3)

            classification = result.get('classification', 'AGENTIC').upper()

            # Map V2 classifications to V4 routes
            if classification == 'DIRECT':
                return IntakeResult(
                    message_type=MessageType.FEEDBACK,  # Could be question/feedback
                    route=RouteType.DIRECT,
                    confidence=0.9,
                    extracted_intent=result.get('intent', 'direct_response'),
                    requires_context=False,
                    detected_entities=QuickClassifier._extract_entities(message),
                    original_message=message,
                    direct_response=result.get('response', '')
                )
            elif classification == 'CLARIFY':
                return IntakeResult(
                    message_type=MessageType.QUESTION,
                    route=RouteType.DIRECT,  # We'll respond with the clarifying question
                    confidence=0.85,
                    extracted_intent='needs_clarification',
                    requires_context=True,
                    detected_entities=QuickClassifier._extract_entities(message),
                    original_message=message,
                    clarify_question=result.get('question', 'Could you clarify what you mean?')
                )
            else:  # AGENTIC
                return IntakeResult(
                    message_type=MessageType.TASK_REQUEST,
                    route=RouteType.EXECUTE,
                    confidence=0.9,
                    extracted_intent=result.get('intent', 'execute_action'),
                    requires_context=False,
                    detected_entities=QuickClassifier._extract_entities(message),
                    original_message=message
                )

        except Exception as e:
            logger.error(f"RouterIntakeClassifier LLM error: {e}")
            # Default fallback - treat as task request
            return IntakeResult(
                message_type=MessageType.TASK_REQUEST,
                route=RouteType.EXECUTE,
                confidence=0.5,
                extracted_intent="unknown - classification failed",
                requires_context=False,
                detected_entities={},
                original_message=message
            )

    def classify_sync(
        self,
        message: str,
        user=None,
        conversation_summary: str = "",
        has_active_execution: bool = False,
        mentioned_entities: Dict[str, List[int]] = None,
        recent_messages: List[Dict] = None
    ) -> IntakeResult:
        """
        Classify a message with V2-style combined classification + response.

        Args:
            message: User message
            user: Django User instance (for context building)
            conversation_summary: Summary of recent conversation
            has_active_execution: Whether there's a paused execution
            mentioned_entities: Recently mentioned entity IDs
            recent_messages: Recent conversation messages

        Returns:
            IntakeResult with classification and optional direct_response
        """
        context = self._build_context(
            user=user,
            conversation_summary=conversation_summary,
            has_active_execution=has_active_execution,
            mentioned_entities=mentioned_entities,
            recent_messages=recent_messages
        )
        return self._call_llm(message, context)


# Alias for backward compatibility
IntakeClassifier = SimpleIntakeClassifier
