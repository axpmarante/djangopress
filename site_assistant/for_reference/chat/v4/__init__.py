"""
Chat V4 - Multi-Agent Architecture

A multi-agent system for ZemoNotes that uses specialized agents
coordinated by an orchestration layer with shared state.

Components:
- IntakeClassifier: Routes incoming messages
- Planner: Creates execution plans
- Stepper: Controls execution flow
- Specialized Agents: Domain-specific actions (tasks, notes, projects, etc.)
- Finisher: Synthesizes final responses

Key concepts:
- ExecutionState: Central state for a single request execution
- ConversationState: Persistent state across conversation
- Working Memory: Cross-step data sharing

Usage:
    from chat.v4 import ChatServiceV4, V4Router

    # Using the service directly
    service = ChatServiceV4(user, conversation)
    result = service.process("Create a task called Review docs")

    # Using the router (compatible with V2 interface)
    router = V4Router(user, conversation)
    result = router.route("Create a task called Review docs")
"""

__version__ = "4.0.0"

# Main service classes
from .service import ChatServiceV4, ServiceConfig, ServiceResult, process_message
from .router import V4Router, V4RouterResult, route_v4_message

# Core state
from .state import ExecutionState, StepResult, PlanStep, Plan

# Models
from .models import ConversationState

# Intake/Classification
from .intake import IntakeClassifier, QuickClassifier, IntakeResult, RouteType, MessageType

# Execution
from .engine import ExecutionEngine, EngineConfig, EngineResult

# Agents
from .agents import AgentRegistry, BaseAgent

__all__ = [
    # Service layer
    'ChatServiceV4',
    'ServiceConfig',
    'ServiceResult',
    'process_message',
    'V4Router',
    'V4RouterResult',
    'route_v4_message',
    # State
    'ExecutionState',
    'StepResult',
    'PlanStep',
    'Plan',
    'ConversationState',
    # Intake
    'IntakeClassifier',
    'QuickClassifier',
    'IntakeResult',
    'RouteType',
    'MessageType',
    # Engine
    'ExecutionEngine',
    'EngineConfig',
    'EngineResult',
    # Agents
    'AgentRegistry',
    'BaseAgent',
]
