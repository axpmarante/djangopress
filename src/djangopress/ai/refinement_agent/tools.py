"""Tool implementations for the Refinement Agent."""

import re
from bs4 import BeautifulSoup


# ── Read-only context tools ──────────────────────────────────────────────────

def inspect_html(params, context):
    """Return the current target HTML."""
    return {
        'success': True,
        'message': 'Current target HTML',
        'html': context['target_html'],
    }


def get_design_guide(params, context):
    """Fetch the site's design guide."""
    if 'design_guide' not in context:
        from djangopress.core.models import SiteSettings
        settings = context.get('site_settings') or SiteSettings.objects.first()
        context['design_guide'] = settings.design_guide if settings else ''
    guide = context['design_guide']
    if not guide:
        return {'success': True, 'message': 'No design guide configured.'}
    return {'success': True, 'message': guide}


def get_briefing(params, context):
    """Fetch the project briefing."""
    if 'briefing' not in context:
        from djangopress.core.models import SiteSettings
        settings = context.get('site_settings') or SiteSettings.objects.first()
        context['briefing'] = settings.get_project_briefing() if settings else ''
    briefing = context['briefing']
    if not briefing:
        return {'success': True, 'message': 'No project briefing configured.'}
    return {'success': True, 'message': briefing}


def get_pages_list(params, context):
    """List all active pages with titles and slugs."""
    from djangopress.core.models import Page
    pages = Page.objects.filter(is_active=True).order_by('id')
    lines = []
    for p in pages:
        title = p.default_title or '(untitled)'
        slug = p.default_slug or '(no slug)'
        lines.append(f'- ID:{p.id} | {title} | /{slug}/')
    return {
        'success': True,
        'message': '\n'.join(lines) if lines else 'No active pages found.',
    }


# ── Direct edit tools (instant, no AI call) ──────────────────────────────────

def update_styles(params, context):
    """Add/remove CSS classes on an element in the target HTML."""
    target_html = context['target_html']
    selector = params.get('selector', '')
    add_classes = params.get('add_classes', '')
    remove_classes = params.get('remove_classes', '')

    if not add_classes and not remove_classes:
        return {'success': False, 'message': 'No classes to add or remove'}

    soup = BeautifulSoup(target_html, 'html.parser')

    if selector:
        element = soup.select_one(selector)
    else:
        # Target the root element (first section or first child)
        element = soup.find('section') or next(soup.children, None)

    if not element or not hasattr(element, 'get'):
        return {'success': False, 'message': f'Element not found for selector: {selector or "(root)"}'}

    current = set(element.get('class', []))

    if remove_classes:
        for cls in remove_classes.split():
            current.discard(cls)
            # Also remove by pattern for Tailwind variants (e.g. "bg-" removes bg-gray-700)
            if cls.endswith('-'):
                current = {c for c in current if not c.startswith(cls)}

    if add_classes:
        for cls in add_classes.split():
            current.add(cls)

    if current:
        element['class'] = sorted(current)
    elif 'class' in element.attrs:
        del element['class']

    new_html = str(soup)
    # Strip wrapper if BeautifulSoup added <html><body>
    if new_html.startswith('<html><body>'):
        new_html = new_html[12:-14]

    context['target_html'] = new_html
    return {
        'success': True,
        'message': f'Updated classes. Added: {add_classes or "(none)"}. Removed: {remove_classes or "(none)"}.',
        'html': new_html,
    }


def update_text(params, context):
    """Update text content directly in the de-templatized HTML."""
    target_html = context['target_html']
    updates = params.get('updates', {})

    if not updates:
        return {'success': False, 'message': 'No text updates provided'}

    soup = BeautifulSoup(target_html, 'html.parser')
    replaced = 0

    for old_text, new_text in updates.items():
        # Find text nodes containing the old text and replace
        for text_node in soup.find_all(string=re.compile(re.escape(old_text))):
            text_node.replace_with(text_node.replace(old_text, new_text))
            replaced += 1

    if replaced == 0:
        return {'success': False, 'message': f'Text not found in HTML. Available text: {soup.get_text(strip=True)[:200]}'}

    new_html = str(soup)
    if new_html.startswith('<html><body>'):
        new_html = new_html[12:-14]

    context['target_html'] = new_html
    return {
        'success': True,
        'message': f'Updated {replaced} text occurrence(s).',
        'html': new_html,
    }


# ── AI delegation tools ──────────────────────────────────────────────────────

def refine_with_ai(params, context):
    """Delegate to ContentGenerationService.refine_section_only() with agent-chosen params."""
    from djangopress.ai.services import ContentGenerationService

    model = params.get('model', 'gemini-flash')
    include_components = params.get('include_components', False)
    include_briefing = params.get('include_briefing', False)
    include_pages = params.get('include_pages', False)
    include_design_guide = params.get('include_design_guide', True)

    page = context['page']
    scope = context['scope']
    instructions = context['instructions']
    conversation_history = context.get('conversation_history', [])
    multi_option = context.get('multi_option', False)

    service = ContentGenerationService(model_name=model)

    if scope == 'element':
        result = service.refine_element_only(
            page_id=page.id,
            selector=context['target_name'],
            instructions=instructions,
            conversation_history=conversation_history,
            multi_option=multi_option,
            model_override=model,
            skip_component_selection=not include_components,
            skip_briefing=not include_briefing,
            skip_pages_list=not include_pages,
            skip_design_guide=not include_design_guide,
        )
    else:
        result = service.refine_section_only(
            page_id=page.id,
            section_name=context['target_name'],
            instructions=instructions,
            conversation_history=conversation_history,
            multi_option=multi_option,
            model_override=model,
            skip_component_selection=not include_components,
            skip_briefing=not include_briefing,
            skip_pages_list=not include_pages,
            skip_design_guide=not include_design_guide,
        )

    return {
        'success': True,
        'message': f'AI refinement complete ({model})',
        'result': result,
        '_is_delegation': True,
    }


# ── Tool registry ────────────────────────────────────────────────────────────

READ_TOOLS = {'inspect_html', 'get_design_guide', 'get_briefing', 'get_pages_list'}
DIRECT_EDIT_TOOLS = {'update_styles', 'update_text'}
DELEGATION_TOOLS = {'refine_with_ai'}

ALL_TOOLS = {
    'inspect_html': inspect_html,
    'get_design_guide': get_design_guide,
    'get_briefing': get_briefing,
    'get_pages_list': get_pages_list,
    'update_styles': update_styles,
    'update_text': update_text,
    'refine_with_ai': refine_with_ai,
}


def execute(tool_name, params, context):
    """Execute a tool by name. Returns dict with at least {success, message}."""
    func = ALL_TOOLS.get(tool_name)
    if not func:
        return {'success': False, 'message': f'Unknown tool: {tool_name}'}
    try:
        return func(params, context)
    except Exception as e:
        return {'success': False, 'message': f'Tool error: {str(e)}'}
