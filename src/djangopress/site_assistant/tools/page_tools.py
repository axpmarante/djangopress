"""Page-level tools — require an active page in the session."""

from djangopress.ai.utils.llm_config import get_ai_model
from djangopress.core.models import Page
from djangopress.core.services import PageService


def _get_page(context):
    """Get the active page from context."""
    page = context.get('active_page')
    if not page:
        return None
    try:
        return Page.objects.get(pk=page.pk)
    except Page.DoesNotExist:
        return None


def _create_version_if_needed(context):
    """Create a page version before mutations (once per turn)."""
    if context.get('_version_created'):
        return
    page = _get_page(context)
    if page:
        user = context.get('user')
        page.create_version(user=user, change_summary='Site Assistant edit')
        context['_version_created'] = True


def update_element_styles(params, context):
    _create_version_if_needed(context)
    page = _get_page(context)
    if not page:
        return {'success': False, 'message': 'Active page not found'}
    result = PageService.update_element_styles(
        page, selector=params.get('selector'),
        section_name=params.get('section_name'),
        new_classes=params.get('new_classes', ''),
    )
    if not result['success']:
        return {'success': False, 'message': result['error']}
    return {'success': True, 'message': result['message']}


def update_element_attribute(params, context):
    _create_version_if_needed(context)
    page = _get_page(context)
    if not page:
        return {'success': False, 'message': 'Active page not found'}
    result = PageService.update_element_attribute(
        page, selector=params.get('selector', ''),
        attribute=params.get('attribute', ''),
        value=params.get('value', ''),
    )
    if not result['success']:
        return {'success': False, 'message': result['error']}
    return {'success': True, 'message': result['message']}


def remove_section(params, context):
    _create_version_if_needed(context)
    page = _get_page(context)
    if not page:
        return {'success': False, 'message': 'Active page not found'}
    result = PageService.remove_section(page, params.get('section_name', ''))
    if not result['success']:
        return {'success': False, 'message': result['error']}
    return {'success': True, 'message': result['message']}


def reorder_sections(params, context):
    _create_version_if_needed(context)
    page = _get_page(context)
    if not page:
        return {'success': False, 'message': 'Active page not found'}
    result = PageService.reorder_sections(page, params.get('order', []))
    if not result['success']:
        return {'success': False, 'message': result['error']}
    return {'success': True, 'message': result['message']}


def refine_section(params, context):
    """AI-regenerate a single section. Delegates to ContentGenerationService."""
    _create_version_if_needed(context)
    page = _get_page(context)
    if not page:
        return {'success': False, 'message': 'Active page not found'}

    section_name = params.get('section_name')
    instructions = params.get('instructions', '')
    if not section_name or not instructions:
        return {'success': False, 'message': 'Missing section_name or instructions'}

    model = get_ai_model('refinement_section')
    ref_images = context.get('reference_images')
    from djangopress.ai.services import ContentGenerationService
    service = ContentGenerationService(
        model_name=model, assistant_session=context.get('session'),
    )
    result = service.refine_section_only(
        page_id=page.id, section_name=section_name,
        instructions=instructions, model_override=model,
        reference_images=ref_images or None,
    )

    refined_html = result.get('options', [{}])[0].get('html', '')
    if not refined_html:
        return {'success': False, 'message': 'The AI returned no section'}

    from djangopress.editor_v2 import ai_apply
    exists = f'data-section="{section_name}"' in (page.html_content_i18n or {}).get(_default_lang(), '')
    if exists:
        applied = ai_apply.apply_section_html(page, refined_html, _default_lang(), section_name=section_name,
                                              user=context.get('user'))
    else:  # a new section is added at the end of the page
        applied = ai_apply.apply_section_html(page, refined_html, _default_lang(), mode='insert',
                                              insert_after=_last_section(page), user=context.get('user'))

    return {
        'success': True,
        'message': f'Refined section "{applied["section_name"]}" with AI' + _languages_note(applied),
        'assistant_message': result.get('assistant_message', ''),
    }


def refine_page(params, context):
    """AI-regenerate entire page. Delegates to ContentGenerationService."""
    _create_version_if_needed(context)
    page = _get_page(context)
    if not page:
        return {'success': False, 'message': 'Active page not found'}

    instructions = params.get('instructions', '')
    if not instructions:
        return {'success': False, 'message': 'Missing instructions'}

    model = get_ai_model('refinement_page')
    ref_images = context.get('reference_images')
    from djangopress.ai.services import ContentGenerationService
    service = ContentGenerationService(
        model_name=model, assistant_session=context.get('session'),
    )
    result = service.refine_page_with_html(
        page_id=page.id, instructions=instructions,
        model_override=model,
        reference_images=ref_images or None,
        handle_images=params.get('handle_images', False),
    )

    page.refresh_from_db()
    html = (result.get('html_content_i18n') or {}).get(result.get('lang') or _default_lang())
    if not html:
        return {'success': False, 'message': 'The AI returned no page'}
    from djangopress.editor_v2 import ai_apply
    applied = ai_apply.apply_page_html(page, html, _default_lang(), user=context.get('user'))
    return {'success': True, 'message': 'Refined entire page with AI' + _languages_note(applied)}


def _default_lang():
    from djangopress.core.models import SiteSettings
    settings = SiteSettings.load()
    return settings.get_default_language() if settings else 'pt'


def _last_section(page):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup((page.html_content_i18n or {}).get(_default_lang(), ''), 'html.parser')
    named = soup.find_all('section', attrs={'data-section': True})
    return named[-1].get('data-section') if named else None


def _languages_note(applied):
    note = ''
    if applied.get('translated_languages'):
        note += f" (translated to {', '.join(applied['translated_languages'])})"
    if applied.get('untranslated_languages'):
        note += f" (not translated: {', '.join(applied['untranslated_languages'])})"
    return note


PAGE_TOOLS = {
    'update_element_styles': update_element_styles,
    'update_element_attribute': update_element_attribute,
    'remove_section': remove_section,
    'reorder_sections': reorder_sections,
    'refine_section': refine_section,
    'refine_page': refine_page,
}
