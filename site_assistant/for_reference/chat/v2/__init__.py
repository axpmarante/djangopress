"""
Chat V2 - Multi-layered Architecture

This module implements the V2 chat architecture with:
- Layer 0: Router (DIRECT / AGENTIC / CLARIFY classification)
- Layer 1: Dynamic Context Assembly
- Layer 2: Tools (search_tool, execute_tool)
- Planner: Creates execution plans for AGENTIC requests
- Executor: Executes plan steps

Key components:
- AgentMemory: Persistent state for LLM conversations
- MemoryState: Runtime state management
- Router: Intent classification
- DynamicContextBuilder: Minimal context assembly
- Planner: Step-by-step plan creation
- Executor: Plan execution with state management
- search_tool: Universal search with filters
- execute_tool: Create, update, delete + external actions
"""

from .models import AgentMemory, PlanStep
from .memory import MemoryState, RouteType
from .router import Router, RouterResult, classify_message
from .context import DynamicContextBuilder, AssembledContext, build_context
from .planner import Planner, PlanResult, create_plan
from .executor import Executor, StepResult, PlanExecutionResult, execute_current_step, run_full_plan
from .orchestrator import ChatServiceV2, ChatResponse, send_message_v2

__all__ = [
    # Models
    'AgentMemory',
    'PlanStep',
    # Memory
    'MemoryState',
    'RouteType',
    # Router
    'Router',
    'RouterResult',
    'classify_message',
    # Context
    'DynamicContextBuilder',
    'AssembledContext',
    'build_context',
    # Planner
    'Planner',
    'PlanResult',
    'create_plan',
    # Executor
    'Executor',
    'StepResult',
    'PlanExecutionResult',
    'execute_current_step',
    'run_full_plan',
    # Orchestrator
    'ChatServiceV2',
    'ChatResponse',
    'send_message_v2',
]