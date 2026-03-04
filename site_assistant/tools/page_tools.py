"""Page-level tools — require an active page in the session."""

from bs4 import BeautifulSoup
from core.models import Page


def _get_default_language():
    """Get the default language from SiteSettings."""
    from core.models import SiteSettings
    site_settings = SiteSettings.objects.first()
    return site_settings.get_default_language() if site_settings else 'pt'


def _get_page_html(page, lang=None):
    """Read page HTML from html_content_i18n.

    Returns:
        Tuple of (html_string, resolved_language_code)
    """
    from django.utils.translation import get_language
    default_lang = _get_default_language()
    lang = lang or get_language() or default_lang
    html_i18n = page.html_content_i18n or {}
    return html_i18n.get(lang) or html_i18n.get(default_lang) or '', lang


def _get_page(context):
    """Get the active page from context."""
    page = context.get('active_page')
    if not page:
        return None
    # Refresh from DB
    try:
        return Page.objects.get(pk=page.pk)
    except Page.DoesNotExist:
        return None


def _save_html(page, soup, lang=None):
    """Save BeautifulSoup back to page.html_content_i18n."""
    from django.utils.translation import get_language
    new_html = str(soup)
    if new_html.startswith('<html><body>'):
        new_html = new_html[12:-14]

    default_lang = _get_default_language()
    lang = lang or get_language() or default_lang

    html_i18n = dict(page.html_content_i18n or {})
    html_i18n[lang] = new_html
    page.html_content_i18n = html_i18n
    page.save()


def _create_version_if_needed(context):
    """Create a page version before mutations (once per turn)."""
    if context.get('_version_created'):
        return
    page = _get_page(context)
    if page:
        user = context.get('user')
        page.create_version(user=user, change_summary='Site Assistant edit')
        context['_version_created'] = True


def update_translations(params, context):
    """Deprecated — text is now embedded in per-language HTML (html_content_i18n).
    Use refine_section or refine_page to change text content."""
    return {'success': False, 'message': 'update_translations is deprecated. Use refine_section or refine_page to change text.'}


def update_element_styles(params, context):
    _create_version_if_needed(context)
    page = _get_page(context)
    if not page:
        return {'success': False, 'message': 'Active page not found'}

    selector = params.get('selector')
    section_name = params.get('section_name')
    new_classes = params.get('new_classes', '')

    if not selector and not section_name:
        return {'success': False, 'message': 'Provide selector or section_name'}

    html, lang = _get_page_html(page)
    if not html:
        return {'success': False, 'message': 'Page has no HTML content'}

    soup = BeautifulSoup(html, 'html.parser')

    if selector:
        element = soup.select_one(selector)
    else:
        element = soup.find('section', attrs={'data-section': section_name})

    if not element:
        return {'success': False, 'message': 'Element not found'}

    old_classes = ' '.join(element.get('class', []))
    if new_classes:
        element['class'] = new_classes.split()
    elif 'class' in element.attrs:
        del element['class']

    _save_html(page, soup, lang)
    return {
        'success': True,
        'message': 'Updated element classes',
        'old_classes': old_classes,
        'new_classes': new_classes,
    }


def update_element_attribute(params, context):
    _create_version_if_needed(context)
    page = _get_page(context)
    if not page:
        return {'success': False, 'message': 'Active page not found'}

    selector = params.get('selector')
    attribute = params.get('attribute')
    value = params.get('value', '')

    if not selector or not attribute:
        return {'success': False, 'message': 'Missing selector or attribute'}

    html, lang = _get_page_html(page)
    soup = BeautifulSoup(html, 'html.parser')
    element = soup.select_one(selector)

    if not element:
        return {'success': False, 'message': 'Element not found for selector'}

    old_value = element.get(attribute, '')
    if value:
        element[attribute] = value
    elif attribute in element.attrs:
        del element[attribute]

    _save_html(page, soup, lang)
    return {
        'success': True,
        'message': f'Updated {attribute} on element',
        'old_value': old_value,
        'new_value': value,
    }


def remove_section(params, context):
    _create_version_if_needed(context)
    page = _get_page(context)
    if not page:
        return {'success': False, 'message': 'Active page not found'}

    section_name = params.get('section_name')
    if not section_name:
        return {'success': False, 'message': 'Missing section_name'}

    html, lang = _get_page_html(page)
    soup = BeautifulSoup(html, 'html.parser')
    section = soup.find('section', attrs={'data-section': section_name})

    if not section:
        return {'success': False, 'message': f'Section "{section_name}" not found'}

    section.decompose()
    _save_html(page, soup, lang)

    return {'success': True, 'message': f'Removed section "{section_name}"'}


def reorder_sections(params, context):
    _create_version_if_needed(context)
    page = _get_page(context)
    if not page:
        return {'success': False, 'message': 'Active page not found'}

    order = params.get('order', [])
    if not order:
        return {'success': False, 'message': 'Missing order list'}

    html, lang = _get_page_html(page)
    soup = BeautifulSoup(html, 'html.parser')

    # Extract all sections
    sections = {}
    for sec in soup.find_all('section', attrs={'data-section': True}):
        sections[sec['data-section']] = sec.extract()

    # Re-insert in new order
    for name in order:
        if name in sections:
            soup.append(sections[name])

    # Append any sections not in the order list (preserve them at the end)
    for name, sec in sections.items():
        if name not in order:
            soup.append(sec)

    _save_html(page, soup, lang)
    return {'success': True, 'message': f'Reordered {len(order)} sections'}


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

    # Always use gemini-pro for AI generation quality, regardless of chat model
    model = 'gemini-pro'

    from ai.services import ContentGenerationService
    service = ContentGenerationService(model_name=model)
    result = service.refine_section_only(
        page_id=page.id,
        section_name=section_name,
        instructions=instructions,
        model_override=model,
    )

    # Apply the refined section to the page
    html, lang = _get_page_html(page)
    soup = BeautifulSoup(html, 'html.parser')
    old_section = soup.find('section', attrs={'data-section': section_name})

    # refine_section_only returns {'options': [{'html': ...}], 'assistant_message': ...}
    # with clean HTML (no template vars) — stored per-language in html_content_i18n
    refined_html = result.get('options', [{}])[0].get('html', '')

    if old_section and refined_html:
        new_soup = BeautifulSoup(refined_html, 'html.parser')
        new_section = new_soup.find('section') or new_soup
        old_section.replace_with(new_section)
    elif refined_html:
        # Append as new section
        new_soup = BeautifulSoup(refined_html, 'html.parser')
        soup.append(new_soup)

    _save_html(page, soup, lang)

    return {
        'success': True,
        'message': f'Refined section "{section_name}" with AI',
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

    # Always use gemini-pro for AI generation quality, regardless of chat model
    model = 'gemini-pro'
    reference_images = params.get('reference_images', [])

    from ai.services import ContentGenerationService
    service = ContentGenerationService(model_name=model)
    result = service.refine_page_with_html(
        page_id=page.id,
        instructions=instructions,
        model_override=model,
        reference_images=reference_images or None,
        handle_images=params.get('handle_images', False),
    )

    page.refresh_from_db()

    # refine_page_with_html returns html_content_i18n
    if 'html_content_i18n' in result:
        page.html_content_i18n = result['html_content_i18n']
    page.save()

    return {
        'success': True,
        'message': 'Refined entire page with AI',
    }


# Registry mapping
PAGE_TOOLS = {
    'update_translations': update_translations,
    'update_element_styles': update_element_styles,
    'update_element_attribute': update_element_attribute,
    'remove_section': remove_section,
    'reorder_sections': reorder_sections,
    'refine_section': refine_section,
    'refine_page': refine_page,
}
