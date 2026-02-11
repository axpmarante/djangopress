"""
Chat V3 Intake Classifier

Fast pattern-based classification to route messages.

Design philosophy:
- Most messages go to AGENTIC (default)
- Only purely conversational messages bypass tools
- Fast pattern matching, no LLM call needed
"""

import re
from typing import List, Tuple

from .config import RouteType
from .types import IntakeResult


class IntakeClassifier:
    """
    Fast classifier for incoming messages.

    Routes to:
    - CONVERSATIONAL: Greetings, thanks, help, conceptual questions
    - AGENTIC: Everything else (data queries, mutations, etc.)

    This is intentionally simple - we bias toward AGENTIC because
    it's better to search and find nothing than to guess from context.
    """

    # Patterns that indicate CONVERSATIONAL (no tools needed)
    CONVERSATIONAL_PATTERNS: List[Tuple[str, str]] = [
        # Greetings - allow trailing words like "hi there!"
        (r'^(hi|hello|hey|hola|good\s*(morning|afternoon|evening))(\s+\w+)?[\s!.,]*$', 'greeting'),
        (r'^(howdy|sup|yo)[\s!.,]*$', 'greeting'),

        # Thanks/Acknowledgments
        (r'^(thanks?|thank\s*you|thx|ty|gracias)[\s!.,]*$', 'thanks'),
        (r'^(got\s*it|understood|ok|okay|cool|great|perfect|nice)[\s!.,]*$', 'acknowledgment'),

        # Help requests (about the system, not data)
        (r'^(help|ayuda|\?)[\s!.,]*$', 'help'),
        (r'^what\s+can\s+you\s+do', 'help'),
        (r'^how\s+do\s+(i|you)\s+use', 'help'),

        # Conceptual questions (about methodology, not user data)
        (r'^what\s+is\s+(para|code|second\s*brain|gtd|progressive\s*summar)', 'conceptual'),
        (r'^(explain|tell\s*me\s*about)\s+(para|areas?|projects?|inbox)', 'conceptual'),

        # Farewells
        (r'^(bye|goodbye|see\s*you|later|ciao|adios)[\s!.,]*$', 'farewell'),

        # Simple affirmations (when no pending action)
        (r'^(yes|yeah|yep|yup|si|sí|sure|absolutely|definitely)[\s!.,]*$', 'affirmation'),
        (r'^(do\s*it|go\s*ahead|proceed|please|pls)[\s!.,]*$', 'affirmation'),
    ]

    # Patterns that FORCE AGENTIC (even if conversational patterns match)
    AGENTIC_FORCE_PATTERNS: List[Tuple[str, str]] = [
        # Explicit data queries
        (r'(show|list|get|find|search|what\'?s?\s+in)', 'data_query'),
        (r'(how\s+many|count)', 'count_query'),

        # Mutations
        (r'(create|add|new|make)\s+(a\s+)?(task|note|project|area)', 'create'),
        (r'(delete|remove|archive)', 'delete'),
        (r'(update|change|edit|modify|rename)', 'update'),
        (r'(move|organize|file)', 'move'),
        (r'(complete|done|finish|mark)', 'complete'),
        (r'(start|begin)', 'start'),

        # Specific item references
        (r'(my|the)\s+(inbox|tasks?|notes?|projects?|areas?)', 'item_reference'),
        (r'(overdue|due\s+(today|tomorrow|this\s+week))', 'due_reference'),

        # Questions about user's data
        (r'(do\s+i\s+have|are\s+there)', 'existence_query'),
    ]

    def __init__(self):
        # Compile patterns for efficiency
        self._conversational_compiled = [
            (re.compile(pattern, re.IGNORECASE), reason)
            for pattern, reason in self.CONVERSATIONAL_PATTERNS
        ]
        self._agentic_compiled = [
            (re.compile(pattern, re.IGNORECASE), reason)
            for pattern, reason in self.AGENTIC_FORCE_PATTERNS
        ]

    def classify(self, message: str, has_pending_action: bool = False) -> IntakeResult:
        """
        Classify a message for routing.

        Args:
            message: The user's message
            has_pending_action: True if there's a pending confirmation/action

        Returns:
            IntakeResult with route_type and confidence
        """
        message = message.strip()

        # Empty message - conversational
        if not message:
            return IntakeResult(
                route_type=RouteType.CONVERSATIONAL,
                confidence=1.0,
                reason="empty message"
            )

        # If there's a pending action, affirmations should continue it
        if has_pending_action and self._is_affirmation(message):
            return IntakeResult(
                route_type=RouteType.AGENTIC,
                confidence=0.95,
                reason="affirmation with pending action"
            )

        # Check for AGENTIC force patterns first
        for pattern, reason in self._agentic_compiled:
            if pattern.search(message):
                return IntakeResult(
                    route_type=RouteType.AGENTIC,
                    confidence=0.95,
                    reason=f"pattern:{reason}"
                )

        # Check for CONVERSATIONAL patterns
        for pattern, reason in self._conversational_compiled:
            if pattern.match(message):
                return IntakeResult(
                    route_type=RouteType.CONVERSATIONAL,
                    confidence=0.9,
                    reason=f"pattern:{reason}"
                )

        # Default to AGENTIC - better to search and verify than guess
        return IntakeResult(
            route_type=RouteType.AGENTIC,
            confidence=0.7,
            reason="default to agentic"
        )

    def _is_affirmation(self, message: str) -> bool:
        """Check if message is a simple affirmation."""
        affirmations = [
            r'^(yes|yeah|yep|yup|si|sí|sure|absolutely|definitely|do\s*it|go\s*ahead)[\s!.,]*$',
            r'^(ok|okay|k|alright)[\s!.,]*$',
            r'^(please|pls)[\s!.,]*$',
            r'^(the\s+)?(first|second|third|last)\s*(one)?[\s!.,]*$',
            r'^[1-9][\s!.,]*$',  # Just a number
        ]
        for pattern in affirmations:
            if re.match(pattern, message, re.IGNORECASE):
                return True
        return False


# Singleton instance
intake_classifier = IntakeClassifier()


def classify_message(message: str, has_pending_action: bool = False) -> IntakeResult:
    """
    Convenience function to classify a message.

    Args:
        message: The user's message
        has_pending_action: True if there's a pending confirmation

    Returns:
        IntakeResult with route_type
    """
    return intake_classifier.classify(message, has_pending_action)
