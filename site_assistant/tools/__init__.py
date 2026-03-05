import logging
from .site_tools import SITE_TOOLS
from .page_tools import PAGE_TOOLS

logger = logging.getLogger(__name__)

ALL_TOOLS = {**SITE_TOOLS, **PAGE_TOOLS}

# Conditionally import news tools if the news app is installed
try:
    from .news_tools import NEWS_TOOLS
    ALL_TOOLS.update(NEWS_TOOLS)
except ImportError:
    NEWS_TOOLS = {}

DESTRUCTIVE_TOOLS = {'delete_page', 'delete_menu_item', 'delete_form'}


class ToolRegistry:
    """Dispatches tool calls to their implementations."""

    SITE_TOOL_NAMES = set(SITE_TOOLS.keys())
    PAGE_TOOL_NAMES = set(PAGE_TOOLS.keys())
    NEWS_TOOL_NAMES = set(NEWS_TOOLS.keys()) if NEWS_TOOLS else set()

    @classmethod
    def get_available_tools(cls, has_active_page):
        tools = set(cls.SITE_TOOL_NAMES) | cls.NEWS_TOOL_NAMES
        if has_active_page:
            tools |= cls.PAGE_TOOL_NAMES
        return tools

    @classmethod
    def execute(cls, tool_name, params, context):
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
