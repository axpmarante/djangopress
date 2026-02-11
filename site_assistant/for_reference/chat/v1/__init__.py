"""
Chat V1 - Tool Loop Architecture with VEL Gate

The original chat implementation using:
- <internal>/<public> tag system for LLM responses
- VEL command execution in tool loop
- VEL Gate validation for hallucination prevention
- Two-phase LLM approach (tool loop + structured summary)

Usage:
    from chat.v1 import ChatService

    service = ChatService(user, conversation)
    result = service.send_message("Create a task")
"""

from .service import ChatService

__all__ = ['ChatService']
