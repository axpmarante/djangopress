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

# Confirmation words (multi-language) — user must say one of these
# in their last message before a destructive tool is allowed
CONFIRMATION_WORDS = {
    'yes', 'sim', 'confirmo', 'confirmar', 'confirm', 'ok', 'sure',
    'go ahead', 'do it',
}


def _has_recent_confirmation(context):
    """Check if the user's most recent message confirms a destructive action.

    Looks at the session's message history for the last user message and
    checks if it contains a confirmation word.
    """
    session = context.get('session')
    if not session or not session.messages:
        return False

    # Find the last user message
    for msg in reversed(session.messages):
        if msg.get('role') == 'user':
            content = msg.get('content', '').lower().strip()
            # Strip punctuation for word-boundary matching
            import re
            clean_content = re.sub(r'[^\w\s]', ' ', content)
            words_in_message = set(clean_content.split())
            for word in CONFIRMATION_WORDS:
                if ' ' in word:
                    # Multi-word: check as substring in cleaned content
                    if word in clean_content:
                        return True
                elif word in words_in_message:
                    return True
            return False

    return False


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

        # Destructive action safety net
        if tool_name in DESTRUCTIVE_TOOLS:
            if not _has_recent_confirmation(context):
                return {
                    'success': False,
                    'message': (
                        f'BLOCKED: "{tool_name}" is destructive and requires user confirmation. '
                        f'Ask the user to confirm before calling this tool. '
                        f'Do NOT call the tool again until the user explicitly confirms.'
                    ),
                }

        try:
            return func(params, context)
        except Exception as e:
            logger.exception(f'Tool {tool_name} failed')
            return {'success': False, 'message': f'Tool error: {str(e)}'}
