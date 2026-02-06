from django import template
from django.urls import reverse
from django.utils.safestring import mark_safe

register = template.Library()


@register.inclusion_tag('partials/global_sections/cta.html')
def cta_section(title=None, text=None, button_text=None, button_url=None):
    """Render a call-to-action section"""
    return {
        'section_title': title,
        'section_text': text,
        'button_text': button_text,
        'button_url': button_url or reverse('core:contact'),
    }


@register.simple_tag
def site_image(key, default=None, css_class=None):
    """Render an image by its key with optional fallback and CSS class"""
    from core.models import SiteImage
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
    Load and render a global section (header, footer, etc) with caching.

    Usage:
        {% load_global_section 'main-header' fallback_template='partials/header.html' %}

    The section is cached per language for performance.
    If section doesn't exist and fallback_template is provided, uses fallback.
    """
    from core.models import GlobalSection
    from django.core.cache import cache
    from django.template.loader import render_to_string
    from django.template import Template, Context

    # Get current language
    language = context.get('LANGUAGE_CODE', 'pt')

    # Try to get from cache first
    cache_key = f'global_section_{key}_{language}'
    cached_html = cache.get(cache_key)

    if cached_html is not None:
        return mark_safe(cached_html)

    # Try to load from database
    try:
        section = GlobalSection.objects.get(key=key, is_active=True)

        # Use html_template
        if hasattr(section, 'html_template') and section.html_template:
            # Get translated content
            translations = section.content.get('translations', {}) if hasattr(section, 'content') else {}
            trans = translations.get(language, translations.get('pt', {}))

            # Build context for rendering
            section_context = {
                'section': section,
                'trans': trans,
                'LANGUAGE_CODE': language,
            }
            section_context.update(context.flatten())

            # Render template
            template = Template(section.html_template)
            rendered_html = template.render(Context(section_context))
        else:
            return mark_safe(f'<!-- Global section has no content: {key} -->')

        # Cache the rendered HTML
        cache.set(cache_key, rendered_html, section.cache_duration)

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


@register.simple_tag
def clear_global_section_cache(key):
    """
    Clear cache for a specific global section.
    Usage: {% clear_global_section_cache 'main-header' %}
    """
    from core.models import GlobalSection

    try:
        section = GlobalSection.objects.get(key=key)
        section.clear_cache()
        return ''
    except GlobalSection.DoesNotExist:
        return ''
