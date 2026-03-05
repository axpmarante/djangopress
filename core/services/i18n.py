"""i18n helpers for the service layer.

Builds complete i18n dicts from single-language values by auto-translating
to other enabled languages. Uses gemini-lite for translation.
"""

from django.utils.text import slugify


def _get_language_config():
    """Get enabled languages and default language from SiteSettings."""
    from core.models import SiteSettings
    settings = SiteSettings.load()
    default_lang = settings.get_default_language() if settings else 'pt'
    all_langs = settings.get_language_codes() if settings else [default_lang]
    return default_lang, all_langs


def _translate_text(text, source_lang, target_lang):
    """Translate text using the LLM translation pipeline.

    Uses gemini-lite. Falls back to original text if translation fails.
    """
    try:
        from ai.utils.llm_config import LLMBase
        llm = LLMBase()
        messages = [
            {'role': 'system', 'content': (
                f'Translate the following text from {source_lang} to {target_lang}. '
                f'Return ONLY the translated text, nothing else.'
            )},
            {'role': 'user', 'content': text},
        ]
        response = llm.get_completion(messages, tool_name='gemini-lite')
        translated = response.choices[0].message.content.strip()
        return translated if translated else text
    except Exception:
        return text


def build_i18n_field(value=None, value_i18n=None):
    """Build a complete i18n dict from a single-language value or partial dict.

    Args:
        value: Text in the default language (auto-translated to others).
        value_i18n: Explicit per-language dict. If all languages present, used as-is.
                    If partial, missing languages are auto-translated.

    Returns:
        Dict with a key for every enabled language.

    Raises:
        ValueError: If neither value nor value_i18n provided.
    """
    if not value and not value_i18n:
        raise ValueError('Provide value or value_i18n')

    default_lang, all_langs = _get_language_config()

    result = dict(value_i18n or {})

    if value and default_lang not in result:
        result[default_lang] = value

    if all(lang in result and result[lang] for lang in all_langs):
        return result

    source_lang = default_lang if default_lang in result else next(iter(result))
    source_text = result[source_lang]

    for lang in all_langs:
        if lang not in result or not result[lang]:
            result[lang] = _translate_text(source_text, source_lang, lang)

    return result


def auto_generate_slugs(title_i18n, slug=None, slug_i18n=None):
    """Generate slug_i18n from title_i18n.

    Args:
        title_i18n: Complete title dict.
        slug: Optional explicit slug for the default language.
        slug_i18n: Optional explicit slugs (overrides if complete).

    Returns:
        Dict with a slug for every language in title_i18n.
    """
    if slug_i18n and len(slug_i18n) >= len(title_i18n):
        return slug_i18n

    default_lang, _ = _get_language_config()
    result = dict(slug_i18n or {})

    for lang, title in title_i18n.items():
        if lang not in result:
            result[lang] = slugify(title)

    if slug:
        result[default_lang] = slug

    return result
