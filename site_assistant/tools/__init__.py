import logging
from .site_tools import SITE_TOOLS
from .page_tools import PAGE_TOOLS

logger = logging.getLogger(__name__)

ALL_TOOLS = {**SITE_TOOLS, **PAGE_TOOLS}


class ToolRegistry:
    """Dispatches tool calls to their implementations."""

    SITE_TOOL_NAMES = set(SITE_TOOLS.keys())
    PAGE_TOOL_NAMES = set(PAGE_TOOLS.keys())

    @classmethod
    def get_available_tools(cls, has_active_page):
        """Return tool names available given current context."""
        tools = set(cls.SITE_TOOL_NAMES)
        if has_active_page:
            tools |= cls.PAGE_TOOL_NAMES
        return tools

    @classmethod
    def execute(cls, tool_name, params, context):
        """
        Execute a tool by name.

        Args:
            tool_name: Name of the tool to execute
            params: Dict of parameters for the tool
            context: Dict with 'session', 'user', 'active_page' keys

        Returns:
            Dict with 'success', 'message', and tool-specific data
        """
        func = ALL_TOOLS.get(tool_name)
        if not func:
            return {'success': False, 'message': f'Unknown tool: {tool_name}'}

        if tool_name in cls.PAGE_TOOL_NAMES and not context.get('active_page'):
            return {
                'success': False,
                'message': f'Tool "{tool_name}" requires an active page. Use set_active_page first.'
            }

        try:
            return func(params, context)
        except Exception as e:
            logger.exception(f'Tool {tool_name} failed')
            return {'success': False, 'message': f'Tool error: {str(e)}'}
