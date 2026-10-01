"""Site-wide restyles: find elements by tag and classes on every page (and the
header/footer), then change their classes everywhere in one call."""
from bs4 import BeautifulSoup

from djangopress.site_assistant import changes

MAX_GROUPS = 15


def _split(value):
    if isinstance(value, (list, tuple)):
        value = ' '.join(str(v) for v in value)
    return [v.strip().lower() if v.strip().isalpha() else v.strip() for v in str(value or '').replace(',', ' ').split() if v.strip()]


def _matches(el, tags, has_classes):
    return (not tags or el.name in tags) and set(has_classes) <= set(el.get('class') or [])


def _out(soup):
    html = str(soup)
    return html[12:-14] if html.startswith('<html><body>') else html


def _pages(names):
    from djangopress.core.models import Page
    from djangopress.site_assistant.tools import resolve_page
    if not names or names == 'all' or names == ['all']:
        return list(Page.objects.filter(is_active=True)), []
    names = [names] if isinstance(names, str) else names
    found, missing = [], []
    for name in names:
        page = resolve_page(name)
        (found.append(page) if page else missing.append(str(name)))
    return found, missing


def _globals(include):
    from djangopress.core.models import GlobalSection
    return list(GlobalSection.objects.filter(is_active=True, key__in=['main-header', 'main-footer'])) if include else []


def _default_lang():
    from djangopress.core.models import SiteSettings
    s = SiteSettings.load()
    return s.get_default_language() if s else 'pt'


def find_elements(params, context):
    tags = _split(params.get('tags') or 'a,button')
    has = [c for c in str(params.get('has_classes') or '').split() if c]
    contains = (params.get('text_contains') or '').strip().lower()
    pages, missing = _pages(params.get('pages'))
    if missing:
        return {'success': False, 'message': f'Pages not found: {", ".join(missing)}'}
    lang = _default_lang()
    groups = {}
    sources = [(p.default_title or str(p.pk), (p.html_content_i18n or {}).get(lang, '')) for p in pages]
    sources += [(g.name or g.key, (g.html_template_i18n or {}).get(lang, '')) for g in _globals(True)]
    for label, html in sources:
        for el in BeautifulSoup(html or '', 'html.parser').find_all(True):
            if not _matches(el, tags, has) or (contains and contains not in el.get_text(' ', strip=True).lower()):
                continue
            key = ' '.join(el.get('class') or [])
            group = groups.setdefault(key, {'classes': key, 'tag': el.name, 'count': 0, 'where': [], 'examples': []})
            group['count'] += 1
            section = el.find_parent(attrs={'data-section': True})
            where = f'{label} › {section["data-section"]}' if section else label
            if where not in group['where']:
                group['where'].append(where)
            text = el.get_text(' ', strip=True)[:40]
            if text and text not in group['examples'] and len(group['examples']) < 3:
                group['examples'].append(text)
    ordered = sorted(groups.values(), key=lambda g: -g['count'])
    for g in ordered:
        g['where'] = g['where'][:8]
    shown = ordered[:MAX_GROUPS]
    if not shown:
        return {'success': True, 'groups': [], 'message': 'No matching elements.'}
    lines = [f'{g["count"]}× <{g["tag"]} class="{g["classes"]}"> e.g. {", ".join(g["examples"]) or "-"} '
             f'(in {", ".join(g["where"][:4])}{"…" if len(g["where"]) > 4 else ""})' for g in shown]
    more = f' (+{len(ordered) - MAX_GROUPS} smaller groups)' if len(ordered) > MAX_GROUPS else ''
    return {'success': True, 'groups': shown,
            'message': f'{len(ordered)} style group(s){more}, default language. ' + ' | '.join(lines)}


def restyle_elements(params, context):
    tags = _split(params.get('tags') or 'a,button')
    has = [c for c in str(params.get('has_classes') or '').split() if c]
    add = [c for c in str(params.get('add_classes') or '').split() if c]
    remove = set(c for c in str(params.get('remove_classes') or '').split() if c)
    if not has:
        return {'success': False, 'message': 'Give has_classes (from find_elements) so only those elements change'}
    if not add and not remove:
        return {'success': False, 'message': 'Give add_classes and/or remove_classes'}
    pages, missing = _pages(params.get('pages'))
    if missing:
        return {'success': False, 'message': f'Pages not found: {", ".join(missing)}'}

    def restyle(html):
        soup = BeautifulSoup(html or '', 'html.parser')
        n = 0
        for el in soup.find_all(True):
            if _matches(el, tags, has):
                classes = [c for c in (el.get('class') or []) if c not in remove]
                classes += [c for c in add if c not in classes]
                if classes:
                    el['class'] = classes
                else:
                    el.attrs.pop('class', None)
                n += 1
        return (_out(soup), n) if n else (html, 0)

    report = []
    tracker = (context or {}).get('changes')
    for page in pages:
        copies = dict(page.html_content_i18n or {})
        results = {code: restyle(html) for code, html in copies.items() if html}
        count = max((n for _h, n in results.values()), default=0)
        if not count:
            continue
        changes.page_checkpoint(context, page)
        page.html_content_i18n = {**copies, **{code: h for code, (h, _n) in results.items()}}
        page.save()
        if tracker:
            tracker.touched.setdefault(page.pk, None)
        report.append(f'{page.default_title}: {count}')
    for section in _globals(params.get('include_header_footer')):
        copies = dict(section.html_template_i18n or {})
        results = {code: restyle(html) for code, html in copies.items() if html}
        count = max((n for _h, n in results.values()), default=0)
        if not count:
            continue
        changes.global_section_checkpoint(context, section)
        section.html_template_i18n = {**copies, **{code: h for code, (h, _n) in results.items()}}
        section.save()
        report.append(f'{section.name or section.key}: {count}')
    if not report:
        return {'success': False, 'message': 'No element matched; call find_elements to see the real classes.'}
    return {'success': True, 'message': 'Restyled (elements per page, every language): ' + ', '.join(report)}


STYLE_TOOLS = {
    'find_elements': find_elements,
    'restyle_elements': restyle_elements,
}
