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
        from djangopress.site_assistant import changes
        changes.page_checkpoint(context, page)
        context['_version_created'] = True


def update_element_styles(params, context):
    _create_version_if_needed(context)
    page = _get_page(context)
    if not page:
        return {'success': False, 'message': 'Active page not found'}
    if params.get('add_classes') or params.get('remove_classes'):
        result = PageService.update_element_classes(
            page, selector=params.get('selector'), section_name=params.get('section_name'),
            add=params.get('add_classes', ''), remove=params.get('remove_classes', ''),
        )
    elif params.get('new_classes') is not None:
        result = PageService.update_element_styles(
            page, selector=params.get('selector'),
            section_name=params.get('section_name'),
            new_classes=params.get('new_classes', ''),
        )
    else:
        return {'success': False, 'message': 'Give add_classes/remove_classes (or new_classes to replace all)'}
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


READ_LIMIT = 12000


def read_section(params, context):
    """The section's HTML in the editing language, so restyles use real classes."""
    page = _get_page(context)
    if not page:
        return {'success': False, 'message': 'Active page not found'}
    from bs4 import BeautifulSoup
    lang = _default_lang()
    name = params.get('section_name')
    soup = BeautifulSoup((page.html_content_i18n or {}).get(lang, ''), 'html.parser')
    section = soup.find('section', attrs={'data-section': name})
    if section is None:
        return {'success': False,
                'message': f'Section "{name}" not found. Sections on this page: {", ".join(_section_names(page, lang)) or "none"}'}
    html = str(section)
    message = f'HTML of section "{name}" ({lang})'
    if len(html) > READ_LIMIT:
        html = html[:READ_LIMIT]
        message += f'; cut at {READ_LIMIT} characters, the rest of the section is not shown'
    return {'success': True, 'message': message, 'html': html}


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
                                              user=context.get('user'), checkpoint=False)
    else:  # a new section is added at the end of the page
        applied = ai_apply.apply_section_html(page, refined_html, _default_lang(), mode='insert',
                                              insert_after=_last_section(page), user=context.get('user'), checkpoint=False)

    return {
        'success': True,
        'message': f'Refined section "{applied["section_name"]}" with AI' + _languages_note(applied),
        'assistant_message': result.get('assistant_message', ''),
    }


def insert_section(params, context):
    """Generate ONE new section and put it where asked. Only the new section is
    translated; the rest of the page stays byte-identical in every language."""
    page = _get_page(context)
    if not page:
        return {'success': False, 'message': 'Active page not found'}
    instructions = params.get('instructions', '')
    if not instructions:
        return {'success': False, 'message': 'Missing instructions'}

    lang = _default_lang()
    names = _section_names(page, lang)
    position = params.get('position') or 'end'
    anchor = params.get('anchor_section')
    if position in ('before', 'after'):
        if anchor not in names:
            return {'success': False,
                    'message': f'Section "{anchor}" not found. Sections on this page: {", ".join(names) or "none"}'}
        index = names.index(anchor)
        insert_after = anchor if position == 'after' else (names[index - 1] if index else None)
    elif position == 'start':
        insert_after = None
    else:
        insert_after = names[-1] if names else None

    _create_version_if_needed(context)
    model = get_ai_model('refinement_section')
    from djangopress.ai.services import ContentGenerationService
    service = ContentGenerationService(model_name=model, assistant_session=context.get('session'))
    result = service.generate_section(
        page_id=page.id, insert_after=insert_after, instructions=instructions,
        model_override=model, lang=lang,
    )
    new_html = (result.get('options') or [{}])[0].get('html', '')
    if not new_html:
        return {'success': False, 'message': 'The AI returned no section'}

    from djangopress.editor_v2 import ai_apply
    page.refresh_from_db()
    applied = ai_apply.apply_section_html(page, new_html, lang, mode='insert', insert_after=insert_after,
                                          user=context.get('user'), checkpoint=False)
    where = f'after "{insert_after}"' if insert_after else 'at the top of the page'
    return {'success': True,
            'message': f'Added section "{applied["section_name"]}" {where}' + _languages_note(applied),
            'section_name': applied['section_name']}


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
    applied = ai_apply.apply_page_html(page, html, _default_lang(), user=context.get('user'), checkpoint=False)
    return {'success': True, 'message': 'Refined entire page with AI' + _languages_note(applied)}


def _default_lang():
    from djangopress.core.models import SiteSettings
    settings = SiteSettings.load()
    return settings.get_default_language() if settings else 'pt'


def _section_names(page, lang):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup((page.html_content_i18n or {}).get(lang, ''), 'html.parser')
    return [s.get('data-section') for s in soup.find_all('section', attrs={'data-section': True})]


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
    'insert_section': insert_section,
    'read_section': read_section,
    'refine_section': refine_section,
    'refine_page': refine_page,
}
