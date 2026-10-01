"""Buttons under an assistant reply: the pages it worked on or talks about
(view at the touched section / edit in the editor), and the backoffice screens
it sends the user to. Built from the turn's tools and text, never by the model,
so every link points somewhere real."""
import re

from django.urls import Resolver404, resolve

BACKOFFICE_PATH_RE = re.compile(r'/backoffice/[\w\-/]*')

SCREEN_LABELS = {
    'media': 'Media library', 'media_upload': 'Upload images', 'media_bulk_upload': 'Upload images',
    'pages': 'Pages', 'forms': 'Forms', 'menu': 'Navigation', 'news_list': 'News',
    'settings': 'Settings', 'settings_general': 'General settings', 'settings_contact': 'Contact settings',
    'settings_seo': 'SEO settings', 'settings_design': 'Design settings', 'settings_languages': 'Languages',
    'settings_integrations': 'Integrations', 'header_edit': 'Edit header', 'footer_edit': 'Edit footer',
}
TOOL_SCREENS = {
    'validate_contacts': 'settings_contact',
    'update_settings': 'settings_general',
    'refine_header': 'header_edit',
    'refine_footer': 'footer_edit',
}
FORM_TOOLS = {'test_form', 'create_form', 'update_form'}


def _page_buttons(page, section=None):
    title = page.default_title or f'Page {page.pk}'
    url = page.get_absolute_url()
    preview = '' if page.is_active else 'preview=true'
    view = url + (f'?{preview}' if preview else '') + (f'#{section}' if section else '')
    edit = url + '?' + (f'{preview}&' if preview else '') + 'edit=v2'
    return [{'label': f'View {title}', 'url': view, 'kind': 'view'},
            {'label': f'Edit {title}', 'url': edit, 'kind': 'edit'}]


def _mentioned_pages(text, pages):
    """Pages named in bold or right after "página"/"page" — a title in plain prose isn't enough."""
    found = []
    for page in pages:
        for title in {t for t in (page.title_i18n or {}).values() if t}:
            t = re.escape(title)
            if re.search(rf'\*\*\s*{t}\s*\*\*|\b(?:página|pagina|page)\s+[*"“«]*{t}\b', text, re.IGNORECASE):
                found.append(page)
                break
    return found


def _screen(path):
    try:
        match = resolve(path)
    except Resolver404:
        return None
    if match.namespace != 'backoffice' or match.url_name not in SCREEN_LABELS:
        return None
    return {'label': SCREEN_LABELS[match.url_name], 'url': path, 'kind': 'screen'}


def _forms(actions):
    from djangopress.core.models import DynamicForm
    slugs, ids = [], []
    for a in actions:
        if a.get('tool') not in FORM_TOOLS or not a.get('success'):
            continue
        params = a.get('params') or {}
        slugs += [params.get('slug')] + [c.get('form') for c in a.get('checks') or []]
        ids += [params.get('form_id'), a.get('form_id')]
    forms = list(DynamicForm.objects.filter(slug__in=[s for s in slugs if s])) + \
        list(DynamicForm.objects.filter(pk__in=[i for i in ids if isinstance(i, int)]))
    out = []
    for form in dict((f.pk, f) for f in forms).values():
        out += [{'label': f'Form {form.name}', 'url': f'/backoffice/forms/{form.pk}/edit/', 'kind': 'screen'},
                {'label': f'{form.name} submissions', 'url': f'/backoffice/forms/{form.pk}/submissions/', 'kind': 'screen'}]
    return out


def build_links(text, actions, touched=None):
    """[{label, url, kind}] — kind is 'view' (public page), 'edit' (editor) or 'screen' (backoffice)."""
    from djangopress.core.models import Page
    touched = dict(touched or {})
    text = text or ''
    pages = {p.pk: p for p in Page.objects.all()}

    # Pages changed or named in the reply; pages the tools only looked at count when there are none.
    order = list(touched) + [p.pk for p in _mentioned_pages(text, pages.values())]
    if not order:
        for a in actions:
            if a.get('success'):
                pk = (a.get('params') or {}).get('page_id') or a.get('page_id')
                if isinstance(pk, int):
                    order.append(pk)

    out = []
    for pk in dict.fromkeys(order):
        if pk in pages:
            out += _page_buttons(pages[pk], touched.get(pk))
    out += _forms(actions)
    for a in actions:
        name = TOOL_SCREENS.get(a.get('tool'))
        if name and a.get('success'):
            from django.urls import reverse
            out.append({'label': SCREEN_LABELS[name], 'url': reverse(f'backoffice:{name}'), 'kind': 'screen'})
    for raw in BACKOFFICE_PATH_RE.findall(text):
        path = raw if raw.endswith('/') else raw + '/'
        screen = _screen(path)
        if screen:
            out.append(screen)

    seen, unique = set(), []
    for link in out:
        if link['label'] not in seen:
            seen.add(link['label'])
            unique.append(link)
    return unique
