"""
Chat V3 Exceptions

Custom exceptions for the V3 chat system.
"""

from typing import Optional, Dict, Any


class ChatV3Error(Exception):
    """Base exception for Chat V3."""
    pass


class ParseError(ChatV3Error):
    """Error parsing LLM response."""

    def __init__(self, message: str, raw_response: Optional[str] = None):
        super().__init__(message)
        self.raw_response = raw_response


class ToolError(ChatV3Error):
    """Error executing a tool."""

    def __init__(
        self,
        message: str,
        tool_name: str,
        params: Optional[Dict[str, Any]] = None,
        is_recoverable: bool = True
    ):
        super().__init__(message)
        self.tool_name = tool_name
        self.params = params
        self.is_recoverable = is_recoverable


class ToolNotFoundError(ToolError):
    """Tool not found in registry."""

    def __init__(self, tool_name: str):
        super().__init__(
            f"Unknown tool: {tool_name}",
            tool_name=tool_name,
            is_recoverable=False
        )


class ValidationError(ToolError):
    """Tool parameter validation failed."""

    def __init__(self, message: str, tool_name: str, params: Dict[str, Any]):
        super().__init__(
            message,
            tool_name=tool_name,
            params=params,
            is_recoverable=True
        )


class ResourceNotFoundError(ToolError):
    """Requested resource not found."""

    def __init__(self, resource_type: str, resource_id: Any):
        super().__init__(
            f"{resource_type} with ID {resource_id} not found",
            tool_name="execute",
            params={"resource_type": resource_type, "id": resource_id},
            is_recoverable=True
        )


class PermissionError(ToolError):
    """User doesn't have permission for this operation."""

    def __init__(self, message: str, resource_type: str, resource_id: Any):
        super().__init__(
            message,
            tool_name="execute",
            params={"resource_type": resource_type, "id": resource_id},
            is_recoverable=False
        )


class MaxIterationsError(ChatV3Error):
    """Maximum iterations reached without completing task."""

    def __init__(self, iterations: int, partial_result: Optional[str] = None):
        super().__init__(f"Maximum iterations ({iterations}) reached")
        self.iterations = iterations
        self.partial_result = partial_result


class LLMError(ChatV3Error):
    """Error from LLM API call."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class PlanError(ChatV3Error):
    """Error in plan execution."""

    def __init__(self, message: str, step_index: Optional[int] = None):
        super().__init__(message)
        self.step_index = step_index
