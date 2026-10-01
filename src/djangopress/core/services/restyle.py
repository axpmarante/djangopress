"""Find elements by tag and classes across the site (active pages, and the
header/footer when asked) and change their classes in every language.
Shared by the site assistant (find_elements / restyle_elements) and the
editor's "Apply to all similar"."""
import re

from bs4 import BeautifulSoup

RUNTIME_CLASS_RE = re.compile(r'^(ev2-|is-(active|visible|prev|next|initialized|rendered|overflow|focus-in)$|splide--|splide__slide--clone$)')


def real_classes(classes):
    return [c for c in (classes or []) if c and not RUNTIME_CLASS_RE.match(c)]


def matcher(tags=(), has_classes=(), exact_classes=None, text_contains=''):
    tags = {t.lower() for t in tags or ()}
    has = set(has_classes or ())
    exact = set(real_classes(exact_classes)) if exact_classes is not None else None
    needle = (text_contains or '').strip().lower()

    def matches(el):
        if tags and el.name not in tags:
            return False
        classes = set(real_classes(el.get('class')))
        if exact is not None and classes != exact:
            return False
        if not has <= classes:
            return False
        return not needle or needle in el.get_text(' ', strip=True).lower()
    return matches


def _default_lang():
    from djangopress.core.models import SiteSettings
    s = SiteSettings.load()
    return s.get_default_language() if s else 'pt'


def _sources(pages, include_globals):
    from djangopress.core.models import GlobalSection, Page
    pages = list(Page.objects.filter(is_active=True)) if pages is None else list(pages)
    out = [('page', p, p.default_title or str(p.pk)) for p in pages]
    if include_globals:
        out += [('global', g, g.name or g.key)
                for g in GlobalSection.objects.filter(is_active=True, key__in=['main-header', 'main-footer'])]
    return out


def _copies(kind, obj):
    return dict((obj.html_content_i18n if kind == 'page' else obj.html_template_i18n) or {})


def _out(soup):
    html = str(soup)
    return html[12:-14] if html.startswith('<html><body>') else html


def find(match, pages=None, include_globals=False, lang=None):
    """[{kind, obj, label, section, tag, classes, text}] in the default-language copy."""
    lang = lang or _default_lang()
    found = []
    for kind, obj, label in _sources(pages, include_globals):
        html = _copies(kind, obj).get(lang, '')
        for el in BeautifulSoup(html or '', 'html.parser').find_all(True):
            if match(el):
                section = el.find_parent(attrs={'data-section': True})
                found.append({'kind': kind, 'obj': obj, 'label': label,
                              'section': section['data-section'] if section else None,
                              'tag': el.name, 'classes': ' '.join(el.get('class') or []),
                              'text': el.get_text(' ', strip=True)})
    return found


def apply(match, add=(), remove=(), pages=None, include_globals=False, checkpoint=None):
    """Change the matching elements' classes in every language copy.
    `checkpoint(kind, obj)` runs before a page/section is first changed.
    Returns [{kind, obj, label, count}] (count = elements in the copy with most matches)."""
    add, remove = list(add or ()), set(remove or ())

    def restyle(html):
        soup = BeautifulSoup(html or '', 'html.parser')
        n = 0
        for el in soup.find_all(True):
            if match(el):
                classes = [c for c in (el.get('class') or []) if c not in remove]
                classes += [c for c in add if c not in classes]
                if classes:
                    el['class'] = classes
                else:
                    el.attrs.pop('class', None)
                n += 1
        return (_out(soup), n) if n else (html, 0)

    report = []
    for kind, obj, label in _sources(pages, include_globals):
        copies = _copies(kind, obj)
        results = {code: restyle(html) for code, html in copies.items() if html}
        count = max((n for _h, n in results.values()), default=0)
        if not count:
            continue
        if checkpoint:
            checkpoint(kind, obj)
        merged = {**copies, **{code: h for code, (h, _n) in results.items()}}
        if kind == 'page':
            obj.html_content_i18n = merged
        else:
            obj.html_template_i18n = merged
        obj.save()
        report.append({'kind': kind, 'obj': obj, 'label': label, 'count': count})
    return report
