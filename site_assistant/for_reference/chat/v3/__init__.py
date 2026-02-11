"""
Chat V3 - Agentic-First Architecture

An understanding-first chat system inspired by Claude Code.

Key components:
- IntakeClassifier: Fast routing (conversational vs agentic)
- AgentLoop: Iterative execution engine
- Planner: Plan generation and management (Phase 2)
- MemoryManager: Context and learnings (Phase 3)

Usage:
    from chat.v3 import ChatServiceV3

    service = ChatServiceV3(conversation)
    response = await service.send_message("What's in my inbox?")
"""

from .service import ChatServiceV3

__all__ = ['ChatServiceV3']
__version__ = '0.1.0'
