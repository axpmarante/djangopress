from django import template
from django.utils.safestring import mark_safe

register = template.Library()


@register.inclusion_tag('partials/global_sections/cta.html')
def cta_section(title=None, text=None, button_text=None, button_url=None):
    """Render a call-to-action section"""
    return {
        'section_title': title,
        'section_text': text,
        'button_text': button_text,
        'button_url': button_url or '#',
    }


@register.simple_tag
def site_image(key, default=None, css_class=None):
    """Render an image by its key with optional fallback and CSS class"""
    from djangopress.core.models import SiteImage
    from django.utils.safestring import mark_safe

    try:
        image = SiteImage.objects.get(key=key, is_active=True)
        img_url = image.image.url
        alt_text = image.alt_text or image.title
    except SiteImage.DoesNotExist:
        if default:
            img_url = default
            alt_text = key.replace('_', ' ').title()
        else:
            return ''

    class_attr = f' class="{css_class}"' if css_class else ''
    return mark_safe(f'<img src="{img_url}" alt="{alt_text}"{class_attr}>')


@register.filter
def translate(content, lang):
    """
    Extract translation from JSON content.
    Usage: {{ section.content|translate:LANGUAGE_CODE }}
    Returns: dict with title, subtitle, description, button_text
    """
    if not isinstance(content, dict):
        return {}

    translations = content.get('translations', {})
    return translations.get(lang, {})


@register.filter
def get_design(design, key):
    """
    Get design value from JSON.
    Usage: {{ section.design|get_design:'background_color' }}
    """
    if not isinstance(design, dict):
        return ''
    return design.get(key, '')


@register.filter
def get_setting(settings, key):
    """
    Get setting value from JSON.
    Usage: {{ section.settings|get_setting:'button_url' }}
    """
    if not isinstance(settings, dict):
        return ''
    return settings.get(key, '')


@register.filter
def index(indexable, i):
    """
    Get item from list by index.
    Usage: {{ section.settings.image_urls|index:forloop.counter0 }}
    """
    try:
        return indexable[int(i)]
    except (IndexError, ValueError, TypeError, KeyError):
        return ''


@register.filter
def getitem(dictionary, key):
    """
    Get item from dictionary by key.
    Usage: {{ some_dict|getitem:'key' }}
    """
    if not isinstance(dictionary, dict):
        return None
    return dictionary.get(key)


@register.filter
def get_translation(json_field, lang=None):
    """
    Extract translation from JSON field.
    Usage: {{ page.title|get_translation:LANGUAGE_CODE }}

    Supports both simple dict and nested translations structure:
    - Simple: {"pt": "Title PT", "en": "Title EN"}
    - Nested: {"translations": {"pt": {...}, "en": {...}}}

    If lang is None, returns entire JSON (for debugging)
    Falls back to 'pt' if requested language not found
    """
    # Handle non-JSON fields (return as-is for backward compatibility)
    if not isinstance(json_field, dict):
        return json_field

    # If no language specified, return entire JSON
    if lang is None:
        return json_field

    # Check if it's a nested translations structure (like Section content)
    if 'translations' in json_field:
        translations = json_field.get('translations', {})
        return translations.get(lang, translations.get('pt', ''))

    # Otherwise treat as simple dict (like new i18n fields)
    return json_field.get(lang, json_field.get('pt', ''))


@register.filter
def get_translation_or_fallback(json_field, lang=None):
    """
    Same as get_translation but returns the first available language if requested lang not found.
    More forgiving for incomplete translations.

    Usage: {{ page.title|get_translation_or_fallback:LANGUAGE_CODE }}
    """
    if not isinstance(json_field, dict):
        return json_field

    if lang is None:
        return json_field

    # Check nested structure
    if 'translations' in json_field:
        translations = json_field.get('translations', {})
    else:
        translations = json_field

    # Try requested language
    if lang in translations:
        return translations[lang]

    # Fall back to default language
    if 'pt' in translations:
        return translations['pt']

    # Fall back to first available language
    if translations:
        first_lang = next(iter(translations.keys()))
        return translations[first_lang]

    return ''


@register.simple_tag(takes_context=True)
def load_global_section(context, key, fallback_template=None):
    """
    Load and render a global section (header, footer, etc) from the database.

    Usage:
        {% load_global_section 'main-header' fallback_template='partials/header.html' %}

    If section doesn't exist and fallback_template is provided, uses fallback.
    """
    from djangopress.core.models import GlobalSection
    from django.template.loader import render_to_string
    from django.template import Template, Context

    # Get current language
    language = context.get('LANGUAGE_CODE', 'pt')

    # Try to load from database
    try:
        section = GlobalSection.objects.get(key=key, is_active=True)

        # Get default language from SiteSettings
        from djangopress.core.models import SiteSettings
        site_settings = SiteSettings.load()
        default_lang = site_settings.get_default_language() if site_settings else 'pt'

        # Get per-language HTML (with fallback to default language)
        html_i18n = section.html_template_i18n or {}
        html = html_i18n.get(language) or html_i18n.get(default_lang)

        if html:
            # Build context for rendering (Django template engine needed for {% url %}, etc.)
            section_context = {
                'section': section,
                'LANGUAGE_CODE': language,
            }
            section_context.update(context.flatten())

            # Render template (Django template engine always needed for {% url %}, etc.)
            template = Template(html)
            rendered_html = template.render(Context(section_context))
        else:
            return mark_safe(f'<!-- Global section has no content: {key} -->')

        return mark_safe(rendered_html)

    except GlobalSection.DoesNotExist:
        # Fall back to template file if provided
        if fallback_template:
            try:
                rendered_html = render_to_string(fallback_template, context.flatten())
                return mark_safe(rendered_html)
            except Exception as e:
                return mark_safe(f'<!-- Global section fallback failed: {fallback_template} - {e} -->')

        return mark_safe(f'<!-- Global section not found: {key} -->')


@register.filter
def get_menu_label(menu_item, lang=None):
    """
    Get menu item label in specified language.
    Usage: {{ item|get_menu_label:LANGUAGE_CODE }}
    """
    if not lang:
        lang = 'pt'
    return menu_item.get_label(lang)


@register.filter
def get_menu_url(menu_item, lang=None):
    """
    Get menu item URL in specified language.
    Usage: {{ item|get_menu_url:LANGUAGE_CODE }}
    """
    if not lang:
        lang = 'pt'
    return menu_item.get_url(lang)


@register.simple_tag(takes_context=True)
def hreflang_tags(context):
    """
    Output <link rel="alternate" hreflang="xx"> tags for all enabled languages,
    plus an x-default pointing to the default language URL.

    Usage in <head>: {% hreflang_tags %}
    """
    page_obj = context.get('page_obj')
    if not page_obj or not hasattr(page_obj, 'get_absolute_url'):
        return ''

    request = context.get('request')
    language_codes = context.get('LANGUAGE_CODES', [])
    default_language = context.get('DEFAULT_LANGUAGE', 'pt')

    if not language_codes or len(language_codes) < 2:
        return ''

    links = []
    for lang in language_codes:
        url = page_obj.get_absolute_url(lang)
        if request:
            url = request.build_absolute_uri(url)
        links.append(f'<link rel="alternate" hreflang="{lang}" href="{url}">')

    # x-default points to the default language URL
    default_url = page_obj.get_absolute_url(default_language)
    if request:
        default_url = request.build_absolute_uri(default_url)
    links.append(f'<link rel="alternate" hreflang="x-default" href="{default_url}">')

    return mark_safe('\n    '.join(links))
