"""Translate short editor strings (slide text, alt text) with the engine's HTML translator."""
import html
import logging

from bs4 import BeautifulSoup

from djangopress.editor_v2.components import read_text

logger = logging.getLogger(__name__)


def translate_texts(texts, source_lang, target_lang):
    """The texts translated into target_lang, same order; None on any failure."""
    if not texts:
        return []
    snippet = ''.join(
        f'<p data-i="{i}">{html.escape(t, quote=False).replace(chr(10), "<br>")}</p>'
        for i, t in enumerate(texts)
    )
    try:
        from djangopress.ai.services import ContentGenerationService
        translated = ContentGenerationService().translate_html(snippet, source_lang, target_lang)
    except Exception:
        logger.exception('translate_texts %s->%s failed', source_lang, target_lang)
        return None
    soup = BeautifulSoup(translated or '', 'html.parser')
    out = []
    for i in range(len(texts)):
        el = soup.find(attrs={'data-i': str(i)})
        value = read_text(el) if el is not None else ''
        if not value:
            return None
        out.append(value)
    return out
