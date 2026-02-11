"""
Chat V3 Configuration

Central configuration for the V3 chat system.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class RouteType(Enum):
    """Classification of incoming messages."""
    CONVERSATIONAL = "conversational"  # Greetings, thanks, general questions
    AGENTIC = "agentic"  # Requires tools to complete


class SafetyLevel(Enum):
    """Safety classification for tools."""
    READ_ONLY = "read_only"  # Search, get operations
    MUTATION = "mutation"  # Create, update operations
    DESTRUCTIVE = "destructive"  # Delete, archive operations


class PlanStatus(Enum):
    """Status of an execution plan."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepStatus(Enum):
    """Status of a plan step."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class V3Config:
    """Configuration for Chat V3."""

    # Loop limits
    MAX_ITERATIONS: int = 15
    MAX_SEARCH_ITERATIONS: int = 5
    MAX_CONSECUTIVE_ERRORS: int = 3

    # Token budgets
    MAX_CONTEXT_TOKENS: int = 4000
    MAX_RESPONSE_TOKENS: int = 1000

    # Memory settings
    MAX_DISCOVERIES_IN_CONTEXT: int = 5
    MAX_LEARNINGS_IN_CONTEXT: int = 3
    MAX_CONVERSATION_HISTORY: int = 10

    # Planning thresholds
    MIN_STEPS_FOR_PLAN: int = 2
    MAX_PLAN_STEPS: int = 10

    # Timing (in seconds)
    LLM_TIMEOUT_SECONDS: int = 30
    TOOL_TIMEOUT_SECONDS: int = 10

    # Retry settings
    MAX_PARSE_RETRIES: int = 2
    MAX_TOOL_RETRIES: int = 1


# Default configuration instance
config = V3Config()
