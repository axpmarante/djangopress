"""Site-wide restyles: find elements by tag and classes on every page (and the
header/footer), then change their classes everywhere in one call."""
from djangopress.core.services import restyle as restyle_service
from djangopress.site_assistant import changes

MAX_GROUPS = 15


def _split(value):
    if isinstance(value, (list, tuple)):
        value = ' '.join(str(v) for v in value)
    return [v.strip().lower() if v.strip().isalpha() else v.strip() for v in str(value or '').replace(',', ' ').split() if v.strip()]


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


def find_elements(params, context):
    tags = _split(params.get('tags') or 'a,button')
    has = [c for c in str(params.get('has_classes') or '').split() if c]
    contains = (params.get('text_contains') or '').strip().lower()
    pages, missing = _pages(params.get('pages'))
    if missing:
        return {'success': False, 'message': f'Pages not found: {", ".join(missing)}'}
    groups = {}
    match = restyle_service.matcher(tags, has_classes=has, text_contains=contains)
    for hit in restyle_service.find(match, pages=pages, include_globals=True):
        key = hit['classes']
        group = groups.setdefault(key, {'classes': key, 'tag': hit['tag'], 'count': 0, 'where': [], 'examples': []})
        group['count'] += 1
        where = f"{hit['label']} › {hit['section']}" if hit['section'] else hit['label']
        if where not in group['where']:
            group['where'].append(where)
        text = hit['text'][:40]
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

    tracker = (context or {}).get('changes')

    def checkpoint(kind, obj):
        if kind == 'page':
            changes.page_checkpoint(context, obj)
            if tracker:
                tracker.touched.setdefault(obj.pk, None)
        else:
            changes.global_section_checkpoint(context, obj)

    done = restyle_service.apply(restyle_service.matcher(tags, has_classes=has), add=add, remove=remove,
                                 pages=pages, include_globals=bool(params.get('include_header_footer')),
                                 checkpoint=checkpoint)
    report = [f"{r['label']}: {r['count']}" for r in done]
    if not report:
        return {'success': False, 'message': 'No element matched; call find_elements to see the real classes.'}
    return {'success': True, 'message': 'Restyled (elements per page, every language): ' + ', '.join(report)}


STYLE_TOOLS = {
    'find_elements': find_elements,
    'restyle_elements': restyle_elements,
}
