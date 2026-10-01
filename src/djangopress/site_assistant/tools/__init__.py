import logging
from .site_tools import SITE_TOOLS
from .page_tools import PAGE_TOOLS
from .component_tools import COMPONENT_TOOLS
from .photo_tools import PHOTO_TOOLS

logger = logging.getLogger(__name__)

ALL_TOOLS = {**SITE_TOOLS, **PAGE_TOOLS, **COMPONENT_TOOLS, **PHOTO_TOOLS}

# Conditionally import news tools if the news app is installed
try:
    from .news_tools import NEWS_TOOLS
    ALL_TOOLS.update(NEWS_TOOLS)
except ImportError:
    NEWS_TOOLS = {}

# Conditionally import properties tools if the properties app is installed
try:
    from .properties_tools import PROPERTIES_TOOLS
    ALL_TOOLS.update(PROPERTIES_TOOLS)
except ImportError:
    PROPERTIES_TOOLS = {}

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
    PROPERTIES_TOOL_NAMES = set(PROPERTIES_TOOLS.keys()) if PROPERTIES_TOOLS else set()

    @classmethod
    def get_available_tools(cls, has_active_page):
        tools = set(cls.SITE_TOOL_NAMES) | cls.NEWS_TOOL_NAMES | cls.PROPERTIES_TOOL_NAMES
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
            track_before(tool_name, params, context)
            result = func(params, context)
            if result.get('success'):
                track_after(tool_name, params, result, context)
            return result
        except Exception as e:
            logger.exception(f'Tool {tool_name} failed')
            return {'success': False, 'message': f'Tool error: {str(e)}'}


# --- undo tracking (site_assistant.changes) ----------------------------------------

# Tools that change the active page: one labelled checkpoint per page per turn.
ACTIVE_PAGE_TOOLS = {
    'update_element_styles', 'update_element_attribute', 'remove_section', 'reorder_sections',
    'refine_section', 'refine_page', 'insert_section', 'set_section_background',
    'reorder_items', 'replace_item_image', 'add_item_images', 'remove_item',
}


def _obj(model_label, pk):
    from django.apps import apps
    try:
        return apps.get_model(model_label).objects.filter(pk=pk).first() if pk else None
    except LookupError:
        return None


def track_before(tool_name, params, context):
    from djangopress.site_assistant import changes
    if not (context or {}).get('changes'):
        return
    if tool_name in ACTIVE_PAGE_TOOLS and context.get('active_page'):
        changes.page_checkpoint(context, context['active_page'])
    elif tool_name in ('update_page_meta', 'delete_page'):
        changes.snapshot(context, _obj('core.page', params.get('page_id')), 'Page settings')
    elif tool_name == 'reorder_pages':
        for pk in params.get('order') or []:
            changes.snapshot(context, _obj('core.page', pk), 'Page order')
    elif tool_name in ('update_menu_item', 'delete_menu_item'):
        changes.snapshot(context, _obj('core.menuitem', params.get('menu_item_id')), 'Menu item')
    elif tool_name == 'update_settings':
        from djangopress.core.models import SiteSettings
        changes.snapshot(context, SiteSettings.load(), 'Site settings')
    elif tool_name in ('update_form', 'delete_form'):
        from djangopress.core.models import DynamicForm
        form = _obj('core.dynamicform', params.get('form_id')) or \
            DynamicForm.objects.filter(slug=params.get('slug') or '').first()
        changes.snapshot(context, form, 'Form')
    elif tool_name in ('refine_header', 'refine_footer'):
        from djangopress.core.models import GlobalSection
        key = 'main-header' if tool_name == 'refine_header' else 'main-footer'
        section = GlobalSection.objects.filter(key=key).first()
        if section:
            changes.global_section_checkpoint(context, section)
    elif tool_name == 'update_news_post':
        changes.snapshot(context, _obj('news.newspost', params.get('post_id')), 'News post')
    elif tool_name == 'update_property':
        changes.snapshot(context, _obj('properties.property', params.get('property_id')), 'Property')


def track_after(tool_name, params, result, context):
    from djangopress.site_assistant import changes
    if not (context or {}).get('changes'):
        return
    created = {
        'create_page': ('core.page', 'page_id', 'New page'),
        'create_menu_item': ('core.menuitem', 'menu_item_id', 'New menu item'),
        'create_form': ('core.dynamicform', 'form_id', 'New form'),
        'create_news_post': ('news.newspost', 'post_id', 'New news post'),
    }.get(tool_name)
    if created:
        model, key, label = created
        changes.created(context, _obj(model, result.get(key)), label)
