"""
Chat V3 Tools - Base Infrastructure

Simplified tool system for V3 architecture.

Tools:
- search: Read-only queries
- execute: Mutations (create, update, delete, move, etc.)
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, TYPE_CHECKING
from enum import Enum

if TYPE_CHECKING:
    from django.contrib.auth import get_user_model
    User = get_user_model()

from ..types import ToolCall, ToolResult
from ..config import SafetyLevel


class BaseTool(ABC):
    """
    Base class for V3 tools.

    Simplified from V2:
    - No action routing (each tool does one thing)
    - Cleaner result format
    - Better error messages for LLM recovery
    """

    name: str = ""
    description: str = ""
    safety_level: SafetyLevel = SafetyLevel.READ_ONLY

    def __init__(self, user):
        self.user = user

    @abstractmethod
    def execute(self, call: ToolCall) -> ToolResult:
        """Execute the tool and return result."""
        pass

    def _success(
        self,
        data: Any = None,
        summary: str = ""
    ) -> ToolResult:
        """Create a success result."""
        return ToolResult(
            success=True,
            data=data,
            summary=summary
        )

    def _error(self, message: str) -> ToolResult:
        """Create an error result."""
        return ToolResult(
            success=False,
            error=message,
            summary=f"Error: {message}"
        )

    def _not_found(self, resource_type: str, identifier: Any) -> ToolResult:
        """Create a not-found result."""
        return ToolResult(
            success=False,
            error=f"{resource_type.capitalize()} with ID {identifier} not found",
            summary=f"Not found: {resource_type} {identifier}"
        )


class ToolRegistry:
    """
    Registry for V3 tools.

    Simplified interface:
    - register(tool) - Add a tool
    - execute(call) - Execute a tool call
    """

    def __init__(self, user):
        self.user = user
        self._tools: Dict[str, BaseTool] = {}
        self._register_default_tools()

    def _register_default_tools(self):
        """Register search and execute tools."""
        from .search import SearchTool
        from .execute import ExecuteTool

        self.register(SearchTool(self.user))
        self.register(ExecuteTool(self.user))

    def register(self, tool: BaseTool):
        """Register a tool."""
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[BaseTool]:
        """Get a tool by name."""
        return self._tools.get(name)

    def execute(self, call: ToolCall) -> ToolResult:
        """
        Execute a tool call.

        Args:
            call: ToolCall with tool name and params

        Returns:
            ToolResult with success/error and data
        """
        tool = self.get(call.tool)
        if not tool:
            return ToolResult(
                success=False,
                error=f"Unknown tool: {call.tool}. Available: {list(self._tools.keys())}",
                summary=f"Unknown tool: {call.tool}"
            )

        try:
            return tool.execute(call)
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Tool execution failed: {str(e)}",
                summary=f"Error in {call.tool}: {str(e)}"
            )

    def get_available_tools(self) -> List[str]:
        """Get list of available tool names."""
        return list(self._tools.keys())
