"""
One save path for AI-generated HTML (editor AI Refine, new section, element,
whole page; the site assistant's refine tools).

Every apply: checkpoint first (Undo covers it), write the language being edited,
translate the change into every other language that has content, rewrite
internal links for that language, and report what could not be translated.
Pages keep the same structure in every language.
"""
import copy
import html as html_lib
import re

from bs4 import BeautifulSoup, Comment

from djangopress.core.models import Page, SiteSettings
from djangopress.editor_v2 import structure


def translate_snippet(html, source_lang, target_lang):
    """Translate an HTML snippet with the engine's translation model."""
    from djangopress.ai.services import ContentGenerationService
    from djangopress.ai.utils.llm_config import get_ai_model
    return ContentGenerationService(model_name=get_ai_model('translation')).translate_html(html, source_lang, target_lang)


def _soup(html):
    return BeautifulSoup(html or '', 'html.parser')


def _out(soup):
    html = str(soup)
    return html[12:-14] if html.startswith('<html><body>') else html


def _first_tag(html):
    return next((t for t in _soup(html).contents if getattr(t, 'name', None)), None)


def localize_internal_links(html, source_lang, target_lang):
    """/pt/reservas/#x -> /en/book-a-table/#x. Unknown slugs and deeper paths only
    swap the language prefix; external links and anchors are untouched."""
    if source_lang == target_lang:
        return html
    slugs = {}
    for page in Page.objects.all():
        src = (page.slug_i18n or {}).get(source_lang)
        if src:
            slugs[src] = (page.slug_i18n or {}).get(target_lang) or src
    pattern = re.compile(rf'^/{re.escape(source_lang)}(?=/|$)(?P<path>/[^?#]*)?(?P<rest>[?#].*)?$')
    soup = _soup(html)
    for a in soup.find_all(href=True):
        m = pattern.match(a['href'])
        if not m:
            continue
        segments = [s for s in (m.group('path') or '/').split('/') if s]
        if len(segments) == 1:
            segments = [slugs.get(segments[0], segments[0])]
        path = '/' + '/'.join(segments) + '/' if segments else '/'
        a['href'] = f'/{target_lang}{path}{m.group("rest") or ""}'
    return _out(soup)


def _languages(page, source_lang):
    """(source, others): the copy being written and the other non-empty copies."""
    settings = SiteSettings.load()
    default = settings.get_default_language() if settings else 'pt'
    html_i18n = page.html_content_i18n or {}
    source = source_lang if html_i18n.get(source_lang) else default
    others = [code for code in (settings.get_language_codes() if settings else html_i18n.keys())
              if code != source and html_i18n.get(code)]
    return source, others


def _checkpoint(page, user, summary):
    if not hasattr(page, 'create_version'):
        return
    if isinstance(page, Page):
        page.create_version(user=user, change_summary=summary, kind='checkpoint')
    else:
        page.create_version(change_summary=summary)


def _translate_one(fragment_html, source, target):
    """Raw translation or None; runs in a worker thread (no ORM work besides the AI call log)."""
    from django.db import connection
    try:
        translated = translate_snippet(fragment_html, source, target)
        return translated if translated and _first_tag(translated) else None
    except Exception:
        return None
    finally:
        connection.close()


def _translations(fragment_html, source, targets):
    """{target: (html, ok)} — all languages translated in parallel (a whole page per language
    can take a minute; in series several languages would outlast the request timeout), then
    links localized here, on the request thread."""
    from concurrent.futures import ThreadPoolExecutor
    if not targets:
        return {}
    with ThreadPoolExecutor(max_workers=len(targets)) as pool:
        raw = dict(zip(targets, pool.map(lambda t: _translate_one(fragment_html, source, t), targets)))
    return {t: (localize_internal_links(raw[t] or fragment_html, source, t), raw[t] is not None) for t in targets}


TEXT_ATTRS = ('alt', 'title', 'aria-label', 'placeholder', 'value', 'label', 'data-alt', 'data-title', 'data-caption',
              'aria-description', 'aria-valuetext', 'aria-roledescription')


def _tags(tag):
    return [tag, *tag.find_all(True)]


def _signature(tag):
    """What a translation would change: visible text and text-bearing attributes, in order."""
    texts = [' '.join(t.split()) for t in tag.find_all(string=True) if not isinstance(t, Comment) and t.strip()]
    attrs = [(el.name, a, el.get(a)) for el in _tags(tag) for a in TEXT_ATTRS if el.get(a)]
    return texts, attrs


def _shape(tag):
    return [el.name for el in _tags(tag)]


def _localized_href(href, source, target):
    return _soup(localize_internal_links(f'<a href="{html_lib.escape(href)}"></a>', source, target)).a['href']


def _copy_attributes(old_source, new_source, target_tag, source, target):
    """The other language's copy with every attribute the source edit changed, or None when
    its structure differs (then it is translated instead)."""
    if target_tag is None or not (_shape(old_source) == _shape(new_source) == _shape(target_tag)):
        return None
    result = copy.copy(target_tag)
    for old, new, el in zip(_tags(old_source), _tags(new_source), _tags(result)):
        for key in set(old.attrs) | set(new.attrs):
            before, after = old.get(key), new.get(key)
            if before == after:
                continue
            if after is None:
                del el[key]
            else:
                el[key] = _localized_href(after, source, target) if key == 'href' else copy.copy(after)
    return result


def _rename_section(tag, old, new):
    tag['data-section'] = new
    tag['id'] = new
    for a in tag.find_all('a', href=f'#{old}'):
        a['href'] = f'#{new}'


def apply_section_html(page, html, source_lang, *, section_name=None, mode='replace', insert_after=None, user=None, checkpoint=True):
    new = _soup(html).find('section')
    if new is None:
        raise ValueError('The AI output has no <section>')
    source, others = _languages(page, source_lang)
    html_i18n = dict(page.html_content_i18n or {})

    if mode == 'insert':
        used = set()
        for copy_html in html_i18n.values():
            used |= {s.get('data-section') for s in _soup(copy_html).find_all('section')}
        name = new.get('data-section') or 'section'
        if name in used:
            fresh = structure.next_free_section_name(_soup(''), name, extra_used=used)
            _rename_section(new, name, fresh)
            name = fresh
        else:
            _rename_section(new, name, name)
    else:
        name = section_name or new.get('data-section')
        _rename_section(new, new.get('data-section') or name, name)

    def put(code, tag):
        soup = _soup(html_i18n.get(code))
        if mode == 'insert':
            anchor = soup.find('section', attrs={'data-section': insert_after}) if insert_after else None
            if anchor is not None:
                anchor.insert_after(tag)
            elif insert_after is None and soup.find('section') is not None:
                soup.find('section').insert_before(tag)
            else:
                soup.append(tag)
        else:
            old = soup.find('section', attrs={'data-section': name})
            if old is None:
                return False
            old.replace_with(tag)
        html_i18n[code] = _out(soup)
        return True

    old_source = None if mode == 'insert' else _soup(html_i18n.get(source)).find('section', attrs={'data-section': name})
    if checkpoint:
        _checkpoint(page, user, f'AI {"new section" if mode == "insert" else "section"} "{name}"')
    if not put(source, new):
        raise ValueError(f'Section "{name}" not found')

    translated, untranslated = [], []
    if old_source is not None and _signature(old_source) == _signature(new):
        # Same text: copy the attribute changes, no translation needed.
        for code in list(others):
            copied = _copy_attributes(old_source, new, _soup(html_i18n.get(code)).find('section', attrs={'data-section': name}),
                                      source, code)
            if copied is not None and put(code, copied):
                translated.append(code)
                others.remove(code)
    results = _translations(str(new), source, others)
    for code in others:
        fragment, ok = results[code]
        tag = _soup(fragment).find('section') or copy.copy(new)
        _rename_section(tag, tag.get('data-section') or name, name)
        if not put(code, tag):
            untranslated.append(code)
            continue
        (translated if ok else untranslated).append(code)

    page.html_content_i18n = html_i18n
    page.save()
    return {'section_name': name, 'translated_languages': translated, 'untranslated_languages': untranslated,
            'html': str(new)}


def apply_element_html(page, selector, html, source_lang, *, user=None, checkpoint=True):
    new = _first_tag(html)
    if new is None or new.name == 'section':
        raise ValueError('Element output must be one element, not a section')
    source, others = _languages(page, source_lang)
    html_i18n = dict(page.html_content_i18n or {})

    def put(code, tag):
        soup = _soup(html_i18n.get(code))
        old = soup.select_one(selector)
        if old is None:
            return False
        old.replace_with(tag)
        html_i18n[code] = _out(soup)
        return True

    old_source = _soup(html_i18n.get(source)).select_one(selector)
    if checkpoint:
        _checkpoint(page, user, 'AI element edit')
    if not put(source, new):
        raise ValueError('Element not found for selector')
    translated, untranslated = [], []
    if old_source is not None and _signature(old_source) == _signature(new):
        for code in list(others):
            copied = _copy_attributes(old_source, new, _soup(html_i18n.get(code)).select_one(selector), source, code)
            if copied is not None and put(code, copied):
                translated.append(code)
                others.remove(code)
    results = _translations(str(new), source, others)
    for code in others:
        fragment, ok = results[code]
        tag = _first_tag(fragment) or copy.copy(new)
        if not put(code, tag):
            untranslated.append(code)
            continue
        (translated if ok else untranslated).append(code)
    page.html_content_i18n = html_i18n
    page.save()
    return {'translated_languages': translated, 'untranslated_languages': untranslated, 'html': str(new)}


def apply_page_html(page, html, source_lang, *, user=None, checkpoint=True):
    if not _soup(html).find('section'):
        raise ValueError('The AI output has no <section>')
    source, others = _languages(page, source_lang)
    html_i18n = dict(page.html_content_i18n or {})
    if checkpoint:
        _checkpoint(page, user, 'AI page refine')
    html_i18n[source] = html
    translated, untranslated = [], []
    results = _translations(html, source, others)
    for code in others:
        fragment, ok = results[code]
        html_i18n[code] = fragment
        (translated if ok else untranslated).append(code)
    page.html_content_i18n = html_i18n
    page.save()
    return {'translated_languages': translated, 'untranslated_languages': untranslated}
