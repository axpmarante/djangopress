"""
Chat V2 Tools - Base Infrastructure

Base classes and utilities for the V2 tool system.

Tools are the interface between the LLM and the application.
Two types:
- search_tool: Read-only queries with filters
- execute_tool: Mutations (create, update, delete) + actions
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Union, Callable
from enum import Enum
from datetime import datetime


class ToolStatus(str, Enum):
    """Status of a tool execution."""
    SUCCESS = "success"
    ERROR = "error"
    NOT_FOUND = "not_found"
    PERMISSION_DENIED = "permission_denied"
    VALIDATION_ERROR = "validation_error"
    CONFIRMATION_REQUIRED = "confirmation_required"


@dataclass
class ToolResult:
    """
    Result from a tool execution.

    Used by both search_tool and execute_tool.
    """
    status: ToolStatus
    data: Optional[Any] = None  # The actual result data
    message: str = ""  # Human-readable message
    error: Optional[str] = None  # Error details if failed

    # Metadata
    tool: str = ""  # Tool name (search_tool, execute_tool)
    action: str = ""  # Action performed (search, create, etc.)
    resource_type: str = ""  # Resource type (note, task, project, area)
    execution_time_ms: int = 0

    # For confirmation flow
    requires_confirmation: bool = False
    confirmation_token: Optional[str] = None

    def is_success(self) -> bool:
        return self.status == ToolStatus.SUCCESS

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            'status': self.status.value,
            'message': self.message,
            'tool': self.tool,
            'action': self.action,
            'resource_type': self.resource_type,
        }

        if self.data is not None:
            result['data'] = self.data

        if self.error:
            result['error'] = self.error

        if self.requires_confirmation:
            result['requires_confirmation'] = True
            result['confirmation_token'] = self.confirmation_token

        return result

    def to_llm_string(self) -> str:
        """Format result for LLM context injection."""
        if self.status == ToolStatus.SUCCESS:
            if isinstance(self.data, list):
                return f"Found {len(self.data)} items: {self.message}"
            elif isinstance(self.data, dict):
                return f"{self.message}: {self.data}"
            else:
                return self.message or str(self.data)
        else:
            return f"Error: {self.error or self.message}"


@dataclass
class ToolCall:
    """
    Represents a tool call request from the LLM.

    Parsed from LLM output JSON.
    """
    tool: str  # search_tool or execute_tool
    action: str  # search, list, read, create, update, delete, etc.
    resource_type: str = ""  # note, task, project, area, tag
    params: Dict[str, Any] = field(default_factory=dict)

    # Tracking
    call_id: str = ""  # Unique ID for this call
    created_at: datetime = field(default_factory=datetime.now)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ToolCall':
        """Create ToolCall from dictionary."""
        return cls(
            tool=data.get('tool', ''),
            action=data.get('action', ''),
            resource_type=data.get('resource_type', ''),
            params=data.get('params', {}),
        )

    def validate(self) -> List[str]:
        """Validate the tool call. Returns list of error messages."""
        errors = []

        if not self.tool:
            errors.append("Tool name is required")
        elif self.tool not in ['search_tool', 'execute_tool']:
            errors.append(f"Unknown tool: {self.tool}")

        if not self.action:
            errors.append("Action is required")

        return errors


class BaseTool(ABC):
    """
    Base class for all tools.

    Subclasses implement specific actions for search_tool and execute_tool.
    """

    # Tool name (search_tool, execute_tool)
    name: str = ""

    # Available actions for this tool
    actions: List[str] = []

    # Resource types this tool can work with
    resource_types: List[str] = ['note', 'task', 'project', 'area', 'tag']

    def __init__(self, user):
        self.user = user

    @abstractmethod
    def execute(self, call: ToolCall) -> ToolResult:
        """Execute a tool call and return result."""
        pass

    def validate_call(self, call: ToolCall) -> Optional[str]:
        """
        Validate a tool call before execution.

        Returns error message if invalid, None if valid.
        """
        if call.tool != self.name:
            return f"Wrong tool: expected {self.name}, got {call.tool}"

        if call.action not in self.actions:
            return f"Unknown action '{call.action}' for {self.name}. Available: {self.actions}"

        if call.resource_type and call.resource_type not in self.resource_types:
            return f"Unknown resource type '{call.resource_type}'. Available: {self.resource_types}"

        return None

    def _result(
        self,
        status: ToolStatus,
        data: Any = None,
        message: str = "",
        error: str = None,
        action: str = "",
        resource_type: str = ""
    ) -> ToolResult:
        """Helper to create ToolResult with common fields filled."""
        return ToolResult(
            status=status,
            data=data,
            message=message,
            error=error,
            tool=self.name,
            action=action,
            resource_type=resource_type,
        )


class ToolRegistry:
    """
    Registry for all available tools.

    Provides a single entry point for executing tool calls.
    """

    def __init__(self, user):
        self.user = user
        self._tools: Dict[str, BaseTool] = {}
        self._register_default_tools()

    def _register_default_tools(self):
        """Register the default search_tool and execute_tool."""
        from .search_tool import SearchTool
        from .execute_tool import ExecuteTool

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

        Validates the call, routes to the correct tool, and returns result.
        """
        import time
        start_time = time.time()

        # Validate basic call structure
        validation_errors = call.validate()
        if validation_errors:
            return ToolResult(
                status=ToolStatus.VALIDATION_ERROR,
                error="; ".join(validation_errors),
                tool=call.tool,
                action=call.action,
            )

        # Get the tool
        tool = self.get(call.tool)
        if not tool:
            return ToolResult(
                status=ToolStatus.ERROR,
                error=f"Unknown tool: {call.tool}",
                tool=call.tool,
                action=call.action,
            )

        # Validate action
        validation_error = tool.validate_call(call)
        if validation_error:
            return ToolResult(
                status=ToolStatus.VALIDATION_ERROR,
                error=validation_error,
                tool=call.tool,
                action=call.action,
            )

        # Execute
        try:
            result = tool.execute(call)
            result.execution_time_ms = int((time.time() - start_time) * 1000)
            return result
        except Exception as e:
            return ToolResult(
                status=ToolStatus.ERROR,
                error=str(e),
                tool=call.tool,
                action=call.action,
                resource_type=call.resource_type,
            )

    def execute_many(self, calls: List[ToolCall]) -> List[ToolResult]:
        """Execute multiple tool calls in sequence."""
        return [self.execute(call) for call in calls]

    def list_tools(self) -> List[Dict[str, Any]]:
        """List all registered tools and their actions."""
        return [
            {
                'name': tool.name,
                'actions': tool.actions,
                'resource_types': tool.resource_types,
            }
            for tool in self._tools.values()
        ]


def parse_tool_calls(llm_response: str) -> List[ToolCall]:
    """
    Parse tool calls from LLM response.

    Expects JSON format like:
    {
        "tool_calls": [
            {"tool": "search_tool", "resource_type": "task", "filters": {...}}
        ]
    }

    Or single call:
    {"tool": "search_tool", "resource_type": "task", "filters": {...}}
    """
    import json
    import re

    calls = []

    # Try to find JSON in response
    json_patterns = [
        r'```json\s*(.*?)\s*```',  # Markdown code block
        r'```\s*(.*?)\s*```',  # Generic code block
        r'(\{.*\})',  # Raw JSON object
    ]

    json_str = None
    for pattern in json_patterns:
        match = re.search(pattern, llm_response, re.DOTALL)
        if match:
            json_str = match.group(1).strip()
            break

    if not json_str:
        return calls

    try:
        data = json.loads(json_str)

        # Check for tool_calls array
        if 'tool_calls' in data and isinstance(data['tool_calls'], list):
            for call_data in data['tool_calls']:
                calls.append(ToolCall.from_dict(call_data))

        # Check for single tool call
        elif 'tool' in data and 'action' in data:
            calls.append(ToolCall.from_dict(data))

    except json.JSONDecodeError:
        pass

    return calls
